from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests import _cli_subprocess as helper


def test_active_environment_child_does_not_use_unprepared_project_uv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "uv"
    fake.write_text("#!/bin/sh\nexit 91\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.defpath)
    monkeypatch.delenv("AGK_TEST_PYTHON", raising=False)
    helper._has_uv.cache_clear()
    helper._sys_executable_can_import_package.cache_clear()
    assert sys.prefix != sys.base_prefix
    command = [*helper.python_invocation(project=True), "-c", "import antigravity_k; print('active-package-ready')"]
    result = subprocess.run(command, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "active-package-ready"


def test_explicit_child_interpreter_still_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGK_TEST_PYTHON", sys.executable)
    assert helper.python_invocation(project=True) == [sys.executable]
