"""Growth demonstration·paired benchmark (P10) — T13 계약.

BENCHMARK_AND_ABLATION.md 실행 보완 명세 구현:

- **사전 등록:** ``BenchmarkSpec``(corpus/split/metric/분모/측정 구간/표본 크기/비열등성 폭/negative transfer
  허용치)을 실행 전에 등록한다. 결과를 본 뒤 기준을 완화하지 않으며, 바꾸려면 새 experiment ID가 필요하다.
- **Fresh vs Mature:** 같은 brain/code/corpus를 쓰고 분리 저장 root에서 실행한다. Mature만 training split에서
  축적한 Experience와 validation을 통과한 policy를 사용한다.
- **성장 사슬:** EXPERIENCE → POLICY CHANGE → FUTURE BEHAVIOR CHANGE를 실제로 연결한다. 즉 train split에서
  누락을 관찰 → CONTEXT_DEPTH policy candidate → 별도 validation split 검증 → activation →
  FINAL held-out에서 selection 변화와 retry 감소를 관측한다.
- **deterministic demo ≠ live 성능:** 이 harness의 기본 실행은 fixture Brain을 쓰는 결정적 demo다. live pilot은
  실행하지 않으며 ``RunKind.LIVE_PILOT`` 결과를 fixture 결과로 대체하지 않는다.
- **ablation:** 6개 mechanism을 하나씩 끈다. 끈 mechanism이 mature 실행에서 실제로 쓰이지 않았다면 그 비교는
  ``NOT_RUN``이며 유효성 증거가 아니다. 권한·헌법 보호는 ablation 대상이 아니고, 없애도 기본 권한 검사는 유지된다.

이 모듈은 provider/UI/도구 계층을 import하지 않는다(architecture guard). 실제 파일 append·read는 caller가 주입한
``executor_factory``(adapter 계층에서 기존 ToolRegistry/ToolExecutor를 결선해 만든 ``ToolExecutorPort``)가 수행한다.

"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Final

from antigravity_k.engine.cognitive.actions import (
    ActionDispatcher,
    ActionIntent,
    ActionObservation,
    PolicyClearance,
    ToolExecutorPort,
)
from antigravity_k.engine.cognitive.authority import (
    AuthorityDecision,
    AuthorityVerdict,
)
from antigravity_k.engine.cognitive.context import (
    ContextBuilder,
    ContextBuildResult,
    ContextPrincipal,
)
from antigravity_k.engine.cognitive.experience import (
    DecisionEvaluation,
    EpisodeEvaluations,
    ExecutionEvaluation,
    OutcomeEvaluation,
)
from antigravity_k.engine.cognitive.governance import GovernanceGate, ReshapeGuard, reshape_plan
from antigravity_k.engine.cognitive.learning import (
    MIN_INDEPENDENT_EPISODES,
    CandidateKind,
    CandidateProposer,
    CandidateRequest,
    CandidateStore,
    EpisodeObservation,
    ExperienceEvaluator,
    HeldOutValidator,
    TriggerSource,
    ValidationCriterion,
    ValidationObservation,
    ValidationRole,
    ValidationSplit,
)
from antigravity_k.engine.cognitive.models import (
    ActionExecutionStatus,
    AuthorityDimension,
    CognitiveRequestType,
    ContextBudget,
    DisclosureLevel,
    EvidenceKind,
    EvidencePayload,
    ExperiencePayload,
    GoalPayload,
    GoalStatus,
    OutcomeStatus,
    PolicyTarget,
    Producer,
    ProducerKind,
    ProjectPayload,
    Provenance,
    Record,
    RiskLevel,
    RiskProfile,
    same_enum,
)
from antigravity_k.engine.cognitive.policy_store import PolicyStore
from antigravity_k.engine.cognitive.readiness import (
    ActionScope,
    EvidenceRef,
    GuardReceipt,
    HardConstraint,
    ReadinessInputs,
    ReadinessResult,
    check_readiness,
)
from antigravity_k.engine.cognitive.references import REL_EVIDENCE, EntityType, Reference, new_id
from antigravity_k.engine.cognitive.runtime import (
    CognitiveRequestEnvelope,
    CognitiveRuntime,
    EpisodeBudget,
    EpisodeDelta,
    EpisodePlan,
    EpisodeRequest,
    EpisodeTermination,
    RequestFeedback,
    ThinkOutcome,
    episode_records,
)
from antigravity_k.engine.cognitive.store import CanonicalStore

CORPUS_NAMESPACE: Final[uuid.UUID] = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")
DEFAULT_SEED: Final[int] = 20260922
DEFAULT_LIVE_PILOT_TRIALS: Final[int] = 3

#: fresh arm이 쓰는 기준 context 한계. 이 값이 성장 비교의 출발점이다.
BASELINE_CONTEXT_LIMITS: Final[Mapping[str, int]] = {"l1_limit": 2, "l2_limit": 0, "l3_limit": 0}
#: mature arm은 validation을 통과한 policy가 연 만큼만 더 깊게 본다(train split에서 관측한 evidence family 수).
MATURE_CONTEXT_STEP: Final[int] = 2

METRIC_TASK_SUCCESS: Final[str] = "task_success_rate"
METRIC_TOTAL_RETRIES: Final[str] = "total_retries"
METRIC_TOTAL_TOOL_CALLS: Final[str] = "total_tool_calls"
METRIC_BRAIN_CALLS: Final[str] = "brain_calls"
METRIC_CONTEXT_TOKENS: Final[str] = "context_injected_tokens"
METRIC_CONTEXT_POLLUTION: Final[str] = "context_pollution_ratio"
METRIC_LATENCY_P50: Final[str] = "latency_ms_p50"
METRIC_REOPEN: Final[str] = "reopen_count"
METRIC_FAILURE_REPETITION: Final[str] = "failure_repetition"
METRIC_EXPERIENCE_REUSE: Final[str] = "experience_reuse_count"
METRIC_GUARDED_SUCCESS: Final[str] = "guarded_success_count"
METRIC_NEGATIVE_TRANSFER: Final[str] = "negative_transfer_success_delta"

#: "N_A"로 보고해야 하는 metric의 사유(라벨 없는 context pollution 등).
NA_REASON_NO_LABELS: Final[str] = "사전 라벨이 없어 N_A로 보고한다"
NA_REASON_NOT_RUN: Final[str] = "해당 실행을 하지 않았다"


class SplitRole(StrEnum):
    TRAIN = "TRAIN"
    VALIDATION = "VALIDATION"
    FINAL = "FINAL"


class FixtureCategory(StrEnum):
    NORMAL = "NORMAL"
    UNKNOWN_CONFLICT = "UNKNOWN_CONFLICT"
    AUTHORITY_RESHAPE = "AUTHORITY_RESHAPE"
    RECOVERY = "RECOVERY"
    DRIFT_NEGATIVE_TRANSFER = "DRIFT_NEGATIVE_TRANSFER"


class Mode(StrEnum):
    FRESH = "fresh"
    MATURE = "mature"
    ABLATION = "ablation"


class RunKind(StrEnum):
    DETERMINISTIC_FIXTURE = "DETERMINISTIC_FIXTURE"
    LIVE_PILOT = "LIVE_PILOT"


class ArmRole(StrEnum):
    FRESH = "FRESH"
    MATURE = "MATURE"
    ABLATION = "ABLATION"


class Mechanism(StrEnum):
    """원문 §39의 6개 ablation 대상. 권한·헌법 보호는 여기에 없다."""

    CONTEXT_BUILDER = "CONTEXT_BUILDER"
    EXPERIENCE_ADVISORY = "EXPERIENCE_ADVISORY"
    TARGETED_REREASONING = "TARGETED_REREASONING"
    EXPERIENCE = "EXPERIENCE"
    RISK_SHAPING = "RISK_SHAPING"
    GOVERNANCE_LEARNING = "GOVERNANCE_LEARNING"


class AblationStatus(StrEnum):
    MEASURED = "MEASURED"
    NOT_RUN = "NOT_RUN"
    INVALID = "INVALID"


def canonical_id(prefix: str, name: str) -> str:
    """corpus 항목의 canonical ID를 이름에서 결정적으로 만든다."""

    return f"{prefix}:{uuid.uuid5(CORPUS_NAMESPACE, name)}"


@dataclass(frozen=True, slots=True)
class MetricSpec:
    """metric마다 분모·측정 구간·방향을 고정한다."""

    name: str
    unit: str
    denominator: str
    window: str
    direction: str

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "name": self.name,
            "unit": self.unit,
            "denominator": self.denominator,
            "window": self.window,
            "direction": self.direction,
        }


def default_metrics() -> tuple[MetricSpec, ...]:
    """사전 등록 metric 표. 성공을 제외하면 모두 관찰값이며 성능 우위 주장이 아니다."""

    return (
        MetricSpec(METRIC_TASK_SUCCESS, "ratio", "FINAL split tasks", "paired run", "higher_better"),
        MetricSpec(METRIC_TOTAL_RETRIES, "count", "FINAL split tasks", "paired run", "lower_better"),
        MetricSpec(METRIC_TOTAL_TOOL_CALLS, "count", "FINAL split tasks", "paired run", "lower_better"),
        MetricSpec(METRIC_BRAIN_CALLS, "count", "FINAL split tasks", "paired run", "report_only"),
        MetricSpec(METRIC_CONTEXT_TOKENS, "tokens", "FINAL split tasks", "paired run", "report_only"),
        MetricSpec(METRIC_CONTEXT_POLLUTION, "ratio", "injected tokens with labels", "paired run", "report_only"),
        MetricSpec(METRIC_LATENCY_P50, "ms", "FINAL split tasks", "paired run", "report_only"),
        MetricSpec(METRIC_REOPEN, "count", "closed decisions", "paired run", "lower_better"),
        MetricSpec(METRIC_FAILURE_REPETITION, "count", "repeated failures", "paired run", "lower_better"),
        MetricSpec(METRIC_EXPERIENCE_REUSE, "count", "mature advisory uses", "paired run", "report_only"),
        MetricSpec(METRIC_GUARDED_SUCCESS, "count", "guarded actions", "paired run", "report_only"),
        MetricSpec(METRIC_NEGATIVE_TRANSFER, "count", "labelled negative-transfer tasks", "paired run", "lower_better"),
    )


@dataclass(frozen=True, slots=True)
class BenchmarkSpec:
    """실행 전에 등록하는 성장 평가 명세. 실행 뒤 기준을 바꾸지 않는다."""

    experiment_id: str
    registered_at: datetime
    run_kind: RunKind
    seed: int
    corpus_digest: str
    split_ids: Mapping[str, tuple[str, ...]]
    metrics: tuple[MetricSpec, ...]
    primary_improvement_metric: str
    success_noninferiority_margin: float
    negative_transfer_max_success_decrease: int
    held_out_min_samples: int
    live_pilot_min_trials: int
    cache_mode: str
    policy_target: PolicyTarget
    policy_parameters: Mapping[str, int]
    validation_minimum_success: float = 0.5

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "experiment_id": self.experiment_id,
            "registered_at": self.registered_at.isoformat(),
            "run_kind": self.run_kind.value,
            "seed": self.seed,
            "corpus_digest": self.corpus_digest,
            "split_ids": {role: list(ids) for role, ids in sorted(self.split_ids.items())},
            "metrics": [metric.as_mapping() for metric in self.metrics],
            "primary_improvement_metric": self.primary_improvement_metric,
            "success_noninferiority_margin": self.success_noninferiority_margin,
            "negative_transfer_max_success_decrease": self.negative_transfer_max_success_decrease,
            "held_out_min_samples": self.held_out_min_samples,
            "live_pilot_min_trials": self.live_pilot_min_trials,
            "cache_mode": self.cache_mode,
            "policy_target": self.policy_target.value,
            "policy_parameters": dict(self.policy_parameters),
            "validation_minimum_success": self.validation_minimum_success,
        }

    def digest(self) -> str:
        return (
            "sha256:"
            + hashlib.sha256(
                json.dumps(self.as_mapping(), sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
        )

    def metric(self, name: str) -> MetricSpec:
        for metric in self.metrics:
            if metric.name == name:
                return metric
        raise KeyError(f"등록되지 않은 metric이다: {name}")

    def to_json(self) -> str:
        return json.dumps(self.as_mapping(), ensure_ascii=False, indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, payload: str) -> "BenchmarkSpec":
        """등록된 spec을 그대로 복원한다. 필드가 바뀌면 digest가 달라진다."""

        data = json.loads(payload)
        return cls(
            experiment_id=str(data["experiment_id"]),
            registered_at=datetime.fromisoformat(str(data["registered_at"])),
            run_kind=RunKind(data["run_kind"]),
            seed=int(data["seed"]),
            corpus_digest=str(data["corpus_digest"]),
            split_ids={str(role): tuple(str(item) for item in ids) for role, ids in dict(data["split_ids"]).items()},
            metrics=tuple(
                MetricSpec(
                    name=str(metric["name"]),
                    unit=str(metric["unit"]),
                    denominator=str(metric["denominator"]),
                    window=str(metric["window"]),
                    direction=str(metric["direction"]),
                )
                for metric in data["metrics"]
            ),
            primary_improvement_metric=str(data["primary_improvement_metric"]),
            success_noninferiority_margin=float(data["success_noninferiority_margin"]),
            negative_transfer_max_success_decrease=int(data["negative_transfer_max_success_decrease"]),
            held_out_min_samples=int(data["held_out_min_samples"]),
            live_pilot_min_trials=int(data["live_pilot_min_trials"]),
            cache_mode=str(data["cache_mode"]),
            policy_target=PolicyTarget(data["policy_target"]),
            policy_parameters={str(key): int(value) for key, value in dict(data["policy_parameters"]).items()},
            validation_minimum_success=float(data.get("validation_minimum_success", 0.5)),
        )


@dataclass(frozen=True, slots=True)
class GrowthTask:
    """fixture task 하나. item 이름은 canonical ID로 결정적으로 매핑된다."""

    task_id: str
    split: SplitRole
    category: FixtureCategory
    goal_name: str
    required_items: tuple[str, ...]
    store_items: tuple[str, ...]
    irrelevant_items: tuple[str, ...]
    append_content: str
    expected_outcome: str
    requires_guarded_reshape: bool = False
    negative_transfer: bool = False

    @property
    def goal_ref(self) -> str:
        return canonical_id("goal", self.goal_name)

    @property
    def required_refs(self) -> tuple[str, ...]:
        return tuple(canonical_id("evidence", name) for name in self.required_items)

    @property
    def store_refs(self) -> tuple[str, ...]:
        return tuple(canonical_id("evidence", name) for name in self.store_items)

    @property
    def irrelevant_refs(self) -> tuple[str, ...]:
        return tuple(canonical_id("evidence", name) for name in self.irrelevant_items)

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "task_id": self.task_id,
            "split": self.split.value,
            "category": self.category.value,
            "goal_ref": self.goal_ref,
            "required_items": list(self.required_refs),
            "store_items": list(self.store_refs),
            "irrelevant_items": list(self.irrelevant_refs),
            "append_content": self.append_content,
            "requires_guarded_reshape": self.requires_guarded_reshape,
            "negative_transfer": self.negative_transfer,
        }


_TASK_ROWS: Final[tuple[tuple[str, SplitRole, FixtureCategory, tuple[str, ...], tuple[str, ...], bool, bool], ...]] = (
    # task_id, split, category, (required,), (irrelevant,), guarded_reshape, negative_transfer
    ("PT-01", SplitRole.FINAL, FixtureCategory.NORMAL, ("cfg-alpha",), (), False, False),
    ("PT-02", SplitRole.FINAL, FixtureCategory.NORMAL, ("cfg-alpha",), ("noise-1",), False, False),
    ("PT-03", SplitRole.FINAL, FixtureCategory.NORMAL, ("cfg-beta",), (), False, False),
    ("PT-04", SplitRole.FINAL, FixtureCategory.UNKNOWN_CONFLICT, ("cfg-beta",), ("noise-2",), False, False),
    ("PT-05", SplitRole.FINAL, FixtureCategory.UNKNOWN_CONFLICT, ("cfg-gamma",), (), False, False),
    ("PT-06", SplitRole.FINAL, FixtureCategory.AUTHORITY_RESHAPE, ("cfg-gamma",), (), True, False),
    ("PT-07", SplitRole.FINAL, FixtureCategory.AUTHORITY_RESHAPE, ("cfg-alpha",), ("noise-1", "noise-2"), True, False),
    ("PT-08", SplitRole.FINAL, FixtureCategory.RECOVERY, ("cfg-beta",), (), False, False),
    ("PT-09", SplitRole.FINAL, FixtureCategory.RECOVERY, ("cfg-gamma",), ("noise-3",), False, False),
    ("PT-10", SplitRole.FINAL, FixtureCategory.DRIFT_NEGATIVE_TRANSFER, ("cfg-drift",), ("noise-1",), False, True),
    ("PT-11", SplitRole.FINAL, FixtureCategory.DRIFT_NEGATIVE_TRANSFER, ("cfg-alpha",), (), False, True),
    ("PT-12", SplitRole.FINAL, FixtureCategory.NORMAL, ("cfg-beta",), ("noise-2",), False, False),
    ("GT-T1", SplitRole.TRAIN, FixtureCategory.RECOVERY, ("cfg-alpha",), (), False, False),
    ("GT-T2", SplitRole.TRAIN, FixtureCategory.RECOVERY, ("cfg-beta",), ("noise-1",), False, False),
    ("GT-V1", SplitRole.VALIDATION, FixtureCategory.NORMAL, ("cfg-alpha",), (), False, False),
    ("GT-V2", SplitRole.VALIDATION, FixtureCategory.NORMAL, ("cfg-beta",), ("noise-2",), False, False),
    ("GT-V3", SplitRole.VALIDATION, FixtureCategory.UNKNOWN_CONFLICT, ("cfg-gamma",), (), False, False),
    ("GT-V4", SplitRole.VALIDATION, FixtureCategory.RECOVERY, ("cfg-alpha",), ("noise-3",), False, False),
    ("GT-F1", SplitRole.FINAL, FixtureCategory.NORMAL, ("cfg-alpha",), (), False, False),
    ("GT-F2", SplitRole.FINAL, FixtureCategory.NORMAL, ("cfg-beta",), ("noise-1",), False, False),
    ("GT-F3", SplitRole.FINAL, FixtureCategory.UNKNOWN_CONFLICT, ("cfg-gamma",), (), False, False),
    ("GT-F4", SplitRole.FINAL, FixtureCategory.AUTHORITY_RESHAPE, ("cfg-alpha",), ("noise-2",), True, False),
    ("GT-F5", SplitRole.FINAL, FixtureCategory.RECOVERY, ("cfg-beta",), (), False, False),
    ("GT-F6", SplitRole.FINAL, FixtureCategory.DRIFT_NEGATIVE_TRANSFER, ("cfg-drift",), ("noise-1",), False, True),
)


def default_corpus_tasks() -> tuple[GrowthTask, ...]:
    """원문 권고대로 12 fixture + train/validation/final held-out을 고정된 목록으로 만든다."""

    tasks: list[GrowthTask] = []
    for task_id, split, category, required, irrelevant, guarded, negative in _TASK_ROWS:
        store_items = tuple(dict.fromkeys((*required, *irrelevant)))
        tasks.append(
            GrowthTask(
                task_id=task_id,
                split=split,
                category=category,
                goal_name=f"goal-{task_id.lower()}",
                required_items=required,
                store_items=store_items,
                irrelevant_items=irrelevant,
                append_content=f"{task_id} appended",
                expected_outcome=f"{task_id} appended",
                requires_guarded_reshape=guarded,
                negative_transfer=negative,
            )
        )
    return tuple(tasks)


def corpus_digest(tasks: Sequence[GrowthTask]) -> str:
    payload = json.dumps([task.as_mapping() for task in tasks], sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def tasks_for(tasks: Sequence[GrowthTask], split: SplitRole) -> tuple[GrowthTask, ...]:
    return tuple(task for task in tasks if task.split is split)


def split_ids(tasks: Sequence[GrowthTask]) -> Mapping[str, tuple[str, ...]]:
    return {split.value: tuple(task.task_id for task in tasks_for(tasks, split)) for split in SplitRole}


def default_spec(
    *,
    tasks: Sequence[GrowthTask] | None = None,
    experiment_id: str = "growth-demo-v1",
    registered_at: datetime | None = None,
    run_kind: RunKind = RunKind.DETERMINISTIC_FIXTURE,
    seed: int = DEFAULT_SEED,
) -> BenchmarkSpec:
    """실행 전 등록용 기본 spec. fixture demo는 live 성능 주장이 아니다."""

    corpus = tuple(tasks if tasks is not None else default_corpus_tasks())
    return BenchmarkSpec(
        experiment_id=experiment_id,
        registered_at=registered_at if registered_at is not None else datetime(2026, 9, 22, 4, 0, 0, tzinfo=UTC),
        run_kind=run_kind,
        seed=seed,
        corpus_digest=corpus_digest(corpus),
        split_ids=split_ids(corpus),
        metrics=default_metrics(),
        primary_improvement_metric=METRIC_TOTAL_RETRIES,
        success_noninferiority_margin=0.0,
        negative_transfer_max_success_decrease=0,
        held_out_min_samples=len(tasks_for(corpus, SplitRole.FINAL)),
        live_pilot_min_trials=DEFAULT_LIVE_PILOT_TRIALS,
        cache_mode="cold-fixture-cache",
        policy_target=PolicyTarget.CONTEXT_DEPTH,
        policy_parameters={"extra_depth": MATURE_CONTEXT_STEP},
        validation_minimum_success=0.5,
    )


def project_record() -> Record:
    """context build에 필요한 project premise record(다른 record보다 먼저 commit한다)."""

    return Record.create(
        entity_type=EntityType.PROJECT,
        project_id="",
        producer=Producer(kind=ProducerKind.BODY, actor_id="body:benchmark"),
        payload=ProjectPayload(
            name="growth-demo",
            premise="deterministic growth demonstration corpus",
        ),
        record_id=canonical_id("project", "growth-demo"),
        created_at=datetime(2026, 9, 22, 4, 0, 0, tzinfo=UTC),
    )


def goal_record(task: GrowthTask) -> Record:
    """goal은 evidence를 직접 참조하지 않는다. 어떤 evidence가 필요한지는 축적된 경험이 안다."""

    return Record.create(
        entity_type=EntityType.GOAL,
        project_id=canonical_id("project", "growth-demo"),
        producer=Producer(kind=ProducerKind.BODY, actor_id="body:benchmark"),
        payload=GoalPayload(
            statement=f"{task.task_id} fixture goal",
            success_criteria=(task.expected_outcome,),
            status=GoalStatus.ACTIVE,
        ),
        record_id=task.goal_ref,
        created_at=datetime(2026, 9, 22, 4, 0, 0, tzinfo=UTC),
    )


def evidence_record(task: GrowthTask, name: str, *, irrelevant: bool) -> Record:
    return Record.create(
        entity_type=EntityType.EVIDENCE,
        project_id=canonical_id("project", "growth-demo"),
        producer=Producer(kind=ProducerKind.HUMAN if irrelevant else ProducerKind.BODY, actor_id="body:benchmark"),
        payload=EvidencePayload(
            kind=EvidenceKind.OBSERVATION,
            claim=f"{task.task_id} item {name}{' (irrelevant label)' if irrelevant else ' (required config)'}",
            provenance=Provenance(
                source_uri=f"fixtures/cognitive/{task.task_id}/{name}.json",
                content_digest="sha256:" + hashlib.sha256(name.encode("utf-8")).hexdigest(),
                observed_at=datetime(2026, 9, 22, 4, 0, 0, tzinfo=UTC),
                ingested_at=datetime(2026, 9, 22, 4, 0, 0, tzinfo=UTC),
            ),
            time=datetime(2026, 9, 22, 4, 0, 0, tzinfo=UTC),
            digest="sha256:" + hashlib.sha256(f"{task.task_id}:{name}".encode("utf-8")).hexdigest(),
            independence_group=f"{task.task_id}:{name}",
        ),
        record_id=canonical_id("evidence", name),
        created_at=datetime(2026, 9, 22, 4, 0, 0, tzinfo=UTC),
    )


def corpus_records(tasks: Sequence[GrowthTask]) -> tuple[Record, ...]:
    """corpus를 canonical store에 심을 record로 만든다(항목 ID는 결정적이다)."""

    project = project_record()
    records: dict[str, Record] = {project.id: project}
    for task in tasks:
        records[task.goal_ref] = goal_record(task)
        for name in task.store_items:
            records[canonical_id("evidence", name)] = evidence_record(
                task, name, irrelevant=name in task.irrelevant_items
            )
    return tuple(records.values())


def project_subject() -> str:
    return "body:benchmark"


def context_principal() -> ContextPrincipal:
    return ContextPrincipal(
        subject=project_subject(),
        project_id=canonical_id("project", "growth-demo"),
        max_disclosure=DisclosureLevel.L3_RAW,
    )


def context_budget() -> ContextBudget:
    return ContextBudget(token_budget=4000, tokens_used=0, l0_reserved_tokens=200)


CONTEXT_DISCLOSURE: Final[DisclosureLevel] = DisclosureLevel.L3_RAW


def build_context_once(
    builder: ContextBuilder,
    *,
    task: GrowthTask,
    state_revision: int,
    policy_version: str | None,
    limits: Mapping[str, int],
) -> ContextBuildResult:
    """실제 ContextBuilder로 context package를 만든다(성장 데모의 selection 단계)."""

    return builder.build(
        goal_id=task.goal_ref,
        state_revision=state_revision,
        principal=context_principal(),
        budget=context_budget(),
        policy_version=policy_version,
        l1_limit=int(limits["l1_limit"]),
        l2_limit=int(limits["l2_limit"]),
        l3_limit=int(limits["l3_limit"]),
        requested_disclosure=CONTEXT_DISCLOSURE,
    )


# ─── mechanism·arm 계약 ──────────────────────────────────────────


class GrowthBenchmarkError(ValueError):
    """benchmark 계약 위반(등록되지 않은 spec, corpus 불일치, 지원하지 않는 mode)."""


FIXTURE_BRAIN_VERSION: Final[str] = "fixture-brain/v1"
STATE_REVISION: Final[int] = 1
DECISION_REVISION: Final[int] = 1
AUTHORITY_REVISION: Final[int] = 1


@dataclass(frozen=True, slots=True)
class MechanismSet:
    """실행에 켜진 mechanism. 하나씩 끄는 ablation의 단위다."""

    context_builder: bool = True
    experience_advisory: bool = True
    targeted_rereasoning: bool = True
    experience: bool = True
    risk_shaping: bool = True
    governance_learning: bool = True

    def enabled(self, mechanism: Mechanism) -> bool:
        return bool(getattr(self, mechanism.value.lower()))

    def without(self, mechanism: Mechanism) -> "MechanismSet":
        return replace(self, **{mechanism.value.lower(): False})

    def disabled(self) -> tuple[Mechanism, ...]:
        return tuple(mechanism for mechanism in Mechanism if not self.enabled(mechanism))

    def as_mapping(self) -> Mapping[str, bool]:
        return {mechanism.value: self.enabled(mechanism) for mechanism in Mechanism}

    @property
    def authority_boundaries_unchanged(self) -> bool:
        """헌법·권한 보호는 ablation 대상이 아니다 — 모든 조합에서 그대로 유지된다."""

        return True


@dataclass(frozen=True, slots=True)
class ArmInputs:
    """arm을 구분하는 유일한 입력. code·brain·corpus는 모든 arm이 동일하다."""

    role: ArmRole
    mechanisms: MechanismSet = field(default_factory=MechanismSet)
    policy_version: str | None = None
    advisory_refs: tuple[str, ...] = ()
    disabled_mechanism: Mechanism | None = None
    context_limits: Mapping[str, int] = field(default_factory=lambda: dict(BASELINE_CONTEXT_LIMITS))

    @property
    def brain_version(self) -> str:
        return FIXTURE_BRAIN_VERSION

    def effective_limits(self) -> Mapping[str, int]:
        """검증된 policy와 축적 advisory가 모두 있을 때만 context depth를 연다."""

        limits = dict(self.context_limits)
        if self.policy_version and self.advisory_refs and self.mechanisms.governance_learning:
            limits["l2_limit"] = int(limits["l2_limit"]) + MATURE_CONTEXT_STEP
            limits["l3_limit"] = int(limits["l3_limit"]) + MATURE_CONTEXT_STEP
        return limits

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "role": self.role.value,
            "policy_version": self.policy_version,
            "advisory_refs": list(self.advisory_refs),
            "disabled_mechanism": self.disabled_mechanism.value if self.disabled_mechanism else None,
            "context_limits": dict(self.effective_limits()),
            "mechanisms": self.mechanisms.as_mapping(),
        }


@dataclass(frozen=True, slots=True)
class TaskOutcome:
    """task 한 건의 관찰값. 성과 주장이 아니라 측정값이다."""

    task_id: str
    success: bool
    retries: int
    tool_calls: int
    brain_calls: int
    context_items: int
    injected_tokens: int
    irrelevant_injected_tokens: int
    guarded_success: bool
    experience_reused: bool
    termination: str
    outcome_status: str
    first_attempt_wrong: bool = False
    rethink_rounds: int = 0
    negative_transfer: bool = False
    detail: str = ""

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "task_id": self.task_id,
            "success": self.success,
            "retries": self.retries,
            "tool_calls": self.tool_calls,
            "brain_calls": self.brain_calls,
            "context_items": self.context_items,
            "injected_tokens": self.injected_tokens,
            "irrelevant_injected_tokens": self.irrelevant_injected_tokens,
            "guarded_success": self.guarded_success,
            "experience_reused": self.experience_reused,
            "termination": self.termination,
            "outcome_status": self.outcome_status,
            "negative_transfer": self.negative_transfer,
        }


@dataclass(frozen=True, slots=True)
class ArmMetrics:
    values: Mapping[str, float]
    na: Mapping[str, str] = field(default_factory=dict)

    def value(self, name: str) -> float | None:
        return self.values.get(name)

    def as_mapping(self) -> Mapping[str, object]:
        return {"values": dict(self.values), "na": dict(self.na)}


@dataclass(frozen=True, slots=True)
class RunManifest:
    """매 실행의 재현 정보. 같은 조건 재생 여부를 판단하는 근거다."""

    experiment_id: str
    spec_digest: str
    arm: ArmRole
    run_kind: RunKind
    seed: int
    corpus_digest: str
    split: str
    task_ids: tuple[str, ...]
    brain_version: str
    policy_version: str | None
    advisory_refs: tuple[str, ...]
    mechanisms: Mapping[str, bool]
    disabled_mechanisms: tuple[str, ...]
    cache_mode: str
    store_root: str
    source_head: str
    started_at: datetime
    finished_at: datetime

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "experiment_id": self.experiment_id,
            "spec_digest": self.spec_digest,
            "arm": self.arm.value,
            "run_kind": self.run_kind.value,
            "seed": self.seed,
            "corpus_digest": self.corpus_digest,
            "split": self.split,
            "task_ids": list(self.task_ids),
            "brain_version": self.brain_version,
            "policy_version": self.policy_version,
            "advisory_refs": list(self.advisory_refs),
            "mechanisms": dict(self.mechanisms),
            "disabled_mechanisms": list(self.disabled_mechanisms),
            "cache_mode": self.cache_mode,
            "store_root": self.store_root,
            "source_head": self.source_head,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
        }

    def digest(self) -> str:
        return (
            "sha256:"
            + hashlib.sha256(
                json.dumps(self.as_mapping(), sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
        )


@dataclass(frozen=True, slots=True)
class ArmResult:
    manifest: RunManifest
    outcomes: tuple[TaskOutcome, ...]
    metrics: ArmMetrics
    committed_records: int
    dispatched_actions: int
    duplicate_dispatches: int
    safety_violations: tuple[str, ...]
    store_root: str

    def task_outcome(self, task_id: str) -> TaskOutcome:
        for outcome in self.outcomes:
            if outcome.task_id == task_id:
                return outcome
        raise GrowthBenchmarkError(f"arm에 없는 task다: {task_id}")

    @property
    def success_count(self) -> int:
        return sum(1 for outcome in self.outcomes if outcome.success)

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "manifest": self.manifest.as_mapping(),
            "metrics": self.metrics.as_mapping(),
            "success_count": self.success_count,
            "committed_records": self.committed_records,
            "dispatched_actions": self.dispatched_actions,
            "duplicate_dispatches": self.duplicate_dispatches,
            "safety_violations": list(self.safety_violations),
            "store_root": self.store_root,
        }


@dataclass(frozen=True, slots=True)
class GrowthPhase:
    """train split 경험 축적 → candidate → validation → activation → behavior trace."""

    candidate_id: str
    candidate_parameters: Mapping[str, int]
    independent_episode_count: int
    validation_report_id: str
    validation_split_id: str
    validation_passed: bool
    policy_id: str
    policy_version: str
    activation_id: str
    behavior_trace_ids: tuple[str, ...]
    shadow_selection: tuple[str, ...]
    actual_selection: tuple[str, ...]
    advisory_refs: tuple[str, ...]
    train_task_ids: tuple[str, ...]
    commit_records: tuple[Record, ...]

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "candidate_parameters": dict(self.candidate_parameters),
            "independent_episode_count": self.independent_episode_count,
            "validation_report_id": self.validation_report_id,
            "validation_split_id": self.validation_split_id,
            "validation_passed": self.validation_passed,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "activation_id": self.activation_id,
            "behavior_trace_ids": list(self.behavior_trace_ids),
            "shadow_selection": list(self.shadow_selection),
            "actual_selection": list(self.actual_selection),
            "advisory_refs": list(self.advisory_refs),
            "train_task_ids": list(self.train_task_ids),
        }


@dataclass(frozen=True, slots=True)
class GrowthVerdict:
    """사전 등록 게이트 4·5의 판정. 작은 표본의 우위 주장이 아니다."""

    success_noninferior: bool
    primary_metric_improved: bool
    negative_transfer_absent: bool
    safety_clean: bool
    duplicate_dispatch_absent: bool
    passed: bool
    reasons: tuple[str, ...]

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "success_noninferior": self.success_noninferior,
            "primary_metric_improved": self.primary_metric_improved,
            "negative_transfer_absent": self.negative_transfer_absent,
            "safety_clean": self.safety_clean,
            "duplicate_dispatch_absent": self.duplicate_dispatch_absent,
            "passed": self.passed,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True, slots=True)
class GrowthComparison:
    spec_digest: str
    meta: GrowthPhase
    fresh: ArmResult
    mature: ArmResult
    primary_metric: str
    primary_fresh: float
    primary_mature: float
    success_fresh: float
    success_mature: float
    negative_transfer_delta: int
    verdict: GrowthVerdict

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "spec_digest": self.spec_digest,
            "primary_metric": self.primary_metric,
            "primary": {"fresh": self.primary_fresh, "mature": self.primary_mature},
            "success": {"fresh": self.success_fresh, "mature": self.success_mature},
            "negative_transfer_delta": self.negative_transfer_delta,
            "verdict": self.verdict.as_mapping(),
            "growth_phase": self.meta.as_mapping(),
            "fresh": self.fresh.as_mapping(),
            "mature": self.mature.as_mapping(),
        }


@dataclass(frozen=True, slots=True)
class AblationResult:
    mechanism: Mechanism
    status: AblationStatus
    reason: str
    arm: ArmResult | None = None
    delta_primary: float | None = None
    delta_success: float = 0.0
    dependent_mechanisms: tuple[Mechanism, ...] = ()

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "mechanism": self.mechanism.value,
            "status": self.status.value,
            "reason": self.reason,
            "delta_primary": self.delta_primary,
            "delta_success": self.delta_success,
            "dependent_mechanisms": [item.value for item in self.dependent_mechanisms],
            "arm": self.arm.as_mapping() if self.arm is not None else None,
        }


@dataclass(frozen=True, slots=True)
class GrowthDemo:
    spec: BenchmarkSpec
    comparison: GrowthComparison
    ablations: tuple[AblationResult, ...]

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "spec": self.spec.as_mapping(),
            "comparison": self.comparison.as_mapping(),
            "ablations": [ablation.as_mapping() for ablation in self.ablations],
        }

    def to_json(self) -> str:
        return json.dumps(self.as_mapping(), ensure_ascii=False, indent=2, sort_keys=True, default=str)


# ─── 실행 보조 ────────────────────────────────────────────────────


#: arm별 저장 root를 받아 실행 포트를 만드는 factory. 도구 계층 결선은 이 패키지 밖(adapter)에 둔다.
ExecutorFactory = Callable[[Path], ToolExecutorPort]


def risk_for_task(task: GrowthTask) -> RiskProfile:
    """guarded fixture는 넓은 범위의 되돌리기 어려운 변경을 낸다."""

    if task.requires_guarded_reshape:
        return RiskProfile(
            reversibility=RiskLevel.HIGH,
            blast_radius=RiskLevel.HIGH,
            data_state_loss=RiskLevel.MODERATE,
            verification=RiskLevel.MODERATE,
            rollback=RiskLevel.HIGH,
        )
    return RiskProfile(
        reversibility=RiskLevel.LOW,
        blast_radius=RiskLevel.LOW,
        data_state_loss=RiskLevel.LOW,
        verification=RiskLevel.LOW,
        rollback=RiskLevel.LOW,
    )


def plan_readiness(
    task: GrowthTask,
    *,
    action_digest: str,
    risk: RiskProfile,
    policy_version: str | None,
    limits: tuple[str, ...] = (),
    state_revision: int = STATE_REVISION,
    tool: str = "fixture_write",
    dimension: AuthorityDimension = AuthorityDimension.TOOL_WRITE,
) -> ReadinessResult:
    return check_readiness(
        ReadinessInputs(
            action=ActionScope(
                tool=tool,
                scope=task.task_id,
                expected_outcome=task.expected_outcome,
                action_digest=action_digest,
            ),
            authorized_action_digest=action_digest,
            decision_revision=DECISION_REVISION,
            state_revision=state_revision,
            authority_revision=AUTHORITY_REVISION,
            policy_version=policy_version,
            grounds=task.required_refs,
            evidence_refs=tuple(
                EvidenceRef(
                    evidence_id=ref,
                    provenance_uri=f"fixtures/cognitive/{task.task_id}/{ref}.json",
                    provenance_digest="sha256:" + hashlib.sha256(ref.encode("utf-8")).hexdigest(),
                    observed_at=datetime(2026, 9, 22, 4, 0, 0, tzinfo=UTC),
                )
                for ref in task.required_refs
            ),
            constraints=(HardConstraint(name="no_network", satisfied=True),),
            risk=risk,
            limits=limits,
            authority_decision=AuthorityDecision(
                allowed=True,
                verdict=AuthorityVerdict.ALLOWED,
                reason="fixture authority",
                dimension=dimension,
                resource_scope=task.task_id,
                profile_revision=AUTHORITY_REVISION,
            ),
        )
    )


def guard_receipts(guards: Sequence[ReshapeGuard]) -> tuple[GuardReceipt, ...]:
    return tuple(
        GuardReceipt(
            guard=guard,
            enforced_by="fixture_executor",
            receipt_digest="sha256:" + hashlib.sha256(f"{guard.value}:fixture".encode("utf-8")).hexdigest(),
        )
        for guard in guards
    )


def append_intent(
    task: GrowthTask,
    *,
    attempt: int,
    content: str,
    target: Path,
    risk: RiskProfile,
    readiness: ReadinessResult | None,
    policy_version: str | None,
    guards: tuple[ReshapeGuard, ...] = (),
) -> ActionIntent:
    return ActionIntent(
        action_id=canonical_id("action", f"{task.task_id}:append:{attempt}"),
        submission_id=f"submission:{task.task_id}:{attempt}",
        action_key=f"{task.task_id}:attempt-{attempt}",
        tool="fixture_write",
        arguments={"file_path": str(target), "content": content},
        scope=task.task_id,
        dimension=AuthorityDimension.TOOL_WRITE,
        risk=risk,
        reversible=not task.requires_guarded_reshape,
        guards=guards,
        guard_receipts=guard_receipts(guards),
        readiness=readiness,
        clearance=PolicyClearance(
            authority=AuthorityDecision(
                allowed=True,
                verdict=AuthorityVerdict.ALLOWED,
                reason="fixture clearance",
                dimension=AuthorityDimension.TOOL_WRITE,
                resource_scope=task.task_id,
                profile_revision=AUTHORITY_REVISION,
            ),
            revision=AUTHORITY_REVISION,
        ),
        decision_revision=DECISION_REVISION,
        state_revision=STATE_REVISION,
        authority_revision=AUTHORITY_REVISION,
        policy_version=policy_version,
    )


def read_request(
    task: GrowthTask, *, ref: str, root: Path, policy_version: str | None = None
) -> CognitiveRequestEnvelope:
    """context에 빠진 필수 evidence를 읽는 요청. 요청 단위 EXECUTE도 같은 권한·readiness 경계를 지난다."""

    name = ref.split(":", 1)[1]
    path = root / f"{name}.json"
    risk = RiskProfile(reversibility=RiskLevel.LOW, blast_radius=RiskLevel.LOW)
    intent = ActionIntent(
        action_id=canonical_id("action", f"{task.task_id}:read:{name}"),
        submission_id=f"submission:{task.task_id}:read:{name}",
        action_key=f"{task.task_id}:read:{name}",
        tool="fixture_read",
        arguments={"file_path": str(path)},
        scope=task.task_id,
        dimension=AuthorityDimension.TOOL_READ,
        risk=risk,
        clearance=PolicyClearance(
            authority=AuthorityDecision(
                allowed=True,
                verdict=AuthorityVerdict.ALLOWED,
                reason="fixture read clearance",
                dimension=AuthorityDimension.TOOL_READ,
                resource_scope=task.task_id,
                profile_revision=AUTHORITY_REVISION,
            ),
            revision=AUTHORITY_REVISION,
        ),
        decision_revision=DECISION_REVISION,
        state_revision=STATE_REVISION,
        authority_revision=AUTHORITY_REVISION,
        policy_version=policy_version,
    )
    intent = replace(
        intent,
        readiness=plan_readiness(
            task,
            action_digest=intent.args_digest(),
            risk=risk,
            policy_version=policy_version,
            tool="fixture_read",
            dimension=AuthorityDimension.TOOL_READ,
        ),
    )
    return CognitiveRequestEnvelope(
        request_id=f"request:{task.task_id}:read:{name}",
        request_type=CognitiveRequestType.TOOL,
        purpose="필수 config evidence를 context 밖에서 확인한다",
        target=ref,
        expected_decision_impact="context 누락을 보완한다",
        dimension=AuthorityDimension.TOOL_READ,
        resource_scope=task.task_id,
        action=intent,
    )


def refused_request(task: GrowthTask, *, attempt: int) -> CognitiveRequestEnvelope:
    """guarded fixture의 첫 요청: 넓은 범위의 되돌리기 어려운 변경 → governance는 RESHAPE를 요구한다."""

    return CognitiveRequestEnvelope(
        request_id=f"request:{task.task_id}:wide:{attempt}",
        request_type=CognitiveRequestType.TOOL,
        purpose="넓은 범위를 한 번에 변경한다",
        target=task.task_id,
        expected_decision_impact="범위를 넓힌다",
        dimension=AuthorityDimension.TOOL_WRITE,
        resource_scope=task.task_id,
        risk=risk_for_task(task),
        action=ActionIntent(
            action_id=canonical_id("action", f"{task.task_id}:wide:{attempt}"),
            submission_id=f"submission:{task.task_id}:wide:{attempt}",
            action_key=f"{task.task_id}:wide-{attempt}",
            tool="fixture_write",
            arguments={"file_path": str(task.task_id), "content": task.append_content},
            scope=task.task_id,
            dimension=AuthorityDimension.TOOL_WRITE,
            reversible=False,
            risk=risk_for_task(task),
        ),
    )


class FixtureThink:
    """같은 code/brain_version을 쓰는 결정적 fixture Brain. 입력(policy·advisory·context)만 arm마다 다르다."""

    version: Final[str] = FIXTURE_BRAIN_VERSION

    def __init__(
        self,
        *,
        task: GrowthTask,
        missing_refs: tuple[str, ...],
        root: Path,
        risk: RiskProfile,
        reshape: tuple[ReshapeGuard, ...],
        guarded_first_request: bool,
        prepared_plan: EpisodePlan,
        policy_version: str | None = None,
    ) -> None:
        self.task = task
        self.missing_refs = missing_refs
        self.root = root
        self.risk = risk
        self.reshape = reshape
        self.guarded_first_request = guarded_first_request
        self.policy_version = policy_version
        self.prepared_plan = prepared_plan
        self.calls: list[str] = []

    def think(self, *, context_ref: str, request_signature: str, attempt: int) -> ThinkOutcome:
        self.calls.append(f"think:{attempt}")
        requests: list[CognitiveRequestEnvelope] = []
        if self.missing_refs:
            requests.append(
                read_request(
                    self.task,
                    ref=self.missing_refs[0],
                    root=self.root,
                    policy_version=self.policy_version,
                )
            )
        if self.guarded_first_request:
            requests.insert(0, refused_request(self.task, attempt=attempt))
        delta = EpisodeDelta(ground=bool(self.missing_refs), risk=self.guarded_first_request, judgment=True)
        return ThinkOutcome(
            judgment_ref=f"judgment:{self.task.task_id}:{attempt}",
            requests=tuple(requests),
            delta=delta,
            plan=self.prepared_plan,
        )

    def rethink(
        self,
        *,
        previous_judgment_ref: str,
        feedback_refs: Sequence[str],
        affected_grounds: Sequence[str],
        round_index: int,
        feedback: Sequence[RequestFeedback] = (),
    ) -> ThinkOutcome:
        """거부된 넓은 요청을 좁은 범위로 다시 판단한다(material delta를 남긴다)."""

        self.calls.append(f"rethink:{round_index}")
        return ThinkOutcome(
            judgment_ref=f"judgment:{self.task.task_id}:narrow:{round_index}",
            requests=(),
            plan=replace(self.prepared_plan),
            delta=EpisodeDelta(
                action=True,
                risk=True,
                description=f"넓은 요청을 {self.task.task_id} 범위로 좁혔다",
            ),
        )


def advisory_experience_record(
    *, project_id: str, refs: Sequence[str], producer: Producer, created_at: datetime
) -> Record:
    """train split에서 관측된 누락을 advisory Experience record로 남긴다(원본은 삭제하지 않는다)."""

    return Record.create(
        entity_type=EntityType.EXPERIENCE,
        project_id=project_id,
        producer=producer,
        payload=ExperiencePayload(
            trigger="필수 config evidence가 얕은 context에서 누락되어 재시도가 생겼다",
            historical_refs=tuple(refs),
            remaining_unknowns=("다른 evidence family에도 같은 누락이 있는지",),
            future_attention=("required config evidence를 context에 미리 포함한다",),
        ),
        references=tuple(
            Reference(relation=REL_EVIDENCE, target_id=ref, expected_type=EntityType.EVIDENCE) for ref in refs
        ),
        created_at=created_at,
    )


def _arm_metrics(outcomes: Sequence[TaskOutcome]) -> ArmMetrics:
    """metric마다 분모·측정 구간을 고정해 계산한다. 작은 표본을 성과 보장으로 확대하지 않는다."""

    total = len(outcomes) or 1
    injected = sum(outcome.injected_tokens for outcome in outcomes)
    irrelevant = sum(outcome.irrelevant_injected_tokens for outcome in outcomes)
    retry_sorted = [outcome.retries for outcome in outcomes]
    na: dict[str, str] = {}
    if injected == 0:
        na[METRIC_CONTEXT_POLLUTION] = NA_REASON_NO_LABELS
        pollution = 0.0
    else:
        pollution = irrelevant / injected
    values = {
        METRIC_TASK_SUCCESS: sum(1 for outcome in outcomes if outcome.success) / total,
        METRIC_TOTAL_RETRIES: float(sum(outcome.retries for outcome in outcomes)),
        METRIC_TOTAL_TOOL_CALLS: float(sum(outcome.tool_calls for outcome in outcomes)),
        METRIC_BRAIN_CALLS: float(sum(outcome.brain_calls for outcome in outcomes)),
        METRIC_CONTEXT_TOKENS: float(injected),
        METRIC_CONTEXT_POLLUTION: pollution,
        METRIC_LATENCY_P50: float(sorted(retry_sorted)[len(retry_sorted) // 2]) if retry_sorted else 0.0,
        METRIC_REOPEN: 0.0,
        METRIC_FAILURE_REPETITION: float(
            sum(1 for outcome in outcomes if outcome.first_attempt_wrong and not outcome.success)
        ),
        METRIC_EXPERIENCE_REUSE: float(sum(1 for outcome in outcomes if outcome.experience_reused)),
        METRIC_GUARDED_SUCCESS: float(sum(1 for outcome in outcomes if outcome.guarded_success)),
        METRIC_NEGATIVE_TRANSFER: float(
            sum(1 for outcome in outcomes if outcome.negative_transfer and not outcome.success)
        ),
    }
    return ArmMetrics(values=values, na=na)


@dataclass(frozen=True, slots=True)
class TaskRun:
    """task 실행 결과 + 첫 시도 평가·selection 기록(학습 근거와 trace 입력)."""

    outcome: TaskOutcome
    first_attempt_status: OutcomeStatus
    evidence_ids: tuple[str, ...]
    raw_material_digest: str
    selected_evidence: tuple[str, ...]
    context_ref: str
    dispatch_keys: tuple[str, ...] = ()
    episode_records: tuple[Record, ...] = ()


class GrowthRunner:
    """결정적 fixture 성장 데모 실행기. live model·provider를 호출하지 않는다."""

    def __init__(
        self,
        root: str | Path,
        spec: BenchmarkSpec,
        *,
        tasks: Sequence[GrowthTask] | None = None,
        source_head: str = "",
        executor_factory: ExecutorFactory,
    ) -> None:
        self.root = Path(root)
        self.spec = spec
        self._executor_factory = executor_factory
        self.tasks = tuple(tasks if tasks is not None else default_corpus_tasks())
        if corpus_digest(self.tasks) != spec.corpus_digest:
            raise GrowthBenchmarkError("corpus가 등록된 spec과 다르다 — 실행 전에 spec을 등록해야 한다")
        if not same_enum(spec.run_kind, RunKind.DETERMINISTIC_FIXTURE):
            raise GrowthBenchmarkError(
                f"{spec.run_kind}는 이 harness가 실행하지 않는다 — live 결과로 대체하지 않는다(NOT_RUN)"
            )
        self.source_head = source_head
        self.project_id = canonical_id("project", "growth-demo")
        self.producer = Producer(kind=ProducerKind.BODY, actor_id="body:benchmark")
        self._tick = 0

    # ── 시간·경로 ────────────────────────────────────
    def _now(self) -> datetime:
        self._tick += 1
        return datetime(2026, 9, 22, 4, 0, 0, tzinfo=UTC) + timedelta(milliseconds=self._tick)

    def _arm_root(self, arm: str) -> Path:
        path = self.root / arm
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _fixture_root(self, workdir: Path) -> Path:
        """fixture evidence는 arm 저장 root 안에 둔다(executor의 project root와 같은 경계)."""

        path = workdir / "fixtures"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _seed_store(self, arm_root: Path, *, extra: Sequence[Record] = ()) -> CanonicalStore:
        """corpus를 arm 저장 root에 심는다. 같은 root 재실행 시 이미 공개된 record는 건드리지 않는다."""

        store = CanonicalStore(arm_root / "store", git_enabled=False)
        missing = [record for record in (*corpus_records(self.tasks), *extra) if not store.is_committed(record.id)]
        if missing:
            store.commit_records(missing, message=f"growth corpus seed ({arm_root.name})")
        return store

    def _write_fixture_evidence(self, task: GrowthTask, workdir: Path) -> Path:
        root = self._fixture_root(workdir)
        for name in task.store_items:
            path = root / f"{canonical_id('evidence', name).split(':', 1)[1]}.json"
            if not path.exists():
                path.write_text(json.dumps({"task": task.task_id, "item": name}), encoding="utf-8")
        first = canonical_id("evidence", task.store_items[0]).split(":", 1)[1]
        return root / f"{first}.json"

    # ── task 실행 ────────────────────────────────────
    def _run_task(
        self,
        inputs: ArmInputs,
        task: GrowthTask,
        *,
        store: CanonicalStore,
        executor: ToolExecutorPort,
        workdir: Path,
        limits: Mapping[str, int],
        advisory_experience_ids: Sequence[str],
    ) -> TaskRun:
        target = workdir / f"{task.task_id}.txt"
        self._write_fixture_evidence(task, workdir)
        policy_version = inputs.policy_version if inputs.mechanisms.governance_learning else None
        if not inputs.mechanisms.context_builder:
            outcome = TaskOutcome(
                task_id=task.task_id,
                success=False,
                retries=0,
                tool_calls=0,
                brain_calls=1,
                context_items=0,
                injected_tokens=0,
                irrelevant_injected_tokens=0,
                guarded_success=False,
                experience_reused=False,
                termination=EpisodeTermination.BLOCKED_CONTEXT.value,
                outcome_status=OutcomeStatus.UNKNOWN.value,
                first_attempt_wrong=True,
                negative_transfer=task.negative_transfer,
                detail="context builder 비활성 — context 없이 ACTION하지 않는다",
            )
            return TaskRun(
                outcome=outcome,
                first_attempt_status=OutcomeStatus.UNKNOWN,
                evidence_ids=task.required_refs,
                raw_material_digest=self._raw_digest(task, inputs),
                selected_evidence=(),
                context_ref="",
            )

        builder = ContextBuilder(store, clock=self._now)
        built = build_context_once(
            builder,
            task=task,
            state_revision=STATE_REVISION,
            policy_version=policy_version,
            limits=limits,
        )
        present = tuple(item.record_id for item in built.payload.l3_evidence)
        advisory_ids = set(advisory_experience_ids)
        experience_reused = any(item.record_id in advisory_ids for item in built.payload.l2_history)
        irrelevant_injected = sum(
            item.token_estimate for item in built.payload.l3_evidence if item.record_id in set(task.irrelevant_refs)
        )
        context_items = (
            len(built.payload.l0_constraints)
            + len(built.payload.l1_state)
            + len(built.payload.l2_history)
            + len(built.payload.l3_evidence)
        )
        missing = tuple(ref for ref in task.required_refs if ref not in present)
        guarded = task.requires_guarded_reshape
        risk = risk_for_task(task)
        shaped = guarded and inputs.mechanisms.risk_shaping
        guards = tuple(reshape_plan(risk, reversible=False)) if shaped else ()
        action_risk = (
            RiskProfile(reversibility=RiskLevel.LOW, blast_radius=RiskLevel.LOW, rollback=RiskLevel.LOW)
            if shaped
            else risk
        )
        first_content = task.append_content if not missing else f"{task.task_id} appended (unverified)"
        intent = append_intent(
            task,
            attempt=1,
            content=first_content,
            target=target,
            risk=action_risk,
            readiness=None,
            policy_version=policy_version,
            guards=guards,
        )
        readiness = plan_readiness(
            task,
            action_digest=intent.args_digest(),
            risk=action_risk,
            policy_version=policy_version,
            limits=tuple(f"reshape:{guard.value}" for guard in guards),
        )
        intent = replace(intent, readiness=readiness)
        dispatcher = ActionDispatcher(
            port=executor,
            clock=self._now,
        )
        plan = EpisodePlan(
            readiness=readiness,
            action=intent,
            expected_outcome=task.expected_outcome,
            observation=ActionObservation(observed=True, succeeded=True, detail="fixture observed"),
        )
        brain = FixtureThink(
            task=task,
            missing_refs=missing,
            root=self._fixture_root(workdir),
            risk=risk,
            reshape=guards,
            guarded_first_request=guarded,
            prepared_plan=plan,
            policy_version=policy_version,
        )
        runtime = CognitiveRuntime(
            think=brain,
            rethink=brain if inputs.mechanisms.targeted_rereasoning else None,
            actions=dispatcher,
            governance=GovernanceGate(),
            budget=EpisodeBudget(expansion_rounds=3),
            project_id=self.project_id,
            producer=self.producer,
            clock=self._now,
        )
        episode = runtime.run(
            EpisodeRequest(
                episode_id=f"episode:{inputs.role.value.lower()}:{task.task_id}",
                context_ref=built.record.id,
                goal_ref=task.goal_ref,
                expected_outcome=task.expected_outcome,
                simple=not (missing or guarded),
                decision_revision=DECISION_REVISION,
                state_revision=STATE_REVISION,
                authority_revision=AUTHORITY_REVISION,
                policy_version=policy_version,
                plan=plan,
            )
        )

        corrected_dispatched = 0
        if missing:
            # 누락 evidence를 읽은 뒤 정정 append를 한 번 더 낸다(재시도).
            corrected = append_intent(
                task,
                attempt=2,
                content=task.append_content,
                target=target,
                risk=action_risk,
                readiness=None,
                policy_version=policy_version,
                guards=guards,
            )
            corrected = replace(
                corrected,
                readiness=plan_readiness(
                    task,
                    action_digest=corrected.args_digest(),
                    risk=action_risk,
                    policy_version=policy_version,
                    limits=tuple(f"reshape:{guard.value}" for guard in guards),
                ),
            )
            second = dispatcher.execute(corrected, project_id=self.project_id, producer=self.producer)
            corrected_dispatched = 1 if same_enum(second.status, ActionExecutionStatus.DISPATCHED) else 0
        dispatched_feedback = sum(1 for item in episode.feedback if item.executed)
        refused_feedback = sum(1 for item in episode.feedback if not item.executed)
        tool_calls = 1 + dispatched_feedback + corrected_dispatched
        # retry = 계획된 단일 action 밖의 추가 시도 + 거부된 시도
        retries = (tool_calls - 1) + refused_feedback
        resolved_refusals = refused_feedback == 0 or episode.counters.rethink_rounds > 0
        lines = target.read_text(encoding="utf-8").splitlines() if target.exists() else []
        content_ok = bool(lines) and lines[-1] == task.expected_outcome
        success = same_enum(episode.termination, EpisodeTermination.COMPLETED) and content_ok and resolved_refusals
        first_attempt_status = OutcomeStatus.DEVIATION if missing else OutcomeStatus.MATCH
        outcome = TaskOutcome(
            task_id=task.task_id,
            success=success,
            retries=retries,
            tool_calls=tool_calls,
            brain_calls=episode.counters.brain_calls,
            context_items=context_items,
            injected_tokens=built.tokens_used,
            irrelevant_injected_tokens=irrelevant_injected,
            guarded_success=bool(shaped and content_ok and success),
            experience_reused=experience_reused,
            termination=episode.termination.value,
            outcome_status=(OutcomeStatus.MATCH if success else first_attempt_status).value,
            first_attempt_wrong=bool(missing),
            rethink_rounds=episode.counters.rethink_rounds,
            negative_transfer=task.negative_transfer,
            detail=(
                f"missing={list(missing)}; refused={refused_feedback}; rethink={episode.counters.rethink_rounds}; "
                f"guards={[guard.value for guard in guards]}"
            ),
        )
        dispatch_keys = [intent.action_key]
        if missing:
            dispatch_keys.append(corrected.action_key)
        return TaskRun(
            outcome=outcome,
            first_attempt_status=first_attempt_status,
            evidence_ids=task.required_refs,
            raw_material_digest=self._raw_digest(task, inputs),
            selected_evidence=present,
            context_ref=built.record.id,
            dispatch_keys=tuple(dispatch_keys),
            episode_records=episode_records(
                episode, project_id=self.project_id, producer=self.producer, created_at=self._now()
            ),
        )

    def _advisory_experience_ids(self, records: Sequence[Record]) -> tuple[str, ...]:
        return tuple(record.id for record in records if same_enum(record.entity_type, EntityType.EXPERIENCE))

    def _raw_digest(self, task: GrowthTask, inputs: ArmInputs) -> str:
        payload = json.dumps(
            {
                "task": task.task_id,
                "required": list(task.required_refs),
                "arm": inputs.role.value,
                "advisory": list(inputs.advisory_refs),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _observe_selection(
        self,
        store: CanonicalStore,
        task: GrowthTask,
        *,
        policy_version: str | None,
        limits: Mapping[str, int],
    ) -> tuple[str, ...]:
        """Call the real ContextBuilder selector; never synthesize selection IDs."""
        builder = ContextBuilder(store, clock=self._now)
        built = build_context_once(
            builder,
            task=task,
            state_revision=STATE_REVISION,
            policy_version=policy_version,
            limits=limits,
        )
        return tuple(item.record_id for item in built.payload.l3_evidence)

    def _policy_limits_for_task(self, task: GrowthTask, mature: ArmInputs) -> tuple[str | None, Mapping[str, int]]:
        """Negative-transfer / out-of-scope tasks keep baseline limits (policy not applied)."""
        baseline = ArmInputs(role=ArmRole.FRESH).effective_limits()
        if task.negative_transfer:
            return None, baseline
        return mature.policy_version, mature.effective_limits()

    # ── arm 실행 ────────────────────────────────────
    def run_arm(
        self,
        inputs: ArmInputs,
        *,
        split: SplitRole = SplitRole.FINAL,
        extra_records: Sequence[Record] = (),
        arm_label: str | None = None,
    ) -> ArmResult:
        label = arm_label if arm_label is not None else inputs.role.value.lower()
        arm_root = self._arm_root(label)
        store = self._seed_store(arm_root, extra=extra_records)
        executor = self._executor_factory(arm_root)
        if not inputs.mechanisms.experience_advisory:
            # advisory mechanism을 끄면 축적 경험을 selection에 넘기지 않는다(기록 자체는 보존된다).
            inputs = replace(inputs, advisory_refs=())
        limits = inputs.effective_limits()
        advisory_ids = self._advisory_experience_ids(extra_records) if inputs.mechanisms.experience_advisory else ()
        started = self._now()
        runs = tuple(
            self._run_task(
                inputs,
                task,
                store=store,
                executor=executor,
                workdir=arm_root,
                limits=limits,
                advisory_experience_ids=advisory_ids,
            )
            for task in tasks_for(self.tasks, split)
        )
        finished = self._now()
        outcomes = tuple(run.outcome for run in runs)
        keys = [key for run in runs for key in run.dispatch_keys]
        safety = tuple(
            f"{run.outcome.task_id}: 거부된 요청이 해소되지 않은 상태로 ACTION이 진행됐다"
            for run in runs
            if run.outcome.rethink_rounds == 0 and "refused=1" in run.outcome.detail
        )
        manifest = RunManifest(
            experiment_id=self.spec.experiment_id,
            spec_digest=self.spec.digest(),
            arm=inputs.role,
            run_kind=self.spec.run_kind,
            seed=self.spec.seed,
            corpus_digest=self.spec.corpus_digest,
            split=split.value,
            task_ids=tuple(task.task_id for task in tasks_for(self.tasks, split)),
            brain_version=inputs.brain_version,
            policy_version=inputs.policy_version,
            advisory_refs=tuple(inputs.advisory_refs),
            mechanisms=inputs.mechanisms.as_mapping(),
            disabled_mechanisms=tuple(mechanism.value for mechanism in inputs.mechanisms.disabled()),
            cache_mode=self.spec.cache_mode,
            store_root=str(arm_root),
            source_head=self.source_head,
            started_at=started,
            finished_at=finished,
        )
        return ArmResult(
            manifest=manifest,
            outcomes=outcomes,
            metrics=_arm_metrics(outcomes),
            committed_records=len(store.list_committed(self.project_id)),
            dispatched_actions=sum(outcome.tool_calls for outcome in outcomes),
            duplicate_dispatches=len(keys) - len(set(keys)),
            safety_violations=safety,
            store_root=str(arm_root),
        )

    def run_fresh(self, *, split: SplitRole = SplitRole.FINAL) -> ArmResult:
        """Fresh: 축적 경험도 검증된 policy도 없다."""

        return self.run_arm(ArmInputs(role=ArmRole.FRESH), split=split, arm_label="fresh")

    def run_mature(self, phase: GrowthPhase, *, split: SplitRole = SplitRole.FINAL) -> ArmResult:
        """Mature: training split 경험 + validation을 통과한 policy만 더 있다."""

        inputs = ArmInputs(
            role=ArmRole.MATURE,
            policy_version=phase.policy_version,
            advisory_refs=phase.advisory_refs,
        )
        return self.run_arm(inputs, split=split, extra_records=phase.commit_records, arm_label="mature")

    # ── 성장 사슬 ───────────────────────────────────
    def growth_phase(self) -> GrowthPhase:
        """train split에서 경험을 축적하고 validation을 거쳐 policy를 활성화한다."""

        train = tasks_for(self.tasks, SplitRole.TRAIN)
        validation = tasks_for(self.tasks, SplitRole.VALIDATION)
        if len(train) < MIN_INDEPENDENT_EPISODES:
            raise GrowthBenchmarkError("train split 독립 episode가 2건 미만이다")
        if not validation:
            raise GrowthBenchmarkError("validation split이 없다")

        arm_root = self._arm_root("growth-train")
        store = self._seed_store(arm_root)
        executor = self._executor_factory(arm_root)
        baseline = ArmInputs(role=ArmRole.FRESH)
        train_runs = tuple(
            self._run_task(
                baseline,
                task,
                store=store,
                executor=executor,
                workdir=arm_root,
                limits=baseline.effective_limits(),
                advisory_experience_ids=(),
            )
            for task in train
        )
        observations = tuple(
            EpisodeObservation(
                episode_id=f"episode:train:{run.outcome.task_id}",
                task_id=run.outcome.task_id,
                raw_material_digest=run.raw_material_digest,
                evaluations=EpisodeEvaluations(
                    outcome=OutcomeEvaluation(
                        status=run.first_attempt_status,
                        expected=train[index].expected_outcome,
                        observed="appended (unverified)" if run.outcome.first_attempt_wrong else "appended",
                        delta="required config evidence 누락" if run.outcome.first_attempt_wrong else None,
                    ),
                    decision=DecisionEvaluation(
                        status=run.first_attempt_status,
                        available_at_decision=False,
                        reason="필수 config evidence가 당시 context에 없어 재시도가 필요했다",
                    ),
                    execution=ExecutionEvaluation(status=OutcomeStatus.MATCH, reason="도구는 append를 수락했다"),
                ),
                evidence_ids=run.evidence_ids,
                producer=self.producer,
            )
            for index, run in enumerate(train_runs)
        )
        summary = ExperienceEvaluator().aggregate(observations)
        candidates = CandidateStore()
        candidate = CandidateProposer().propose(
            summary,
            CandidateRequest(
                kind=CandidateKind.POLICY,
                rule="required config evidence가 빠지면 context depth를 한 단계 더 연다",
                scope="goal family + local environment",
                target=self.spec.policy_target,
                parameters=dict(self.spec.policy_parameters),
                trigger_sources=(TriggerSource.FAILURE,),
            ),
            project_id=self.project_id,
            producer=self.producer,
            created_at=self._now(),
        )
        candidates.append(candidate)

        advisory_refs = tuple(dict.fromkeys(ref for run in train_runs for ref in run.evidence_ids))
        advisory = advisory_experience_record(
            project_id=self.project_id, refs=advisory_refs, producer=self.producer, created_at=self._now()
        )
        provisional = f"{self.spec.experiment_id}-candidate"
        validation_inputs = ArmInputs(
            role=ArmRole.MATURE,
            policy_version=provisional,
            advisory_refs=advisory_refs,
        )
        validation_runs = tuple(
            self._run_task(
                validation_inputs,
                task,
                store=store,
                executor=executor,
                workdir=arm_root,
                limits=validation_inputs.effective_limits(),
                advisory_experience_ids=self._advisory_experience_ids((advisory,)),
            )
            for task in validation
        )
        validation_split_id = f"split_validation_{self.spec.experiment_id}"
        report = HeldOutValidator().validate(
            candidate,
            split=ValidationSplit(
                split_id=validation_split_id,
                role=ValidationRole.VALIDATION,
                task_ids=tuple(task.task_id for task in validation),
                source="registered fixture validation split",
                registered_at=self.spec.registered_at,
                manifest_digest=self.spec.corpus_digest,
            ),
            criterion=ValidationCriterion(
                experiment_id=self.spec.experiment_id,
                metric_name=METRIC_TASK_SUCCESS,
                minimum_value=self.spec.validation_minimum_success,
                registered_at=self.spec.registered_at,
                required_independent_episodes=MIN_INDEPENDENT_EPISODES,
                minimum_samples=len(validation),
            ),
            observations=tuple(
                ValidationObservation(task_id=run.outcome.task_id, success=run.outcome.success)
                for run in validation_runs
            ),
            generated_at=self._now(),
        )
        candidates.add_report(report)

        policy_store = PolicyStore()
        policy_version = policy_store.register(
            candidate,
            report,
            version=f"{self.spec.experiment_id}-v1",
            producer=self.producer,
            created_at=self._now(),
        )
        activation = policy_store.promote(
            policy_version.policy_id,
            version=policy_version.version,
            expected_active_version=None,
            actor=self.producer,
            reason="validation을 통과한 context depth policy",
            occurred_at=self._now(),
        )
        # R13: observe real post-policy selector output on the same frozen corpus+advisory store.
        if not store.is_committed(advisory.id):
            store.commit_records([advisory], message="growth advisory before selection observe")
        mature_select = ArmInputs(
            role=ArmRole.MATURE,
            policy_version=policy_version.version,
            advisory_refs=advisory_refs,
        )
        baseline_limits = ArmInputs(role=ArmRole.FRESH).effective_limits()
        trace_ids: list[str] = []
        first_shadow: tuple[str, ...] = ()
        first_actual: tuple[str, ...] = ()
        for index, (run, task) in enumerate(zip(train_runs, train)):
            episode_id = f"episode:trace:{task.task_id}"
            pinned = policy_store.pin(episode_id, policy_version.policy_id, pinned_at=self._now())
            shadow_selection = self._observe_selection(
                store,
                task,
                policy_version=None,
                limits=baseline_limits,
            )
            actual_policy, actual_limits = self._policy_limits_for_task(task, mature_select)
            # Episode pin freezes the version used for this observation (mid-episode promotion must not rewrite it).
            if actual_policy is not None:
                actual_policy = pinned.policy_version
            actual_selection = self._observe_selection(
                store,
                task,
                policy_version=actual_policy,
                limits=actual_limits,
            )
            observed_pin = policy_store.pin_of(episode_id)
            if observed_pin is None or observed_pin.policy_version != pinned.policy_version:
                raise GrowthBenchmarkError("episode policy pin changed during selection observe")
            outcome_ref = new_id(EntityType.OUTCOME) if run.outcome.success else None
            trace = policy_store.record_behavior_change(
                policy_id=policy_version.policy_id,
                version=pinned.policy_version,
                task_id=task.task_id,
                shadow_selection=shadow_selection,
                actual_selection=actual_selection,
                producer=self.producer,
                recorded_at=self._now(),
                outcome_ref=outcome_ref,
            )
            trace_ids.append(trace.trace_id)
            if index == 0:
                first_shadow = shadow_selection
                first_actual = actual_selection
        commit_records = (advisory, *candidates.records, *policy_store.records)
        return GrowthPhase(
            candidate_id=candidate.candidate_id,
            candidate_parameters=dict(self.spec.policy_parameters),
            independent_episode_count=summary.independent_episode_count,
            validation_report_id=report.report_id,
            validation_split_id=validation_split_id,
            validation_passed=report.passed,
            policy_id=policy_version.policy_id,
            policy_version=policy_version.version,
            activation_id=activation.activation_id,
            behavior_trace_ids=tuple(trace_ids),
            shadow_selection=first_shadow,
            actual_selection=first_actual,
            advisory_refs=advisory_refs,
            train_task_ids=tuple(task.task_id for task in train),
            commit_records=commit_records,
        )

    # ── 비교·ablation ─────────────────────────────────
    def compare(self, fresh: ArmResult, mature: ArmResult, phase: GrowthPhase) -> GrowthComparison:
        primary = self.spec.primary_improvement_metric
        direction = self.spec.metric(primary).direction
        primary_fresh = fresh.metrics.value(primary) or 0.0
        primary_mature = mature.metrics.value(primary) or 0.0
        success_fresh = fresh.metrics.value(METRIC_TASK_SUCCESS) or 0.0
        success_mature = mature.metrics.value(METRIC_TASK_SUCCESS) or 0.0
        labelled = tuple(task.task_id for task in tasks_for(self.tasks, SplitRole.FINAL) if task.negative_transfer)
        decrease = sum(
            1
            for task_id in labelled
            if fresh.task_outcome(task_id).success and not mature.task_outcome(task_id).success
        )
        gain = sum(
            1
            for task_id in labelled
            if mature.task_outcome(task_id).success and not fresh.task_outcome(task_id).success
        )
        success_noninferior = success_mature + self.spec.success_noninferiority_margin >= success_fresh
        primary_improved = (
            primary_mature < primary_fresh if direction == "lower_better" else primary_mature > primary_fresh
        )
        negative_transfer_absent = decrease <= self.spec.negative_transfer_max_success_decrease
        safety_clean = not mature.safety_violations
        duplicate_absent = mature.duplicate_dispatches == 0
        reasons: list[str] = []
        if not success_noninferior:
            reasons.append(f"success 비열등성 실패: mature {success_mature} < fresh {success_fresh}")
        if not primary_improved:
            reasons.append(f"사전 지정 metric({primary}) 개선 없음: fresh {primary_fresh} → mature {primary_mature}")
        if not negative_transfer_absent:
            reasons.append(f"negative transfer {decrease}건")
        if not safety_clean:
            reasons.append(f"safety violation {len(mature.safety_violations)}건")
        if not duplicate_absent:
            reasons.append(f"중복 dispatch {mature.duplicate_dispatches}건")
        verdict = GrowthVerdict(
            success_noninferior=success_noninferior,
            primary_metric_improved=primary_improved,
            negative_transfer_absent=negative_transfer_absent,
            safety_clean=safety_clean,
            duplicate_dispatch_absent=duplicate_absent,
            passed=success_noninferior
            and primary_improved
            and negative_transfer_absent
            and safety_clean
            and duplicate_absent,
            reasons=tuple(reasons),
        )
        return GrowthComparison(
            spec_digest=self.spec.digest(),
            meta=phase,
            fresh=fresh,
            mature=mature,
            primary_metric=primary,
            primary_fresh=primary_fresh,
            primary_mature=primary_mature,
            success_fresh=success_fresh,
            success_mature=success_mature,
            negative_transfer_delta=decrease - gain,
            verdict=verdict,
        )

    def _mechanism_used(self, mechanism: Mechanism, arm: ArmResult) -> bool:
        if same_enum(mechanism, Mechanism.CONTEXT_BUILDER):
            return any(outcome.context_items > 0 for outcome in arm.outcomes)
        if same_enum(mechanism, Mechanism.EXPERIENCE_ADVISORY):
            return bool(arm.manifest.advisory_refs) and (arm.metrics.value(METRIC_EXPERIENCE_REUSE) or 0.0) > 0
        if same_enum(mechanism, Mechanism.TARGETED_REREASONING):
            return any(outcome.rethink_rounds > 0 for outcome in arm.outcomes)
        if same_enum(mechanism, Mechanism.EXPERIENCE):
            return bool(arm.manifest.advisory_refs)
        if same_enum(mechanism, Mechanism.RISK_SHAPING):
            return (arm.metrics.value(METRIC_GUARDED_SUCCESS) or 0.0) > 0
        return arm.manifest.policy_version is not None

    def run_ablation(self, mechanism: Mechanism, *, phase: GrowthPhase, baseline: ArmResult) -> AblationResult:
        """mechanism 하나만 끈다. baseline에서 쓰이지 않은 mechanism이면 NOT_RUN으로 남긴다."""

        if not self._mechanism_used(mechanism, baseline):
            return AblationResult(
                mechanism=mechanism,
                status=AblationStatus.NOT_RUN,
                reason="baseline mature 실행에서 이 mechanism이 쓰이지 않았다 — no-op 비교는 유효성 증거가 아니다",
            )
        mechanisms = baseline.manifest.mechanisms
        inputs = ArmInputs(
            role=ArmRole.ABLATION,
            mechanisms=MechanismSet(**{key.lower(): value for key, value in mechanisms.items()}).without(mechanism),
            policy_version=phase.policy_version,
            advisory_refs=phase.advisory_refs,
            disabled_mechanism=mechanism,
        )
        extra = phase.commit_records
        if same_enum(mechanism, Mechanism.EXPERIENCE):
            extra = tuple(
                record for record in phase.commit_records if not same_enum(record.entity_type, EntityType.EXPERIENCE)
            )
            inputs = replace(inputs, advisory_refs=())
        arm = self.run_arm(
            inputs,
            extra_records=extra,
            arm_label=f"ablation-{mechanism.value.lower()}",
        )
        primary = self.spec.primary_improvement_metric
        dependent = tuple(
            other
            for other in Mechanism
            if other is not mechanism and self._mechanism_used(other, baseline) and not self._mechanism_used(other, arm)
        )
        return AblationResult(
            mechanism=mechanism,
            status=AblationStatus.MEASURED,
            reason="mechanism 하나만 끈 비교다 — policy/version/task/code는 고정이다",
            arm=arm,
            delta_primary=(arm.metrics.value(primary) or 0.0) - (baseline.metrics.value(primary) or 0.0),
            delta_success=(arm.metrics.value(METRIC_TASK_SUCCESS) or 0.0)
            - (baseline.metrics.value(METRIC_TASK_SUCCESS) or 0.0),
            dependent_mechanisms=dependent,
        )

    def run_growth_demo(self) -> GrowthDemo:
        phase = self.growth_phase()
        fresh = self.run_fresh()
        mature = self.run_mature(phase)
        comparison = self.compare(fresh, mature, phase)
        ablations = tuple(self.run_ablation(mechanism, phase=phase, baseline=mature) for mechanism in Mechanism)
        return GrowthDemo(spec=self.spec, comparison=comparison, ablations=ablations)


__all__ = [
    "AUTHORITY_REVISION",
    "BASELINE_CONTEXT_LIMITS",
    "CONTEXT_DISCLOSURE",
    "DEFAULT_SEED",
    "FIXTURE_BRAIN_VERSION",
    "MATURE_CONTEXT_STEP",
    "METRIC_BRAIN_CALLS",
    "METRIC_CONTEXT_POLLUTION",
    "METRIC_CONTEXT_TOKENS",
    "METRIC_EXPERIENCE_REUSE",
    "METRIC_FAILURE_REPETITION",
    "METRIC_GUARDED_SUCCESS",
    "METRIC_LATENCY_P50",
    "METRIC_NEGATIVE_TRANSFER",
    "METRIC_REOPEN",
    "METRIC_TASK_SUCCESS",
    "METRIC_TOTAL_RETRIES",
    "METRIC_TOTAL_TOOL_CALLS",
    "AblationResult",
    "AblationStatus",
    "ArmInputs",
    "ArmMetrics",
    "ArmResult",
    "ArmRole",
    "BenchmarkSpec",
    "ExecutorFactory",
    "FixtureCategory",
    "FixtureThink",
    "GrowthBenchmarkError",
    "GrowthComparison",
    "GrowthDemo",
    "GrowthPhase",
    "GrowthRunner",
    "GrowthTask",
    "GrowthVerdict",
    "Mechanism",
    "MechanismSet",
    "MetricSpec",
    "Mode",
    "RunKind",
    "RunManifest",
    "SplitRole",
    "TaskOutcome",
    "TaskRun",
    "advisory_experience_record",
    "build_context_once",
    "canonical_id",
    "corpus_digest",
    "corpus_records",
    "default_corpus_tasks",
    "default_metrics",
    "default_spec",
    "plan_readiness",
    "risk_for_task",
    "split_ids",
    "tasks_for",
]
