"""PermissionGate — 3-Tier 권한 모델.

==================================
Claw Code의 PermissionPolicy 아키텍처를 이식.

- Allow : 읽기 전용 도구 → 자동 실행
- Prompt: 파일 쓰기/수정 → 사용자 확인 후 실행
- Deny  : 시스템 변경/위험 명령 → 차단

사용:
    gate = PermissionGate(project_root="/path/to/project")
    decision = gate.check(tool, args)
    if decision == Permission.ALLOW: ...
"""

import hashlib
import json
import logging
import os
import re
from collections.abc import Mapping, Sequence

from antigravity_k.engine.cognitive.protected_targets import (
    ActorKind,
    HumanApproval,
    ProtectedWriteGuard,
    ProtectedWriteRequest,
    WriteChannel,
    WriteOperation,
)

from .tool_contracts import Permission, PermissionDecision, ToolArgument, ToolInvocation, ToolSpec
from .tool_path import (
    ToolPathError,
    assert_shell_command_paths_in_root,
    effective_project_root,
    extract_apply_patch_paths,
    resolve_tool_path,
)

logger = logging.getLogger(__name__)

#: shell 도구 이름 — 동일한 보호 경계를 지나야 한다.
SHELL_TOOL_NAMES = ("run_bash_command", "bash", "run_persistent_command", "shell", "terminal")
#: 이름에 이 조각이 있으면 쓰기 도구로 취급한다.
WRITE_TOOL_HINTS = (
    "write",
    "edit",
    "replace",
    "patch",
    "create",
    "delete",
    "remove",
    "move",
    "rename",
    "append",
    "mkdir",
    "copy",
    "restore",
    "snapshot",
)
PATH_ARG_KEYS = ("file_path", "path", "target", "dir_path", "target_path", "src", "dest")


def protection_action_digest(tool_name: str, args: Mapping[str, ToolArgument]) -> str:
    encoded = json.dumps(
        {"tool": tool_name, "arguments": dict(args)},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


class PermissionGate:
    """도구 실행 전 권한 검증 게이트.

    Claw Code의 PermissionPolicy struct 패턴:
    - per-tool 오버라이드
    - 경로 기반 샌드박싱
    - 위험 명령 블랙리스트
    """

    # ─── 위험 명령 블랙리스트 ───
    DANGEROUS_COMMANDS: list[str] = [
        r"rm\s+-rf\s+/",  # 루트 삭제
        r"del\s+/[sS]",  # Windows 전체 삭제
        r"format\s+[A-Za-z]:",  # 디스크 포맷
        r"mkfs\.",  # 파일시스템 포맷
        r"dd\s+if=.*of=/dev/",  # 디스크 덮어쓰기
        r"chmod\s+-R\s+777\s+/",  # 전체 권한 오픈
        r"shutdown",  # 시스템 종료
        r"reboot",  # 시스템 재시작
        r"curl.*\|\s*(ba)?sh",  # 원격 스크립트 실행
        r"wget.*\|\s*(ba)?sh",  # 원격 스크립트 실행
    ]

    # ─── 보호 경로 (절대 쓰기 불가) ───
    PROTECTED_PATHS: list[str] = [
        "/etc",
        "/usr",
        "/bin",
        "/sbin",
        "/boot",
        "/sys",
        "/proc",
        "C:\\Windows",
        "C:\\Program Files",
        "C:\\Program Files (x86)",
    ]

    def __init__(
        self,
        project_root: str | None = None,
        mode: str = "auto-pilot",  # strict | balanced | permissive | auto-pilot
        auto_allow_safe: bool = True,
    ) -> None:
        """Initialize the PermissionGate.

        Args:
            project_root (str | None): str | None project root.
            mode (str): str mode.
            auto_allow_safe (bool): bool auto allow safe.

        """
        self.project_root: str = os.path.abspath(project_root) if project_root else os.getcwd()
        self.mode: str = mode
        self.auto_allow_safe: bool = auto_allow_safe

        # 도구별 명시적 오버라이드
        self._overrides: dict[str, Permission] = {}

        # 승인 캐시 (세션 내 반복 승인 방지)
        self._approval_cache: set[str] = set()

        # cognitive protected target(P03) — 헌법/authority/premise/이력 쓰기 allowlist
        self._protection_guard: ProtectedWriteGuard | None = None
        self._protection_guard_root: str | None = None
        self._protection_approvals: tuple[HumanApproval, ...] = ()
        self._protection_approval_root: str | None = None

        logger.info("PermissionGate initialized: mode=%s, project_root=%s", mode, self.project_root)

    def set_project_root(self, new_root: str) -> None:
        """런타임 중에 프로젝트 루트를 변경하고 권한 모드를 자동화 모드로 설정합니다."""
        self.project_root = os.path.abspath(new_root)
        self.mode = "auto-pilot"  # 사용자의 개입 최소화를 위해 내부 파일 작업 자동 승인
        self._protection_guard = None  # root가 바뀌면 protected root를 다시 계산한다
        logger.info(
            "PermissionGate project_root updated to: %s (mode set to auto-pilot)",
            self.project_root,
        )

    def set_protection_guard(self, guard: ProtectedWriteGuard | None) -> None:
        """protected target 판정기를 주입한다(None이면 project_root 기준 기본값으로 재생성)."""

        self._protection_guard = guard
        self._protection_guard_root = guard.project_root if guard is not None else None

    def set_protection_approvals(self, approvals: Sequence[HumanApproval]) -> None:
        """사람 승인 record를 등록한다. 승인이 없으면 protected 쓰기는 거부된다."""

        self._protection_approvals = tuple(approvals)
        self._protection_approval_root = os.path.realpath(self.effective_root())

    @property
    def protection_guard(self) -> ProtectedWriteGuard:
        """request-scoped root(effective_root)를 반영해 protected root를 계산한다."""

        root = os.path.realpath(self.effective_root())
        if self._protection_guard is None or self._protection_guard_root != root:
            self._protection_guard = ProtectedWriteGuard(root)
            self._protection_guard_root = root
        return self._protection_guard

    def _check_cognitive_protection(self, tool_name: str, args: Mapping[str, ToolArgument]) -> str | None:
        """헌법·authority·premise·이력 쓰기 시도를 거부한다. 거부 사유가 없으면 None."""

        guard = self.protection_guard
        approvals = self._protection_approvals if self._protection_approval_root == guard.project_root else ()
        try:
            digest = protection_action_digest(tool_name, args)
        except (TypeError, ValueError):
            return "Tool arguments cannot be bound to a canonical approval digest."
        if tool_name in SHELL_TOOL_NAMES:
            raw_command = args.get("command")
            command = raw_command if isinstance(raw_command, str) else ""
            if not command:
                return None
            decision = guard.evaluate_shell_command(
                command,
                actor_kind=ActorKind.BODY,
                actor_id="body:permission-gate",
                action_digest=digest,
                approvals=approvals,
            )
            if not decision.allowed:
                return f"Protected cognitive target ({decision.code.value}): {decision.detail}"
            return None

        if not any(hint in tool_name.lower() for hint in WRITE_TOOL_HINTS):
            return None

        targets = self._protection_targets(tool_name, args)
        if not targets:
            return None
        decision = guard.evaluate(
            ProtectedWriteRequest(
                channel=WriteChannel.FILE_TOOL,
                actor_kind=ActorKind.BODY,
                actor_id="body:permission-gate",
                targets=targets,
                operation=WriteOperation.UPDATE,
                action_digest=digest,
                project_root=self.project_root,
                approvals=approvals,
            )
        )
        if not decision.allowed:
            return f"Protected cognitive target ({decision.code.value}): {decision.detail}"
        return None

    @staticmethod
    def _protection_targets(tool_name: str, args: Mapping[str, ToolArgument]) -> tuple[str, ...]:
        targets: list[str] = []
        for key in PATH_ARG_KEYS:
            value = args.get(key)
            if isinstance(value, str) and value:
                targets.append(value)
            elif isinstance(value, (list, tuple)):
                targets.extend(item for item in value if isinstance(item, str) and item)
        raw_patch = args.get("patch")
        if isinstance(raw_patch, str) and raw_patch:
            targets.extend(extract_apply_patch_paths(raw_patch))
        return tuple(dict.fromkeys(targets))

    def set_override(self, tool_name: str, permission: Permission) -> None:
        """특정 도구에 대한 권한을 명시적으로 설정합니다."""
        self._overrides[tool_name] = permission
        logger.info("Permission override set: %s → %s", tool_name, permission.value)

    def check(self, tool_name: str, args: Mapping[str, object], risk_level: str = "safe") -> Permission:
        """도구 실행 권한을 검증합니다.

        Returns:
            Permission.ALLOW  — 즉시 실행
            Permission.PROMPT — 사용자 확인 필요
            Permission.DENY   — 차단

        """
        invocation = ToolInvocation(
            spec=ToolSpec(name=tool_name, risk_level=risk_level, category="legacy"),
            arguments=args,
        )
        return self.decide(invocation).permission

    def decide(self, invocation: ToolInvocation[ToolArgument]) -> PermissionDecision:
        tool_name = invocation.spec.name
        args: Mapping[str, ToolArgument] = invocation.arguments
        risk_level = invocation.spec.risk_level

        # Cognitive protection first: tool overrides must not open constitution/authority writes.
        protection_reason = self._check_cognitive_protection(tool_name, args)
        if protection_reason is not None:
            logger.warning("DENIED protected cognitive target write: %s", protection_reason)
            return PermissionDecision(
                spec=invocation.spec,
                permission=Permission.DENY,
                source="cognitive_protection",
                reason=protection_reason,
                inspected_path=None,
                executed_path=None,
            )

        if tool_name in self._overrides:
            return PermissionDecision(
                spec=invocation.spec,
                permission=self._overrides[tool_name],
                source="override",
                reason="A tool-specific permission override is configured.",
            )

        # 2. 위험 명령 차단 (Bash/Shell 도구) + absolute/escape path policy (WS-02 F2)
        # run_persistent_command도 동일 shell 경로 검사 대상이다 (FR-02/RP-02).
        if tool_name in ("run_bash_command", "bash", "run_persistent_command"):
            raw_command = args.get("command")
            command = raw_command if isinstance(raw_command, str) else ""
            if self._is_dangerous_command(command):
                logger.warning("DENIED dangerous command: %s", command[:100])
                return PermissionDecision(
                    spec=invocation.spec,
                    permission=Permission.DENY,
                    source="permission_gate",
                    reason="The command matches a blocked dangerous-command policy.",
                )
            try:
                assert_shell_command_paths_in_root(command, self.effective_root())
            except ToolPathError as exc:
                logger.warning("DENIED shell path escape: %s (%s)", command[:120], exc)
                return PermissionDecision(
                    spec=invocation.spec,
                    permission=Permission.DENY,
                    source="permission_gate",
                    reason="The shell command references a path outside the permitted project boundary.",
                    inspected_path=None,
                    executed_path=None,
                )

        # 2b. apply_patch — paths live inside patch text, not PATH_ARG keys (WS-02 F1)
        if tool_name == "apply_patch":
            raw_patch = args.get("patch")
            patch_text = raw_patch if isinstance(raw_patch, str) else ""
            for patch_path in extract_apply_patch_paths(patch_text):
                path_decision: Permission | None = self._check_path(patch_path, tool_name)
                if path_decision == Permission.DENY:
                    return PermissionDecision(
                        spec=invocation.spec,
                        permission=Permission.DENY,
                        source="permission_gate",
                        reason="The requested path is outside the permitted project boundary or protected.",
                        inspected_path=None,
                        executed_path=None,
                    )

        # 3. 경로 기반 샌드박싱 (파일 도구) — inspected path == executed path (WS-02)
        path_decision = None
        resolved_path: str | None = None
        raw_file_path = (
            args.get("file_path") or args.get("path") or args.get("target") or args.get("cwd") or args.get("dir_path")
        )
        file_path = raw_file_path if isinstance(raw_file_path, str) else None
        if file_path is not None:
            path_decision = self._check_path(file_path, tool_name)
            if path_decision == Permission.DENY:
                return PermissionDecision(
                    spec=invocation.spec,
                    permission=Permission.DENY,
                    source="permission_gate",
                    reason="The requested path is outside the permitted project boundary or protected.",
                    inspected_path=None,
                    executed_path=None,
                )
            if tool_name != "set_workspace":
                try:
                    resolved_path = self.resolve_for_tool(file_path)
                except ToolPathError:
                    resolved_path = None

        # 4. risk_level 기반 결정
        risk_map = {
            "safe": Permission.ALLOW,
            "low": (Permission.ALLOW if self.mode in ("permissive", "auto-pilot") else Permission.PROMPT),
            "medium": (Permission.ALLOW if self.mode == "auto-pilot" else Permission.PROMPT),
            "high": (Permission.ALLOW if self.mode == "auto-pilot" else Permission.PROMPT),
            "critical": (
                Permission.DENY
                if self.mode in ("strict", "balanced")
                else (Permission.ALLOW if self.mode == "auto-pilot" else Permission.PROMPT)
            ),
        }

        decision = risk_map.get(risk_level, Permission.PROMPT)

        # 경로 검사에서 PROMPT가 요구되었다면, risk_map이 ALLOW더라도 PROMPT로 격상
        if path_decision == Permission.PROMPT and decision == Permission.ALLOW:
            decision = Permission.PROMPT

        # 5. 승인 캐시 확인 (같은 도구+패턴 반복 시 자동 승인)
        cache_key = f"{tool_name}:{risk_level}"
        if decision == Permission.PROMPT and cache_key in self._approval_cache:
            logger.debug("Auto-approved from cache: %s", cache_key)
            return PermissionDecision(
                spec=invocation.spec,
                permission=Permission.ALLOW,
                source="approval_cache",
                reason="A matching approved tool action is cached for this session.",
                inspected_path=resolved_path,
                executed_path=resolved_path,
            )

        return PermissionDecision(
            spec=invocation.spec,
            permission=decision,
            source="permission_gate",
            reason="The tool risk and path policy determine this permission.",
            inspected_path=resolved_path,
            executed_path=resolved_path,
        )

    def record_approval(self, tool_name: str, risk_level: str = "safe") -> None:
        """사용자가 승인한 도구를 캐시에 기록합니다."""
        cache_key = f"{tool_name}:{risk_level}"
        self._approval_cache.add(cache_key)

    def _is_dangerous_command(self, command: str) -> bool:
        """위험 명령 블랙리스트 검사."""
        for pattern in self.DANGEROUS_COMMANDS:
            if re.search(pattern, command, re.IGNORECASE):
                return True
        return False

    def effective_root(self) -> str:
        """Request-scoped canonical root when bound; else this gate's project_root."""
        return effective_project_root(self.project_root)

    def resolve_for_tool(self, file_path: str) -> str:
        """Resolve a tool path under the effective project root (WS-02)."""
        return resolve_tool_path(file_path, self.effective_root())

    def _check_path(self, file_path: str, tool_name: str) -> Permission:
        """경로 기반 권한 검사 — 검사 경로는 실제 open 경로와 동일해야 한다 (WS-02)."""
        raw_path = str(file_path)
        raw_norm = os.path.normcase(raw_path).replace("/", "\\")
        for protected in self.PROTECTED_PATHS:
            protected_norm = os.path.normcase(protected).replace("/", "\\")
            if raw_norm.lower().startswith(protected_norm.lower()):
                logger.warning("DENIED access to protected path: %s", raw_path)
                return Permission.DENY

        # Workspace switch is not a project-scoped file tool; still block protected roots.
        if tool_name == "set_workspace":
            try:
                abs_path = os.path.realpath(os.path.abspath(file_path))
            except OSError:
                return Permission.DENY
            for protected in self.PROTECTED_PATHS:
                protected_path = os.path.realpath(os.path.abspath(protected))
                try:
                    inside_protected = os.path.commonpath([abs_path, protected_path]) == protected_path
                except ValueError:
                    inside_protected = False
                if inside_protected:
                    logger.warning("DENIED access to protected path: %s", abs_path)
                    return Permission.DENY
            return Permission.ALLOW

        # All other file/search tools: must resolve under canonical project root.
        try:
            abs_path = self.resolve_for_tool(file_path)
        except ToolPathError as exc:
            logger.warning("DENIED escaping tool path: %s (%s)", raw_path, exc)
            return Permission.DENY

        for protected in self.PROTECTED_PATHS:
            protected_path = os.path.realpath(os.path.abspath(protected))
            try:
                inside_protected = os.path.commonpath([abs_path, protected_path]) == protected_path
            except ValueError:
                inside_protected = False
            if inside_protected:
                logger.warning("DENIED access to protected path: %s", abs_path)
                return Permission.DENY

        # Inside project — mode decides write prompting; reads are allow.
        if tool_name in ("read_file", "grep_search", "glob_search", "list_directory"):
            return Permission.ALLOW

        if self.mode in ("permissive", "auto-pilot"):
            return Permission.ALLOW
        return Permission.PROMPT

    def reset_cache(self) -> None:
        """승인 캐시를 초기화합니다."""
        self._approval_cache.clear()

    def to_dict(self) -> dict[str, object]:
        """상태를 직렬화합니다."""
        return {
            "project_root": self.project_root,
            "mode": self.mode,
            "overrides": {k: v.value for k, v in self._overrides.items()},
            "cached_approvals": list(self._approval_cache),
        }
