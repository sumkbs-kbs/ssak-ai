"""Ssak-Ai: 명령 실행 샌드박스 (P2-1).

====================================
에이전트가 실행하는 셸 명령을 OS 수준에서 격리합니다.
macOS의 sandbox-exec(seatbelt)와 Docker 컨테이너를 지원합니다.

보안 모델:
  - 파일 시스템: 프로젝트 디렉토리만 쓰기 허용, 나머지 읽기 전용
  - 읽기 경계(restrict_reads): 사용자 트리·공용/사용자 임시 디렉터리를 차단하고
    작업 디렉터리·인터프리터 런타임·호출자가 명시한 경로만 다시 허용한다.
  - 네트워크: config의 sandbox_network 설정 (none = 차단)
  - 프로세스: 자식 프로세스 생성 제한
  - 타임아웃: 무한 실행 방지

사용법:
    runner = SandboxRunner(project_root="/path/to/project", enabled=True)
    result = runner.execute("npm test", timeout=60)
"""

from __future__ import annotations

import logging
import math
import os
import platform
import shlex
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from antigravity_k.engine.limited_process_runner import LimitedProcessRunner

logger = logging.getLogger("antigravity_k.sandbox")


# CR-03: 읽기 경계에서 항상 차단하는 트리(다른 프로세스·다른 사용자 데이터).
# macOS의 per-user 임시 루트 ``/var/folders``(canonical ``/private/var/folders``)는
# pytest/`tempfile.mkdtemp()`가 실제로 쓰는 위치라 과거 경계에 빠져 있었다.
RESTRICTED_DENIED_ROOTS: Final[tuple[str, ...]] = (
    "/tmp",  # nosec B108 - 샌드박스 deny 규칙이며 파일 생성 경로가 아니다
    "/private/tmp",
    "/var/tmp",
    "/private/var/tmp",
    "/var/folders",
    "/private/var/folders",
)


def _realpath_forms(path: str) -> list[str]:
    """seatbelt가 canonical 경로로 매칭하므로 원문과 realpath를 함께 돌려준다."""
    forms: list[str] = []
    for candidate in (os.path.realpath(path), path):
        if candidate and candidate != "/" and candidate not in forms:
            forms.append(candidate)
    return forms


def restricted_denied_roots() -> list[str]:
    """restrict_reads에서 차단할 루트 목록(정렬·중복 제거)."""
    roots: list[str] = []
    user_tree = _user_tree_denied_root()
    if user_tree:
        roots.extend(_realpath_forms(user_tree))
    for denied in RESTRICTED_DENIED_ROOTS:
        roots.extend(_realpath_forms(denied))
    return list(dict.fromkeys(roots))


def ancestor_literal_read_allows(targets: Sequence[str], denied_roots: Sequence[str]) -> list[str]:
    """denied 트리 안에 놓인 대상의 조상 디렉터리를 literal로만 다시 연다.

    literal은 그 디렉터리 자체(entry 이름 해석·패키지 탐색)만 열고 하위 트리는
    열지 않는다. 이 규칙이 없으면 임시 디렉터리 아래 workspace의 부모 stat/list가
    EPERM이 되어 pytest 수집과 패키지 import가 실패한다(실측).
    """
    ancestors: list[str] = []
    for target in dict.fromkeys(targets):
        current = os.path.dirname(os.path.realpath(target))
        while current and current != "/":
            if any(current == denied or current.startswith(f"{denied}{os.sep}") for denied in denied_roots):
                ancestors.append(current)
            current = os.path.dirname(current)
    return sorted(dict.fromkeys(ancestors))


def _user_tree_denied_root() -> str | None:
    """Return the directory whose subtree should be unreadable in restricted mode.

    On a multi-user layout this is the parent of HOME (e.g. ``/Users``) so other
    accounts are covered as well; otherwise HOME itself.
    """
    home = os.path.expanduser("~")
    if not home or home == "/":
        return None
    parent = os.path.dirname(home.rstrip("/"))
    if parent and parent not in ("", "/"):
        return parent
    return home


@dataclass
class SandboxResult:
    """샌드박스 실행 결과."""

    success: bool
    stdout: str = ""
    stderr: str = ""
    return_code: int = 0
    timed_out: bool = False
    sandboxed: bool = False
    output_truncated: bool = False
    error: str = ""


def run_sandboxed_argv(
    args: list[str],
    *,
    cwd: str,
    timeout: float,
    env: Mapping[str, str] | None = None,
    max_output_bytes: int = 1_000_000,
    extra_read_paths: Sequence[str] = (),
) -> SandboxResult:
    """Execute model-generated code through the mandatory OS sandbox.

    This boundary deliberately has no raw-process fallback. A verifier must fail
    closed when seatbelt/Docker is unavailable instead of executing generated code
    with the parent process privileges.

    Read access is restricted to the working directory, the Python interpreter
    runtime that must execute the code and explicit ``extra_read_paths``; the
    user tree and shared/user temporary roots (``restricted_denied_roots()``)
    stay blocked. The parent's ``os.environ`` is never inherited: ``env=None``
    falls back to a minimal environment so caller secrets cannot leak into
    generated-code processes.
    """
    if not args:
        return SandboxResult(
            success=False,
            return_code=-1,
            sandboxed=True,
            error="Sandbox execution requires a non-empty argv.",
        )

    workspace = os.path.realpath(os.path.abspath(cwd))
    effective_timeout = max(1, math.ceil(timeout))
    read_paths = [workspace, *_python_runtime_read_paths(), *extra_read_paths]
    effective_env: dict[str, str] = dict(env) if env is not None else _minimal_child_env(workspace)
    runner = SandboxRunner(
        project_root=workspace,
        enabled=True,
        network="none",
        timeout=effective_timeout,
        max_output_bytes=max_output_bytes,
        restrict_reads=True,
        require_sandbox=True,
        read_allow_paths=read_paths,
    )
    return runner.execute(
        shlex.join(args),
        timeout=effective_timeout,
        env=effective_env,
        cwd=workspace,
    )


def _python_runtime_read_paths() -> list[str]:
    """Return interpreter locations a sandboxed Python needs to boot.

    conda/venv interpreters live under the user HOME, so only these exact
    prefixes are allow-listed instead of the whole HOME directory.
    Seatbelt matches canonical (realpath) locations, and venv interpreters are
    frequently symlinks into a manager store (uv/conda), so both the symlink
    location and its resolved target tree must be allow-listed.
    """
    exe_real = os.path.realpath(os.path.abspath(sys.executable))
    paths = {
        sys.prefix,
        sys.base_prefix,
        os.path.realpath(sys.prefix),
        os.path.realpath(sys.base_prefix),
        os.path.dirname(os.path.abspath(sys.executable)),
        os.path.dirname(exe_real),
        os.path.dirname(os.path.dirname(exe_real)),
    }
    return sorted(p for p in paths if p)


def _minimal_child_env(workspace: str) -> dict[str, str]:
    """Default child environment when the caller does not supply one.

    No os.environ inheritance: only what a bare Python process needs. The
    interpreter's own bin directory stays first on PATH so callers that spawn
    ``python3``/``pytest`` by name keep resolving to the project environment.
    """
    home = os.path.join(workspace, ".sandbox-home")
    tmpdir = os.path.join(workspace, ".sandbox-tmp")
    os.makedirs(home, exist_ok=True)
    os.makedirs(tmpdir, exist_ok=True)
    interpreter_bin = os.path.dirname(os.path.abspath(sys.executable))
    return {
        "PATH": f"{interpreter_bin}:/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": home,
        "TMPDIR": tmpdir,
        "PYTHONDONTWRITEBYTECODE": "1",
    }


class SandboxRunner:
    """OS 수준 샌드박스 명령 실행기.

    macOS에서는 sandbox-exec(seatbelt) 프로파일을 생성하여 명령을 격리합니다.
    Linux/Docker 환경에서는 Docker 컨테이너 내부 실행을 지원합니다.
    샌드박스가 비활성화되거나 사용 불가능하면 일반 subprocess로 폴백합니다.
    """

    def __init__(
        self,
        project_root: str = ".",
        enabled: bool = False,
        network: str = "none",
        timeout: int = 60,
        max_output_bytes: int = 1_000_000,
        max_memory_mb: int = 2_048,
        max_processes: int = 64,
        restrict_reads: bool = False,
        require_sandbox: bool = False,
        read_allow_paths: Sequence[str] = (),
        protected_write_deny_paths: Sequence[str] | None = None,
    ):
        """Initialize the SandboxRunner.

        Args:
            project_root: 쓰기 허용할 프로젝트 루트 디렉토리
            enabled: 샌드박스 활성화 여부
            network: 네트워크 모드 (none/proxy/all)
            timeout: 기본 타임아웃 (초)
            restrict_reads: True면 읽기를 명시적 허용 경로로 제한한다.
                False(기본)는 기존 호출자 호환을 위해 전체 읽기를 허용한다.
            require_sandbox: True면 ``enabled``와 무관하게 실제 샌드박스 실행만
                허용한다(설정으로 꺼져 있으면 raw 실행 대신 fail-closed).
            read_allow_paths: restrict_reads=True일 때 추가로 읽기를 허용할 경로.
            protected_write_deny_paths: project root 안에서도 쓰기를 거부할 절대경로.
                None이면 default_protected_roots(project_root)를 사용한다.
                빈 시퀀스는 명시적으로 deny 없음을 뜻한다.

        """
        self.project_root: str = os.path.realpath(os.path.abspath(project_root))
        self.enabled: bool = enabled
        self.network: str = network
        self.timeout: int = timeout
        self.max_output_bytes: int = max(1, max_output_bytes)
        self.max_memory_mb: int = max(128, max_memory_mb)
        self.max_processes: int = max(1, max_processes)
        self.restrict_reads: bool = restrict_reads
        self.require_sandbox: bool = require_sandbox
        self.read_allow_paths: tuple[str, ...] = tuple(
            os.path.realpath(os.path.abspath(p)) for p in read_allow_paths if p
        )
        if protected_write_deny_paths is None:
            try:
                from antigravity_k.engine.cognitive.protected_targets import (
                    sandbox_protected_unlink_denies,
                    sandbox_protected_write_denies,
                )

                self.protected_write_deny_paths: tuple[str, ...] = sandbox_protected_write_denies(self.project_root)
                self.protected_unlink_deny_paths: tuple[str, ...] = sandbox_protected_unlink_denies(self.project_root)
            except Exception as exc:
                # Prefer empty deny only for unsandboxed compatibility; require_sandbox
                # callers still fail closed when no Darwin/Docker boundary exists.
                logger.warning("protected write deny list unavailable: %s", exc)
                self.protected_write_deny_paths = ()
                self.protected_unlink_deny_paths = ()
        else:
            self.protected_write_deny_paths = tuple(
                os.path.realpath(os.path.abspath(p)) for p in protected_write_deny_paths if p
            )
            self.protected_unlink_deny_paths = ()
        self._platform: str = platform.system()

    def execute(
        self,
        command: str,
        timeout: int | None = None,
        env: Mapping[str, str] | None = None,
        cwd: str | None = None,
    ) -> SandboxResult:
        """명령을 샌드박스에서 실행합니다.

        Args:
            command: 실행할 셸 명령
            timeout: 타임아웃 (기본값 사용 시 None)
            env: 환경 변수

        Returns:
            SandboxResult
        """
        effective_timeout = timeout or self.timeout

        if not self.enabled:
            if self.require_sandbox:
                # CR-03: 설정으로 꺼진 상태에서 host raw 실행으로 대체하지 않는다.
                logger.warning("샌드박스가 설정으로 비활성 — raw 실행을 거부")
                return SandboxResult(
                    success=False,
                    return_code=-1,
                    sandboxed=True,
                    error="Sandbox is disabled by configuration; raw execution is refused.",
                )
            return self._execute_raw(command, effective_timeout, env, cwd)

        # 플랫폼별 샌드박스
        if self._platform == "Darwin":
            return self._execute_macos_sandbox(command, effective_timeout, env, cwd)
        elif self._is_docker_available():
            return self._execute_docker(command, effective_timeout, env, cwd)
        else:
            logger.warning(
                "샌드박스를 사용할 수 없는 환경(%s) — 실행을 차단",
                self._platform,
            )
            return SandboxResult(
                success=False,
                return_code=-1,
                sandboxed=True,
                error=f"Sandbox is unavailable on {self._platform}; raw execution is disabled.",
            )

    def _execute_macos_sandbox(
        self,
        command: str,
        timeout: int,
        env: Mapping[str, str] | None,
        cwd: str | None,
    ) -> SandboxResult:
        """macOS sandbox-exec(seatbelt)로 명령을 격리 실행."""
        profile_path = None
        try:
            profile = self._build_seatbelt_profile()
        except Exception as exc:
            # CR-03: 정책 생성 실패는 실행 전에 fail-closed(raw 폴백 없음).
            logger.warning("샌드박스 정책 생성 실패 — 실행을 차단: %s", exc)
            return SandboxResult(
                success=False,
                return_code=-1,
                sandboxed=True,
                error="Sandbox policy construction failed; raw execution is disabled.",
            )
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".sb", delete=False, encoding="utf-8") as f:
                _ = f.write(profile)
                profile_path = f.name

            # sandbox-exec -f <profile> sh -c "<command>"
            # sh -c로 래핑하여 셸 메타문자와 파이프를 올바르게 처리
            sandbox_cmd = [
                "sandbox-exec",
                "-f",
                profile_path,
                "sh",
                "-c",
                self._limited_command(command, timeout, process_limit=self._macos_process_limit()),
            ]

            return_code, stdout, stderr, output_truncated = self._run_limited_process(
                sandbox_cmd,
                shell=False,
                timeout=timeout,
                env=env,
                cwd=cwd,
            )

            return SandboxResult(
                success=return_code == 0,
                stdout=stdout,
                stderr=stderr,
                return_code=return_code,
                output_truncated=output_truncated,
                sandboxed=True,
            )
        except subprocess.TimeoutExpired:
            return SandboxResult(
                success=False,
                timed_out=True,
                error=f"샌드박스 명령 타임아웃 ({timeout}초)",
                sandboxed=True,
            )
        except FileNotFoundError:
            logger.warning("sandbox-exec를 찾을 수 없음 — 실행을 차단")
            return SandboxResult(
                success=False,
                return_code=-1,
                sandboxed=True,
                error="sandbox-exec is unavailable; raw execution is disabled.",
            )
        except (OSError, ValueError) as e:
            logger.warning("macOS 샌드박스 실행 실패: %s", e)
            return SandboxResult(
                success=False,
                return_code=-1,
                sandboxed=True,
                error=f"macOS sandbox execution failed: {e}",
            )
        finally:
            if profile_path and os.path.exists(profile_path):
                os.unlink(profile_path)

    def _protected_write_deny_section(self) -> str:
        """seatbelt: allow(root) 뒤에 오는 보호 경로 write/unlink deny."""
        lines: list[str] = []
        root = self.project_root

        def _in_project(real: str) -> bool:
            return real == root or real.startswith(root + os.sep)

        for path in self.protected_write_deny_paths:
            real = os.path.realpath(path)
            if not _in_project(real) or real == root:
                continue
            lines.append(f'(deny file-write* (subpath "{real}"))')
            lines.append(f'(deny file-write* (literal "{real}"))')
        for path in getattr(self, "protected_unlink_deny_paths", ()):
            real = os.path.realpath(path)
            if not _in_project(real) or real == root:
                continue
            lines.append(f'(deny file-write-unlink (subpath "{real}"))')
            lines.append(f'(deny file-write-unlink (literal "{real}"))')
        return "\n".join(lines)

    def build_seatbelt_profile(self) -> str:
        """Return the seatbelt profile used by long-lived sandbox clients."""
        return self._build_seatbelt_profile()

    def _build_seatbelt_profile(self) -> str:
        """macOS seatbelt 샌드박스 프로파일을 생성합니다.

        정책:
          - 프로젝트 디렉토리: 읽기/쓰기 허용
          - 시스템 경로(/usr, /bin, /lib): 읽기 전용
          - /tmp, /var/tmp: 읽기/쓰기 (빌드 산출물)
          - 네트워크: config에 따라 차단 또는 허용
          - fork/exec: 허용 (명령 실행 필요)
          - restrict_reads=True면 사용자 트리/공용·사용자 임시 루트를 deny하고
            작업 디렉터리·런타임·호출자 경로만 다시 허용해 다른 프로세스의
            비밀·임시 파일 접근을 차단한다(자식 프로세스에도 그대로 적용).
        """
        root = self.project_root
        allow_net = self.network != "none"

        # (deny default)가 네트워크도 포함해 전부 차단하므로, 허용 모드에서는
        # 명시적 allow가 없으면 실상 항상 차단된다
        network_policy = "(allow network*)\n;; network allowed" if allow_net else "(deny network*)\n;; network blocked"

        if self.restrict_reads:
            # CR-03 실측(macOS 26.6.2, arm64): (deny default) 뒤의 좁은 read allow
            # 목록은 CPython 부팅을 SIGABRT로 죽이고(인터프리터 로더), 임시 트리
            # 아래 workspace는 부모 stat EPERM으로 pytest 수집이 실패한다.
            # 따라서 경계를 "민감 트리 deny + workspace/런타임/호출자 경로만
            # 재허용 + 조상 metadata"로 구성한다. seatbelt는 같은 구체성에서
            # 나중에 오는 규칙을 우선 적용하므로 deny 뒤의 allow가 재허용이다.
            # 탐색·근거: .omo/evidence/commercial-reliability/CR-03/attempt-001/repro/.
            denied_roots = restricted_denied_roots()
            read_rules = ["(allow file-read*)"]
            for denied in denied_roots:
                read_rules.append(f'(deny file-read* (subpath "{denied}"))')
            allowed = list(dict.fromkeys([root, *self.read_allow_paths]))
            for ancestor in ancestor_literal_read_allows(allowed, denied_roots):
                read_rules.append(f'(allow file-read* (literal "{ancestor}"))')
            # 재허용: 작업 디렉토리/런타임/호출자 지정 경로가 차단 트리
            # 안에 있더라도 정확히 그 prefix(subpath)만 다시 연다.
            for p in allowed:
                read_rules.append(f'(allow file-read* (literal "{p}"))')
                read_rules.append(f'(allow file-read* (subpath "{p}"))')
            read_section = "\n".join(read_rules)
            # restrict 모드: 쓰기도 root만. /tmp, /var/folders 전체 쓰기 허용 제거.
            deny = self._protected_write_deny_section()
            write_section = f'(allow file-write* (subpath "{root}"))\n(allow file-write* (literal "/dev/null"))' + (
                f"\n{deny}" if deny else ""
            )
        else:
            read_section = "(allow file-read*)"
            cache_section = f'(allow file-write* (subpath "{os.path.expanduser("~/.cache")}"))'
            deny = self._protected_write_deny_section()
            # 보호 deny는 /tmp·/var/folders 등 넓은 allow보다 뒤에 둔다.
            # 임시 project root가 /var/folders 아래일 때 넓은 allow가
            # 앞선 deny를 무력화하지 않게 한다.
            write_section = f""";; 프로젝트 디렉토리 쓰기 허용
(allow file-write* (subpath "{root}"))
;; 임시 디렉토리 (빌드 산출물)
(allow file-write* (subpath "/tmp"))
(allow file-write* (subpath "/var/tmp"))
(allow file-write* (subpath "/private/tmp"))
(allow file-write* (subpath "/private/var/folders"))
(allow file-write* (literal "/dev/null"))
;; 사용자 캐시 (pip, npm 등)
{cache_section}
;; 보호 경로 deny (넓은 allow 이후 — 이후 규칙/구체 path 우선)
{deny}"""

        return f"""(version 1)
(deny default)
(allow process-fork)
(allow process-exec)
(allow signal (target self))
(allow sysctl-read)
{read_section}
{write_section}
{network_policy}
"""

    def _execute_docker(
        self,
        command: str,
        timeout: int,
        env: Mapping[str, str] | None,
        cwd: str | None,
    ) -> SandboxResult:
        """Docker 컨테이너 내부에서 명령을 실행합니다.

        읽기 경계는 bind mount가 담당한다: host의 project root만 ``/workspace``로
        올라가므로 그 밖의 host 경로(HOME·/tmp·/var/folders)는 컨테이너에서 보이지
        않는다. restrict_reads의 deny 목록을 컨테이너 내부에 추가로 적용하지 않는다.
        """
        network_flag = "--network=none" if self.network == "none" else ""
        working_dir = "/workspace"
        if cwd:
            try:
                canonical_cwd = os.path.realpath(os.path.abspath(cwd))
                relative_cwd = os.path.relpath(canonical_cwd, self.project_root)
            except ValueError:
                relative_cwd = ".."
            if relative_cwd == ".." or relative_cwd.startswith(f"..{os.sep}"):
                return SandboxResult(
                    success=False,
                    return_code=-1,
                    sandboxed=True,
                    error="Working directory must remain inside the project root.",
                )
            if relative_cwd != ".":
                working_dir = f"/workspace/{relative_cwd.replace(os.sep, '/')}"
        docker_cmd = [
            "docker",
            "run",
            "--rm",
            f"--memory={self.max_memory_mb}m",
            f"--memory-swap={self.max_memory_mb}m",
            f"--pids-limit={self.max_processes}",
            "-v",
            f"{self.project_root}:/workspace",
            "-w",
            working_dir,
        ]
        # Protected paths: remount read-only over the RW workspace bind (later mounts win).
        for host_path in self.protected_write_deny_paths:
            real = os.path.realpath(host_path)
            if not (real == self.project_root or real.startswith(self.project_root + os.sep)):
                continue
            rel = os.path.relpath(real, self.project_root).replace(os.sep, "/")
            docker_cmd.extend(["-v", f"{real}:/workspace/{rel}:ro"])
        if network_flag:
            docker_cmd.append(network_flag)
        docker_cmd.extend(["python:3.12-slim", "sh", "-c", self._limited_command(command, timeout)])

        try:
            return_code, stdout, stderr, output_truncated = self._run_limited_process(
                docker_cmd,
                shell=False,
                timeout=timeout,
                env=env,
                cwd=None,
            )
            return SandboxResult(
                success=return_code == 0,
                stdout=stdout,
                stderr=stderr,
                return_code=return_code,
                output_truncated=output_truncated,
                sandboxed=True,
            )
        except subprocess.TimeoutExpired:
            return SandboxResult(
                success=False,
                timed_out=True,
                error=f"Docker 명령 타임아웃 ({timeout}초)",
                sandboxed=True,
            )
        except FileNotFoundError:
            logger.warning("Docker를 찾을 수 없음 — 실행을 차단")
            return SandboxResult(
                success=False,
                return_code=-1,
                sandboxed=True,
                error="Docker is unavailable; raw execution is disabled.",
            )

    def _execute_raw(
        self,
        command: str,
        timeout: int,
        env: Mapping[str, str] | None,
        cwd: str | None,
    ) -> SandboxResult:
        """일반 subprocess 실행 (샌드박스 미적용 폴백)."""
        try:
            return_code, stdout, stderr, output_truncated = self._run_limited_process(
                self._limited_command(command, timeout),
                # Callers explicitly select the documented unsandboxed compatibility mode.
                shell=True,  # nosec B604
                timeout=timeout,
                env=env,
                cwd=cwd,
            )
            return SandboxResult(
                success=return_code == 0,
                stdout=stdout,
                stderr=stderr,
                return_code=return_code,
                output_truncated=output_truncated,
                sandboxed=False,
            )
        except subprocess.TimeoutExpired:
            return SandboxResult(
                success=False,
                timed_out=True,
                error=f"명령 타임아웃 ({timeout}초)",
            )
        except (OSError, ValueError) as e:
            return SandboxResult(success=False, error=str(e))

    def _macos_process_limit(self) -> int:
        try:
            result = subprocess.run(
                ["ps", "-u", str(os.getuid()), "-o", "pid="],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            current = len([line for line in result.stdout.splitlines() if line.strip()])
            return max(self.max_processes, current + self.max_processes)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return self.max_processes

    def _limited_command(self, command: str, timeout: int, process_limit: int | None = None) -> str:
        limit = process_limit or self.max_processes
        return (
            f"ulimit -t {max(1, timeout)} 2>/dev/null; "
            f"ulimit -u {limit} 2>/dev/null; "
            f"ulimit -v {self.max_memory_mb * 1024} 2>/dev/null; "
            f"exec sh -c {self._shell_quote(command)}"
        )

    @staticmethod
    def _shell_quote(command: str) -> str:
        return "'" + command.replace("'", "'\\''") + "'"

    def _bounded_streams(self, stdout: str | None, stderr: str | None) -> tuple[str, str, bool]:
        bounded_stdout, stdout_truncated = self._bound_output(stdout or "")
        bounded_stderr, stderr_truncated = self._bound_output(stderr or "")
        return bounded_stdout, bounded_stderr, stdout_truncated or stderr_truncated

    def _bound_output(self, output: str) -> tuple[str, bool]:
        raw = output.encode("utf-8", errors="replace")
        if len(raw) <= self.max_output_bytes:
            return output, False
        bounded = raw[: self.max_output_bytes].decode("utf-8", errors="ignore")
        return bounded, True

    def _run_limited_process(
        self,
        args: list[str] | str,
        *,
        shell: bool,
        timeout: int,
        env: Mapping[str, str] | None,
        cwd: str | None,
    ) -> tuple[int, str, str, bool]:
        result = LimitedProcessRunner(self.max_output_bytes).run(
            args,
            # SandboxRunner selects and enforces this execution mode.
            shell=shell,  # nosec B604
            timeout=timeout,
            env=env,
            cwd=cwd or self.project_root,
        )
        return result.return_code, result.stdout, result.stderr, result.output_truncated

    @staticmethod
    def _is_docker_available() -> bool:
        """Docker 사용 가능 여부."""
        try:
            result = subprocess.run(
                ["docker", "--version"],
                capture_output=True,
                timeout=5,
                check=False,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
