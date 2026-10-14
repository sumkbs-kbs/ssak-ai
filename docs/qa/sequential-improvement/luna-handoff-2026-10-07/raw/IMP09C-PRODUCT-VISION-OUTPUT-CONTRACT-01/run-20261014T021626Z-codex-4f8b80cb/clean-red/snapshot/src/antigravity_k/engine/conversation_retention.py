"""NX-02 후속 — 대화 이력(journal)의 retention/quota 결정과 집행 (ADR-DAT-02 Context 8).

배경: journal 은 "원본을 압축 뒤에도 보존한다"는 결정(NX-02)의 결과로 **총 턴 수에 비례해
커진다**. view 는 soft max 64 로 bounded 이지만 journal 은 bounded 가 아니어서, 릴리스 전에
"얼마나 커질 수 있고, 한계에 닿으면 무엇이 일어나는가"를 정해야 한다.

결정(ADR-DAT-02 Context 8 의 요구를 만족하는 형태):

* **자동 prune 은 없다.** 조용한 삭제는 ADR 이 명시적으로 금지한다("silent pruning is not
  allowed"). 사용자가 보는 원본 이력을 스스로 지우는 기능은 이 카드에서 만들지 않는다.
* 한계는 **바이트**로 명시하고, 한계에 닿으면 **쓰기를 거절한다**(fail-closed). 거절은
  507 `conversation_history_quota_exceeded` 로 표면화되고, 기존 데이터는 그대로 남는다.
  "가득 차면 오래된 것을 지운다"는 선택은 데이터 손실이므로 기본값이 될 수 없다.
* 연속 두 단계로 나눈다: soft cap 은 **경고**(운영자가 미리 조치), hard cap 은 **거절**.
* 한계는 **대화 하나당** 집행한다. 저장소 전체 스캔은 O(대화 수)라 매 append 마다 할 수
  없다 — 저장소 전체 사용량은 `ConversationStore.store_usage()` 로 **요청 시 관측**한다.

기본값(환경변수로 덮어쓴다, `0` = 그 단계 비활성):

| 단계 | 환경변수 | 기본값 | 의미 |
|---|---|---|---|
| soft | `AGK_CONVERSATION_JOURNAL_SOFT_CAP_MB` | 64 MiB | 넘으면 경고 로그 + `degraded` 관측. 쓰기는 계속된다 |
| hard | `AGK_CONVERSATION_JOURNAL_HARD_CAP_MB` | 512 MiB | 넘으면 append 거절(507). 데이터는 지우지 않는다 |
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Final, Literal

logger = logging.getLogger("antigravity_k.engine.conversation_retention")

SOFT_CAP_ENV: Final = "AGK_CONVERSATION_JOURNAL_SOFT_CAP_MB"
HARD_CAP_ENV: Final = "AGK_CONVERSATION_JOURNAL_HARD_CAP_MB"
DEFAULT_SOFT_CAP_MB: Final = 64.0
DEFAULT_HARD_CAP_MB: Final = 512.0
BYTES_PER_MB: Final = 1024 * 1024
DISABLED_CAP_MB: Final = 0.0

UsageVerdict = Literal["ok", "soft_exceeded", "hard_exceeded"]


@dataclass(frozen=True)
class JournalRetentionPolicy:
    """대화 하나의 journal 에 적용되는 byte 한계."""

    soft_cap_bytes: int
    hard_cap_bytes: int

    @property
    def enforced(self) -> bool:
        """hard cap 이 켜져 있는가 — 꺼져 있으면 쓰기를 거절하지 않는다."""
        return self.hard_cap_bytes > 0

    def verdict(self, size_bytes: int) -> UsageVerdict:
        """현재 크기의 판정. hard 가 soft 보다 낮게 설정돼도 hard 가 이긴다."""
        if self.hard_cap_bytes > 0 and size_bytes >= self.hard_cap_bytes:
            return "hard_exceeded"
        if self.soft_cap_bytes > 0 and size_bytes >= self.soft_cap_bytes:
            return "soft_exceeded"
        return "ok"

    def to_dict(self) -> dict[str, int | bool]:
        return {
            "soft_cap_bytes": self.soft_cap_bytes,
            "hard_cap_bytes": self.hard_cap_bytes,
            "enforced": self.enforced,
        }


def _read_cap_mb(env_name: str, default_mb: float) -> float:
    """환경변수에서 MB 값을 읽는다. 잘못된 값은 기본값으로 돌리고 이유를 남긴다."""
    raw = os.environ.get(env_name)
    if raw is None or not raw.strip():
        return default_mb
    try:
        value = float(raw)
    except ValueError:
        logger.warning("Ignoring invalid %s=%r (using %.0f MB)", env_name, raw, default_mb)
        return default_mb
    if value < 0:
        logger.warning("Ignoring negative %s=%r (using %.0f MB)", env_name, raw, default_mb)
        return default_mb
    return value


def resolve_policy() -> JournalRetentionPolicy:
    """환경변수에서 정책을 해석한다(매 호출 — 설정 변경이 재시작 없이 반영된다)."""
    soft_mb = _read_cap_mb(SOFT_CAP_ENV, DEFAULT_SOFT_CAP_MB)
    hard_mb = _read_cap_mb(HARD_CAP_ENV, DEFAULT_HARD_CAP_MB)
    if hard_mb > 0 and soft_mb > 0 and hard_mb < soft_mb:
        # 역전은 설정 실수다 — 경고만 남기고 값을 그대로 둔다(hard 판정이 우선이라 동작은 안전하다).
        logger.warning("hard cap %.0f MB is below soft cap %.0f MB — hard refusal wins", hard_mb, soft_mb)
    return JournalRetentionPolicy(
        soft_cap_bytes=int(soft_mb * BYTES_PER_MB),
        hard_cap_bytes=int(hard_mb * BYTES_PER_MB),
    )


def format_mb(size_bytes: int) -> str:
    """사람이 읽는 크기 — 메시지/컨텍스트에 같은 표기를 쓴다."""
    return f"{size_bytes / BYTES_PER_MB:.2f} MB"
