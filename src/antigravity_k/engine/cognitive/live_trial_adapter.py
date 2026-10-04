"""R18 — LiveTrialPort adapter: model choice → real tool/store effects (no canned success).

Uses existing CanonicalStore, ToolExecutorPort (fixture_tool_port), ActionDispatcher, and
CognitiveRuntime. Does not invent a parallel agent runtime. FixtureThink / GrowthRunner
oracle content is not used for live outcomes: append bytes come from ModelPort only.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from antigravity_k.engine.cognitive.actions import ToolExecutorPort
from antigravity_k.engine.cognitive.growth import (
    ArmInputs,
    ArmRole,
    GrowthBenchmarkError,
    GrowthTask,
    MechanismSet,
    SplitRole,
    canonical_id,
    corpus_records,
    default_corpus_tasks,
)
from antigravity_k.engine.cognitive.live_learning import LiveLearning
from antigravity_k.engine.cognitive.live_pilot import (
    LiveTrialOutcome,
    LiveTrialRequest,
    ProviderAttestation,
)
from antigravity_k.engine.cognitive.live_training import train_validation
from antigravity_k.engine.cognitive.live_trial_execution import execute_live_trial
from antigravity_k.engine.cognitive.live_trial_types import (
    ModelChoice,
    ModelDrivenThink,
    ModelPort,
    PolicyGateState,
    ScriptedModelPort,
)
from antigravity_k.engine.cognitive.models import (
    GoalPayload,
    PolicyTarget,
    Producer,
    ProducerKind,
    same_enum,
)
from antigravity_k.engine.cognitive.store import CanonicalStore


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


@dataclass
class LiveTrialAdapter:
    """LiveTrialPort: arm별 분리 root + ModelPort + 실제 tool/store."""

    workspace: Path
    model: ModelPort
    executor_factory: Callable[[Path], ToolExecutorPort]
    tasks: Sequence[GrowthTask] = field(default_factory=default_corpus_tasks)
    mechanisms: MechanismSet = field(default_factory=MechanismSet)
    policy_gate: PolicyGateState = field(default_factory=PolicyGateState)
    producer: Producer = field(default_factory=lambda: Producer(kind=ProducerKind.BODY, actor_id="body:live-trial"))
    project_id: str = field(default_factory=lambda: canonical_id("project", "growth-demo"))
    attestation: ProviderAttestation = field(init=False)
    learning: LiveLearning = field(init=False)

    def __post_init__(self) -> None:
        if not all(
            (
                self.mechanisms.context_builder,
                self.mechanisms.experience,
                self.mechanisms.experience_advisory,
                self.mechanisms.risk_shaping,
            )
        ):
            raise GrowthBenchmarkError("Live adapter does not support context/experience/advisory/risk ablations")
        self.learning = LiveLearning(self.project_id, self.producer)
        self.workspace = Path(self.workspace).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        (self.workspace / "fresh").mkdir(exist_ok=True)
        (self.workspace / "mature").mkdir(exist_ok=True)
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
        records = []
        for record in corpus_records(self.tasks):
            if isinstance(record.payload, GoalPayload):
                record = record.model_copy(
                    update={
                        "payload": record.payload.model_copy(
                            update={
                                "statement": "Synthetic append task: append the task ID, a space, and the word appended",
                                "success_criteria": ("Execute the public append instruction in the isolated output",),
                            }
                        )
                    }
                )
            records.append(record)
        missing = [record for record in records if not store.is_committed(record.id)]
        if missing:
            store.commit_records(missing, message=f"live corpus seed ({arm_root.name})")
        fixtures = arm_root / "fixtures"
        fixtures.mkdir(exist_ok=True)
        return store

    def _policy_for(self, request: LiveTrialRequest) -> str | None:
        if same_enum(request.arm, ArmRole.FRESH) or not self.mechanisms.governance_learning:
            return None
        if self._task(request.task_id).negative_transfer:
            return None
        # Mature FINAL may only see promoted policy
        if request.split == SplitRole.FINAL.value or request.split == "FINAL":
            active = self.learning.policies.active_policy(PolicyTarget.CONTEXT_DEPTH)
            return active.version if active else None
        if request.split in {SplitRole.VALIDATION.value, "VALIDATION"}:
            return self.policy_gate.candidate_version
        return request.policy_version

    def context_limits(self, request: LiveTrialRequest) -> Mapping[str, int]:
        limits = dict(ArmInputs(role=request.arm, mechanisms=self.mechanisms).effective_limits())
        version = self._policy_for(request)
        if not version or not self.learning.advisory_refs:
            return limits
        active = self.learning.policies.active_policy(PolicyTarget.CONTEXT_DEPTH)
        parameters = active.parameters if active else self.learning.candidates.candidates[-1].parameters
        depth = int(parameters.get("extra_depth", 0))
        limits["l2_limit"] += depth
        limits["l3_limit"] += depth
        return limits

    def run_train_validation(self, *, force_validation_fail: bool | None = None) -> PolicyGateState:
        return train_validation(self, force_validation_fail)

    def run_trial(self, request: LiveTrialRequest) -> LiveTrialOutcome:
        return execute_live_trial(self, request)


__all__ = [
    "LiveTrialAdapter",
    "ModelChoice",
    "ModelDrivenThink",
    "ModelPort",
    "PolicyGateState",
    "ScriptedModelPort",
]
