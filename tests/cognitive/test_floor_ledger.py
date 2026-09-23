"""하한 원장(`scripts/floor_ledger.py`)의 계약 — **“이 저장소에는 어떤 하한이 있고 무엇을 보고 정해졌는가”** 를 한 표가 답하는가.

원장이 없으면 그 물음은 열 개 파일을 손으로 여는 일이 되고, 하한이 **판단**이라는 사실(값만 있으면 나중에 누구도
내려도 되는지 판단할 수 없다)이 사라진다. 그래서 여기서는 표가 실제로 서 있는지와, 표가 **거짓말할 수 없는지**를 고정한다:

  * 지금 저장소에서 원장이 통과하고, 층마다 하한·근거·승인(누가 언제)이 표에 실린다.
  * 자기 자신도 같은 규칙으로 판정된다 — 자기 행은 캔버스에 안 들어가고(자기를 세면 저절로 참이 된다), 승인을
    못 읽으면 자기 행 하나 때문에 원장 전체가 실패한다.
  * 아무도 읽지 않는 기록(`floors` 를 담았는데 어떤 harness 도 안 읽음)은 면죄부로 남지 않고 실패로 간다.
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
