from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import ClassVar, cast
from urllib.parse import urlparse
from urllib.request import Request

from pydantic import ValidationError

from antigravity_k.engine.ollama_process_snapshot import OllamaProcessSnapshot
from antigravity_k.tools.egress_policy import safe_urlopen

logger = logging.getLogger("antigravity_k.local_model_discovery")

# CR-14 attempt-039 — hermetic ambient 전용 허브 시드(AGK_SEED_LOCAL_HUB).
# 생산 경로에서는 환경변수가 없으므로 동작하지 않는다. 실 unsloth/GPU 없이
# ModelHubPage 의 `.hub-card` + `실행 중` 배지를 게이트가 소유하기 위한 픽스처다.
HERMETIC_HUB_MODEL_ID = "orpheus-3b-0.1-ft-UD-Q4_K_XL"


def hermetic_local_hub_seed_enabled() -> bool:
    raw = os.getenv("AGK_SEED_LOCAL_HUB", "").strip().lower()
    return raw in {"1", "true", "yes", "hub"}


def hermetic_local_hub_fixture() -> DiscoveredLocalModel:
    """게이트 전용 픽스처 — 실 런타임 API 베이스가 아닌 닫힌 loopback."""
    return DiscoveredLocalModel(
        name=HERMETIC_HUB_MODEL_ID,
        repo=f"unsloth/{HERMETIC_HUB_MODEL_ID}",
        provider="unsloth",
        api_base="http://127.0.0.1:9/v1",
        role="audio",
        parameter_count_b=3.0,
        estimated_memory_gb=2.0,
        context_length=4096,
        quantization="UD-Q4_K_XL",
        capabilities=("audio",),
        source="hermetic_seed",
        disk_path=f"[hermetic-fixture]/{HERMETIC_HUB_MODEL_ID}",
        disk_size_gb=1.99,
        status="running",
    )


def apply_hermetic_local_hub_seed(
    models: Sequence[DiscoveredLocalModel],
) -> tuple[DiscoveredLocalModel, ...]:
    """시드 ON 일 때 명명 모델을 running 으로 올리거나 없으면 픽스처를 넣는다."""
    if not hermetic_local_hub_seed_enabled():
        return tuple(models)
    target = HERMETIC_HUB_MODEL_ID.casefold()
    updated: list[DiscoveredLocalModel] = []
    found = False
    for model in models:
        if model.name.casefold() == target:
            found = True
            updated.append(
                replace(
                    model,
                    status="running",
                    source=model.source or "hermetic_seed",
                    provider=model.provider or "unsloth",
                    quantization=model.quantization or "UD-Q4_K_XL",
                )
            )
        else:
            updated.append(model)
    if not found:
        updated.insert(0, hermetic_local_hub_fixture())
    return tuple(updated)


@dataclass(frozen=True, slots=True)
class DiscoveredLocalModel:
    name: str
    repo: str
    provider: str
    api_base: str
    role: str
    parameter_count_b: float = 0.0
    estimated_memory_gb: float = 0.0
    context_length: int = 0
    quantization: str = ""
    capabilities: tuple[str, ...] = ()
    source: str = ""
    disk_path: str = ""
    disk_size_gb: float = 0.0
    status: str = ""


class LocalModelDiscovery:
    _default_model_dirs: ClassVar[tuple[Path, ...]] = (
        Path("~/.cache/huggingface/hub").expanduser(),
        Path("~/models").expanduser(),
        Path("~/Library/Application Support/LM Studio/models").expanduser(),
    )

    def __init__(
        self,
        *,
        model_dirs: Sequence[Path] | None = None,
        openai_endpoints: Sequence[tuple[str, str]] | None = None,
        disable_network: bool = False,
    ) -> None:
        self._custom_model_dirs: bool = model_dirs is not None
        self._model_dirs: tuple[Path, ...] = (
            tuple(model_dirs) if model_dirs is not None else self._configured_model_dirs()
        )
        self._openai_endpoints: tuple[tuple[str, str], ...] = (
            tuple(openai_endpoints) if openai_endpoints is not None else self._configured_openai_endpoints()
        )
        self._disable_network: bool = disable_network

    def discover(self) -> tuple[DiscoveredLocalModel, ...]:
        found: list[DiscoveredLocalModel] = []
        if not self._disable_network:
            found.extend(self._discover_ollama())
            for provider, base_url in self._openai_endpoints:
                found.extend(self._discover_openai(provider, base_url))
        found.extend(self._discover_huggingface_cache())
        found.extend(self._discover_filesystem())
        deduped = self._deduplicate(found)
        # attempt-039: AGK_SEED_LOCAL_HUB 일 때만 허브 픽스처(실행 중) 적용
        return apply_hermetic_local_hub_seed(deduped)

    def _discover_ollama(self) -> tuple[DiscoveredLocalModel, ...]:
        base_url = os.getenv("AGK_OLLAMA_API_BASE", "http://127.0.0.1:11434").rstrip("/")
        payload = self._request_json(f"{base_url}/api/tags")
        if payload is None:
            return ()
        raw_models = payload.get("models")
        if not isinstance(raw_models, list):
            return ()
        running_names: frozenset[str] | None = None
        process_payload = self._request_json(f"{base_url}/api/ps")
        if process_payload is not None:
            try:
                running_names = OllamaProcessSnapshot.model_validate(process_payload).names
            except ValidationError:
                running_names = None
        models: list[DiscoveredLocalModel] = []
        for raw in _items(cast(object, raw_models)):
            item = _mapping(raw)
            if item is None:
                continue
            name = _text(item.get("name")) or _text(item.get("model"))
            if not name:
                continue
            details = _mapping(item.get("details")) or {}
            size = _number(item.get("size"))
            parameter_count = _parameter_count(details.get("parameter_size"))
            if parameter_count <= 0:
                parameter_count = _parameter_count(name)
            capabilities = _strings(item.get("capabilities"))
            models.append(
                DiscoveredLocalModel(
                    name=name,
                    repo=_text(item.get("model")) or name,
                    provider="ollama",
                    api_base=base_url,
                    role=_infer_role(name, details.get("family")),
                    parameter_count_b=parameter_count,
                    estimated_memory_gb=size / (1024**3) if size > 0 else 0.0,
                    context_length=int(_number(details.get("context_length"))),
                    quantization=_text(details.get("quantization_level")),
                    capabilities=capabilities,
                    source="ollama",
                    status="unknown"
                    if running_names is None
                    else ("running" if name in running_names else "installed"),
                ),
            )
        return tuple(models)

    def _discover_openai(self, provider: str, base_url: str) -> tuple[DiscoveredLocalModel, ...]:
        payload = self._request_json(f"{base_url.rstrip('/')}/models")
        if payload is None:
            return ()
        raw_models = payload.get("data")
        if not isinstance(raw_models, list):
            return ()
        models: list[DiscoveredLocalModel] = []
        for raw in _items(cast(object, raw_models)):
            item = _mapping(raw)
            if item is None:
                continue
            name = _text(item.get("id"))
            if not name:
                continue
            parameter_count = _parameter_count(item.get("parameter_count_b"))
            if parameter_count <= 0:
                parameter_count = _parameter_count(name)
            models.append(
                DiscoveredLocalModel(
                    name=name,
                    repo=name,
                    provider=provider,
                    api_base=base_url.rstrip("/"),
                    role=_infer_role(name, item.get("family")),
                    parameter_count_b=parameter_count,
                    estimated_memory_gb=_number(item.get("estimated_memory_gb")),
                    context_length=int(_number(item.get("context_length"))),
                    quantization=_text(item.get("quantization")),
                    capabilities=_strings(item.get("capabilities")),
                    source=provider,
                    status="running",
                ),
            )
        return tuple(models)

    def _discover_filesystem(self) -> tuple[DiscoveredLocalModel, ...]:
        models: list[DiscoveredLocalModel] = []
        hf_cache_dir = Path("~/.cache/huggingface/hub").expanduser()
        for root in self._model_dirs:
            if root == hf_cache_dir:
                continue
            if root.is_file() and root.suffix.casefold() == ".gguf":
                models.append(_filesystem_model(root))
                continue
            if not root.is_dir():
                continue
            for path in _limited_paths(root.rglob("*.gguf")):
                models.append(_filesystem_model(path))
            for path in _limited_paths(root.rglob("mlx_model.safetensors")):
                models.append(_filesystem_model(path.parent))
            for path in _limited_paths(root.rglob("adapter_config.json")):
                models.append(_filesystem_model(path.parent, provider="unsloth"))
            for path in _limited_paths(root.rglob("config.json")):
                model_dir = path.parent
                if (model_dir / "adapter_config.json").is_file() or (model_dir / "mlx_model.safetensors").is_file():
                    continue
                if _has_transformer_weights(model_dir):
                    models.append(_filesystem_model(model_dir, provider="transformers"))
        return tuple(models)

    def _discover_huggingface_cache(self) -> tuple[DiscoveredLocalModel, ...]:
        if self._custom_model_dirs:
            hf_hub_dirs = [d for d in self._model_dirs if d.name.startswith("models--") or list(d.glob("models--*"))]
            if not hf_hub_dirs:
                return ()
        else:
            default_hf = Path("~/.cache/huggingface/hub").expanduser()
            if not default_hf.is_dir():
                return ()
            hf_hub_dirs = [default_hf]

        models: list[DiscoveredLocalModel] = []
        for hf_hub_dir in hf_hub_dirs:
            repo_dirs = [hf_hub_dir] if hf_hub_dir.name.startswith("models--") else list(hf_hub_dir.glob("models--*"))
            for repo_dir in repo_dirs:
                if not repo_dir.is_dir():
                    continue

                repo_name = repo_dir.name.removeprefix("models--").replace("--", "/")
                snapshots_dir = repo_dir / "snapshots"
                if not snapshots_dir.is_dir():
                    continue

                snapshots = [d for d in snapshots_dir.iterdir() if d.is_dir()]
                if not snapshots:
                    continue
                snapshot_dir = max(snapshots, key=lambda d: d.stat().st_mtime)

                org = repo_name.split("/")[0] if "/" in repo_name else repo_name
                provider = (
                    "unsloth"
                    if org in ("unsloth", "unslothai")
                    else ("mlx" if org == "mlx-community" else "huggingface")
                )

                gguf_dirs: set[Path] = set()
                found_gguf = False
                for path in snapshot_dir.rglob("*.gguf"):
                    if "mmproj" in path.name.casefold():
                        continue
                    found_gguf = True
                    if path.parent != snapshot_dir:
                        gguf_dirs.add(path.parent)
                    else:
                        model = self._build_hf_model(path, repo_name, provider)
                        if model.disk_size_gb * 1024 >= 10:
                            models.append(model)

                for gdir in gguf_dirs:
                    model = self._build_hf_model(gdir, repo_name, provider)
                    if model.disk_size_gb * 1024 >= 10:
                        models.append(model)

                if not found_gguf:
                    if (snapshot_dir / "mlx_model.safetensors").is_file():
                        model = self._build_hf_model(snapshot_dir, repo_name, provider)
                        if model.disk_size_gb * 1024 >= 10:
                            models.append(model)
                    elif _has_transformer_weights(snapshot_dir):
                        model = self._build_hf_model(snapshot_dir, repo_name, provider)
                        if model.disk_size_gb * 1024 >= 10:
                            models.append(model)

        return tuple(models)

    def _build_hf_model(self, path: Path, repo_name: str, provider: str) -> DiscoveredLocalModel:
        is_gguf = path.is_file() and path.suffix.casefold() == ".gguf"

        if is_gguf:
            name = path.stem
        elif path.parent.name == "snapshots":
            name = repo_name.split("/")[-1]
        else:
            name = f"{repo_name.split('/')[-1]}-{path.name}"

        size = 0
        if is_gguf:
            try:
                size = path.resolve().stat().st_size
            except OSError:
                pass
        else:
            for p in path.rglob("*"):
                if p.is_file():
                    try:
                        size += p.resolve().stat().st_size
                    except OSError:
                        pass

        metadata = _read_model_config(path) if not is_gguf else {}
        text = f"{name} {path}".casefold()
        parameter_count = next(
            (
                parsed
                for key in ("num_parameters", "num_params", "n_params")
                for parsed in (_parameter_count(metadata.get(key)),)
                if parsed > 0
            ),
            _parameter_count(text),
        )
        context_length = next(
            (
                int(_number(metadata.get(key)))
                for key in ("max_position_embeddings", "model_max_length", "max_sequence_length")
                if _number(metadata.get(key)) > 0
            ),
            0,
        )

        return DiscoveredLocalModel(
            name=name,
            repo=repo_name,
            provider=provider,
            api_base=os.getenv("AGK_LLAMA_CPP_API_BASE", "http://127.0.0.1:8080/v1")
            if is_gguf or (not is_gguf and list(path.glob("*.gguf")))
            else "",
            role=_infer_role(name),
            parameter_count_b=parameter_count,
            estimated_memory_gb=size / (1024**3) if size > 0 else 0.0,
            context_length=context_length,
            quantization=_quantization_from_config(metadata) or _quantization(name),
            source="huggingface_cache",
            disk_path=str(path.resolve()),
            disk_size_gb=size / (1024**3) if size > 0 else 0.0,
            status="cached",
        )

    def _request_json(self, url: str) -> Mapping[str, object] | None:
        parsed = urlparse(url)
        if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            return None
        try:
            request = Request(url, headers={"Accept": "application/json"})
            with safe_urlopen(request, timeout=2) as response:
                raw_body = response.read()
                value = cast(object, json.loads(raw_body.decode("utf-8")))
        except (OSError, ValueError, UnicodeError) as exc:
            logger.debug("local model discovery failed for %s: %s", url, exc)
            return None
        return _mapping(value)

    @classmethod
    def _configured_model_dirs(cls) -> tuple[Path, ...]:
        raw = os.getenv("AGK_LOCAL_MODEL_DIRS", "")
        configured = tuple(Path(value).expanduser() for value in raw.split(os.pathsep) if value.strip())
        return configured + cls._default_model_dirs

    @staticmethod
    def _configured_openai_endpoints() -> tuple[tuple[str, str], ...]:
        endpoints: list[tuple[str, str]] = [
            ("lmstudio", os.getenv("AGK_LMSTUDIO_API_BASE", "http://127.0.0.1:1234/v1")),
            ("llama.cpp", os.getenv("AGK_LLAMA_CPP_API_BASE", "http://127.0.0.1:8080/v1")),
        ]
        unsloth_base = os.getenv("UNSLOTH_API_BASE", "").strip()
        if unsloth_base:
            endpoints.append(("unsloth", unsloth_base))
        optional_servers = (
            ("vllm", "AGK_VLLM_API_BASE"),
            ("tgi", "AGK_TGI_API_BASE"),
            ("koboldcpp", "AGK_KOBOLDCPP_API_BASE"),
            ("text-generation-webui", "AGK_TEXTGEN_WEBUI_API_BASE"),
        )
        for provider, variable in optional_servers:
            base_url = os.getenv(variable, "").strip()
            if base_url:
                endpoints.append((provider, base_url))
        raw = os.getenv("AGK_LOCAL_OPENAI_BASE_URLS", "")
        for value in raw.split(","):
            base_url = value.strip()
            if base_url:
                endpoints.append(("openai-compatible-local", base_url))
        return tuple(dict.fromkeys(endpoints))

    @staticmethod
    def _deduplicate(models: Iterable[DiscoveredLocalModel]) -> tuple[DiscoveredLocalModel, ...]:
        model_list = list(models)
        # Find running models where name or repo is a filesystem path
        running_by_path: dict[str, DiscoveredLocalModel] = {}
        for m in model_list:
            if m.status == "running" and ("/" in m.name or "/" in m.repo):
                resolved = ""
                try:
                    p = Path(m.name) if Path(m.name).exists() else Path(m.repo)
                    if p.exists():
                        resolved = str(p.resolve())
                except OSError:
                    pass
                if resolved:
                    running_by_path[resolved] = m
                if m.disk_path:
                    running_by_path[m.disk_path] = m

        seen: set[tuple[str, str]] = set()
        unique: list[DiscoveredLocalModel] = []
        raw_path_keys_to_skip: set[tuple[str, str]] = set()

        # If a disk-based model matches a running path, upgrade its status to running
        updated_models: list[DiscoveredLocalModel] = []
        for model in model_list:
            disk_p = model.disk_path
            matched_running = running_by_path.get(disk_p)
            if matched_running is not None and model != matched_running:
                updated = replace(
                    model,
                    status="running",
                    api_base=matched_running.api_base or model.api_base,
                )
                updated_models.append(updated)
                raw_path_keys_to_skip.add((matched_running.provider.casefold(), matched_running.name.casefold()))
            else:
                updated_models.append(model)

        for model in updated_models:
            key = (model.provider.casefold(), model.name.casefold())
            if key in raw_path_keys_to_skip:
                continue
            if key in seen:
                continue
            seen.add(key)
            unique.append(model)
        return tuple(unique)


def _mapping(value: object) -> Mapping[str, object] | None:
    if isinstance(value, Mapping):
        typed_value = cast(Mapping[object, object], value)
        return {str(key): item for key, item in typed_value.items()}
    return None


def _items(value: object) -> tuple[object, ...]:
    if isinstance(value, list):
        typed_value = cast(list[object], value)
        return tuple(typed_value)
    return ()


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _number(value: object) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return 0.0
    return 0.0


def _parameter_count(value: object) -> float:
    numeric = _number(value)
    if numeric > 0:
        return numeric / 1_000_000_000 if numeric > 1000 else numeric
    text = _text(value)
    match = re.search(r"(?<!\d)(\d+(?:\.\d+)?)\s*([bm])\b", text, re.IGNORECASE)
    if match is None:
        return 0.0
    amount = float(match.group(1))
    return amount / 1000 if match.group(2).casefold() == "m" else amount


def _strings(value: object) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        typed_value = cast(Sequence[object], value)
        return tuple(item.strip() for item in typed_value if isinstance(item, str) and item.strip())
    return ()


def _infer_role(name: str, family: object = None) -> str:
    text = f"{name} {_text(family)}".casefold()
    if any(token in text for token in ("embed", "e5-", "bge-")):
        return "embedding"
    if any(token in text for token in ("vision", "vlm", "llava", "pixtral", "qwen-vl")):
        return "vision"
    if any(token in text for token in ("orpheus", "tts", "asr", "whisper", "speech", "voice", "audio")):
        return "audio"
    if any(token in text for token in ("coder", "coding", "code", "deepseek-c")):
        return "coding"
    return "reasoning"


def _filesystem_model(path: Path, provider: str | None = None) -> DiscoveredLocalModel:
    is_gguf = path.is_file() and path.suffix.casefold() == ".gguf"
    model_path = path if is_gguf else path
    name = _filesystem_name(model_path)
    text = f"{name} {model_path}".casefold()
    resolved_provider = provider or ("llama.cpp" if is_gguf else "mlx")
    metadata = _read_model_config(model_path)
    parameter_count = next(
        (
            parsed
            for key in ("num_parameters", "num_params", "n_params")
            for parsed in (_parameter_count(metadata.get(key)),)
            if parsed > 0
        ),
        _parameter_count(text),
    )
    context_length = next(
        (
            int(_number(metadata.get(key)))
            for key in ("max_position_embeddings", "model_max_length", "max_sequence_length")
            if _number(metadata.get(key)) > 0
        ),
        0,
    )
    quantization = _quantization_from_config(metadata) or _quantization(name)
    size = model_path.stat().st_size if is_gguf else _directory_size(model_path)
    return DiscoveredLocalModel(
        name=name,
        repo=str(model_path),
        provider=resolved_provider,
        api_base=os.getenv("AGK_LLAMA_CPP_API_BASE", "http://127.0.0.1:8080/v1") if is_gguf else "",
        role=_infer_role(name),
        parameter_count_b=parameter_count,
        estimated_memory_gb=size / (1024**3) if size > 0 else 0.0,
        context_length=context_length,
        quantization=quantization,
        source="filesystem",
        disk_path=str(model_path.resolve()),
        disk_size_gb=size / (1024**3) if size > 0 else 0.0,
        status="installed",
    )


def _filesystem_name(path: Path) -> str:
    for part in reversed(path.parts):
        if part.startswith("models--"):
            return part.removeprefix("models--").replace("--", "/")
    return path.stem if path.is_file() else path.name


def _directory_size(path: Path) -> int:
    total = 0
    for pattern in ("*.safetensors", "*.bin", "*.pt", "*.pth"):
        for child in _limited_paths(path.rglob(pattern)):
            try:
                total += child.stat().st_size
            except OSError:
                continue
    return total


def _has_transformer_weights(path: Path) -> bool:
    return any(path.glob("*.safetensors"))


def _read_model_config(path: Path) -> Mapping[str, object]:
    config_path = path / "config.json" if path.is_dir() else None
    if config_path is None or not config_path.is_file():
        return {}
    try:
        value = cast(object, json.loads(config_path.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, ValueError):
        return {}
    return _mapping(value) or {}


def _quantization_from_config(metadata: Mapping[str, object]) -> str:
    config = _mapping(metadata.get("quantization_config")) or {}
    bits = _number(config.get("bits"))
    if bits > 0:
        return f"{int(bits)}bit"
    if config.get("load_in_4bit") is True:
        return "4bit"
    if config.get("load_in_8bit") is True:
        return "8bit"
    return ""


def _limited_paths(paths: Iterable[Path], limit: int = 200) -> tuple[Path, ...]:
    result: list[Path] = []
    for path in paths:
        if len(result) >= limit:
            break
        if any(part.startswith(".") for part in path.parts):
            continue
        result.append(path)
    return tuple(result)


# unsloth Dynamic GGUF 네이밍 규약 파서 (벤치마킹: unslothai/unsloth).
# 예: Qwen3.8-27B-UD-Q4_K_XL.gguf, unsloth/Qwen3.8-27B-GGUF:UD-Q4_K_XL,
#     Qwen3.8-27B-Q4_K_M.gguf, model-IQ4_XS.gguf, TQ1_0(ternary), gemma-4-9b-it-q4_k_m.gguf
# - UD- 접두사: Unsloth Dynamic (레이어별 혼합 정밀도) 양자화
# - IQ*/TQ* 시리즈: I-quant, ternary quant; Q*는 레거시 K-quant
# - 표준 GGUF 양자 토큰은 항상 언더스코어 그룹을 포함 (Q4_K_M, Q8_0, IQ4_XS, TQ1_0)
# - 기존 호환: "4bit" 표기 유지
_QUANT_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])((?:UD-)?(?:TQ|IQ|Q)\d(?:_[A-Z0-9]+)+|\d+bit)",
    re.IGNORECASE,
)


def _quantization(name: str) -> str:
    match = _QUANT_TOKEN_RE.search(name)
    if match:
        token = match.group(1)
        if token.casefold().endswith("bit"):
            return token.casefold()
        return token.upper()
    return ""
