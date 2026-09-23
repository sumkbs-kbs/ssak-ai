"""하한 원장(`scripts/floor_ledger.py`)의 계약 — **“이 저장소에는 어떤 하한이 있고 무엇을 보고 정해졌는가”** 를 한 표가 답하는가.

원장이 없으면 그 물음은 열 개 파일을 손으로 여는 일이 되고, 하한이 **판단**이라는 사실(값만 있으면 나중에 누구도
내려도 되는지 판단할 수 없다)이 사라진다. 그래서 여기서는 표가 실제로 서 있는지와, 표가 **거짓말할 수 없는지**를 고정한다:

  * 지금 저장소에서 원장이 통과하고, 층마다 하한·근거·승인(누가 언제)이 표에 실린다.
  * 자기 자신도 같은 규칙으로 판정된다 — 자기 행은 캔버스에 안 들어가고(자기를 세면 저절로 참이 된다), 승인을
    못 읽으면 자기 행 하나 때문에 원장 전체가 실패한다.
  * 아무도 읽지 않는 기록(`floors` 를 담았는데 어떤 harness 도 안 읽음)은 면죄부로 남지 않고 실패로 간다.
  * **표 밖의 하한**이 침묵하지 않는다 — 이름이 하한처럼 생긴 상수는 하한 목록에 실리거나, 왜 아닌지(근거·소유자·기한)
    선언돼야 한다. 선언은 양방향이다(하한이 되거나 사라지면 낡은 선언으로 실패한다 — 면죄부가 다음 결함을 가린다).
  * **사람이 승인한 하한 기록**과 지금 표가 같다 — 기록에서 하한이 사라지거나, 하한값이 내려가거나, 근거가 바뀌면
    그 판단이 어디에도 안 남으므로 실패다. 관측이 움직인 것은 보고일 뿐이다(그것까지 실패로 만들면 기록이 잡음이 된다).
  * 그 이동은 **층 단위로 묶여** 말해진다 — 층 하나가 roster 에서 빠지면 하한이 한꺼번에 사라지는데, 그것을 하한 개수만큼의
    문장으로 내면 읽는 사람이 하나의 결정을 다시 세어야 한다. 그 층이 아직 roster 에 있으면 결정이 아니라 결함이다.
  * JSON 을 내는 실행도 **판정을 종료 코드로** 말하고, 소요 시간은 판정 수치에 섞이지 않는다.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
LEDGER_SCRIPT = SCRIPTS / "floor_ledger.py"


def load_ledger() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ledger_under_test", LEDGER_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def ledger_module() -> Any:  # noqa: ANN401 - 스크립트 module
    return load_ledger()


@pytest.fixture(scope="module")
def ledger(ledger_module: Any) -> Any:  # noqa: ANN401 - 측정 한 번을 시험 넷이 공유한다(빌드 없이 도는 규칙 시험은 따로)
    return ledger_module.build()


# --------------------------------------------------------------------- 저장소의 실제 상태


def test_ledger_passes_on_this_repo(ledger: Any) -> None:  # noqa: ANN401
    """지금 저장소에서 원장이 통과한다 — 하한이 없거나·근거가 없거나·승인을 못 읽으면 여기서 멈춘다."""

    assert ledger.ok, ledger.problems


def test_every_layer_carries_floors_basis_and_approval(ledger: Any) -> None:  # noqa: ANN401
    """표의 모든 행이 하한과 근거와 승인을 갖는다 — 셋 중 하나가 비면 그 행은 읽는 사람에게 말을 못 한다."""

    assert len(ledger.rows) >= 2
    for row in ledger.rows:
        assert row.floors, f"{row.name}: 하한이 없다"
        assert all(floor.why.strip() for floor in row.floors), f"{row.name}: 근거 없는 하한"
        assert row.approval_text != "**못 읽음**", f"{row.name}: 승인(누가 언제)을 읽지 못했다"


def test_ledger_floor_does_not_muzzle_the_canvas(ledger_module: Any, ledger: Any) -> None:  # noqa: ANN401
    """원장 자신의 하한이 정상 측정을 막지 않고 근거를 갖는다 — 하한이 지금 본 하한 수보다 크면 원장은 늘 빨간을 낸다."""

    floors = ledger_module.coverage_floors(ledger)

    assert floors
    assert ledger_module.floor_problems(floors) == []
    assert all(floor.why.strip() for floor in floors)


def test_self_row_is_judged_like_every_other(ledger_module: Any, ledger: Any) -> None:  # noqa: ANN401
    """자기 행은 캔버스에 안 들어가고(자기 참조 금지), 자기 이름으로 표에 실린다."""

    self_rows = [row for row in ledger.rows if row.kind == ledger_module.KIND_SELF]
    others = [row for row in ledger.rows if row.kind != ledger_module.KIND_SELF]

    assert [row.name for row in self_rows] == [ledger_module.SELF_NAME]
    assert self_rows[0].floors[0].observed == sum(len(row.floors) for row in others) == ledger.canvas
    assert ledger.canvas < ledger.floors  # 자기 하한은 표에 세지만 캔버스에는 안 든다
    assert ledger_module.SELF_NAME not in {row.name for row in others}  # 자기 행은 하나뿐이다


# --------------------------------------------------------------------- 고아 기록 · 판정 규칙


def test_unread_record_is_reported_not_swallowed(ledger_module: Any, tmp_path: Path) -> None:  # noqa: ANN401
    """`floors` 를 담았는데 아무도 읽지 않는 기록은 실패로 간다 — 기록을 남긴 층이 사라져도 아무도 모르면 안 된다."""

    evidence = tmp_path / "evidence"
    evidence.mkdir()
    orphan = evidence / "lonely.json"
    orphan.write_text(json.dumps({"floors": [{"label": "x", "observed": 1, "minimum": 1, "why": "근거"}]}), "utf-8")
    deaf = evidence / "floorsless.json"
    deaf.write_text(json.dumps({"counts": {"a": 1}}), "utf-8")

    assert ledger_module.orphan_records(evidence, []) == ("lonely.json",)
    built = ledger_module.build(evidence_dir=evidence)

    assert not built.ok
    assert any("lonely.json" in problem for problem in built.problems)


def test_the_outside_scan_speaks_or_declares(ledger_module: Any, ledger: Any) -> None:  # noqa: ANN401
    """표 밖으로 스캔된 상수는 전부 배선되거나 선언돼 있다 — 침묵하는 후보가 없다.

    하한처럼 보이는데 아무도 안 보는 상수가 있는 층은 하한이 없는 것과같다: 카나리아가 눈멀게 한 사본으로 시험하지도,
    표가 그 이름을 말하지도 못한다. 선언에는 근거·소유자·재검토 기한이 함께 있어야 한다(없으면 면죄부다).
    """

    covered = set(ledger.covered) | {item.name for item in ledger.outside}

    assert ledger.candidates, "스캔이 아무것도 못 봤다 — 하한 후보 스캔이 스스로를 재는 값이 0 이다"
    assert set(ledger.candidates) - covered == set()
    assert ledger.outside
    assert all(item.reason.strip() and item.owner.strip() and item.review_by.strip() for item in ledger.outside)
    assert len(ledger.candidates) >= ledger_module._MIN_CANDIDATES


def test_reason_strings_are_not_floor_candidates(ledger_module: Any) -> None:  # noqa: ANN401
    """근거 문자열(`_WHY_*`)은 후보가 아니다 — 스캔이 자기 근거를 하한으로 세면 표가 부풀려진다."""

    candidates = ledger_module.floor_candidates()

    assert all("_WHY_" not in name for name in candidates)
    assert "scripts/floor_ledger.py:_MIN_FLOORS" in candidates  # 숫자 상수는 본다
    assert list(candidates) == sorted(candidates)  # 같은 저장소에 같은 답(순회 순서에 기대지 않는다)


def test_a_declaration_is_not_a_perpetual_excuse(ledger_module: Any) -> None:  # noqa: ANN401
    """선언은 **양방향**이다 — 그 상수가 하한 목록에 실리는 순간 그 선언은 낡아 실패한다(면죄부는 지운다)."""

    name = ledger_module.OUTSIDE[0].name
    _, stale = ledger_module.outside_floors((name,), (name,), (name,))

    assert stale == (name,)
    assert ledger_module.outside_problems((name,), (name,), ledger_module.OUTSIDE)  # 실제 선언도 이때는 낡은 것이다
    assert {item.name for item in ledger_module.OUTSIDE} <= set(ledger_module.floor_candidates())


def test_the_promoted_review_floor_is_in_the_table(ledger: Any) -> None:  # noqa: ANN401
    """표 밖 스캔이 찾아낸 하한(리뷰의 인용)이 표에 실려 있다 — 승격의 증거는 “그 이름이 표에 있다” 이다."""

    rows = {row.name: row for row in ledger.rows}

    assert "review" in rows
    assert [floor.label for floor in rows["review"].floors] == ["인용"]
    assert rows["review"].source == "scripts/architecture_review.py"
    assert rows["review"].approval_text != "**못 읽음**"


def test_the_committed_record_matches_the_current_judgment(ledger_module: Any, ledger: Any) -> None:  # noqa: ANN401
    """커밋된 하한 기록이 지금 판단과 같다 — 내리고·지우고·근거를 고치고 다시 기록하지 않으면 여기서 멈춘다."""

    stored = ledger_module.read_record()

    assert stored is not None, "하한 기록이 없다 — “내려도 되는 하한인가” 를 물을 자리가 없다"
    assert str(stored.get("method", "")).strip(), "기록에 승인 문장이 없다"
    assert ledger_module.record_problems(ledger_module.judged_floors(ledger), stored) == []
    assert ledger.record["problems"] == [] and ledger.record["present"] is True


def test_the_record_judges_judgments_and_only_reports_observations(ledger_module: Any, ledger: Any) -> None:  # noqa: ANN401
    """기록은 **판단**과 대조한다 — 관측은 매 회차 움직이므로 실패가 아니라 보고다(아니면 기록이 잡음이 된다)."""

    stored = ledger_module.read_record()
    assert stored is not None
    moved = {
        **stored,
        "floors": [{**item, "observed": int(item["observed"]) + 1000} for item in stored["floors"]],  # type: ignore[index]
    }

    assert ledger_module.record_problems(ledger_module.judged_floors(ledger), moved) == []
    assert len(ledger_module.record_moves(ledger, moved)) == len(ledger_module.judged_floors(ledger))
    assert ledger_module.judged_floors(ledger)  # 판단 목록 자체는 관측과 무관하게 서 있다


def test_a_lowered_floor_makes_the_record_stale(ledger_module: Any, ledger: Any) -> None:  # noqa: ANN401
    """승인 없이 하한을 내리면 기록이 낡는다 — 실패 문장이 어느 하한인지 값과 함께 말한다."""

    stored = ledger_module.read_record()
    assert stored is not None
    floors = [dict(item) for item in stored["floors"]]  # type: ignore[index]
    floors[0]["minimum"] = int(floors[0]["minimum"]) + 1  # 기록이 더 높다 = 지금이 그만큼 내려갔다
    problems = ledger_module.record_problems(ledger_module.judged_floors(ledger), {**stored, "floors": floors})

    assert len(problems) == 1 and "내려간 하한" in problems[0]
    assert f"{floors[0]['minimum']} → {int(floors[0]['minimum']) - 1}" in problems[0]


def test_a_vanished_or_added_floor_makes_the_record_stale(ledger_module: Any, ledger: Any) -> None:  # noqa: ANN401
    """하한을 지우는 것도, 새 하한을 기록 없이 들이는 것도 결정이다 — 문장이 방향과 **결함의 종류**를 구분한다."""

    stored = ledger_module.read_record()
    assert stored is not None
    judged = ledger_module.judged_floors(ledger)
    roster = [row.name for row in ledger.rows]
    without = {**stored, "floors": stored["floors"][1:]}  # type: ignore[index]
    ghost_layer = {
        **stored,
        "floors": [
            *stored["floors"],  # type: ignore[index]
            {"layer": "ghost", "label": "수", "minimum": 1, "observed": 1, "why": "근거"},
        ],
    }

    # 표에서 사라진 하한(그 층은 살아 있다) = 기록에는 있는데 지금 표가 안 싣는다.
    assert any("사라진 하한" in problem for problem in ledger_module.record_problems(judged[1:], stored, roster=roster))
    # 기록에 없는 하한(그 층은 살아 있다) = 지금 표가 새로 들였는데 기록이 모른다(기록에서 지운 경우도 같다).
    assert any(
        "기록에 없는 하한" in problem for problem in ledger_module.record_problems(judged, without, roster=roster)
    )
    # 기록에만 있는 층은 “층이 통째로 사라진” 쪽이다 — roster 가 그 층을 여전히 알고 있으면 결함, 모르면 결정이다.
    known = ledger_module.record_problems(judged, ghost_layer, roster=[*roster, "ghost"])
    forgotten = ledger_module.record_problems(judged, ghost_layer, roster=roster)

    assert any("ghost" in problem and "통째로 표에서 사라졌다" in problem for problem in known)
    assert any("ghost" in problem and "roster 에서도 표에서도" in problem for problem in forgotten)


def test_a_vanished_layer_is_one_decision_not_many_sentences(ledger_module: Any) -> None:  # noqa: ANN401
    """층이 통째로 사라진 것은 **하나의 결정**이다 — 하한 개수만큼의 문장으로 흐트러지면 읽는 사람이 다시 세어야 한다.

    그리고 그 층이 아직 카나리아 roster 에 있으면 그것은 결정이 아니라 **결함**이다(표가 그 층을 읽지 못했다) —
    두 경우가 같은 문장이 되면 서로 다른 사건이 같은 초록으로 보인다.
    """

    stored = {
        "method": "시험 승인",
        "recorded_on": "2026-01-01",
        "floors": [
            {"layer": "gone", "label": "수", "minimum": 1, "observed": 3, "why": "근거"},
            {"layer": "gone", "label": "다른 수", "minimum": 2, "observed": 4, "why": "근거"},
            {"layer": "alive", "label": "수", "minimum": 1, "observed": 5, "why": "근거"},
        ],
    }
    judged = (("alive", "수", 1, "근거"),)

    still_listed = ledger_module.record_problems(judged, stored, roster=("gone", "alive"))
    left_roster = ledger_module.record_problems(judged, stored, roster=("alive",))

    assert len(still_listed) == 1, still_listed  # 하한 둘이 함께 갔는데 문장은 하나다
    assert "층 gone" in still_listed[0] and "2개" in still_listed[0]
    assert "아직 카나리아 roster 에" in still_listed[0]
    assert len(left_roster) == 1 and "roster 에서도 표에서도" in left_roster[0]
    assert still_listed[0] != left_roster[0], "결정과 결함이 같은 문장이면 둘은 같은 초록으로 보인다"


def test_a_partial_move_names_the_layer_but_not_the_whole_lifecycle(ledger_module: Any) -> None:  # noqa: ANN401
    """층이 살아 있으면 그 층 이름으로 묶되 “층이 사라졌다” 고 말하지 않는다 — 결함의 종류를 섞으면 안 된다."""

    stored = {
        "method": "시험 승인",
        "recorded_on": "2026-01-01",
        "floors": [
            {"layer": "p", "label": "수", "minimum": 1, "observed": 3, "why": "근거"},
            {"layer": "p", "label": "다른 수", "minimum": 1, "observed": 5, "why": "근거"},
        ],
    }
    problems = ledger_module.record_problems((("p", "수", 1, "근거"),), stored, roster=("p",))

    assert len(problems) == 1 and "층 p: 다른 수" in problems[0]
    assert "roster 에서도" not in problems[0] and "통째로" not in problems[0]


def test_the_committed_record_has_no_layer_moves(ledger_module: Any, ledger: Any) -> None:  # noqa: ANN401
    """커밋된 기록과 지금 표 사이에 층 이동이 없다 — 표가 보는 층이 그대로라는 뜻이고, 그 수는 보고와 추이에 실린다."""

    assert ledger.record["vanished_layers"] == []
    assert ledger.record["added_layers"] == []
    assert ledger_module.record_changes(
        ledger_module.judged_floors(ledger), ledger_module.read_record()
    ).layer_moves == (
        (),
        (),
    )


def test_row_rules_bite(ledger_module: Any) -> None:  # noqa: ANN401
    """읽은 행의 규칙(하한·근거·승인)이 각각 따로 문다 — 하나라도 빠지면 통과가 아니다."""

    floor = ledger_module.Floor("수", 3, 1, why="근거")
    healthy = ledger_module.LayerRow(
        "probe", ledger_module.KIND_MEASURED, "scripts/probe.py", (floor,), {}, {"on": "2026-01-01", "hash": "a"}
    )
    baseless = ledger_module.replace(healthy, floors=(ledger_module.Floor("수", 3, 1, why="   "),))

    assert ledger_module.row_problems(healthy, "") == []
    assert len(ledger_module.row_problems(ledger_module.replace(healthy, commit=None), "")) == 1
    assert len(ledger_module.row_problems(ledger_module.replace(healthy, floors=()), "")) == 1
    assert len(ledger_module.row_problems(baseless, "")) == 1
    assert ledger_module.row_problems(ledger_module.replace(healthy, commit=None), "기록을 읽지 못했다") == [
        "기록을 읽지 못했다"
    ]


def test_blind_ledger_floor_bites(ledger_module: Any) -> None:  # noqa: ANN401
    """원장 자신의 하한도 눈멀게 하면 문다 — 자기 하한이 장식이면 표 전체가 장식이다."""

    floors = ledger_module.coverage_floors()
    blinded = [ledger_module.Floor(floor.label, 0, floor.minimum, why=floor.why) for floor in floors]

    assert all(not ledger_module.floor_problems([floor]) for floor in floors)
    assert all(ledger_module.floor_problems([floor]) for floor in blinded)


def test_counts_carry_no_runtime(ledger_module: Any) -> None:  # noqa: ANN401
    """소요 시간은 판정 수치에 안 들어간다 — 추이에 그날의 기계 속도가 섞이면 움직임이 안 보인다."""

    mapping = ledger_module.Ledger((), (), (), 1.5).as_mapping(ledger_module.Probe(cases=0, failures=()))

    assert "seconds" not in mapping["counts"]
    assert mapping["runtime"] == {"seconds": 1.5}


# --------------------------------------------------------------------- 이음매(CLI)


@pytest.mark.slow
def test_cli_json_speaks_the_same_verdict_as_its_exit_code() -> None:
    """JSON 을 내는 실행도 판정을 종료 코드로 말한다 — 보고는 PASS 인데 exit 1 인 모순이 없어야 한다."""

    result = subprocess.run(
        [sys.executable, str(LEDGER_SCRIPT), "--emit-json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    report = json.loads(result.stdout)
    summed = sum(len(layer["floors"]) for layer in report["layers"])

    assert result.returncode == 0, result.stderr
    assert report["verdict"] == "PASS"
    assert report["counts"]["floors"] == summed
    assert report["counts"]["orphans"] == len(report["orphans"])
    assert report["coverage"]["min_floors"] <= report["counts"]["canvas"]
    assert "seconds" not in report["counts"]
    assert report["runtime"]["seconds"] > 0


@pytest.mark.slow
def test_cli_record_requires_an_approval_and_refuses_a_failing_run(tmp_path: Path) -> None:
    """기록은 사람의 승인이다 — 승인 문장 없이는 쓰지 않고, 이미 실패한 실행은 기록하지 않는다.

    마지막이 중요한 까닭은 기록이 “지금의 하한 목록이 옳다” 는 승인이기 때문이다: 실패한 표를 승인하면 그 승인이 거짓이 된다.
    """

    evidence = tmp_path / "evidence"
    evidence.mkdir()
    record = evidence / "floor_ledger.json"
    without_approval = subprocess.run(
        [sys.executable, str(LEDGER_SCRIPT), "--record", "--evidence", str(evidence)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert without_approval.returncode == 1
    assert "--method" in without_approval.stderr
    assert not record.exists(), "승인 없이 기록을 남기면 그 기록은 승인이 아니다"

    # 표 밖 기록이 하나 있으면 그 실행은 실패한다(고아 기록) — 실패한 실행은 기록하지 않는다.
    (evidence / "orphan.json").write_text(
        json.dumps({"floors": [{"label": "x", "observed": 1, "minimum": 1, "why": "근거"}]}), "utf-8"
    )
    failing = subprocess.run(
        [sys.executable, str(LEDGER_SCRIPT), "--record", "--method", "시험 승인", "--evidence", str(evidence)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert failing.returncode == 1
    assert "기록하지 않았다" in failing.stderr
    assert not record.exists()


@pytest.mark.slow
def test_cli_record_round_trips_into_a_pass(tmp_path: Path) -> None:
    """기록을 남기면 그 자리에서 다시 읽혀 판정이 통과로 돌아온다 — 쓰기와 읽기가 같은 것을 말한다."""

    evidence = tmp_path / "evidence"
    evidence.mkdir()
    recorded = subprocess.run(
        [sys.executable, str(LEDGER_SCRIPT), "--record", "--method", "시험 승인", "--evidence", str(evidence)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert recorded.returncode == 0, recorded.stderr
    assert (evidence / "floor_ledger.json").exists()

    again = subprocess.run(
        [sys.executable, str(LEDGER_SCRIPT), "--emit-json", "--evidence", str(evidence)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(again.stdout)

    assert again.returncode == 0, again.stderr
    assert payload["record"]["present"] is True
    assert payload["record"]["problems"] == []
    assert payload["counts"]["recorded_floors"] == payload["counts"]["floors"]
    assert payload["verdict"] == "PASS"


@pytest.mark.slow
def test_cli_self_test_passes_without_reading_the_repo() -> None:
    """자기시험은 저장소를 읽지 않고도 자기 규칙을 다시 묻는다(리뷰가 돌릴 수 있어야 한다)."""

    result = subprocess.run(
        [sys.executable, str(LEDGER_SCRIPT), "--self-test"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "재판정" in result.stdout
