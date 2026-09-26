"""P11 표면 opt-in adapter 시험.

검증 범위:
- 설정이 없거나 enabled=false거나 mode가 이상하면 OFF로 fail-closed 하고 legacy 경로를 유지한다.
- OFF에서는 shadow/active가 조용히 실행되지 않고 거부된다.
- SHADOW는 실제 dispatcher를 쓰되 port가 없어 dispatch가 0이다(REFUSED_ACTION / NO_DISPATCH_PORT).
- ACTIVE는 사람 승인·dispatch port·governance gate가 모두 있을 때만 실행된다.
- 상태 조회는 실행 없이 읽히고, 마지막 episode·판정·dispatch 수를 반영한다.
- 표면 도달 실측은 import 그래프 기준으로 legacy/core 도달을 구분한다.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from antigravity_k.cli import app
from antigravity_k.engine.cognitive.actions import DispatchOutcome, PolicyClearance
from antigravity_k.engine.cognitive.authority import AuthorityDecision, AuthorityVerdict
from antigravity_k.engine.cognitive.governance import GovernanceGate
from antigravity_k.engine.cognitive.models import AuthorityDimension, RiskProfile
from antigravity_k.engine.cognitive.readiness import (
    ActionScope,
    EvidenceRef,
    HardConstraint,
    ReadinessInputs,
    check_readiness,
)
from antigravity_k.engine.cognitive.runtime import ThinkOutcome
from antigravity_k.engine.cognitive_surface import (
    CORE_MODULE,
    LEGACY_MODULE,
    CognitiveCoreSettings,
    CognitiveSurfaceAdapter,
    SurfaceDisabledError,
    SurfaceEpisodeRequest,
    SurfaceIntentRequest,
    SurfaceMode,
    SurfaceNotReadyError,
    SurfaceSource,
    measure_surface_reach,
)

AUTHORITY_REVISION = 3
DECISION_REVISION = 7
STATE_REVISION = 11
POLICY_VERSION = "surface-v1"
ACTION_KEY = "surface:append:1"


def _matching_freshness(intent, now):
    """ACTIVE fixture live head: matches readiness, recomputes action_digest from args."""
    from antigravity_k.engine.cognitive.readiness import FreshnessBinding

    readiness = intent.readiness
    if readiness is None:
        raise AssertionError("fixture intent requires readiness")
    fr = readiness.freshness
    return FreshnessBinding(
        decision_revision=fr.decision_revision,
        action_digest=intent.args_digest(),
        state_revision=fr.state_revision,
        authority_revision=fr.authority_revision,
        policy_version=fr.policy_version,
    )


def surface_intent(*, with_clearance: bool = True, readiness: object | None = "auto") -> SurfaceIntentRequest:
    request = raw_surface_intent()
    digest = request.to_intent().args_digest()
    decision = AuthorityDecision(
        allowed=True,
        verdict=AuthorityVerdict.ALLOWED,
        reason="surface test clearance",
        dimension=AuthorityDimension.TOOL_WRITE,
        resource_scope="surface-test",
        profile_revision=AUTHORITY_REVISION,
    )
    result = check_readiness(
        ReadinessInputs(
            action=ActionScope(
                tool="surface_write",
                scope="surface-test",
                expected_outcome="appended",
                action_digest=digest,
            ),
            authorized_action_digest=digest,
            decision_revision=DECISION_REVISION,
            state_revision=STATE_REVISION,
            authority_revision=AUTHORITY_REVISION,
            policy_version=POLICY_VERSION,
            grounds=("evidence:surface",),
            evidence_refs=(
                EvidenceRef(
                    evidence_id="evidence:surface",
                    provenance_uri="fixtures/surface/evidence.json",
                    provenance_digest="sha256:" + hashlib.sha256(b"evidence").hexdigest(),
                    observed_at=datetime(2026, 9, 22, 4, 0, 0, tzinfo=UTC),
                ),
            ),
            constraints=(HardConstraint(name="no_network", satisfied=True),),
            risk=RiskProfile(),
            authority_decision=decision,
        )
    )
    return replace(
        request,
        readiness=result if readiness == "auto" else readiness,  # type: ignore[arg-type]
        clearance=(PolicyClearance(authority=decision, revision=AUTHORITY_REVISION) if with_clearance else None),
    )


def raw_surface_intent() -> SurfaceIntentRequest:
    """clearance/readiness 없이 의도만 만든다(readiness를 digest에 결박하려면 먼저 필요하다)."""

    return SurfaceIntentRequest(
        action_key=ACTION_KEY,
        tool="surface_write",
        arguments={"value": "shadow"},
        scope="surface-test",
        dimension=AuthorityDimension.TOOL_WRITE,
        policy_version=POLICY_VERSION,
        decision_revision=DECISION_REVISION,
        state_revision=STATE_REVISION,
        authority_revision=AUTHORITY_REVISION,
    )


class StubThink:
    def __init__(self, judgment_ref: str = "judgment:surface") -> None:
        self.judgment_ref = judgment_ref
        self.calls = 0

    def think(self, *, context_ref: str, request_signature: str, attempt: int) -> ThinkOutcome:
        _ = (context_ref, request_signature, attempt)
        self.calls += 1
        return ThinkOutcome(judgment_ref=self.judgment_ref)


class StubDispatchPort:
    """ACTIVE 경로 확인용. 실제 도구 대신 dispatch 수락만 돌려준다."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def dispatch(self, tool: str, arguments: object, *, action_id: str) -> DispatchOutcome:
        _ = action_id
        self.calls.append((tool, dict(arguments)))  # type: ignore[arg-type]
        return DispatchOutcome(accepted=True, external_ref=f"stub:{tool}", detail="stub accepted")


def episode_request(*, intent: SurfaceIntentRequest | None = None) -> SurfaceEpisodeRequest:
    return SurfaceEpisodeRequest(
        episode_id="episode:surface:1",
        context_ref="context:surface:1",
        goal_ref="goal:surface",
        intent=intent,
        expected_outcome="appended",
        policy_version=POLICY_VERSION,
    )


# ─── 설정 fail-closed ─────────────────────────────────────────────


def test_missing_section_is_off() -> None:
    settings = CognitiveCoreSettings.from_config({})
    assert settings.enabled is False
    assert settings.effective_mode is SurfaceMode.OFF
    assert "설정이 없다" in settings.note


def test_enabled_false_forces_off_even_with_mode() -> None:
    settings = CognitiveCoreSettings.from_config({"cognitive_core": {"enabled": False, "mode": "active"}})
    assert settings.effective_mode is SurfaceMode.OFF
    assert settings.requested_mode == "active"


def test_unknown_mode_fails_closed() -> None:
    settings = CognitiveCoreSettings.from_config({"cognitive_core": {"enabled": True, "mode": "sometimes"}})
    assert settings.enabled is False
    assert settings.effective_mode is SurfaceMode.OFF
    assert "fail-closed" in settings.note


def test_enabled_shadow_is_effective() -> None:
    settings = CognitiveCoreSettings.from_config(
        {"cognitive_core": {"enabled": True, "mode": "shadow", "project_id": "project:surface"}}
    )
    assert settings.effective_mode is SurfaceMode.SHADOW
    assert settings.project_id == "project:surface"


def test_config_object_with_private_raw_is_supported() -> None:
    class ConfigLike:
        def __init__(self) -> None:
            self._raw = {"cognitive_core": {"enabled": True, "mode": "shadow"}}

    assert CognitiveCoreSettings.from_config(ConfigLike()).effective_mode is SurfaceMode.SHADOW


# ─── OFF에서는 아무 것도 실행하지 않는다 ──────────────────────────


def test_off_surface_reports_legacy_and_refuses_to_run() -> None:
    adapter = CognitiveSurfaceAdapter(CognitiveCoreSettings(), think=StubThink())
    status = adapter.status()
    assert status.source is SurfaceSource.LEGACY
    assert status.mode is SurfaceMode.OFF
    assert status.legacy_module == LEGACY_MODULE
    assert status.core_module == CORE_MODULE
    with pytest.raises(SurfaceDisabledError, match="legacy 경로를 그대로 쓴다"):
        adapter.run_shadow(episode_request(intent=surface_intent()))
    with pytest.raises(SurfaceNotReadyError, match="mode가 ACTIVE가 아니다"):
        adapter.run_active(episode_request(intent=surface_intent()))


def test_shadow_without_brain_port_is_refused() -> None:
    adapter = CognitiveSurfaceAdapter(CognitiveCoreSettings(enabled=True, mode=SurfaceMode.SHADOW))
    with pytest.raises(SurfaceNotReadyError, match="Primary Brain port"):
        adapter.run_shadow(episode_request(intent=surface_intent()))


# ─── SHADOW: action 0 ────────────────────────────────────────────


def test_shadow_runs_episode_without_dispatching() -> None:
    adapter = CognitiveSurfaceAdapter(CognitiveCoreSettings(enabled=True, mode=SurfaceMode.SHADOW), think=StubThink())
    run = adapter.run_shadow(episode_request(intent=surface_intent()))
    assert run.dispatched_actions == 0
    assert run.refusal == "NO_DISPATCH_PORT"
    assert run.action_status == "BLOCKED"
    assert run.termination == "REFUSED_ACTION"
    assert run.planned_records == ()  # 거부는 receipt·planned record를 만들지 않는다
    assert "ACTION" in run.states
    status = adapter.status()
    assert status.source is SurfaceSource.CORE_SHADOW
    assert status.last_episode_id == "episode:surface:1"
    assert status.last_termination == "REFUSED_ACTION"
    assert status.dispatched_actions == 0
    assert status.refused_actions == 1


def test_shadow_records_missing_clearance_as_not_authorized() -> None:
    adapter = CognitiveSurfaceAdapter(CognitiveCoreSettings(enabled=True, mode=SurfaceMode.SHADOW), think=StubThink())
    run = adapter.run_shadow(episode_request(intent=surface_intent(with_clearance=False)))
    assert run.refusal == "NOT_AUTHORIZED"
    assert run.dispatched_actions == 0


def test_shadow_without_planned_action_does_not_touch_dispatch() -> None:
    adapter = CognitiveSurfaceAdapter(CognitiveCoreSettings(enabled=True, mode=SurfaceMode.SHADOW), think=StubThink())
    run = adapter.run_shadow(episode_request(intent=None))
    assert run.dispatched_actions == 0
    assert run.action_status is None
    assert "계획된 action 없음" in run.note


def test_readiness_bound_to_another_action_is_refused() -> None:
    adapter = CognitiveSurfaceAdapter(CognitiveCoreSettings(enabled=True, mode=SurfaceMode.SHADOW), think=StubThink())
    other = surface_intent()
    # action digest는 tool·scope·arguments로 정해진다 → arguments를 바꾸면 결박이 끊긴다.
    mismatched = replace(other, arguments={"value": "different"})
    with pytest.raises(SurfaceNotReadyError, match="결박되지 않았다"):
        adapter.run_shadow(episode_request(intent=mismatched))


def test_shadow_is_not_refused_by_readiness_failure() -> None:
    adapter = CognitiveSurfaceAdapter(CognitiveCoreSettings(enabled=True, mode=SurfaceMode.SHADOW), think=StubThink())
    run = adapter.run_shadow(episode_request(intent=surface_intent(readiness=None)))
    assert run.dispatched_actions == 0
    assert run.termination == "BLOCKED_READINESS"


# ─── ACTIVE: 사람 승인 + 실행 경계 ───────────────────────────────


ACTIVE_PROJECT_ID = "project:" + str(uuid.uuid5(uuid.NAMESPACE_URL, "surface-test-project"))


def active_settings(**overrides: object) -> CognitiveCoreSettings:
    base = CognitiveCoreSettings(enabled=True, mode=SurfaceMode.ACTIVE, project_id=ACTIVE_PROJECT_ID)
    return replace(base, **overrides) if overrides else base


def test_active_requires_human_approval_and_ports(tmp_path: Path) -> None:
    settings = active_settings()
    no_ports = CognitiveSurfaceAdapter(settings, think=StubThink())
    with pytest.raises(SurfaceNotReadyError, match="dispatch port와 governance gate"):
        no_ports.activate(approver="human:owner", reason="P11 승인")
    with pytest.raises(SurfaceNotReadyError, match="사람 승인 기록이 없다"):
        no_ports.run_active(episode_request(intent=surface_intent()))

    from antigravity_k.engine.cognitive.action_journal import SqliteActionJournal
    from antigravity_k.engine.cognitive.store import CanonicalStore

    intent = surface_intent()
    assert intent.clearance is not None
    decision = intent.clearance.authority
    assert decision is not None
    store = CanonicalStore(tmp_path / "canonical")
    adapter = CognitiveSurfaceAdapter(
        settings,
        think=StubThink(),
        governance=GovernanceGate(),
        dispatch_port=StubDispatchPort(),
        journal=SqliteActionJournal(tmp_path / "claims.sqlite"),
        record_sink=store.commit_records,
        authority_resolver=lambda action, now: decision,
        freshness_resolver=_matching_freshness,
        activation_authorizer=lambda project, actor, now: project == ACTIVE_PROJECT_ID and actor == "human:owner",
    )
    with pytest.raises(SurfaceNotReadyError, match="사람 승인"):
        adapter.activate(approver="  ", reason="승인")
    activation = adapter.activate(
        approver="human:owner", reason="P11 승인", now=datetime(2026, 9, 22, 5, 0, 0, tzinfo=UTC)
    )
    assert activation.approver == "human:owner"
    run = adapter.run_active(episode_request(intent=surface_intent()))
    assert run.dispatched_actions == 1
    status = adapter.status()
    assert status.source is SurfaceSource.CORE_ACTIVE
    assert status.activation is not None and status.activation.approver == "human:owner"
    assert status.dispatched_actions == 1
    assert "active" in run.note and "shadow" not in run.note
    repeated = adapter.run_active(episode_request(intent=surface_intent()))
    assert repeated.dispatched_actions == 0
    assert repeated.refusal == "DUPLICATE_ACTION"
    # R11: each ACTIVE run sinks action receipts plus operational/selection trail.
    assert len(store.committed_manifests()) == 4
    assert len(adapter.experience.operational_records) >= 1


def test_active_requires_canonical_project_id() -> None:
    adapter = CognitiveSurfaceAdapter(
        active_settings(project_id="surface-test"),
        think=StubThink(),
        governance=GovernanceGate(),
        dispatch_port=StubDispatchPort(),
    )
    with pytest.raises(SurfaceNotReadyError, match="canonical project id"):
        adapter.activate(approver="human:owner", reason="P11 승인")


def test_active_activation_is_impossible_in_shadow_mode() -> None:
    adapter = CognitiveSurfaceAdapter(
        CognitiveCoreSettings(enabled=True, mode=SurfaceMode.SHADOW),
        think=StubThink(),
        governance=GovernanceGate(),
        dispatch_port=StubDispatchPort(),
    )
    with pytest.raises(SurfaceNotReadyError, match="mode가 ACTIVE가 아니다"):
        adapter.activate(approver="human:owner", reason="승인")


# ─── 표면 도달 실측 ───────────────────────────────────────────────


def test_measurement_separates_legacy_and_core_reach() -> None:
    measurement = measure_surface_reach()
    by_module = {item.module: item for item in measurement.entrypoints}
    legacy_entry = by_module["antigravity_k.engine.tool_loop"]
    assert legacy_entry.reaches_legacy is True
    assert legacy_entry.reaches_core is False
    assert legacy_entry.legacy_via[-1] == LEGACY_MODULE
    # 2026-09-24 P11 배선: dependencies의 opt-in surface 부착과 스트림 라우트의 관찰 호출로
    # API 진입(CLI·server·chat·SSE)과 agent runtime의 import 그래프가 core에 닿는다.
    # legacy loop를 소유한 실행 경로(engine_context·loop·tool_loop)와 background 집행은
    # 여전히 core에 닿지 않는다 — 관찰은 observe_interaction 호출 지점에서만 일어난다.
    for wired in (
        "antigravity_k.cli",
        "antigravity_k.api.server",
        "antigravity_k.api.routes.chat",
        "antigravity_k.api.routes.agent_stream_api",
        "antigravity_k.engine.agent_runtime",
    ):
        assert by_module[wired].reaches_core is True, wired
    for legacy_only in (
        "antigravity_k.engine.orchestrator.agent",
        "antigravity_k.engine.engine_context",
    ):
        assert by_module[legacy_only].reaches_core is False, legacy_only
    assert measurement.legacy_count >= 5
    payload = measurement.as_mapping()
    assert payload["legacy_module"] == LEGACY_MODULE
    assert payload["core_module"] == CORE_MODULE


def test_measurement_resolves_relative_imports(tmp_path: Path) -> None:
    """상대 import로 연결된 모듈도 도달로 센다(패키지 __init__ 경유)."""

    root = tmp_path / "src"
    core = root / "antigravity_k" / "engine" / "cognitive"
    core.mkdir(parents=True)
    (root / "antigravity_k" / "__init__.py").write_text("", encoding="utf-8")
    (root / "antigravity_k" / "engine" / "__init__.py").write_text("", encoding="utf-8")
    (core / "__init__.py").write_text("", encoding="utf-8")
    (core / "runtime.py").write_text("", encoding="utf-8")
    routes = root / "antigravity_k" / "routes"
    routes.mkdir()
    (routes / "__init__.py").write_text("from . import surface_api\n", encoding="utf-8")
    (routes / "surface_api.py").write_text(
        "from ..engine.cognitive.runtime import CognitiveRuntime\n", encoding="utf-8"
    )
    (root / "antigravity_k" / "entry.py").write_text("from .routes import surface_api\n", encoding="utf-8")
    measurement = measure_surface_reach(source_root=root, entrypoints=(("entry", "antigravity_k.entry"),))
    reach = measurement.entrypoints[0]
    assert reach.reaches_core is True
    assert reach.core_via[-1] == CORE_MODULE
    assert "antigravity_k.routes.surface_api" in reach.core_via


def test_measurement_detects_core_reach_in_synthetic_package(tmp_path: Path) -> None:
    root = tmp_path / "src"
    core = root / "antigravity_k" / "engine" / "cognitive"
    core.mkdir(parents=True)
    (root / "antigravity_k" / "__init__.py").write_text("", encoding="utf-8")
    (root / "antigravity_k" / "engine" / "__init__.py").write_text("", encoding="utf-8")
    (core / "__init__.py").write_text("", encoding="utf-8")
    (core / "runtime.py").write_text("", encoding="utf-8")
    (root / "antigravity_k" / "surface.py").write_text(
        "from antigravity_k.engine.cognitive.runtime import CognitiveRuntime\n", encoding="utf-8"
    )
    (root / "antigravity_k" / "missing_dep.py").write_text("", encoding="utf-8")
    measurement = measure_surface_reach(
        source_root=root,
        entrypoints=(
            ("new surface", "antigravity_k.surface"),
            ("없는 표면", "antigravity_k.not_there"),
        ),
    )
    reach = {item.module: item for item in measurement.entrypoints}
    assert reach["antigravity_k.surface"].reaches_core is True
    assert reach["antigravity_k.surface"].reaches_legacy is False
    assert reach["antigravity_k.not_there"].exists is False
    assert reach["antigravity_k.not_there"].reaches_core is False
    assert measurement.core_count == 1


# ─── CLI ─────────────────────────────────────────────────────────


def test_cli_cognitive_status_is_read_only() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["cognitive", "status"])
    assert result.exit_code == 0, result.output
    assert "cognitive_core" in result.output
    assert "legacy" in result.output

    as_json = runner.invoke(app, ["cognitive", "status", "--json"])
    assert as_json.exit_code == 0, as_json.output
    assert '"source": "legacy"' in as_json.output.replace("'", '"')


def test_cli_cognitive_surface_prints_measurement(tmp_path: Path) -> None:
    output = tmp_path / "surface.json"
    result = CliRunner().invoke(app, ["cognitive", "surface", "--output", str(output)])
    assert result.exit_code == 0, result.output
    assert "legacy 도달" in result.output
    assert output.is_file()
    assert '"core_module"' in output.read_text(encoding="utf-8")


# ── P11 배선(2026-09-24): AgentRuntime의 shadow 관찰 계약 ───────────────


class _StubOrchestrator:
    """AgentRuntime 구성에 필요한 최소 orchestrator. 실행은 일어나지 않는다."""

    max_engine = None

    def get_model_for_role(self, role: str) -> str:  # pragma: no cover - 사용되지 않는다
        return ""

    def run_stream(self, messages, target_model, max_steps=15, ephemeral_message=None):  # pragma: no cover
        yield from ()


def test_runtime_observation_is_noop_without_surface_or_when_off() -> None:
    from antigravity_k.engine.agent_runtime import AgentRuntime

    runtime = AgentRuntime(_StubOrchestrator())
    assert runtime.observe_interaction(episode_id="e:1", context_ref="c", goal_ref="g") is None

    off = CognitiveSurfaceAdapter(CognitiveCoreSettings(), think=StubThink())
    runtime.attach_cognitive_surface(off)
    assert runtime.observe_interaction(episode_id="e:1", context_ref="c", goal_ref="g") is None


def test_runtime_observation_runs_shadow_episode_with_dispatch_zero() -> None:
    from antigravity_k.engine.agent_runtime import AgentRuntime

    adapter = CognitiveSurfaceAdapter(CognitiveCoreSettings(enabled=True, mode=SurfaceMode.SHADOW), think=StubThink())
    runtime = AgentRuntime(_StubOrchestrator(), cognitive_surface=adapter)

    observation = runtime.observe_interaction(
        episode_id="stream:t-1",
        context_ref="legacy:agent-stream",
        goal_ref="legacy:agent-stream",
        expected_outcome="hi",
    )

    assert observation is not None
    assert observation.dispatched_actions == 0
    assert adapter.status().last_episode_id == "stream:t-1"
    assert adapter.status().dispatched_actions == 0


def test_runtime_observation_never_breaks_legacy_on_failure() -> None:
    from antigravity_k.engine.agent_runtime import AgentRuntime

    class ExplodingSurface:
        settings = CognitiveCoreSettings(enabled=True, mode=SurfaceMode.SHADOW)

        def run_shadow(self, request):  # type: ignore[no-untyped-def]
            raise RuntimeError("shadow 고장")

    runtime = AgentRuntime(_StubOrchestrator(), cognitive_surface=ExplodingSurface())

    assert runtime.observe_interaction(episode_id="e:boom", context_ref="c", goal_ref="g") is None


def test_background_outcome_recorder_fires_shadow_after_recording() -> None:
    from antigravity_k.engine.agent_runtime import AgentRuntime
    from antigravity_k.engine.benchmark_harness import TaskOutcome

    adapter = CognitiveSurfaceAdapter(CognitiveCoreSettings(enabled=True, mode=SurfaceMode.SHADOW), think=StubThink())
    recorded: list[str] = []

    def recorder(outcome: TaskOutcome) -> TaskOutcome:
        recorded.append(outcome.case_id)
        return outcome

    runtime = AgentRuntime(_StubOrchestrator(), task_outcome_recorder=recorder, cognitive_surface=adapter)
    wrapped = runtime._direct_tasks._task_outcome_recorder
    outcome = TaskOutcome(case_id="case-1", target="t", success=True, completion_reason="done")
    assert wrapped is not None and wrapped(outcome) is outcome

    assert recorded == ["case-1"], "기존 outcome 기록은 그대로 먼저 일어난다"
    assert adapter.status().last_episode_id == "task:case-1"
    assert adapter.status().dispatched_actions == 0


def test_surface_brain_port_does_not_claim_material_judgment() -> None:
    # 관찰 요약 think는 물질 판단을 주장하지 않는다(delta=None → simple 경로).
    # 모델 실패는 failed think로만 나타난다(legacy와 무관).
    from antigravity_k.engine.cognitive_surface import SurfaceBrainPort

    ok = SurfaceBrainPort(lambda prompt: f"요약:{prompt[:20]}")
    outcome = ok.think(context_ref="legacy:agent-stream", request_signature="stream:1", attempt=1)
    assert outcome.failed is False
    assert outcome.delta is None
    assert outcome.judgment_ref.startswith("judgment:")

    def explode(prompt: str) -> str:
        raise RuntimeError("모델 고장")

    failed = SurfaceBrainPort(explode).think(context_ref="c", request_signature="s", attempt=1)
    assert failed.failed is True
    assert failed.judgment_ref == ""


def test_active_rejects_missing_durable_boundaries() -> None:
    adapter = CognitiveSurfaceAdapter(
        active_settings(), think=StubThink(), governance=GovernanceGate(), dispatch_port=StubDispatchPort()
    )
    with pytest.raises(SurfaceNotReadyError, match="durable journal"):
        adapter.activate(approver="human:owner", reason="a label is not an authorization")


def test_active_revalidates_authenticated_activation(tmp_path: Path) -> None:
    from antigravity_k.engine.cognitive.action_journal import SqliteActionJournal
    from antigravity_k.engine.cognitive.store import CanonicalStore

    intent = surface_intent()
    assert intent.clearance is not None
    decision = intent.clearance.authority
    assert decision is not None
    allowed = [False]
    port = StubDispatchPort()
    store = CanonicalStore(tmp_path / "canonical")
    adapter = CognitiveSurfaceAdapter(
        active_settings(),
        think=StubThink(),
        governance=GovernanceGate(),
        dispatch_port=port,
        journal=SqliteActionJournal(tmp_path / "claims.sqlite"),
        record_sink=store.commit_records,
        authority_resolver=lambda action, now: decision,
        freshness_resolver=_matching_freshness,
        activation_authorizer=lambda project, actor, now: allowed[0],
    )
    with pytest.raises(SurfaceNotReadyError, match="authorization denied"):
        adapter.activate(approver="human:owner", reason="forged label")
    allowed[0] = True
    adapter.activate(approver="human:owner", reason="trusted application authorizes activation")
    allowed[0] = False
    with pytest.raises(SurfaceNotReadyError, match="authorization denied"):
        adapter.run_active(episode_request(intent=intent))
    assert port.calls == []
    assert store.committed_manifests() == ()
