#!/usr/bin/env python
"""전량 회귀의 **빨간 집합**을 seed 별로 수집해, 결정적 실패와 순서 민감 실패를 분리한다.

왜 필요한가
===========
회귀를 한 번 돌려 `N failed` 만 적으면 두 종류를 뭉갠다.

  * **결정적 실패** — 같은 scope·같은 명령이면 매번 같은 집합. 오너가 정리할 몫이다.
  * **variant 민감 실패** — 프로세스·순서 조건에 따라 집합이 바뀐다(hash seed·수집 순서·동시 실행·
    tmp 충돌·공유 상태). 이걸 뭉개면 “우연히 초록”과 “우연히 빨강”이 구별되지 않는다.

그래서 **같은 scope** 를 명시적 hash seed 로 두 번 이상 돌리고, junit XML(구조화된 산출물)을 읽어
교집합(=결정적)과 대칭차(=seed 민감)를 계산한다. 로그 문자열을 긁지 않는다.

scope 와 variant
================
`scope` 는 **무엇을** 돌렸는지(예: `flat-001-060`, `cognitive`), `variant` 는 **어떤 조건으로** 돌렸는지의
이름이다(기본 `seed-<n>`, 수집 순서를 뒤집은 회차는 예컨대 `rev-seed-101`). 원장은 **scope 별로** 두 개
이상의 **서로 다른 variant** 를 요구한다 — 서로 다른 scope 의 실패를 교집합하면 없던 결정적 실패가 생기고,
같은 variant 를 두 번 재도 “같은 조건을 두 번” 잰 것이라 아무것도 분리하지 못한다.

그래서 이 원장이 재는 것은 "seed 를 바꾸면 달라지는가" 하나가 아니다 — scope 안에서 **variant 를 바꿨을 때
빨강 집합이 달라지는가**이고, variant 에 수집 순서를 넣으면 **순서 민감성**이 같은 계산에 들어온다.

긴 suite 를 한 번에 못 돌리는 환경(단일 호출 상한)에서는 scope 를 나눠 여러 번 호출하면 된다.
각 호출은 자기 scope 의 xml 을 남기고, 마지막에 `--from-junit` 으로 합쳐 읽는다.

읽는 사람을 위한 계약
=====================
* `--run` 없이 `--from-junit` 으로 **이미 받아 둔 XML 만** 다시 읽을 수 있다(재실행 0회).
* 분류표(`OWNERS`)에 없는 결정적 실패는 **무소유(unowned)** 로 보고한다. 새 빨강을 “누군가 알아서”
  로 넘기지 않기 위해서다.
* `--gate` 를 주면 ① 무소유 결정적 실패 ② variant 가 둘 미만인 scope ③ variant 민감 집합이 허용치를 넘는 경우
  중 하나라도 있으면 exit 1.

실행:    .venv/bin/python scripts/regression_ledger.py --run 2 --scope cognitive --extra 'tests/cognitive'
  .venv/bin/python scripts/regression_ledger.py --seeds 202 --scope flat-081-220 --extra "$FILES"  # 중단 재실행
  FILES=$(ls tests/test_*.py | sed -n '1,60p' | tr '\\n' ' ')
  .venv/bin/python scripts/regression_ledger.py --run 2 --scope flat-001-060 --extra "$FILES"
  .venv/bin/python scripts/regression_ledger.py --from-junit .regression-ledger --gate

회차가 남기는 것: `<scope>__<variant>.xml`(판정 근거) · `<scope>__<variant>.log`(pytest 출력 원문) ·
원장 JSON(요약). scope·variant·명령이 원장에 그대로 남으므로 나중에 같은 조건을 재현할 수 있다.

순서 민감성 측정(수집 순서를 뒤집은 회차):
  FILES=$(ls tests/test_*.py | sed -n '1,80p' | tac | tr '\n' ' ')
  .venv/bin/python scripts/regression_ledger.py --seeds 101 --variant rev-seed-101 \
      --scope flat-001-080 --extra "$FILES"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess  # noqa: S404 - 이 저장소의 회귀 명령을 그대로 부르는 것이 목적이다
import sys
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

EXIT_OK: Final[int] = 0
EXIT_GATE: Final[int] = 1

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
DEFAULT_JUNIT_DIR: Final[Path] = REPO_ROOT / ".regression-ledger"
DEFAULT_JSON: Final[Path] = REPO_ROOT / "docs" / "ssak-ai-core" / "evidence" / "regression_ledger.json"
DEFAULT_PATTERN: Final[str] = "not slow and not benchmark"
DEFAULT_SCOPE: Final[str] = "tests"
DEFAULT_SEEDS: Final[tuple[int, ...]] = (101, 202)

# 알려진 결정적 실패의 **소유자**. 여기 없는 실패는 `unowned` 로 남는다(조용히 넘기지 않는다).
OWNERS: Final[tuple[tuple[str, str, str], ...]] = (
    (
        "tests/test_cr14_fence_movement_detection.py",
        "cr14-lane",
        "선언 후보~HEAD 커밋 이동·트리 지문 비교 — 기록 커밋 규율(커밋을 만들지 않은 상태의 기준선)",
    ),
    (
        "tests/test_model_registry.py",
        "config-owner",
        "루트 config.yaml 이 번들 기본값과 다름 — 그 파일은 소유자가 동기화하는 자리",
    ),
    (
        "tests/test_nx07_doc_consistency.py",
        "release-owner",
        "EX-05 대장 행의 지표/귀속 두 단계 분리 — 오너 판정 브리프"
        "(docs/qa/2026-09-16-followup/nx10/EX05_PROMOTION_CONFLICT.md §5 B)",
    ),
    (
        "tests/test_ws01_project_binding.py",
        "ws01/cr01-lane",
        "ConversationStorageMigrationRequiredError — 이 체크아웃의 대화 저장소가 v2 마이그레이션 전이라"
        "request root 를 resolve 하는 단계에서 fail-closed 된다(단독 실행으로도 재현 · CR-01 런북 소관)",
    ),
    (
        "tests/test_trn02_timeout_resource.py",
        "trn02-lane",
        "학습 job cancel API 가 ok=False 를 돌려준다 — 단독 실행으로 재현되는 결정적 실패(다른 레인 소관)",
    ),
)

# 허용되는 seed 민감 실패 수. 이 수를 넘으면 `--gate` 가 실패한다(추세 감시용).
DEFAULT_DRIFT_ALLOWANCE: Final[int] = 0

_RED_TAGS: Final[frozenset[str]] = frozenset({"failure", "error"})
_REPORT_NAME: Final[re.Pattern[str]] = re.compile(r"^(?P<scope>.+)__(?P<variant>[^/]+)\.xml$")


@dataclass(frozen=True)
class Owner:
    """실패 하나의 소유자 표기."""

    lane: str
    reason: str

    def as_mapping(self) -> dict[str, str]:
        return {"lane": self.lane, "reason": self.reason}


@dataclass(frozen=True)
class Report:
    """junit XML 하나에서 읽은 것.

    `aborted` 는 pytest 가 **내부 오류**를 남겼다는 뜻이다(`<testcase classname="pytest" name="internal">`).
    실측 예: 시험이 fd 1 을 닫아 종료 시 `sys.stdout.flush()` 가 `OSError: [Errno 9]` 를 내고 회차가
    중간에 끝났다(수집 1860 중 1078 까지만 기록). 그런 회차의 빨간 집합은 **비교 대상이 아니다** —
    끝까지 돌지 않았으므로 “안 나온 실패”가 “통과”처럼 보인다.
    """

    tests: int
    skipped: int
    red: frozenset[str]
    aborted: bool


@dataclass(frozen=True)
class RunResult:
    """한 scope 의 한 회차 관찰.

    `variant` 가 회차의 정체성이다(기본 `seed-<n>`). 같은 scope 안에서 variant 가 서로 달라야 비교가 된다.
    """

    scope: str
    variant: str
    seed: int
    junit: str
    tests: int
    red: frozenset[str]
    skipped: int
    aborted: bool = False

    def as_mapping(self) -> dict[str, object]:
        return {
            "scope": self.scope,
            "variant": self.variant,
            "seed": self.seed,
            "junit": self.junit,
            "tests": self.tests,
            "skipped": self.skipped,
            "aborted": self.aborted,
            "red": sorted(self.red),
        }


@dataclass
class Ledger:
    """여러 scope·회차를 합친 원장."""

    runs: list[RunResult] = field(default_factory=list)
    deterministic: frozenset[str] = frozenset()
    drift: frozenset[str] = frozenset()
    owners: dict[str, Owner] = field(default_factory=dict)
    unowned: tuple[str, ...] = ()
    incomplete: tuple[str, ...] = ()
    aborted: tuple[str, ...] = ()
    command: tuple[str, ...] = ()

    @property
    def scopes(self) -> dict[str, int]:
        """scope 별 회차 수."""

        counts: dict[str, int] = {}
        for run in self.runs:
            counts[run.scope] = counts.get(run.scope, 0) + 1
        return counts

    def as_mapping(self) -> dict[str, object]:
        return {
            "command": list(self.command),
            "runs": [run.as_mapping() for run in self.runs],
            "scopes": self.scopes,
            "incomplete_scopes": list(self.incomplete),
            "aborted_scopes": list(self.aborted),
            "deterministic": sorted(self.deterministic),
            "drift": sorted(self.drift),
            "owners": {node: owner.as_mapping() for node, owner in sorted(self.owners.items())},
            "unowned": list(self.unowned),
            "counts": {
                "runs": len(self.runs),
                "scopes": len(self.scopes),
                "deterministic": len(self.deterministic),
                "drift": len(self.drift),
                "unowned": len(self.unowned),
            },
        }


def slug(text: str) -> str:
    """scope 이름을 파일명에 안전한 형태로 만든다."""

    cleaned = re.sub(r"[^0-9A-Za-z._-]+", "-", text).strip("-")
    return cleaned or "scope"


def module_file(classname: str) -> str | None:
    """junit 의 dotted classname 을 저장소 상대 파일 경로로 되돌린다(모르면 None)."""

    if not classname:
        return None
    parts = classname.split(".")
    for cut in range(len(parts), 0, -1):
        candidate = Path(*parts[:cut]).with_suffix(".py")
        if (REPO_ROOT / candidate).is_file():
            return str(candidate)
    return None


def display_path(path: Path) -> str:
    """저장소 안이면 상대 경로, 밖(scratch)이면 절대 경로 — 기록을 위해 실패하지 않는다."""

    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def node_id(classname: str, name: str) -> str:
    """사람이 읽고 소유자를 붙일 수 있는 id — 파일::[class::]test."""

    path = module_file(classname)
    if path is None:
        return f"{classname}::{name}"
    tail = classname.split(".")[len(Path(path).with_suffix("").parts) :]
    if tail:
        return f"{path}::{'.'.join(tail)}::{name}"
    return f"{path}::{name}"


def parse_junit(text: str, *, source: str) -> Report:
    """junit XML 하나에서 수집 수·skip 수·빨간 집합·중단 여부를 읽는다."""

    root = ET.fromstring(text)  # noqa: S314 - 우리가 방금 만든 산출물만 읽는다
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    if not suites:
        raise ValueError(f"junit 리포트에서 testsuite 를 찾지 못했다: {source}")
    total = 0
    skipped = 0
    red: set[str] = set()
    aborted = False

    for suite in suites:
        total += int(suite.get("tests") or 0)
        skipped += int(suite.get("skipped") or 0)
        for case in suite.iter("testcase"):
            classname = case.get("classname") or ""
            name = case.get("name") or ""
            tags = {child.tag for child in case}
            if classname == "pytest" and name == "internal":
                aborted = True
            if tags & _RED_TAGS:
                red.add(node_id(classname, name))
    return Report(tests=total, skipped=skipped, red=frozenset(red), aborted=aborted)


def owner_table(entries: Sequence[tuple[str, str, str]] = OWNERS) -> dict[str, Owner]:
    """분류표를 파일 경로 → 소유자 mapping 으로 만든다."""

    return {path: Owner(lane=lane, reason=reason) for path, lane, reason in entries}


def classify(node: str, owners: Mapping[str, Owner]) -> Owner | None:
    """실패 id 의 소유자를 찾는다 — 파일 경로 접두 매칭(정확히 그 파일만)."""

    return owners.get(node.split("::", 1)[0])


def build_ledger(runs: Iterable[RunResult]) -> Ledger:
    """scope 안에서 교집합(결정적)/대칭차(seed 민감)를 계산하고, scope 들을 합친다."""

    collected = list(runs)
    if not collected:
        raise ValueError("회차가 하나도 없다 — 최소 한 회차의 junit 이 필요하다")

    by_scope: dict[str, list[RunResult]] = {}
    for run in collected:
        by_scope.setdefault(run.scope, []).append(run)

    deterministic: set[str] = set()
    drift: set[str] = set()
    incomplete: list[str] = []
    aborted_scopes: list[str] = []
    for scope, entries in sorted(by_scope.items()):
        variants = {entry.variant for entry in entries}
        if any(entry.aborted for entry in entries):
            aborted_scopes.append(scope)
            incomplete.append(scope)
            continue
        if len(entries) < 2 or len(variants) < 2:
            incomplete.append(scope)
            continue
        sets = [entry.red for entry in entries]
        intersection = set(sets[0])
        union = set(sets[0])
        for red in sets[1:]:
            intersection &= red
            union |= red
        deterministic |= intersection
        drift |= union - intersection

    table = owner_table()
    ledger = Ledger(runs=collected)
    ledger.deterministic = frozenset(deterministic)
    ledger.drift = frozenset(drift)
    ledger.incomplete = tuple(incomplete)
    ledger.aborted = tuple(aborted_scopes)
    ledger.owners = {
        node: owner for node in sorted(ledger.deterministic) if (owner := classify(node, table)) is not None
    }
    ledger.unowned = tuple(sorted(node for node in ledger.deterministic if node not in ledger.owners))
    return ledger


def default_variant(seed: int) -> str:
    """기본 variant 이름 — hash seed 하나만 바꿔 돌린 회차."""

    return f"seed-{seed}"


def report_path(directory: Path, scope: str, variant: str) -> Path:
    """회차 산출물 경로 — scope 와 variant 가 파일명에 그대로 남는다."""

    return directory / f"{slug(scope)}__{slug(variant)}.xml"


def load_runs(directory: Path) -> list[RunResult]:
    """디렉터리의 junit XML 을 회차로 읽는다 — 재실행 없이 원장을 다시 만든다."""

    runs: list[RunResult] = []
    for path in sorted(directory.glob("*.xml")):
        match = _REPORT_NAME.match(path.name)
        if match is None:
            continue
        report = parse_junit(path.read_text(encoding="utf-8"), source=str(path))
        variant = match.group("variant")
        runs.append(
            RunResult(
                scope=match.group("scope"),
                variant=variant,
                seed=variant_seed(variant),
                junit=display_path(path),
                tests=report.tests,
                red=report.red,
                skipped=report.skipped,
                aborted=report.aborted,
            )
        )
    if not runs:
        raise SystemExit(f"junit 산출물이 없다: {display_path(directory)} — 먼저 --run 으로 돌려야 한다")
    return runs


def variant_seed(variant: str) -> int:
    """variant 이름에서 hash seed 를 복원한다(모르면 -1 — 기록용 숫자일 뿐이다)."""

    match = re.search(r"seed-(\d+)", variant)
    return int(match.group(1)) if match else -1


def pytest_command(*, pattern: str, extra: Sequence[str]) -> list[str]:
    """회귀 명령 — 회차별 junit 을 `--junitxml` 로 남긴다(로그 문자열 파싱 금지)."""

    return [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--tb=no",
        "-p",
        "no:cacheprovider",
        "-m",
        pattern,
        *extra,
    ]


def run_once(*, scope: str, variant: str, seed: int, directory: Path, pattern: str, extra: Sequence[str]) -> RunResult:
    """한 회차 실행 — scope·variant 를 그리고 hash seed 를 명시적으로 고정한다."""

    directory.mkdir(parents=True, exist_ok=True)
    report = report_path(directory, scope, variant)
    log = report.with_suffix(".log")
    env = dict(os.environ, PYTHONHASHSEED=str(seed))
    command = [*pytest_command(pattern=pattern, extra=extra), f"--junitxml={report}"]
    print(f"[regression-ledger] {scope} · {variant} · PYTHONHASHSEED={seed} → {report.name}", flush=True)
    completed = subprocess.run(  # noqa: S603
        command, cwd=REPO_ROOT, env=env, capture_output=True, text=True, check=False
    )
    captured_text = (completed.stdout or "") + (completed.stderr or "")
    log.write_text(captured_text, encoding="utf-8")
    tail = [line for line in captured_text.splitlines() if line.strip()]
    if tail:
        print(f"  {tail[-1].strip()}", flush=True)
    if not report.is_file():
        raise SystemExit(f"pytest 가 junit 을 남기지 않았다(exit {completed.returncode}) — 로그: {display_path(log)}")
    parsed = parse_junit(report.read_text(encoding="utf-8"), source=str(report))
    if parsed.aborted:
        print(f"  경고: 이 회차는 pytest 내부 오류로 중단됐다({parsed.tests} 까지만 기록) — 다시 돌려야 한다")
    return RunResult(
        scope=scope,
        variant=variant,
        seed=seed,
        junit=display_path(report),
        tests=parsed.tests,
        red=parsed.red,
        skipped=parsed.skipped,
        aborted=parsed.aborted,
    )


def describe(ledger: Ledger) -> str:
    """사람이 읽는 요약 — scope 별 회차·결정적·seed 민감·소유자."""

    lines = ["# 전량 회귀 원장", ""]
    for scope, count in ledger.scopes.items():
        entries = [run for run in ledger.runs if run.scope == scope]
        seeds = ", ".join(run.variant for run in entries)
        tests = sum(run.tests for run in entries)
        reds = sum(len(run.red) for run in entries)
        mark = ""
        if scope in ledger.incomplete:
            mark = (
                "  ← 중단된 회차가 있다(판정 제외)"
                if scope in ledger.aborted
                else "  ← 서로 다른 variant 가 둘 미만(판정 불가)"
            )
        lines.append(f"* {scope}: 회차 {count}({seeds}) · 수집 {tests} · 빨강 합 {reds}{mark}")
    lines.append("")
    lines.append(f"* 결정적 실패 {len(ledger.deterministic)}건(모든 scope 에서 같은 집합)")
    for node in sorted(ledger.deterministic):
        owner = ledger.owners.get(node)
        mark = f"[{owner.lane}] {owner.reason}" if owner else "**무소유**"
        lines.append(f"  - {node} — {mark}")
    lines.append(f"* variant 민감 실패 {len(ledger.drift)}건(회차 조건마다 달라짐)")
    for node in sorted(ledger.drift):
        lines.append(f"  - {node}")
    if ledger.unowned:
        lines.append(f"* 무소유 결정적 실패 {len(ledger.unowned)}건 — 분류표에 없다")
    return "\n".join(lines)


def gate_failures(ledger: Ledger, *, drift_allowance: int) -> list[str]:
    """`--gate` 판정 — 무소유·미완 scope·허용치 초과 drift 를 문장으로 돌려준다."""

    problems: list[str] = []
    if ledger.unowned:
        problems.append(f"무소유 결정적 실패 {len(ledger.unowned)}건: " + ", ".join(ledger.unowned))
    if ledger.aborted:
        problems.append(
            "중단된 회차가 있어 판정에서 제외한 scope(끝까지 돌지 않은 회차는 증거가 아니다): "
            + ", ".join(ledger.aborted)
        )
    still_incomplete = tuple(scope for scope in ledger.incomplete if scope not in ledger.aborted)
    if still_incomplete:
        problems.append(
            "서로 다른 variant 두 회차가 없는 scope(같은 조건을 두 번 재면 아무것도 분리되지 않는다): "
            + ", ".join(still_incomplete)
        )
    if len(ledger.drift) > drift_allowance:
        problems.append(
            f"variant 민감 실패 {len(ledger.drift)}건 > 허용 {drift_allowance}건: " + ", ".join(sorted(ledger.drift))
        )
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="전량 회귀의 결정적/seed 민감 실패를 분리한다")
    parser.add_argument("--run", type=int, default=0, help="회차 수(0이면 실행하지 않고 기존 junit 만 읽는다)")
    parser.add_argument(
        "--seeds",
        default=None,
        help="회차의 hash seed 를 직접 지정한다(쉼표 구분). 중단된 회차 하나만 다시 돌릴 때 쓴다",
    )
    parser.add_argument("--scope", default=DEFAULT_SCOPE, help="이번 회차가 재는 선택의 이름(예: cognitive)")
    parser.add_argument(
        "--variant",
        default=None,
        help="회차 조건의 이름(기본 seed-<seed>). 수집 순서를 바꾼 회차는 rev-seed-<seed> 처럼 적는다",
    )
    parser.add_argument("--junit-dir", type=Path, default=DEFAULT_JUNIT_DIR, help="junit XML 을 두는 자리")
    parser.add_argument(
        "--from-junit",
        type=Path,
        default=None,
        help="실행 없이 이 디렉터리의 junit XML 만 읽어 원장을 다시 만든다",
    )
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON, help="원장 JSON 산출물")
    parser.add_argument("--pattern", default=DEFAULT_PATTERN, help="pytest -m 식")
    parser.add_argument(
        "--extra",
        action="append",
        default=[],
        metavar="'PYTEST ARGS'",
        help="pytest 에 덧붙일 인자(따옴표로 묶어 쓴다, 여러 번 가능) — 예: --extra 'tests/cognitive'",
    )
    parser.add_argument("--gate", action="store_true", help="무소유·미완 scope·drift 초과면 exit 1")
    parser.add_argument(
        "--drift-allowance",
        type=int,
        default=DEFAULT_DRIFT_ALLOWANCE,
        help="허용하는 seed 민감 실패 수",
    )
    parsed = parser.parse_args(argv)

    extra = [token for chunk in parsed.extra for token in shlex.split(chunk)]
    seeds = (
        tuple(int(token) for token in str(parsed.seeds).split(",") if token.strip())
        if parsed.seeds
        else tuple(DEFAULT_SEEDS[0] + 101 * index for index in range(parsed.run))
    )
    runs = [
        run_once(
            scope=parsed.scope,
            variant=parsed.variant or default_variant(seed),
            seed=seed,
            directory=parsed.junit_dir,
            pattern=parsed.pattern,
            extra=extra,
        )
        for seed in seeds
    ] or load_runs(parsed.from_junit or parsed.junit_dir)

    ledger = build_ledger(runs)
    ledger.command = tuple(pytest_command(pattern=parsed.pattern, extra=extra))
    parsed.json.parent.mkdir(parents=True, exist_ok=True)
    parsed.json.write_text(json.dumps(ledger.as_mapping(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(describe(ledger))
    print(f"\n원장 JSON: {display_path(parsed.json)}")

    if not parsed.gate:
        return EXIT_OK
    problems = gate_failures(ledger, drift_allowance=parsed.drift_allowance)
    for problem in problems:
        print(f"[FAIL] {problem}", file=sys.stderr)
    return EXIT_GATE if problems else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
