"""code-server must not start by default; explicit opt-in runs preflight checks."""

from pathlib import Path
from unittest import mock

import pytest

from antigravity_k.engine import ide_server
from antigravity_k.engine.ide_server import IDE_AUTOSTART_ENV, IDEServer, ide_autostart_requested

SERVER = Path(__file__).resolve().parents[1] / "src/antigravity_k/api/server.py"


@pytest.mark.parametrize("value", ["0", "false", "no", "OFF"])
def test_autostart_explicit_off(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(IDE_AUTOSTART_ENV, value)
    assert ide_autostart_requested() is False


@pytest.mark.parametrize("value", [None, "1", "true", "YES", "on"])
def test_dev_default_and_explicit_on_keep_autostart(monkeypatch: pytest.MonkeyPatch, value: str | None) -> None:
    if value is None:
        monkeypatch.delenv(IDE_AUTOSTART_ENV, raising=False)
    else:
        monkeypatch.setenv(IDE_AUTOSTART_ENV, value)
    assert ide_autostart_requested() is True


def test_dmg_launcher_disables_autostart_but_honours_explicit_request() -> None:
    script = (Path(__file__).resolve().parents[1] / "scripts/build_mac_dmg.sh").read_text()
    assert 'export AGK_IDE_SERVER_AUTOSTART="${AGK_IDE_SERVER_AUTOSTART:-0}"' in script


def test_lifespan_block_has_no_unconditional_start() -> None:
    block = SERVER.read_text().split("# 6) IDE Server")[1].split("# 7)")[0]
    assert "if ide_autostart_requested():" in block
    assert ".start()" not in block


def test_disabled_lifespan_block_makes_zero_ide_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(IDE_AUTOSTART_ENV, "0")
    with (
        mock.patch.object(IDEServer, "start_if_available") as sia,
        mock.patch.object(IDEServer, "start") as st,
        mock.patch("antigravity_k.engine.ide_server.subprocess.Popen") as popen,
    ):
        block = SERVER.read_text().split("# 6) IDE Server (code-server Web IDE)")[1].split("# 7)")[0]
        state = mock.MagicMock()
        state.state = mock.MagicMock(spec=[])
        namespace = {"app": state, "project_root": ".", "logger": mock.MagicMock()}
        exec(compile("if True:\n" + block, "server-block", "exec"), namespace)  # noqa: S102
    assert sia.call_count == st.call_count == popen.call_count == 0
    assert state.state.ide_status == "disabled"


@mock.patch("antigravity_k.engine.ide_server.subprocess.Popen")
def test_explicit_start_normal_path(popen: mock.MagicMock) -> None:
    popen.return_value.poll.return_value = None
    with (
        mock.patch.object(ide_server.shutil, "which", return_value="/x/code-server"),
        mock.patch.object(ide_server, "_port_in_use", return_value=False),
    ):
        srv = IDEServer(port=18999)
        assert srv.start_if_available() == "running"
    assert popen.call_count == 1
    assert popen.call_args.args[0][:3] == ["code-server", "--bind-addr", "127.0.0.1:18999"]


@mock.patch("antigravity_k.engine.ide_server.subprocess.Popen")
def test_not_installed_reports_status_without_spawn(popen: mock.MagicMock) -> None:
    with mock.patch.object(ide_server.shutil, "which", return_value=None):
        srv = IDEServer()
        assert srv.start_if_available() == "not_installed"
    assert popen.call_count == 0 and srv.process is None


@mock.patch("antigravity_k.engine.ide_server.subprocess.Popen")
def test_port_conflict_reports_status_and_leaves_port_alone(popen: mock.MagicMock) -> None:
    with (
        mock.patch.object(ide_server.shutil, "which", return_value="/x/code-server"),
        mock.patch.object(ide_server, "_port_in_use", return_value=True) as in_use,
    ):
        srv = IDEServer(port=8080)
        assert srv.start_if_available() == "port_in_use"
    in_use.assert_called_once_with(8080)
    assert popen.call_count == 0 and srv.process is None
