#!/usr/bin/env python3
"""순차 감사용 격리 실행기. 제품 설정과 과거 감사 기록은 수정하지 않는다."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCOPES = (
    "src/antigravity_k",
    "dashboard/src",
    "dashboard/package.json",
    "dashboard/pnpm-lock.yaml",
    "dashboard/vite.config.ts",
    "tests",
    "scripts",
    ".github/workflows",
    "vscode-extension/src",
    "vscode-extension/package.json",
    "pyproject.toml",
    "uv.lock",
    "config.yaml",
    "README.md",
    "docs/20_CURRENT_STATUS.md",
    "docs/ga/CR14_FINAL_CANDIDATE_VERDICT.md",
)
# 계약이 직접 읽는 공개 QA 텍스트만 추가한다. ignored 디렉터리 전체는 읽지 않는다.
QA_RECEIPTS = (
    ".omo/evidence/web-search-answer/final-two-run-manifest.json",
    ".omo/evidence/web-search-answer/final-two-run-verification.txt",
    ".omo/evidence/web-search-answer/web-search-answer-fix.md",
    "docs/qa/2026-10-04-sequential-audit/dashboard-responsive-build.log",
    "docs/qa/2026-10-04-sequential-audit/dashboard-responsive-lint.log",
    "docs/qa/2026-10-04-sequential-audit/dashboard-responsive-tests.log",
    # Historical links are exercised by test_docs_toolchain_contract in an owned export.
    # Select exact logs rather than copying arbitrary ignored *.log files.
    "docs/qa/2026-09-16-followup/tests.log",
)
STORES = ("data", "models", "logs", "sessions", "wiki", ".ssak", ".antigravity", ".codex", ".agk_vault")
PATH_SETTINGS = ("models", "data", "documents", "vectors", "logs", "wiki")
CHECKOUT_DIRECTORIES = (
    "src",
    "tests",
    "scripts",
    "dashboard",
    "docs",
    ".github",
    ".agent",
    ".omo",
    "vscode-extension",
    "contracts",
    "deploy",
    "desktop",
    "prompts",
    "config",
    "demo_service",
    "research",
)
CHECKOUT_FILES = (
    "README.md",
    "README.ko.md",
    "LICENSE",
    "NOTICE",
    "Makefile",
    "AGENTS.md",
    "CLAUDE.md",
    "ARCHITECTURE.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "ONBOARDING.md",
    "Dockerfile",
    "docker-entrypoint.sh",
    ".gitignore",
    ".gitattributes",
    ".dockerignore",
    ".pre-commit-config.yaml",
    "pyproject.toml",
    "uv.lock",
    "setup.py",
    "requirements.txt",
    "THIRD_PARTY_PROVENANCE.toml",
    "policy.yaml",
    "run.sh",
    "config.yaml.example",
    ".env.example",
    ".env.template",
    "docker-compose.vllm.yml",
)


def owned_checkout(root: Path, origin: Path = ROOT) -> dict[str, Any]:
    """현재 코드만 복사한다. 데이터·HOME·자격증명은 fixture 입력으로 사용하지 않는다."""
    project = root / "project"
    project.mkdir(parents=True, exist_ok=True)
    listing = (
        subprocess.check_output(
            [
                "git",
                "ls-files",
                "-z",
                "--cached",
                "--others",
                "--exclude-standard",
                "--",
                *CHECKOUT_DIRECTORIES,
                *CHECKOUT_FILES,
            ],
            cwd=origin,
        )
        .decode("utf-8", "surrogateescape")
        .split("\0")
    )
    copied: dict[str, str] = {}
    omitted: list[str] = []
    for name in sorted(set(listing) | set(QA_RECEIPTS)):
        if not name:
            continue
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"잘못된 checkout 경로: {name}")
        source = origin / relative
        if (
            source.is_symlink()
            or not source.is_file()
            or "__pycache__" in relative.parts
            or "node_modules" in relative.parts
            or name.endswith(".pyc")
            or relative.name in (".env", "auth_hash", "token_secret")
            or source.suffix in (".db", ".sqlite", ".sqlite3")
        ):
            omitted.append(name)
            continue
        resolved = source.resolve()
        if not resolved.is_relative_to(origin.resolve()):
            raise ValueError(f"checkout symlink 부모 이탈: {name}")
        destination = project / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied[name] = str(digest(destination))
    # 이력 객체와 index/config/lock을 모두 사본이 소유해 원본 Git 경로를 참조하지 않는다.
    git_env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    subprocess.run(
        ["git", "clone", "--no-local", "--depth=1", "--no-checkout", "--quiet", str(origin), str(root / "history")],
        env=git_env,
        check=True,
        capture_output=True,
    )
    shutil.move(str(root / "history/.git"), str(project / ".git"))
    (root / "history").rmdir()
    subprocess.run(["git", "read-tree", "HEAD"], cwd=project, env=git_env, check=True, capture_output=True)
    # 개인 config 대신 package 기본 config로 byte 비교 계약을 재현한다. 원본과 구분해서 기록한다.
    shutil.copy2(project / "src/antigravity_k/config.yaml", project / "config.yaml")
    (project / ".env").touch()
    return {
        "mode": "owned-checkout",
        "copied_sources": copied,
        "copied_source_count": len(copied),
        "omitted_paths": omitted,
        "runtime_stores_copied": False,
        "qa_receipt_allowlist": list(QA_RECEIPTS),
        "substitutions": {"config.yaml": "packaged default bytes", ".env": "empty synthetic fixture"},
        "git_history": "owned shallow objects, index and config; no original-object alternates",
        "release_candidate_certified": False,
    }


# Python 하위 프로세스에서도 import 전에 적용된다. OS sandbox가 비-Python 자식도 보호한다.
BOOTSTRAP = """import json
import os
import sys
import traceback
from pathlib import Path

_root = Path(os.environ["SSAK_AUDIT_ROOT"])
if os.environ.get("SSAK_AUDIT_CHECKOUT") == "owned":
    _origin = Path(os.environ["SSAK_AUDIT_ORIGIN_ROOT"])
    sys.path[:] = [p for p in sys.path if not p or not Path(p).is_relative_to(_origin)
                  or Path(p).is_relative_to(_origin / ".venv")]
    sys.path.insert(0, str(_root / "project/src"))
Path.home = classmethod(lambda cls: _root / "home")

# sitecustomize의 일반 예외는 Python이 무시하므로 bootstrap 오류는 즉시 종료한다.
try:
    for key in ("AGK_CONFIG_FILE", "AGK_ENV_FILE", "AGK_SEC_PIN_HASH_FILE",
                "AGK_SEC_TOKEN_SECRET_FILE", "AGK_PATH_PROJECT_ROOT"):
        if not Path(os.environ[key]).resolve().is_relative_to(_root):
            raise ValueError(key)
    if not Path(os.environ["AGK_CONFIG_FILE"]).is_file():
        raise ValueError("명시적 config 없음")
except (KeyError, ValueError, OSError) as exc:
    print("격리 bootstrap 실패: " + str(exc), file=sys.stderr)
    os._exit(78)

_protected = tuple(Path(p).resolve() for p in json.loads(os.environ["SSAK_AUDIT_PROTECTED"]))
_owned_mode = os.environ.get("SSAK_AUDIT_CHECKOUT") == "owned"
_allowed_venv = Path(os.environ["SSAK_AUDIT_ORIGIN_ROOT"]) / ".venv"
_log = _root / "access-violations.jsonl"
_logging = False

def _guard(event, args):
    global _logging
    if _logging or event not in ("open", "os.listdir", "os.scandir", "sqlite3.connect"):
        return
    if not args or not isinstance(args[0], (str, bytes, os.PathLike)):
        return
    path = Path(os.fsdecode(args[0])).absolute()
    # resolve()는 없는 파일과 symlink 부모도 처리한다.
    path = path.resolve()
    if path.is_relative_to(_root):
        return
    if _owned_mode and path.is_relative_to(_allowed_venv):
        return
    if any(path == p or path.is_relative_to(p) for p in _protected):
        _logging = True
        try:
            with _log.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"event": event, "path": str(path), "stack": traceback.format_stack(limit=10)}) + "\\n")
        finally:
            _logging = False
        raise PermissionError("개인 저장소 접근 차단: " + str(path))

sys.addaudithook(_guard)
"""

PLUGIN = """import json
import os
from pathlib import Path

_log = Path(os.environ["SSAK_AUDIT_ROOT"]) / "pytest-outcomes.jsonl"

def _save(report, kind):
    with _log.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"nodeid": report.nodeid, "kind": kind,
            "when": getattr(report, "when", "collect"), "outcome": report.outcome,
            "wasxfail": getattr(report, "wasxfail", None),
            "longrepr": str(report.longrepr) if report.longrepr else None}) + "\\n")

def pytest_runtest_logreport(report):
    _save(report, "test")

def pytest_collectreport(report):
    if report.failed or report.skipped:
        _save(report, "collection")
"""


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def source_manifest() -> dict[str, Any]:
    names = git("ls-files", "--cached", "--others", "--exclude-standard", "--", *SCOPES).splitlines()
    names = [name for name in names if "/__pycache__/" not in name and not name.endswith(".pyc")]
    sources = {name: digest(ROOT / name) for name in sorted(set(names) | set(QA_RECEIPTS))}
    previous = json.loads((ROOT / "docs/qa/2026-10-04-sequential-audit/source-final-marker-after.json").read_text())
    changed = [name for name, sha in previous["sources"].items() if digest(ROOT / name) != sha]
    return {
        "recorded_at": utc_now(),
        "head": git("rev-parse", "HEAD"),
        "branch": git("branch", "--show-current"),
        "sources": sources,
        "source_count": len(sources),
        "audit_snapshot_changed": changed,
        "locks": {name: digest(ROOT / name) for name in ("uv.lock", "dashboard/pnpm-lock.yaml")},
        "python": sys.version,
        "python_executable": sys.executable,
        "os": platform.platform(),
        "node": subprocess.check_output(["node", "--version"], text=True).strip(),
        "pnpm": subprocess.check_output(["pnpm", "--version"], text=True).strip(),
        "provider": "isolated-unavailable-fixture",
        "model": None,
        "provider_version": None,
        "unstaged_paths": git("diff", "--name-only", "--", *SCOPES).splitlines(),
        "staged_paths": git("diff", "--cached", "--name-only", "--", *SCOPES).splitlines(),
    }


def source_changes(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    names = set(before["sources"]) | set(after["sources"])
    changed = sorted(name for name in names if before["sources"].get(name) != after["sources"].get(name))
    if before["head"] != after["head"]:
        changed.append("HEAD")
    return changed


def isolated_environment(root: Path, port: int, *, checkout: bool = False) -> dict[str, str]:
    """호출자의 환경은 바꾸지 않고 허용한 시스템 변수만 자식에게 전달한다."""
    keep = ("PATH", "LANG", "LC_ALL", "SYSTEMROOT", "COMSPEC", "TERM", "TZ")
    env = {key: os.environ[key] for key in keep if key in os.environ}
    for folder in ("home", "project", "tmp", "bootstrap", *PATH_SETTINGS):
        (root / folder).mkdir(parents=True, exist_ok=True)
    # cwd도 소유 프로젝트다. source contract가 필요한 경로만 읽기 전용 symlink로 제공한다.
    for name in (
        "src",
        "tests",
        "scripts",
        "dashboard",
        "docs",
        ".github",
        "pyproject.toml",
        "uv.lock",
        "README.md",
        "LICENSE",
    ):
        if not checkout:
            if name == "src":
                shutil.copytree(
                    ROOT / name, root / "project" / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
                )
            elif name == "pyproject.toml":
                shutil.copy2(ROOT / name, root / "project" / name)
            else:
                (root / "project" / name).symlink_to(ROOT / name, target_is_directory=(ROOT / name).is_dir())
    config_path = root / "config.json"
    defaults = yaml.safe_load((root / "project/src/antigravity_k/config.yaml").read_text()) if checkout else {}
    config_values: dict[str, dict[str, Any]] = {
        "paths": {
            "project_root": str(root / "project"),
            **{f"{name}_dir": str(root / name) for name in PATH_SETTINGS},
        },
        "model": {"api_base": f"http://127.0.0.1:{port}/v1", "api_engine": "ollama", "api_key": ""},
        "workflow": {"autopilot": False, "auto_commit": False},
        "computer_use": {
            "enabled": False,
            "screenshot_dir": str(root / "data/screenshots"),
            "audit_log_path": str(root / "logs/computer-use.jsonl"),
        },
    }
    if checkout:
        defaults["model"] = {**defaults.get("model", {}), **config_values.pop("model")}
        defaults.update(config_values)
        config_values = defaults
    write_json(config_path, config_values)
    (root / "empty.env").touch()
    (root / "bootstrap/sitecustomize.py").write_text(BOOTSTRAP, encoding="utf-8")
    (root / "bootstrap/sequential_audit_plugin.py").write_text(PLUGIN, encoding="utf-8")
    protected = [str(ROOT / name) for name in (*STORES, ".env", "config.yaml")]
    if checkout:
        protected.append(str(ROOT))
    home = Path.home().resolve()
    protected.extend(
        str(home / name)
        for name in (
            ".antigravity-k",
            ".ssak",
            ".codex",
            ".ssh",
            ".config",
            ".aws",
            ".ollama",
            "Library/Keychains",
        )
    )
    env.update(
        {
            "SSAK_AUDIT_ROOT": str(root),
            "SSAK_AUDIT_CHECKOUT": "owned" if checkout else "linked",
            "SSAK_AUDIT_ORIGIN_ROOT": str(ROOT),
            "SSAK_AUDIT_PROTECTED": json.dumps(protected),
            "HOME": str(root / "home"),
            "CODEX_HOME": str(root / "home/.codex"),
            "TMPDIR": str(root / "tmp"),
            "PYTHONPATH": os.pathsep.join([str(root / "bootstrap"), str(root / "project/src")]),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHON_DOTENV_DISABLED": "1",
            "AGK_CONFIG_FILE": str(config_path),
            "AGK_ENV_FILE": str(root / "empty.env"),
            "AGK_PATH_PROJECT_ROOT": str(root / "project"),
            "AGK_SEC_PIN_HASH_FILE": str(root / "data/auth_hash"),
            "AGK_SEC_TOKEN_SECRET_FILE": str(root / "data/token_secret"),
            "AGK_SEC_ACCESS_PIN": "",
            "AGK_SEC_DEV_NO_PIN_ALLOW": "false",
            "AGK_ENV": "test",
            "AGK_ALLOWED_ROOTS": str(root / "project"),
            "AGK_CONVERSATION_STORE_DIR": str(root / "data/conversations"),
            "AGK_MODEL_API_BASE": f"http://127.0.0.1:{port}/v1",
            "AGK_MODEL_API_ENGINE": "ollama",
            "AGK_CU_SCREENSHOT_DIR": str(root / "data/screenshots"),
            "AGK_CU_AUDIT_LOG_PATH": str(root / "logs/computer-use.jsonl"),
            "HF_HOME": str(root / "home/huggingface"),
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "XDG_CACHE_HOME": str(root / "home/.cache"),
            "UV_CACHE_DIR": str(root / "home/uv-cache"),
            "AGK_TEST_PYTHON": sys.executable,
            "AGK_VAULT_DIR": str(root / "data/key-vault"),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_OPTIONAL_LOCKS": "0",
        }
    )
    env.update({f"AGK_PATH_{name.upper()}_DIR": str(root / name) for name in PATH_SETTINGS})
    return env


def preflight(root: Path, env: dict[str, str]) -> None:
    keys = (
        "AGK_CONFIG_FILE",
        "AGK_ENV_FILE",
        "AGK_PATH_PROJECT_ROOT",
        "AGK_SEC_PIN_HASH_FILE",
        "AGK_SEC_TOKEN_SECRET_FILE",
        *(f"AGK_PATH_{name.upper()}_DIR" for name in PATH_SETTINGS),
    )
    for key in keys:
        if key not in env or not Path(env[key]).resolve().is_relative_to(root.resolve()):
            raise ValueError(f"격리 설정 누락 또는 외부 경로: {key}")
    config = Path(env["AGK_CONFIG_FILE"])
    if not config.is_file():
        raise ValueError("명시적 config 파일 없음")
    values = json.loads(config.read_text(encoding="utf-8"))
    for name in ("project_root", *(f"{name}_dir" for name in PATH_SETTINGS)):
        value = values.get("paths", {}).get(name)
        if not isinstance(value, str) or not Path(value).resolve().is_relative_to(root.resolve()):
            raise ValueError(f"config 경로 누락 또는 외부 경로: {name}")


def sandbox_profile(root: Path, *, checkout: bool = False) -> str:
    """개인 HOME 읽기와 owned root 밖 쓰기를 OS 수준에서 차단한다(macOS 전용)."""

    def quote(value: Path) -> str:
        return json.dumps(str(value))

    home = Path.home().resolve()
    reads = [
        ROOT / name
        for name in (
            "src",
            "tests",
            "scripts",
            "dashboard",
            "docs",
            ".github",
            ".git",
            ".venv",
            "pyproject.toml",
            "uv.lock",
            "README.md",
            "LICENSE",
            "Makefile",
            "vscode-extension",
            ".agent/skills",
        )
    ]
    if checkout:
        reads = [ROOT / ".git", ROOT / ".venv"]
    # venv의 실제 Python/라이브러리는 HOME 아래의 conda 설치일 수 있다.
    reads.extend((Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve(), root))
    exceptions = " ".join(f"(subpath {quote(path)})" for path in reads)
    exceptions += f" (literal {quote(ROOT)})"
    rules = [
        "(version 1)",
        "(allow default)",
        f"(deny file-read-data (require-all (subpath {quote(home)}) (require-not (require-any {exceptions}))))",
    ]
    rules.extend(f"(deny file-read-data (subpath {quote(ROOT / name)}))" for name in (*STORES, ".env", "config.yaml"))
    rules.extend(
        (
            "(deny file-write*)",
            f"(allow file-write* (subpath {quote(root)}))",
            '(allow file-write* (literal "/dev/null") (literal "/dev/tty") (literal "/dev/ptmx"))',
            "(deny network*)",
            '(allow network* (local ip "localhost:*") (remote ip "localhost:*"))',
        )
    )
    return "\n".join(rules)


def read_json_lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line] if path.exists() else []


def stop_group(process: subprocess.Popen[bytes]) -> None:
    """직접 생성한 새 프로세스 그룹만 정리한다. 정상 종료한 parent의 자식도 포함한다."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except PermissionError:
        if remaining_group_pids(process.pid):
            raise
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except PermissionError:
        if remaining_group_pids(process.pid):
            raise
    process.wait(timeout=3)


def remaining_group_pids(pgid: int) -> list[int]:
    rows = subprocess.check_output(["ps", "-axo", "pid=,pgid=,stat="], text=True).splitlines()
    return [
        int(parts[0])
        for row in rows
        if len(parts := row.split()) == 3 and int(parts[1]) == pgid and not parts[2].startswith("Z")
    ]


def run_command(
    arguments: Sequence[str],
    evidence: Path,
    *,
    timeout: float = 600,
    monitor_source: bool = True,
    checkout: bool = False,
    cache_paths: Sequence[str] = (),
    pytest_args: Sequence[str] | None = None,
) -> dict[str, Any]:
    """한 명령의 전후 manifest, 원시 로그, 실패·정리 상태를 보존한다."""
    evidence.mkdir(parents=True, exist_ok=False)
    before = source_manifest()
    write_json(evidence / "manifest-before.json", before)
    parent_env = dict(os.environ)
    started = utc_now()
    clock = time.monotonic()
    receipt: dict[str, Any] = {"argv": list(arguments), "cwd": str(ROOT), "start": started, "status": "RUNNING"}
    interrupted = False
    try:
        _run_command_body(
            arguments,
            evidence,
            timeout=timeout,
            monitor_source=monitor_source,
            checkout=checkout,
            cache_paths=cache_paths,
            pytest_args=pytest_args,
            receipt=receipt,
            before=before,
            parent_env=parent_env,
            clock=clock,
        )
    except KeyboardInterrupt:
        # 인터럽트에도 receipt 를 종결 상태로 남긴다 — RUNNING 으로 남으면 "도는 중"과 "중단됨"을
        # 구분할 수 없다(과거 baseline/backend-full 의 stale RUNNING 재발 방지).
        interrupted = True
        receipt.update(status="INCONCLUSIVE", reason="INTERRUPTED")
    finally:
        if interrupted and receipt.get("status") == "RUNNING":
            receipt.update(status="INCONCLUSIVE", reason="INTERRUPTED")
    # 최종 기록은 반드시 디스크에 남긴다 — 인터럽트나 manifest 계산 실패가 있어도 receipt가
    # stale RUNNING으로 남지 않게 한다(과거 backend-full 중단의 재발 방지).
    try:
        after = source_manifest()
        write_json(evidence / "manifest-after.json", after)
        changed = source_changes(before, after)
        if changed:
            receipt.update(status="INCONCLUSIVE", reason="SOURCE_MOVED", changed_sources=changed)
        if receipt.get("status") == "RUNNING":
            receipt.update(status="INCONCLUSIVE", reason="INCOMPLETE")
        owned_root = receipt.get("owned_root")
        owned_root_removed = isinstance(owned_root, (str, Path)) and not Path(owned_root).exists()
        receipt.update(
            end=utc_now(),
            elapsed_s=time.monotonic() - clock,
            cleanup={
                "owned_root_removed": owned_root_removed,
                "parent_environment_unchanged": parent_env == dict(os.environ),
            },
        )
    finally:
        write_json(evidence / "receipt.json", receipt)
    return receipt


def _run_command_body(
    arguments: Sequence[str],
    evidence: Path,
    *,
    timeout: float,
    monitor_source: bool,
    checkout: bool,
    cache_paths: Sequence[str],
    pytest_args: Sequence[str] | None,
    receipt: dict[str, Any],
    before: dict[str, Any],
    parent_env: dict[str, str],
    clock: float,
) -> None:
    """격리 실행 본체(with 블록 전체). KeyboardInterrupt 는 호출자가 받아 종결 기록을 남긴다."""
    process: subprocess.Popen[bytes] | None = None
    with tempfile.TemporaryDirectory(prefix="ssak-sequential-") as temporary, socket.socket() as reserved:
        root = Path(temporary).resolve()
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
        checkout_manifest: dict[str, Any] = {"copied_sources": {}}
        if checkout:
            checkout_manifest = owned_checkout(root)
            # 캐시(예: dashboard/node_modules)는 부모가 복사해 제공한다 — 자식은 개인 데이터·원본에 접근하지 않고도
            # 오프라인 도구 체인을 돌릴 수 있다(격리 의미는 그대로 유지).
            copied_caches: dict[str, int] = {}
            for relative in cache_paths:
                source = ROOT / relative
                destination = root / "project" / relative
                if source.is_dir():
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(source, destination, symlinks=True, dirs_exist_ok=True)
                    copied_caches[relative] = sum(1 for _ in destination.rglob("*"))
            checkout_manifest["copied_caches"] = copied_caches
            write_json(evidence / "checkout-manifest.json", checkout_manifest)
        env = isolated_environment(root, port, checkout=checkout)
        receipt["cwd"] = str(root / "project")
        executed = list(arguments)
        if pytest_args is not None:
            copied_args: list[str] = []
            for argument in pytest_args:
                filename, separator, node_id = argument.partition("::")
                source = Path(filename).resolve()
                if source.is_file():
                    relative = (
                        source.relative_to(ROOT)
                        if source.is_relative_to(ROOT)
                        else Path("pytest-inputs")
                        / (hashlib.sha256(str(source).encode()).hexdigest()[:12] + "-" + source.name)
                    )
                    destination = root / "project" / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    if source != destination:
                        shutil.copy2(source, destination)
                    copied_args.append(str(destination) + (separator + node_id if separator else ""))
                elif source.is_dir() and source.is_relative_to(ROOT):
                    copied_args.append(str(root / "project" / source.relative_to(ROOT)))
                else:
                    copied_args.append(argument)
            code = (
                'import os, pytest; from pathlib import Path; root=Path(os.environ["SSAK_AUDIT_ROOT"]); '
                'raise SystemExit(pytest.main(["-p", "sequential_audit_plugin", '
                '"-c", str(root/"project/pyproject.toml"), "--rootdir="+str(root/"project"), '
                '"--basetemp="+str(root/"tmp/pytest"), "--junitxml="+str(root/"junit.xml"), '
                '"-o", "cache_dir="+str(root/"tmp/pytest-cache"), *' + repr(copied_args) + "]))"
            )
            executed = [sys.executable, "-c", code]
        if checkout:
            for index, argument in enumerate(executed):
                path = Path(argument)
                if path.is_absolute() and path.is_relative_to(ROOT) and not path.is_relative_to(ROOT / ".venv"):
                    executed[index] = str(root / "project" / path.relative_to(ROOT))
        receipt["executed_argv"] = executed
        environment = {
            "owned_root": str(root),
            "project": str(root / "project"),
            "provider": "unavailable-fixture",
            "checkout_mode": "owned" if checkout else "linked",
            "release_candidate_certified": False,
            "provider_port": port,
            "actual_model": False,
            "lifespan": None,
            "browser_pids": [],
            "sandbox": "macOS sandbox-exec",
            "parent_environment_unchanged": None,
        }
        write_json(evidence / "environment.json", environment)
        write_json(evidence / "receipt.json", receipt)
        try:
            preflight(root, env)
            if sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").is_file():
                receipt.update(status="BLOCKED_ENV", reason="OS 접근 격리를 제공할 sandbox-exec 없음")
            else:
                profile = root / "sandbox.sb"
                profile.write_text(sandbox_profile(root, checkout=checkout), encoding="utf-8")
                with (evidence / "stdout.txt").open("wb") as stdout, (evidence / "stderr.txt").open("wb") as stderr:
                    process = subprocess.Popen(
                        ["/usr/bin/sandbox-exec", "-f", str(profile), *executed],
                        cwd=root / "project",
                        env=env,
                        stdout=stdout,
                        stderr=stderr,
                        start_new_session=True,
                    )
                    environment["child_pid"] = process.pid
                    write_json(evidence / "environment.json", environment)
                    next_check = time.monotonic() + 5
                    while process.poll() is None:
                        violation_log = root / "access-violations.jsonl"
                        if violation_log.exists() and violation_log.stat().st_size:
                            receipt.update(status="FAIL", reason="ISOLATION_VIOLATION")
                            break
                        if time.monotonic() - clock >= timeout:
                            receipt.update(status="FAIL", reason="TIMEOUT")
                            break
                        if monitor_source and time.monotonic() >= next_check:
                            changed = source_changes(before, source_manifest())
                            if changed:
                                receipt.update(status="INCONCLUSIVE", reason="SOURCE_MOVED", changed_sources=changed)
                                break
                            next_check = time.monotonic() + 5
                        time.sleep(0.05)
                    if process.poll() is None:
                        stop_group(process)
                    receipt["exit"] = process.returncode
                    if receipt["status"] == "RUNNING":
                        receipt["status"] = "PASS" if process.returncode == 0 else "FAIL"
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            receipt.update(status="FAIL", reason=f"HARNESS_ERROR: {type(exc).__name__}: {exc}")
        finally:
            if process is not None:
                cleanup_errors: list[str] = []
                try:
                    stop_group(process)
                except (OSError, subprocess.SubprocessError) as exc:
                    cleanup_errors.append(f"stop_group: {type(exc).__name__}: {exc}")
                remaining: list[int] | None = None
                try:
                    for _ in range(20):
                        remaining = remaining_group_pids(process.pid)
                        if not remaining:
                            break
                        time.sleep(0.05)
                except (OSError, subprocess.SubprocessError) as exc:
                    cleanup_errors.append(f"remaining_group_pids: {type(exc).__name__}: {exc}")
                receipt["owned_processes_remaining"] = remaining if not cleanup_errors else None
                if cleanup_errors:
                    # 정리 실패를 통과로 숨기지 않되 JUnit·raw output·종료 receipt 보존을 계속한다.
                    receipt.update(status="FAIL", reason="CLEANUP_ERROR: " + "; ".join(cleanup_errors))
                elif remaining:
                    receipt.update(status="FAIL", reason="CLEANUP_PROCESS_LEAK")
            if checkout:
                moved = [
                    name
                    for name, sha in checkout_manifest["copied_sources"].items()
                    if digest(root / "project" / name) != sha
                ]
                write_json(
                    evidence / "checkout-source-after.json",
                    {
                        "changed_copied_sources": moved,
                        "release_candidate_certified": False,
                    },
                )
                if moved:
                    receipt.update(
                        status="INCONCLUSIVE", reason="EXECUTED_SOURCE_MOVED", changed_checkout_sources=moved
                    )
            violations = read_json_lines(root / "access-violations.jsonl")
            write_json(evidence / "access-violations.json", violations)
            outcomes = read_json_lines(root / "pytest-outcomes.jsonl")
            write_json(evidence / "pytest-outcomes.json", outcomes)
            junit = root / "junit.xml"
            if junit.is_file():
                (evidence / "junit.xml").write_bytes(junit.read_bytes())
            if violations:
                receipt.update(status="FAIL", reason="ISOLATION_VIOLATION", access_violation_count=len(violations))
            environment["parent_environment_unchanged"] = parent_env == dict(os.environ)
            write_json(evidence / "environment.json", environment)
            receipt["owned_root"] = str(root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("pytest", "python"))
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--checkout", action="store_true", help="개인 데이터를 제외한 현재 코드 사본에서 실행")
    parser.add_argument(
        "--cache",
        action="append",
        default=[],
        metavar="RELPATH",
        help="checkout 시 사본에 함께 복사할 캐시 디렉터리(예: dashboard/node_modules). 반복 가능",
    )
    # -- 앞은 실행기 옵션, 뒤는 대상 argv다.
    argv = sys.argv[1:]
    split = argv.index("--") if "--" in argv else len(argv)
    options = parser.parse_args(argv[:split])
    args = argv[split + 1 :] if split < len(argv) else []
    if options.timeout <= 0:
        parser.error("timeout은 양수여야 한다")
    if options.mode == "python" and not args:
        parser.error("python 모드는 -- 뒤에 실행할 argv가 필요하다")
    run_id = datetime.now(UTC).strftime("%Y-%m-%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    evidence = (options.evidence or ROOT / "docs/qa/sequential-improvement" / run_id).resolve()
    if options.mode == "pytest":
        # owned root 경로는 자식에서 계산한다. shell과 argv 문자열 치환은 사용하지 않는다.
        code = (
            'import os, pytest; from pathlib import Path; root=Path(os.environ["SSAK_AUDIT_ROOT"]); '
            'raise SystemExit(pytest.main(["-p", "sequential_audit_plugin", '
            '"-c", str(root/"project/pyproject.toml"), "--rootdir="+str(root/"project"), '
            '"--basetemp="+str(root/"tmp/pytest"), "--junitxml="+str(root/"junit.xml"), '
            '"-o", "cache_dir="+str(root/"tmp/pytest-cache"), *' + repr(args) + "]))"
        )
        command = [sys.executable, "-c", code]
    else:
        command = [sys.executable, *args]
    receipt = run_command(
        command,
        evidence,
        timeout=options.timeout,
        checkout=options.checkout or options.mode == "pytest",
        cache_paths=options.cache,
        pytest_args=args if options.mode == "pytest" else None,
    )
    print(f"{receipt['status']}: {evidence}")
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
