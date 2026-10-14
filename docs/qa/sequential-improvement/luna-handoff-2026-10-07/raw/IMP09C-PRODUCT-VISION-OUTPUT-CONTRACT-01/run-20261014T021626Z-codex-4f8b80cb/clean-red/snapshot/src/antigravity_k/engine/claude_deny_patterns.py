"""ClaudeDenyPatterns — 선언적 위험 명령 deny 패턴 시스템.

========================================================
Sidabari의 claude_safety.rs 패턴을 Python으로 이식.

.claude/settings.local.json에 위험 명령 deny 패턴을 자동 설치합니다.
기존 사용자 규칙을 보존하면서 새 패턴을 병합하고,
self-cleanup 마커로 이전 설치 패턴을 추적/갱신합니다.

보안 원칙 (Sidabari CLAUDE.md §1.2):
  - 자격증명/키 파일 내용은 로그에 찍지 않음
  - 사용자 입력을 셸 명령으로 직접 연결하지 않음
  - 자동 재시도 금지 — 실패 시 멈추고 사용자가 결정
"""

from __future__ import annotations

import json
import logging
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import ClassVar, cast

logger = logging.getLogger("antigravity_k.engine.claude_deny_patterns")

RULES_MARKER_KEY = "_antigravity_managed"

# 레거시 마커 키 (Sidabari 호환)
LEGACY_MARKER_KEYS = {"_sidabari_managed"}


def _as_object_dict(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    items = cast(Mapping[object, object], value).items()
    return {str(key): item for key, item in items}


def deny_patterns() -> list[str]:
    """위험 명령 deny 패턴 목록을 반환합니다.

    Sidabari claude_safety.rs의 deny_patterns() 전체 이식 +
    Ssak-Ai 로컬 환경에 맞는 추가 패턴.
    """
    return [
        # ── 파일 삭제/이동/덮어쓰기 (로컬·원격 양쪽) ──
        "Bash(rm:*)",
        "Bash(*rm -rf*)",
        "Bash(*rm -fr*)",
        "Bash(sudo rm:*)",
        "Bash(*sudo rm*)",
        "Bash(mv:*)",
        "Bash(*sudo mv*)",
        "Bash(*sudo cp*)",
        "Bash(*sudo dd*)",
        "Bash(dd:*)",
        "Bash(*mkfs*)",
        "Bash(*shred*)",
        # ── 권한 변경 ──
        "Bash(chmod:*)",
        "Bash(chown:*)",
        "Bash(*sudo chmod*)",
        "Bash(*sudo chown*)",
        # ── 서비스 변경 ──
        "Bash(*systemctl stop*)",
        "Bash(*systemctl start*)",
        "Bash(*systemctl restart*)",
        "Bash(*systemctl reload*)",
        "Bash(*systemctl disable*)",
        "Bash(*systemctl enable*)",
        "Bash(*systemctl mask*)",
        "Bash(*systemctl unmask*)",
        "Bash(*service * stop*)",
        "Bash(*service * restart*)",
        "Bash(*service * start*)",
        "Bash(*kill -9*)",
        "Bash(*killall*)",
        "Bash(*pkill*)",
        # ── 패키지 변경 ──
        "Bash(*apt install*)",
        "Bash(*apt remove*)",
        "Bash(*apt-get install*)",
        "Bash(*apt-get remove*)",
        "Bash(*yum install*)",
        "Bash(*yum remove*)",
        "Bash(*dnf install*)",
        "Bash(*dnf remove*)",
        "Bash(*pip install*)",
        "Bash(*pip3 install*)",
        "Bash(*npm install*)",
        "Bash(*brew install*)",
        "Bash(*brew remove*)",
        "Bash(*brew uninstall*)",
        # ── 파일 업로드/원격 쓰기 ──
        "Bash(scp:*)",
        "Bash(*scp *)",
        "Bash(sftp:*)",
        "Bash(*sftp *)",
        "Bash(rsync:*)",
        "Bash(*rsync *)",
        # ── 리다이렉션을 통한 시스템 파일 쓰기 ──
        "Bash(*> /etc/*)",
        "Bash(*>> /etc/*)",
        "Bash(*> /var/*)",
        "Bash(*>> /var/*)",
        "Bash(*> /usr/*)",
        "Bash(*>> /usr/*)",
        "Bash(*> /home/*)",
        "Bash(*>> /home/*)",
        "Bash(*> /root/*)",
        "Bash(*>> /root/*)",
        "Bash(*> /System/*)",
        "Bash(*>> /System/*)",
        # ── sudoers 변경 ──
        "Bash(*visudo*)",
        # ── 네트워크 변경 ──
        "Bash(*iptables*)",
        "Bash(*ufw *)",
        "Bash(*firewall-cmd*)",
        # ── 디렉토리 트리 삭제 ──
        "Bash(*rm -r*)",
        # ── 원격 코드 실행 패턴 ──
        "Bash(*curl* | bash*)",
        "Bash(*curl* | sh*)",
        "Bash(*wget* | bash*)",
        "Bash(*wget* | sh*)",
        # ── base64 디코딩 후 실행 ──
        "Bash(*base64 -d* | bash*)",
        "Bash(*base64 -d* | sh*)",
        "Bash(*base64 --decode* | bash*)",
        # ── .claude/settings 자체 변조 차단 ──
        "Edit(**/.claude/settings*)",
        "Write(**/.claude/settings*)",
        # ── Git 위험 명령 ──
        "Bash(*git push --force*)",
        "Bash(*git push -f*)",
        "Bash(*git reset --hard*)",
        "Bash(*git clean -fd*)",
    ]


# 코드 변경으로 삭제된 레거시 패턴 — 매 install 시 자동 제거
LEGACY_REMOVED_PATTERNS: list[str] = [
    "Bash(*sidabari*)",
    "Bash(*antigravity*)",  # 너무 broad — 진단 명령까지 차단
]


class DenyInstallReport:
    """deny 패턴 설치 결과 리포트."""

    __slots__: ClassVar[tuple[str, ...]] = ("installed_path", "created", "backed_up_path", "deny_count")
    installed_path: str
    created: bool
    backed_up_path: str | None
    deny_count: int

    def __init__(
        self,
        installed_path: str,
        created: bool,
        backed_up_path: str | None,
        deny_count: int,
    ):
        """Initialize the DenyInstallReport.

        Args:
            installed_path (str): str installed path.
            created (bool): bool created.
            backed_up_path (str | None): str | None backed up path.
            deny_count (int): int deny count.

        """
        self.installed_path = installed_path
        self.created = created
        self.backed_up_path = backed_up_path
        self.deny_count = deny_count

    def to_dict(self) -> dict[str, object]:
        """To Dict.

        Returns:
            dict[str, Any]: The dict[str, any] result.

        """
        return {
            "installed_path": self.installed_path,
            "created": self.created,
            "backed_up_path": self.backed_up_path,
            "deny_count": self.deny_count,
        }


def validate_directory(directory: str) -> Path:
    """작업 디렉토리를 검증합니다."""
    trimmed = directory.strip()
    if not trimmed:
        raise ValueError("작업 디렉토리가 설정되지 않았습니다")
    path = Path(trimmed)
    if not path.is_absolute():
        raise ValueError("작업 디렉토리는 절대경로여야 합니다")
    if not path.exists():
        raise ValueError(f"작업 디렉토리가 존재하지 않습니다: {path}")
    if not path.is_dir():
        raise ValueError(f"작업 디렉토리가 폴더가 아닙니다: {path}")
    return path


def _merge_deny(existing: dict[str, object], new_patterns: list[str]) -> int:
    """기존 설정에 deny 패턴을 병합합니다.

    Sidabari의 merge_deny 로직 이식:
    1. self-cleanup: 이전 _antigravity_managed 마커의 installed_patterns 제거
    2. 레거시 패턴 제거 (코드 변경으로 삭제된 것들)
    3. 새 패턴 추가 (중복 방지)
    4. 마커 갱신

    Returns:
        새로 추가된 패턴 수

    """
    permissions = _as_object_dict(existing.get("permissions", {}))
    existing["permissions"] = permissions

    # 1) 이전 marker의 installed_patterns 회수
    prev_installed: set[str] = set()
    for marker_key in [RULES_MARKER_KEY] + list(LEGACY_MARKER_KEYS):
        marker = _as_object_dict(permissions.get(marker_key, {}))
        if marker:
            installed_list = marker.get("installed_patterns", [])
            if isinstance(installed_list, list):
                prev_installed.update(p for p in cast(list[object], installed_list) if isinstance(p, str))

    deny_value = permissions.get("deny", [])
    deny_list: list[object] = cast(list[object], deny_value) if isinstance(deny_value, list) else []
    permissions["deny"] = deny_list

    # 1a) 이전 _antigravity 패턴 제거
    if prev_installed:
        deny_list[:] = [d for d in deny_list if not (isinstance(d, str) and d in prev_installed)]

    # 1b) 레거시 마커 키 제거
    for legacy_key in LEGACY_MARKER_KEYS:
        _ = permissions.pop(legacy_key, None)

    # 2) 코드 변경으로 삭제된 레거시 패턴 제거
    deny_list[:] = [d for d in deny_list if not (isinstance(d, str) and d in LEGACY_REMOVED_PATTERNS)]

    # 3) 새 패턴 추가 (중복 방지)
    existing_set: set[str] = {d for d in deny_list if isinstance(d, str)}
    added = 0
    for pat in new_patterns:
        if pat not in existing_set:
            deny_list.append(pat)
            existing_set.add(pat)
            added += 1

    # 4) 마커 갱신 — installed_patterns에 설치된 패턴 보관
    permissions[RULES_MARKER_KEY] = {
        "version": 2,
        "note": "Ssak-Ai 자동 설치. self-cleanup 마커.",
        "installed_patterns": list(new_patterns),
    }

    return added


def _write_with_backup(path: Path, content: bytes) -> str | None:
    """파일을 쓰면서 기존 파일은 백업합니다."""
    backup_path = None
    if path.exists():
        bak = path.with_suffix(".local.json.antigravity-bak")
        _ = shutil.copy2(path, bak)
        backup_path = str(bak)

    _ = path.write_bytes(content)
    return backup_path


def install_deny_rules(directory: str) -> DenyInstallReport:
    """지정 디렉토리의 .claude/settings.local.json에 deny 패턴을 설치합니다.

    Args:
        directory: Claude Code 작업 디렉토리 절대 경로

    Returns:
        DenyInstallReport — 설치 결과

    Raises:
        ValueError: 디렉토리 검증 실패

    """
    work_dir = validate_directory(directory)
    claude_dir = work_dir / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    settings_path = claude_dir / "settings.local.json"

    # 기존 설정 로드
    if settings_path.exists():
        raw = settings_path.read_text(encoding="utf-8").strip()
        if not raw:
            root: dict[str, object] = {}
            created = True
        else:
            payload = cast(object, json.loads(raw))
            if not isinstance(payload, dict):
                raise ValueError("settings.local.json이 객체가 아닙니다")
            root = _as_object_dict(cast(object, payload))
            created = False
    else:
        root = {}
        created = True

    patterns = deny_patterns()
    added = _merge_deny(root, patterns)

    serialized = json.dumps(root, indent=2, ensure_ascii=False).encode("utf-8")
    backup = _write_with_backup(settings_path, serialized)

    return DenyInstallReport(
        installed_path=str(settings_path),
        created=created,
        backed_up_path=backup,
        deny_count=len(patterns) if created else added,
    )


def get_deny_rules_status(directory: str) -> DenyInstallReport | None:
    """현재 deny 패턴 설치 상태를 확인합니다.

    Returns:
        DenyInstallReport 또는 None (미설치)

    """
    work_dir = validate_directory(directory)
    path = work_dir / ".claude" / "settings.local.json"
    if not path.exists():
        return None

    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return None

    try:
        parsed = cast(object, json.loads(raw))
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, dict):
        return None
    parsed_mapping = cast(dict[str, object], parsed)
    permissions = _as_object_dict(parsed_mapping.get("permissions", {}))
    deny_list = permissions.get("deny", [])
    deny_count = len(cast(list[object], deny_list)) if isinstance(deny_list, list) else 0

    managed = RULES_MARKER_KEY in permissions
    if not managed and deny_count == 0:
        return None

    return DenyInstallReport(
        installed_path=str(path),
        created=False,
        backed_up_path=None,
        deny_count=deny_count,
    )


def get_blocked_patterns_for_runtime() -> list[str]:
    """런타임 도구 가드레일에서 사용할 Bash glob 패턴 목록을 반환합니다.

    deny 패턴에서 Bash() 접두사를 제거한 순수 glob 패턴.
    fnmatch로 매칭할 수 있는 형식으로 반환합니다.
    """
    result: list[str] = []
    for pat in deny_patterns():
        if pat.startswith("Bash(") and pat.endswith(")"):
            inner = pat[5:-1]
            if inner:
                result.append(inner)
    return result


def is_command_blocked_by_deny(command: str) -> bool:
    """명령이 deny 패턴에 의해 차단되는지 확인합니다.

    fnmatch glob 매칭을 사용합니다.
    Claude Code 특수 형식(chmod:*)도 처리합니다:
      - "chmod:*" → 명령이 "chmod"로 시작하면 매칭
      - "*rm -rf*" → 표준 glob 매칭
    """
    import fnmatch

    patterns = get_blocked_patterns_for_runtime()
    for pattern in patterns:
        # Claude Code 콜론 형식: "chmod:*" → 명령이 "chmod"로 시작
        if ":" in pattern and not pattern.startswith("*"):
            prefix = pattern.split(":")[0]
            if command.startswith(prefix) or command.startswith(f"sudo {prefix}"):
                return True
        # 표준 fnmatch glob 매칭
        elif fnmatch.fnmatch(command, pattern):
            return True
    return False
