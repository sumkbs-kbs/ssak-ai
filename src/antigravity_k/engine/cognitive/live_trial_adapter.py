"""R18 — LiveTrialPort adapter: model choice → real tool/store effects (no canned success).

Uses existing CanonicalStore, ToolExecutorPort (fixture_tool_port), ActionDispatcher, and
CognitiveRuntime. Does not invent a parallel agent runtime. FixtureThink / GrowthRunner
oracle content is not used for live outcomes: append bytes come from ModelPort only.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

from antigravity_k.engine.cognitive.action_types import ActionObservation
from antigravity_k.engine.cognitive.actions import ActionDispatcher
from antigravity_k.engine.cognitive.context import ContextBuilder
from antigravity_k.engine.cognitive.governance import GovernanceGate
from antigravity_k.engine.cognitive.growth import (
    AUTHORITY_REVISION,
    DECISION_REVISION,
    STATE_REVISION,
    ArmInputs,
    ArmRole,
    GrowthTask,
    MechanismSet,
    SplitRole,
    append_intent,
    build_context_once,
    canonical_id,
    corpus_records,
    default_corpus_tasks,
    plan_readiness,
    risk_for_task,
    tasks_for,
)
from antigravity_k.engine.cognitive.live_pilot import (
    LiveTrialOutcome,
    LiveTrialRequest,
    LiveTrialTimeout,
    ProviderAttestation,
)
from antigravity_k.engine.cognitive.models import Producer, ProducerKind
from antigravity_k.engine.cognitive.runtime import (
    CognitiveRuntime,
    EpisodeBudget,
    EpisodeDelta,
    EpisodePlan,
    EpisodeRequest,
    ThinkOutcome,
)
from antigravity_k.engine.cognitive.store import CanonicalStore
from antigravity_k.engine.growth_fixture_tools import fixture_tool_port


@dataclass(frozen=True, slots=True)
class ModelChoice:
    """모델이 고른 실행 의도. 정답 label을 몰래 넣지 않는다."""

    append_content: str
    target_name: str | None = None  # None → task_id.txt inside arm root
    expand_missing: bool = False
    detail: str = ""


@runtime_checkable
class ModelPort(Protocol):
    attestation: ProviderAttestation

    def choose(
        self,
        request: LiveTrialRequest,
        task: GrowthTask,
        *,
        missing_refs: tuple[str, ...],
        workspace: Path,
    ) -> ModelChoice: ...


@dataclass
class ScriptedModelPort:
    """시험용 모델. correct/wrong/timeout/outside 행동을 명시한다."""

    mode: str = "correct"
    attestation: ProviderAttestation = field(
        default_factory=lambda: ProviderAttestation(
            provider_id="scripted-local",
            model_id="scripted-v1",
            model_snapshot="snapshot:scripted-1",
            decoding="temperature=0",
            hardware="test-host",
            snapshot_pinned=True,
        )
    )
    calls: int = 0

    def choose(
        self,
        request: LiveTrialRequest,
        task: GrowthTask,
        *,
        missing_refs: tuple[str, ...],
        workspace: Path,
    ) -> ModelChoice:
        self.calls += 1
        if self.mode == "timeout":
            raise LiveTrialTimeout("scripted model timeout")
        if self.mode == "outside":
            return ModelChoice(
                append_content="escaped",
                target_name=str((workspace.parent / "OUTSIDE_JAIL.txt").resolve()),
                detail="attempt outside workspace",
            )
        if self.mode == "wrong":
            return ModelChoice(
                append_content=f"WRONG:{task.task_id}",
                expand_missing=False,
                detail="deliberately wrong append",
            )
        # correct: emit the registered expected append bytes (model "knows" them)
        return ModelChoice(
            append_content=task.append_content,
            expand_missing=bool(missing_refs),
            detail="scripted correct",
        )


@dataclass
class PolicyGateState:
    """TRAIN → VALIDATION → promote. VALIDATION 실패 시 FINAL Mature에 미적용."""

    train_successes: int = 0
    train_total: int = 0
    validation_successes: int = 0
    validation_total: int = 0
    validation_minimum: float = 0.75
    promoted_version: str | None = None
    candidate_version: str = "live-candidate-v1"
    force_validation_fail: bool = False

    @property
    def validation_passed(self) -> bool:
        if self.force_validation_fail:
            return False
        if self.validation_total == 0:
            return False
        return (self.validation_successes / self.validation_total) >= self.validation_minimum

    def maybe_promote(self) -> str | None:
        if self.validation_passed:
            self.promoted_version = f"{self.candidate_version}-promoted"
        else:
            self.promoted_version = None
        return self.promoted_version


@dataclass
class ModelDrivenThink:
    """ModelPort 선택만 반영한다. task.append_content로 몰래 성공시키지 않는다."""

    task: GrowthTask
    choice: ModelChoice
    calls: list[str] = field(default_factory=list)

    def think(self, *, context_ref: str, request_signature: str, attempt: int) -> ThinkOutcome:
        self.calls.append(f"think:{attempt}")
        return ThinkOutcome(
            judgment_ref=f"judgment:live:{self.task.task_id}:{attempt}",
            requests=(),
            delta=EpisodeDelta(judgment=True, action=True),
            detail=self.choice.detail or "model-driven",
        )

    def rethink(
        self,
        *,
        previous_judgment_ref: str,
        feedback_refs: Sequence[str],
        affected_grounds: Sequence[str],
        round_index: int,
    ) -> ThinkOutcome:
        self.calls.append(f"rethink:{round_index}")
        return ThinkOutcome(
            judgment_ref=f"judgment:live:{self.task.task_id}:re:{round_index}",
            requests=(),
            delta=EpisodeDelta(action=True, description="live rethink"),
        )


def _root_digest(path: Path) -> str:
    """arm root의 파일 상대경로·크기·내용 해시로 독립성 확인용 digest."""

    if not path.exists():
        return "sha256:" + hashlib.sha256(b"").hexdigest()
    chunks: list[str] = []
    for file in sorted(path.rglob("*")):
        if not file.is_file():
            continue
        rel = str(file.relative_to(path))
        digest = hashlib.sha256(file.read_bytes()).hexdigest()
        chunks.append(f"{rel}:{file.stat().st_size}:{digest}")
    payload = "\n".join(chunks).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _resolve_target(workspace: Path, arm_root: Path, task: GrowthTask, choice: ModelChoice) -> Path:
    if choice.target_name is None:
        return arm_root / f"{task.task_id}.txt"
    candidate = Path(choice.target_name)
    if not candidate.is_absolute():
        candidate = (arm_root / candidate).resolve()
    else:
        candidate = candidate.resolve()
    return candidate


def _inside_workspace(workspace: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(workspace.resolve())
        return True
    except ValueError:
        return False


@dataclass
class LiveTrialAdapter:
    """LiveTrialPort: arm별 분리 root + ModelPort + 실제 tool/store."""

    workspace: Path
    model: ModelPort
    tasks: Sequence[GrowthTask] = field(default_factory=default_corpus_tasks)
    mechanisms: MechanismSet = field(default_factory=MechanismSet)
    policy_gate: PolicyGateState = field(default_factory=PolicyGateState)
    producer: Producer = field(default_factory=lambda: Producer(kind=ProducerKind.BODY, actor_id="body:live-trial"))
    project_id: str = field(default_factory=lambda: canonical_id("project", "live-trial"))
    attestation: ProviderAttestation | None = None
    _effects_outside: int = 0

    def __post_init__(self) -> None:
        self.workspace = Path(self.workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        (self.workspace / "fresh").mkdir(exist_ok=True)
        (self.workspace / "mature").mkdir(exist_ok=True)
        if self.attestation is None:
            self.attestation = self.model.attestation

    def arm_root(self, arm: ArmRole | str) -> Path:
        name = arm.value.lower() if isinstance(arm, ArmRole) else str(arm).lower()
        if name == "fresh":
            return self.workspace / "fresh"
        if name == "mature":
            return self.workspace / "mature"
        path = self.workspace / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def root_digest(self, arm: ArmRole | str) -> str:
        return _root_digest(self.arm_root(arm))

    def _task(self, task_id: str) -> GrowthTask:
        for task in self.tasks:
            if task.task_id == task_id:
                return task
        raise KeyError(f"unknown task_id: {task_id}")

    def _seed(self, arm_root: Path) -> CanonicalStore:
        store = CanonicalStore(arm_root / "store", git_enabled=False)
        missing = [record for record in corpus_records(self.tasks) if not store.is_committed(record.id)]
        if missing:
            store.commit_records(missing, message=f"live corpus seed ({arm_root.name})")
        fixtures = arm_root / "fixtures"
        fixtures.mkdir(exist_ok=True)
        return store

    def _policy_for(self, request: LiveTrialRequest) -> str | None:
        if request.arm is ArmRole.FRESH or request.arm.value == "FRESH":
            return None
        # Mature FINAL may only see promoted policy
        if request.split == SplitRole.FINAL.value or request.split == "FINAL":
            return self.policy_gate.promoted_version
        if request.split in {SplitRole.VALIDATION.value, "VALIDATION"}:
            return self.policy_gate.candidate_version
        return request.policy_version

    def run_train_validation(
        self,
        *,
        force_validation_fail: bool | None = None,
    ) -> PolicyGateState:
        """TRAIN 경험 후 VALIDATION. 실패하면 promote하지 않는다 (R18-A2)."""

        if force_validation_fail is not None:
            self.policy_gate.force_validation_fail = force_validation_fail
        train = tasks_for(self.tasks, SplitRole.TRAIN)
        validation = tasks_for(self.tasks, SplitRole.VALIDATION)
        self.policy_gate.train_total = 0
        self.policy_gate.train_successes = 0
        for index, task in enumerate(train):
            req = LiveTrialRequest(
                task_id=task.task_id,
                split=SplitRole.TRAIN.value,
                arm=ArmRole.MATURE,
                trial_index=index,
                order=__import__(
                    "antigravity_k.engine.cognitive.live_pilot", fromlist=["TrialOrder"]
                ).TrialOrder.FRESH_FIRST,
                policy_version=None,
                advisory_refs=(),
            )
            out = self.run_trial(req)
            self.policy_gate.train_total += 1
            self.policy_gate.train_successes += int(out.success)
        self.policy_gate.validation_total = 0
        self.policy_gate.validation_successes = 0
        for index, task in enumerate(validation):
            req = LiveTrialRequest(
                task_id=task.task_id,
                split=SplitRole.VALIDATION.value,
                arm=ArmRole.MATURE,
                trial_index=index,
                order=__import__(
                    "antigravity_k.engine.cognitive.live_pilot", fromlist=["TrialOrder"]
                ).TrialOrder.FRESH_FIRST,
                policy_version=self.policy_gate.candidate_version,
                advisory_refs=(),
            )
            out = self.run_trial(req)
            self.policy_gate.validation_total += 1
            # force fail overrides observed successes for promotion gate
            if not self.policy_gate.force_validation_fail and out.success:
                self.policy_gate.validation_successes += 1
        self.policy_gate.maybe_promote()
        return self.policy_gate

    def run_trial(self, request: LiveTrialRequest) -> LiveTrialOutcome:
        started = time.perf_counter()
        task = self._task(request.task_id)
        arm_root = self.arm_root(request.arm)
        store = self._seed(arm_root)
        # local provider check immediately before execute
        _ = self.model.attestation
        policy_version = self._policy_for(request)
        builder = ContextBuilder(store, clock=lambda: datetime.now(tz=UTC))
        built = build_context_once(
            builder,
            task=task,
            state_revision=STATE_REVISION,
            policy_version=policy_version,
            limits=ArmInputs(role=ArmRole.FRESH).effective_limits(),
        )
        present = tuple(item.record_id for item in built.payload.l3_evidence)
        missing = tuple(ref for ref in task.required_refs if ref not in present)

        choice = self.model.choose(request, task, missing_refs=missing, workspace=self.workspace)
        target = _resolve_target(self.workspace, arm_root, task, choice)
        if not _inside_workspace(self.workspace, target):
            self._effects_outside += 0  # explicit: zero effects
            return LiveTrialOutcome(
                success=False,
                retries=0,
                tool_calls=0,
                brain_calls=1,
                tokens=32,
                latency_ms=(time.perf_counter() - started) * 1000,
                safety_violation="target outside allowed workspace",
                detail=f"refused outside path: {target}",
                error_category="WORKSPACE_JAIL",
            )

        executor = fixture_tool_port(arm_root)
        risk = risk_for_task(task)
        intent = append_intent(
            task,
            attempt=1,
            content=choice.append_content,  # model bytes only — never swap to oracle
            target=target,
            risk=risk,
            readiness=None,
            policy_version=policy_version,
            guards=(),
        )
        readiness = plan_readiness(
            task,
            action_digest=intent.args_digest(),
            risk=risk,
            policy_version=policy_version,
            limits=(),
        )
        intent = replace(intent, readiness=readiness)
        think = ModelDrivenThink(task=task, choice=choice)
        runtime = CognitiveRuntime(
            think=think,
            rethink=think if self.mechanisms.targeted_rereasoning else None,
            actions=ActionDispatcher(port=executor, clock=lambda: datetime.now(tz=UTC)),
            governance=GovernanceGate(),
            budget=EpisodeBudget(expansion_rounds=2),
            project_id=self.project_id,
            producer=self.producer,
            clock=lambda: datetime.now(tz=UTC),
        )
        plan = EpisodePlan(
            readiness=readiness,
            action=intent,
            expected_outcome=task.expected_outcome,
            observation=ActionObservation(observed=True, succeeded=True, detail="live observe"),
        )
        episode = runtime.run(
            EpisodeRequest(
                episode_id=f"episode:live:{request.arm.value}:{task.task_id}:{request.trial_index}",
                context_ref=built.record.id,
                goal_ref=task.goal_ref,
                expected_outcome=task.expected_outcome,
                simple=True,
                decision_revision=DECISION_REVISION,
                state_revision=STATE_REVISION,
                authority_revision=AUTHORITY_REVISION,
                policy_version=policy_version,
                plan=plan,
            )
        )
        # Persist a tiny policy marker for mature independence digest when promoted
        if policy_version and request.arm is ArmRole.MATURE:
            marker = arm_root / "policy" / f"{policy_version}.json"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(
                json.dumps({"policy_version": policy_version, "task": task.task_id}),
                encoding="utf-8",
            )

        written = target.read_text(encoding="utf-8") if target.exists() else ""
        # success only if model-produced bytes match registered expected append
        success = written == task.append_content
        retries = max(0, len(think.calls) - 1)
        latency_ms = (time.perf_counter() - started) * 1000
        tool_calls = 1 if target.exists() else 0
        return LiveTrialOutcome(
            success=success,
            retries=retries,
            tool_calls=tool_calls,
            brain_calls=len(think.calls) or 1,
            tokens=64,
            latency_ms=latency_ms,
            detail=(
                f"policy={policy_version!r}; written={written!r}; "
                f"expected={task.append_content!r}; episode={getattr(episode, 'termination', episode)}"
            ),
        )


__all__ = [
    "LiveTrialAdapter",
    "ModelChoice",
    "ModelDrivenThink",
    "ModelPort",
    "PolicyGateState",
    "ScriptedModelPort",
]
