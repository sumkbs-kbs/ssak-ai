"""Live pilot harness (P10 부속) — 실제 provider 실행과 분리 보고 계약.

계약(BENCHMARK_AND_ABLATION.md 실행 보완 명세 · T13):

- **분리 보고:** fixture(``DETERMINISTIC_FIXTURE``)와 live(``LIVE_PILOT``) 결과는 별도 artifact다.
  ``merge_reports``는 kind가 섞이면 거부한다 — fixture 통과를 live 성능으로 주장할 수 없다.
- **stub 금지:** 이 harness는 주입된 ``LiveTrialPort``만 쓴다. port가 없으면 수치를 만들지 않고
  ``NOT_RUN``과 사유를 남긴다.
- **최소 3 paired trial:** 동일 task를 arm별로 최소 ``spec.live_pilot_min_trials``회 반복하고
  평균·중앙값·p95·분포를 함께 보고한다. trial 수가 부족하면 실행하지 않는다.
- **순서 효과:** trial마다 fresh-first / mature-first를 교대하고, 순서별 평균 차이를 report에 남긴다.
- **스냅샷:** model snapshot을 고정하지 못하면 reproducibility 제한 사유를 필수로 기록한다(비어 있으면 거부).
- **확증 아님:** pilot 표본으로 우위를 확정하지 않는다. 확증 표본 크기는 별도 등록이며, 등록 없이는
  ``claim_scope``가 pilot 전용으로 남는다.

이 모듈은 provider/UI를 import하지 않는다(architecture guard). 실제 모델 호출은 caller가 port로 결선한다.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final, Protocol, runtime_checkable

from antigravity_k.engine.cognitive.growth import (
    ArmRole,
    BenchmarkSpec,
    GrowthBenchmarkError,
    GrowthTask,
    MechanismSet,
    RunKind,
    SplitRole,
    tasks_for,
)
from antigravity_k.engine.cognitive.models import same_enum

#: pilot 결과는 확증이 아니다. 확증 표본이 등록되기 전까지 이 scope를 유지한다.
CLAIM_SCOPE_PILOT: Final[str] = "LIVE_PILOT_PILOT_ONLY"
CLAIM_SCOPE_LIMITED: Final[str] = "LIVE_PILOT_REPRODUCIBILITY_LIMITED"
PILOT_ARMS: Final[tuple[ArmRole, ...]] = (ArmRole.FRESH, ArmRole.MATURE)


class LivePilotStatus(StrEnum):
    NOT_RUN = "NOT_RUN"
    COMPLETED = "COMPLETED"
    INVALID = "INVALID"
    NOT_COMPLETE = "NOT_COMPLETE"


class TrialOrder(StrEnum):
    """순서 효과를 확인하기 위해 trial마다 교대한다."""

    FRESH_FIRST = "FRESH_FIRST"
    MATURE_FIRST = "MATURE_FIRST"


class TrialEventStatus(StrEnum):
    """원시 ledger에 남는 trial 사건 상태."""

    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"


class LiveTrialTimeout(TimeoutError):
    """port가 trial 시간 초과를 보고할 때 사용한다."""


class LiveTrialBudgetExhausted(RuntimeError):
    """port가 budget 소진을 보고할 때 사용한다."""


#: order_policy / primary metric 허용 목록 — 미지원은 provider 호출 전 거절.
SUPPORTED_ORDER_POLICIES: Final[frozenset[str]] = frozenset({"alternating"})
#: metric name → (outcome attribute, lower_is_better)
PRIMARY_METRIC_FIELDS: Final[Mapping[str, tuple[str, bool]]] = {
    "total_retries": ("retries", True),
    "total_tool_calls": ("tool_calls", True),
    "latency_p50": ("latency_ms", True),
    "context_tokens": ("tokens", True),
}
SUPPORTED_PRIMARY_METRICS: Final[frozenset[str]] = frozenset(PRIMARY_METRIC_FIELDS)


class FixtureLiveMixError(ValueError):
    """fixture 결과와 live 결과를 한 판정으로 합치려 할 때 거부한다."""


@dataclass(frozen=True, slots=True)
class ProviderAttestation:
    """실제 provider 정체성. stub은 여기에 stub이라고 적어야 한다."""

    provider_id: str
    model_id: str
    model_snapshot: str
    decoding: str
    hardware: str
    snapshot_pinned: bool
    reproducibility_limits: tuple[str, ...] = ()

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "model_snapshot": self.model_snapshot,
            "decoding": self.decoding,
            "hardware": self.hardware,
            "snapshot_pinned": self.snapshot_pinned,
            "reproducibility_limits": list(self.reproducibility_limits),
        }


@dataclass(frozen=True, slots=True)
class LiveTrialRequest:
    task_id: str
    split: str
    arm: ArmRole
    trial_index: int
    order: TrialOrder
    policy_version: str | None
    advisory_refs: tuple[str, ...]
    mechanism_flags: Mapping[str, bool] = field(default_factory=dict)
    seed: int = 0
    run_id: str = ""
    trial_uid: str = ""

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "task_id": self.task_id,
            "split": self.split,
            "arm": self.arm.value,
            "trial_index": self.trial_index,
            "order": self.order.value,
            "policy_version": self.policy_version,
            "advisory_refs": list(self.advisory_refs),
            "mechanism_flags": dict(self.mechanism_flags),
            "seed": self.seed,
            "run_id": self.run_id,
            "trial_uid": self.trial_uid,
        }


@dataclass(frozen=True, slots=True)
class LiveTrialOutcome:
    """trial 한 건의 관찰값. 성과 주장이 아니라 측정값이다."""

    success: bool
    retries: int
    tool_calls: int
    brain_calls: int
    tokens: int
    latency_ms: float
    duplicate_dispatch: bool = False
    safety_violation: str = ""
    detail: str = ""
    error_category: str = ""

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "success": self.success,
            "retries": self.retries,
            "tool_calls": self.tool_calls,
            "brain_calls": self.brain_calls,
            "tokens": self.tokens,
            "latency_ms": self.latency_ms,
            "duplicate_dispatch": self.duplicate_dispatch,
            "safety_violation": self.safety_violation,
            "detail": self.detail,
            "error_category": self.error_category,
        }


@runtime_checkable
class LiveTrialPort(Protocol):
    """실제 모델·runtime 결선. harness는 이 표면만 안다."""

    attestation: ProviderAttestation

    def run_trial(self, request: LiveTrialRequest) -> LiveTrialOutcome: ...


@dataclass(frozen=True, slots=True)
class LivePilotPlan:
    """실행 전에 고정하는 pilot 계획."""

    trials_per_task: int
    split: SplitRole = SplitRole.FINAL
    order_policy: str = "alternating"
    #: 확증 표본 크기는 pilot 변동성을 본 뒤가 아니라 별도로 등록한다. None이면 확증 근거가 아니다.
    confirmatory_sample_size: int | None = None
    policy_version: str | None = None
    advisory_refs: tuple[str, ...] = ()
    seed: int = 0
    budget_calls: int | None = None
    budget_tokens: int | None = None
    code_fingerprint: str = ""

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "trials_per_task": self.trials_per_task,
            "split": self.split.value,
            "order_policy": self.order_policy,
            "confirmatory_sample_size": self.confirmatory_sample_size,
            "policy_version": self.policy_version,
            "advisory_refs": list(self.advisory_refs),
            "seed": self.seed,
            "budget_calls": self.budget_calls,
            "budget_tokens": self.budget_tokens,
            "code_fingerprint": self.code_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class Distribution:
    """평균 하나로 보고하지 않는다 — 중앙값·p95·분포를 함께 남긴다."""

    count: int
    mean: float
    median: float
    p95: float
    values: Mapping[str, int] = field(default_factory=dict)

    @classmethod
    def of(cls, samples: Sequence[float]) -> Distribution:
        if not samples:
            raise GrowthBenchmarkError("표본이 없는 분포는 만들지 않는다")
        ordered = sorted(float(sample) for sample in samples)
        buckets: dict[str, int] = {}
        for value in ordered:
            key = f"{value:g}"
            buckets[key] = buckets.get(key, 0) + 1
        index = min(len(ordered) - 1, max(0, int(round(0.95 * (len(ordered) - 1)))))
        return cls(
            count=len(ordered),
            mean=sum(ordered) / len(ordered),
            median=ordered[len(ordered) // 2]
            if len(ordered) % 2
            else (ordered[len(ordered) // 2 - 1] + ordered[len(ordered) // 2]) / 2,
            p95=ordered[index],
            values=dict(sorted(buckets.items())),
        )

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "count": self.count,
            "mean": self.mean,
            "median": self.median,
            "p95": self.p95,
            "values": dict(self.values),
        }


@dataclass(frozen=True, slots=True)
class LiveArmSummary:
    arm: ArmRole
    trials: int
    success_rate: Distribution
    retries: Distribution
    tool_calls: Distribution
    latency_ms: Distribution
    tokens: Distribution
    negative_transfer_successes: int
    duplicate_dispatches: int
    safety_violations: tuple[str, ...]
    outcome_statuses: Mapping[str, int]

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "arm": self.arm.value,
            "trials": self.trials,
            "success_rate": self.success_rate.as_mapping(),
            "retries": self.retries.as_mapping(),
            "tool_calls": self.tool_calls.as_mapping(),
            "latency_ms": self.latency_ms.as_mapping(),
            "tokens": self.tokens.as_mapping(),
            "negative_transfer_successes": self.negative_transfer_successes,
            "duplicate_dispatches": self.duplicate_dispatches,
            "safety_violations": list(self.safety_violations),
            "outcome_statuses": dict(self.outcome_statuses),
        }


@dataclass(frozen=True, slots=True)
class LivePilotVerdict:
    """pilot 판정. 확증 주장이 아니며 scope를 함께 남긴다."""

    success_noninferior: bool
    primary_metric_improved: bool
    negative_transfer_absent: bool
    safety_clean: bool
    duplicate_dispatch_absent: bool
    passed: bool
    claim_scope: str
    confirmatory_sample_size_registered: bool
    reasons: tuple[str, ...]

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "success_noninferior": self.success_noninferior,
            "primary_metric_improved": self.primary_metric_improved,
            "negative_transfer_absent": self.negative_transfer_absent,
            "safety_clean": self.safety_clean,
            "duplicate_dispatch_absent": self.duplicate_dispatch_absent,
            "passed": self.passed,
            "claim_scope": self.claim_scope,
            "confirmatory_sample_size_registered": self.confirmatory_sample_size_registered,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True, slots=True)
class LivePilotReport:
    """live pilot artifact. fixture artifact와 절대 합치지 않는다."""

    status: LivePilotStatus
    reason: str
    spec_digest: str
    spec_run_kind: RunKind
    provider: ProviderAttestation | None
    plan: LivePilotPlan | None
    arms: Mapping[str, LiveArmSummary]
    order_effect: Mapping[str, float]
    verdict: LivePilotVerdict | None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    pre_registration: PilotPreRegistration | None = None
    ledger: tuple[TrialLedgerEntry, ...] = ()

    @property
    def run_kind(self) -> RunKind:
        return RunKind.LIVE_PILOT

    @property
    def has_numbers(self) -> bool:
        return bool(self.arms)

    @property
    def reproducibility_limited(self) -> bool:
        return self.provider is not None and not self.provider.snapshot_pinned

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "run_kind": self.run_kind.value,
            "status": self.status.value,
            "reason": self.reason,
            "spec_digest": self.spec_digest,
            "spec_run_kind": self.spec_run_kind.value,
            "provider_attestation": self.provider.as_mapping() if self.provider else None,
            "plan": self.plan.as_mapping() if self.plan else None,
            "arms": {key: value.as_mapping() for key, value in sorted(self.arms.items())},
            "order_effect": dict(self.order_effect),
            "verdict": self.verdict.as_mapping() if self.verdict else None,
            "reproducibility_limited": self.reproducibility_limited,
            "mixed_with_fixture": False,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "pre_registration": self.pre_registration.as_mapping() if self.pre_registration else None,
            "ledger": [entry.as_mapping() for entry in self.ledger],
        }

    def to_json(self) -> str:
        return json.dumps(self.as_mapping(), ensure_ascii=False, indent=2, sort_keys=True, default=str)

    def digest(self) -> str:
        payload = json.dumps(self.as_mapping(), sort_keys=True, separators=(",", ":"), default=str)
        return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def assert_live_artifact(artifact: Mapping[str, object]) -> None:
    """live가 아닌 artifact를 live로 승격하려는 시도를 거부한다."""

    kind = str(artifact.get("run_kind", ""))
    if kind != RunKind.LIVE_PILOT.value:
        raise FixtureLiveMixError(
            f"{kind or 'run_kind 없음'} artifact는 live 결과가 아니다 — fixture를 live 성능으로 주장하지 않는다"
        )
    if artifact.get("mixed_with_fixture") is True:
        raise FixtureLiveMixError("fixture와 합쳐진 artifact는 live 증거가 아니다")


def merge_reports(*artifacts: Mapping[str, object]) -> Mapping[str, object]:
    """같은 run_kind의 report만 병합한다. kind가 섞이면 거부한다."""

    if not artifacts:
        raise FixtureLiveMixError("병합할 report가 없다")
    kinds = {str(artifact.get("run_kind", "")) for artifact in artifacts}
    if len(kinds) != 1:
        raise FixtureLiveMixError(
            f"run_kind가 다른 report는 병합하지 않는다: {sorted(kinds)} — fixture와 live 결과는 분리 보고한다"
        )
    if RunKind.LIVE_PILOT.value in kinds:
        for artifact in artifacts:
            assert_live_artifact(artifact)
    return {"run_kind": kinds.pop(), "reports": list(artifacts)}


@dataclass(frozen=True, slots=True)
class PilotPreRegistration:
    """실험 시작 전 고정하는 공개 등록 schema (C08)."""

    corpus_digest: str
    split: str
    task_ids: tuple[str, ...]
    task_families: Mapping[str, str]
    content_digests: Mapping[str, str]
    seed: int
    arm_order_policy: str
    primary_metric: str
    safety_metric: str
    mechanism_flags: Mapping[str, bool]
    model_digest: str
    code_fingerprint: str
    hardware: str
    budget_calls: int | None
    budget_tokens: int | None
    trials_per_task: int

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "corpus_digest": self.corpus_digest,
            "split": self.split,
            "task_ids": list(self.task_ids),
            "task_families": dict(self.task_families),
            "content_digests": dict(self.content_digests),
            "seed": self.seed,
            "arm_order_policy": self.arm_order_policy,
            "primary_metric": self.primary_metric,
            "safety_metric": self.safety_metric,
            "mechanism_flags": dict(self.mechanism_flags),
            "model_digest": self.model_digest,
            "code_fingerprint": self.code_fingerprint,
            "hardware": self.hardware,
            "budget_calls": self.budget_calls,
            "budget_tokens": self.budget_tokens,
            "trials_per_task": self.trials_per_task,
        }


@dataclass(frozen=True, slots=True)
class TrialLedgerEntry:
    """append-only 원시 trial 기록. 비밀 prompt는 넣지 않는다."""

    run_id: str
    trial_uid: str
    task_id: str
    arm: str
    repetition: int
    order: str
    status: str
    started_at: str | None
    finished_at: str | None
    outcome: Mapping[str, object] | None
    error_category: str = ""
    policy_version: str | None = None
    mechanism_flags: Mapping[str, bool] = field(default_factory=dict)

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "run_id": self.run_id,
            "trial_uid": self.trial_uid,
            "task_id": self.task_id,
            "arm": self.arm,
            "repetition": self.repetition,
            "order": self.order,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "outcome": dict(self.outcome) if self.outcome else None,
            "error_category": self.error_category,
            "policy_version": self.policy_version,
            "mechanism_flags": dict(self.mechanism_flags),
        }


@dataclass
class RawTrialLedger:
    """시작·완료·실패를 순서대로 남긴다. 집계는 이 목록만으로 재계산 가능해야 한다."""

    entries: list[TrialLedgerEntry] = field(default_factory=list)

    def append(self, entry: TrialLedgerEntry) -> None:
        self.entries.append(entry)

    def as_mapping(self) -> Mapping[str, object]:
        return {"entries": [entry.as_mapping() for entry in self.entries]}

    def completed_outcomes(self) -> list[tuple[TrialLedgerEntry, LiveTrialOutcome]]:
        rows: list[tuple[TrialLedgerEntry, LiveTrialOutcome]] = []
        for entry in self.entries:
            if entry.status != TrialEventStatus.COMPLETED.value or not entry.outcome:
                continue
            payload = entry.outcome
            rows.append(
                (
                    entry,
                    LiveTrialOutcome(
                        success=bool(payload["success"]),
                        retries=_as_int(payload["retries"]),
                        tool_calls=_as_int(payload["tool_calls"]),
                        brain_calls=_as_int(payload["brain_calls"]),
                        tokens=_as_int(payload["tokens"]),
                        latency_ms=_as_float(payload["latency_ms"]),
                        duplicate_dispatch=bool(payload.get("duplicate_dispatch", False)),
                        safety_violation=str(payload.get("safety_violation", "")),
                        detail=str(payload.get("detail", "")),
                        error_category=str(payload.get("error_category", "")),
                    ),
                )
            )
        return rows


def _as_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        return int(value)
    if value is None:
        return default
    return int(str(value))


def _as_float(value: object, default: float = 0.0) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str) and value.strip():
        return float(value)
    if value is None:
        return default
    return float(str(value))


def _as_str_bool_map(value: object) -> dict[str, bool]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return {str(k): bool(v) for k, v in value.items()}
    raise TypeError(f"expected mapping, got {type(value).__name__}")


def _task_content_digest(task: GrowthTask) -> str:
    payload = json.dumps(
        {
            "goal": task.goal_name,
            "required": list(task.required_items),
            "store": list(task.store_items),
            "category": task.category.value if hasattr(task.category, "value") else str(task.category),
            "append": task.append_content,
            "expected": task.expected_outcome,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _mechanism_flags(mechanisms: MechanismSet) -> dict[str, bool]:
    raw = mechanisms.as_mapping() if hasattr(mechanisms, "as_mapping") else {}
    if not isinstance(raw, Mapping):
        raw = {}
    return {str(key): bool(value) for key, value in sorted(raw.items())}


def validate_live_pilot_inputs(
    *,
    spec: BenchmarkSpec,
    plan: LivePilotPlan,
    tasks: Sequence[GrowthTask],
    all_corpus: Sequence[GrowthTask],
) -> None:
    """첫 provider 호출 전에 입력 계약을 검사한다. 실패 시 GrowthBenchmarkError."""

    import math

    if plan.order_policy not in SUPPORTED_ORDER_POLICIES:
        raise GrowthBenchmarkError(f"unsupported order_policy: {plan.order_policy}")
    if spec.primary_improvement_metric not in SUPPORTED_PRIMARY_METRICS:
        raise GrowthBenchmarkError(f"unsupported primary metric: {spec.primary_improvement_metric}")
    if not isinstance(plan.trials_per_task, int) or plan.trials_per_task < 0:
        raise GrowthBenchmarkError("trials_per_task must be a nonnegative int")
    if plan.trials_per_task != plan.trials_per_task or (
        isinstance(plan.trials_per_task, float) and math.isnan(plan.trials_per_task)
    ):
        raise GrowthBenchmarkError("trials_per_task is not finite")
    for label, value in (
        ("budget_calls", plan.budget_calls),
        ("budget_tokens", plan.budget_tokens),
        ("seed", plan.seed),
        ("confirmatory_sample_size", plan.confirmatory_sample_size),
    ):
        if value is None:
            continue
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            raise GrowthBenchmarkError(f"{label} is not finite")
        if isinstance(value, (int, float)) and value < 0:
            raise GrowthBenchmarkError(f"{label} must be nonnegative")

    # split ID / content / family leakage across TRAIN / VALIDATION / FINAL
    by_split: dict[str, list[GrowthTask]] = {}
    for task in all_corpus:
        by_split.setdefault(task.split.value, []).append(task)
    id_sets = {name: {task.task_id for task in group} for name, group in by_split.items()}
    names = sorted(id_sets)
    for i, left in enumerate(names):
        for right in names[i + 1 :]:
            overlap = id_sets[left] & id_sets[right]
            if overlap:
                raise GrowthBenchmarkError(f"overlap split task IDs between {left} and {right}: {sorted(overlap)[:5]}")
    digests: dict[str, set[str]] = {}
    families: dict[str, set[str]] = {}
    for name, group in by_split.items():
        digests[name] = {_task_content_digest(task) for task in group}
        families[name] = {
            (task.category.value if hasattr(task.category, "value") else str(task.category)) for task in group
        }
    train_d = digests.get(SplitRole.TRAIN.value, set())
    for held in (SplitRole.VALIDATION.value, SplitRole.FINAL.value):
        leak = train_d & digests.get(held, set())
        if leak:
            raise GrowthBenchmarkError(f"TRAIN content digest leaks into {held}: {len(leak)} item(s)")

    if not tasks:
        raise GrowthBenchmarkError(f"{plan.split.value} split에 task가 없다")


def build_pre_registration(
    *,
    spec: BenchmarkSpec,
    plan: LivePilotPlan,
    tasks: Sequence[GrowthTask],
    mechanisms: MechanismSet,
    attestation: ProviderAttestation | None,
) -> PilotPreRegistration:
    return PilotPreRegistration(
        corpus_digest=spec.corpus_digest,
        split=plan.split.value,
        task_ids=tuple(task.task_id for task in tasks),
        task_families={
            task.task_id: (task.category.value if hasattr(task.category, "value") else str(task.category))
            for task in tasks
        },
        content_digests={task.task_id: _task_content_digest(task) for task in tasks},
        seed=plan.seed,
        arm_order_policy=plan.order_policy,
        primary_metric=spec.primary_improvement_metric,
        safety_metric="safety_violation",
        mechanism_flags=_mechanism_flags(mechanisms),
        model_digest=(
            f"{attestation.provider_id}:{attestation.model_id}:{attestation.model_snapshot}" if attestation else ""
        ),
        code_fingerprint=plan.code_fingerprint,
        hardware=attestation.hardware if attestation else "",
        budget_calls=plan.budget_calls,
        budget_tokens=plan.budget_tokens,
        trials_per_task=plan.trials_per_task,
    )


class LivePilotHarness:
    """주입된 port로만 실행한다. port가 없으면 NOT_RUN이며 수치를 만들지 않는다."""

    def __init__(
        self,
        spec: BenchmarkSpec,
        plan: LivePilotPlan,
        *,
        tasks: Sequence[GrowthTask],
        mechanisms: MechanismSet | None = None,
    ) -> None:
        if not same_enum(spec.run_kind, RunKind.LIVE_PILOT):
            raise GrowthBenchmarkError(
                "deterministic fixture spec으로 live pilot를 실행하지 않는다 — live는 별도 등록 spec이 필요하다"
            )
        if plan.trials_per_task < spec.live_pilot_min_trials:
            raise GrowthBenchmarkError(
                f"paired trial이 부족하다: {plan.trials_per_task} < 최소 {spec.live_pilot_min_trials}"
            )
        self.spec = spec
        self.plan = plan
        self.all_corpus = tuple(tasks)
        self.tasks = tuple(task for task in tasks if task.split is plan.split)
        if not self.tasks:
            raise GrowthBenchmarkError(f"{plan.split.value} split에 task가 없다")
        self.mechanisms = mechanisms if mechanisms is not None else MechanismSet()
        validate_live_pilot_inputs(
            spec=self.spec,
            plan=self.plan,
            tasks=self.tasks,
            all_corpus=self.all_corpus,
        )

    # ── 실행 ─────────────────────────────────────────
    def run(self, port: LiveTrialPort | None) -> LivePilotReport:
        if port is None:
            return self._not_run("live provider port가 주입되지 않았다 — fixture 결과로 대체하지 않는다(NOT_RUN)")
        attestation = port.attestation
        prereg = build_pre_registration(
            spec=self.spec,
            plan=self.plan,
            tasks=self.tasks,
            mechanisms=self.mechanisms,
            attestation=attestation,
        )
        if not attestation.snapshot_pinned and not attestation.reproducibility_limits:
            return LivePilotReport(
                status=LivePilotStatus.INVALID,
                reason=(
                    "model snapshot이 고정되지 않았는데 reproducibility 제한 사유도 없다"
                    " — 제한을 기록할 수 없는 실행은 증거가 아니다"
                ),
                spec_digest=self.spec.digest(),
                spec_run_kind=self.spec.run_kind,
                provider=attestation,
                plan=self.plan,
                arms={},
                order_effect={},
                verdict=None,
                pre_registration=prereg,
                ledger=(),
            )
        started = datetime.now(tz=UTC)
        run_id = f"live-pilot:{self.spec.digest()}:{started.isoformat()}"
        ledger = RawTrialLedger()
        trials, incomplete_reason = self._collect(port, run_id=run_id, ledger=ledger)
        finished = datetime.now(tz=UTC)
        summaries = {arm.value: self._summarize(arm, trials[arm]) for arm in PILOT_ARMS if trials[arm]}
        verdict = self._verdict(summaries, attestation) if len(summaries) == len(PILOT_ARMS) else None
        if incomplete_reason:
            status = LivePilotStatus.NOT_COMPLETE
            reason = incomplete_reason
        else:
            status = LivePilotStatus.COMPLETED
            reason = (
                "pilot 실행 완료 — 확증 표본이 아니며 fixture 결과와 분리 보고한다"
                if not attestation.snapshot_pinned
                else "pilot 실행 완료 — 확증 표본이 아니다(확증 표본 크기는 별도 등록)"
            )
        return LivePilotReport(
            status=status,
            reason=reason,
            spec_digest=self.spec.digest(),
            spec_run_kind=self.spec.run_kind,
            provider=attestation,
            plan=self.plan,
            arms=summaries,
            order_effect=self._order_effect(trials) if all(trials[arm] for arm in PILOT_ARMS) else {},
            verdict=verdict,
            started_at=started,
            finished_at=finished,
            pre_registration=prereg,
            ledger=tuple(ledger.entries),
        )

    def _not_run(self, reason: str) -> LivePilotReport:
        return LivePilotReport(
            status=LivePilotStatus.NOT_RUN,
            reason=reason,
            spec_digest=self.spec.digest(),
            spec_run_kind=self.spec.run_kind,
            provider=None,
            plan=self.plan,
            arms={},
            order_effect={},
            verdict=None,
        )

    def _collect(
        self,
        port: LiveTrialPort,
        *,
        run_id: str,
        ledger: RawTrialLedger,
    ) -> tuple[Mapping[ArmRole, list[tuple[LiveTrialRequest, LiveTrialOutcome]]], str | None]:
        collected: dict[ArmRole, list[tuple[LiveTrialRequest, LiveTrialOutcome]]] = {arm: [] for arm in PILOT_ARMS}
        flags = _mechanism_flags(self.mechanisms)
        calls_used = 0
        tokens_used = 0
        for trial_index in range(self.plan.trials_per_task):
            order = TrialOrder.FRESH_FIRST if trial_index % 2 == 0 else TrialOrder.MATURE_FIRST
            for task in self.tasks:
                for arm in self._arm_order(order):
                    if self.plan.budget_calls is not None and calls_used >= self.plan.budget_calls:
                        return collected, "budget_calls exhausted before remaining trials — NOT_COMPLETE"
                    trial_uid = f"{run_id}:{task.task_id}:{arm.value}:{trial_index}"
                    request = LiveTrialRequest(
                        task_id=task.task_id,
                        split=task.split.value,
                        arm=arm,
                        trial_index=trial_index,
                        order=order,
                        policy_version=self.plan.policy_version if same_enum(arm, ArmRole.MATURE) else None,
                        advisory_refs=self.plan.advisory_refs if same_enum(arm, ArmRole.MATURE) else (),
                        mechanism_flags=flags,
                        seed=self.plan.seed,
                        run_id=run_id,
                        trial_uid=trial_uid,
                    )
                    started_at = datetime.now(tz=UTC).isoformat()
                    ledger.append(
                        TrialLedgerEntry(
                            run_id=run_id,
                            trial_uid=trial_uid,
                            task_id=task.task_id,
                            arm=arm.value,
                            repetition=trial_index,
                            order=order.value,
                            status=TrialEventStatus.STARTED.value,
                            started_at=started_at,
                            finished_at=None,
                            outcome=None,
                            policy_version=request.policy_version,
                            mechanism_flags=flags,
                        )
                    )
                    try:
                        outcome = port.run_trial(request)
                    except LiveTrialTimeout as exc:
                        finished_at = datetime.now(tz=UTC).isoformat()
                        ledger.append(
                            TrialLedgerEntry(
                                run_id=run_id,
                                trial_uid=trial_uid,
                                task_id=task.task_id,
                                arm=arm.value,
                                repetition=trial_index,
                                order=order.value,
                                status=TrialEventStatus.TIMEOUT.value,
                                started_at=started_at,
                                finished_at=finished_at,
                                outcome=None,
                                error_category="TIMEOUT",
                                policy_version=request.policy_version,
                                mechanism_flags=flags,
                            )
                        )
                        return collected, f"trial timeout at {trial_uid}: {exc} — NOT_COMPLETE"
                    except LiveTrialBudgetExhausted as exc:
                        finished_at = datetime.now(tz=UTC).isoformat()
                        ledger.append(
                            TrialLedgerEntry(
                                run_id=run_id,
                                trial_uid=trial_uid,
                                task_id=task.task_id,
                                arm=arm.value,
                                repetition=trial_index,
                                order=order.value,
                                status=TrialEventStatus.BUDGET_EXHAUSTED.value,
                                started_at=started_at,
                                finished_at=finished_at,
                                outcome=None,
                                error_category="BUDGET_EXHAUSTED",
                                policy_version=request.policy_version,
                                mechanism_flags=flags,
                            )
                        )
                        return collected, f"budget exhausted at {trial_uid}: {exc} — NOT_COMPLETE"
                    except Exception as exc:  # noqa: BLE001 — partial ledger must preserve failure
                        finished_at = datetime.now(tz=UTC).isoformat()
                        ledger.append(
                            TrialLedgerEntry(
                                run_id=run_id,
                                trial_uid=trial_uid,
                                task_id=task.task_id,
                                arm=arm.value,
                                repetition=trial_index,
                                order=order.value,
                                status=TrialEventStatus.FAILED.value,
                                started_at=started_at,
                                finished_at=finished_at,
                                outcome=None,
                                error_category=type(exc).__name__,
                                policy_version=request.policy_version,
                                mechanism_flags=flags,
                            )
                        )
                        return collected, f"trial failed at {trial_uid}: {type(exc).__name__} — NOT_COMPLETE"
                    finished_at = datetime.now(tz=UTC).isoformat()
                    calls_used += 1
                    tokens_used += int(outcome.tokens)
                    if self.plan.budget_tokens is not None and tokens_used > self.plan.budget_tokens:
                        ledger.append(
                            TrialLedgerEntry(
                                run_id=run_id,
                                trial_uid=trial_uid,
                                task_id=task.task_id,
                                arm=arm.value,
                                repetition=trial_index,
                                order=order.value,
                                status=TrialEventStatus.BUDGET_EXHAUSTED.value,
                                started_at=started_at,
                                finished_at=finished_at,
                                outcome=outcome.as_mapping(),
                                error_category="BUDGET_EXHAUSTED",
                                policy_version=request.policy_version,
                                mechanism_flags=flags,
                            )
                        )
                        collected[arm].append((request, outcome))
                        return collected, f"budget_tokens exceeded at {trial_uid} — NOT_COMPLETE"
                    ledger.append(
                        TrialLedgerEntry(
                            run_id=run_id,
                            trial_uid=trial_uid,
                            task_id=task.task_id,
                            arm=arm.value,
                            repetition=trial_index,
                            order=order.value,
                            status=TrialEventStatus.COMPLETED.value,
                            started_at=started_at,
                            finished_at=finished_at,
                            outcome=outcome.as_mapping(),
                            policy_version=request.policy_version,
                            mechanism_flags=flags,
                        )
                    )
                    collected[arm].append((request, outcome))
        return collected, None

    @staticmethod
    def _arm_order(order: TrialOrder) -> tuple[ArmRole, ...]:
        return PILOT_ARMS if same_enum(order, TrialOrder.FRESH_FIRST) else tuple(reversed(PILOT_ARMS))

    def _summarize(self, arm: ArmRole, trials: Sequence[tuple[LiveTrialRequest, LiveTrialOutcome]]) -> LiveArmSummary:
        if not trials:
            raise GrowthBenchmarkError(f"{arm.value} arm에 trial이 없다")
        outcomes = [outcome for _, outcome in trials]
        negative_ids = {task.task_id for task in self.tasks if task.negative_transfer}
        statuses: dict[str, int] = {}
        for _, outcome in trials:
            key = "success" if outcome.success else "failure"
            statuses[key] = statuses.get(key, 0) + 1
        return LiveArmSummary(
            arm=arm,
            trials=len(outcomes),
            success_rate=Distribution.of([1.0 if outcome.success else 0.0 for outcome in outcomes]),
            retries=Distribution.of([outcome.retries for outcome in outcomes]),
            tool_calls=Distribution.of([outcome.tool_calls for outcome in outcomes]),
            latency_ms=Distribution.of([outcome.latency_ms for outcome in outcomes]),
            tokens=Distribution.of([outcome.tokens for outcome in outcomes]),
            negative_transfer_successes=sum(
                1 for request, outcome in trials if request.task_id in negative_ids and outcome.success
            ),
            duplicate_dispatches=sum(1 for outcome in outcomes if outcome.duplicate_dispatch),
            safety_violations=tuple(
                f"{request.task_id}: {outcome.safety_violation}"
                for request, outcome in trials
                if outcome.safety_violation
            ),
            outcome_statuses=dict(sorted(statuses.items())),
        )

    def _order_effect(
        self, trials: Mapping[ArmRole, list[tuple[LiveTrialRequest, LiveTrialOutcome]]]
    ) -> Mapping[str, float]:
        effect: dict[str, float] = {}
        for arm in PILOT_ARMS:
            rows = trials[arm]
            for order in TrialOrder:
                values = [outcome.retries for request, outcome in rows if request.order is order]
                if values:
                    effect[f"{arm.value}:{order.value}:mean_retries"] = sum(values) / len(values)
                    effect[f"{arm.value}:{order.value}:trials"] = float(len(values))
        first = effect.get(f"{ArmRole.MATURE.value}:{TrialOrder.FRESH_FIRST.value}:mean_retries")
        second = effect.get(f"{ArmRole.MATURE.value}:{TrialOrder.MATURE_FIRST.value}:mean_retries")
        if first is not None and second is not None:
            effect["MATURE:order_gap"] = abs(first - second)
        return dict(sorted(effect.items()))

    def _verdict(self, summaries: Mapping[str, LiveArmSummary], attestation: ProviderAttestation) -> LivePilotVerdict:
        fresh = summaries[ArmRole.FRESH.value]
        mature = summaries[ArmRole.MATURE.value]
        reasons: list[str] = []
        success_noninferior = (
            mature.success_rate.mean >= fresh.success_rate.mean - self.spec.success_noninferiority_margin
        )
        if not success_noninferior:
            reasons.append(f"success 비열등 실패: {mature.success_rate.mean:.3f} < {fresh.success_rate.mean:.3f}")
        field_name, lower_better = PRIMARY_METRIC_FIELDS[self.spec.primary_improvement_metric]
        summary_attr = field_name  # LiveArmSummary field matches outcome attr
        mature_metric = getattr(mature, summary_attr).mean
        fresh_metric = getattr(fresh, summary_attr).mean
        primary_improved = (mature_metric < fresh_metric) if lower_better else (mature_metric > fresh_metric)
        if not primary_improved:
            reasons.append(
                f"{self.spec.primary_improvement_metric} 개선 없음: {mature_metric:.3f} vs {fresh_metric:.3f}"
            )
        negative_transfer_absent = mature.negative_transfer_successes >= fresh.negative_transfer_successes
        if not negative_transfer_absent:
            reasons.append("negative transfer: mature가 labelled task에서 더 실패했다")
        fresh_safe = not fresh.safety_violations
        mature_safe = not mature.safety_violations
        safety_clean = fresh_safe and mature_safe
        if not fresh_safe:
            reasons.append(f"fresh safety violation {len(fresh.safety_violations)}건")
        if not mature_safe:
            reasons.append(f"mature safety violation {len(mature.safety_violations)}건")
        duplicate_absent = mature.duplicate_dispatches == 0 and fresh.duplicate_dispatches == 0
        if not duplicate_absent:
            reasons.append(
                f"duplicate dispatch fresh={fresh.duplicate_dispatches} mature={mature.duplicate_dispatches}"
            )
        if self.plan.confirmatory_sample_size is None:
            reasons.append("확증 표본 크기가 등록되지 않았다 — 이 결과는 pilot이며 확증이 아니다")
        if not attestation.snapshot_pinned:
            reasons.append("model snapshot 미고정 — reproducibility 제한을 함께 보고한다")
        passed = all((success_noninferior, primary_improved, negative_transfer_absent, safety_clean, duplicate_absent))
        return LivePilotVerdict(
            success_noninferior=success_noninferior,
            primary_metric_improved=primary_improved,
            negative_transfer_absent=negative_transfer_absent,
            safety_clean=safety_clean,
            duplicate_dispatch_absent=duplicate_absent,
            passed=passed,
            claim_scope=CLAIM_SCOPE_PILOT if attestation.snapshot_pinned else CLAIM_SCOPE_LIMITED,
            confirmatory_sample_size_registered=self.plan.confirmatory_sample_size is not None,
            reasons=tuple(reasons),
        )


def aggregate_from_ledger(
    ledger_entries: Sequence[TrialLedgerEntry] | Sequence[Mapping[str, object]],
    *,
    spec: BenchmarkSpec,
    plan: LivePilotPlan,
    tasks: Sequence[GrowthTask],
    attestation: ProviderAttestation,
) -> tuple[Mapping[str, LiveArmSummary], LivePilotVerdict | None]:
    """원시 ledger만으로 arm 요약·verdict를 재계산한다 (R17-A4)."""

    normalized: list[TrialLedgerEntry] = []
    for item in ledger_entries:
        if isinstance(item, TrialLedgerEntry):
            normalized.append(item)
        else:
            normalized.append(
                TrialLedgerEntry(
                    run_id=str(item["run_id"]),
                    trial_uid=str(item["trial_uid"]),
                    task_id=str(item["task_id"]),
                    arm=str(item["arm"]),
                    repetition=_as_int(item["repetition"]),
                    order=str(item["order"]),
                    status=str(item["status"]),
                    started_at=item.get("started_at"),  # type: ignore[arg-type]
                    finished_at=item.get("finished_at"),  # type: ignore[arg-type]
                    outcome=item.get("outcome"),  # type: ignore[arg-type]
                    error_category=str(item.get("error_category") or ""),
                    policy_version=item.get("policy_version"),  # type: ignore[arg-type]
                    mechanism_flags=_as_str_bool_map(item.get("mechanism_flags")),
                )
            )

    collected: dict[ArmRole, list[tuple[LiveTrialRequest, LiveTrialOutcome]]] = {arm: [] for arm in PILOT_ARMS}
    for entry in normalized:
        if entry.status != TrialEventStatus.COMPLETED.value or not entry.outcome:
            continue
        arm = ArmRole(entry.arm)
        payload = entry.outcome
        request = LiveTrialRequest(
            task_id=entry.task_id,
            split=plan.split.value,
            arm=arm,
            trial_index=entry.repetition,
            order=TrialOrder(entry.order),
            policy_version=entry.policy_version,
            advisory_refs=(),
            mechanism_flags=dict(entry.mechanism_flags),
            seed=plan.seed,
            run_id=entry.run_id,
            trial_uid=entry.trial_uid,
        )
        outcome = LiveTrialOutcome(
            success=bool(payload["success"]),
            retries=_as_int(payload["retries"]),
            tool_calls=_as_int(payload["tool_calls"]),
            brain_calls=_as_int(payload["brain_calls"]),
            tokens=_as_int(payload["tokens"]),
            latency_ms=_as_float(payload["latency_ms"]),
            duplicate_dispatch=bool(payload.get("duplicate_dispatch", False)),
            safety_violation=str(payload.get("safety_violation", "")),
            detail=str(payload.get("detail", "")),
            error_category=str(payload.get("error_category", "")),
        )
        collected[arm].append((request, outcome))

    if not all(collected[arm] for arm in PILOT_ARMS):
        return {}, None

    harness = LivePilotHarness(spec, plan, tasks=tasks)
    summaries = {arm.value: harness._summarize(arm, collected[arm]) for arm in PILOT_ARMS}
    return summaries, harness._verdict(summaries, attestation)


@dataclass(frozen=True, slots=True)
class RegisteredExperimentManifest:
    """실행 전 freeze. FINAL 결과를 보고 task/metric을 바꾸면 안 된다 (R19-A1)."""

    pre_registration: PilotPreRegistration
    independent_task_count: int
    planned_trial_slots: int
    analysis_unit: str  # "task" | "family" — never inflate reps as independent samples

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "pre_registration": self.pre_registration.as_mapping(),
            "independent_task_count": self.independent_task_count,
            "planned_trial_slots": self.planned_trial_slots,
            "analysis_unit": self.analysis_unit,
        }


@dataclass(frozen=True, slots=True)
class RegisteredExperimentResult:
    manifest: RegisteredExperimentManifest
    report: LivePilotReport
    recalculated_verdict: LivePilotVerdict | None
    ledger_gaps: tuple[str, ...]
    independent_task_ids: tuple[str, ...]
    unfavorable_preserved: bool

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "manifest": self.manifest.as_mapping(),
            "report": self.report.as_mapping(),
            "recalculated_verdict": self.recalculated_verdict.as_mapping() if self.recalculated_verdict else None,
            "ledger_gaps": list(self.ledger_gaps),
            "independent_task_ids": list(self.independent_task_ids),
            "unfavorable_preserved": self.unfavorable_preserved,
        }


def freeze_registered_manifest(
    *,
    spec: BenchmarkSpec,
    plan: LivePilotPlan,
    tasks: Sequence[GrowthTask],
    mechanisms: MechanismSet,
    attestation: ProviderAttestation | None,
) -> RegisteredExperimentManifest:
    split_tasks = tuple(task for task in tasks if task.split is plan.split)
    prereg = build_pre_registration(
        spec=spec,
        plan=plan,
        tasks=split_tasks,
        mechanisms=mechanisms,
        attestation=attestation,
    )
    # slots = tasks × trials × 2 arms (paired)
    slots = len(split_tasks) * plan.trials_per_task * len(PILOT_ARMS)
    return RegisteredExperimentManifest(
        pre_registration=prereg,
        independent_task_count=len(split_tasks),
        planned_trial_slots=slots,
        analysis_unit="task",
    )


def assert_manifest_unchanged(
    frozen: RegisteredExperimentManifest,
    report: LivePilotReport,
) -> None:
    """FINAL 결과를 본 뒤 task/metric을 바꾸면 GrowthBenchmarkError."""

    if report.pre_registration is None:
        raise GrowthBenchmarkError("report missing pre_registration — cannot verify freeze")
    before = frozen.pre_registration
    after = report.pre_registration
    if before.task_ids != after.task_ids:
        raise GrowthBenchmarkError("task_ids changed after run — registered experiment violated freeze")
    if before.primary_metric != after.primary_metric:
        raise GrowthBenchmarkError("primary_metric changed after run — registered experiment violated freeze")
    if before.corpus_digest != after.corpus_digest:
        raise GrowthBenchmarkError("corpus_digest changed after run")
    if before.arm_order_policy != after.arm_order_policy:
        raise GrowthBenchmarkError("arm_order_policy changed after run")


def validate_ledger_trial_closure(ledger: Sequence[TrialLedgerEntry]) -> tuple[str, ...]:
    """모든 trial_uid는 STARTED와 terminal(COMPLETED|TIMEOUT|FAILED|BUDGET_EXHAUSTED)을 가져야 한다."""

    terminal = {
        TrialEventStatus.COMPLETED.value,
        TrialEventStatus.TIMEOUT.value,
        TrialEventStatus.FAILED.value,
        TrialEventStatus.BUDGET_EXHAUSTED.value,
    }
    by_uid: dict[str, set[str]] = {}
    for entry in ledger:
        by_uid.setdefault(entry.trial_uid, set()).add(entry.status)
    gaps: list[str] = []
    for uid, statuses in sorted(by_uid.items()):
        if TrialEventStatus.STARTED.value not in statuses:
            gaps.append(f"{uid}: missing STARTED")
        if not (statuses & terminal):
            gaps.append(f"{uid}: missing terminal status")
    return tuple(gaps)


def independent_task_ids_from_ledger(ledger: Sequence[TrialLedgerEntry]) -> tuple[str, ...]:
    """반복 trial을 독립 표본으로 부풀리지 않는다 — unique task_id만."""

    return tuple(dict.fromkeys(entry.task_id for entry in ledger))


def run_registered_live_experiment(
    harness: LivePilotHarness,
    port: LiveTrialPort | None,
    *,
    attestation_for_freeze: ProviderAttestation | None = None,
) -> RegisteredExperimentResult:
    """등록 manifest freeze → 실행 → ledger 검증 → 독립 재계산. 불리한 verdict도 보존."""

    attestation = attestation_for_freeze
    if attestation is None and port is not None:
        attestation = port.attestation
    frozen = freeze_registered_manifest(
        spec=harness.spec,
        plan=harness.plan,
        tasks=harness.all_corpus,
        mechanisms=harness.mechanisms,
        attestation=attestation,
    )
    report = harness.run(port)
    assert_manifest_unchanged(frozen, report)
    gaps = validate_ledger_trial_closure(report.ledger)
    tasks = independent_task_ids_from_ledger(report.ledger)
    recalc_verdict = None
    if report.ledger and port is not None and report.status is LivePilotStatus.COMPLETED:
        _, recalc_verdict = aggregate_from_ledger(
            report.ledger,
            spec=harness.spec,
            plan=harness.plan,
            tasks=harness.all_corpus,
            attestation=port.attestation,
        )
    unfavorable = False
    if report.verdict is not None and not report.verdict.passed:
        unfavorable = True
    if recalc_verdict is not None and not recalc_verdict.passed:
        unfavorable = True
    # unfavorable must remain visible on the report reasons / status
    unfavorable_preserved = unfavorable and (
        report.verdict is None
        or report.verdict.passed is False
        or any("개선 없음" in r or "safety" in r or "비열등" in r for r in report.verdict.reasons)
        or report.status is LivePilotStatus.NOT_COMPLETE
    )
    if not unfavorable:
        unfavorable_preserved = True  # N/A when result is favorable
    return RegisteredExperimentResult(
        manifest=frozen,
        report=report,
        recalculated_verdict=recalc_verdict,
        ledger_gaps=gaps,
        independent_task_ids=tasks,
        unfavorable_preserved=unfavorable_preserved,
    )


def live_pilot_tasks(tasks: Sequence[GrowthTask], plan: LivePilotPlan) -> tuple[GrowthTask, ...]:
    """pilot이 쓰는 held-out task. split 밖 task는 쓰지 않는다."""

    return tasks_for(tasks, plan.split)


__all__ = [
    "CLAIM_SCOPE_LIMITED",
    "CLAIM_SCOPE_PILOT",
    "PILOT_ARMS",
    "PRIMARY_METRIC_FIELDS",
    "SUPPORTED_ORDER_POLICIES",
    "SUPPORTED_PRIMARY_METRICS",
    "Distribution",
    "FixtureLiveMixError",
    "LiveArmSummary",
    "LivePilotHarness",
    "LivePilotPlan",
    "LivePilotReport",
    "LivePilotStatus",
    "LivePilotVerdict",
    "LiveTrialBudgetExhausted",
    "LiveTrialOutcome",
    "LiveTrialPort",
    "LiveTrialRequest",
    "LiveTrialTimeout",
    "PilotPreRegistration",
    "ProviderAttestation",
    "RawTrialLedger",
    "TrialEventStatus",
    "TrialLedgerEntry",
    "TrialOrder",
    "aggregate_from_ledger",
    "assert_manifest_unchanged",
    "freeze_registered_manifest",
    "independent_task_ids_from_ledger",
    "RegisteredExperimentManifest",
    "RegisteredExperimentResult",
    "run_registered_live_experiment",
    "validate_ledger_trial_closure",
    "assert_live_artifact",
    "build_pre_registration",
    "live_pilot_tasks",
    "merge_reports",
    "validate_live_pilot_inputs",
]
