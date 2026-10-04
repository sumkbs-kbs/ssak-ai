"""Typed action/risk changes require an explicitly prepared Primary plan."""

from dataclasses import replace

import pytest

from antigravity_k.engine.cognitive.actions import ActionDispatcher
from antigravity_k.engine.cognitive.authority import AuthorityProfile
from antigravity_k.engine.cognitive.models import CognitiveRequestType, LoopState
from antigravity_k.engine.cognitive.runtime import (
    CognitiveRequestEnvelope,
    CognitiveRuntime,
    EpisodeDelta,
    EpisodeRequest,
    EpisodeTermination,
    ThinkOutcome,
)
from tests.cognitive.test_episode import (
    BODY,
    NOW,
    PROJECT,
    CallablePort,
    FakeRethink,
    FakeThink,
    plan_with_action,
)


@pytest.mark.parametrize("phase", ["think", "rethink"])
@pytest.mark.parametrize("change", ["risk", "action", "ground"])
@pytest.mark.parametrize("explicit_plan", [False, True])
def test_final_action_requires_prepared_plan_after_action_or_risk_change(phase, change, explicit_plan):
    # Given a prepared final action plus a Primary-authored typed change.
    calls: list[str] = []
    prepared, intent = plan_with_action()
    delta = EpisodeDelta(risk=change == "risk", action=change == "action", ground=change == "ground")
    current = ThinkOutcome(
        judgment_ref="judgment:latest", delta=delta, plan=replace(prepared) if explicit_plan else None
    )
    request = CognitiveRequestEnvelope(
        request_id="request:review",
        request_type=CognitiveRequestType.TOOL,
        purpose="inspect",
        target="src/a.py",
        expected_decision_impact="ground",
        authority=AuthorityProfile(revision=1),
    )
    initial = current if phase == "think" else ThinkOutcome(judgment_ref="judgment:old", requests=(request,))
    runtime = CognitiveRuntime(
        think=FakeThink(initial),
        rethink=FakeRethink([current]),
        actions=ActionDispatcher(
            port=CallablePort(lambda tool, args, action_id: (calls.append(action_id), "ok")[1]), clock=lambda: NOW
        ),
        clock=lambda: NOW,
        project_id=PROJECT,
        producer=BODY,
    )
    # When the episode considers the existing prepared final action.
    episode = runtime.run(
        EpisodeRequest(
            episode_id="episode:plan-binding",
            context_ref="context:1",
            goal_ref="goal:1",
            simple=phase == "think",
            plan=prepared,
        )
    )
    # Then unprepared action/risk changes defer; ground-only changes retain the prepared plan.
    if change in ("risk", "action") and not explicit_plan:
        assert episode.termination == EpisodeTermination.DEFERRED
        assert calls == []
        assert LoopState.ACTION not in episode.states()
        assert episode.judgment_ref == "judgment:latest"
    else:
        assert calls == [intent.action_id]
