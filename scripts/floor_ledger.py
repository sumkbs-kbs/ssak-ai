#!/usr/bin/env python
"""하한 원장 — 이 저장소의 탐지력 하한을 **한 자리에서** 물어볼 수 있게 한다.

하한은 다섯 harness 의 코드 상수와 네 개의 기록 artifact 에 흩어져 있고, “이 저장소에는 어떤 하한이 있고 무엇을 보고
정해졌는가” 를 묻는 자리는 사람의 기억뿐이었다. 그 물음이 중요한 까닭은 하한이 **판단**이기 때문이다 — 값만 있으면 나중에
누구도 그것을 낮춰도 되는지 판단할 수 없다. 그래서 이 도구는 층마다 하한을 모아 **관측·하한값·여유·근거(`why`)** 와
**승인(무엇을 보고 언제 누가)** 을 한 표로 낸다.

어디서 값을 가져오는가: 하한은 **카나리아와 같은 눈**으로 읽는다(`harness_canary.harness_floors`) — 기록이 있는 층은
저장본(마지막으로 승인된 실행의 관측), 나머지는 저장소를 직접 재서. 두 번째 구현을 만들면 표와 판정이 갈라지므로,
기록 artifact 가 승인 문장(`method`)·날짜를 담고 있으면 그것을, 담고 있지 않으면 **그 근거 파일의 마지막 커밋**(날짜·사람·해시)을
승인으로 적는다. 커밋은 하한 자체의 변경이 아닐 수도 있으므로 그 사실도 행마다 함께 적는다(모르는 것을 아는 척하지 않는다).

실패로 보는 것:

  * **하한이 없는 harness** — 하한 없는 층은 빈손으로도 결과를 통과시킨다(그 층의 하한을 원장이 말할 수 없다).
  * **근거 없는 하한** — 왜 그 값인지 물을 수 없는 하한은 나중에 내려도 되는지 판단할 수 없다.
  * **읽지 못한 기록 artifact** — 그 층의 하한을 원장이 말할 수 없다(기록이 깨졌거나 사라졌다).
  * **아무도 읽지 않는 기록** — `floors` 를 담았는데 어떤 harness 도 그것을 읽지 않으면, 그 기록은 다음 결함을 가리는
    면죄부다(기록을 남긴 층이 사라져도 아무도 모른다).
  * **승인 날짜를 읽지 못함** — git 이 없거나 근거가 추적되지 않으면 “언제 누가” 를 말할 수 없다(원장의 답이 추측이 된다).
  * **원장에 실린 하한이 너무 적음** — 모든 출처가 망가져 빈 표가 되면 “빠진 하한 없음” 과 구별되지 않는다.

```sh
.venv/bin/python scripts/floor_ledger.py --gate        # 표 + 판정(하나라도 어긋나면 exit 1)
.venv/bin/python scripts/floor_ledger.py --emit-json   # 리뷰·게이트 stage 가 읽는다(판정은 종료 코드)
.venv/bin/python scripts/floor_ledger.py --self-test   # 자기시험만(저장소를 읽지 않는다)
```
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import tempfile
import time
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from types import ModuleType
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
EXIT_FAIL: Final[int] = 1
EVIDENCE_DIR: Final[Path] = REPO_ROOT / "docs" / "ssak-ai-core" / "evidence"
KIND_RECORDED: Final[str] = "기록"
KIND_MEASURED: Final[str] = "직접 측정"
KIND_SELF: Final[str] = "자기 판정"
# 자기 자신을 카나리아 루프에서 빼는 자리 — 하한을 만들려고 자기를 부르면 무한 재귀다.
# 대신 자기 하한을 **표의 마지막 행**으로 싣고 스스로 판정한다(자기시험·게이트도 같은 값을 본다).
SELF_NAME: Final[str] = "floor_ledger"
# 카나리아 script — 원장이 **신뢰하는 유일한 roster 출처**이므로 자기시험의 커밋 확인도 여기에 건다.
CANARY_SCRIPT: Final[Path] = SCRIPTS_DIR / "harness_canary.py"
# 이 원장 자신의 하한 — 표에 실린 하한이 이 수보다 적으면 “하한을 못 본 것” 이다. 모든 출처가 실패하면 표가 비는데,
# 빈 표는 “빠진 하한 없음” 과 구별되지 않는다.
_MIN_FLOORS: Final[int] = 15
_WHY_MIN_FLOORS: Final[str] = (
    "2026-09-23 기준 관측: 다른 층을 보는 하한 18개가 실린다(기록 넷: digest 2 · 회귀 원장 2 · 상태 주장 2 · "
    "배포 산출물 6 = 12, 직접 다섯: 열거 1 · namespace 1 · 도달 2 · 게이트 1 · 리허설 1 = 6). 하한 15는 **한 층이 "
    "roster 에서 빠져도 정상 측정을 막지 않지만**(가장 큰 층이 6개를 들고 있다) **둘 이상 빠지면(≤ 12) 표를 내주면서 "
    "‘빠진 하한 없음’ 이라고 말하지 못하게** 한다 — 하한이나 출처가 망가지면 여기서 드러난다."
)
# 자기시험용 합성 승인 — git 을 읽지 않고 행 규칙만 묻는다.
_COMMIT_SAMPLE: Final[dict[str, str]] = {
    "on": "2026-01-01",
    "by": "tester",
    "hash": "abc1234",
    "path": "scripts/probe.py",
}
# 커밋에서 “언제 누가” 를 읽는 자리 — 하한 자체의 변경이 아닐 수 있으므로 그 사실을 행마다 적는다.
COMMIT_NOTE: Final[str] = (
    "그 하한을 담은 파일의 마지막 커밋이다(하한만 바뀐 커밋이 아닐 수 있다 — 기록 artifact 는 그 커밋이 곧 승인이다)"
)


def load_canary() -> ModuleType:
    """카나리아를 불러온다 — **roster 와 하한을 읽는 눈의 단일 출처**(원장이 자기 눈을 만들지 않는다)."""

    spec = importlib.util.spec_from_file_location("ledger_canary", CANARY_SCRIPT)
    if spec is None or spec.loader is None:
        raise SystemExit(f"{CANARY_SCRIPT.name} 를 불러오지 못했다")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def commit_of(path: Path, *, repo: Path = REPO_ROOT) -> dict[str, str] | None:
    """그 파일의 마지막 커밋(날짜·사람·해시) — git 이 없거나 추적되지 않으면 None(호출자가 실패로 처리)."""

    try:
        relative = str(path.resolve().relative_to(repo.resolve()))
    except ValueError:  # 저장소 밖 — 커밋을 말할 수 없다
        return None
    result = subprocess.run(
        ["git", "log", "-1", "--format=%cs%x09%an%x09%h", "--", relative],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    fields = result.stdout.strip().split("\t")
    if result.returncode != 0 or len(fields) != 3 or not all(fields):
        return None
    return {"on": fields[0], "by": fields[1], "hash": fields[2], "path": relative, "note": COMMIT_NOTE}


def orphan_records(evidence_dir: Path, known: Sequence[Path]) -> tuple[str, ...]:
    """`floors` 를 담았는데 아무도 읽지 않는 기록 — 순수 함수라 합성 입력으로 시험한다.

    읽는 자리(`known`)는 roster 가 가리키는 artifact 경로다. 기록을 남긴 층이 roster 에서 사라지면 여기서 걸린다.
    """

    known_paths = {path.resolve() for path in known}
    found: list[str] = []
    for path in sorted(evidence_dir.glob("*.json")):
        if path.resolve() in known_paths:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue  # 못 읽는 파일은 이 검사의 대상이 아니다(그 파일을 읽는 층이 따로 실패한다)
        floors = payload.get("floors") if isinstance(payload, dict) else None
        if isinstance(floors, list) and floors:
            found.append(_display(path))
    return tuple(found)


def _display(path: Path) -> str:
    """사람이 읽는 경로 — 저장소 안이면 상대 경로(다른 기계에서는 절대 경로가 틀린다)."""

    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return path.name


@dataclass(frozen=True, slots=True)
class LayerRow:
    """한 층의 하한 묶음 — 어디서 읽었고, 무엇으로 승인됐고, 하한이 무엇인가."""

    name: str
    kind: str
    source: str
    floors: tuple[Floor, ...]
    approval: dict[str, str]
    commit: dict[str, str] | None
    note: str = ""

    @property
    def approval_text(self) -> str:
        """사람이 읽는 승인(전문) — 기록이 승인 문장을 담고 있으면 그것, 아니면 그 근거 파일의 마지막 커밋."""

        method = self.approval.get("method", "").strip()
        recorded = f"{self.approval.get('recorded_on', '')} {method}".strip()
        if method and method.startswith(self.approval.get("recorded_on", "")):
            recorded = method  # 기록이 이미 날짜로 시작하면 두 번 적지 않는다
        if recorded:
            return recorded
        if self.commit is None:
            return "**못 읽음**"
        return f"{self.commit['on']} {self.commit['by']} {self.commit['hash']}"

    @property
    def approval_short(self) -> str:
        """표 칸에 들어갈 승인 — 날짜와 지문만(전문은 층별 각주에 있다)."""

        if self.approval:
            return f"{self.approval.get('recorded_on', '?')} 기록"
        if self.commit is None:
            return "**못 읽음**"
        return f"{self.commit['on']} {self.commit['hash']}"

    def as_mapping(self) -> dict[str, object]:
        return {
            "name": self.name,
            "kind": self.kind,
            "source": self.source,
            "floors": floor_records(self.floors),
            "approval": dict(self.approval),
            "commit": dict(self.commit) if self.commit else None,
            "approval_text": self.approval_text,
            "approval_short": self.approval_short,
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class Ledger:
    """이 실행이 읽은 원장 — 층·고아 기록·문제."""

    rows: tuple[LayerRow, ...]
    orphans: tuple[str, ...]
    problems: tuple[str, ...]
    seconds: float

    @property
    def canvas(self) -> int:
        """이 원장이 **다른 층에서 본** 하한 수 — 자기 하한이 재는 값이다(자기를 세면 저절로 참이 된다)."""

        return sum(len(row.floors) for row in self.rows if row.kind != KIND_SELF)

    @property
    def floors(self) -> int:
        return sum(len(row.floors) for row in self.rows)

    @property
    def ok(self) -> bool:
        return not self.problems

    def as_mapping(self, probe: Probe) -> dict[str, object]:
        return {
            "command": ["python", "scripts/floor_ledger.py"],
            "layers": [row.as_mapping() for row in self.rows],
            "orphans": list(self.orphans),
            "counts": {
                "layers": len(self.rows),
                "floors": self.floors,
                "canvas": self.canvas,
                "recorded": sum(1 for row in self.rows if row.kind == KIND_RECORDED),
                "measured": sum(1 for row in self.rows if row.kind == KIND_MEASURED),
                "self": sum(1 for row in self.rows if row.kind == KIND_SELF),
                "orphans": len(self.orphans),
                "without_basis": sum(1 for row in self.rows for floor in row.floors if not floor.why.strip()),
                "undated": sum(1 for row in self.rows if row.commit is None),
            },
            # 소요 시간은 **판정 수치에 넣지 않는다** — 게이트의 추이에 그날의 기계 속도가 섞이면 움직임이 안 보인다.
            "runtime": {"seconds": round(self.seconds, 1)},
            "coverage": {"canvas": self.canvas, "floors": self.floors, "min_floors": _MIN_FLOORS},
            "floors": floor_records(coverage_floors(self)),
            "probe": probe.as_mapping(),
            "problems": list(self.problems),
            "verdict": "PASS" if self.ok else "FAIL",
        }


def ledger_floor(observed: int) -> Floor:
    """이 원장의 하한 — 표에 실린 하한 수(값 + 근거)."""

    return Floor("원장에 실린 하한", observed, _MIN_FLOORS, why=_WHY_MIN_FLOORS)


def coverage_floors(ledger: Ledger | None = None) -> list[Floor]:
    """이 원장의 탐지력 하한 — 관측은 **다른 층에서 본 하한 수**다(자가 참조면 아무것도 말하지 않는다)."""

    return [ledger_floor(ledger.canvas if ledger is not None else _MIN_FLOORS)]


def read_floor_rows(name: str, canary: ModuleType) -> tuple[LayerRow, str]:
    """한 층의 하한과 승인을 읽는다 — (행, 문제). 읽지 못한 이유를 함께 돌려준다(추측하지 않는다)."""

    recorded = str(canary.ARTIFACT_FLOORS.get(name, ""))
    source = recorded or f"scripts/{name}.py"
    if recorded:
        approval, payload_note = _record_approval(REPO_ROOT / recorded)
        try:
            recorded_floors = canary.artifact_floors(name)
        except (Exception, SystemExit) as exc:  # noqa: BLE001 - 못 읽은 이유도 판정이다
            recorded_floors = None
            payload_note = f"기록을 읽는 중 예외: {type(exc).__name__}: {exc}"
        if recorded_floors is None:
            return (
                LayerRow(name, KIND_RECORDED, source, (), approval, None, note=payload_note),
                f"기록 artifact 를 읽지 못했다({source}) — 이 원장은 그 층의 하한을 말할 수 없다",
            )
        floors = tuple(recorded_floors)
        return LayerRow(name, KIND_RECORDED, source, floors, approval, commit_of(REPO_ROOT / source), payload_note), ""
    try:
        module = canary.load_harness(name)
        floors = tuple(canary.harness_floors(name, module))
    except (Exception, SystemExit) as exc:  # noqa: BLE001 - 못 읽은 이유도 판정이다
        return (
            LayerRow(name, KIND_MEASURED, source, (), {}, None, note="하한을 읽지 못했다"),
            f"{name} 의 하한을 읽지 못했다: {type(exc).__name__}: {exc}",
        )
    return LayerRow(name, KIND_MEASURED, source, floors, {}, commit_of(REPO_ROOT / source)), ""


def _record_approval(path: Path) -> tuple[dict[str, str], str]:
    """기록 artifact 의 승인 문장·날짜와, 그 사실에 대한 한 줄 설명."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}, "기록을 읽지 못했다"
    if not isinstance(payload, dict):
        return {}, "기록이 객체가 아니다"
    approval = {key: str(payload[key]) for key in ("method", "recorded_on") if str(payload.get(key, "")).strip()}
    note = (
        "기록 artifact 의 승인 문장·날짜를 그대로 실었다"
        if approval
        else "기록 artifact 에 승인 문장이 없다(리뷰가 저장본과 새 측정을 대조한다)"
    )
    return approval, note


def build(*, evidence_dir: Path = EVIDENCE_DIR) -> Ledger:
    """원장을 만든다 — roster 는 카나리아가 알고, 하한은 카나리아의 눈으로 읽는다."""

    started = time.monotonic()
    canary = load_canary()
    known = [REPO_ROOT / str(path) for path in canary.ARTIFACT_FLOORS.values()]
    readings = [read_floor_rows(str(name), canary) for name in canary.HARNESSES if str(name) != SELF_NAME]
    # 자기 하한을 **표의 마지막 행**으로 싣는다 — “이 원장은 몇 개를 보나” 가 표 밖에 있으면 읽는 사람이 못 본다.
    # 자기 하한은 다른 층을 보는 수(캔버스)를 재므로, 자기 자신을 세면 저절로 참이 된다 — 그래서 자기 행은 캔버스에 안 든다.
    canvas = sum(len(row.floors) for row, _ in readings)
    readings.append(
        (
            LayerRow(
                SELF_NAME,
                KIND_SELF,
                "scripts/floor_ledger.py",
                (ledger_floor(canvas),),
                {},
                commit_of(Path(__file__).resolve()),
                note="이 원장 자신이다 — 자기 하한은 스스로 판정하고, 카나리아도 같은 눈으로 본다",
            ),
            "",
        )
    )
    problems = [problem for row, read_problem in readings for problem in row_problems(row, read_problem)]
    orphans = orphan_records(evidence_dir, known)
    for orphan in orphans:
        problems.append(
            f"{orphan} 에 `floors` 가 있는데 어떤 harness 도 읽지 않는다 — 아무도 읽지 않는 하한 기록은 면죄부다"
        )
    problems.extend(floor_problems([ledger_floor(canvas)]))
    return Ledger(tuple(row for row, _ in readings), orphans, tuple(problems), time.monotonic() - started)


def row_problems(row: LayerRow, read_problem: str) -> list[str]:
    """한 행의 문제 — 읽지 못한 행은 그 한 문장으로 끝내고, 읽은 행은 하한·근거·승인을 각각 묻는다."""

    if read_problem:
        return [read_problem]
    problems: list[str] = []
    if not row.floors:
        problems.append(f"{row.name} 에 하한이 없다 — 하한 없는 층은 빈손으로도 결과를 통과시킨다")
    for floor in row.floors:
        if not floor.why.strip():
            problems.append(
                f"{row.name} 의 하한 `{floor.label}` 에 근거가 없다 — 왜 그 값인지 물을 수 없는 하한은 "
                "내려도 되는지 판단할 수 없다"
            )
    if row.commit is None:
        problems.append(
            f"{row.name} 의 승인 날짜를 읽지 못했다({row.source} — git 없음 또는 추적되지 않는 근거): "
            "“언제 누가” 를 모르면서 아는 척하지 않는다"
        )
    return problems


def self_probe() -> Probe:
    """판정 규칙을 합성 입력으로 다시 물어본다 — **저장소를 읽지 않는다**(리뷰가 돌릴 수 있어야 한다)."""

    cases = Cases()
    floors = coverage_floors()
    cases.check("원장 자신의 하한이 있다", len(floors) == 1)
    cases.check("하한에 근거가 기록돼 있다", all(floor.why.strip() for floor in floors))
    cases.check("하한이 지금 관측을 넘지 않는다", not floor_problems(floors))
    cases.check(
        "눈멀게 한 하한(관측 0)은 문다", bool(floor_problems([Floor("원장에 실린 하한", 0, _MIN_FLOORS, why="근거")]))
    )
    empty = Ledger((), (), (), 1.5).as_mapping(Probe(cases=0, failures=()))
    empty_counts = empty["counts"]
    cases.check(
        "counts 에 소요 시간을 넣지 않는다(추이에 그날의 속도가 섞이지 않게)",
        isinstance(empty_counts, dict) and "seconds" not in empty_counts,
    )
    cases.equal("소요 시간은 runtime 으로 뺀다", empty["runtime"], {"seconds": 1.5})
    # 행 판정 — 읽은 행·못 읽은 행·근거 없는 행·승인 못 읽은 행이 각각 다르게 판정돼야 한다.
    healthy = LayerRow("probe", KIND_MEASURED, "scripts/probe.py", (Floor("수", 3, 1, why="근거"),), {}, _COMMIT_SAMPLE)
    cases.equal("정상 행은 문제가 없다", row_problems(healthy, ""), [])
    cases.equal(
        "승인을 못 읽은 행은 실패한다(언제 누가 를 모르면서 아는 척하지 않는다)",
        len(row_problems(replace(healthy, commit=None), "")),
        1,
    )
    cases.equal(
        "근거 없는 하한은 실패한다",
        len(row_problems(replace(healthy, floors=(Floor("수", 3, 1, why="  "),)), "")),
        1,
    )
    cases.equal("하한이 없는 층은 실패한다", len(row_problems(replace(healthy, floors=()), "")), 1)
    cases.equal(
        "읽지 못한 행은 그 한 문장으로 끝난다(같은 자리를 두 번 탓하지 않는다)",
        row_problems(replace(healthy, floors=(), commit=None), "기록을 읽지 못했다"),
        ["기록을 읽지 못했다"],
    )
    # 고아 기록 — 아무도 읽지 않는 `floors` 는 면죄부다. 읽는 자리를 알면 조용하다.
    with tempfile.TemporaryDirectory() as work:
        evidence = Path(work)
        mine = evidence / "read.json"
        mine.write_text(json.dumps({"floors": [{"label": "a", "observed": 1, "minimum": 1, "why": "근거"}]}), "utf-8")
        lonely = evidence / "lonely.json"
        lonely.write_text(json.dumps({"floors": [{"label": "b", "observed": 1, "minimum": 1, "why": "근거"}]}), "utf-8")
        (evidence / "floorsless.json").write_text(json.dumps({"counts": {"a": 1}}), "utf-8")
        (evidence / "broken.json").write_text("{", "utf-8")
        names = lambda found: [Path(item).name for item in found]  # noqa: E731 - 시험용 한 줄
        cases.equal("아무도 읽지 않는 기록만 고아로 센다", names(orphan_records(evidence, [mine])), ["lonely.json"])
        cases.equal("`floors` 가 없는 artifact 는 고아가 아니다", names(orphan_records(evidence, [mine, lonely])), [])
        cases.equal(
            "roster 가 그 층을 잊으면 그 기록도 고아가 된다(면죄부가 남지 않는다)",
            names(orphan_records(evidence, [])),
            ["lonely.json", "read.json"],
        )
    # 커밋 읽기 — 저장소 밖이거나 추적되지 않으면 None(추측하지 않는다).
    cases.check("저장소 밖 경로는 커밋을 말하지 않는다", commit_of(Path("/tmp/없는파일.json")) is None)
    canary_commit = commit_of(CANARY_SCRIPT) or {}
    cases.check(
        "추적되는 파일은 커밋(날짜·사람·해시)을 읽는다", bool(canary_commit.get("by") and canary_commit.get("hash"))
    )
    return cases.probe()


def _probe_or_failure() -> Probe:
    """자기시험이 예외로 죽으면 그 사실을 **실패**로 바꾼다(사고는 판정이 아니다)."""

    try:
        return self_probe()
    except Exception as exc:  # noqa: BLE001
        return Probe(cases=0, failures=(f"자기시험이 예외로 죽었다: {type(exc).__name__}: {exc}",))


def _pad(text: str, width: int) -> str:
    """한글·한자·전각 기호를 두 칸으로 세어 자리를 맞춘다(글자 수로 맞추면 표가 어긋난다)."""

    cells = sum(2 if unicodedata.east_asian_width(char) in "WFA" else 1 for char in text)
    return text + " " * max(0, width - cells)


def describe(ledger: Ledger, probe: Probe) -> str:
    recorded = sum(1 for row in ledger.rows if row.kind == KIND_RECORDED)
    lines = [
        f"[ledger] 하한 원장 — {len(ledger.rows)}층 · 하한 {ledger.floors}개(기록 {recorded} · "
        f"직접 {len(ledger.rows) - recorded - 1} · 자기 1) · 다른 층에서 본 하한 {ledger.canvas}개 · "
        f"고아 기록 {len(ledger.orphans)}",
        f"  {_pad('층', 26)} {_pad('하한', 14)} {'관측':>6} {'하한값':>7} {'여유':>6} 승인",
    ]
    for row in ledger.rows:
        if not row.floors:
            lines.append(
                f"  {_pad(row.name, 26)} {_pad('**하한 없음**', 14)} {'-':>6} {'-':>7} {'-':>6} {row.approval_short}"
            )
            continue
        for floor in row.floors:
            lines.append(
                f"  {_pad(row.name, 26)} {_pad(floor.label, 14)} {floor.observed:>6d} {floor.minimum:>7d} "
                f"{floor.margin:>6d} {row.approval_short}"
            )
    lines.append("  출처와 승인(전문)")
    for row in ledger.rows:
        lines.append(f"    · {_pad(row.name, 26)} {row.kind} {row.source}")
        lines.append(f"      승인: {row.approval_text}")
        if row.note:
            lines.append(f"      각주: {row.note}")
    for orphan in ledger.orphans:
        lines.append(f"  고아기록  {orphan} — 어떤 harness 도 읽지 않는다")
    lines.append(
        f"  소요      {ledger.seconds:.1f}초 · 자기시험 {probe.cases}건 재판정 · 승인 = 기록의 승인 문장 또는 "
        "그 근거 파일의 마지막 커밋(하한만 바뀐 커밋이 아닐 수 있다)"
    )
    for problem in ledger.problems:
        lines.append(f"    - {problem}")
    lines.append(
        "* 이 표가 없으면 “이 저장소에 어떤 하한이 있고 무엇을 보고 정해졌는가” 는 열 개 파일을 손으로 열어야 알 수 있다."
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="floor_ledger",
        description="탐지력 하한 원장 — 어떤 하한이 있고, 무엇을 보고, 언제 누가 승인했는가",
    )
    parser.add_argument("--gate", action="store_true", help="하나라도 어긋나면 exit 1")
    parser.add_argument("--emit-json", action="store_true", help="결과를 stdout JSON 으로 낸다(리뷰·게이트가 읽는다)")
    parser.add_argument("--self-test", action="store_true", help="자기시험만 돌리고 끝낸다(저장소를 읽지 않는다)")
    parser.add_argument(
        "--evidence", type=Path, default=EVIDENCE_DIR, help="고아 기록을 찾을 자리(기본: 증거 디렉터리)"
    )
    args = parser.parse_args(argv)

    probe = _probe_or_failure()
    if args.self_test:
        print(describe_self_test("floor_ledger", probe))
        return EXIT_OK if probe.ok else EXIT_FAIL

    ledger = build(evidence_dir=args.evidence)
    problems = list(ledger.problems)
    problems.extend(probe_problems(probe, name="floor_ledger"))
    if args.emit_json:
        print(json.dumps(ledger.as_mapping(probe), ensure_ascii=False, indent=2))
        # JSON 을 내는 실행도 **판정을 종료 코드로** 말한다 — 진단은 stdout 에 그대로 남는다.
        return EXIT_FAIL if problems else EXIT_OK
    print(describe(ledger, probe))
    if not args.gate:
        return EXIT_OK if ledger.ok else EXIT_FAIL
    for problem in problems:
        print(f"[FAIL] {problem}", file=sys.stderr)
    return EXIT_FAIL if problems else EXIT_OK


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
