"""r37 prerequisite regressions: root≠auto-pilot, bound write approval, vault project_id validation,
resume cursor join. Real PermissionGate / ApprovalManager / FastAPI vault routes / ResumeJoiner;
no permission check is mocked. The only stub is the project vault factory (RAG off, no embed)."""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from antigravity_k.engine.approval_manager import (
    ApprovalDecision,
    ApprovalManager,
    approval_binding,
    describe_write_target,
)
from antigravity_k.engine.task_runner import ResumeJoiner, resume_control_kind
from antigravity_k.tools.permission_gate import PermissionGate
from antigravity_k.tools.tool_contracts import Permission, ToolInvocation, ToolSpec


# ─── 1. root setting keeps the user's mode ─────────────────────────────────
@pytest.mark.parametrize("mode", ["strict", "balanced", "permissive", "auto-pilot"])
def test_set_project_root_keeps_mode(tmp_path: Path, mode: str) -> None:
    gate = PermissionGate(project_root=str(tmp_path / "a"), mode=mode)
    gate.set_project_root(str(tmp_path / "b"))
    assert gate.mode == mode
    assert gate.project_root == str(tmp_path / "b")


def test_balanced_mode_still_prompts_after_root_change(tmp_path: Path) -> None:
    (tmp_path / "b").mkdir()
    gate = PermissionGate(project_root=str(tmp_path / "a"), mode="balanced")
    gate.set_project_root(str(tmp_path / "b"))
    spec = ToolSpec(name="write_artifact", risk_level="medium", category="file")
    decision = gate.decide(ToolInvocation(spec, {"artifact_name": "x.md", "content": "y"}))
    assert decision.permission != Permission.ALLOW


def test_tool_registry_root_change_keeps_mode(tmp_path: Path) -> None:
    from antigravity_k.tools.tool_registry import ToolRegistry

    reg = ToolRegistry(project_root=str(tmp_path))
    gate = reg._permission_gate  # pyright: ignore[reportPrivateUsage]
    gate.mode = "balanced"
    reg.set_project_root(str(tmp_path / "other"))
    assert gate.mode == "balanced"


# ─── 2. approval payload shows the real target and is bound ────────────────
def _mgr() -> ApprovalManager:
    from antigravity_k.engine.approval_review import ApprovalReview, ApprovalReviewDecision

    class _Rev:
        def review(self, _req: object) -> ApprovalReview:
            return ApprovalReview(
                decision=ApprovalReviewDecision.ESCALATE, risk_score=1.0, reason_codes=(), rationale="", reviewer="t"
            )

    return ApprovalManager(review_provider=_Rev())  # pyright: ignore[reportArgumentType]


def test_write_artifact_payload_has_target_action_diff(tmp_path: Path) -> None:
    root = tmp_path / "alpha"
    root.mkdir()
    mgr = _mgr()
    req = mgr.request_approval(
        "write_artifact", {"artifact_name": "rec", "content": "line one\n"}, project_root=str(root)
    )
    d = req.to_dict()
    assert d["target"] is not None
    assert d["target"]["project"] == "alpha" and d["target"]["path"] == "artifacts/rec.md"
    assert d["target"]["action"] == "create" and d["target"]["outside_root"] is False
    assert "line one" in d["diff_preview"] and "alpha/artifacts/rec.md" in d["diff_preview"]
    assert "_real" not in d["target"] and str(tmp_path) not in str(d)
    assert str(d["args"]["content"]).startswith("[9 chars, sha256:")
    (root / "artifacts").mkdir()
    (root / "artifacts" / "rec.md").write_text("old\n")
    d2 = mgr.request_approval(
        "write_artifact", {"artifact_name": "rec", "content": "new\n"}, project_root=str(root)
    ).to_dict()
    assert d2["target"] is not None and d2["target"]["action"] == "overwrite"
    assert "-old" in d2["diff_preview"] and "+new" in d2["diff_preview"]


def test_write_file_modify_and_secret_never_shown(tmp_path: Path) -> None:
    root = tmp_path / "alpha"
    root.mkdir()
    mgr = _mgr()
    secret = "api_key=sk-SYNTHETIC-r37-should-not-show"
    d = mgr.request_approval(
        "write_file", {"file_path": "conf.txt", "content": secret}, project_root=str(root)
    ).to_dict()
    assert "sk-SYNTHETIC" not in str(d)
    d3 = mgr.request_approval(
        "edit_file", {"file_path": "a.py", "old_str": "x", "new_str": "y"}, project_root=str(root)
    ).to_dict()
    assert d3["target"] is not None and d3["target"]["action"] == "modify"
    d4 = mgr.request_approval(
        "write_file", {"file_path": "../escape.txt", "content": "z"}, project_root=str(root)
    ).to_dict()
    assert d4["target"] is not None and d4["target"]["outside_root"] is True
    assert str(tmp_path) not in str(d4)


def _approve(mgr: ApprovalManager, tool: str, args: dict, root: Path) -> None:  # type: ignore[type-arg]
    req = mgr.request_approval(tool, args, project_root=str(root))
    assert mgr.resolve(req.request_id, ApprovalDecision.APPROVE)


def _bind(tool: str, args: dict, root: Path) -> str:  # type: ignore[type-arg]
    return approval_binding(tool, args, describe_write_target(tool, args, str(root)))


def test_approval_bound_to_target_and_action(tmp_path: Path) -> None:
    root = tmp_path / "alpha"
    root.mkdir()
    mgr = _mgr()
    args = {"artifact_name": "rec", "content": "v1\n"}
    _approve(mgr, "write_artifact", args, root)
    # different target -> not consumed
    assert not mgr.consume_one_time_approval(
        "write_artifact", _bind("write_artifact", {**args, "artifact_name": "other"}, root)
    )
    # different content -> not consumed
    assert not mgr.consume_one_time_approval(
        "write_artifact", _bind("write_artifact", {**args, "content": "v2\n"}, root)
    )
    # different project root -> not consumed
    other = tmp_path / "beta"
    other.mkdir()
    assert not mgr.consume_one_time_approval("write_artifact", _bind("write_artifact", args, other))
    # action changed create -> overwrite (file appeared after approval) -> not consumed
    (root / "artifacts").mkdir()
    (root / "artifacts" / "rec.md").write_text("x")
    assert not mgr.consume_one_time_approval("write_artifact", _bind("write_artifact", args, root))
    (root / "artifacts" / "rec.md").unlink()
    # exact same target/action/args -> consumed exactly once
    assert mgr.consume_one_time_approval("write_artifact", _bind("write_artifact", args, root))
    assert not mgr.consume_one_time_approval("write_artifact", _bind("write_artifact", args, root))


def test_executor_registration_requires_reapproval_on_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from antigravity_k.engine import approval_manager as am
    from antigravity_k.engine.tool_executor import ToolExecutor

    root = tmp_path / "alpha"
    root.mkdir()
    mgr = _mgr()
    monkeypatch.setattr(am, "_approval_manager", mgr)
    ex = ToolExecutor.__new__(ToolExecutor)
    ex.project_root = str(root)  # type: ignore[attr-defined]
    monkeypatch.setattr(ex, "_broadcast_approval_required", lambda *a: None)
    args = {"artifact_name": "rec", "content": "v1\n"}
    run, rid = ex._register_approval_request("write_artifact", args, "needs approval")  # pyright: ignore[reportPrivateUsage]
    # r40: returns (ApprovalEvidence | None, request_id); found evidence is NOT consumed here
    assert run is None and rid
    assert mgr.resolve(rid, ApprovalDecision.APPROVE)
    run2, rid2 = ex._register_approval_request("write_artifact", {**args, "artifact_name": "evil"}, "r")  # pyright: ignore[reportPrivateUsage]
    assert run2 is None and rid2 and rid2 != rid
    pend = mgr.get_pending()
    assert any(p.request_id == rid2 and p.target and p.target["path"] == "artifacts/evil.md" for p in pend)
    run3, _ = ex._register_approval_request("write_artifact", args, "r")  # pyright: ignore[reportPrivateUsage]
    assert run3 is not None  # evidence found (consumed later, at execution start)


# ─── 3. vault project_id validated, no cross-project store ─────────────────
def _git_init(d: Path) -> None:
    d.mkdir(parents=True, exist_ok=True)
    _ = subprocess.run(
        ["git", "init", "-q", "-b", "main"],
        cwd=d,
        check=True,
        capture_output=True,
        env={"HOME": str(d), "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"},
    )


@pytest.fixture
def two_projects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, str, str, Path, Path]]:
    from antigravity_k.api import dependencies
    from antigravity_k.api.server import app
    from antigravity_k.config import config as app_config
    from antigravity_k.engine import project_registry as pr
    from antigravity_k.engine.project_memory_paths import project_vault_dir
    from antigravity_k.engine.vault import VaultEngine

    allowed = tmp_path / "allowed"
    a, b = allowed / "alpha", allowed / "beta"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    monkeypatch.setenv("AGK_ALLOWED_ROOTS", str(allowed))
    reg = pr.ProjectRegistry(storage_path=tmp_path / "reg" / "projects.json")
    pa = reg.add_project("alpha", str(a))
    pb = reg.add_project("beta", str(b))
    monkeypatch.setattr(pr, "_global_registry", reg)

    def build(root: str) -> VaultEngine:
        vd = Path(project_vault_dir(root))
        if not (vd / ".git").exists():
            _git_init(vd)
        return VaultEngine(vault_path=str(vd), sync_rag=False)

    monkeypatch.setattr(dependencies, "_build_project_vault", build)
    ambient = tmp_path / "ambient"
    _git_init(ambient)
    monkeypatch.setattr(dependencies, "vault_engine", VaultEngine(vault_path=str(ambient), sync_rag=False))
    from antigravity_k.api.project_binding import get_session_project_bindings

    store = get_session_project_bindings()
    saved = dict(store._bindings)  # pyright: ignore[reportPrivateUsage]
    store.reset_all()  # isolate from other tests' session bindings
    client = TestClient(app, raise_server_exceptions=False)
    client.headers.update({"X-Access-Pin": app_config.security.access_pin})
    yield client, pa.id, pb.id, a, ambient
    store.reset_all()
    store._bindings.update(saved)  # pyright: ignore[reportPrivateUsage]
    for pid in (pa.id, pb.id):
        dependencies.evict_project_runtime(pid)


def test_vault_wrong_project_id_rejected_no_fallback(two_projects: tuple[TestClient, str, str, Path, Path]) -> None:
    client, _pa, _pb, _a, ambient = two_projects
    before = sorted(p.name for p in ambient.rglob("*.md"))
    r = client.post(
        "/api/vault/write", json={"path": "n.md", "content": "MEMO-X"}, headers={"X-AGK-Project-Id": "proj_nope"}
    )
    assert r.status_code == 404
    r2 = client.get("/v1/notes/search", params={"q": "MEMO-X", "project_id": "proj_nope"})
    assert r2.status_code == 404
    assert sorted(p.name for p in ambient.rglob("*.md")) == before


def test_vault_project_mismatch_with_session_rejected(two_projects: tuple[TestClient, str, str, Path, Path]) -> None:
    from antigravity_k.api.project_binding import SESSION_ID_HEADER, bind_session_active_project

    client, pa, pb, _a, _amb = two_projects
    bind_session_active_project("sess-r37", pa)
    r = client.post(
        "/api/vault/write",
        json={"path": "n.md", "content": "Z"},
        headers={"X-AGK-Project-Id": pb, SESSION_ID_HEADER: "sess-r37"},
    )
    assert r.status_code == 409


def test_vault_no_cross_project_save_search_modify(two_projects: tuple[TestClient, str, str, Path, Path]) -> None:
    client, pa, pb, a, ambient = two_projects
    fact = "R37-ALPHA-ONLY-FACT-7731"
    assert (
        client.post(
            "/api/vault/write", json={"path": "memo.md", "content": fact}, headers={"X-AGK-Project-Id": pa}
        ).status_code
        == 200
    )
    hits_a = client.get("/v1/notes/search", params={"q": fact, "project_id": pa}).json()["keyword_results"]
    hits_b = client.get("/v1/notes/search", params={"q": fact, "project_id": pb}).json()["keyword_results"]
    assert hits_a and not hits_b
    assert client.get("/api/vault/read", params={"path": "memo.md", "project_id": pb}).status_code == 404
    # modify through beta does not touch alpha's note
    assert (
        client.post(
            "/api/vault/write", json={"path": "memo.md", "content": "beta text"}, headers={"X-AGK-Project-Id": pb}
        ).status_code
        == 200
    )
    ra = client.get("/api/vault/read", params={"path": "memo.md", "project_id": pa}).json()
    assert fact in ra["content"] and "beta text" not in ra["content"]
    assert any(fact in p.read_text() for p in a.rglob("memo.md"))
    assert not any(fact in p.read_text() for p in ambient.rglob("*.md"))


# ─── 4. resume join at the streaming cursor ────────────────────────────────
def _join(prior: str, chunks: list[str]) -> str:
    j = ResumeJoiner(prior)
    out = "".join(j.feed(c) for c in chunks) + j.flush()
    return prior + out


def test_midline_pause_restart_not_duplicated() -> None:
    prior = "tool ok\nr36-A completed: artifa"
    assert (
        _join(prior, ["r36-A ", "completed: ", "artifact recorded.\n"])
        == "tool ok\nr36-A completed: artifact recorded.\n"
    )


def test_midline_pause_continuation_kept_verbatim() -> None:
    prior = "tool ok\nr36-A completed: artifa"
    assert _join(prior, ["ct recorded.\n"]) == "tool ok\nr36-A completed: artifact recorded.\n"


def test_korean_partial_uses_char_counts() -> None:
    prior = "결과\n알파 기록 완"  # 6 chars, 16 UTF-8 bytes
    assert _join(prior, ["알파 ", "기록 완료.\n"]) == "결과\n알파 기록 완료.\n"
    assert _join(prior, ["료.\n"]) == "결과\n알파 기록 완료.\n"


def test_complete_line_repeat_dropped_but_new_lines_kept() -> None:
    prior = "a\nfinal line\n"
    assert _join(prior, ["final line\n", "next\n"]) == "a\nfinal line\nnext\n"
    assert _join(prior, ["other\n"]) == "a\nfinal line\nother\n"


def test_short_stream_flush_never_loses_text() -> None:
    prior = "x\nlong partial line"
    assert _join(prior, ["ab"]) == "x\nlong partial lineab"


def test_control_events_classified() -> None:
    assert resume_control_kind("\n🧭 대화 이력이 길어 핵심 궤적을 압축했습니다.\n\n") == "compaction_notice"
    assert resume_control_kind("🏢 ") == "banner"
    assert resume_control_kind("r36-A completed") is None
    assert resume_control_kind("🧭 inside text then more\nbody") is None


# ─── 5. runner-level: mid-line pause → restart → resume (control events + restart) ──
import threading  # noqa: E402
import time  # noqa: E402
from collections.abc import Callable  # noqa: E402
from contextlib import contextmanager  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from antigravity_k.engine.task_execution_context import TaskExecutionContext  # noqa: E402
from antigravity_k.engine.task_runner import BackgroundTaskRunner  # noqa: E402
from antigravity_k.engine.tool_loop import ToolLoopEngine  # noqa: E402


def _wait(pred: Callable[[], bool], timeout: float = 8.0) -> None:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return
        time.sleep(0.01)
    raise AssertionError("condition not reached")


class _MidOrch:
    vault_engine = None

    def __init__(self, chunks: list[str]) -> None:
        self.chunks = chunks
        self.gate = threading.Semaphore(0)
        self.task_execution_context: TaskExecutionContext | None = None
        self.status_at_tool_done: list[str] = []

    @contextmanager
    def bind_task_execution(self, task_id, state_store) -> Iterator[None]:  # type: ignore[no-untyped-def]
        self.task_execution_context = TaskExecutionContext(task_id, state_store)
        try:
            yield
        finally:
            self.task_execution_context = None

    def run_stream(self, messages, target_model) -> Iterator[str]:  # type: ignore[no-untyped-def]
        from antigravity_k.engine.chat_stream_events import ProgressChunk

        for c in self.chunks:
            assert self.gate.acquire(timeout=5)
            yield ProgressChunk(c) if c.lstrip().startswith(("🧭", "🏢")) else c
        shim = SimpleNamespace(orch=self)
        shim._task_execution_context = lambda: ToolLoopEngine._task_execution_context(shim)  # type: ignore[attr-defined]
        shim._state_store = ToolLoopEngine._state_store  # type: ignore[attr-defined]
        ToolLoopEngine._transition_task_state(shim, "done", output="segment")  # type: ignore[arg-type]
        ctx = self.task_execution_context
        assert ctx is not None
        rec = ctx.state_store.get_task(ctx.task_id)
        self.status_at_tool_done.append(rec["status"] if rec else "?")
        yield "\n[quality_check done]\n"


def test_runner_midline_resume_no_duplicate_no_notice_in_body(tmp_path: Path) -> None:
    db = str(tmp_path / "t.db")
    r1 = BackgroundTaskRunner(db_path=db)
    o1 = _MidOrch(["tool ok\n", "r37-A completed: artifa", "ct never-reached\n"])
    tid = r1.submit_task("synthetic r37 mid-line task", orchestrator=o1, target_model="fake")
    _wait(lambda: (r1.state_store.get_task(tid) or {}).get("status") == "running")
    o1.gate.release(1)
    time.sleep(0.2)
    assert r1.pause_task(tid) == "pausing"
    o1.gate.release(1)
    _wait(lambda: (r1.state_store.get_task(tid) or {}).get("status") == "paused")
    phase1 = r1.state_store.get_task(tid)["output"]  # type: ignore[index]
    assert phase1.endswith("r37-A completed: artifa")

    r2 = BackgroundTaskRunner(db_path=db)
    o2 = _MidOrch(
        ["\n🧭 대화 이력이 길어 핵심 궤적을 압축했습니다.\n\n", "🏢 ", "r37-A ", "completed: ", "artifact recorded.\n"]
    )
    assert r2.resume_task(tid, orchestrator=o2, target_model="fake")
    o2.gate.release(10)
    _wait(lambda: (r2.state_store.get_task(tid) or {}).get("status") == "done")
    final = r2.state_store.get_task(tid)["output"]  # type: ignore[index]
    assert final.startswith(phase1)
    assert final.count("r37-A completed") == 1
    assert "r37-A completed: artifact recorded.\n" in final
    assert "🧭" not in final and "🏢" not in final
    assert final.index("[quality_check done]") > final.index("artifact recorded")
    assert o2.status_at_tool_done == ["running"]  # completed is not recorded before quality checks
    events = (
        [e["event_type"] for e in r2.state_store.list_execution_events(tid)]
        if hasattr(r2.state_store, "list_execution_events")
        else []
    )
    if events:
        assert "task.resume.control_event" in events


# --- r37 adversarial finding c04: hard-link alias to an outside inode must be refused ---
def test_verified_read_refuses_hardlink_alias(tmp_path):
    import os as _os

    from antigravity_k.tools import verified_read

    outside = tmp_path / "outside"
    proj = tmp_path / "proj"
    outside.mkdir()
    proj.mkdir()
    secret = outside / "note.txt"
    secret.write_text("R37-SYNTHETIC-OUTSIDE", encoding="utf-8")
    alias = proj / "alias-hard.txt"
    _os.link(secret, alias)
    with pytest.raises(verified_read.VerifiedReadError, match="hard-linked"):
        verified_read.read_text_under(str(alias), str(proj))
    single = proj / "plain.txt"
    single.write_text("ok", encoding="utf-8")
    assert verified_read.read_text_under(str(single), str(proj)) == "ok"
