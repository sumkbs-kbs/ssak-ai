"""r27c2: opt-in provider-input audit records contains-checks and hashes only, never raw text."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from antigravity_k.engine import llm_input_audit as audit


def test_off_by_default_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(audit.AUDIT_PATH_ENV, raising=False)
    audit.audit_wire_messages(model="qwen3.8", provider="ollama", purpose="stream", messages=[{"content": "x"}])
    assert not audit.enabled() and list(tmp_path.iterdir()) == []


def test_wire_audit_contains_checks_without_raw_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = tmp_path / "audit.jsonl"
    monkeypatch.setenv(audit.AUDIT_PATH_ENV, str(out))
    monkeypatch.setenv(audit.EXPECT_ENV, "FACT-AAA-1")
    monkeypatch.setenv(audit.FORBID_ENV, "FACT-BBB-2")
    secretish = "synthetic body sentence with FACT-AAA-1 inside"
    audit.audit_wire_messages(
        model="qwen3.8", provider="ollama", purpose="stream", messages=[{"content": f"<relevant_code>{secretish}"}]
    )
    proj = tmp_path / "proj"
    (proj / "docs").mkdir(parents=True)
    (proj / "docs" / "a.md").write_text("FACT-AAA-1")
    audit.audit_retrieval(
        project_root=str(proj), project_id="p1", path="graph", sources=[("docs/a.md", "s1"), ("/etc/hosts", "s2")]
    )
    raw = out.read_text()
    assert secretish not in raw
    wire, retr = (json.loads(line) for line in raw.splitlines())
    assert wire["expect_fact_contained"] is True and wire["forbid_fact_contained"] is False
    assert wire["has_relevant_code"] is True and len(wire["input_sha256"]) == 64
    assert retr["docs"][0]["doc"] == "docs/a.md" and retr["docs"][0]["sha256_16"]
    assert retr["docs"][1]["doc"] == "<outside-project>"
