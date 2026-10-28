"""r32: intent events are structured and carry no raw text."""

import antigravity_k.engine.intent_observability as obs


def test_event_has_no_raw_text_and_is_bounded() -> None:
    secret = "SYNTHETIC-RAW-TEXT-r32"
    before = obs.snapshot()["total"]
    ev = obs.record("SEARCH", "keyword", True, "fast_search", len(secret))
    snap = obs.snapshot()
    assert snap["total"] == cast_int(before) + 1
    assert ev["text_len"] == len(secret)
    assert secret not in repr(snap)
    # r33 added model/parse/reply_len/final_path (still text-free)
    assert {"seq", "ts", "intent", "stage", "ok", "follow_up", "text_len"} <= set(ev)
    for _ in range(80):
        obs.record("GENERAL", "llm", True, "general", 1)
    assert len(obs.snapshot()["recent"]) == 50  # type: ignore[arg-type]


def cast_int(v: object) -> int:
    assert isinstance(v, int)
    return v
