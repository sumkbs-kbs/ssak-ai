from __future__ import annotations

import atexit
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from typing import Protocol
from urllib.parse import urlparse
from urllib.request import Request

from antigravity_k.tools.egress_policy import safe_urlopen


class _Process(Protocol):
    def poll(self) -> int | None: ...

    def terminate(self) -> None: ...


class LocalRuntimeSupervisor:
    def __init__(self, *, process_factory: Callable[..., _Process] | None = None) -> None:
        self._process_factory: Callable[..., _Process] = process_factory or subprocess.Popen
        self._processes: dict[str, _Process] = {}
        _ = atexit.register(self.shutdown)

    def ensure_available(self, profile: object) -> str:
        from pathlib import Path

        provider = str(getattr(profile, "provider", "")).casefold()
        api_base = str(getattr(profile, "api_base", ""))
        repo = str(getattr(profile, "repo", ""))
        disk_path = str(getattr(profile, "disk_path", ""))
        name = str(getattr(profile, "name", repo))

        def _is_gguf(target: Path) -> bool:
            if not target.is_file():
                return False
            if target.suffix.casefold() == ".gguf":
                return True
            try:
                with open(target, "rb") as f:
                    return f.read(4) == b"GGUF"
            except OSError:
                return False

        # 실제 GGUF 파일 경로 탐색
        model_file = ""
        if disk_path:
            p = Path(disk_path)
            if _is_gguf(p):
                model_file = str(p)
            elif p.is_dir():
                shards = sorted(p.rglob("*"))
                gguf_shards = [s for s in shards if _is_gguf(s)]
                shard1 = [s for s in gguf_shards if "-00001-of-" in s.name or "_00001" in s.name]
                if shard1:
                    model_file = str(shard1[0])
                elif gguf_shards:
                    main_shards = [s for s in gguf_shards if not s.name.startswith("mmproj")]
                    model_file = str(main_shards[0] if main_shards else gguf_shards[0])
        elif repo and (repo.casefold().endswith(".gguf") or (Path(repo).exists() and _is_gguf(Path(repo)))):
            model_file = repo
        elif name and name.casefold().endswith(".gguf"):
            model_file = name

        is_gguf = bool(model_file)
        if not is_gguf or provider not in {"llama.cpp", "llamacpp", "unsloth"}:
            return api_base

        if not api_base:
            api_base = os.getenv("AGK_LLAMA_CPP_API_BASE", "http://127.0.0.1:8080/v1")
            setattr(profile, "api_base", api_base)

        process = self._processes.get(name)
        if process is not None and process.poll() is None:
            if self._probe(api_base, expected_model=model_file):
                return api_base

        # 현재 실행 중인 서버가 이미 요청한 모델을 서비스하고 있는지 확인
        if self._probe(api_base, expected_model=model_file):
            return api_base

        binary = self._resolve_binary()
        if not binary:
            raise RuntimeError(
                f"GGUF 모델 '{name}'을 실행하려면 llama-server가 필요합니다. llama.cpp를 설치하거나 "
                + "AGK_LLAMA_SERVER_BIN을 설정하세요."
            )

        # 기존에 다른 모델이 8080 포트를 점유하고 있으면 종료 후 새 모델 기동
        for existing_name, existing_proc in list(self._processes.items()):
            if existing_proc.poll() is None:
                existing_proc.terminate()
                self._processes.pop(existing_name, None)

        parsed = urlparse(api_base)
        port = parsed.port or 8080
        raw_ctx = getattr(profile, "context_length", 0) or 0
        ctx_size = max(16384, min(int(raw_ctx) if raw_ctx else 16384, 32768))
        cmd = [
            binary,
            "-m",
            model_file,
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "-c",
            str(ctx_size),
            "-ngl",
            "99",
            "--reasoning-preserve",
        ]

        log_file = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            errors="replace",
            prefix=f"agk_llama_server_{port}_",
            suffix=".log",
            delete=False,
        )
        log_path = log_file.name
        process = self._process_factory(
            cmd,
            stdout=log_file,
            stderr=log_file,
            start_new_session=True,
        )
        self._processes[name] = process

        if not self._wait_until_available(api_base, timeout=60.0, process=process):
            process.terminate()
            _ = self._processes.pop(name, None)
            err_details = self._extract_recent_log_errors(log_path)
            detail_str = f": {err_details}" if err_details else ""
            raise RuntimeError(f"llama-server가 모델 '{name}'을 준비하지 못했습니다{detail_str}.")
        return api_base

    @classmethod
    def _resolve_binary(cls) -> str:
        binary = os.getenv("AGK_LLAMA_SERVER_BIN", "").strip() or shutil.which("llama-server")
        if binary and os.path.exists(binary):
            return binary
        for candidate in ("/opt/homebrew/bin/llama-server", "/usr/local/bin/llama-server"):
            if os.path.exists(candidate):
                return candidate
        return ""

    @staticmethod
    def _extract_recent_log_errors(log_path: str) -> str:
        if not os.path.exists(log_path):
            return ""
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                lines = [ln.strip() for ln in f.readlines() if ln.strip()]
            error_keywords = ("error", "failed", "unknown", "abort", "assert", "exception", "fatal")
            err_lines = [ln for ln in lines if any(k in ln.lower() for k in error_keywords)]
            if err_lines:
                return " | ".join(err_lines[-3:])
            if lines:
                return " | ".join(lines[-3:])
        except OSError:
            pass
        return ""

    def shutdown(self) -> None:
        for name, process in tuple(self._processes.items()):
            if process.poll() is None:
                process.terminate()
            _ = self._processes.pop(name, None)

    @staticmethod
    def _probe(api_base: str, expected_model: str = "") -> bool:
        import json
        from pathlib import Path

        try:
            request = Request(f"{api_base.rstrip('/')}/models")
            with safe_urlopen(request, timeout=1) as response:
                if not expected_model or not hasattr(response, "read"):
                    return True
                try:
                    payload = json.loads(response.read().decode("utf-8"))
                    models = payload.get("data", []) or payload.get("models", [])
                    if not models:
                        return True
                    loaded_ids = [str(m.get("id", "") or m.get("name", "") or m.get("model", "")) for m in models]
                    exp_name = Path(expected_model).name
                    exp_stem = Path(expected_model).stem
                    exp_real = str(Path(expected_model).resolve()) if Path(expected_model).exists() else expected_model
                    return any(
                        exp_name in lid
                        or exp_stem in lid
                        or exp_real in lid
                        or lid in exp_real
                        or expected_model in lid
                        for lid in loaded_ids
                    )
                except Exception:
                    return True
        except (OSError, TimeoutError, ValueError):
            return False

    @classmethod
    def _wait_until_available(
        cls,
        api_base: str,
        timeout: float = 30.0,
        process: _Process | None = None,
    ) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if process is not None and process.poll() is not None:
                return False
            if cls._probe(api_base):
                return True
            time.sleep(0.25)
        return False
