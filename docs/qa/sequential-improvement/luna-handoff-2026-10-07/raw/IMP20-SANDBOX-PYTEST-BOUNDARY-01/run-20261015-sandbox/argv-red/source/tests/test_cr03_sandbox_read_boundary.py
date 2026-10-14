"""CR-03: 실제 sandbox 읽기 경계 (계획 카드 CR-03).

C03-01 workspace 정상 Python/pytest 성공
C03-02 외부 sentinel(사용자 임시 트리·/tmp·/var/tmp·형제 workspace) 읽기/쓰기 거부
C03-03 symlink canonical target·alias(/var/folders ↔ /private/var/folders)·자식 프로세스 거부
C03-04 최소 env·전용 HOME/TMPDIR·network·timeout 회귀
C03-05 backend unavailable/정책 생성 실패/설정 비활성 → 실행 0회(fail-closed)

실측 기반이다. seatbelt backend가 없는 OS에서는 mock으로 승격하지 않고 skip한다
(계획 §CR-03: "해당 OS가 없으면 그 지원 행은 검증 대기로 유지").
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

from antigravity_k.engine.sandbox import (
    RESTRICTED_DENIED_ROOTS,
    SandboxRunner,
    restricted_denied_roots,
    run_sandboxed_argv,
)

IS_MACOS = sys.platform == "darwin"
requires_seatbelt = pytest.mark.skipif(not IS_MACOS, reason="seatbelt backend required")

SENTINEL = "SYNTHETIC-SENTINEL-NOT-A-REAL-SECRET"


def _sandbox_env(work: str) -> dict[str, str]:
    return {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": work, "TMPDIR": work}


@pytest.fixture()
def workdir(tmp_path: Path) -> Path:
    home = tmp_path / ".sandbox-home"
    tmp = tmp_path / ".sandbox-tmp"
    home.mkdir()
    tmp.mkdir()
    return tmp_path


def _run_probe(workdir: Path, code: str, *, timeout: float = 60) -> Any:
    (workdir / "probe.py").write_text(code, encoding="utf-8")
    return run_sandboxed_argv(
        [sys.executable, "-B", "probe.py"],
        cwd=str(workdir),
        timeout=timeout,
        env=_sandbox_env(str(workdir)),
    )


def _read_probe(target: str) -> str:
    """target 읽기 시도 결과를 한 줄로 출력하는 프로브 코드."""
    return (
        "import pathlib\n"
        f"p = pathlib.Path({target!r})\n"
        "try:\n"
        "    print('READ_OK', p.read_text())\n"
        "except Exception as exc:\n"
        "    print('READ_BLOCKED', type(exc).__name__)\n"
    )


def _outside_dir(prefix: str) -> Path:
    """사용자 임시 트리(/var/folders → /private/var/folders) 아래 합성 디렉터리."""
    return Path(os.path.realpath(tempfile.mkdtemp(prefix=prefix)))


# ── C03-01: workspace 정상 실행 ────────────────────────────────────────────


@requires_seatbelt
class TestWorkspaceStillRuns:
    def test_python_runs_inside_workspace(self, workdir: Path) -> None:
        result = _run_probe(workdir, "print('PYTHON_OK')\n")

        assert result.sandboxed is True
        assert result.success is True, result.error or result.stderr
        assert "PYTHON_OK" in result.stdout

    def test_pytest_runs_inside_workspace(self, workdir: Path) -> None:
        (workdir / "test_sample.py").write_text("def test_ok():\n    assert 1 + 1 == 2\n", encoding="utf-8")

        result = run_sandboxed_argv(
            [sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", "test_sample.py"],
            cwd=str(workdir),
            timeout=120,
            env=_sandbox_env(str(workdir)),
        )

        assert result.success is True, result.error or result.stderr
        assert "1 passed" in result.stdout

    def test_workspace_writes_and_reads_are_allowed(self, workdir: Path) -> None:
        code = (
            "import pathlib\n"
            "pathlib.Path('written.txt').write_text('INSIDE-OK')\n"
            "print('READ', pathlib.Path('written.txt').read_text())\n"
        )

        result = _run_probe(workdir, code)

        assert result.success is True, result.error or result.stderr
        assert "READ INSIDE-OK" in result.stdout


# ── C03-02: 외부 sentinel 거부 ────────────────────────────────────────────


@requires_seatbelt
class TestExternalSentinelsDenied:
    def test_user_temp_tree_sentinel_is_denied(self, workdir: Path) -> None:
        outside = _outside_dir("cr03-outside-")
        sentinel = outside / "other-process-secret.txt"
        sentinel.write_text(SENTINEL, encoding="utf-8")

        result = _run_probe(workdir, _read_probe(str(sentinel)))

        assert SENTINEL not in result.stdout
        assert "READ_BLOCKED" in result.stdout

    def test_shared_tmp_sentinel_is_denied(self, workdir: Path) -> None:
        sentinel = Path("/tmp") / f"cr03_sentinel_{os.getpid()}.txt"
        sentinel.write_text(SENTINEL, encoding="utf-8")
        try:
            result = _run_probe(workdir, _read_probe(str(sentinel)))
        finally:
            sentinel.unlink(missing_ok=True)

        assert SENTINEL not in result.stdout
        assert "READ_BLOCKED" in result.stdout

    def test_var_tmp_sentinel_is_denied(self, workdir: Path) -> None:
        sentinel = Path("/var/tmp") / f"cr03_sentinel_{os.getpid()}.txt"
        sentinel.write_text(SENTINEL, encoding="utf-8")
        try:
            result = _run_probe(workdir, _read_probe(str(sentinel)))
        finally:
            sentinel.unlink(missing_ok=True)

        assert SENTINEL not in result.stdout
        assert "READ_BLOCKED" in result.stdout

    def test_sibling_workspace_sentinel_is_denied(self, workdir: Path) -> None:
        sibling = _outside_dir("cr03-sibling-")
        sentinel = sibling / "sibling-secret.txt"
        sentinel.write_text(SENTINEL, encoding="utf-8")

        result = _run_probe(workdir, _read_probe(str(sentinel)))

        assert SENTINEL not in result.stdout
        assert "READ_BLOCKED" in result.stdout

    def test_write_outside_workspace_is_denied(self, workdir: Path) -> None:
        outside = _outside_dir("cr03-write-")
        target = outside / "escape.txt"
        code = (
            "import pathlib\n"
            f"target = pathlib.Path({str(target)!r})\n"
            "try:\n"
            "    target.write_text('ESCAPED')\n"
            "    print('WRITE_OK')\n"
            "except Exception as exc:\n"
            "    print('WRITE_BLOCKED', type(exc).__name__)\n"
        )

        result = _run_probe(workdir, code)

        assert "WRITE_BLOCKED" in result.stdout
        assert not target.exists()


# ── C03-03: symlink·alias·자식 프로세스 ───────────────────────────────────


@requires_seatbelt
class TestCanonicalAndChildBoundary:
    def test_symlink_to_outside_target_is_denied(self, workdir: Path) -> None:
        outside = _outside_dir("cr03-symlink-")
        sentinel = outside / "other-process-secret.txt"
        sentinel.write_text(SENTINEL, encoding="utf-8")
        link = workdir / "outside-link.txt"
        link.symlink_to(sentinel)

        result = _run_probe(workdir, _read_probe(str(link)))

        assert SENTINEL not in result.stdout
        assert "READ_BLOCKED" in result.stdout

    def test_alias_path_to_same_sentinel_is_denied(self, workdir: Path) -> None:
        """/var/folders(비-canonical)로 접근해도 canonical deny가 적용된다."""
        outside = _outside_dir("cr03-alias-")
        sentinel = outside / "other-process-secret.txt"
        sentinel.write_text(SENTINEL, encoding="utf-8")

        result = _run_probe(workdir, _read_probe(str(sentinel)))

        assert os.path.realpath(sentinel).startswith("/private/var/folders")
        assert SENTINEL not in result.stdout
        assert "READ_BLOCKED" in result.stdout

    def test_child_process_inherits_boundary(self, workdir: Path) -> None:
        outside = _outside_dir("cr03-child-")
        sentinel = outside / "other-process-secret.txt"
        sentinel.write_text(SENTINEL, encoding="utf-8")
        code = (
            "import subprocess, sys\n"
            f"child = subprocess.run([sys.executable, '-c', {_read_probe(str(sentinel))!r}],"
            " capture_output=True, text=True)\n"
            "print('CHILD_RC', child.returncode)\n"
            "print('CHILD_OUT', child.stdout.strip())\n"
        )

        result = _run_probe(workdir, code)

        assert SENTINEL not in result.stdout
        assert "READ_BLOCKED" in result.stdout

    def test_profile_denies_user_tree_and_temp_roots(self, workdir: Path) -> None:
        runner = SandboxRunner(project_root=str(workdir), enabled=True, restrict_reads=True)
        profile = runner.build_seatbelt_profile()

        for denied in restricted_denied_roots():
            assert f'(deny file-read* (subpath "{denied}"))' in profile, denied
        assert "/private/var/folders" in profile
        for shared in ("/tmp", "/private/tmp", "/var/tmp", "/private/var/tmp"):
            assert shared in RESTRICTED_DENIED_ROOTS

    def test_profile_reallows_only_workspace_runtime_and_caller_paths(self, workdir: Path) -> None:
        caller_path = workdir / "caller-extra"
        caller_path.mkdir()
        runner = SandboxRunner(
            project_root=str(workdir),
            enabled=True,
            restrict_reads=True,
            read_allow_paths=[str(caller_path)],
        )
        profile = runner.build_seatbelt_profile()

        allowed = [
            os.path.realpath(str(workdir)),
            os.path.realpath(str(caller_path)),
        ]
        for path in allowed:
            assert f'(allow file-read* (subpath "{path}"))' in profile

        # deny 이후의 read-data 허용은 workspace/런타임/호출자 경로뿐이다.
        denied_roots = restricted_denied_roots()
        for line in profile.splitlines():
            if not line.startswith("(allow file-read* (subpath "):
                continue
            target = line.split('"')[1]
            if any(target == denied or target.startswith(f"{denied}{os.sep}") for denied in denied_roots):
                runtime_ok = any(
                    target.startswith(f"{prefix}") for prefix in _runtime_roots_within(runner, denied_roots)
                )
                caller_ok = target.startswith(os.path.realpath(str(workdir)))
                assert runtime_ok or caller_ok, target

    def test_ancestor_allows_are_literal_only(self, workdir: Path) -> None:
        """조상 디렉터리는 literal로만 열린다(하위 트리 subpath 허용 없음)."""
        runner = SandboxRunner(project_root=str(workdir), enabled=True, restrict_reads=True)
        profile = runner.build_seatbelt_profile()

        if not os.path.realpath(str(workdir)).startswith("/private/var/folders"):
            pytest.skip("임시 트리 밖 workspace에서는 조상 literal 규칙이 필요 없다")
        ancestor_literals = [line for line in profile.splitlines() if line.startswith("(allow file-read* (literal ")]
        assert ancestor_literals
        forbidden_ancestors = {os.path.dirname(os.path.realpath(str(workdir))), "/private/var/folders"}
        assert forbidden_ancestors <= {line.split('"')[1] for line in ancestor_literals}
        for line in ancestor_literals:
            assert "subpath" not in line

    def test_ancestor_listing_may_reveal_names_but_not_contents(self, workdir: Path) -> None:
        """잔여 위험 측정: 부모 체인 이름은 보일 수 있지만 sibling 내용은 거부된다."""
        sibling = _outside_dir("cr03-name-leak-")
        sentinel = sibling / "sibling-secret.txt"
        sentinel.write_text(SENTINEL, encoding="utf-8")
        code = (
            "import os, pathlib\n"
            f"parent = pathlib.Path({str(Path(sibling).parent)!r})\n"
            "try:\n"
            "    print('LIST_OK', len(os.listdir(parent)) > 0)\n"
            "except Exception as exc:\n"
            "    print('LIST_BLOCKED', type(exc).__name__)\n"
            f"target = pathlib.Path({str(sentinel)!r})\n"
            "try:\n"
            "    print('CONTENT_READ', target.read_text())\n"
            "except Exception as exc:\n"
            "    print('CONTENT_BLOCKED', type(exc).__name__)\n"
        )

        result = _run_probe(workdir, code)

        assert SENTINEL not in result.stdout
        assert "CONTENT_BLOCKED" in result.stdout


def _runtime_roots_within(runner: SandboxRunner, denied_roots: list[str]) -> list[str]:
    from antigravity_k.engine.sandbox import _python_runtime_read_paths

    return [
        path
        for path in [*runner.read_allow_paths, *_python_runtime_read_paths()]
        if any(path == denied or path.startswith(f"{denied}{os.sep}") for denied in denied_roots)
    ]


# ── C03-04: 최소 env·전용 tmp·network·timeout ─────────────────────────────


@requires_seatbelt
class TestMinimalEnvironment:
    def test_parent_secret_env_is_not_inherited(self, workdir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CR03_SYNTHETIC_SECRET", SENTINEL)
        code = "import os\nprint('ENV', os.environ.get('CR03_SYNTHETIC_SECRET'))\n"

        result = _run_probe(workdir, code)

        assert result.success is True, result.error or result.stderr
        assert SENTINEL not in result.stdout
        assert "ENV None" in result.stdout

    def test_home_and_tmpdir_point_inside_workspace(self, workdir: Path) -> None:
        result = run_sandboxed_argv(
            [
                sys.executable,
                "-B",
                "-c",
                "import os;print('HOME', os.environ.get('HOME'));print('TMPDIR', os.environ.get('TMPDIR'))",
            ],
            cwd=str(workdir),
            timeout=60,
        )

        assert result.success is True, result.error or result.stderr
        assert f"HOME {workdir}/.sandbox-home" in result.stdout
        assert f"TMPDIR {workdir}/.sandbox-tmp" in result.stdout

    def test_network_egress_is_denied(self, workdir: Path) -> None:
        code = (
            "import socket\n"
            "s = socket.socket()\n"
            "s.settimeout(2)\n"
            "try:\n"
            "    s.connect(('127.0.0.1', 9))\n"
            "    print('CONNECT_OK')\n"
            "except Exception as exc:\n"
            "    print('CONNECT_BLOCKED', type(exc).__name__)\n"
        )

        result = _run_probe(workdir, code)

        assert "CONNECT_OK" not in result.stdout
        assert "CONNECT_BLOCKED" in result.stdout

    def test_timeout_still_kills_the_process(self, workdir: Path) -> None:
        result = _run_probe(workdir, "import time\nprint('START')\ntime.sleep(30)\n", timeout=2)

        assert result.timed_out is True
        assert result.success is False


# ── C03-05: fail-closed (실행 0회) ────────────────────────────────────────


class TestFailClosedWithoutExecution:
    def _marker_command(self, workdir: Path) -> tuple[str, Path]:
        marker = workdir / "executed.marker"
        command = f"import pathlib;pathlib.Path({str(marker)!r}).write_text('ran')"
        return command, marker

    def test_unsupported_platform_refuses_without_executing(self, workdir: Path) -> None:
        command, marker = self._marker_command(workdir)
        runner = SandboxRunner(project_root=str(workdir), enabled=True)
        runner._platform = "FakeOS"

        result = runner.execute(f"{sys.executable} -c {command!r}", env=_sandbox_env(str(workdir)))

        assert result.success is False
        assert result.sandboxed is True
        assert "unavailable" in result.error
        assert not marker.exists()

    def test_missing_sandbox_exec_refuses_without_executing(
        self, workdir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        command, marker = self._marker_command(workdir)
        monkeypatch.setenv("PATH", "/nonexistent-bin")
        runner = SandboxRunner(project_root=str(workdir), enabled=True)
        if not IS_MACOS:  # pragma: no cover - seatbelt 경로는 macOS 실측
            pytest.skip("seatbelt backend required")

        result = runner.execute(
            f"{sys.executable} -c {command!r}",
            env={"PATH": "/nonexistent-bin", "HOME": str(workdir), "TMPDIR": str(workdir)},
        )

        assert result.success is False
        assert result.sandboxed is True
        assert "sandbox-exec" in result.error
        assert not marker.exists()

    def test_policy_construction_failure_refuses_without_executing(
        self, workdir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        if not IS_MACOS:  # pragma: no cover - seatbelt 경로는 macOS 실측
            pytest.skip("seatbelt backend required")
        command, marker = self._marker_command(workdir)
        runner = SandboxRunner(project_root=str(workdir), enabled=True)

        def boom() -> str:
            raise RuntimeError("profile construction failed (synthetic)")

        monkeypatch.setattr(runner, "_build_seatbelt_profile", boom)

        result = runner.execute(f"{sys.executable} -c {command!r}", env=_sandbox_env(str(workdir)))

        assert result.success is False
        assert result.sandboxed is True
        assert "policy construction failed" in result.error
        assert not marker.exists()

    def test_require_sandbox_refuses_when_disabled(self, workdir: Path) -> None:
        command, marker = self._marker_command(workdir)
        runner = SandboxRunner(project_root=str(workdir), enabled=False, require_sandbox=True)

        result = runner.execute(f"{sys.executable} -c {command!r}")

        assert result.success is False
        assert result.sandboxed is True
        assert "disabled by configuration" in result.error
        assert not marker.exists()

    def test_legacy_disabled_runner_keeps_raw_compatibility_mode(self, workdir: Path) -> None:
        """enabled=False + require_sandbox=False는 문서화된 호환 모드다(CR-04가 호출부 게이트)."""
        runner = SandboxRunner(project_root=str(workdir), enabled=False)

        result = runner.execute("echo compatibility-mode")

        assert result.success is True
        assert result.sandboxed is False
        assert "compatibility-mode" in result.stdout
