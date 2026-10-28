"""r34: approved model / provider / endpoint boundary, checked immediately before every LLM send.

Opt-in via environment (unset => legacy, no allowlist):
- ``AGK_MODEL_ALLOWLIST``: comma-separated model names (``qwen3.8`` == ``qwen3.8:latest``).
- ``AGK_LLM_PROVIDER_ALLOWLIST``: comma-separated provider ids (e.g. ``ollama``).
- ``AGK_LLM_ENDPOINT_ALLOWLIST``: comma-separated ``host:port`` values for explicit per-model bases.

A refused model is never sent and never charged; callers must not substitute another model
(r33: a combo fallback actually sent a request to the unapproved ``qwen3.6:latest``).
"""

from __future__ import annotations

import logging
import os
import threading
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

MODEL_ENV = "AGK_MODEL_ALLOWLIST"
PROVIDER_ENV = "AGK_LLM_PROVIDER_ALLOWLIST"
ENDPOINT_ENV = "AGK_LLM_ENDPOINT_ALLOWLIST"

_lock = threading.Lock()
_refused = 0


class ModelNotAllowedError(RuntimeError):
    """Raised before sending to a model/provider/endpoint outside the approved set (non-retryable)."""

    status = "model_not_allowed"

    def __init__(self, model: str, reason: str) -> None:
        super().__init__(f"model_not_allowed: '{model}' refused ({reason}); request not sent, no substitute model")
        self.model = model
        self.reason = reason


def _items(env: str) -> set[str] | None:
    raw = os.environ.get(env, "").strip()
    if not raw:
        return None
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


def _norm_model(name: str) -> str:
    value = (name or "").strip().lower()
    for prefix in ("ollama/", "ollama:"):
        if value.startswith(prefix):
            value = value[len(prefix) :]
    return value[: -len(":latest")] if value.endswith(":latest") else value


def model_allowed(name: str) -> bool:
    allowed = _items(MODEL_ENV)
    if allowed is None:
        return True
    return _norm_model(name) in {_norm_model(item) for item in allowed}


def _endpoint_key(endpoint: str) -> str:
    parsed = urlparse(endpoint if "://" in endpoint else f"http://{endpoint}")
    host = (parsed.hostname or "").lower()
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return f"{host}:{port}"


def refusal_reason(model: str, provider: str = "", endpoint: str = "") -> str | None:
    if not model_allowed(model):
        return "model_not_allowlisted"
    providers = _items(PROVIDER_ENV)
    if providers is not None and (provider or "").strip().lower() not in providers:
        return "provider_not_allowlisted"
    endpoints = _items(ENDPOINT_ENV)
    if endpoints is not None and endpoint and _endpoint_key(endpoint) not in {_endpoint_key(e) for e in endpoints}:
        return "endpoint_not_allowlisted"
    return None


def check_send(model: str, provider: str = "", endpoint: str = "") -> None:
    """Raise :class:`ModelNotAllowedError` (nothing sent) when the target is not approved."""
    global _refused
    reason = refusal_reason(model, provider, endpoint)
    if reason is None:
        return
    with _lock:
        _refused += 1
    logger.error("[ModelAllowlist] refused model=%s provider=%s reason=%s (not sent)", model, provider or "-", reason)
    raise ModelNotAllowedError(model, reason)


def refused_count() -> int:
    return _refused


def reset_for_tests() -> None:
    global _refused
    with _lock:
        _refused = 0


EMBED_MODEL_ENV = "AGK_EMBED_MODEL_ALLOWLIST"


def embed_model_allowed(model: str) -> bool:
    """r34: embedding wire-model allowlist (unset = legacy). Refusal happens before any send."""
    raw = os.environ.get(EMBED_MODEL_ENV, "").strip()
    if not raw:
        return True
    allowed = {_norm_model(m) for m in raw.split(",") if m.strip()}
    ok = _norm_model(model) in allowed
    if not ok:
        logger.error("[ModelAllowlist] refused embedding model=%s", model)
    return ok
