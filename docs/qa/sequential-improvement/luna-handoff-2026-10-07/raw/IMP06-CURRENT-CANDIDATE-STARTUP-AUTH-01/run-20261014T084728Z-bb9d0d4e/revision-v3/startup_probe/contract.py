# /// script
# requires-python = ">=3.12"
# dependencies = ["pydantic>=2"]
# ///
# Run with the project's existing Python; imported by the owned QA entry points.
"""Pure startup probe contracts: identity, bounds, environment, and acceptance."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field


class ProbeError(RuntimeError):
    """A bounded startup observation failed its explicit contract."""


class SourcePlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    candidate: Path
    candidate_head: str
    app_version: str
    python: Path
    source_hashes: dict[str, str]
    dotenv_path: Path
    dotenv_sha256: str
    startup_seconds: float = 60
    request_seconds: float = 5
    graceful_seconds: float = 10
    kill_seconds: float = 5
    total_seconds: float = 90


class Approval(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    scope: str
    plan_sha256: str
    harness_sha256: dict[str, str]


class Started(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    pid: int
    port: int = Field(gt=0, lt=65536)
    version: str
    app_source: Path
    lifespan: str


class GuardReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    violations: list[str]
    binds: int
    model_calls: int
    scheduled_ticks: int
    subprocesses: list[str]


class Token(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    access_token: str = Field(min_length=1)
    token_type: str


class Health(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    status: str
    version: str


class Access(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    ok: bool
    mode: str


@dataclass(frozen=True, slots=True)
class Cleanup:
    exit_code: int | None
    reaped: bool
    group_empty: bool
    forced: bool

    def passed(self) -> bool:
        return self.exit_code == 0 and self.reaped and self.group_empty and not self.forced


_ENV_KEEP: Final = ("HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "SYSTEMROOT")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_sources(plan: SourcePlan) -> None:
    for relative, expected in plan.source_hashes.items():
        path = plan.candidate / relative
        if not path.resolve().is_relative_to(plan.candidate.resolve()) or digest(path) != expected:
            raise ProbeError(f"Candidate source drift: {relative}")
    if digest(plan.dotenv_path) != plan.dotenv_sha256:
        raise ProbeError("python-dotenv implementation drift")


def child_environment(parent: Mapping[str, str], plan: SourcePlan, owned: Path, pin: str) -> dict[str, str]:
    """Whitelist inherited values; all persistence and credentials belong to this attempt."""
    env = {key: parent[key] for key in _ENV_KEEP if key in parent}
    env.update(
        {
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": str(plan.candidate / "src"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
            "PYTHON_DOTENV_DISABLED": "1",
            "AGK_CONFIG_FILE": str(owned / "config.yaml"),
            "AGK_ENV_FILE": str(owned / "empty.env"),
            "AGK_SEC_ACCESS_PIN": pin,
            "AGK_SEC_PIN_HASH_FILE": str(owned / "auth-private/pin-hash"),
            "AGK_SEC_TOKEN_SECRET_FILE": str(owned / "auth-private/token-secret"),
            "AGK_SEC_DEV_NO_PIN_ALLOW": "false",
            "AGK_AUTO_DISCOVER_LOCAL_MODELS": "false",
            "AGK_SERVER_HOST": "127.0.0.1",
            "AGK_HOOK_VAULT_DIR": str(owned / "hooks"),
            "AGK_USAGE_DB": str(owned / "usage.json"),
            "ANTIGRAVITY_VAULT_PATH": str(owned / "vault"),
            "AGK_ALLOWED_ROOTS": str(owned),
            "AGK_DATA_DIR": str(owned / "data"),
            "AGK_GBRAIN_DIR": str(owned / "gbrain"),
            "AGK_GLOBAL_MEMORY_DIR": str(owned / "global-memory"),
            "AGK_CONTEXT_STORE_DIR": str(owned / "context-store"),
            "AGK_CONVERSATION_STORE_DIR": str(owned / "conversations"),
            "AGK_TASK_DB_PATH": str(owned / "data/tasks.db"),
            "AGK_BENCHMARK_DB": str(owned / "data/benchmarks.db"),
            "TMPDIR": str(owned / "tmp"),
            "XDG_CACHE_HOME": str(owned / "cache"),
            "HF_HOME": str(owned / "cache/huggingface"),
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "ANONYMIZED_TELEMETRY": "False",
        }
    )
    for name in ("PROJECT_ROOT", "MODELS_DIR", "DATA_DIR", "DOCUMENTS_DIR", "VECTORS_DIR", "LOGS_DIR", "WIKI_DIR"):
        env["AGK_PATH_" + name] = str(owned / name.lower())
    return env


def remaining(deadline: float, now: float, cap: float) -> float:
    value = min(cap, deadline - now)
    if value <= 0:
        raise ProbeError("Observation deadline exceeded")
    return value


def require_approval(plan_path: Path, approval_path: Path, harness: list[Path]) -> Approval:
    approval = Approval.model_validate_json(approval_path.read_bytes())
    expected = {path.name: digest(path) for path in harness}
    if approval.scope != "STARTUP_AUTH_ONCE" or approval.plan_sha256 != digest(plan_path):
        raise ProbeError("Approval does not bind this startup plan")
    if approval.harness_sha256 != expected:
        raise ProbeError("Approval does not bind this harness")
    return approval
