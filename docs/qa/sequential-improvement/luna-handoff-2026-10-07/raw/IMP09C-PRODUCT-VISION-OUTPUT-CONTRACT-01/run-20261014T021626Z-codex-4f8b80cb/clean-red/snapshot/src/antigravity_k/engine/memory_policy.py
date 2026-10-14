"""Ssak-Ai: 메모리 정책 엔진 (Memory Policy).

=================================================
LRU 기반 모델 메모리 관리 정책을 캡슐화합니다.
ModelManager의 _ensure_memory 로직을 분리하여 테스트 용이성과 확장성을 높입니다.

사용법:
    policy = MemoryPolicy(max_gb=48.0, cooldown_sec=60, auto_unload=True)
    policy.ensure_memory(needed_gb=8.0, loaded_models=manager._loaded, unload_fn=manager.unload)
    policy.evict_unused(loaded_models=manager._loaded, unload_fn=manager.unload, idle_sec=300)
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from typing import Protocol

logger = logging.getLogger("antigravity_k.memory_policy")


class LoadedModelLike(Protocol):
    actual_memory_gb: float
    last_used_at: float


class MemoryPolicy:
    """LRU 기반 모델 메모리 관리 정책.

    Attributes:
        max_gb: 최대 허용 메모리 (GB)
        cooldown_sec: 언로드 쿨다운 (초)
        auto_unload: 자동 언로드 활성화 여부
        idle_eviction_sec: 유휴 모델 자동 퇴출 기준 시간 (초), 데몬에서 사용

    """

    def __init__(
        self,
        max_gb: float = 48.0,
        cooldown_sec: float = 60.0,
        auto_unload: bool = True,
        idle_eviction_sec: float = 300.0,
    ):
        """Initialize the MemoryPolicy.

        Args:
            max_gb (float): float max gb.
            cooldown_sec (float): float cooldown sec.
            auto_unload (bool): bool auto unload.
            idle_eviction_sec (float): float idle eviction sec.

        """
        self.max_gb: float = max_gb
        self.cooldown_sec: float = cooldown_sec
        self.auto_unload: bool = auto_unload
        self.idle_eviction_sec: float = idle_eviction_sec

    def current_usage_gb(self, loaded_models: Mapping[str, LoadedModelLike]) -> float:
        """현재 로드된 모델의 총 메모리 사용량(GB)을 반환합니다."""
        return sum(model.actual_memory_gb for model in loaded_models.values())

    def ensure_memory(
        self,
        needed_gb: float,
        loaded_models: Mapping[str, LoadedModelLike],
        unload_fn: Callable[[str], bool],
    ) -> None:
        """필요한 메모리를 확보합니다. LRU 순서로 모델을 언로드합니다.

        Args:
            needed_gb: 확보해야 할 메모리 (GB)
            loaded_models: {model_name: LoadedModel} 딕셔너리
            unload_fn: 모델 언로드 함수 (model_name -> bool)

        Raises:
            MemoryError: 충분한 메모리를 확보할 수 없을 때

        """
        if not self.auto_unload:
            return

        current_used = self.current_usage_gb(loaded_models)
        available = self.max_gb - current_used

        if available >= needed_gb:
            return

        # LRU: last_used_at 기준 오래된 모델부터 언로드
        sorted_models = sorted(
            list(loaded_models.items()),
            key=lambda item: item[1].last_used_at,
        )

        for name, loaded in sorted_models:
            if available >= needed_gb:
                break

            elapsed_sec = time.time() - loaded.last_used_at
            mem_gb = loaded.actual_memory_gb

            if elapsed_sec < self.cooldown_sec:
                logger.warning(
                    "[%s] 쿨다운(%s초) 경과 전이지만 메모리 부족으로 강제 언로드 시도 (경과: %s초)",
                    name,
                    self.cooldown_sec,
                    elapsed_sec,
                )
            else:
                logger.info("[%s] 메모리 확보를 위해 자동 언로드 (%sGB)", name, mem_gb)

            available += mem_gb
            _ = unload_fn(name)

        if available < needed_gb:
            raise MemoryError(
                f"메모리 부족: 필요 {needed_gb}GB, 사용 가능 {available:.1f}GB (한도 {self.max_gb}GB)",
            )

    def evict_unused(
        self,
        loaded_models: Mapping[str, LoadedModelLike],
        unload_fn: Callable[[str], bool],
        idle_sec: float | None = None,
    ) -> list[str]:
        """유휴 시간이 초과된 모델을 퇴출합니다.

        Args:
            loaded_models: {model_name: LoadedModel} 딕셔너리
            unload_fn: 모델 언로드 함수
            idle_sec: 유휴 판정 기준 (초), None이면 self.idle_eviction_sec 사용

        Returns:
            퇴출된 모델 이름 리스트

        """
        threshold = idle_sec if idle_sec is not None else self.idle_eviction_sec
        now = time.time()
        evicted: list[str] = []

        # dict가 반복 중 변경되므로 리스트로 미리 복사
        for name, loaded in list(loaded_models.items()):
            last_used = loaded.last_used_at
            if now - last_used > threshold:
                mem_gb = loaded.actual_memory_gb
                logger.info(
                    "[MemoryPolicy] 유휴 모델 퇴출: %s (idle %ss > %ss, %sGB)",
                    name,
                    now - last_used,
                    threshold,
                    mem_gb,
                )
                _ = unload_fn(name)
                evicted.append(name)

        return evicted
