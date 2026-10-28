"""Opt-in minimal audit of the input actually sent to the LLM provider (test verification only).

OFF unless ``AGK_LLM_INPUT_AUDIT_PATH`` is set. Never writes prompt text, tokens or environment:
only identifiers, hashes and contains-checks of pre-chosen synthetic marker strings.
Performs no search and no model call.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path

AUDIT_PATH_ENV = "AGK_LLM_INPUT_AUDIT_PATH"
EXPECT_ENV = "AGK_LLM_AUDIT_EXPECT"  # synthetic fact that must appear
FORBID_ENV = "AGK_LLM_AUDIT_FORBID"  # other synthetic project's fact that must not appear
RUN_ID_ENV = "AGK_LLM_AUDIT_RUN_ID"

_lock = threading.Lock()


def enabled() -> bool:
    return bool(os.environ.get(AUDIT_PATH_ENV, "").strip())


def _request_ids() -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        from antigravity_k.api.error_handler import correlation_id_var

        out["request_id"] = correlation_id_var.get("") or ""
    except Exception:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK - audit must never break a request
        out["request_id"] = ""
    try:
        from antigravity_k.api.project_binding import get_request_project_root

        root = get_request_project_root() or ""
        out["project_root_sha"] = hashlib.sha256(root.encode()).hexdigest()[:16] if root else ""
        out["project_root_name"] = Path(root).name if root else ""
    except Exception:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK
        out["project_root_sha"] = ""
    return out


def _write(record: dict[str, object]) -> None:
    path = os.environ.get(AUDIT_PATH_ENV, "").strip()
    if not path:
        return
    record = {"ts": round(time.time(), 3), "run_id": os.environ.get(RUN_ID_ENV, ""), **_request_ids(), **record}
    with _lock, open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _marker_checks(text: str) -> dict[str, object]:
    expect = os.environ.get(EXPECT_ENV, "")
    forbid = os.environ.get(FORBID_ENV, "")
    return {
        "expect_fact_contained": (expect in text) if expect else None,
        "forbid_fact_contained": (forbid in text) if forbid else None,
    }


def audit_provider_input(*, attempt: int, model: str, provider: str, purpose: str, final_input: str) -> None:
    if not enabled():
        return
    _write(
        {
            "kind": "provider_input",
            "attempt": attempt,
            "model": model,
            "provider": provider,
            "purpose": purpose,
            "input_sha256": hashlib.sha256(final_input.encode("utf-8", "replace")).hexdigest(),
            "input_chars": len(final_input),
            "has_relevant_code": "<relevant_code>" in final_input,
            **_marker_checks(final_input),
        }
    )


def audit_retrieval(*, project_root: str, project_id: str, path: str, sources: list[tuple[str, str]]) -> None:
    if not enabled():
        return
    docs: list[dict[str, str]] = []
    root = Path(project_root).resolve()
    for source, source_id in sources:
        cand = Path(source)
        cand = (cand if cand.is_absolute() else root / cand).resolve()
        inside = cand.is_relative_to(root)
        digest = ""
        if inside and cand.is_file():
            digest = hashlib.sha256(cand.read_bytes()).hexdigest()[:16]
        rel = str(cand.relative_to(root)) if inside else "<outside-project>"
        docs.append({"doc": rel, "source_id": str(source_id), "sha256_16": digest, "inside_project": str(inside)})
    _write({"kind": "retrieval", "project_id": project_id, "execution_path": path, "docs": docs})


def audit_answer(*, answer: str, tool_calls: list[str]) -> None:
    if not enabled():
        return
    _write({"kind": "answer", "tool_calls": tool_calls, **_marker_checks(answer)})


def audit_wire_messages(*, model: str, provider: str, purpose: str, messages: object) -> None:
    """Audit the exact message list placed in the provider HTTP payload (post assembly/truncation)."""
    if not enabled():
        return
    parts: list[str] = []
    if isinstance(messages, list):
        for msg in messages:
            content = msg.get("content") if isinstance(msg, dict) else None
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                parts.extend(str(p.get("text", "")) for p in content if isinstance(p, dict))
    text = "\n".join(parts)
    rag, rest = split_rag_segment(text)
    per_message: list[dict[str, object]] = []
    if isinstance(messages, list):
        for idx, msg in enumerate(messages):
            content = msg.get("content") if isinstance(msg, dict) else None
            body = content if isinstance(content, str) else ""
            per_message.append(
                {
                    "index": idx,
                    "role": str(msg.get("role", "")) if isinstance(msg, dict) else "",
                    "sha256_16": _sha16(body),
                    "chars": len(body),
                    **_marker_checks(body),
                }
            )
    segments = {
        name: {
            "present_in_input": bool(seg) and seg in text,
            "sha256_16": _sha16(seg),
            "chars": len(seg),
            **_marker_checks(seg),
        }
        for name, seg in _segments_for_request().items()
    }
    _write(
        {
            "kind": "wire_input",
            "per_message": per_message,
            "assembled_segments": segments,
            "rag_segment_chars": len(rag),
            "rag_segment": _marker_checks(rag),
            "non_rag_segment": _marker_checks(rest),
            "model": model,
            "provider": provider,
            "purpose": purpose,
            "messages": len(parts),
            "input_sha256": hashlib.sha256(text.encode("utf-8", "replace")).hexdigest(),
            "input_chars": len(text),
            "has_relevant_code": "<relevant_code>" in text,
            **_marker_checks(text),
        }
    )


_RAG_OPEN, _RAG_CLOSE = "<relevant_code>", "</relevant_code>"


def split_rag_segment(text: str) -> tuple[str, str]:
    """Return (all <relevant_code> blocks, everything else) of the assembled provider input."""
    rag: list[str] = []
    rest: list[str] = []
    pos = 0
    while True:
        start = text.find(_RAG_OPEN, pos)
        if start < 0:
            rest.append(text[pos:])
            break
        end = text.find(_RAG_CLOSE, start)
        end = len(text) if end < 0 else end + len(_RAG_CLOSE)
        rest.append(text[pos:start])
        rag.append(text[start:end])
        pos = end
    return "".join(rag), "".join(rest)


def audit_embed(*, inputs: int, ledger_cumulative: int | None, model: str) -> None:
    if not enabled():
        return
    _write({"kind": "embed_request", "inputs": inputs, "ledger_cumulative": ledger_cumulative, "model": model})


def audit_tool(*, name: str, stage: str) -> None:
    """Tool name and stage only (never args or results)."""
    if not enabled():
        return
    _write({"kind": "tool", "tool": name, "stage": stage})


_SEGMENTS: dict[str, dict[str, str]] = {}


def _sha16(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:16]


def _segments_for_request() -> dict[str, str]:
    return _SEGMENTS.get(_request_ids().get("request_id", ""), {})


def register_segments(segments: dict[str, str], *, rag_status: str) -> None:
    """Record the assembled context segments (question, rag code, file selection, past_memory, ...).

    Only hashes, sizes and synthetic-marker booleans are written; raw text stays in memory for the
    later wire-input contains-check of the same request and is never logged.
    """
    if not enabled():
        return
    rid = _request_ids().get("request_id", "")
    with _lock:
        if len(_SEGMENTS) > 64:
            _SEGMENTS.clear()
        _SEGMENTS[rid] = {k: v for k, v in segments.items() if v}
    _write(
        {
            "kind": "context_segments",
            "rag_status": rag_status,
            "segments": {
                k: {"sha256_16": _sha16(v), "chars": len(v), **_marker_checks(v)} for k, v in segments.items()
            },
        }
    )
