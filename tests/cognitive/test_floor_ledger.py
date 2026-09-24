"""하한 원장(`scripts/floor_ledger.py`)의 계약 — **“이 저장소에는 어떤 하한이 있고 무엇을 보고 정해졌는가”** 를 한 표가 답하는가.

원장이 없으면 그 물음은 열 개 파일을 손으로 여는 일이 되고, 하한이 **판단**이라는 사실(값만 있으면 나중에 누구도
내려도 되는지 판단할 수 없다)이 사라진다. 그래서 여기서는 표가 실제로 서 있는지와, 표가 **거짓말할 수 없는지**를 고정한다:

  * 지금 저장소에서 원장이 통과하고, 층마다 하한·근거·승인(누가 언제)이 표에 실린다.
  * 자기 자신도 같은 규칙으로 판정된다 — 자기 행은 캔버스에 안 들어가고(자기를 세면 저절로 참이 된다), 승인을
    못 읽으면 자기 행 하나 때문에 원장 전체가 실패한다.
  * 아무도 읽지 않는 기록(`floors` 를 담았는데 어떤 harness 도 안 읽음)은 면죄부로 남지 않고 실패로 간다.
  * **표 밖의 하한**이 침묵하지 않는다 — 이름이 하한처럼 생긴 상수는 하한 목록에 실리거나, 왜 아닌지(근거·소유자·기한)
    선언돼야 한다. 선언은 양방향이다(하한이 되거나 사라지면 낡은 선언으로 실패한다 — 면죄부가 다음 결함을 가린다).
  * 그리고 그 면제는 **기록이 약속까지 승인한 것**이어야 한다 — 면제를 만들거나·거두거나·근거·소유자를 바꾸거나
    **기한을 미루면** 그 결정이 기록을 지나야 한다(날짜를 미루는 것은 “다시 보겠다” 는 약속을 미루는 결정인데, 표는
    날짜가 있으면 통과시키므로 승인 없이는 어디에도 안 남는다 — 면죄부가 스스로 갱신되지 않는다). 기한을 **앞당긴**
    것은 더 자주 보는 쪽이므로 보고일 뿐이고, 약속이 그대로인 채 이름만 바뀐 것으로 보이면 한 문장으로 말하되
    “보인다” 까지만 말한다(원장은 상수의 동일성을 모른다).
  * **사람이 승인한 하한 기록**과 지금 표가 같다 — 기록에서 하한이 사라지거나, 하한값이 내려가거나, 근거가 바뀌면
    그 판단이 어디에도 안 남으므로 실패다. 관측이 움직인 것은 보고일 뿐이다(그것까지 실패로 만들면 기록이 잡음이 된다).
  * 그 이동은 **층 단위로 묶여** 말해진다 — 층 하나가 roster 에서 빠지면 하한이 한꺼번에 사라지는데, 그것을 하한 개수만큼의
    문장으로 내면 읽는 사람이 하나의 결정을 다시 세어야 한다. 그 층이 아직 roster 에 있으면 결정이 아니라 결함이다.
  * 그리고 그 층이 **이름만 바뀐 것**으로 보이면(하한 이름 집합이 그대로면) 사라짐·새로 생김 두 문장이 아니라 한 문장으로
    말하되 단정하지 않는다 — 원장은 층의 동일성을 모르므로 짝과 근거(그대로인 하한 이름들)만 내고 판단은 사람에게 남긴다.
  * 그 이름 변경은 **기록에 사실로 남고** 다음 기록으로 이어진다 — `floors` 는 지금 이름만 담으므로 그것만으로는 그 하한들이
    처음부터 새 이름의 층에 있었던 것으로 읽힌다(옛 이름은 다음 회차에 사라진다). 이력은 기록 안에서 자기 자리를 갖어야 하고
    (새 이름은 기록의 하한에, 옛 이름은 거기에 없어야 한다), 기록이 승인한 옛 이름이 표에 돌아오면 다시 승인받아야 한다.
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


def test_the_committed_record_approves_the_exemptions_with_their_promise(ledger_module: Any, ledger: Any) -> None:  # noqa: ANN401
    """커밋된 기록이 면제를 **약속까지** 승인한다 — 이름만 담긴 기록은 기한을 물을 자리가 없다.

    면제는 “이 상수는 하한이 아니다” 라는 판단이므로, 기록이 그 판단을 왜·누가·언제까지와 함께 승인해야 다음 회차가
    “기한을 미룬 것인가” 를 물을 수 있다(이름만 담긴 기록에서는 그 물음을 할 수 없고, 물을 수 없으면 면죄부가 스스로 갱신된다).
    """

    stored = ledger_module.read_record()
    assert stored is not None
    recorded = ledger_module.recorded_outside(stored)

    assert recorded.shape == ledger_module.OUTSIDE_SHAPE_FULL, "기록이 면제를 이름으로만·확인일 없이 담고 있다"
    assert recorded.names == {item.name for item in ledger_module.OUTSIDE}
    assert recorded.window_days == ledger_module._MAX_REVIEW_WINDOW_DAYS, "기록이 창을 승인하지 않았다"
    assert recorded.window_why.strip(), "창에는 근거가 붙어야 한다(숫자만 있으면 나중에 넓혀도 되는지 모른다)"
    assert all(
        item.reason.strip() and item.owner.strip() and item.reviewed_on.strip() and item.review_by.strip()
        for item in ledger_module.OUTSIDE
    )
    assert ledger_module.outside_record_problems(ledger_module.OUTSIDE, recorded) == []
    assert ledger.record["outside"]["recorded"] == len(ledger_module.OUTSIDE)
    assert ledger.record["outside"]["deferred"] == []
    assert ledger.record["outside"]["renamed"] == []
    # 기한 이동 이력 — “몇 번째 재검토인가” 를 세는 근거는 기록이 **사실로** 남긴 이동뿐이다(주장이 아니라 계산이다).
    assert isinstance(stored["outside"]["deadline_moves"], list), "기록이 기한 이동 이력 칸을 갖고 있지 않다"
    assert ledger_module.deadline_move_problems(stored) == [], "기록의 이력이 이어지지 않거나 지금 기한과 어긋난다"
    approved = {item["name"]: item["review_by"] for item in stored["outside"]["declared"]}
    for name, _was, now, on in ledger_module.recorded_deadline_moves(stored):
        assert on.strip(), f"이력에 승인 날짜가 없다: {name}"
        assert now == approved[name], f"이력의 마지막 기한이 지금 승인된 기한과 다르다: {name}"
    # 승격 이력 — 면제가 층이 되는 순간도 사실이라야 “그 도구가 층이 되었다” 와 “그 상수를 지웠다” 가 갈린다.
    assert isinstance(stored["outside"]["promoted"], list), "기록이 승격 이력 칸을 갖고 있지 않다"
    assert stored["outside"]["promoted"] == [], "이 기록에는 층이 된 면제가 없다 — 그 사실이 빈 것도 사실이다"
    assert ledger_module.promotion_problems(stored) == [], "기록이 자기 승격 사실과 모순된다"
    # 같은 상수가 면제이면서 동시에 하한일 수는 없다(둘은 다른 판단이고 한 이름은 한 자리다).
    exempt = {item.name for item in ledger_module.OUTSIDE}
    floors = {floor.label for row in ledger.rows for floor in row.floors}
    assert not (exempt & floors), exempt & floors


def test_an_exemption_deadline_is_bounded_by_a_confirmation(ledger_module: Any, ledger: Any) -> None:  # noqa: ANN401
    """기한은 **확인일로부터의 창** 안에서만 준다 — 한 번의 확인으로 두 해를 미루지 못하게 한다(면죄부의 크기에도 상한).

    기한만 뒤로 미는 것은 검토가 아니므로, 원장은 “언제 확인했나” 를 함께 묻고 그 확인일이 갱신됐는지도 본다.
    """

    declared = ledger_module.OUTSIDE[0]
    window = (ledger_module._MAX_REVIEW_WINDOW_DAYS, ledger_module._WHY_MAX_REVIEW_WINDOW)
    tight = ledger_module.replace(
        declared, review_by="2026-10-31"
    )  # 기록이 승인한 기한은 더 이르다(표가 그만큼 미룬 상태)
    approved = ledger_module.RecordedOutside(ledger_module.OUTSIDE_SHAPE_FULL, {tight.name: tight.promise}, *window)
    skipped = ledger_module.outside_record_problems((declared,), approved)

    assert declared.window is not None and declared.window <= ledger_module._MAX_REVIEW_WINDOW_DAYS
    assert len(skipped) == 1 and "기한만 미뤘다" in skipped[0] and declared.reviewed_on in skipped[0]
    stretched = ledger_module.replace(declared, review_by="2029-12-31")
    assert any(
        "창을 넘는다" in problem for problem in ledger_module.outside_problems((declared.name,), (), (stretched,))
    ), "창을 넘는 기한은 표가 먼저 막는다(기록을 보기 전에)"
    refreshed = ledger_module.replace(declared, reviewed_on="2026-11-30", review_by="2027-11-30")
    reviewed = ledger_module.outside_record_problems((refreshed,), approved)
    assert len(reviewed) == 1 and "기한을 미뤘다" in reviewed[0] and "기한만 미뤘다" not in reviewed[0]
    assert ledger.record["outside"]["window_days"] == ledger_module._MAX_REVIEW_WINDOW_DAYS
    assert ledger.record["outside"]["bare_deferred"] == []


def test_an_exemption_is_not_a_free_extension(ledger_module: Any) -> None:  # noqa: ANN401
    """면제의 생성·거둠·근거 변경은 승인을 지나야 하고, **기한을 미루는 것은 특히** 그렇다(면죄부의 자기 갱신을 막는다).

    반대로 기한을 앞당기는 것은 더 자주 보겠다는 뜻이므로 실패가 아니라 보고다 — 안전한 쪽으로 틀리는 것을 실패로 만들면
    그 실패가 잡음이 되고, 잡음 속에서 진짜 결정(미룸)이 안 보인다.
    """

    exemption = ledger_module.OutsideFloor(
        "scripts/b.py:MIN_Y", "하한이 아니라 유효성 임계다", "tester", "2026-01-01", "2026-12-31"
    )
    window = (ledger_module._MAX_REVIEW_WINDOW_DAYS, ledger_module._WHY_MAX_REVIEW_WINDOW)
    approved = ledger_module.RecordedOutside(
        ledger_module.OUTSIDE_SHAPE_FULL, {exemption.name: exemption.promise}, *window
    )
    moved_up = ledger_module.replace(exemption, reviewed_on="2025-06-01", review_by="2026-06-01")

    assert ledger_module.outside_record_problems((exemption,), approved) == []
    empty = ledger_module.RecordedOutside(ledger_module.OUTSIDE_SHAPE_FULL, {}, *window)
    made = ledger_module.outside_record_problems((exemption,), empty)
    assert len(made) == 1 and "기록에 없는 면제" in made[0] and "`--record --method`" in made[0]
    assert any("면제를 거두는 것" in item for item in ledger_module.outside_record_problems((), approved))
    assert any(
        "근거·소유자가 달라진 면제" in item
        for item in ledger_module.outside_record_problems((ledger_module.replace(exemption, owner="other"),), approved)
    )
    renewed = ledger_module.outside_record_problems(
        (ledger_module.replace(exemption, reviewed_on="2026-06-01", review_by="2027-06-01"),), approved
    )
    assert len(renewed) == 1 and "기한을 미뤘다" in renewed[0] and "2026-12-31 → 2027-06-01" in renewed[0]
    assert ledger_module.outside_record_problems((moved_up,), approved) == [], "앞당긴 기한은 실패가 아니다"
    assert ledger_module.outside_pulled((moved_up,), approved) == ("scripts/b.py:MIN_Y 2026-12-31 → 2026-06-01",)


def test_a_renamed_exemption_is_one_sentence_that_still_needs_approval(ledger_module: Any) -> None:  # noqa: ANN401
    """약속이 그대로인 면제는 **이름만 바뀐 것으로 보인다** — 다만 그것도 결정이므로 승인 전에는 초록이 아니다.

    옛 이름은 낡은 선언으로 따로 말하지 않는다(하나의 결정이 두 문장이 되면 읽는 사람이 다시 묶어야 한다). 그리고 약속이
    일부라도 다르면 짝짓지 않는다 — 이름 변경이 아니라 다른 판단일 수 있고, 원장은 상수의 동일성을 아는 것이 아니다.
    """

    old = ledger_module.OutsideFloor(
        "scripts/a.py:MIN_OLD", "판정 기준이다(관측 대상이 없다)", "qa", "2026-01-01", "2026-12-31"
    )
    new = ledger_module.replace(old, name="scripts/a.py:MIN_NEW")
    recorded = ledger_module.RecordedOutside(
        ledger_module.OUTSIDE_SHAPE_FULL,
        {old.name: old.promise},
        ledger_module._MAX_REVIEW_WINDOW_DAYS,
        ledger_module._WHY_MAX_REVIEW_WINDOW,
    )
    live = (new.name,)
    pairs = ledger_module.renamed_declarations((new,), recorded, candidates=live, wired=())

    assert pairs == ((old.name, new.name),)
    assert ledger_module.outside_problems(live, (), (old, new), renamed=pairs) == []
    said = ledger_module.outside_record_problems((new,), recorded, renamed=pairs)
    assert len(said) == 1 and "이름만 바뀐 것으로 보인다" in said[0] and "`--record --method`" in said[0]
    assert (
        ledger_module.renamed_declarations(
            (ledger_module.replace(new, reason="다른 이유"),), recorded, candidates=live, wired=()
        )
        == ()
    )


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
    changes = ledger_module.record_changes(ledger_module.judged_floors(ledger), ledger_module.read_record())
    assert changes.layer_moves == ((), ())
    # 이름 변경 후보도 없다 — 지금 기록과 지금 표가 같은 층 이름을 쓴다.
    assert ledger.record["renamed_layers"] == []
    assert changes.renamed_layers == ()
    assert ledger.as_mapping(ledger_module.Probe(cases=1, failures=()))["counts"]["record_layers_renamed"] == 0


def test_a_layer_rename_is_one_sentence_with_evidence(ledger_module: Any) -> None:  # noqa: ANN401
    """하한 이름 집합이 그대로인 층은 **이름만 바뀐 것으로 보인다** — 두 문장으로 나누면 하나의 결정이 둘로 보인다.

    다만 그것은 단정이 아니다: 원장은 층의 동일성을 모르므로 짝과 근거를 내고, 기록을 요구하며, 판단은 사람에게 남긴다.
    """

    stored = {
        "method": "시험 승인",
        "recorded_on": "2026-01-01",
        "floors": [
            {"layer": "old", "label": "수", "minimum": 1, "observed": 3, "why": "근거"},
            {"layer": "old", "label": "다른 수", "minimum": 2, "observed": 4, "why": "근거"},
            {"layer": "kept", "label": "수", "minimum": 1, "observed": 5, "why": "근거"},
        ],
    }
    judged = (("new", "수", 1, "근거"), ("new", "다른 수", 2, "근거"), ("kept", "수", 1, "근거"))

    renamed = ledger_module.record_problems(judged, stored, roster=("new", "kept"))
    assert len(renamed) == 1, renamed  # 하한 둘이 함께 옮겨갔는데 문장은 하나다
    assert "old" in renamed[0] and "new" in renamed[0] and "하한 이름 2개가 그대로" in renamed[0]
    assert "다른 수" in renamed[0] and "`--record --method`" in renamed[0]
    assert "모른다" in renamed[0], "단정하지 않는다는 사실을 문장이 말해야 한다"
    # 이름이 다른 새 층이라면 두 문장(사라짐·새 층)이 맞다.
    different = ledger_module.record_problems(
        (("new", "새 이름", 1, "근거"), ("kept", "수", 1, "근거")), stored, roster=("new", "kept")
    )
    assert any("roster 에서도 표에서도" in item for item in different)
    assert any("기록에 없는 새 층 new" in item for item in different)
    assert not any("이름만 바뀐 것으로 보인다" in item for item in different)


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
def test_a_rename_is_carried_into_the_record_as_a_fact(tmp_path: Path) -> None:
    """이름 변경은 `--record` 를 지나며 **기록의 사실**이 된다 — 하한 목록만 적으면 그 하한들이 처음부터 새 이름의 층에
    있었던 것으로 읽히고, 옛 이름은 다음 회차에 사라진다.

    저장소의 실제 층 하나를 **기록 안에서만** 바꾸고(하한·근거는 그대로 — 실제 이름 변경의 모양이다) 다시 기록하게 한다:
    대조가 그 짝을 찾아내고, 옛 이름·새 이름·그대로인 하한 이름들이 기록에 남으며, 그 기록으로 게이트가 통과한다
    (이력 자체는 결함이 아니고, 기록 안에서 자기 자리를 갖으면 통과다).
    """

    evidence = tmp_path / "evidence"
    evidence.mkdir()
    record = evidence / "floor_ledger.json"
    first = subprocess.run(
        [sys.executable, str(LEDGER_SCRIPT), "--record", "--method", "첫 승인", "--evidence", str(evidence)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert first.returncode == 0, first.stderr
    payload = json.loads(record.read_text(encoding="utf-8"))
    floors = payload["floors"]
    assert floors, "기록이 하한을 담지 않으면 이 시험은 무엇을 보는지 모른다"
    original = floors[0]["layer"]
    payload["floors"] = [
        {**item, "layer": f"{item['layer']}_old"} if item["layer"] == original else item for item in floors
    ]
    record.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")

    second = subprocess.run(
        [sys.executable, str(LEDGER_SCRIPT), "--record", "--method", "이름 변경 승인", "--evidence", str(evidence)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert second.returncode == 0, second.stderr
    carried = json.loads(record.read_text(encoding="utf-8"))["renames"]
    assert any(item["from"] == f"{original}_old" and item["to"] == original for item in carried), carried
    assert all(item["on"] for item in carried), "이력에는 언제 승인됐는지가 함께 남아야 한다"

    gate = subprocess.run(
        [sys.executable, str(LEDGER_SCRIPT), "--gate", "--evidence", str(evidence)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert gate.returncode == 0, gate.stdout + gate.stderr
    assert "이름 변경 이력" in gate.stdout


@pytest.mark.slow
def test_cli_a_renewed_exemption_must_pass_through_the_record(tmp_path: Path) -> None:
    """면제의 재검토 기한을 미루면 그 결정이 기록을 지나야 한다 — 그리고 기록을 지나면 다시 통과한다.

    이 자리가 이 규칙의 핵심이다: 날짜를 뒤로 미는 것은 “그 도구가 층이 되었는지 다시 본다” 는 약속을 한 회차 더 미루는
    결정인데, 표는 날짜가 있으면 통과시켰다(면죄부가 스스로 갱신되고, 검토가 있었는지 없었는지 아무도 몰랐다).
    그래서 기록 안에서만 면제 하나의 기한을 **옛날로** 옮겨 두고(표가 그만큼 미룬 상태를 만든다) 게이트가 그것을
    잡는지 묻고, 그 상태로 `--record` 를 지나면 승인이 되어 다시 초록이 되는지까지 확인한다(막다른 길이 아니다).
    """

    evidence = tmp_path / "evidence"
    evidence.mkdir()
    record = evidence / "floor_ledger.json"
    first = subprocess.run(
        [sys.executable, str(LEDGER_SCRIPT), "--record", "--method", "첫 승인", "--evidence", str(evidence)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert first.returncode == 0, first.stderr
    payload = json.loads(record.read_text(encoding="utf-8"))
    declared = payload["outside"]["declared"]
    assert declared and all(item["review_by"] and item["owner"] for item in declared), declared
    declared[0]["review_by"] = "2020-06-01"
    declared[0]["reviewed_on"] = "2020-01-01"  # 기록은 옛 확인·옛 기한 → 표의 확인·기한이 둘 다 뒤로 갔다
    record.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")

    gate = subprocess.run(
        [sys.executable, str(LEDGER_SCRIPT), "--gate", "--evidence", str(evidence)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert gate.returncode == 1, gate.stdout
    assert "재검토 기한을 미뤘다" in gate.stderr and declared[0]["name"] in gate.stderr, gate.stderr
    assert "`--record --method`" in gate.stderr

    second = subprocess.run(
        [sys.executable, str(LEDGER_SCRIPT), "--record", "--method", "기한 미룸 승인", "--evidence", str(evidence)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    again = subprocess.run(
        [sys.executable, str(LEDGER_SCRIPT), "--gate", "--evidence", str(evidence)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert second.returncode == 0, second.stderr
    assert again.returncode == 0, again.stderr


@pytest.mark.slow
def test_cli_a_deferred_deadline_without_a_fresh_confirmation_is_not_a_renewal(tmp_path: Path) -> None:
    """기한을 미루면서 확인일을 그대로 두면 그것은 연장이 아니다 — 게이트가 그 둘을 다른 문장으로 말하고,
    확인일까지 움직여 다시 기록하면 통과한다(막다른 길이 아니라 검토를 요구하는 자리다).

    기록 안에서만 면제 하나의 기한을 **앞으로** 옮기면(표가 그만큼 미룬 상태다) 확인일이 그대로이므로 “기한만 미뤘다” 가 나오고,
    확인일까지 뒤로 옮겨 다시 물으면 이번에는 “기한을 미뤘다” 라는 결정 문장이 나온다 — 같은 사실(기한이 뒤로 갔다)이
    검토가 있었는지에 따라 다른 문장이 되는 자리가 이 회차의 핵심이다. 마지막으로 `--record` 를 지나면 다시 통과한다.
    """

    evidence = tmp_path / "evidence"
    evidence.mkdir()
    record = evidence / "floor_ledger.json"
    first = subprocess.run(
        [sys.executable, str(LEDGER_SCRIPT), "--record", "--method", "첫 승인", "--evidence", str(evidence)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert first.returncode == 0, first.stderr
    payload = json.loads(record.read_text(encoding="utf-8"))
    declared = payload["outside"]["declared"]
    assert declared and all(item["reviewed_on"] and item["review_by"] for item in declared), declared
    assert payload["outside"]["review_window"]["days"] == 366
    name, was = declared[0]["name"], declared[0]["review_by"]
    declared[0]["review_by"] = was[:4] + "-01-31"  # 기한을 옛날로(표가 그만큼 미룬 상태) — 확인일은 그대로
    record.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")

    def gate() -> Any:  # noqa: ANN401
        return subprocess.run(
            [sys.executable, str(LEDGER_SCRIPT), "--gate", "--evidence", str(evidence)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    bare = gate()

    assert bare.returncode == 1, bare.stdout
    assert "기한만 미뤘다" in bare.stderr and name in bare.stderr and "확인일" in bare.stderr, bare.stderr

    declared[0]["reviewed_on"] = "2026-01-01"  # 기록도 옛 확인일로(표가 확인까지 새로 한 상태가 된다)
    record.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
    reviewed = gate()

    assert reviewed.returncode == 1, reviewed.stdout
    assert "재검토 기한을 미뤘다" in reviewed.stderr and "기한만 미뤘다" not in reviewed.stderr, reviewed.stderr

    second = subprocess.run(
        [sys.executable, str(LEDGER_SCRIPT), "--record", "--method", "기한 미룸 승인", "--evidence", str(evidence)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert second.returncode == 0, second.stderr
    assert gate().returncode == 0


@pytest.mark.slow
def test_cli_a_bare_extension_is_refused_rather_than_written_away(tmp_path: Path) -> None:
    """검토 없이 기한만 미룬 실행은 **기록을 거부**한다 — 그대로 쓰면 그 사실이 지워지기 때문이다.

    원장은 이미 둘을 거부한다(승인 문장 없는 실행, 표가 실패한 실행). 셋째는 성질이 다르다: 기록이 **사실을 지우는**
    경우다. 기록 안에서만 면제 하나의 기한을 옛날로 옮겨 두면(표가 그만큼 미룬 상태다) 표는 “기한만 미뤘다” 라고 하는데,
    그대로 기록하면 옛 기한이 새 기한으로 덮여 그 사실 자체가 사라진다 — 그래서 파일이 손대지지 않고 남아야 한다.
    확인일까지 옮기면 그것은 검토를 지난 결정이므로 기록을 통과해 다시 초록이 되고, 그 이동이 **기록의 사실**로 남아
    재검토 시트가 “미룸 1회” 를 셀 수 있게 된다.
    """

    evidence = tmp_path / "evidence"
    evidence.mkdir()
    record = evidence / "floor_ledger.json"
    first = subprocess.run(
        [sys.executable, str(LEDGER_SCRIPT), "--record", "--method", "첫 승인", "--evidence", str(evidence)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert first.returncode == 0, first.stderr
    payload = json.loads(record.read_text(encoding="utf-8"))
    assert payload["outside"]["deadline_moves"] == [], "첫 기록에 이동 이력 칸이 없다"
    declared = payload["outside"]["declared"]
    name, was = declared[0]["name"], declared[0]["review_by"]
    moved = was[:4] + "-01-31"  # 기록이 옛 기한을 승인한 상태가 된다(표가 그만큼 검토 없이 미룬 셈이다)
    declared[0]["review_by"] = moved
    record.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
    before = record.read_text(encoding="utf-8")

    def ledger(*extra: str) -> Any:  # noqa: ANN401
        return subprocess.run(
            [sys.executable, str(LEDGER_SCRIPT), *extra, "--evidence", str(evidence)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    bare = ledger("--gate")

    assert bare.returncode == 1, bare.stdout
    assert "기한만 미뤘다" in bare.stderr and name in bare.stderr, bare.stderr

    refused = ledger("--record", "--method", "검토 없이 미룸")

    assert refused.returncode == 1, refused.stdout
    assert "기록하지 않았다" in refused.stderr and "기한만 미룬" in refused.stderr, refused.stderr
    assert record.read_text(encoding="utf-8") == before, "거부한 기록이 파일을 덮었다(사실이 사라졌다)"

    declared[0]["reviewed_on"] = "2026-01-01"  # 검토를 지난 연장(기록이 옛 확인·옛 기한을 낸다)
    record.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")

    second = ledger("--record", "--method", "검토하고 미룸 승인")

    assert second.returncode == 0, second.stderr
    assert ledger("--gate").returncode == 0
    written = json.loads(record.read_text(encoding="utf-8"))
    moves = [item for item in written["outside"]["deadline_moves"] if item["name"] == name]

    assert len(moves) == 1, written["outside"]["deadline_moves"]
    assert moves[0]["from"] == moved and moves[0]["to"] == was and moves[0]["on"], moves
    sheet = ledger("--review")

    assert sheet.returncode == 0, sheet.stderr
    assert f"{name} — " in sheet.stdout and "미룸 1회" in sheet.stdout, sheet.stdout
    assert was in sheet.stdout and "승인" in sheet.stdout, sheet.stdout


@pytest.mark.slow
def test_cli_promotion_plan_says_what_is_left(ledger_module: Any) -> None:  # noqa: ANN401
    """면제를 층으로 올리는 일은 셋이다 — `--promote` 가 그 셋을 한 자리에서 읽고 남은 일을 낸다.

    승격은 하한 목록에 싣고(`coverage_floors`)·면제 선언을 지우고·기록하는 일인데, 셋이 서로 다른 파일에 흩어져 있으면
    사람이 매번 맞춰야 하고 하나를 빼먹었는지도 모른다. 이 명령은 코드를 대신 고치지는 않는다(어느 층의 하한인가는 그 층의
    파일에 사람이 쓴다) — 대신 **어디까지 왔는지**를 말하고, 끝나지 않았으면 exit 1 로 말한다. 스캔이 보지 못하는 이름은
    추측으로 올리지 않고 “대상이 아니다” 라고 말한다.
    """

    name = ledger_module.OUTSIDE[0].name
    planned = subprocess.run(
        [sys.executable, str(LEDGER_SCRIPT), "--promote", name],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert planned.returncode == 1, planned.stdout
    assert "면제 승격 절차" in planned.stdout and name in planned.stdout, planned.stdout
    assert "[ ] ②" in planned.stdout and "OUTSIDE" in planned.stdout, planned.stdout
    assert "--record --method" in planned.stdout, planned.stdout
    assert "아직 끝나지 않았다" in planned.stdout, planned.stdout

    outsider = subprocess.run(
        [sys.executable, str(LEDGER_SCRIPT), "--promote", "scripts/whatever.py:NOT_THERE"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert outsider.returncode == 1
    assert "대상이 아니다" in outsider.stdout, outsider.stdout


@pytest.mark.slow
def test_cli_a_promotion_fact_the_record_cannot_support_is_refused(tmp_path: Path) -> None:
    """기록이 "이 면제는 그 층의 하한이 되었다" 고 말하면 그 하한이 기록에 있어야 한다 — 손으로 넣은 사실은 문다.

    승격은 기록 한 줄로 끝나지 않는다(그 층의 하한 목록에 실리고 선언이 지워져야 끝난다). 그래서 기록이 승격했다고 하면서
    그 하한을 자기 `floors` 에 담고 있지 않으면 그것은 사실이 아니라 주장이고, 게이트가 그 자리에서 멈춘다.
    """

    evidence = tmp_path / "evidence"
    evidence.mkdir()
    record = evidence / "floor_ledger.json"
    first = subprocess.run(
        [sys.executable, str(LEDGER_SCRIPT), "--record", "--method", "첫 승인", "--evidence", str(evidence)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert first.returncode == 0, first.stderr
    payload = json.loads(record.read_text(encoding="utf-8"))
    assert payload["outside"]["promoted"] == []
    payload["outside"]["promoted"] = [
        {"name": "scripts/zzz.py:MIN_GHOST", "layer": "review", "label": "없는 하한", "on": "2026-09-24"}
    ]
    record.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")

    gate = subprocess.run(
        [sys.executable, str(LEDGER_SCRIPT), "--gate", "--evidence", str(evidence)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert gate.returncode == 1, gate.stdout
    assert "그 층에서 읽지 못한다" in gate.stderr and "MIN_GHOST" in gate.stderr, gate.stderr
    assert "면제로 선언하고 있다" not in gate.stderr, gate.stderr


def test_the_wiring_map_links_known_floors_to_their_layer(ledger_module: Any, ledger: Any) -> None:  # noqa: ANN401
    """표가 하한으로 아는 이름은 **어느 층의 하한인지**까지 이어져 있다 — 승격을 잇는 자리는 라벨이 아니라 코드의 배선이다.

    하한의 라벨은 사람이 쓴 이름(`pin`·`회차`)이라 상수 이름으로 잇지 못한다: 라벨로 이으려 한 첫 구현은 합성 자료로 돌린
    자기시험을 전부 통과했는데 실제 저장소에서는 승격 감지가 **0건**이었다(합성 입력이 결함을 가렸다). 그래서 표는 roster 의
    스크립트를 AST 로 읽어 `Floor(..., minimum=<이름>)` 에 실제로 넘겨진 상수를 모으고 그 이름을 그 하한을 드는 층에 잇는다 —
    이어지지 않은 이름이 남으면 면제가 정말로 층이 되는 순간에 그 사실을 잇지 못한다.
    """

    wiring = dict(ledger.wiring)
    names = {str(layer.name) for layer in ledger.rows}
    labels = {floor.label for row in ledger.rows for floor in row.floors}

    assert len(wiring) == len(ledger.covered) > 0, wiring
    assert set(wiring) == set(ledger.covered)
    assert set(wiring.values()) <= names, wiring
    assert wiring["scripts/floor_ledger.py:_MIN_FLOORS"] == "floor_ledger"
    # 실제 라벨은 상수 이름이 아니다 — 라벨로 이으려 한 첫 구현이 이 저장소에서 0건을 이은 이유다(배선으로 이어야 한다).
    assert "pin" in labels and "pin" not in wiring
    assert ledger_module.promotion_layer(ledger, "scripts/floor_ledger.py:_MIN_FLOORS") == "floor_ledger"


@pytest.mark.slow
def test_cli_a_promotion_fact_carries_the_label_the_layer_uses(tmp_path: Path) -> None:
    """승격 사실은 그 층이 그 하한을 부르는 **이름**(라벨)까지 담아야 한다 — 담지 않으면 기록이 자기 사실을 확인할 수 없다.

    라벨이 없으면 “그 층에 그 하한이 실렸는가” 를 기록 안에서 물을 수 없고(라벨은 상수 이름과 다르다), 라벨이 있어도 그 층의
    하한이 아니면 문다. 둘 다 지나면 다음 물음(표는 그 상수를 아직 면제로 선언하고 있는가)이 나온다 — 손으로 쓴 사실이 그
    자리까지 가는지를 CLI 로 확인한다(승격 감지가 라벨을 상수 이름으로 보던 동안에는 이 자국이 나오지 않았다).
    """

    evidence = tmp_path / "evidence"
    evidence.mkdir()
    record = evidence / "floor_ledger.json"
    first = subprocess.run(
        [sys.executable, str(LEDGER_SCRIPT), "--record", "--method", "첫 승인", "--evidence", str(evidence)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert first.returncode == 0, first.stderr
    payload = json.loads(record.read_text(encoding="utf-8"))
    name = payload["outside"]["declared"][0]["name"]
    floor = payload["floors"][0]

    def run() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(LEDGER_SCRIPT), "--gate", "--evidence", str(evidence)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    payload["outside"]["promoted"] = [{"name": name, "layer": floor["layer"], "on": "2026-09-24"}]
    record.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
    without = run()

    assert without.returncode == 1
    assert "(라벨)이 없다" in without.stderr and name in without.stderr, without.stderr

    payload["outside"]["promoted"] = [
        {"name": name, "layer": floor["layer"], "label": floor["label"], "on": "2026-09-24"}
    ]
    payload["outside"]["declared"] = [item for item in payload["outside"]["declared"] if item["name"] != name]
    record.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
    labelled = run()

    assert labelled.returncode == 1
    assert "(라벨)이 없다" not in labelled.stderr, labelled.stderr
    assert "그 층에서 읽지 못한다" not in labelled.stderr, labelled.stderr
    # 라벨까지 맞으면 남는 물음은 표 쪽이다 — 표는 그 상수를 아직 면제로 선언하고 있다(승격은 선언을 지워야 끝난다).
    assert "면제로 선언하고 있다" in labelled.stderr, labelled.stderr


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
