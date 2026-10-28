"""CR-04: API shell도 동일한 실행·승인 경계 (계획 카드 CR-04).

발견 S01(`api/routes/agent_tools.py`의 `run_shell`)은 ① `mode="auto-pilot"` 고정으로
현재 실행 권한 모드를 무시하고 ② 최소 env/제한 읽기를 전달하지 않아 부모 프로세스의
provider 키·서버 PIN/token secret이 자식 셸로 상속되며 ③ `sandbox_enabled=False`일 때
raw host 실행으로 대체됐다. 이 파일은 handler 단독이 아니라 **실제 인증 앱/HTTP**로
그 경계를 검증한다.

C04-01 auth+ALLOW 정상 실행
C04-02 ASK/DENY 실행 0회 (실행 marker 없음)
C04-03 합성 secret 비노출 (자식 env·오류 응답)
C04-04 CR-03 경계 재사용·backend fail-closed
C04-05 요청 root 고정·실패 응답 구분·기존 도구 회귀
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from antigravity_k.api.project_binding import (
    SESSION_ID_HEADER,
    bind_session_active_project,
    get_session_project_bindings,
    reset_bound_request_execution_context,
)
from antigravity_k.api.routes import agent_tools
from antigravity_k.api.server import app
from antigravity_k.config import config
from antigravity_k.engine.access_mode import AccessMode, get_access_mode, set_access_mode
from antigravity_k.engine.execution_mode import ExecutionMode
from antigravity_k.engine.project_registry import get_project_registry
from antigravity_k.engine.sandbox import SandboxResult

IS_MACOS = sys.platform == "darwin"
requires_seatbelt = pytest.mark.skipif(not IS_MACOS, reason="seatbelt backend required")

SENTINEL = "SYNTHETIC-CR04-SENTINEL-NOT-A-REAL-SECRET"
SYNTHETIC_SECRET_ENV = "AGK_CR04_SYNTHETIC_SECRET"
SYNTHETIC_SECRET_VALUE = "cr04-synthetic-4b71e2-should-not-leak"


def _outside_dir(prefix: str) -> Path:
    """사용자 임시 트리(/var/folders → /private/var/folders) 아래 합성 디렉터리."""
    return Path(os.path.realpath(tempfile.mkdtemp(prefix=prefix)))


def _restore_execution_mode(manager: Any, prior: ExecutionMode) -> None:
    if manager.current_mode is prior:
        return
    if prior is ExecutionMode.PLAN:
        _ = manager.switch_to_plan(reason="cr04-test-restore")
    elif prior is ExecutionMode.BUILD:
        _ = manager.switch_to_build(reason="cr04-test-restore")
    else:
        _ = manager.switch_to_interactive(reason="cr04-test-restore")


@pytest.fixture()
def shell_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, Path]]:
    """실제 앱 + 격리된 프로젝트 root/레지스트리/권한 모드."""
    import antigravity_k.engine.project_registry as preg
    from antigravity_k.api.dependencies import get_mode_manager

    # 허용 base를 tmp_path로 둔다 — 등록할 프로젝트 root가 그 안에 있어야
    # ARC-01 canonical root 검증을 통과한다(실사용과 동일한 순서).
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    monkeypatch.setattr(config.paths, "project_root", tmp_path)
    monkeypatch.setattr("antigravity_k.engine.project_registry._DEFAULT_STORAGE_PATH", tmp_path / "projects.json")
    monkeypatch.setattr(preg, "_global_registry", None)
    monkeypatch.delenv("AGK_ALLOWED_ROOTS", raising=False)

    get_session_project_bindings().reset_all()
    reset_bound_request_execution_context()

    prior_access_mode = get_access_mode()
    set_access_mode(AccessMode.FULL_ACCESS)
    # r39: FULL_ACCESS alone no longer implies auto-pilot. These tests exercise the explicit opt-in.
    from antigravity_k.engine.access_mode import ExecutionPolicy, set_execution_policy

    set_execution_policy(ExecutionPolicy.AUTO_PILOT)
    mode_manager = get_mode_manager()
    prior_execution_mode = mode_manager.current_mode

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, workspace
    finally:
        set_access_mode(prior_access_mode)
        set_execution_policy(None)
        _restore_execution_mode(mode_manager, prior_execution_mode)
        get_session_project_bindings().reset_all()
        reset_bound_request_execution_context()
        monkeypatch.setattr(preg, "_global_registry", None)


@pytest.fixture()
def pinned_shell_env(shell_env: tuple[TestClient, Path], tmp_path: Path) -> Iterator[tuple[TestClient, Path, str]]:
    """PIN이 설정된 인증 서버 + 발급된 bearer 토큰.

    자격증명 상태는 전역 공유 정책이므로 테스트 종료 시 원래 해시 경로로
    재초기화해 다음 테스트가 익명(open_loopback) 상태를 유지하게 한다.
    """
    import antigravity_k.api.auth_routes as auth_routes_mod
    from antigravity_k.api.auth_policy import init_shared_auth_policy

    client, workspace = shell_env
    original = {
        "access_pin": config.security.access_pin,
        "pin_hash_file": config.security.pin_hash_file,
        "token_secret_file": config.security.token_secret_file,
        "dev_allow": os.environ.get("AGK_SEC_DEV_NO_PIN_ALLOW"),
    }

    config.security.access_pin = "cr04-pin-2026"
    config.security.pin_hash_file = str(tmp_path / "auth_hash")
    config.security.token_secret_file = str(tmp_path / "token_secret")
    os.environ.pop("AGK_SEC_DEV_NO_PIN_ALLOW", None)
    auth_routes_mod._token_service = None
    auth_routes_mod._pin_hash = None
    auth_routes_mod.init_auth_state()

    try:
        login = client.post("/api/auth/login", json={"pin": "cr04-pin-2026"})
        assert login.status_code == 200, login.text
        yield client, workspace, str(login.json()["access_token"])
    finally:
        config.security.access_pin = str(original["access_pin"])
        config.security.pin_hash_file = str(original["pin_hash_file"])
        config.security.token_secret_file = str(original["token_secret_file"])
        if original["dev_allow"] is None:
            os.environ.pop("AGK_SEC_DEV_NO_PIN_ALLOW", None)
        else:
            os.environ["AGK_SEC_DEV_NO_PIN_ALLOW"] = str(original["dev_allow"])
        auth_routes_mod._token_service = None
        auth_routes_mod._pin_hash = None
        _ = init_shared_auth_policy(config.security.pin_hash_file)
        auth_routes_mod.init_auth_state()


def _shell(client: TestClient, workspace: Path, command: str, **overrides: Any) -> Any:
    payload: dict[str, Any] = {"command": command, "cwd": str(workspace), "timeout": 20}
    payload.update(overrides)
    return client.post("/api/agent/tools/shell/run", json=payload)


def _register_project(client: TestClient, name: str, path: Path) -> dict[str, Any]:
    path.mkdir(parents=True, exist_ok=True)
    response = client.post("/api/projects", json={"name": name, "path": str(path)})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    return body["project"]


# ── C04-01: auth + ALLOW 정상 실행 ────────────────────────────────────────


@requires_seatbelt
class TestAuthAndAllow:
    def test_pin_configured_requires_bearer_before_execution(
        self, pinned_shell_env: tuple[TestClient, Path, str]
    ) -> None:
        """PIN이 설정된 서버에서는 토큰 없는 요청이 실행 전에 401로 끝난다."""
        client, workspace, token = pinned_shell_env
        marker = workspace / "auth-marker.txt"
        command = "printf ran > auth-marker.txt"

        unauthenticated = _shell(client, workspace, command)
        assert unauthenticated.status_code == 401, unauthenticated.text
        assert not marker.exists()

        authorized = client.post(
            "/api/agent/tools/shell/run",
            json={"command": command, "cwd": str(workspace), "timeout": 20},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert authorized.status_code == 200, authorized.text
        assert marker.exists()

    def test_full_access_allow_executes_and_keeps_response_shape(self, shell_env: tuple[TestClient, Path]) -> None:
        client, workspace = shell_env

        response = _shell(client, workspace, "printf shell-ok")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["ok"] is True
        assert body["stdout"] == "shell-ok"
        assert body["returncode"] == 0
        assert body["sandboxed"] is True
        assert body["timed_out"] is False
        assert set(body) >= {
            "ok",
            "stdout",
            "stderr",
            "returncode",
            "sandboxed",
            "output_truncated",
            "timed_out",
        }


# ── C04-02: ASK/DENY는 실행 0회 ───────────────────────────────────────────


class TestAskDenyNeverExecutes:
    def test_read_only_mode_returns_403_approval_required_without_executing(
        self, shell_env: tuple[TestClient, Path]
    ) -> None:
        """읽기 전용(기존 실행 권한 모드)에서는 ASK → 실행 없이 403."""
        client, workspace = shell_env
        marker = workspace / "readonly-marker.txt"
        set_access_mode(AccessMode.READ_ONLY)

        response = _shell(client, workspace, "printf ran > readonly-marker.txt")

        assert response.status_code == 403, response.text
        assert response.json()["error"] == "shell_approval_required"
        assert response.json()["access_mode"] == "read_only"
        assert not marker.exists()

    def test_plan_mode_returns_403_policy_denied_without_executing(self, shell_env: tuple[TestClient, Path]) -> None:
        """Plan 실행 모드는 실행 도구를 허용하지 않는다 → DENY, 실행 0회."""
        from antigravity_k.api.dependencies import get_mode_manager

        client, workspace = shell_env
        marker = workspace / "plan-marker.txt"
        _ = get_mode_manager().switch_to_plan(reason="cr04-test")

        response = _shell(client, workspace, "printf ran > plan-marker.txt")

        assert response.status_code == 403, response.text
        assert response.json()["error"] == "shell_policy_denied"
        assert response.json()["execution_mode"] == "plan"
        assert not marker.exists()

    def test_dangerous_command_is_denied_before_execution(self, shell_env: tuple[TestClient, Path]) -> None:
        client, workspace = shell_env
        marker = workspace / "danger-marker.txt"

        response = _shell(client, workspace, "rm -rf / && printf ran > danger-marker.txt")

        assert response.status_code == 403, response.text
        assert response.json()["error"] == "shell_policy_denied"
        assert not marker.exists()

    def test_command_path_escape_is_denied_before_execution(self, shell_env: tuple[TestClient, Path]) -> None:
        client, workspace = shell_env
        outside = _outside_dir("cr04-escape-")
        marker = workspace / "escape-marker.txt"
        try:
            response = _shell(client, workspace, f"cat {outside}/nope.txt && printf ran > escape-marker.txt")
        finally:
            shutil.rmtree(outside, ignore_errors=True)

        assert response.status_code == 403, response.text
        assert response.json()["error"] == "shell_policy_denied"
        assert not marker.exists()

    def test_cwd_outside_request_root_is_rejected(self, shell_env: tuple[TestClient, Path]) -> None:
        client, workspace = shell_env
        outside = _outside_dir("cr04-cwd-")
        try:
            response = _shell(client, workspace, "printf ran", cwd=str(outside))
        finally:
            shutil.rmtree(outside, ignore_errors=True)

        assert response.status_code == 403, response.text


# ── C04-03: 합성 secret 비노출 ────────────────────────────────────────────


@requires_seatbelt
class TestSecretsDoNotReachChildOrErrorBody:
    def test_child_env_is_minimal_and_excludes_server_secrets(
        self, shell_env: tuple[TestClient, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, workspace = shell_env
        monkeypatch.setenv(SYNTHETIC_SECRET_ENV, SYNTHETIC_SECRET_VALUE)
        monkeypatch.setenv("AGK_SEC_ACCESS_PIN", "cr04-server-pin-value")
        monkeypatch.setenv("AGK_MODEL_API_KEY", "cr04-provider-key-value")

        response = _shell(client, workspace, f"printenv {SYNTHETIC_SECRET_ENV} || true; env")

        assert response.status_code == 200, response.text
        body = response.json()
        stdout = str(body["stdout"])
        combined = f"{stdout}\n{body['stderr']}\n{response.text}"

        assert SYNTHETIC_SECRET_VALUE not in combined
        assert "cr04-server-pin-value" not in combined
        assert "cr04-provider-key-value" not in combined
        # 최소 env만 상속된다 — AGK_* 접두사가 자식 환경에 존재하지 않는다.
        assert "AGK_" not in stdout
        assert "PATH=" in stdout

    def test_sandbox_unavailable_error_has_no_internal_paths(
        self, shell_env: tuple[TestClient, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, workspace = shell_env
        monkeypatch.setenv(SYNTHETIC_SECRET_ENV, SYNTHETIC_SECRET_VALUE)
        monkeypatch.setattr(config.security, "sandbox_enabled", False)

        response = _shell(client, workspace, "printf ran")

        assert response.status_code == 503, response.text
        body = response.json()
        assert body["error"] == "sandbox_unavailable"
        assert SYNTHETIC_SECRET_VALUE not in response.text
        assert str(workspace) not in response.text
        assert "raw" not in body["detail"].lower() or "disabled" in body["detail"].lower()


# ── C04-04: CR-03 경계 재사용·backend fail-closed ─────────────────────────


class TestSandboxBoundaryReused:
    def test_disabled_sandbox_fails_closed_without_executing(
        self, shell_env: tuple[TestClient, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """sandbox 비활성은 raw host 실행으로 대체되지 않는다 (실행 marker 없음)."""
        client, workspace = shell_env
        marker = workspace / "nosandbox-marker.txt"
        monkeypatch.setattr(config.security, "sandbox_enabled", False)

        response = _shell(client, workspace, "printf ran > nosandbox-marker.txt")

        assert response.status_code == 503, response.text
        assert response.json()["error"] == "sandbox_unavailable"
        assert not marker.exists()

    def test_runner_gets_cr03_read_boundary_and_minimal_env(
        self, shell_env: tuple[TestClient, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """생성된 runner가 restrict_reads/require_sandbox/최소 env를 실제로 받는지 고정."""
        client, workspace = shell_env
        calls: dict[str, Any] = {}

        class _RecordingRunner:
            def __init__(self, **kwargs: Any) -> None:
                calls["init"] = kwargs

            def execute(self, command: str, **kwargs: Any) -> SandboxResult:
                calls["execute"] = {"command": command, **kwargs}
                return SandboxResult(success=True, stdout="recorded", sandboxed=True)

        monkeypatch.setattr(agent_tools, "SandboxRunner", _RecordingRunner)

        response = _shell(client, workspace, "printf recorded")

        assert response.status_code == 200, response.text
        init = calls["init"]
        assert init["restrict_reads"] is True
        assert init["require_sandbox"] is True
        # project_root는 요청 root, 실행 디렉터리는 그 안의 cwd다.
        assert init["project_root"] == os.path.realpath(str(tmp_path))
        assert os.path.realpath(str(workspace)) in init["read_allow_paths"]
        execute = calls["execute"]
        assert execute["cwd"] == os.path.realpath(str(workspace))
        child_env = execute["env"]
        assert set(child_env) == {"PATH", "HOME", "TMPDIR", "PYTHONDONTWRITEBYTECODE"}
        assert "AGK_SEC_ACCESS_PIN" not in child_env
        # 자식 HOME/TMPDIR은 실행 root 안쪽이다(사용자 트리 미사용).
        assert child_env["HOME"].startswith(os.path.realpath(str(workspace)))

    @requires_seatbelt
    def test_other_process_temp_secret_is_not_readable(self, shell_env: tuple[TestClient, Path]) -> None:
        """CR-03 경계가 API shell에도 적용된다 — symlink target 읽기 거부."""
        client, workspace = shell_env
        outside = _outside_dir("cr04-read-")
        sentinel = outside / "other-process-secret.txt"
        sentinel.write_text(SENTINEL, encoding="utf-8")
        link = workspace / "outside-link.txt"
        link.symlink_to(sentinel)
        try:
            response = _shell(client, workspace, "cat outside-link.txt")
        finally:
            shutil.rmtree(outside, ignore_errors=True)

        assert response.status_code == 200, response.text
        body = response.json()
        assert SENTINEL not in str(body["stdout"])
        assert body["ok"] is False

    @requires_seatbelt
    def test_python_runtime_still_boots_inside_workspace(self, shell_env: tuple[TestClient, Path]) -> None:
        client, workspace = shell_env

        response = _shell(client, workspace, "python3 -c 'print(\"RUNTIME-OK\")'")

        assert response.status_code == 200, response.text
        assert "RUNTIME-OK" in response.json()["stdout"]


# ── C04-05: 요청 root 고정·실패 응답·기존 도구 회귀 ───────────────────────


@requires_seatbelt
class TestRequestRootPinning:
    def test_session_active_project_root_wins_over_global_workspace(
        self, shell_env: tuple[TestClient, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """전역 active project를 B로 바꿔도 명시한 session binding의 root A에서 실행한다."""
        from antigravity_k.api.routes import filesystem

        client, _workspace = shell_env
        alpha_dir = tmp_path / "alpha"
        beta_dir = tmp_path / "beta"
        alpha = _register_project(client, "Alpha", alpha_dir)
        beta = _register_project(client, "Beta", beta_dir)
        session_id = "cr04-root-lock"
        _ = bind_session_active_project(session_id, alpha["id"])

        alpha_root = os.path.realpath(str(alpha_dir))
        beta_root = os.path.realpath(str(beta_dir))
        monkeypatch.setattr(filesystem, "WORKSPACE_ROOT", beta_root)
        assert get_project_registry().switch_project(beta["id"]) is not None

        response = client.post(
            "/api/agent/tools/shell/run",
            json={"command": "pwd", "timeout": 20},
            headers={SESSION_ID_HEADER: session_id},
        )

        assert response.status_code == 200, response.text
        stdout = response.json()["stdout"]
        assert alpha_root in stdout
        assert beta_root not in stdout

    def test_explicit_project_id_pins_execution_root(self, shell_env: tuple[TestClient, Path], tmp_path: Path) -> None:
        client, _workspace = shell_env
        alpha_dir = tmp_path / "alpha-explicit"
        beta_dir = tmp_path / "beta-explicit"
        alpha = _register_project(client, "AlphaExplicit", alpha_dir)
        _ = _register_project(client, "BetaExplicit", beta_dir)

        response = _shell(client, Path(os.path.realpath(str(beta_dir))), "pwd", project_id=alpha["id"])

        # cwd가 alpha root 밖이면 실행 없이 403이다(요청 root 고정의 직접 증거).
        assert response.status_code == 403, response.text

        response_in_root = _shell(client, Path(os.path.realpath(str(alpha_dir))), "pwd", project_id=alpha["id"])
        assert response_in_root.status_code == 200, response_in_root.text
        assert os.path.realpath(str(alpha_dir)) in response_in_root.json()["stdout"]

    def test_root_does_not_move_when_active_project_switches_midflight(
        self, shell_env: tuple[TestClient, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """실행 직전/도중 전역 active project가 바뀌어도 실행 root는 요청 값이다."""
        client, _workspace = shell_env
        alpha_dir = tmp_path / "alpha-inflight"
        beta_dir = tmp_path / "beta-inflight"
        alpha = _register_project(client, "AlphaInflight", alpha_dir)
        beta = _register_project(client, "BetaInflight", beta_dir)
        session_id = "cr04-inflight"
        _ = bind_session_active_project(session_id, alpha["id"])
        alpha_root = os.path.realpath(str(alpha_dir))
        beta_root = os.path.realpath(str(beta_dir))

        calls: dict[str, Any] = {}

        class _SwitchingRunner:
            def __init__(self, **kwargs: Any) -> None:
                calls["init"] = kwargs

            def execute(self, command: str, **kwargs: Any) -> SandboxResult:
                calls["execute"] = {"command": command, **kwargs}
                # 실행 도중 전역 active project 전환 시도
                _ = get_project_registry().switch_project(beta["id"])
                return SandboxResult(success=True, stdout="switched", sandboxed=True)

        monkeypatch.setattr(agent_tools, "SandboxRunner", _SwitchingRunner)

        response = client.post(
            "/api/agent/tools/shell/run",
            json={"command": "pwd", "timeout": 20},
            headers={SESSION_ID_HEADER: session_id},
        )

        assert response.status_code == 200, response.text
        assert calls["init"]["project_root"] == alpha_root
        assert calls["execute"]["cwd"] == alpha_root
        assert beta_root not in calls["execute"]["cwd"]
        # 전역 전환 후에도 같은 session binding은 여전히 A를 가리킨다.
        second = client.post(
            "/api/agent/tools/shell/run",
            json={"command": "pwd", "timeout": 20},
            headers={SESSION_ID_HEADER: session_id},
        )
        assert second.status_code == 200, second.text


@requires_seatbelt
class TestFailureResponsesAreDistinct:
    def test_command_failure_is_a_result_not_a_policy_error(self, shell_env: tuple[TestClient, Path]) -> None:
        client, workspace = shell_env

        response = _shell(client, workspace, "exit 3")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["ok"] is False
        assert body["returncode"] == 3
        assert body["timed_out"] is False

    def test_timeout_is_reported_as_shell_timeout(self, shell_env: tuple[TestClient, Path]) -> None:
        client, workspace = shell_env

        response = _shell(client, workspace, "sleep 5", timeout=1)

        assert response.status_code == 504, response.text
        assert response.json()["error"] == "shell_timeout"

    def test_policy_errors_use_frozen_status_codes(self, shell_env: tuple[TestClient, Path]) -> None:
        from antigravity_k.api.contracts.shell import SHELL_ERROR_HTTP_STATUS

        assert SHELL_ERROR_HTTP_STATUS == {
            "shell_approval_required": 403,
            "shell_policy_denied": 403,
            "sandbox_unavailable": 503,
            "shell_timeout": 504,
        }


class TestExistingAgentToolsRegression:
    def test_fs_read_write_still_work(self, shell_env: tuple[TestClient, Path]) -> None:
        client, workspace = shell_env

        write = client.post(
            "/api/agent/tools/fs/write",
            json={"path": str(workspace / "regression.txt"), "content": "cr04-ok", "overwrite": True},
        )
        read = client.post("/api/agent/tools/fs/read", json={"path": str(workspace / "regression.txt")})

        assert write.status_code == 200, write.text
        assert read.status_code == 200, read.text
        assert read.json()["content"] == "cr04-ok"

    def test_read_only_mode_blocks_filesystem_write(self, shell_env: tuple[TestClient, Path]) -> None:
        """기존 실행 권한 모드는 fs 도구에도 동일하게 적용된다(읽기 전용 → 쓰기 403)."""
        client, workspace = shell_env
        set_access_mode(AccessMode.READ_ONLY)

        response = client.post(
            "/api/agent/tools/fs/write",
            json={"path": str(workspace / "readonly.txt"), "content": "nope", "overwrite": True},
        )

        assert response.status_code == 403, response.text
        assert not (workspace / "readonly.txt").exists()

    def test_error_bodies_are_json_without_internal_detail(self, shell_env: tuple[TestClient, Path]) -> None:
        client, workspace = shell_env
        set_access_mode(AccessMode.READ_ONLY)

        response = _shell(client, workspace, "printf ran")

        assert response.headers["content-type"].startswith("application/json")
        body = json.loads(response.text)
        assert body["ok"] is False
        assert body["error"] == "shell_approval_required"
        assert "correlation_id" in body
        assert str(workspace) not in response.text
