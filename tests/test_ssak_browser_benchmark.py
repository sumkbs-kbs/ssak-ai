"""task 22 — 브라우저 업무 benchmark·false-completion 평가의 계약 시험.

재는 것
-------
- **suite 구조**(브라우저 없음): 50개 워크플로(30 읽기 + 20 다단계), 고유 id, 계약 안의
  script 행동, grader 키, by_design 배분(승인 4·정직성 함정 2·접속 불가 2), 읽기 과제는
  변이 0 예산.
- **미니 실측**(실 Chromium + 로컬 fixture 서버): 스크립트를 subprocess 로 돌려 결말 분류
  (성공·승인 차단·거짓 done·접속 불가)와 분모 보존을 확인한다.
- **주입 검출**: grader 에 잘못된 success 를 주입하면 false completion 으로 잡히고
  `--fail-on-false-completion` 게이트가 0이 아닌 코드로 끝난다(계획 QA 의 실패 케이스).

전체 50×3 실행은 pytest 밖에서 증거로 돌린다(E/task-22/results.json) — 시험은 계약만 잰다.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[1]
SUITE = REPO / "tests" / "fixtures" / "browser_workflows"
SCRIPT = REPO / "scripts" / "benchmark_ssak_browser.py"
BY_DESIGN_OK = {"click", "fill", "goto", "done"}

pytest.importorskip("playwright.async_api")


def _load_suite() -> tuple[dict[str, object], list[dict[str, object]]]:
    manifest = json.loads((SUITE / "suite.json").read_text(encoding="utf-8"))
    workflows = [
        json.loads((SUITE / str(name)).read_text(encoding="utf-8"))
        for name in manifest["workflows"]  # type: ignore[union-attr]
    ]
    return manifest, workflows


@pytest.fixture(scope="module")
def suite() -> tuple[dict[str, object], list[dict[str, object]]]:
    return _load_suite()


@pytest.fixture(scope="module")
def by_id(suite) -> dict[str, dict[str, object]]:
    _, workflows = suite
    return {str(w["id"]): w for w in workflows}


# ── ① suite 구조(브라우저 없음) ──────────────────────────────────────────────


class TestSuiteShape:
    def test_fifty_workflows_thirty_read_twenty_multi(self, suite) -> None:
        manifest, workflows = suite
        kinds = [w["kind"] for w in workflows]
        assert len(workflows) == 50
        assert kinds.count("read") == 30 and kinds.count("multi") == 20
        assert manifest["counts"] == {"read": 30, "multi": 20, "total": 50}  # type: ignore[index]

    def test_ids_are_unique_and_match_files(self, suite) -> None:
        _, workflows = suite
        ids = [str(w["id"]) for w in workflows]
        assert len(set(ids)) == 50
        for w in workflows:
            assert (SUITE / "workflows" / f"{w['id']}.json").exists()

    def test_every_workflow_carries_the_contract_fields(self, suite) -> None:
        _, workflows = suite
        for w in workflows:
            for key in ("schema", "id", "kind", "tags", "goal", "entry", "pages", "postconditions", "script", "grader"):
                assert w.get(key) not in (None, "", [], {}), (w["id"], key)
            assert str(w["entry"]).startswith("/")
            for route, html in w["pages"].items():  # type: ignore[union-attr]
                # 페이지는 완전한 문서 또는 body 조각(브라우저가 포장한다)이다 — 비어 있으면 안 된다.
                assert route.startswith("/") and html.strip() and ("<h" in html or "<html" in html), (w["id"], route)
                # fixture 페이지는 다른 워크플로의 경로를 루트에서 가리키지 못한다(@/ 토큰만 쓴다).
                assert 'href="/' not in html and "fetch('/" not in html, (w["id"], route)

    def test_script_actions_stay_inside_the_planner_contract(self, suite) -> None:
        _, workflows = suite
        for w in workflows:
            for step in w["script"]:  # type: ignore[union-attr]
                assert step["action"] in BY_DESIGN_OK, (w["id"], step)
                if step["action"] in ("click", "fill"):
                    assert step.get("target"), (w["id"], step)
                if step["action"] == "fill":
                    assert "value" in step, (w["id"], step)

    def test_every_goal_is_verifiable_from_the_page(self, suite) -> None:
        """사후조건 없는 목표는 검증될 수 없다 — suite 은 그런 목표를 주지 않는다."""
        _, workflows = suite
        for w in workflows:
            assert w["postconditions"], w["id"]  # type: ignore[union-attr]
            for p in w["postconditions"]:  # type: ignore[union-attr]
                assert p["kind"] in {
                    "url_contains",
                    "url_matches",
                    "text_contains",
                    "flag_equals",
                    "element_present",
                    "element_absent",
                    "download_named",
                }

    def test_read_workflows_must_not_mutate(self, suite) -> None:
        _, workflows = suite
        for w in workflows:
            if w["kind"] == "read":
                assert w["grader"]["mutations_equals"] == 0, w["id"]  # type: ignore[index]

    def test_by_design_distribution(self, suite) -> None:
        """사람 개입 4 · 정직성 함정 2 · 접속 불가 2 — 나머지 42 는 스크립트가 끝낼 수 있어야 한다."""
        _, workflows = suite
        tags = [str(w["tags"][0]).split(":", 1)[1] for w in workflows if str(w["tags"][0]).startswith("by_design:")]
        assert tags.count("approval") == 4
        assert tags.count("honesty_trap") == 2
        assert tags.count("unreachable") == 2
        assert tags.count("ok") == 42

    def test_grader_is_independent_of_loop_postconditions(self, suite) -> None:
        """그레이더 예상은 서버 상태·경로 읽기·정적 내용이다 — 루프의 flag 사후조건과 다른 재료다."""
        _, workflows = suite
        for w in workflows:
            grader = w["grader"]  # type: ignore[index]
            assert set(grader) <= {"mutations_equals", "reads_min", "content"}
            for route, minimum in (grader.get("reads_min") or {}).items():  # type: ignore[union-attr]
                assert route in w["pages"] or str(w["tags"][0]).endswith("unreachable"), (w["id"], route)  # type: ignore[index]
                assert minimum >= 1


# ── ② 미니 실측 + 주입(실 Chromium) ─────────────────────────────────────────


def _run_benchmark(*args: str, output: Path) -> tuple[int, dict[str, Any]]:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--suite", str(SUITE), "--output", str(output), *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert completed.returncode in (0, 1), completed.stderr[-2000:]
    results = json.loads(output.read_text(encoding="utf-8"))
    return completed.returncode, results


MINI = "read-01,multi-01,multi-13,multi-17,multi-19"


class TestMiniBenchmark:
    def test_outcomes_are_classified_and_the_denominator_is_kept(self, tmp_path: Path) -> None:
        code, results = _run_benchmark("--runs", "1", "--only", MINI, output=tmp_path / "mini.json")
        assert code == 0
        runs = results["planners"]["scripted"]["runs"]
        by_workflow = {run["workflow"]: run for run in runs}
        assert by_workflow["read-01"]["status"] == "succeeded"
        assert by_workflow["multi-01"]["status"] == "succeeded"
        assert by_workflow["multi-13"]["status"] == "blocked"  # 승인 필요 = 사람 차례
        assert by_workflow["multi-13"]["blocked_kind"] == "approval"
        assert by_workflow["multi-17"]["status"] == "failed" and by_workflow["multi-17"]["code"] == "FALSE_DONE"
        assert by_workflow["multi-19"]["status"] == "failed" and by_workflow["multi-19"]["code"] == "NAVIGATION_FAILED"
        # 접속 불가도 분모에 남는다 — 조용히 빠지지 않는다.
        assert results["denominator"] == {"scheduled": 5, "executed": 5, "excluded": []}
        assert results["summary"]["false_completion"] == 0
        assert results["summary"]["underclaim"] == 0
        # 분류 집계가 실제 결말을 그대로 센다(multi-01 행동 3개 → steps p95=3, p50=0).
        assert results["summary"]["by_status"] == {"succeeded": 2, "blocked": 1, "failed": 2}
        assert results["summary"]["steps"]["p95"] == 3
        assert results["summary"]["steps"]["p50"] == 0

    def test_grader_and_loop_agree_on_the_mini_suite(self, tmp_path: Path) -> None:
        _, results = _run_benchmark("--runs", "1", "--only", MINI, output=tmp_path / "mini.json")
        runs = results["planners"]["scripted"]["runs"]
        for run in runs:
            if run["status"] == "succeeded":
                assert run["grader_achieved"], run["workflow"]
            else:
                assert not run["grader_achieved"], run["workflow"]
        assert results["summary"]["human_intervention"] == 1

    def test_model_planner_column_is_never_silently_empty(self, tmp_path: Path) -> None:
        _, results = _run_benchmark("--runs", "1", "--only", "read-01", output=tmp_path / "model.json")
        model = results["planners"]["model"]
        assert model["status"] == "NOT_RUN" and model["reason"]

    def test_injected_false_success_is_detected_and_fails_the_gate(self, tmp_path: Path) -> None:
        code, results = _run_benchmark(
            "--runs",
            "1",
            "--only",
            "read-01",
            "--inject-false-success",
            "read-01",
            "--fail-on-false-completion",
            output=tmp_path / "injected.json",
        )
        assert code == 1, "거짓 성공이 게이트를 넘어갔다"
        runs = results["planners"]["scripted"]["runs"]
        injected = [run for run in runs if run["injected"]]
        assert len(injected) == 1
        assert injected[0]["status"] == "succeeded" and not injected[0]["grader_achieved"]
        assert injected[0]["false_completion"] is True
        assert results["summary"]["false_completion"] == 1

    def test_a_real_run_of_the_same_workflow_is_not_a_false_completion(self, tmp_path: Path) -> None:
        """같은 워크플로를 실제로 돌면 성공이고 grader 도 달성이다 — 주입 없는 성공과 구분된다."""
        _, results = _run_benchmark("--runs", "1", "--only", "read-01", output=tmp_path / "real.json")
        run = results["planners"]["scripted"]["runs"][0]
        assert run["injected"] is False and run["status"] == "succeeded" and run["false_completion"] is False

    def test_three_runs_of_the_same_workflow_are_all_counted(self, tmp_path: Path) -> None:
        _, results = _run_benchmark("--runs", "3", "--only", "read-01", output=tmp_path / "three.json")
        assert results["denominator"]["executed"] == 3
        assert results["summary"]["by_status"]["succeeded"] == 3
