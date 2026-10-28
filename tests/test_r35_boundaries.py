"""r35: task-context restore contract, secret content binding, other reader paths (synthetic only)."""

from __future__ import annotations

import ast
import inspect
import os
import shutil
import sys
import textwrap
import threading
from pathlib import Path

import pytest

from antigravity_k.engine import tool_execution_journal as tej
from antigravity_k.engine.file_summarizer import FileSummarizer
from antigravity_k.tools.system_tools import ReadFileTool
from antigravity_k.tools.tool_contracts import Permission
from antigravity_k.tools.tool_registry import ToolRegistry

MARK = "SYNTH_R35_SECRET_q7"
MARK2 = "SYNTH_R35_CHANGED_k2"
PLAIN = "SYNTH_R35_PLAIN_z1"


# ---------------- 1. CURRENT_TASK restore contract ----------------
def test_scope_restores_previous_value_on_normal_and_exception() -> None:
    outer = tej.CURRENT_TASK.set(("outer", False))
    try:
        with tej.task_scope("t1", False):
            assert tej.CURRENT_TASK.get() == ("t1", False)
        assert tej.CURRENT_TASK.get() == ("outer", False)
        with pytest.raises(RuntimeError), tej.task_scope("t2", True):
            raise RuntimeError("boom")
        assert tej.CURRENT_TASK.get() == ("outer", False)
    finally:
        tej.CURRENT_TASK.reset(outer)
    assert tej.CURRENT_TASK.get() is None


def test_scope_restores_on_early_return_and_generator_close() -> None:
    def early() -> str:
        with tej.task_scope("t3", False):
            return "paused"

    assert early() == "paused" and tej.CURRENT_TASK.get() is None

    def gen():
        with tej.task_scope("t4", False):
            yield 1
            yield 2

    g = gen()
    next(g)
    g.close()  # cancel mid-stream
    assert tej.CURRENT_TASK.get() is None


def test_concurrent_tasks_and_next_request_do_not_mix(tmp_path: Path) -> None:
    seen: dict[str, list[object]] = {}
    barrier = threading.Barrier(2)

    def run(tid: str) -> None:
        with tej.task_scope(tid, False):
            barrier.wait()
            d = tmp_path / tid
            d.mkdir()
            _, exec_id = tej.journaled_write(str(d), str(d / "a.md"), tid)
            seen[tid] = [tej.CURRENT_TASK.get(), exec_id]
        seen[tid].append(tej.CURRENT_TASK.get())

    ts = [threading.Thread(target=run, args=(t,)) for t in ("ta", "tb")]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert seen["ta"][0] == ("ta", False) and seen["tb"][0] == ("tb", False)
    assert seen["ta"][1] == tej.execution_id("ta", "a.md") != seen["tb"][1]
    assert seen["ta"][2] is None and seen["tb"][2] is None
    # the next request (no task) is legacy per-call: no exec_id from a previous task
    d = tmp_path / "next"
    d.mkdir()
    assert tej.journaled_write(str(d), str(d / "a.md"), "x") == ("written", "")


def test_run_task_uses_scope_for_every_exit_path() -> None:
    from antigravity_k.engine.task_runner import BackgroundTaskRunner as TaskRunner

    src = textwrap.dedent(inspect.getsource(TaskRunner._run_task))
    assert "CURRENT_TASK.set" not in src and "task_scope(" in src
    tree = ast.parse(src)
    withs = [n for n in ast.walk(tree) if isinstance(n, ast.With) and "task_scope" in ast.unparse(n.items[0])]
    assert len(withs) == 1
    inner = {id(n) for n in ast.walk(withs[0])}
    loops = [n for n in ast.walk(tree) if isinstance(n, ast.For) and "_stream_task" in ast.unparse(n.iter)]
    assert loops and all(id(n) in inner for n in loops)  # cancel/pause returns live inside the scope


def test_registry_restores_approval_and_root_context(tmp_path: Path) -> None:
    from antigravity_k.tools import verified_read

    (tmp_path / "p.txt").write_text(PLAIN)
    reg = ToolRegistry(project_root=str(tmp_path))
    _ = reg.install(ReadFileTool())
    _ = reg.execute_with_permission("read_file", {"file_path": "p.txt"})
    assert verified_read.APPROVED_TARGET.get() is None and verified_read.READ_ROOT.get() is None


# ---------------- 2. secret content binding ----------------
@pytest.fixture
def proj(tmp_path: Path) -> Path:
    a = tmp_path / "proj"
    a.mkdir()
    (a / ".env").write_text(f"T={MARK}\n")
    (a / "main.py").write_text(f"# {PLAIN}\n")
    return a


def _reg(root: Path) -> ToolRegistry:
    reg = ToolRegistry(project_root=str(root))
    _ = reg.install(ReadFileTool())
    return reg


def test_same_inode_content_change_after_approval_requires_reapproval(proj: Path) -> None:
    reg = _reg(proj)
    ino = os.stat(proj / ".env").st_ino
    assert reg.execute_with_permission("read_file", {"file_path": ".env"})[0] is Permission.PROMPT
    with open(proj / ".env", "r+") as fh:  # in-place write: same inode
        fh.truncate(0)
        fh.write(f"T={MARK2}\n")
    assert os.stat(proj / ".env").st_ino == ino
    out = reg.execute_approved("read_file", {"file_path": ".env"})
    assert MARK2 not in out and MARK not in out and "re-approval" in out
    # old grant consumed: a new PROMPT + approval reads the new content
    assert reg.execute_with_permission("read_file", {"file_path": ".env"})[0] is Permission.PROMPT
    assert MARK2 in reg.execute_approved("read_file", {"file_path": ".env"})


def test_returned_bytes_are_the_hashed_bytes() -> None:
    src = inspect.getsource(__import__("antigravity_k.tools.verified_read", fromlist=["x"]).read_text)
    # one read from the verified fd, hash of that buffer, decode of that buffer: no reopen by path
    assert src.count("open_verified(") == 1 and "open(path" not in src and "data.decode" in src


# ---------------- FileSummarizer ----------------
def test_file_summarizer_refuses_secret_and_symlink_alias(proj: Path) -> None:
    os.symlink(proj / ".env", proj / "notes.txt")
    out = FileSummarizer().summarize_files([{"file": ".env"}, {"file": "notes.txt"}, {"file": "main.py"}], str(proj))
    assert MARK not in out and PLAIN in out


# ---------------- write_artifact path (scenario A) ----------------
def test_artifact_write_never_follows_symlinked_dir_or_target(tmp_path: Path) -> None:
    out = tmp_path / "outside"
    out.mkdir()
    (tmp_path / "artdir").symlink_to(out, target_is_directory=True)
    with pytest.raises(OSError):
        tej.atomic_write(str(tmp_path / "artdir" / "a.md"), "x")
    assert not (out / "a.md").exists()
    real = tmp_path / "real"
    real.mkdir()
    victim = tmp_path / "victim.txt"
    victim.write_text(PLAIN)
    (real / "a.md").symlink_to(victim)
    tej.atomic_write(str(real / "a.md"), "new")
    assert victim.read_text() == PLAIN and not (real / "a.md").is_symlink()
    (real / ".tool_journal.jsonl").symlink_to(victim)
    with pytest.raises(OSError):
        tej.Journal(str(real)).append({"exec_id": "x", "state": "intent"})
    assert victim.read_text() == PLAIN


# ---------------- shell (real seatbelt, synthetic files) ----------------
@pytest.mark.skipif(sys.platform != "darwin" or not shutil.which("sandbox-exec"), reason="seatbelt only")
@pytest.mark.parametrize(
    ("cmd", "must_fail"),
    [
        ("cat .env", True),
        ("cat ./sub/../.env", True),
        ("grep -r SYNTH .", None),  # must not reveal MARK
        ("mv .env moved.txt", True),
        ("cp .env copied.txt", True),
        ("cat main.py", False),
    ],
)
def test_shell_sandbox_blocks_secret_names(proj: Path, cmd: str, must_fail: bool | None) -> None:
    from antigravity_k.engine.sandbox import SandboxRunner, _minimal_child_env

    (proj / "sub").mkdir()
    r = SandboxRunner(
        project_root=str(proj),
        enabled=True,
        network="none",
        timeout=20,
        restrict_reads=True,
        read_allow_paths=[str(proj)],
    )
    res = r.execute(cmd, env=_minimal_child_env(r.project_root), cwd=str(proj))
    assert res.sandboxed
    assert MARK not in (res.stdout + res.stderr)
    if must_fail is True:
        assert not res.success
    if must_fail is False:
        assert res.success and PLAIN in res.stdout
    assert (proj / ".env").read_text() == f"T={MARK}\n"


@pytest.mark.skipif(sys.platform != "darwin" or not shutil.which("sandbox-exec"), reason="seatbelt only")
def test_shell_hardlink_alias_is_documented_residual(proj: Path) -> None:
    from antigravity_k.engine.sandbox import SandboxRunner, _minimal_child_env

    r = SandboxRunner(
        project_root=str(proj),
        enabled=True,
        network="none",
        timeout=20,
        restrict_reads=True,
        read_allow_paths=[str(proj)],
    )
    res = r.execute("ln .env alias.txt && cat alias.txt", env=_minimal_child_env(r.project_root), cwd=str(proj))
    # record actual behaviour; the assertion is that creating the alias from the shell is refused
    assert MARK not in res.stdout, "RESIDUAL: hard-link alias readable from shell"


# ---------------- MCP (literal secret path refused before the server is called) ----------------
@pytest.mark.parametrize("args", [{"path": ".env"}, {"paths": ["ok.txt", "keys/server.pem"]}, {"q": "cat .ssh/id_rsa"}])
def test_mcp_literal_secret_path_is_refused_before_call(args: dict[str, object]) -> None:
    from antigravity_k.tools.mcp_tool_loader import MCPTool

    calls: list[object] = []
    tool = MCPTool(
        "fs_read",
        "synthetic",
        {"type": "object"},
        server_name="synth",
        annotations={"readOnlyHint": True},
        caller=lambda n, a: calls.append((n, a)) or "x",
    )
    out = tool(**args)
    assert "not allowed" in out and calls == []


def test_mcp_plain_args_still_reach_caller() -> None:
    from antigravity_k.tools.mcp_tool_loader import MCPTool
    from antigravity_k.tools.mcp_tool_result import MCPToolOutcome

    calls: list[object] = []
    tool = MCPTool(
        "fs_read",
        "synthetic",
        {"type": "object"},
        server_name="synth",
        annotations={"readOnlyHint": True},
        caller=lambda n, a: calls.append((n, dict(a))) or MCPToolOutcome(PLAIN),
    )
    _ = tool(path="main.py")
    assert calls and calls[0][1] == {"path": "main.py"}


# ---------------- the REAL app write_artifact tool (artifact_tools.WriteArtifactTool) ----------------
def test_app_write_artifact_tool_is_journaled_and_resume_skips(tmp_path: Path) -> None:
    from antigravity_k.tools.artifact_tools import WriteArtifactTool

    tool = WriteArtifactTool(project_root=str(tmp_path))
    with tej.task_scope("task_aw", False):
        out1 = tool.execute(artifact_name="r35-a.md", content="one")
    target = tmp_path / "artifacts" / "r35-a.md"
    assert "ARTIFACT GENERATED" in str(out1) and target.read_text() == "one"
    states = [__import__("json").loads(x)["state"] for x in (tmp_path / "artifacts" / ".tool_journal.jsonl").read_text().splitlines()]
    assert states == ["intent", "executed"]
    with tej.task_scope("task_aw", True):  # resume after restart: same call again
        out2 = tool.execute(artifact_name="r35-a.md", content="one")
    assert "ALREADY WRITTEN" in str(out2) and target.read_text() == "one"
    target.write_text("tampered")  # external change -> unknown -> held, never rewritten
    with tej.task_scope("task_aw", True):
        out3 = tool.execute(artifact_name="r35-a.md", content="one")
    assert "unknown state" in str(out3) and target.read_text() == "tampered"


def test_app_write_artifact_tool_does_not_follow_symlink(tmp_path: Path) -> None:
    from antigravity_k.tools.artifact_tools import WriteArtifactTool

    victim = tmp_path / "victim.txt"
    victim.write_text(PLAIN)
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts" / "x.md").symlink_to(victim)
    _ = WriteArtifactTool(project_root=str(tmp_path)).execute(artifact_name="x.md", content="new")
    assert victim.read_text() == PLAIN


# ---------------- MEMORY classification: recall yes, search/coding no ----------------
import pytest as _pt


@_pt.mark.parametrize("q", [
    "Which badge colour did we agree on for the Quillmere offsite?",
    "What did we decide about the release name?",
    "우리가 정한 배지 색이 뭐였지?",
])
def test_memory_recall_questions_classified_memory(q: str) -> None:
    from antigravity_k.api.routes.chat import _is_memory_recall
    assert _is_memory_recall(q)


@_pt.mark.parametrize("q", [
    "Explain the difference between a Python list and a tuple in two sentences.",
    "What is the latest stable release of the Rust compiler?",
    "Search the web for today's weather in Seoul",
    "Write a function that reverses a linked list",
    "How do I agree on an API contract with another team?",
    "최신 파이썬 버전 검색해줘",
])
def test_search_and_coding_not_memory(q: str) -> None:
    from antigravity_k.api.routes.chat import _is_memory_recall
    assert not _is_memory_recall(q)


# ---------------- search disabled => no network before any request ----------------
@_pt.mark.parametrize("env", [{"AGK_SEARCH_ENABLED": "false"}, {"AGK_SEARCH_OFFLINE": "1"}])
def test_web_search_tool_refuses_without_network(monkeypatch, env) -> None:
    import socket

    from antigravity_k.tools.web_search_tool import WebSearchTool

    for k, v in env.items():
        monkeypatch.setenv(k, v)

    def _no_net(*a, **k):
        raise AssertionError("network attempted")

    monkeypatch.setattr(socket.socket, "connect", _no_net)
    monkeypatch.setattr(socket, "create_connection", _no_net)
    out = WebSearchTool().execute(query="latest Rust release")
    assert "disabled" in out and "no request sent" in out


def test_chat_fast_search_gated_by_search_disabled() -> None:
    import ast
    src = Path(__file__).resolve().parents[1].joinpath("src/antigravity_k/api/routes/chat.py").read_text()
    i = src.index("web_search_disabled():  # r35")
    j = src.index("tool = WebSearchTool()")
    assert i < j
    ast.parse(src)
