from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from math import sqrt
from statistics import fmean, stdev
from typing import ClassVar, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from antigravity_k.engine.benchmark_cases import BenchmarkCase

_ONE_SIDED_T_95: Final[tuple[float, ...]] = (
    6.314,
    2.920,
    2.353,
    2.132,
    2.015,
    1.943,
    1.895,
    1.860,
    1.833,
    1.812,
    1.796,
    1.782,
    1.771,
    1.761,
    1.753,
    1.746,
    1.740,
    1.734,
    1.729,
    1.725,
    1.721,
    1.717,
    1.714,
    1.711,
    1.708,
    1.706,
    1.703,
    1.701,
    1.699,
    1.697,
)


class FrontierEvidenceError(ValueError):
    def __init__(self, detail: str):
        self.detail: str = detail
        super().__init__(detail)


class FrontierHarnessConfig(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["revision_off"] = "revision_off"
    quality_gate_retries: Literal[0] = 0
    repetitions: int = Field(default=3, ge=1, le=100)
    seed: int = 0


class FrontierEvidencePolicy(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    confidence_level: float = Field(default=0.95, ge=0.95, le=0.95)
    minimum_observations: int = Field(default=6, ge=2)
    maximum_acceptable_gap: float = Field(default=0.05, ge=0.0, le=1.0)


class FrontierObservation(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(min_length=1)
    repetition: int = Field(ge=0)
    local_score: float = Field(ge=0.0, le=1.0)
    frontier_score: float = Field(ge=0.0, le=1.0)
    local_latency_ms: float = Field(ge=0.0)
    frontier_latency_ms: float = Field(ge=0.0)


class FrontierEvidence(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[2] = 2
    local_model: str = Field(min_length=1)
    frontier_model: str = Field(min_length=1)
    run_at: datetime
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    harness_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy: FrontierEvidencePolicy
    observations: tuple[FrontierObservation, ...]
    observation_count: int = Field(ge=1)
    mean_local_score: float
    mean_frontier_score: float
    mean_gap: float
    standard_error: float = Field(ge=0.0)
    confidence_upper_bound: float
    local_reaches_frontier: bool
    reasons: tuple[str, ...] = ()


def build_frontier_evidence(
    *,
    local_model: str,
    frontier_model: str,
    cases: Sequence[BenchmarkCase],
    harness: FrontierHarnessConfig,
    observations: tuple[FrontierObservation, ...],
    policy: FrontierEvidencePolicy | None = None,
    run_at: datetime | None = None,
) -> FrontierEvidence:
    active_policy = policy or FrontierEvidencePolicy()
    _validate_observations(cases, observations, harness.repetitions)
    gaps = tuple(item.frontier_score - item.local_score for item in observations)
    mean_gap = fmean(gaps)
    standard_error = 0.0 if len(gaps) < 2 else stdev(gaps) / sqrt(len(gaps))
    confidence_upper_bound = mean_gap + _critical_value(len(gaps)) * standard_error
    reasons: list[str] = []
    if len(observations) < active_policy.minimum_observations:
        reasons.append("insufficient paired observations")
    if confidence_upper_bound > active_policy.maximum_acceptable_gap:
        reasons.append("confidence upper bound exceeds acceptable frontier gap")
    return FrontierEvidence(
        local_model=local_model,
        frontier_model=frontier_model,
        run_at=run_at or datetime.now(UTC),
        dataset_sha256=_sha256([asdict(case) for case in cases]),
        harness_sha256=_sha256(harness.model_dump(mode="json")),
        policy=active_policy,
        observations=observations,
        observation_count=len(observations),
        mean_local_score=_rounded(fmean(item.local_score for item in observations)),
        mean_frontier_score=_rounded(fmean(item.frontier_score for item in observations)),
        mean_gap=_rounded(mean_gap),
        standard_error=_rounded(standard_error),
        confidence_upper_bound=_rounded(confidence_upper_bound),
        local_reaches_frontier=not reasons,
        reasons=tuple(reasons),
    )


def frontier_evidence_sha256(evidence: FrontierEvidence) -> str:
    return _sha256(evidence.model_dump(mode="json"))


def _validate_observations(
    cases: Sequence[BenchmarkCase],
    observations: tuple[FrontierObservation, ...],
    repetitions: int,
) -> None:
    if not cases:
        raise FrontierEvidenceError("at least one benchmark case is required")
    expected_ids = {case.id for case in cases}
    observed_ids = {item.case_id for item in observations}
    if observed_ids != expected_ids:
        raise FrontierEvidenceError("observation case ids must match the selected dataset")
    expected_pairs = {(case.id, repetition) for case in cases for repetition in range(repetitions)}
    observed_pairs = {(item.case_id, item.repetition) for item in observations}
    if observed_pairs != expected_pairs or len(observed_pairs) != len(observations):
        raise FrontierEvidenceError("each case and repetition must have exactly one paired observation")


def _critical_value(observation_count: int) -> float:
    degrees_of_freedom = observation_count - 1
    index = min(degrees_of_freedom, len(_ONE_SIDED_T_95)) - 1
    return _ONE_SIDED_T_95[index]


def _rounded(value: float) -> float:
    return round(value, 6)


def _sha256(value: Sequence[dict[str, str | int | tuple[str, ...]]] | dict[str, str | int]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "FrontierEvidence",
    "FrontierEvidenceError",
    "FrontierEvidencePolicy",
    "FrontierHarnessConfig",
    "FrontierObservation",
    "build_frontier_evidence",
    "frontier_evidence_sha256",
]
