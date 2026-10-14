from __future__ import annotations

import time
from collections.abc import Iterable
from math import pow

from .memory_contracts import MemoryFact, MemoryFactAuthority

# 권위 수준별 기본 점수: 높은 권위일수록 회상 우선순위가 높다
_AUTHORITY_BASE: dict[MemoryFactAuthority, float] = {
    MemoryFactAuthority.INFERRED_PREFERENCE: 30.0,
    MemoryFactAuthority.PROJECT_DECISION: 50.0,
    MemoryFactAuthority.DURABLE_PREFERENCE: 60.0,
    MemoryFactAuthority.DURABLE_IDENTITY: 70.0,
    MemoryFactAuthority.CURRENT_USER: 80.0,
}
_DEFAULT_AUTHORITY_BASE = 20.0

# 최신성 기여도가 절반으로 줄어드는 기간(일)
_HALF_LIFE_DAYS = 30.0
_RECENCY_WEIGHT = 25.0
_SPECIFICITY_WEIGHT = 5.0
_MAX_SPECIFICITY_CHARS = 100


def score_fact(fact: MemoryFact, now: float | None = None) -> float:
    """메모리 팩트의 중요도 점수를 계산합니다.

    점수 = 권위 기본 점수 + 최신성(반감기 지수 감쇠) + 구체성(값 길이) 가중 합.
    """
    now = time.time() if now is None else now
    authority = _AUTHORITY_BASE.get(fact.authority, _DEFAULT_AUTHORITY_BASE)
    age_days = max(0.0, (now - fact.observed_at) / 86400.0)
    recency: float = _RECENCY_WEIGHT * pow(0.5, age_days / _HALF_LIFE_DAYS)
    specificity = _SPECIFICITY_WEIGHT * (min(len(fact.value), _MAX_SPECIFICITY_CHARS) / _MAX_SPECIFICITY_CHARS)
    return authority + recency + specificity


def rank_facts(
    facts: Iterable[MemoryFact],
    now: float | None = None,
    top_k: int | None = None,
) -> list[tuple[MemoryFact, float]]:
    """팩트 목록을 중요도 점수 내림차순으로 정렬해 (팩트, 점수) 쌍으로 반환합니다."""
    scored = sorted(
        ((fact, score_fact(fact, now)) for fact in facts),
        key=lambda pair: pair[1],
        reverse=True,
    )
    return scored if top_k is None else scored[:top_k]
