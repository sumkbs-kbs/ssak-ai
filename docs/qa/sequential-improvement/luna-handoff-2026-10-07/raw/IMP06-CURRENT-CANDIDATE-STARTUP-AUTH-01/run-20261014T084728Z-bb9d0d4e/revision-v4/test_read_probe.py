"""Pure read-probe audit policy checks; no subprocess is launched."""

import json
import sys
from pathlib import Path

import pytest
from startup_probe.contract import ProbeError
from startup_probe.guard import Guard


@pytest.mark.parametrize("executable", ["file", "/usr/bin/file"])
def test_exact_interpreter_probe_allowed(executable: str, tmp_path: Path) -> None:
    guard = Guard(tmp_path)
    argv = [executable, "-b", str(Path(sys.executable).resolve())]
    guard.audit("subprocess.Popen", (executable, argv, None, {"PATH": "/usr/bin:/bin"}))
    assert guard.violations == []
    receipt = json.loads(guard.subprocesses[-1])
    assert receipt["argv"] == argv
    assert receipt["file_sha256"] and receipt["platform_sha256"]


@pytest.mark.parametrize(
    ("executable", "argv", "path"),
    [
        ("file", ["file", "-b", "/private/secret"], "/usr/bin:/bin"),
        ("file", ["file", "-f", "/private/list"], "/usr/bin:/bin"),
        ("file", ["file", "-b", str(Path(sys.executable).resolve()), "/extra"], "/usr/bin:/bin"),
        ("/tmp/file", ["/tmp/file", "-b", str(Path(sys.executable).resolve())], "/usr/bin:/bin"),
        ("sh", ["sh", "-c", "file -b /private/secret"], "/usr/bin:/bin"),
        ("file", ["file", "-b", str(Path(sys.executable).resolve())], "/tmp:/usr/bin:/bin"),
    ],
)
def test_other_probe_denied(executable: str, argv: list[str], path: str, tmp_path: Path) -> None:
    guard = Guard(tmp_path)
    with pytest.raises(ProbeError):
        guard.audit("subprocess.Popen", (executable, argv, None, {"PATH": path}))
    assert len(guard.violations) == 1
