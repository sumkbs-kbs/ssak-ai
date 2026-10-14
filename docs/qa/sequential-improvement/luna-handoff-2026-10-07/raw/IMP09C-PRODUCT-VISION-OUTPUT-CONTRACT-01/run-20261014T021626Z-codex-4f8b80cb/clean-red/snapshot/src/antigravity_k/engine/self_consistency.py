"""Ssak-Ai: Self-Consistency 증폭 엔진.

========================================================
단일 로컬 모델(qwen3.6 등)에서 같은 프롬프트를 N회 샘플링하고,
가장 일관된 답변을 선택해 추론 정확도를 끌어올린다.

격차 해소 대상: 추론/수치/코드 정확도 (모델 크기 한계를 샘플링 다양성으로 보완)
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from typing import TypedDict, final

from pydantic import JsonValue

logger = logging.getLogger("antigravity_k.self_consistency")

_GenerateFn = Callable[..., str]
type ConfigPrimitive = str | int | float | bool | None
type ConfigInput = ConfigPrimitive | Mapping[str, ConfigPrimitive]


class EngineKwargs(TypedDict, total=False):
    n_samples: int
    base_temperature: float
    temperature_spread: float
    similarity_threshold: float
    complexity_threshold: float
    selection: str


@dataclass(frozen=True, slots=True)
class ConsistencySample:
    """단일 샘플 결과."""

    index: int
    temperature: float
    text: str
    normalized: str
    cluster_id: int = -1


@dataclass(frozen=True, slots=True)
class ConsistencyTrace:
    """Self-consistency 실행 추적."""

    selected: str = ""
    confidence: float = 0.0  # 선택된 클러스터 크기 / N (0.0~1.0)
    samples: list[ConsistencySample] = field(default_factory=list)
    cluster_sizes: list[int] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""
    latency_ms: float = 0.0


_CODE_FENCE = re.compile(r"```(?:\w+)?\s*\n(.*?)```", re.DOTALL)


def normalize_answer(text: str) -> str:
    """비교를 위한 정규화: 코드 펜스는 본문만, 소문자화, 공백/구두점 축약.

    코드 생성 작업에서는 펜스 안의 코드가 정답의 핵심이므로 코드 본문을
    우선 정규화 대상으로 삼는다. 코드가 없으면 전문을 정규화한다.
    """
    fences = _CODE_FENCE.findall(text or "")
    body = fences[-1] if fences else (text or "")
    body = body.lower()
    # 파라미터명/문장 부호/과도한 공백은 동등 답변 비교에서 무시
    body = re.sub(r"[^\w\s]", " ", body)
    body = re.sub(r"\s+", " ", body).strip()
    return body


def _token_set(text: str) -> frozenset[str]:
    return frozenset(text.split()) if text else frozenset()


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    """토큰 집합 간 Jaccard 유사도 (0.0~1.0)."""
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


@final
class SelfConsistencyEngine:
    """단일 모델 N샘플링 → 유사도 클러스터링 → 다수결 대표 선택.

    generate_fn(prompt, **kwargs) -> str 형태로, 엔진이 샘플마다 temperature를
    주입해 다양성을 확보한다. generate_fn이 None이면 비활성(self-consistency off).
    """

    _generate_fn: _GenerateFn | None
    n_samples: int
    base_temperature: float
    temperature_spread: float
    similarity_threshold: float
    selection: str
    complexity_threshold: float | None

    def __init__(
        self,
        generate_fn: _GenerateFn | None = None,
        n_samples: int = 5,
        base_temperature: float = 0.7,
        temperature_spread: float = 0.2,
        similarity_threshold: float = 0.5,
        selection: str = "majority",
        complexity_threshold: float | None = None,
    ) -> None:
        self._generate_fn = generate_fn
        self.n_samples = max(1, int(n_samples))
        self.base_temperature = float(base_temperature)
        self.temperature_spread = float(temperature_spread)
        self.similarity_threshold = float(similarity_threshold)
        self.selection = selection
        # 복잡도 게이트: 작업 복잡도가 임계치 미만이면 N샘플링을 스킵한다 (비용 절제).
        # None이면 게이트 없음(항상 N샘플링). 0.0~1.0.
        self.complexity_threshold = complexity_threshold

    def set_generate_fn(self, fn: _GenerateFn) -> None:
        """모델 호출 함수를 설정한다."""
        self._generate_fn = fn

    def _sample_temperature(self, i: int) -> float:
        """샘플 i에 대한 온도: 기준 온도 ± spread로 다양성 확보 (0.0~1.5 clamp)."""
        half = max(1, self.n_samples - 1)
        offset = (i / half - 0.5) * 2 * self.temperature_spread
        return max(0.0, min(1.5, self.base_temperature + offset))

    def collect_samples(self, prompt: str, **gen_kwargs: JsonValue) -> list[ConsistencySample]:
        """프롬프트를 N회 샘플링해 ConsistencySample 리스트를 반환한다.

        병렬 웨이브 + 과반 조기 종료: 로컬 27B에서 N=5 순차 샘플링은
        5배 지연이다. 첫 웨이브(과반 수)를 병렬 실행한 뒤 이미 과반
        클러스터가 형성됐으면 나머지 샘플은 결과를 바꿀 수 없으므로
        생략한다 → 지연 ~5배 → ~1-2배.
        """
        if self._generate_fn is None:
            return []

        def _one(i: int) -> ConsistencySample:
            temp = self._sample_temperature(i)
            kwargs = dict(gen_kwargs)
            kwargs["temperature"] = temp
            generate_fn = self._generate_fn
            if generate_fn is None:
                return ConsistencySample(index=i, temperature=temp, text="", normalized="")
            try:
                text = generate_fn(prompt, **kwargs)
            except Exception as exc:  # 개별 샘플 실패는 전체를 깨지 않는다
                logger.debug("self-consistency sample %d failed: %s", i, exc)
                text = ""
            return ConsistencySample(
                index=i,
                temperature=temp,
                text=text,
                normalized=normalize_answer(text),
            )

        def _run_wave(indices: list[int]) -> None:
            if len(indices) == 1:
                samples.append(_one(indices[0]))
                return
            with ThreadPoolExecutor(max_workers=len(indices)) as executor:
                samples.extend(executor.map(_one, indices))

        majority = self.n_samples // 2 + 1
        first_wave = min(self.n_samples, max(2, majority))
        samples: list[ConsistencySample] = []

        _run_wave(list(range(first_wave)))
        if first_wave < self.n_samples:
            assignment = self.cluster(samples)
            if assignment:
                largest = max(assignment.count(c) for c in set(assignment))
                if largest >= majority:
                    logger.info(
                        "[SelfConsistency] 과반 클러스터(%d/%d) 형성 — 조기 종료, 남은 %d 샘플 생략",
                        largest,
                        self.n_samples,
                        self.n_samples - first_wave,
                    )
                    samples.sort(key=lambda s: s.index)
                    return samples
            _run_wave(list(range(first_wave, self.n_samples)))

        samples.sort(key=lambda s: s.index)
        return samples

    def cluster(self, samples: list[ConsistencySample]) -> list[int]:
        """정규화된 답변을 유사도 기반 그리디 클러스터링해 cluster_id를 할당한다."""
        clusters: list[set[int]] = []  # 각 클러스터는 샘플 인덱스 집합
        token_sets = [_token_set(s.normalized) for s in samples]
        for i, s in enumerate(samples):
            if not s.normalized:
                continue
            placed = False
            for c in clusters:
                rep = next(iter(c))
                if jaccard(token_sets[i], token_sets[rep]) >= self.similarity_threshold:
                    c.add(i)
                    placed = True
                    break
            if not placed:
                clusters.append({i})
        # 빈 답변은 자기 자신만의 클러스터(또는 버림) — 여기서는 자체 클러스터
        assignment = [-1] * len(samples)
        for cid, members in enumerate(clusters):
            for m in members:
                assignment[m] = cid
        for i, s in enumerate(samples):
            if assignment[i] == -1:
                clusters.append({i})
                assignment[i] = len(clusters) - 1
        return assignment

    def select(self, samples: list[ConsistencySample], assignment: list[int]) -> tuple[str, float, list[int]]:
        """가장 큰 클러스터의 대표 답변과 confidence를 반환한다.

        반환: (선택된 원문, confidence, 클러스터 크기 리스트)
        confidence = 최대 클러스터 크기 / 유효(비빈) 샘플 수.
        """
        if not samples:
            return "", 0.0, []
        n_clusters = max(assignment) + 1 if assignment else 0
        sizes = [assignment.count(c) for c in range(n_clusters)]
        if not sizes:
            return samples[0].text, 0.0, []
        # 동점 처리: 가장 큰 클러스터 중 첫 번째. 평균 온도가 낮은(더 결정론적)
        # 샘플을 대표로 삼아 안정성을 높인다.
        best_cid = max(range(n_clusters), key=lambda c: sizes[c])
        members = [i for i, cid in enumerate(assignment) if cid == best_cid]
        members.sort(key=lambda i: samples[i].temperature)
        chosen = samples[members[0]].text
        valid = sum(1 for s in samples if s.normalized)
        confidence = sizes[best_cid] / valid if valid else 0.0
        return chosen, confidence, sizes

    def run(self, prompt: str, **gen_kwargs: JsonValue) -> ConsistencyTrace:
        """프롬프트에 대해 self-consistency를 수행한다."""
        import time

        start = time.monotonic()
        if self._generate_fn is None or self.n_samples <= 1:
            return ConsistencyTrace(skipped=True, skip_reason="disabled or n_samples<=1")
        if self.complexity_threshold is not None:
            # 복잡도 게이트: 단순 작업은 N샘플링 비용을 절제한다.
            from antigravity_k.engine.chain_of_verification_models import estimate_complexity

            complexity = estimate_complexity(prompt)
            if complexity < self.complexity_threshold:
                return ConsistencyTrace(
                    skipped=True,
                    skip_reason=f"below complexity threshold ({complexity:.2f}<{self.complexity_threshold})",
                )
        samples = self.collect_samples(prompt, **gen_kwargs)
        if not any(s.text.strip() for s in samples):
            return ConsistencyTrace(
                samples=samples,
                skipped=True,
                skip_reason="all samples empty",
                latency_ms=(time.monotonic() - start) * 1000,
            )
        assignment = self.cluster(samples)
        chosen, confidence, sizes = self.select(samples, assignment)
        samples = [replace(sample, cluster_id=cid) for sample, cid in zip(samples, assignment, strict=True)]
        return ConsistencyTrace(
            selected=chosen,
            confidence=confidence,
            samples=samples,
            cluster_sizes=sizes,
            latency_ms=(time.monotonic() - start) * 1000,
        )


def config_to_engine_kwargs(cfg: ConfigInput) -> EngineKwargs:
    """amplification.self_consistency config dict를 SelfConsistencyEngine kwargs로 매핑.

    None 키는 엔진 기본값으로 폴백된다.
    """
    if not isinstance(cfg, Mapping):
        return {}
    out: EngineKwargs = {}
    numeric_values = {
        key: cfg[key]
        for key in (
            "n_samples",
            "base_temperature",
            "temperature_spread",
            "similarity_threshold",
            "complexity_threshold",
        )
        if key in cfg and cfg[key] is not None
    }
    for key, raw in numeric_values.items():
        if not isinstance(raw, (str, int, float)) or isinstance(raw, bool):
            continue
        try:
            if key == "n_samples":
                out["n_samples"] = int(raw)
            elif key == "base_temperature":
                out["base_temperature"] = float(raw)
            elif key == "temperature_spread":
                out["temperature_spread"] = float(raw)
            elif key == "similarity_threshold":
                out["similarity_threshold"] = float(raw)
            elif key == "complexity_threshold":
                out["complexity_threshold"] = float(raw)
        except (TypeError, ValueError):
            logger.warning("self-consistency.%s 무시(잘못된 값): %r", key, raw)
    selection = cfg.get("selection")
    if isinstance(selection, str):
        out["selection"] = selection
    return out
