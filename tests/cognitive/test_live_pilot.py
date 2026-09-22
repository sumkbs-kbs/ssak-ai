"""Live pilot harness 시험 (P10 부속).

검증 범위:
- fixture spec으로 live pilot를 돌리지 못한다(별도 등록 spec 필요).
- provider port가 없으면 수치를 만들지 않고 NOT_RUN을 남긴다.
- snapshot 미고정은 reproducibility 제한 사유가 있을 때만 실행되고, claim scope가 제한으로 남는다.
- 최소 paired trial 미달은 실행 전에 거부된다.
- 완료 보고는 평균만이 아니라 중앙값·p95·분포·순서 효과를 함께 남긴다.
- negative transfer·safety·duplicate dispatch가 있으면 판정이 실패로 남는다.
- fixture artifact와 live artifact는 병합되지 않는다.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from antigravity_k.engine.cognitive.growth import (
    BenchmarkSpec,
    GrowthBenchmarkError,
    MechanismSet,
    RunKind,
    SplitRole,
    default_corpus_tasks,
    default_spec,
)
from antigravity_k.engine.cognitive.live_pilot import (
    CLAIM_SCOPE_LIMITED,
    CLAIM_SCOPE_PILOT,
    FixtureLiveMixError,
    LivePilotHarness,
    LivePilotPlan,
    LivePilotStatus,
    LiveTrialOutcome,
    LiveTrialRequest,
    ProviderAttestation,
    TrialOrder,
    assert_live_artifact,
    merge_reports,
)

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "benchmark_cognitive_growth.py"


def live_spec(**overrides: object) -> BenchmarkSpec:
    spec = default_spec(experiment_id="growth-live-pilot-v1", run_kind=RunKind.LIVE_PILOT)
    return replace(spec, **overrides) if overrides else spec


class StubLivePort:
    """시험용 stub. live 성능 증거가 아니며 attestation에 stub임을 적는다."""

    def __init__(
        self,
        *,
        snapshot_pinned: bool = True,
        mature_retries: int = 1,
        fresh_retries: int = 3,
        mature_success: bool = True,
        fresh_success: bool = True,
        duplicate_dispatch: bool = False,
        safety_violation: str = "",
        order_sensitive: bool = False,
    ) -> None:
        self.attestation = ProviderAttestation(
            provider_id="stub-live-port",
            model_id="stub-model",
            model_snapshot="snapshot:stub-rev-1" if snapshot_pinned else "",
            decoding="temperature=0",
            hardware="test-host",
            snapshot_pinned=snapshot_pinned,
            reproducibility_limits=() if snapshot_pinned else ("외부 provider revision 고정 불가",),
        )
        self._mature_retries = mature_retries
        self._fresh_retries = fresh_retries
        self._mature_success = mature_success
        self._fresh_success = fresh_success
        self._duplicate_dispatch = duplicate_dispatch
        self._safety_violation = safety_violation
        self._order_sensitive = order_sensitive
        self.requests: list[LiveTrialRequest] = []

    def run_trial(self, request: LiveTrialRequest) -> LiveTrialOutcome:
        self.requests.append(request)
        mature = request.arm.value == "MATURE"
        retries = self._mature_retries if mature else self._fresh_retries
        if mature and self._order_sensitive and request.order is TrialOrder.FRESH_FIRST:
            # 순서 효과를 재현한다: fresh를 먼저 돌린 trial에서 mature가 더 재시도한다.
            retries += 2
        return LiveTrialOutcome(
            success=self._mature_success if mature else self._fresh_success,
            retries=retries,
            tool_calls=retries + 1,
            brain_calls=1,
            tokens=100,
            latency_ms=12.5,
            duplicate_dispatch=self._duplicate_dispatch and mature,
            safety_violation=self._safety_violation if mature else "",
        )


def harness(spec: BenchmarkSpec | None = None, **plan_overrides: object) -> LivePilotHarness:
    plan = LivePilotPlan(
        trials_per_task=int(plan_overrides.pop("trials_per_task", 3)),
        confirmatory_sample_size=plan_overrides.pop("confirmatory_sample_size", None),
        policy_version=plan_overrides.pop("policy_version", "growth-live-pilot-v1-v1"),
        advisory_refs=plan_overrides.pop("advisory_refs", ("evidence:advisory",)),
        **plan_overrides,
    )
    return LivePilotHarness(
        spec if spec is not None else live_spec(),
        plan,
        tasks=default_corpus_tasks(),
        mechanisms=MechanismSet(),
    )


# ─── 분리·사전 등록 ────────────────────────────────────────────────


def test_fixture_spec_cannot_run_live_pilot() -> None:
    with pytest.raises(GrowthBenchmarkError, match="deterministic fixture spec"):
        LivePilotHarness(default_spec(), LivePilotPlan(trials_per_task=3), tasks=default_corpus_tasks())


def test_trials_below_minimum_are_refused() -> None:
    with pytest.raises(GrowthBenchmarkError, match="paired trial이 부족"):
        LivePilotHarness(live_spec(), LivePilotPlan(trials_per_task=2), tasks=default_corpus_tasks())


def test_missing_tasks_in_split_are_refused() -> None:
    with pytest.raises(GrowthBenchmarkError, match="task가 없다"):
        LivePilotHarness(live_spec(), LivePilotPlan(trials_per_task=3, split=SplitRole.TRAIN), tasks=())


# ─── NOT_RUN · reproducibility ────────────────────────────────────


def test_missing_port_reports_not_run_without_numbers() -> None:
    report = harness().run(None)
    payload = report.as_mapping()
    assert report.status is LivePilotStatus.NOT_RUN
    assert report.has_numbers is False
    assert payload["arms"] == {}
    assert payload["verdict"] is None
    assert "NOT_RUN" in payload["reason"]
    assert "fixture 결과로 대체하지 않는다" in payload["reason"]
    assert payload["run_kind"] == "LIVE_PILOT"
    assert payload["mixed_with_fixture"] is False


def test_unpinned_snapshot_without_limits_is_invalid() -> None:
    port = StubLivePort()
    port.attestation = replace(port.attestation, snapshot_pinned=False, reproducibility_limits=())
    report = harness().run(port)
    assert report.status is LivePilotStatus.INVALID
    assert report.has_numbers is False
    assert "reproducibility 제한 사유도 없다" in report.reason


def test_unpinned_snapshot_with_limits_is_reported_as_limited() -> None:
    report = harness().run(StubLivePort(snapshot_pinned=False))
    assert report.status is LivePilotStatus.COMPLETED
    assert report.reproducibility_limited is True
    verdict = report.verdict
    assert verdict is not None and verdict.claim_scope == CLAIM_SCOPE_LIMITED
    assert "snapshot 미고정" in " ".join(verdict.reasons)


# ─── 완료 보고 ────────────────────────────────────────────────────


def test_completed_report_carries_distributions_and_order_effect() -> None:
    port = StubLivePort(fresh_retries=3, mature_retries=1)
    report = harness().run(port)
    payload = report.as_mapping()
    arms = payload["arms"]
    assert report.status is LivePilotStatus.COMPLETED
    final_tasks = len({task.task_id for task in default_corpus_tasks() if task.split is SplitRole.FINAL})
    assert arms["FRESH"]["trials"] == final_tasks * 3
    for arm, retries in (("FRESH", 3.0), ("MATURE", 1.0)):
        metrics = arms[arm]["retries"]
        assert metrics["mean"] == retries
        assert metrics["median"] == retries
        assert metrics["p95"] == retries
        assert metrics["values"] == {f"{retries:g}": arms[arm]["trials"]}
    assert arms["FRESH"]["latency_ms"]["mean"] == 12.5
    # 순서는 trial마다 교대하고, 순서별 평균·차이를 남긴다.
    orders = {request.trial_index: request.order for request in port.requests}
    assert orders[0] is TrialOrder.FRESH_FIRST and orders[1] is TrialOrder.MATURE_FIRST
    assert payload["order_effect"]["MATURE:order_gap"] == 0.0
    assert payload["order_effect"]["FRESH:FRESH_FIRST:trials"] == float(final_tasks * 2)


def test_order_effect_is_measured_by_trial_order() -> None:
    report = harness().run(StubLivePort(fresh_retries=3, mature_retries=1, order_sensitive=True))
    effect = report.as_mapping()["order_effect"]
    # trial 2회는 FRESH_FIRST, 1회는 MATURE_FIRST → mature 평균 3.0 vs 1.0.
    assert effect["MATURE:FRESH_FIRST:mean_retries"] == 3.0
    assert effect["MATURE:MATURE_FIRST:mean_retries"] == 1.0
    assert effect["MATURE:order_gap"] == 2.0
    assert "FRESH:order_gap" not in effect  # gap은 mature arm의 순서 민감도만 본다


def test_verdict_stays_pilot_only_without_confirmatory_registration() -> None:
    verdict = harness().run(StubLivePort()).verdict
    assert verdict is not None
    assert verdict.passed is True
    assert verdict.claim_scope == CLAIM_SCOPE_PILOT
    assert verdict.confirmatory_sample_size_registered is False
    assert any("확증 표본" in reason for reason in verdict.reasons)

    registered = harness(confirmatory_sample_size=120).run(StubLivePort()).verdict
    assert registered is not None
    assert registered.confirmatory_sample_size_registered is True
    assert not any("확증 표본" in reason for reason in registered.reasons)


def test_worse_or_unsafe_mature_arm_fails_the_verdict() -> None:
    worse = harness().run(StubLivePort(fresh_retries=1, mature_retries=2)).verdict
    assert worse is not None and worse.passed is False
    assert worse.primary_metric_improved is False

    unsuccessful = harness().run(StubLivePort(fresh_success=True, mature_success=False)).verdict
    assert unsuccessful is not None and unsuccessful.passed is False
    assert unsuccessful.success_noninferior is False
    assert unsuccessful.negative_transfer_absent is False

    duplicated = harness().run(StubLivePort(duplicate_dispatch=True)).verdict
    assert duplicated is not None and duplicated.duplicate_dispatch_absent is False

    unsafe = harness().run(StubLivePort(safety_violation="권한 없이 ACTION했다")).verdict
    assert unsafe is not None and unsafe.safety_clean is False
    assert any("safety violation" in reason for reason in unsafe.reasons)


# ─── artifact 병합 거부 ──────────────────────────────────────────


def test_fixture_and_live_artifacts_are_never_merged() -> None:
    live = harness().run(StubLivePort()).as_mapping()
    fixture = {"run_kind": RunKind.DETERMINISTIC_FIXTURE.value, "comparison": {"primary": {"fresh": 39.0}}}
    with pytest.raises(FixtureLiveMixError, match="run_kind가 다른 report"):
        merge_reports(fixture, live)
    with pytest.raises(FixtureLiveMixError, match="live 결과가 아니다"):
        assert_live_artifact(fixture)
    assert merge_reports(live, live)["run_kind"] == RunKind.LIVE_PILOT.value
    with pytest.raises(FixtureLiveMixError, match="run_kind 없음"):
        assert_live_artifact({"status": "COMPLETED"})


# ─── CLI ──────────────────────────────────────────────────────────


def test_cli_writes_not_run_artifact_for_live_mode(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    spec = importlib.util.spec_from_file_location("growth_cli_live", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["growth_cli_live"] = module
    spec.loader.exec_module(module)
    output = tmp_path / "live.json"
    assert module.main(["--mode", "live-pilot", "--output", str(output)]) == 2
    assert "NOT_RUN" in capsys.readouterr().err
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["run_kind"] == "LIVE_PILOT"
    assert payload["status"] == "NOT_RUN"
    assert payload["mixed_with_fixture"] is False
    assert "arms" not in payload and "verdict" not in payload
