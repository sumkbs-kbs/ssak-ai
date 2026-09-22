"""P11 feature-off 회귀 시험 — 설정 OFF가 기존 경로를 바꾸지 않는지 고정한다.

`scripts/measure_feature_off_regression.py`를 그대로 불러(CLI와 같은 코드 경로) 세 설정을 비교한다:

1. `cognitive_core` 섹션 없음(현재 기본)
2. `enabled=false` + `mode=active`(켜려는 시도를 명시적으로 거부)
3. `enabled=true` + `mode=shadow`(adapter를 만들고 shadow episode 실행)

기대: legacy 인지 루프 transcript가 세 설정에서 동일하고, shadow는 workspace에 아무 것도 만들지 않는다.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

from antigravity_k.engine.cognitive_surface import SurfaceMode, SurfaceSource

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "measure_feature_off_regression.py"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("feature_off_regression", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["feature_off_regression"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def measured() -> Any:  # noqa: ANN401 - 스크립트의 FeatureOffMeasurement
    return load_script().measure()


def config_run(measured: Any, config: str) -> Any:  # noqa: ANN401
    return measured.runs[config]


def test_legacy_transcript_is_identical_across_configs(measured: Any) -> None:  # noqa: ANN401
    assert measured.legacy_transcript_identical is True
    assert len(set(measured.legacy_digests.values())) == 1, "설정별 legacy 동작이 달라졌다"
    assert measured.workspace_unchanged is True
    assert measured.would_be_target_absent is True
    assert measured.shadow_dispatched_actions == 0
    assert measured.passed is True
    assert measured.reasons == ()


def test_off_configs_never_run_the_core(measured: Any) -> None:  # noqa: ANN401
    for config in ("absent", "disabled_explicit"):
        run = config_run(measured, config)
        assert run.shadow is None, f"{config}에서 core episode가 실행됐다"
        assert run.settings["enabled"] is False
        assert run.settings["effective_mode"] == SurfaceMode.OFF.value
        assert run.surface_status["source"] == SurfaceSource.LEGACY.value
        assert run.surface_status["dispatched_actions"] == 0
        assert run.surface_status["last_episode_id"] is None
    # enabled=false + mode=active 조합도 OFF로 fail-closed 된다.
    assert config_run(measured, "disabled_explicit").settings["requested_mode"] == "active"


def test_shadow_runs_beside_legacy_without_effects(measured: Any) -> None:  # noqa: ANN401
    run = config_run(measured, "shadow_enabled")
    shadow_run = run.shadow
    assert isinstance(shadow_run, dict)
    assert shadow_run["refusal"] == "NO_DISPATCH_PORT"
    assert shadow_run["termination"] == "REFUSED_ACTION"
    assert shadow_run["action_status"] == "BLOCKED"
    assert shadow_run["planned_records"] == []
    assert shadow_run["dispatched_actions"] == 0
    assert run.would_be_target_created is False
    assert run.surface_status["source"] == SurfaceSource.CORE_SHADOW.value
    # shadow는 legacy transcript를 바꾸지 않는다(위 digest 동일성과 별개의 직접 확인).
    assert run.legacy_digest == config_run(measured, "absent").legacy_digest


def test_legacy_transcript_captures_real_loop_behaviour(measured: Any) -> None:  # noqa: ANN401
    transcript = cast("dict[str, Any]", config_run(measured, "absent").legacy_transcript)
    assert transcript["verify_missing"]["passed"] is False
    assert transcript["verify_missing"]["grade"] == "F"
    assert transcript["verify_ok"]["passed"] is True
    assert transcript["verify_ok"]["grade"] == "A"
    assert transcript["reflect"]["what_failed"], "reflect가 실패 단계를 보고하지 않았다"
    assert transcript["anti_patterns"], "anti-pattern 기록이 비어 있다"
    assert transcript["max_retries"] == 1


def test_script_exits_zero_and_writes_artifact(tmp_path: Path) -> None:
    module = load_script()
    output = tmp_path / "feature-off.json"
    assert module.main(["--output", str(output)]) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["verdict"]["passed"] is True
    assert payload["invariants"]["legacy_transcript_identical"] is True
    assert payload["invariants"]["shadow_dispatched_actions"] == 0
    assert payload["source_head"], "source head가 기록되지 않았다"
