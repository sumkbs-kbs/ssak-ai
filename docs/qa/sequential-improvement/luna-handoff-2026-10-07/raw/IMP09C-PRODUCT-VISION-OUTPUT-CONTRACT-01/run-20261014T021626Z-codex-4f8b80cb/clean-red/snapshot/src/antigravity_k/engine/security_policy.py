"""SecurityPolicyEngine — 선언적 보안 정책 + 도구 권한 관리.

=========================================================
IronClaw permissions.rs 패턴 이식:
- PermissionState 3분류: AlwaysAllow / AskEachTime / Disabled
- Seeded Defaults: 도구별 기본 권한 매핑
- Tool Name Canonicalization: 하이픈 ↔ 언더스코어 양방향 해석
- Fail-Closed: 정책 로드 실패 시 안전 우선 (모든 도구 AskEachTime)
"""

import logging
from collections.abc import Mapping
from enum import Enum
from pathlib import Path
from typing import cast

import yaml

logger = logging.getLogger("antigravity_k.engine.security_policy")


# ── IronClaw PermissionState 3분류 ──


class PermissionState(str, Enum):
    """도구 실행 권한 상태 (IronClaw permissions.rs 이식)."""

    ALWAYS_ALLOW = "always_allow"  # 자동 실행 (승인 불필요)
    ASK_EACH_TIME = "ask_each_time"  # 매번 사용자 승인 필요
    DISABLED = "disabled"  # 실행 차단


# ── Seeded Defaults (IronClaw seeded_default_permission 이식) ──

_SEEDED_DEFAULTS: dict[str, PermissionState] = {
    # 읽기 전용 / 정보 조회 → 자동 허용
    "echo": PermissionState.ALWAYS_ALLOW,
    "time": PermissionState.ALWAYS_ALLOW,
    "json": PermissionState.ALWAYS_ALLOW,
    "read_file": PermissionState.ALWAYS_ALLOW,
    "grep_search": PermissionState.ALWAYS_ALLOW,
    "glob_search": PermissionState.ALWAYS_ALLOW,
    "list_directory": PermissionState.ALWAYS_ALLOW,
    "web_search": PermissionState.ALWAYS_ALLOW,
    "search_knowledge": PermissionState.ALWAYS_ALLOW,
    "memory_search": PermissionState.ALWAYS_ALLOW,
    "memory_read": PermissionState.ALWAYS_ALLOW,
    "memory_tree": PermissionState.ALWAYS_ALLOW,
    "tool_list": PermissionState.ALWAYS_ALLOW,
    "tool_info": PermissionState.ALWAYS_ALLOW,
    "git_status": PermissionState.ALWAYS_ALLOW,
    "git_log": PermissionState.ALWAYS_ALLOW,
    "git_diff": PermissionState.ALWAYS_ALLOW,
    "hex_dump": PermissionState.ALWAYS_ALLOW,
    "impact_analyzer": PermissionState.ALWAYS_ALLOW,
    "fetch_dom": PermissionState.ALWAYS_ALLOW,
    # 변경 가능 → 매번 승인
    "run_bash_command": PermissionState.ASK_EACH_TIME,
    "run_persistent_command": PermissionState.ASK_EACH_TIME,
    "write_file": PermissionState.ASK_EACH_TIME,
    "edit_file": PermissionState.ASK_EACH_TIME,
    "multi_replace_file_content": PermissionState.ASK_EACH_TIME,
    "replace_file_content": PermissionState.ASK_EACH_TIME,
    "write_artifact": PermissionState.ASK_EACH_TIME,
    "git_commit": PermissionState.ASK_EACH_TIME,
    "run_tests": PermissionState.ASK_EACH_TIME,
    "auto_lint": PermissionState.ASK_EACH_TIME,
    "create_pr": PermissionState.ASK_EACH_TIME,
    "memory_write": PermissionState.ASK_EACH_TIME,
    "store_knowledge": PermissionState.ASK_EACH_TIME,
    "agent_spawn": PermissionState.ASK_EACH_TIME,
    "cowork_delegate": PermissionState.ASK_EACH_TIME,
    "computer_use": PermissionState.ASK_EACH_TIME,
    "web_scrape": PermissionState.ASK_EACH_TIME,
    "send_command_input": PermissionState.ASK_EACH_TIME,
    "interactive_pty": PermissionState.ASK_EACH_TIME,
    "run_docker_bash": PermissionState.ASK_EACH_TIME,
    "db_migration": PermissionState.ASK_EACH_TIME,
}


def seeded_default_permission(tool_name: str) -> PermissionState | None:
    """도구의 기본 권한을 반환합니다 (IronClaw seeded_default_permission 이식)."""
    canonical = tool_name.replace("-", "_")
    return _SEEDED_DEFAULTS.get(canonical)


def effective_permission(
    tool_name: str,
    overrides: dict[str, PermissionState] | None = None,
) -> PermissionState:
    """실효 권한을 결정합니다 (IronClaw effective_permission 이식).

    조회 순서:
    1. 사용자 오버라이드 (persisted)
    2. Seeded 기본값 (well-known tools)
    3. AskEachTime (안전 폴백 — unknown tools)
    """
    overrides = overrides or {}

    # 도구명 정규화: 하이픈 ↔ 언더스코어 양방향 해석
    canonical = tool_name.replace("-", "_")
    hyphenated = canonical.replace("_", "-")

    # 1. 사용자 오버라이드
    for variant in (tool_name, canonical, hyphenated):
        if variant in overrides:
            return overrides[variant]

    # 2. Seeded 기본값
    seeded = seeded_default_permission(canonical)
    if seeded is not None:
        return seeded

    # 3. 안전 폴백
    return PermissionState.ASK_EACH_TIME


# ── 메인 보안 정책 엔진 ──


class SecurityPolicyEngine:
    """선언적 보안 정책 엔진.

    IronClaw permissions.rs + AdminToolPolicy 패턴 이식:
    - YAML 정책 파일 기반 선언적 보안
    - PermissionState 3분류 도구 권한
    - Fail-Closed: 정책 로드 실패 시 안전 우선
    """

    def __init__(self, policy_file: str = "policy.yaml"):
        """Initialize the SecurityPolicyEngine.

        Args:
            policy_file (str): str policy file.

        """
        # W-5: 상대 경로 시 프로젝트 루트 기준 절대 경로로 변환
        _policy_path = Path(policy_file)
        if not _policy_path.is_absolute():
            _policy_path = Path(__file__).resolve().parent.parent.parent.parent / policy_file
        self.policy_file: Path = _policy_path
        self.policy: dict[str, object] = {
            "network": {"allowed_domains": [], "blocked_domains": []},
            "filesystem": {"allowed_paths": [], "read_only_paths": []},
            "process": {"blocked_commands": []},
        }
        self._load_failed: bool = False  # Fail-Closed 플래그
        self._tool_permission_overrides: dict[str, PermissionState] = {}
        self.load_policy()

    def load_policy(self):
        """정책 파일을 로드합니다.

        IronClaw Fail-Closed 패턴: 로드 실패 시 _load_failed 플래그를 설정하여
        후속 검사에서 안전 우선 동작을 보장합니다.
        """
        if self.policy_file.exists():
            try:
                with open(self.policy_file) as f:
                    loaded = cast(object, yaml.safe_load(f))
                    if isinstance(loaded, Mapping):
                        loaded_mapping = cast(Mapping[object, object], loaded)
                        self.policy.update({str(key): value for key, value in loaded_mapping.items()})
                self._load_failed = False
            except Exception:
                logger.exception("보안 정책 로드 실패 (fail-closed 적용)")
                self._load_failed = True

    def is_command_allowed(self, command: str) -> bool:
        """명령어 실행 허용 여부를 확인합니다."""
        # Fail-Closed: 정책 로드 실패 시 모든 명령어 차단
        if self._load_failed:
            return False

        process = self._section("process")
        for b in self._string_list(process.get("blocked_commands")):
            if b in command:
                return False
        return True

    def is_domain_allowed(self, domain: str) -> bool:
        """도메인 접근 허용 여부를 확인합니다."""
        # Fail-Closed: 정책 로드 실패 시 모든 도메인 차단
        if self._load_failed:
            return False

        network = self._section("network")
        allowed = self._string_list(network.get("allowed_domains"))
        blocked = self._string_list(network.get("blocked_domains"))

        for b in blocked:
            if b in domain:
                return False

        # If allowed list is empty, default is allow-all. If not empty, it's default-deny.
        if allowed:
            for a in allowed:
                if a in domain:
                    return True
            return False

        return True

    def _section(self, name: str) -> dict[str, object]:
        value = self.policy.get(name)
        if not isinstance(value, Mapping):
            return {}
        value_mapping = cast(Mapping[object, object], value)
        return {str(key): item for key, item in value_mapping.items()}

    @staticmethod
    def _string_list(value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        values = cast(list[object], value)
        return [item for item in values if isinstance(item, str)]

    def get_tool_permission(self, tool_name: str) -> PermissionState:
        """도구의 실효 권한을 반환합니다 (IronClaw effective_permission 이식)."""
        return effective_permission(tool_name, self._tool_permission_overrides)

    def set_tool_permission(self, tool_name: str, state: PermissionState) -> None:
        """도구 권한을 오버라이드합니다."""
        canonical = tool_name.replace("-", "_")
        self._tool_permission_overrides[canonical] = state
        logger.info("도구 권한 변경: %s → %s", canonical, state.value)

    def is_tool_allowed(self, tool_name: str) -> bool:
        """도구가 사용 가능한지 확인합니다 (Disabled가 아닌지)."""
        perm = self.get_tool_permission(tool_name)
        return perm != PermissionState.DISABLED

    def is_tool_auto_allowed(self, tool_name: str) -> bool:
        """도구가 자동 실행 가능한지 확인합니다."""
        perm = self.get_tool_permission(tool_name)
        return perm == PermissionState.ALWAYS_ALLOW

    @property
    def is_fail_closed(self) -> bool:
        """정책 로드 실패로 Fail-Closed 상태인지 확인합니다."""
        return self._load_failed


policy_engine = SecurityPolicyEngine()


def get_policy_engine() -> SecurityPolicyEngine:
    """Retrieve policy engine.

    Returns:
        SecurityPolicyEngine: The securitypolicyengine result.

    """
    return policy_engine
