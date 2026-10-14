"""Typed live model boundary and explicitly scripted contract test port."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from antigravity_k.engine.cognitive.actions import ToolExecutorPort
from antigravity_k.engine.cognitive.growth import ArmRole, GrowthTask, MechanismSet
from antigravity_k.engine.cognitive.live_learning import LiveLearning
from antigravity_k.engine.cognitive.live_pilot import (
    LiveTrialOutcome,
    LiveTrialRequest,
    LiveTrialTimeout,
    ProviderAttestation,
)
from antigravity_k.engine.cognitive.models import Producer
from antigravity_k.engine.cognitive.runtime import EpisodeDelta, EpisodePlan, RequestFeedback, ThinkOutcome
from antigravity_k.engine.cognitive.store import CanonicalStore


@dataclass(frozen=True, slots=True)
class ModelTask:
    """Model-visible task; evaluator bytes and expected outcomes are private."""

    task_id: str
    evidence: tuple[str, ...]
    policy_version: str | None
    context_json: str = ""


@dataclass(frozen=True, slots=True)
class ModelChoice:
    """모델이 고른 실행 의도. 정답 label을 몰래 넣지 않는다."""

    append_content: str
    target_name: str | None = None  # None → task_id.txt inside arm root
    expand_missing: bool = False
    detail: str = ""
    tokens: int = 0
    ground_refs: tuple[str, ...] = ()


@runtime_checkable
class ModelPort(Protocol):
    attestation: ProviderAttestation

    def choose(
        self,
        request: LiveTrialRequest,
        task: ModelTask,
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
        task: ModelTask,
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
            append_content=f"{task.task_id} appended",
            expand_missing=bool(missing_refs),
            detail="scripted correct",
            ground_refs=task.evidence,
        )


@dataclass
class PolicyGateState:
    """TRAIN → VALIDATION → promote. VALIDATION 실패 시 FINAL Mature에 미적용."""

    train_successes: int = 0
    train_total: int = 0
    validation_successes: int = 0
    validation_total: int = 0
    validation_minimum: float = 0.5
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
    judgment_ref: str | None = None
    plan: EpisodePlan | None = None
    calls: list[str] = field(default_factory=list)

    def think(self, *, context_ref: str, request_signature: str, attempt: int) -> ThinkOutcome:
        self.calls.append(f"think:{attempt}")
        return ThinkOutcome(
            judgment_ref=self.judgment_ref or f"judgment:live:{self.task.task_id}:{attempt}",
            requests=(),
            delta=EpisodeDelta(judgment=True, action=True),
            detail=self.choice.detail or "model-driven",
            plan=self.plan,
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
        self.calls.append(f"rethink:{round_index}")
        return ThinkOutcome(
            judgment_ref=f"judgment:live:{self.task.task_id}:re:{round_index}",
            requests=(),
            delta=EpisodeDelta(action=True, description="live rethink"),
        )


class LiveTrialHost(Protocol):
    workspace: Path
    model: ModelPort
    tasks: Sequence[GrowthTask]
    mechanisms: MechanismSet
    policy_gate: PolicyGateState
    producer: Producer
    project_id: str
    learning: LiveLearning

    @property
    def executor_factory(self) -> Callable[[Path], ToolExecutorPort]: ...

    def arm_root(self, arm: ArmRole | str) -> Path: ...
    def _task(self, task_id: str) -> GrowthTask: ...
    def _seed(self, arm_root: Path) -> CanonicalStore: ...
    def _policy_for(self, request: LiveTrialRequest) -> str | None: ...
    def context_limits(self, request: LiveTrialRequest) -> Mapping[str, int]: ...
    def run_trial(self, request: LiveTrialRequest) -> LiveTrialOutcome: ...
