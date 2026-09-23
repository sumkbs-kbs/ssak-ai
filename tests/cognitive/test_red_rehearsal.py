"""red 리허설(`scripts/red_rehearsal.py`)의 계약 — **한 번도 빨간을 낸 적 없는 감사를 어떻게 재현하는가**.

이 체크아웃의 두 감사(`audit_enum_identity`·`audit_test_namespace_purge`)는 위반이 0건이라, 그 green 이
“다 봤는데 깨끗하다” 인지 “한 번도 빨간을 본 적이 없다” 인지 **실행으로는** 구분되지 않았다(코드 경로를 읽어 확인했을 뿐).
리허설은 저장소 밖 임시 트리에 **진짜 파일로** 위반을 심고 그 감사를 `--root` 로 그 트리에 돌려 그 물음을 닫는다.
여기서 고정하는 것은 그 판정 규칙이다:

  * 심은 위반을 못 본 보고 · exit 0 · 심은 파일을 지목하지 않은 보고는 **통과가 아니다**.
  * 대조군(같은 자리에 허용 형태)이 초록이어야 한다 — 아니면 “위반을 봐서 빨간” 이 아니라 “트리 모양이 달라서 빨간” 이다.
  * 아무것도 없는 트리를 통과시키면 실패다(“위반 0건” 과 “못 봄” 을 구분하지 못한다).
  * 감사는 `--root` 를 받으면 그 트리만 보고, 지정이 없으면 지금까지처럼 저장소를 본다.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load_script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"{name}_under_test", SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def rehearsal() -> Any:  # noqa: ANN401 - 스크립트 module
    return load_script("red_rehearsal")


@pytest.fixture(scope="module")
def gate() -> Any:  # noqa: ANN401 - 스크립트 module
    return load_script("evidence_gate")


# ------------------------------------------------------------------ 저장소의 실제 상태


def test_every_planted_layer_actually_goes_red(rehearsal: Any) -> None:  # noqa: ANN401
    """심는 층 2개가 지금 저장소에서 실제로 red 를 낸다 — 심은 위반 지목 · 대조군 초록 · 빈 트리 차단."""

    records = rehearsal.run()

    assert len(records) == len(rehearsal.PLANTS) == 2
    for record in records:
        assert record.ok, f"{record.layer}: {record.problems}"
        assert record.dirty_exit == 1
        assert record.seen >= 1
        assert record.clean_exit == 0
        assert record.blind_exit != 0


def test_a_planted_violation_is_seen_and_the_report_names_it(tmp_path: Path, rehearsal: Any) -> None:  # noqa: ANN401
    """한 층을 직접 심어 본다 — JSON 과 사람이 보는 출력 **양쪽**에 심은 파일 이름이 남아야 한다."""

    plant = rehearsal.PLANTS[0]
    record = rehearsal.rehearse(plant, workspace=tmp_path / "tree")

    assert (tmp_path / "tree" / plant.planted).read_text(encoding="utf-8") == plant.allowed  # 대조군이 남아 있다
    assert record.ok, record.problems
    assert record.named is True
    assert record.spoken is True


def test_a_violation_planted_outside_the_repo_does_not_touch_the_repository(
    tmp_path: Path,
    rehearsal: Any,  # noqa: ANN401
) -> None:
    """리허설은 저장소를 건드리지 않는다 — 심는 자리는 임시 트리 안이고, 저장소 스캔은 그대로 깨끗하다."""

    plant = rehearsal.PLANTS[0]
    assert rehearsal._inside_tree(plant.planted) is True  # noqa: SLF001 - 자리 규칙 자체를 본다
    assert rehearsal._inside_tree("/etc/passwd") is False  # noqa: SLF001
    assert rehearsal._inside_tree("../outside.py") is False  # noqa: SLF001

    target = tmp_path / "tree" / plant.planted
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(plant.violation, encoding="utf-8")
    enum_audit = load_script("audit_enum_identity")

    assert [violation.file for violation in enum_audit.scan_paths(root=tmp_path / "tree")] == [plant.planted]
    assert enum_audit.scan_paths() == ()  # 저장소는 그대로 깨끗하다 — 리허설은 저장소를 건드리지 않는다


# ------------------------------------------------------------------ 감사의 --root 계약


@pytest.mark.parametrize("name", ["audit_enum_identity", "audit_test_namespace_purge"])
def test_scan_root_defaults_to_the_repository(name: str) -> None:
    """`--root` 를 주지 않은 실행은 지금까지와 같다 — 저장소를 보고, 저장소 하한을 쓴다."""

    module = load_script(name)

    assert module.resolve_root(None) == REPO_ROOT
    assert module.resolve_root(REPO_ROOT) == REPO_ROOT
    assert module.scanned_files(root=None) == module.scanned_files(root=REPO_ROOT)
    assert module.scan_paths(root=None) == module.scan_paths(root=REPO_ROOT)
    assert len(module.scanned_files(root=None)) >= 10  # “위반 0건” 이 아니라 실제로 본 수가 있다


@pytest.mark.parametrize("name", ["audit_enum_identity", "audit_test_namespace_purge"])
def test_a_missing_scan_root_is_not_a_pass(name: str) -> None:
    """없는 트리를 가리키면 빈손으로 초록이 되지 않는다 — 빈 스캔은 판정이 아니다."""

    module = load_script(name)
    missing = REPO_ROOT / "no_such_tree_for_rehearsal"

    assert module.scan_paths(root=missing) == ()
    assert module.scanned_files(root=missing) == ()
    floors = module.coverage_floors(root=missing)
    assert floors and floors[0].observed == 0 and floors[0].minimum >= 1
    assert module.coverage_floors(root=REPO_ROOT)[0].why != floors[0].why  # 저장소 하한과 다른 근거를 쓴다


# ------------------------------------------------------------------ 리허설 자신의 이빨


def test_a_layer_that_does_not_go_red_is_not_a_pass(rehearsal: Any) -> None:  # noqa: ANN401
    """exit 0 · 못 봄 · 지목 없음 · 대조군 빨강 · 빈 트리 통과는 각각 실패 문장으로 남는다."""

    healthy = {
        "layer": "probe_layer",
        "planted": "probe/planted.py",
        "dirty_exit": 1,
        "seen": 1,
        "named": True,
        "spoken": True,
        "clean_exit": 0,
        "blind_exit": 1,
        "crashed": False,
    }
    assert rehearsal.rehearsal_problems(rehearsal.Rehearsal(**healthy)) == ()

    defects = {
        "dirty_exit": 0,
        "seen": 0,
        "named": False,
        "spoken": False,
        "clean_exit": 1,
        "blind_exit": 0,
        "crashed": True,
        "note": "RuntimeError: 리허설이 죽었다",
    }
    for field, value in defects.items():
        broken = rehearsal.Rehearsal(**{**healthy, field: value})
        assert not broken.ok, field
        assert any("probe_layer" in problem for problem in broken.problems), field


def test_a_layer_no_one_rehearsed_and_no_one_declared_is_caught(gate: Any) -> None:  # noqa: ANN401
    """새 층을 어느 roster 에만 넣고 리허설하지도 선언하지도 않으면 게이트 자기시험이 짚는다."""

    assert gate.load_rehearsal_roster() == (
        ("audit_enum_identity", "audit_test_namespace_purge"),
        tuple(gate.load_rehearsal_roster()[1]),
    )
    original = gate.load_rehearsal_roster
    gate.load_rehearsal_roster = lambda: ((), ())  # type: ignore[assignment]
    try:
        probe = gate.self_probe()
    finally:
        gate.load_rehearsal_roster = original  # type: ignore[assignment]

    assert probe.ok is False
    assert any("red 회계" in failure for failure in probe.failures), probe.failures


def test_the_rehearsal_roster_explains_every_omission(rehearsal: Any) -> None:  # noqa: ANN401
    """리허설되지 않는 층은 **이유와 함께** 선언돼 있다 — 이유 없는 생략은 생략이 아니다."""

    assert rehearsal.DECLARED
    assert all(reason.strip() for reason in rehearsal.DECLARED.values())
    assert not set(rehearsal.DECLARED) & {plant.layer for plant in rehearsal.PLANTS}


# ------------------------------------------------------------------ CLI 계약


def test_gate_fails_when_a_layer_does_not_go_red(
    rehearsal: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:  # noqa: ANN401, E501
    """red 를 못 낸 층이 하나라도 있으면 `--gate` 도 `--emit-json` 도 exit 1 이다(진단은 JSON 에 남는다)."""

    def blind() -> tuple[Any, ...]:
        return (
            rehearsal.Rehearsal(
                layer="probe_layer",
                planted="probe/planted.py",
                dirty_exit=0,
                seen=0,
                named=False,
                spoken=False,
                clean_exit=0,
                blind_exit=1,
                crashed=False,
            ),
        )

    monkeypatch.setattr(rehearsal, "run", blind)
    assert rehearsal.main(["--gate"]) == 1
    assert "[FAIL]" in capsys.readouterr().err

    assert rehearsal.main(["--emit-json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["counts"]["unseen"] == 1
    assert payload["counts"]["ok"] == 0
    assert payload["layers"][0]["problems"]


def test_emit_json_reports_every_layer(rehearsal: Any, capsys: pytest.CaptureFixture[str]) -> None:  # noqa: ANN401
    """`--emit-json` 은 게이트·리뷰가 읽는 형태(층별 관찰 + 회계 + 합계)를 낸다."""

    assert rehearsal.main(["--emit-json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["counts"]["layers"] == 2
    assert payload["counts"]["ok"] == 2
    assert {item["layer"] for item in payload["layers"]} == {plant.layer for plant in rehearsal.PLANTS}
    assert payload["declared"]
    assert payload["floors"][0]["why"].strip()
    assert payload["probe"]["cases"] >= 15
