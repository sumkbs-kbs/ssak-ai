#!/usr/bin/env python
"""red 리허설 — **위반이 0건인 감사가 실제로 빨간을 낼 수 있는가**를 저장소 밖에서 확인한다.

자기시험은 판독 **규칙**을 합성 문자열로 재판정하고, 하한은 “볼 수 있는가” 를 지키고, 카나리아는 하한이 **장식이 아닌지**
본다. 그런데 셋 다 실제로 만들어 보지 않은 것이 하나 남는다: **그 감사가 진짜 위반을 보고 빨간을 낸 적이 있는가.**
이 체크아웃의 두 감사(`audit_enum_identity`·`audit_test_namespace_purge`)는 위반이 0건이라, 지금 green 이 “본 것이 없어서”
green 인지 “다 봤는데 깨끗해서” green 인지는 **실행으로 확인된 적이 없다**(코드 경로를 읽어 확인했을 뿐이다).

그래서 이 도구는 임시 트리에 **진짜 파일로** 위반을 심고, 그 감사를 `--root` 로 그 트리에 돌려 세 가지를 확인한다:

  1. **심은 트리는 빨간이다** — exit 1 이고, 보고가 **심은 파일을 지목**한다(JSON 과 사람이 보는 출력 양쪽에).
  2. **대조군은 초록이다** — 같은 자리에 **허용 형태**를 넣으면 exit 0 이다. 이것이 없으면 “새 파일이 생겨서 빨간” 과
     “위반을 봐서 빨간” 을 구분할 수 없다(오탐을 red 재현으로 세지 않는다).
  3. **아무것도 없는 트리는 통과가 아니다** — 없는 root 를 가리키면 exit 1 이다(“위반 0건” 과 “못 봄” 을 가른다).

사고(traceback)로 죽는 것은 판정이 아니므로 실패로 센다. 리허설되지 않는 층은 **이유와 함께 선언**해야 하고, 게이트가
그 회계를 카나리아 roster·stage roster 와 대조한다 — 새 층을 어느 roster 에만 넣으면 거기서 걸린다.

```sh
.venv/bin/python scripts/red_rehearsal.py             # 층별 표
.venv/bin/python scripts/red_rehearsal.py --gate       # 하나라도 red 를 못 내면 exit 1
.venv/bin/python scripts/red_rehearsal.py --emit-json  # 게이트·리뷰가 읽는다(문제가 있으면 exit 1 + JSON)
```
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
SCRIPTS_DIR: Final[Path] = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from harness_contract import (  # noqa: E402
    Cases,
    Floor,
    Probe,
    describe_self_test,
    floor_problems,
    floor_records,
    probe_problems,
)

EXIT_OK: Final[int] = 0
EXIT_GATE: Final[int] = 1
CRASH_MARKER: Final[str] = "Traceback (most recent call last)"

# 탐지력 하한 — 리허설 대상이 0개면 “red 를 재현할 수 있다” 는 주장은 아무것도 재지 않은 것이 된다.
_MIN_REHEARSALS: Final[int] = 2
_WHY_REHEARSALS: Final[str] = (
    "2026-09-23 기준 관측: 저장소 밖에서 red 를 재현할 수 있어야 하는 층 2개(`audit_enum_identity`·"
    "`audit_test_namespace_purge` — 그동안 위반 0건이라 실제 green 만 봤다). 하한 2는 ’이 도구가 아무것도 심지 않고 "
    "통과했다’ 를 잡는 안전선이고, 다른 층의 red 재현 경로가 생기면 근거와 함께 이 수를 올린다."
)


@dataclass(frozen=True, slots=True)
class Plant:
    """한 층의 red 를 재현하는 방법 — 어느 트리에 무엇을 심고, 어떤 파일이 지목돼야 하는가.

    `allowed` 는 **같은 자리**에 넣는 허용 형태다: 대조군이 초록이어야 “위반을 봐서 빨간” 이 성립한다.
    """

    layer: str
    script: str
    planted: str
    violation: str
    allowed: str
    shows: str

    def as_mapping(self) -> dict[str, object]:
        return {"layer": self.layer, "script": self.script, "planted": self.planted, "shows": self.shows}


# 리허설 대상 — 각 항목은 그 층이 **실제로 빨간을 낼 수 있는지**를 저장소 밖 트리에서 확인한다.
PLANTS: Final[tuple[Plant, ...]] = (
    Plant(
        layer="audit_enum_identity",
        script="audit_enum_identity.py",
        planted="src/antigravity_k/engine/cognitive/planted_enum_probe.py",
        violation="RED = status is RiskLevel.HIGH\n",
        allowed="OK = status == RiskLevel.HIGH\n",
        shows="identity 비교(`is`)를 심으면 감사가 그 파일을 지목하고 exit 1",
    ),
    Plant(
        layer="audit_test_namespace_purge",
        script="audit_test_namespace_purge.py",
        planted="tests/test_planted_purge_probe.py",
        violation="import sys\n\nsys.modules.pop('antigravity_k.x', None)\n",
        allowed="import os\nimport sys\n\nif os.environ.get('REHEARSAL_TREE'):\n    sys.modules.pop('antigravity_k.x', None)\n",
        shows="수집 단계 purge 를 심으면 감사가 그 파일을 지목하고 exit 1",
    ),
)

# 리허설하지 않는 층 — **이유 없이** 빠지면 그 층의 red 는 아무도 재현하지 않은 것이 된다.
# 게이트 자기시험이 이 회계를 카나리아 roster·stage roster 와 대조한다(하나라도 안 맞으면 실패).
DECLARED: Final[dict[str, str]] = {
    "review": (
        "이 리허설을 읽고 판정하는 층이다 — 결함 상태를 재현하는 계약 시험이 "
        "tests/cognitive/test_architecture_review.py 에 있다(검사마다 변형을 만들어 실패를 확인한다)"
    ),
    "canary": (
        "장식 하한을 찾는 것이 곧 red 다 — 눈멀게 한 사본이 안 물리면 `--emit-json` 도 exit 1 이 되고"
        "(scripts/harness_canary.py), 그 사실을 tests/cognitive/test_harness_canary.py 가 재현한다"
    ),
    "digest_drift": (
        "pin 이 움직이거나 저장본이 없을 때의 red 를 tests/cognitive/test_digest_drift.py 가 재현한다"
        "(`--gate` 와 `--emit-json` 이 같은 결론을 내는지까지 확인한다)"
    ),
    "audit_state_claims": (
        "낡은 주장이 있을 때의 red 를 tests/cognitive/test_state_claims.py 가 재현한다(정정 없는 주장 1건이면 exit 1)"
    ),
    "measure_cognitive_surface": (
        "하한 미달(빈 source root)에서 exit 1 과 함께 산출물을 쓰는 red 를 tests/cognitive/ 의 계약 시험이 재현한다"
    ),
    "regression_ledger": (
        "미소유 결정적 실패·중단 회차가 있을 때의 red 를 원장 artifact 와 tests/cognitive/test_regression_ledger.py 가 다룬다"
    ),
    "evidence_gate": (
        "이 리허설을 도는 게이트 자신이다 — stage 로 넣으면 재귀다. 못 돌림·실패 상태의 red 는 "
        "tests/cognitive/test_evidence_gate.py 가 재현한다"
    ),
    "red_rehearsal": (
        "이 도구 자신이다 — 심은 위반을 못 보거나 대조군이 빨간인 보고를 실패로 바꾸는지"
        " tests/cognitive/test_red_rehearsal.py 가 재현한다"
    ),
}


@dataclass(frozen=True, slots=True)
class Rehearsal:
    """한 층의 리허설 관찰 — 심은 트리·대조군·빈 트리를 각각 돌린 결과."""

    layer: str
    planted: str
    dirty_exit: int | None
    seen: int
    named: bool
    spoken: bool
    clean_exit: int | None
    blind_exit: int | None
    crashed: bool
    note: str = ""

    @property
    def problems(self) -> tuple[str, ...]:
        return rehearsal_problems(self)

    @property
    def ok(self) -> bool:
        return not self.problems

    def as_mapping(self) -> dict[str, object]:
        return {
            "layer": self.layer,
            "planted": self.planted,
            "dirty_exit": self.dirty_exit,
            "seen": self.seen,
            "named": self.named,
            "spoken": self.spoken,
            "clean_exit": self.clean_exit,
            "blind_exit": self.blind_exit,
            "crashed": self.crashed,
            "note": self.note,
            "ok": self.ok,
            "problems": list(self.problems),
        }


def rehearsal_problems(record: Rehearsal) -> tuple[str, ...]:
    """관찰 하나를 판정으로 바꾼다 — **red 재현·대조군·빈 트리**를 모두 요구한다."""

    problems: list[str] = []
    # `crashed` 플래그와 `note` 어느 한쪽만 있어도 실패다 — 둘 중 하나가 비면 “사고가 있었다” 는 사실이 사라진다.
    if record.crashed or record.note:
        detail = record.note or "까닭을 남기지 않은 traceback"
        problems.append(f"{record.layer} 리허설을 돌리다 사고가 났다: {detail} — 사고는 판정이 아니다")
    if record.dirty_exit != EXIT_GATE:
        problems.append(f"{record.layer} 가 심은 위반을 보고도 exit {record.dirty_exit} 다 — red 를 내지 못한다")
    if record.seen < 1:
        problems.append(f"{record.layer} 가 심은 위반을 한 건도 보지 못했다(본 위반 0건)")
    elif not record.named:
        problems.append(f"{record.layer} 가 위반을 보긴 했지만 **심은 파일**({record.planted})을 지목하지 않았다")
    elif not record.spoken:
        problems.append(
            f"{record.layer} 의 보고서에는 심은 파일이 있지만 실행 출력에는 없다 — 사람이 돌려도 어느 파일인지 모른다"
        )
    if record.clean_exit != EXIT_OK:
        problems.append(
            f"{record.layer} 가 허용 형태(대조군)를 위반으로 본다(exit {record.clean_exit}) — "
            "그 리허설은 심은 위반이 아니라 트리 모양을 본 것이다"
        )
    if record.blind_exit == EXIT_OK:
        problems.append(f"{record.layer} 가 아무것도 없는 트리를 통과시킨다 — ’위반 0건’ 과 ’못 봄’ 을 구분하지 못한다")
    return tuple(problems)


def coverage_floors(plants: tuple[Plant, ...] | None = None) -> list[Floor]:
    """리허설 대상 수의 하한 — 값과 근거를 함께 낸다(카나리아가 이 하한도 본다)."""

    items = PLANTS if plants is None else plants
    return [Floor("리허설 대상", len(items), _MIN_REHEARSALS, why=_WHY_REHEARSALS)]


def run_audit(script: str, root: Path, report: Path) -> tuple[int, str, dict[str, object] | None]:
    """감사를 **독립 process** 로 돌리고 (종료 코드, 출력, JSON) 을 돌려준다."""

    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / script), "--root", str(root), "--json", str(report)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    payload: dict[str, object] | None = None
    if report.exists():
        try:
            loaded = json.loads(report.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            loaded = None
        if isinstance(loaded, dict):
            payload = loaded
    return result.returncode, result.stdout + result.stderr, payload


def seen_files(payload: dict[str, object] | None) -> list[str]:
    """보고가 지목한 파일 — 구조화된 쪽(JSON)을 읽는다."""

    if not isinstance(payload, dict):
        return []
    items = payload.get("violations")
    if not isinstance(items, list):
        return []
    return [str(item.get("file")) for item in items if isinstance(item, dict)]


def rehearse(plant: Plant, *, workspace: Path | None = None) -> Rehearsal:
    """한 층의 red 를 실제 파일로 재현한다 — 심은 트리 · 대조군 · 없는 트리."""

    base = Path(workspace) if workspace is not None else Path(tempfile.mkdtemp(prefix=f"red-{plant.layer}-"))
    try:
        target = base / plant.planted
        target.parent.mkdir(parents=True, exist_ok=True)

        target.write_text(plant.violation, encoding="utf-8")
        dirty_exit, dirty_out, dirty = run_audit(plant.script, base, base / "dirty.json")
        paths = seen_files(dirty)

        target.write_text(plant.allowed, encoding="utf-8")
        clean_exit, clean_out, _ = run_audit(plant.script, base, base / "clean.json")

        blind_exit, blind_out, _ = run_audit(plant.script, base / "does-not-exist", base / "blind.json")

        crashed = [text for text in (dirty_out, clean_out, blind_out) if CRASH_MARKER in text]
        return Rehearsal(
            layer=plant.layer,
            planted=plant.planted,
            dirty_exit=dirty_exit,
            seen=len(paths),
            named=plant.planted in paths,
            spoken=plant.planted in dirty_out,
            clean_exit=clean_exit,
            blind_exit=blind_exit,
            crashed=bool(crashed),
            note=f"{plant.script} 가 traceback 으로 죽었다" if crashed else "",
        )
    finally:
        if workspace is None:
            shutil.rmtree(base, ignore_errors=True)


def run(plants: tuple[Plant, ...] = PLANTS) -> tuple[Rehearsal, ...]:
    """리허설을 돌린다 — 한 층이 예외로 죽어도 나머지는 계속 본다(한 번에 다 보고한다)."""

    records: list[Rehearsal] = []
    for plant in plants:
        try:
            records.append(rehearse(plant))
        except Exception as exc:  # noqa: BLE001 - 리허설 중 예외도 판정으로 바꾼다(사고를 통과로 세지 않는다)
            records.append(
                Rehearsal(
                    layer=plant.layer,
                    planted=plant.planted,
                    dirty_exit=None,
                    seen=0,
                    named=False,
                    spoken=False,
                    clean_exit=None,
                    blind_exit=None,
                    crashed=True,
                    note=f"{type(exc).__name__}: {exc}",
                )
            )
    return tuple(records)


def self_probe(plants: tuple[Plant, ...] | None = None) -> Probe:
    """판정 규칙을 합성 관찰로 다시 물어본다 — 리허설은 하지 않는다(측정 없이 판정만)."""

    items = PLANTS if plants is None else plants
    cases = Cases()

    def record(
        *,
        dirty_exit: int | None = EXIT_GATE,
        seen: int = 1,
        named: bool = True,
        spoken: bool = True,
        clean_exit: int | None = EXIT_OK,
        blind_exit: int | None = EXIT_GATE,
        crashed: bool = False,
        note: str = "",
    ) -> Rehearsal:
        return Rehearsal(
            layer="probe_layer",
            planted="probe/planted.py",
            dirty_exit=dirty_exit,
            seen=seen,
            named=named,
            spoken=spoken,
            clean_exit=clean_exit,
            blind_exit=blind_exit,
            crashed=crashed,
            note=note,
        )

    cases.check("심은 위반을 지목한 리허설은 통과다", record().ok)
    cases.check("red 를 못 내면(exit 0) 통과가 아니다", not record(dirty_exit=EXIT_OK).ok)
    cases.check("위반을 못 보면 통과가 아니다", not record(seen=0).ok)
    cases.check("심은 파일을 지목하지 않으면 통과가 아니다", not record(named=False).ok)
    cases.check("출력에 파일 이름이 없으면 통과가 아니다", not record(spoken=False).ok)
    cases.check("대조군이 빨간이면 통과가 아니다", not record(clean_exit=EXIT_GATE).ok)
    cases.check("빈 트리를 통과시키면 통과가 아니다", not record(blind_exit=EXIT_OK).ok)
    cases.check("사고로 죽은 리허설은 통과가 아니다", not record(crashed=True, note="traceback").ok)
    cases.check("대조군을 안 돌린 리허설(None)은 통과가 아니다", not record(clean_exit=None).ok)

    cases.check("리허설 대상이 있다", len(items) > 0)
    cases.check("심는 파일이 트리 밖으로 나가지 않는다", all(_inside_tree(plant.planted) for plant in items))
    cases.check("서로 다른 위반을 심는다", len({plant.violation for plant in items}) == len(items))
    cases.check("층마다 다른 감사를 돌린다", len({plant.script for plant in items}) == len(items))
    cases.check("심는 감사 스크립트가 실재한다", all((SCRIPTS_DIR / plant.script).exists() for plant in items))
    cases.check(
        "심는 내용이 그 층의 계약을 실제로 깬다(허용 형태와 다르다)",
        all(plant.violation != plant.allowed for plant in items),
    )
    cases.check("리허설되지 않는 층은 이유와 함께 선언돼 있다", all(reason.strip() for reason in DECLARED.values()))
    cases.check("하한에 근거가 기록돼 있다", all(floor.why.strip() for floor in coverage_floors(items)))
    cases.check("하한이 지금 리허설 수를 넘지 않는다", not floor_problems(coverage_floors(items)))
    cases.check(
        "눈멀게 한 하한(관측 0)은 문다",
        bool(floor_problems([Floor("리허설 대상", 0, _MIN_REHEARSALS, why="근거")])),
    )
    return cases.probe()


def _inside_tree(relative: str) -> bool:
    """심는 자리가 트리 **안**인가 — 밖으로 나가는 경로는 저장소를 건드린다(절대 경로·`..` 를 거부)."""

    path = Path(relative)
    return not path.is_absolute() and ".." not in path.parts and bool(path.parts)


def as_mapping(records: tuple[Rehearsal, ...], probe: Probe) -> dict[str, object]:
    return {
        "command": ["python", "scripts/red_rehearsal.py"],
        "layers": [record.as_mapping() for record in records],
        "declared": dict(sorted(DECLARED.items())),
        "plants": [plant.as_mapping() for plant in PLANTS],
        "probe": probe.as_mapping(),
        "floors": floor_records(coverage_floors()),
        "counts": {
            "layers": len(records),
            "ok": sum(1 for record in records if record.ok),
            "unseen": sum(1 for record in records if record.dirty_exit == EXIT_OK),
            "false_positive": sum(1 for record in records if record.clean_exit not in (None, EXIT_OK)),
        },
    }


def describe(records: tuple[Rehearsal, ...], probe: Probe) -> str:
    lines = [f"[red] 층 {len(records)}개 — 저장소 밖 트리에 위반을 심어 red 를 재현했다"]
    for record in records:
        state = "RED OK  " if record.ok else "NO RED  "
        lines.append(
            f"  {state}{record.layer} · 심은 트리 exit {record.dirty_exit}(본 위반 {record.seen} · 지목 {record.named}) · "
            f"대조군 exit {record.clean_exit} · 빈 트리 exit {record.blind_exit}"
        )
        for problem in record.problems:
            lines.append(f"    - {problem}")
    lines.append(f"* 자기시험 {probe.cases}건 재판정{' — 통과' if probe.ok else ' — 실패'}")
    lines.append(
        "* 이 리허설이 없으면 “위반 0건” 은 ’다 봤는데 깨끗하다’ 와 ’한 번도 red 를 낸 적이 없다’ 를 구분하지 못한다."
    )
    return "\n".join(lines)


def _probe_or_failure(plants: tuple[Plant, ...] | None = None) -> Probe:
    """자기시험이 예외로 죽으면 그 사실을 **실패**로 바꾼다(사고는 판정이 아니다)."""

    try:
        return self_probe(plants)
    except Exception as exc:  # noqa: BLE001
        return Probe(cases=0, failures=(f"자기시험이 예외로 죽었다: {type(exc).__name__}: {exc}",))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="red_rehearsal",
        description="위반 0건인 감사가 실제로 빨간을 낼 수 있는지 저장소 밖 트리에서 재현한다",
    )
    parser.add_argument("--gate", action="store_true", help="하나라도 red 를 못 내면 exit 1")
    parser.add_argument("--emit-json", action="store_true", help="결과만 stdout JSON 으로 낸다(게이트·리뷰가 읽는다)")
    parser.add_argument("--self-test", action="store_true", help="자기시험만 돌리고 끝낸다")
    args = parser.parse_args(argv)

    probe = _probe_or_failure()
    if args.self_test:
        print(describe_self_test("red_rehearsal", probe))
        return EXIT_OK if probe.ok else EXIT_GATE

    records = run()
    problems = [problem for record in records for problem in record.problems]
    problems.extend(probe_problems(probe, name="red_rehearsal"))
    problems.extend(floor_problems(coverage_floors()))
    if args.emit_json:
        print(json.dumps(as_mapping(records, probe), ensure_ascii=False, indent=2))
        # JSON 을 내는 실행도 **판정을 종료 코드로** 말한다 — 진단은 stdout 에 그대로 남는다.
        return EXIT_GATE if problems else EXIT_OK
    print(describe(records, probe))
    if not args.gate:
        return EXIT_OK
    for problem in problems:
        print(f"[FAIL] {problem}", file=sys.stderr)
    return EXIT_GATE if problems else EXIT_OK


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
