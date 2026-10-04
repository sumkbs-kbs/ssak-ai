"""R18 — LiveTrialPort adapter: model choice → real tool/store effects (no canned success).

Uses existing CanonicalStore, ToolExecutorPort (fixture_tool_port), ActionDispatcher, and
CognitiveRuntime. Does not invent a parallel agent runtime. FixtureThink / GrowthRunner
oracle content is not used for live outcomes: append bytes come from ModelPort only.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

from antigravity_k.engine.cognitive.actions import ActionDispatcher
from antigravity_k.engine.cognitive.context import ContextBuilder
from antigravity_k.engine.cognitive.experience import ExecutionEvaluation
from antigravity_k.engine.cognitive.governance import GovernanceGate
from antigravity_k.engine.cognitive.growth import (
    AUTHORITY_REVISION,
    DECISION_REVISION,
    STATE_REVISION,
    ArmInputs,
    ArmRole,
    GrowthTask,
    SplitRole,
    append_intent,
    build_context_once,
    plan_readiness,
    risk_for_task,
)
from antigravity_k.engine.cognitive.live_context import expanded_context, model_task
from antigravity_k.engine.cognitive.live_pilot import (
    LiveTrialOutcome,
    LiveTrialRequest,
)
from antigravity_k.engine.cognitive.live_provenance import LiveProvenance
from antigravity_k.engine.cognitive.live_trial_types import (
    LiveTrialHost,
    ModelChoice,
    ModelDrivenThink,
)
from antigravity_k.engine.cognitive.models import (
    OutcomeStatus,
    PolicyTarget,
)
from antigravity_k.engine.cognitive.runtime import (
    CognitiveRuntime,
    EpisodeBudget,
    EpisodePlan,
    EpisodeRequest,
)


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


def execute_live_trial(adapter: LiveTrialHost, request: LiveTrialRequest) -> LiveTrialOutcome:
    started = time.perf_counter()
    task = adapter._task(request.task_id)
    arm_root = adapter.arm_root(request.arm)
    trial_root = arm_root / "trials" / request.split / task.task_id / str(request.trial_index)
    trial_root.mkdir(parents=True, exist_ok=False)
    store = adapter._seed(arm_root)
    # local provider check immediately before execute
    _ = adapter.model.attestation
    policy_version = adapter._policy_for(request)
    builder = ContextBuilder(store, clock=lambda: datetime.now(tz=UTC))
    state_revision = max(STATE_REVISION, builder.projection_state().last_event_sequence)
    built = build_context_once(
        builder,
        task=task,
        state_revision=state_revision,
        policy_version=policy_version,
        limits=adapter.context_limits(request),
    )
    store.commit_records([built.record], message="live model context")
    present = tuple(item.record_id for item in built.payload.l3_evidence)
    missing = tuple(ref for ref in task.required_refs if ref not in present)

    context_record = built.record
    visible = model_task(task.task_id, context_record, store)
    choice = adapter.model.choose(request, visible, missing_refs=missing, workspace=trial_root)
    brain_calls, tokens = 1, choice.tokens
    if choice.expand_missing and missing and adapter.mechanisms.targeted_rereasoning:
        context_record = expanded_context(context_record, missing, store)
        store.commit_records([context_record], message="actual expanded live context")
        visible = model_task(task.task_id, context_record, store)
        expanded = visible.evidence
        choice = adapter.model.choose(
            request,
            visible,
            missing_refs=tuple(ref for ref in missing if ref not in expanded),
            workspace=trial_root,
        )
        brain_calls += 1
        tokens += choice.tokens
    target = _resolve_target(adapter.workspace, trial_root, task, choice)
    if not _inside_workspace(trial_root, target):
        return LiveTrialOutcome(
            effective_policy_version=policy_version,
            policy_version_reported=True,
            success=False,
            retries=brain_calls - 1,
            tool_calls=0,
            brain_calls=brain_calls,
            tokens=tokens,
            latency_ms=(time.perf_counter() - started) * 1000,
            safety_violation="target outside allowed workspace",
            detail=f"refused outside path: {target}",
            error_category="WORKSPACE_JAIL",
        )

    executor = adapter.executor_factory(arm_root)
    risk = risk_for_task(task)
    intent = append_intent(
        task,
        attempt=request.trial_index + 1,
        content=choice.append_content,  # model bytes only — never swap to oracle
        target=target,
        risk=risk,
        readiness=None,
        policy_version=policy_version,
        guards=(),
    )
    intent = replace(intent, state_revision=state_revision)
    readiness = plan_readiness(
        task,
        action_digest=intent.args_digest(),
        risk=risk,
        policy_version=policy_version,
        limits=(),
        state_revision=state_revision,
    )
    intent = replace(intent, readiness=readiness)
    provenance = LiveProvenance(
        adapter.project_id,
        adapter.model.attestation.model_id,
        adapter.producer,
        "sha256:" + hashlib.sha256(json.dumps(asdict(visible), sort_keys=True).encode()).hexdigest(),
    )
    judgment, decision = provenance.decision_records(choice, readiness)
    store.commit_records(
        [*([judgment] if judgment else []), decision], message="actual model choice and mechanical decision"
    )
    think = ModelDrivenThink(task=task, choice=choice, judgment_ref=judgment.id if judgment else None)
    runtime = CognitiveRuntime(
        think=think,
        rethink=think if adapter.mechanisms.targeted_rereasoning else None,
        actions=ActionDispatcher(port=executor, clock=lambda: datetime.now(tz=UTC)),
        governance=GovernanceGate(),
        budget=EpisodeBudget(expansion_rounds=2),
        project_id=adapter.project_id,
        producer=adapter.producer,
        clock=lambda: datetime.now(tz=UTC),
    )
    plan = EpisodePlan(
        readiness=readiness,
        action=intent,
        expected_outcome=task.expected_outcome,
        observation=None,
        decision_ref=decision.id,
    )
    think.plan = plan
    episode = runtime.run(
        EpisodeRequest(
            episode_id=f"episode:live:{request.arm.value}:{task.task_id}:{request.trial_index}",
            context_ref=context_record.id,
            goal_ref=task.goal_ref,
            expected_outcome=task.expected_outcome,
            simple=True,
            decision_revision=DECISION_REVISION,
            state_revision=state_revision,
            authority_revision=AUTHORITY_REVISION,
            policy_version=policy_version,
            plan=plan,
        )
    )
    available = target.exists()
    written = target.read_text(encoding="utf-8") if available else ""
    # success only if model-produced bytes match registered expected append
    success = written == task.append_content + "\n"
    observation_record, outcome_record = provenance.readback_records(
        task.append_content + "\n", written, available=available
    )
    action_records = episode.action_run.records if episode.action_run else ()
    store.commit_records([*action_records, observation_record, outcome_record], message="actual action and readback")
    if request.split == SplitRole.TRAIN.value:
        adapter.learning.observe(
            task,
            written,
            store=store,
            context_ref=context_record.id,
            judgment_ref=judgment.id if judgment else None,
            decision_ref=decision.id,
            action_ref=episode.action_run.intent.action_id if episode.action_run else None,
            observation_ref=observation_record.id,
            outcome_ref=outcome_record.id,
            execution=ExecutionEvaluation(
                OutcomeStatus.MATCH if available and written == choice.append_content + "\n" else OutcomeStatus.UNKNOWN,
                reason="Requested bytes verified by file readback" if available else "No file readback available",
            ),
        )
    active = adapter.learning.policies.active_policy(PolicyTarget.CONTEXT_DEPTH)
    if policy_version and active and request.split == SplitRole.FINAL.value:
        shadow = build_context_once(
            builder,
            task=task,
            state_revision=state_revision,
            policy_version=None,
            limits=ArmInputs(role=ArmRole.FRESH).effective_limits(),
        )
        adapter.learning.policies.record_behavior_change(
            policy_id=active.policy_id,
            version=active.version,
            task_id=task.task_id,
            shadow_selection=tuple(item.record_id for item in shadow.payload.l3_evidence),
            actual_selection=present,
            producer=adapter.producer,
            recorded_at=datetime.now(UTC),
            difference=f"Actual initial model context; readback success={success}",
            outcome_ref=outcome_record.id,
        )
        store.commit_records([adapter.learning.policies.records[-1]], message="live selector behavior trace")
    retries = brain_calls - 1
    latency_ms = (time.perf_counter() - started) * 1000
    tool_calls = int(episode.action_run is not None and episode.action_run.receipt is not None)
    return LiveTrialOutcome(
        effective_policy_version=policy_version,
        policy_version_reported=True,
        success=success,
        retries=retries,
        tool_calls=tool_calls,
        brain_calls=brain_calls,
        tokens=tokens,
        latency_ms=latency_ms,
        detail=(
            f"policy={policy_version!r}; written={written!r}; "
            f"expected={task.append_content!r}; episode={getattr(episode, 'termination', episode)}"
        ),
    )
