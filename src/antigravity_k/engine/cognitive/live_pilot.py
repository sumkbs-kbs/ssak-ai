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


class TrialOrder(StrEnum):
    """순서 효과를 확인하기 위해 trial마다 교대한다."""

    FRESH_FIRST = "FRESH_FIRST"
    MATURE_FIRST = "MATURE_FIRST"


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

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "task_id": self.task_id,
            "split": self.split,
            "arm": self.arm.value,
            "trial_index": self.trial_index,
            "order": self.order.value,
            "policy_version": self.policy_version,
            "advisory_refs": list(self.advisory_refs),
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

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "trials_per_task": self.trials_per_task,
            "split": self.split.value,
            "order_policy": self.order_policy,
            "confirmatory_sample_size": self.confirmatory_sample_size,
            "policy_version": self.policy_version,
            "advisory_refs": list(self.advisory_refs),
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
        self.tasks = tuple(task for task in tasks if task.split is plan.split)
        if not self.tasks:
            raise GrowthBenchmarkError(f"{plan.split.value} split에 task가 없다")
        self.mechanisms = mechanisms if mechanisms is not None else MechanismSet()

    # ── 실행 ─────────────────────────────────────────
    def run(self, port: LiveTrialPort | None) -> LivePilotReport:
        if port is None:
            return self._not_run("live provider port가 주입되지 않았다 — fixture 결과로 대체하지 않는다(NOT_RUN)")
        attestation = port.attestation
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
            )
        started = datetime.now(tz=UTC)
        trials = self._collect(port)
        finished = datetime.now(tz=UTC)
        summaries = {arm.value: self._summarize(arm, trials[arm]) for arm in PILOT_ARMS}
        verdict = self._verdict(summaries, attestation)
        return LivePilotReport(
            status=LivePilotStatus.COMPLETED,
            reason=(
                "pilot 실행 완료 — 확증 표본이 아니며 fixture 결과와 분리 보고한다"
                if not attestation.snapshot_pinned
                else "pilot 실행 완료 — 확증 표본이 아니다(확증 표본 크기는 별도 등록)"
            ),
            spec_digest=self.spec.digest(),
            spec_run_kind=self.spec.run_kind,
            provider=attestation,
            plan=self.plan,
            arms=summaries,
            order_effect=self._order_effect(trials),
            verdict=verdict,
            started_at=started,
            finished_at=finished,
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

    def _collect(self, port: LiveTrialPort) -> Mapping[ArmRole, list[tuple[LiveTrialRequest, LiveTrialOutcome]]]:
        collected: dict[ArmRole, list[tuple[LiveTrialRequest, LiveTrialOutcome]]] = {arm: [] for arm in PILOT_ARMS}
        for trial_index in range(self.plan.trials_per_task):
            order = TrialOrder.FRESH_FIRST if trial_index % 2 == 0 else TrialOrder.MATURE_FIRST
            for task in self.tasks:
                for arm in self._arm_order(order):
                    request = LiveTrialRequest(
                        task_id=task.task_id,
                        split=task.split.value,
                        arm=arm,
                        trial_index=trial_index,
                        order=order,
                        policy_version=self.plan.policy_version if same_enum(arm, ArmRole.MATURE) else None,
                        advisory_refs=self.plan.advisory_refs if same_enum(arm, ArmRole.MATURE) else (),
                    )
                    collected[arm].append((request, port.run_trial(request)))
        return collected

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
        primary_improved = mature.retries.mean < fresh.retries.mean
        if not primary_improved:
            reasons.append(
                f"{self.spec.primary_improvement_metric} 개선 없음: {mature.retries.mean:.3f} >= {fresh.retries.mean:.3f}"
            )
        negative_transfer_absent = mature.negative_transfer_successes >= fresh.negative_transfer_successes
        if not negative_transfer_absent:
            reasons.append("negative transfer: mature가 labelled task에서 더 실패했다")
        safety_clean = not mature.safety_violations
        if not safety_clean:
            reasons.append(f"mature safety violation {len(mature.safety_violations)}건")
        duplicate_absent = mature.duplicate_dispatches == 0
        if not duplicate_absent:
            reasons.append(f"mature duplicate dispatch {mature.duplicate_dispatches}건")
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


def live_pilot_tasks(tasks: Sequence[GrowthTask], plan: LivePilotPlan) -> tuple[GrowthTask, ...]:
    """pilot이 쓰는 held-out task. split 밖 task는 쓰지 않는다."""

    return tasks_for(tasks, plan.split)


__all__ = [
    "CLAIM_SCOPE_LIMITED",
    "CLAIM_SCOPE_PILOT",
    "PILOT_ARMS",
    "Distribution",
    "FixtureLiveMixError",
    "LiveArmSummary",
    "LivePilotHarness",
    "LivePilotPlan",
    "LivePilotReport",
    "LivePilotStatus",
    "LivePilotVerdict",
    "LiveTrialOutcome",
    "LiveTrialPort",
    "LiveTrialRequest",
    "ProviderAttestation",
    "TrialOrder",
    "assert_live_artifact",
    "live_pilot_tasks",
    "merge_reports",
]
