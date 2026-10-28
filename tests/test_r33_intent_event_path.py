"""r33: intent events carry model, parse result and the final follow-up path — never raw text."""

from __future__ import annotations

import antigravity_k.engine.intent_observability as obs


def test_llm_event_records_model_parse_and_final_path() -> None:
    raw = "SYNTHETIC-R33-REQUEST-TEXT please explain"
    ev = obs.record("TDD", "llm", True, "tdd_rejected_no_code_signal", len(raw), model="qwen3.8:latest", parse="matched_tdd", reply_len=3)
    obs.finalize(ev, "general")
    latest = obs.snapshot()["recent"][-1]  # type: ignore[index]
    assert latest["model"] == "qwen3.8:latest"
    assert latest["parse"] == "matched_tdd" and latest["reply_len"] == 3
    assert latest["follow_up"] == "tdd_rejected_no_code_signal" and latest["final_path"] == "general"
    assert raw not in repr(obs.snapshot())


def test_model_label_drops_paths_and_unknown_values() -> None:
    ev = obs.record("GENERAL", "llm", True, "general", 1, model="/Users/x/models/m.gguf", parse="free text")
    obs.finalize(ev, "somewhere")
    assert ev["model"] == "" and ev["parse"] == "none" and ev["final_path"] == "general"


def test_provider_error_fallback_is_marked_not_ok() -> None:
    ev = obs.record("GENERAL", "llm_error_keyword_fallback", False, "general", 5, model="qwen3.8:latest", parse="provider_error")
    obs.finalize(ev, "general")
    assert ev["ok"] is False and ev["parse"] == "provider_error"


def test_finalize_none_is_noop() -> None:
    obs.finalize(None, "tdd")
