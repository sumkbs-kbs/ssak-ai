from __future__ import annotations

import hashlib
import io
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import NoReturn


ROOT = Path("/Users/mr.k/program/coding/ssak_comp/Ssak-Ai")
OUT = Path(__file__).resolve().parent
STATE = OUT / "state"
SELECTORS = [
    "tests/test_chat_stream_cancel_cleanup.py::test_mid_token_aclose_from_other_task_closes_actual_runtime",
    "tests/test_chat_stream_cancel_cleanup.py::test_inflight_model_pull_cancel_closes_owner_context_once",
    "tests/test_cr14_task_cancel_ownership.py::test_store_refuses_a_cancel_owned_by_a_live_process_and_leaves_the_row_untouched",
    "tests/test_cr14_task_cancel_ownership.py::test_store_cancel_of_a_pending_task_actually_prevents_the_run",
    "tests/test_task_runner_resume.py::test_background_runner_preserves_an_approval_pause_from_the_tool_loop",
    "tests/test_task_runner_resume.py::test_resume_after_store_reopen_injects_only_its_task_context_snapshot",
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name: str, value: object) -> None:
    with (OUT / name).open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def child() -> int:
    sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
    os.chdir(STATE)
    os.environ["AGK_AUTO_DISCOVER_LOCAL_MODELS"] = "false"
    os.environ["AGK_ALLOWED_ROOTS"] = str(STATE)
    os.environ["AGK_USAGE_DB"] = str(STATE / "usage.json")
    attempts = []
    launches = []

    def denied(*args: object, **kwargs: object) -> NoReturn:
        attempts.append(repr(args))
        raise AssertionError("Physical networking is forbidden in lifecycle regression")

    def audit(event: str, args: tuple[object, ...]) -> None:
        if event == "subprocess.Popen":
            launches.append(repr(args[:3]))

    sys.addaudithook(audit)
    socket.socket.connect = denied
    socket.socket.connect_ex = denied
    socket.create_connection = denied

    from antigravity_k.config import config

    config.paths.project_root = STATE
    source_paths = [
        "src/antigravity_k/api/routes/chat.py",
        "src/antigravity_k/api/chat_agent_stream_generator.py",
        "src/antigravity_k/engine/task_runner.py",
        "src/antigravity_k/engine/task_state_store.py",
        "src/antigravity_k/engine/task_process_ownership.py",
        "src/antigravity_k/engine/task_context_snapshot.py",
        "src/antigravity_k/engine/agent_runtime.py",
        "src/antigravity_k/engine/provider_adapters/inference_providers.py",
        "src/antigravity_k/engine/provider_adapters/transport_errors.py",
        "src/antigravity_k/tools/egress_policy.py",
        *sorted({selector.split("::")[0] for selector in SELECTORS}),
    ]
    existing = [p for p in source_paths if (ROOT / p).is_file()]
    binding = {p: sha(ROOT / p) for p in existing}
    write("source-binding.json", binding)
    import pytest
    from antigravity_k.engine import provider_capability_probe_runtime
    from urllib.parse import urlsplit

    metadata_requests = []

    def metadata_terminal(request, **kwargs):
        url = urlsplit(request.full_url)
        assert url.hostname in {"localhost", "127.0.0.1", "::1"} and url.path == "/api/show"
        assert request.get_method() == "POST"
        metadata_requests.append({"url": request.full_url, "method": "POST", "body": json.loads(request.data)})
        return io.BytesIO(b'{"capabilities":["completion"]}')

    metadata_patch = pytest.MonkeyPatch()
    metadata_patch.setattr(provider_capability_probe_runtime, "_urlopen_provider", metadata_terminal)
    code = pytest.main([
        *[str(ROOT / selector) for selector in SELECTORS],
        "-c", str(ROOT / "pyproject.toml"),
        "--basetemp=" + str(STATE / "pytest-temp"),
        "--junitxml=" + str(OUT / "junit.xml"),
        "-p", "no:cacheprovider", "-q",
    ])
    metadata_patch.undo()
    drift = [p for p, value in binding.items() if sha(ROOT / p) != value]
    write("guard-and-binding.json", {
        "pytest_exit": int(code),
        "physical_socket_attempts": attempts,
        "subprocess_launches": launches,
        "mock_metadata_requests": metadata_requests,
        "source_drift": drift,
        "limits": "Existing mocked model/runtime boundaries with real threads, SQLite and owned sleep child; no OS restart/live inference claim",
    })
    return int(code) if not attempts and not drift else 1


def main() -> None:
    assert not (OUT / "receipt.json").exists(), "This selector invocation may run only once"
    STATE.mkdir()
    command = [str(ROOT / ".venv/bin/python"), str(Path(__file__).resolve()), "--child"]
    started = time.time()
    result = subprocess.run(command, cwd=STATE, capture_output=True, timeout=90, check=False)
    with (OUT / "stdout.log").open("xb") as stream:
        stream.write(result.stdout)
    with (OUT / "stderr.log").open("xb") as stream:
        stream.write(result.stderr)
    write("receipt.json", {
        "command": command,
        "selectors": SELECTORS,
        "started_unix": started,
        "ended_unix": time.time(),
        "exit_code": result.returncode,
        "stdout": {"path": "stdout.log", "sha256": sha(OUT / "stdout.log")},
        "stderr": {"path": "stderr.log", "sha256": sha(OUT / "stderr.log")},
        "driver_sha256": sha(Path(__file__)),
    })
    print(result.stdout.decode(errors="replace")[-4000:])
    print(json.dumps({"exit_code": result.returncode, "receipt": str(OUT / "receipt.json")}))
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    if "--child" in sys.argv:
        raise SystemExit(child())
    main()

