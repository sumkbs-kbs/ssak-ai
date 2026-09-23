#!/usr/bin/env python
"""증거 게이트 — 여섯 층을 **한 번에** 돌리고, 어느 층이 얇은지 한 줄로 말한다.

여섯 harness 가 각자 게이트(자기시험 + 탐지력 하한)를 갖게 됐지만, **그것을 도는 자리는 사람의 기억뿐**이었다.
CI 는 이 게이트를 하나도 돌리지 않았고, “어디가 얇은가” 를 보려면 여덟 개 명령을 손으로 쳐야 했다. 이 도구가
그 자리를 하나로 묶는다 — stage 마다 독립 process 로 돌리고, 종료 코드·소요 시간·**첫 실패 문장**을 모아
어느 층이 빨간지 이름으로 말한다.

계약 — **돌리지 못한 층은 통과가 아니다.** 이 도구 자신도 같은 병에 걸릴 수 있다(stage 목록이 비거나,
스크립트 이름이 틀려 아무것도 실행되지 않는데 “문제 없음” 으로 끝나는 것). 그래서 여섯 harness 에 올린
규율을 이 도구에도 그대로 적용한다:

  * **stage 하한** — 실행 대상 수가 하한보다 적으면 실패한다(목록이 비면 “볼 것이 없음” 이 아니라 사고다).
  * **없는 스크립트 = 실패** — 조용히 건너뛰지 않는다.
  * **제한 시간 초과 · 실행 실패 = 실패** — `exit_code` 가 없는 결과(`unrun`)는 판정이 아니라 사고다.
  * **tier 밖 층을 숨기지 않는다** — `fast` 실행은 로컬 회차 산출물이 필요한 회귀 원장을 보지 않는다.
    보고서는 그 층을 “이 실행이 보지 않은 층” 으로 적는다(초록으로 덮지 않는다).
  * **자기시험**(`--self-test`) — 판정 규칙(통과/실패/못 돌림 구분 · tier 필터 · 요약 문장 · stage roster)을
    매 실행 합성 결과로 다시 물어본다. 판정 규칙이 깨진 실행은 증거가 아니다.

**수치도 함께 본다 — 어제보다 얇아졌는가.** 층마다 `exit_code` 만 보면 "지금 빨간가" 밖에 모른다. 그래서 게이트는
각 층을 **한 번의 실행으로** 판정과 수치를 함께 받고(`--emit-json`·`--json`·`--output` — 그 경로가 실패를 종료
코드로 말하지 않으면 여기서 판정이 사라진다), 그 수치를 저장소의 **기준**(사람이 마지막으로 승인한 상태)과 비교해
줄어든 수를 먼저 보여 준다. 수의 이동 자체는 **판정이 아니다** — 하한을 깨는 감소는 그 층의 자체 게이트가 이미
실패시킨다. 판정 대상은 세 가지: 수치를 **읽지 못한 층** · **못 돌린 층** · **깨진 기준 파일**.

```sh
.venv/bin/python scripts/evidence_gate.py                  # fast tier — 8초 안에 끝난다
.venv/bin/python scripts/evidence_gate.py --tier full      # 회귀 원장까지(로컬 산출물 필요)
.venv/bin/python scripts/evidence_gate.py --json .artifacts/evidence-gate.json
.venv/bin/python scripts/evidence_gate.py --no-baseline    # 기준과 비교하지 않는다
.venv/bin/python scripts/evidence_gate.py --record-baseline --method "..."   # 지금을 새 기준으로(사람의 커밋)
.venv/bin/python scripts/evidence_gate.py --self-test      # 판정 규칙만 재판정(아무것도 돌리지 않는다)
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
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import ModuleType
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
SCRIPTS_DIR: Final[Path] = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from harness_contract import Cases, Floor, Probe, floor_problems, floor_records, probe_problems  # noqa: E402

EXIT_OK: Final[int] = 0
EXIT_GATE: Final[int] = 1

TIER_FAST: Final[str] = "fast"
TIER_FULL: Final[str] = "full"
TIERS: Final[tuple[str, ...]] = (TIER_FAST, TIER_FULL)

# 결과의 종류 — `pass` 만 통과다. `unrun`(못 돌림)과 `outside_tier`(이 실행이 보지 않음)는 통과가 아니다.
KIND_PASS: Final[str] = "pass"
KIND_FAIL: Final[str] = "fail"
KIND_UNRUN: Final[str] = "unrun"
KIND_OUTSIDE: Final[str] = "outside_tier"
KINDS: Final[tuple[str, ...]] = (KIND_PASS, KIND_FAIL, KIND_UNRUN, KIND_OUTSIDE)

DEFAULT_TIMEOUT: Final[float] = 300.0

# 수치를 내는 자리 — `stdout` 은 JSON 을 stdout 으로, `file` 은 `{report}` 자리에 파일로 쓴다.
SOURCE_STDOUT: Final[str] = "stdout"
SOURCE_FILE: Final[str] = "file"
SOURCES: Final[tuple[str, ...]] = (SOURCE_STDOUT, SOURCE_FILE)
REPORT_TOKEN: Final[str] = "{report}"

# 지난 승인 시점의 수치 — 게이트는 이 파일을 **읽기만** 한다(갱신은 `--record-baseline` + 사람의 커밋).
BASELINE: Final[Path] = REPO_ROOT / "docs" / "ssak-ai-core" / "evidence" / "evidence_gate_baseline.json"

# 수치의 움직임 — 감소는 **판정이 아니라 관찰**이다(하한을 깨는 감소는 그 층의 자체 게이트가 이미 실패시킨다).
MOVED_SAME: Final[str] = "same"
MOVED_UP: Final[str] = "up"
MOVED_DOWN: Final[str] = "down"
MOVED_NEW: Final[str] = "new"
MOVED_GONE: Final[str] = "gone"
MOVED_NONE: Final[str] = "none"
MOVEMENTS: Final[tuple[str, ...]] = (MOVED_SAME, MOVED_UP, MOVED_DOWN, MOVED_NEW, MOVED_GONE, MOVED_NONE)


@dataclass(frozen=True, slots=True)
class Stage:
    """한 층을 도는 방법 — 무엇을(script) 어떻게(args) 돌려 무엇을 보는지(describes).

    `args` 는 **판정과 수치를 한 번에 내는 실행**이다(그래서 이음매가 중요하다 — JSON 을 내는 경로가 실패를
    종료 코드로 말하지 않으면 여기서 판정이 사라진다). 파일로 수치를 내는 층은 `{report}` 자리에 이 실행이
    만든 임시 경로가 들어간다.
    """

    name: str
    tier: str
    script: str
    args: tuple[str, ...]
    describes: str
    read_source: str
    numbers: tuple[str, ...] = ("counts", "coverage")
    requires: tuple[str, ...] = ()


# stage roster — 단일 출처. `REQUIRED_STAGES` 와 어긋나면 자기시험이 실패한다(이름을 지워도 잡힌다).
STAGES: Final[tuple[Stage, ...]] = (
    Stage(
        "review",
        TIER_FAST,
        "architecture_review.py",
        ("--quiet", "--output", REPORT_TOKEN),
        "24원칙·§63·§52 매핑과 증거의 정합",
        SOURCE_FILE,
        numbers=("measured", "checks"),
    ),
    Stage("canary", TIER_FAST, "harness_canary.py", ("--emit-json",), "탐지력 하한이 실제로 무는가", SOURCE_STDOUT),
    Stage(
        "digest_drift",
        TIER_FAST,
        "digest_drift.py",
        ("--emit-json",),
        "증거가 못 박은 digest 의 현재 일치",
        SOURCE_STDOUT,
    ),
    Stage(
        "audit_state_claims",
        TIER_FAST,
        "audit_state_claims.py",
        ("--emit-json",),
        "산문의 현재-상태 주장 재판정",
        SOURCE_STDOUT,
    ),
    Stage(
        "audit_enum_identity",
        TIER_FAST,
        "audit_enum_identity.py",
        ("--json", REPORT_TOKEN),
        "enum identity 비교 감사",
        SOURCE_FILE,
        numbers=("count", "scanned_files"),
    ),
    Stage(
        "audit_test_namespace_purge",
        TIER_FAST,
        "audit_test_namespace_purge.py",
        ("--json", REPORT_TOKEN),
        "import 시점 purge 감사",
        SOURCE_FILE,
        numbers=("count", "coverage"),
    ),
    Stage(
        "measure_cognitive_surface",
        TIER_FAST,
        "measure_cognitive_surface.py",
        ("--output", REPORT_TOKEN),
        "legacy→core 도달 표 측정",
        SOURCE_FILE,
        numbers=("coverage",),
    ),
    Stage(
        "regression_ledger",
        TIER_FULL,
        "regression_ledger.py",
        ("--gate", "--json", REPORT_TOKEN),
        "전량 회귀 원장(scope 별 seed 두 회차)",
        SOURCE_FILE,
        requires=(".regression-ledger",),
    ),
)

# 자기시험이 고정하는 요구 목록 — 상수를 순회하기만 하면 **지워진 이름**은 순회 대상에서 사라져 안 보인다.
REQUIRED_STAGES: Final[tuple[str, ...]] = (
    "review",
    "canary",
    "digest_drift",
    "audit_state_claims",
    "audit_enum_identity",
    "audit_test_namespace_purge",
    "measure_cognitive_surface",
    "regression_ledger",
)

_MIN_STAGES: Final[int] = 8

# 카나리아가 아는 harness 중 **stage 가 아닌 것** — 게이트 자신뿐이다. stage 로 넣으면 게이트가 자기를 불러
# 끝나지 않으므로(재귀) 그 하한은 카나리아가 대신 본다. 이 목록이 늘어나면 자기시험이 실패한다.
SELF_EXEMPT: Final[dict[str, str]] = {
    "evidence_gate": "게이트 자신이다 — stage 로 넣으면 무한 재귀다(하한은 카나리아가 본다)",
}


def _stage_floor(stages: tuple[Stage, ...]) -> Floor:
    """stage 수의 하한 — 근거를 함께 기록한다(값만 남기면 나중에 누구도 낮춰도 되는지 판단할 수 없다)."""

    return Floor(
        label="stage",
        observed=len(stages),
        minimum=_MIN_STAGES,
        why=(
            "2026-09-23 기준 관측: 여섯 harness 게이트 + 리뷰 + 회귀 원장 = 8 stage. "
            "하한이 잡으려는 것은 '얼마나 많이 도나' 가 아니라 '한 층도 돌지 않고 통과했나' 다. "
            "층이 정말 사라지면 근거를 적고 이 값을 내린다."
        ),
    )


def coverage_floors(stages: tuple[Stage, ...] | None = None) -> list[Floor]:
    """이 도구의 탐지력 하한 — 카나리아가 저장본 없이 직접 재는 자리(harness 와 같은 계약).

    기본값을 `STAGES` 로 못 박지 않고 호출 시점에 읽는다 — 기본 인자가 상수를 **스냅숏**하면 roster 를
    바꾸 놓고도 하한은 옛 명단을 세는 모순이 생긴다(시험이 그 경우를 재현한다).
    """

    return [_stage_floor(STAGES if stages is None else stages)]


def numeric_snapshot(payload: object, keys: tuple[str, ...]) -> dict[str, int]:
    """JSON payload 에서 **수를 고른다** — 지시한 키만 보고, 수가 아니면 조용히 버린다.

    키가 dict 면 `키.이름`, list 면 길이, int 면 값으로 편다. 매직 키를 훑지 않고 stage 가 키를 지목하는 이유:
    무엇을 비교하는지가 roster 한 줄에 드러나야 하고, 새 층이 엉뚱한 수를 실어도 추이에 섞이지 않아야 한다.
    """

    found: dict[str, int] = {}
    for key in keys:
        value = payload.get(key) if isinstance(payload, dict) else None
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            found[key] = value
        elif isinstance(value, list):
            found[key] = len(value)
        elif isinstance(value, dict):
            for name, item in value.items():
                if isinstance(item, bool):
                    continue
                if isinstance(item, int):
                    found[f"{key}.{name}"] = item
                elif isinstance(item, list):
                    found[f"{key}.{name}"] = len(item)
    return dict(sorted(found.items()))


@dataclass(frozen=True, slots=True)
class Outcome:
    """한 stage 의 관찰 — 종류·종료 코드·소요 시간·사람이 읽을 이유·**그 층이 낸 수치**."""

    stage: Stage
    kind: str
    exit_code: int | None
    seconds: float
    detail: str = ""
    numbers: tuple[tuple[str, int], ...] = ()
    read_detail: str = ""

    @property
    def ok(self) -> bool:
        """통과는 `pass` 뿐이다 — 못 돌린 것도, 이 tier 가 보지 않은 것도 통과가 아니다."""

        return self.kind == KIND_PASS

    @property
    def numbers_mapping(self) -> dict[str, int]:
        return dict(self.numbers)

    def as_mapping(self) -> dict[str, object]:
        return {
            "name": self.stage.name,
            "tier": self.stage.tier,
            "kind": self.kind,
            "exit_code": self.exit_code,
            "seconds": round(self.seconds, 2),
            "detail": self.detail,
            "describes": self.stage.describes,
            "numbers": self.numbers_mapping,
            "read_detail": self.read_detail,
        }


def stages_for(tier: str) -> tuple[Stage, ...]:
    """그 tier 가 도는 stage — `full` 은 `fast` 를 포함한다(상위 tier)."""

    if tier not in TIERS:
        raise SystemExit(f"모르는 tier 다: {tier} (가능: {', '.join(TIERS)})")
    if tier == TIER_FAST:
        return tuple(stage for stage in STAGES if stage.tier == TIER_FAST)
    return STAGES


def tier_outsiders(tier: str) -> tuple[Stage, ...]:
    """이 tier 가 **보지 않는** stage — 초록으로 덮지 않고 이름으로 적는다."""

    return tuple(stage for stage in STAGES if stage not in stages_for(tier))


def first_failure_detail(stdout: str, stderr: str) -> str:
    """실패한 stage 에서 사람이 읽을 한 줄 — `[FAIL]` 문장을 우선하고, 없으면 마지막 줄."""

    for block in (stdout, stderr):
        for line in block.splitlines():
            stripped = line.strip()
            if stripped.startswith("[FAIL]"):
                return stripped
    for block in (stdout, stderr):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if lines:
            return lines[-1][:400]
    return "(출력 없음)"


def stage_argv(stage: Stage, report: Path | None) -> list[str]:
    """그 stage 의 실행 argv — `{report}` 자리에 이번 실행의 임시 경로를 채운다.

    자리를 주지 않으면 **거부한다**: 자리표시자를 그대로 넘기면 그 층이 저장소 뿌리에 `{report}` 라는 이름의
    파일을 쓴다(실제로 그랬고, 시험 실행이 그 파일을 남겼다).
    """

    if REPORT_TOKEN in stage.args and report is None:
        raise ValueError(f"{stage.name}: 수치를 받을 자리(report)를 주지 않았다 — 자리표시자를 그대로 넘기지 않는다")
    argv = [sys.executable, str(SCRIPTS_DIR / stage.script)]
    for token in stage.args:
        argv.append(str(report) if token == REPORT_TOKEN else token)
    return argv


def read_numbers(
    stage: Stage, result: subprocess.CompletedProcess[str], report: Path | None
) -> tuple[dict[str, int], str]:
    """그 층이 낸 수치 — 읽지 못했으면 그 이유를 돌려준다(빈 dict 를 “그대로” 로 쓰지 않는다)."""

    raw = ""
    if stage.read_source == SOURCE_STDOUT:
        raw = result.stdout
    elif stage.read_source == SOURCE_FILE:
        if report is None or not report.exists():
            return {}, f"수치 파일을 만들지 않았다({stage.read_source} 경로)"
        raw = report.read_text(encoding="utf-8")
    else:
        return {}, f"수치를 읽는 방법을 모른다: {stage.read_source!r}"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {}, f"수치가 JSON 이 아니다: {exc.msg}"
    numbers = numeric_snapshot(payload, stage.numbers)
    if not numbers:
        return {}, f"{', '.join(stage.numbers)} 에서 수를 찾지 못했다 — 그 층이 내는 수가 바뀌었는지 확인해야 한다"
    return numbers, ""


def run_stage(stage: Stage, *, timeout: float = DEFAULT_TIMEOUT, report_dir: Path | None = None) -> Outcome:
    """stage 하나를 독립 process 로 돌린다 — 예외도 삼키지 않고 **판정으로** 바꾼다.

    한 번의 실행으로 **판정(종료 코드)과 수치(JSON)** 를 함께 받는다. 두 번 돌리면 시간이 두 배가 되고, 두 결과가
    서로 다른 순간을 가리킬 수 있다.
    """

    if REPORT_TOKEN in stage.args and report_dir is None:
        # 부르는 쪽이 자리를 주지 않으면 여기서 만든다 — 수치는 게이트의 계약이라 "안 받은 것" 과 "못 읽은 것" 을
        # 섞으면 멀정한 층이 "수치를 읽지 못했다" 로 실패한다.
        with tempfile.TemporaryDirectory(prefix="evidence-gate-") as workspace:
            return run_stage(stage, timeout=timeout, report_dir=Path(workspace))

    script = SCRIPTS_DIR / stage.script
    if not script.exists():
        return Outcome(stage, KIND_UNRUN, None, 0.0, f"스크립트가 없다: scripts/{stage.script}")
    for required in stage.requires:
        if not (REPO_ROOT / required).exists():
            return Outcome(
                stage,
                KIND_UNRUN,
                None,
                0.0,
                f"필요한 산출물이 없다: {required} — 이 체크아웃에서는 이 층을 돌릴 수 없다(로컬 회차를 만들어야 한다)",
            )

    report = (report_dir / f"{stage.name}.json") if report_dir is not None and REPORT_TOKEN in stage.args else None
    if report is not None:
        report.parent.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    try:
        result = subprocess.run(
            stage_argv(stage, report),
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return Outcome(
            stage,
            KIND_UNRUN,
            None,
            time.monotonic() - started,
            f"제한 시간 {timeout:.0f}s 안에 끝나지 않았다 — 중단은 판정이 아니다",
        )
    except OSError as exc:
        return Outcome(stage, KIND_UNRUN, None, time.monotonic() - started, f"실행하지 못했다: {exc}")

    numbers, read_detail = read_numbers(stage, result, report)
    frozen = tuple(sorted(numbers.items()))
    seconds = time.monotonic() - started
    if result.returncode == 0:
        return Outcome(stage, KIND_PASS, 0, seconds, "", frozen, read_detail)
    return Outcome(
        stage,
        KIND_FAIL,
        result.returncode,
        seconds,
        first_failure_detail(result.stdout, result.stderr),
        frozen,
        read_detail,
    )


def run(tier: str = TIER_FAST, *, timeout: float = DEFAULT_TIMEOUT) -> tuple[Outcome, ...]:
    """그 tier 의 stage 를 **전부** 돌린다(한 층이 죽어도 나머지는 계속 본다 — 한 번에 다 보고한다)."""

    return tuple(run_stage(stage, timeout=timeout) for stage in stages_for(tier))


def outsider_outcomes(tier: str) -> tuple[Outcome, ...]:
    """tier 밖 stage — 실패가 아니라 **기록**이다. 다만 통과로도 세지 않는다."""

    return tuple(
        Outcome(stage, KIND_OUTSIDE, None, 0.0, f"tier {tier} 밖이다 — 이 실행은 이 층을 보지 않았다")
        for stage in tier_outsiders(tier)
    )


def problems(outcomes: tuple[Outcome, ...], floors: list[Floor]) -> list[str]:
    """게이트 문장 — 실패와 못 돌림을 모두 모은다(tier 밖은 문제가 아니라 미보고다)."""

    found: list[str] = []
    for outcome in outcomes:
        if outcome.kind == KIND_FAIL:
            found.append(
                f"{outcome.stage.name} 실패(exit {outcome.exit_code}): {outcome.detail} — {outcome.stage.describes}"
            )
        elif outcome.kind == KIND_UNRUN:
            found.append(f"{outcome.stage.name} 을(를) 돌리지 못했다: {outcome.detail}")
        if outcome.read_detail:
            found.append(
                f"{outcome.stage.name} 의 수치를 읽지 못했다: {outcome.read_detail} — "
                "수가 안 보이는 층의 추이는 증거가 아니다"
            )
    return found + floor_problems(floors)


def as_mapping(
    tier: str,
    outcomes: tuple[Outcome, ...],
    *,
    outsiders: tuple[Outcome, ...] = (),
    probe: Probe,
    floors: list[Floor] | None = None,
    moves: list[Movement] | None = None,
    baseline: dict[str, object] | None = None,
) -> dict[str, object]:
    records = floors if floors is not None else coverage_floors()
    return {
        "command": ["python", "scripts/evidence_gate.py", "--tier", tier],
        "tier": tier,
        "stages": [outcome.as_mapping() for outcome in outcomes],
        "uncovered": [outcome.as_mapping() for outcome in outsiders],
        "counts": {
            "stages": len(outcomes),
            "ok": sum(1 for outcome in outcomes if outcome.kind == KIND_PASS),
            "failed": sum(1 for outcome in outcomes if outcome.kind == KIND_FAIL),
            "unrun": sum(1 for outcome in outcomes if outcome.kind == KIND_UNRUN),
            "outside_tier": len(outsiders),
        },
        "layers": snapshot(outcomes),
        "movements": [move.as_mapping() for move in (moves or [])],
        "baseline": baseline or {"path": "", "read": False},
        "probe": probe.as_mapping(),
        "floors": floor_records(records),
    }


def describe(
    tier: str,
    outcomes: tuple[Outcome, ...],
    outsiders: tuple[Outcome, ...],
    *,
    moves: list[Movement] | None = None,
    baseline: dict[str, object] | None = None,
    trend_all: bool = False,
) -> str:
    """사람이 30초에 읽는 건강 보고서 — 층마다 한 줄, 못 본 층은 따로, 그리고 **기준 대비 움직임**."""

    width = max(20, max(len(stage.name) for stage in STAGES))
    header = f"{'stage':{width}s} {'result':12s} {'exit':>4s} {'sec':>6s}  무엇을 보는가"
    lines = [f"[evidence-gate] tier {tier} — stage {len(outcomes)}개", header, "-" * len(header)]
    for outcome in outcomes:
        code = "-" if outcome.exit_code is None else str(outcome.exit_code)
        lines.append(
            f"{outcome.stage.name:{width}s} {outcome.kind:12s} {code:>4s} {outcome.seconds:6.1f}  "
            f"{outcome.stage.describes}"
        )
        if outcome.detail:
            lines.append(f"    · {outcome.detail}")
        if outcome.read_detail:
            lines.append(f"    · 수치를 읽지 못했다: {outcome.read_detail}")
    for outcome in outsiders:
        lines.append(f"{outcome.stage.name:{width}s} {outcome.kind:12s} {'-':>4s} {'-':>6s}  {outcome.stage.describes}")
    lines.append(
        f"PASS {sum(1 for o in outcomes if o.kind == KIND_PASS)} · "
        f"FAIL {sum(1 for o in outcomes if o.kind == KIND_FAIL)} · "
        f"못 돌림 {sum(1 for o in outcomes if o.kind == KIND_UNRUN)} · "
        f"tier 밖 {len(outsiders)}"
    )
    if outsiders:
        lines.append(
            "이 실행이 보지 않은 층: " + ", ".join(outcome.stage.name for outcome in outsiders) + " — 통과가 아니다"
        )
    if moves:
        lines.append("")
        lines.extend(trend_lines(moves, baseline or {}, show_all=trend_all))
    return "\n".join(lines)


def trend_lines(moves: list[Movement], baseline: dict[str, object], *, show_all: bool = False) -> list[str]:
    """기준 대비 움직임 — **줄어든 수치를 먼저** 보여 준다(늘어난 수부터 보면 얇아진 층이 묻힌다).

    그대로인 수는 기본으로 접는다: 움직이지 않은 60줄 사이에 “얼마나 바뀌었나” 라는 답이 묻힌다.
    """

    order = {MOVED_DOWN: 0, MOVED_GONE: 1, MOVED_NEW: 2, MOVED_NONE: 3, MOVED_UP: 4, MOVED_SAME: 5}
    source = str(baseline.get("path", "")) or "(기준 없음)"
    declared = baseline.get("recorded_on") or "(날짜 없음)"
    lines = [f"[추이] 기준 {source} · 승인 {declared}"]
    shown = [move for move in moves if show_all or move.kind != MOVED_SAME]
    for move in sorted(shown, key=lambda item: (order.get(item.kind, 9), item.layer, item.key)):
        lines.append(f"  · {move.describe()}")
    counts = {
        kind: sum(1 for move in moves if move.kind == kind)
        for kind in (MOVED_DOWN, MOVED_UP, MOVED_SAME, MOVED_NEW, MOVED_GONE, MOVED_NONE)
    }
    lines.append(
        f"  − ↓{counts[MOVED_DOWN]} · ↑{counts[MOVED_UP]} · 그대로 {counts[MOVED_SAME]}"
        f" · 기준에 없던 수 {counts[MOVED_NEW]} · 사라진 수 {counts[MOVED_GONE]}"
        f" · 기준 없는 층 {counts[MOVED_NONE]}"
        "  *(이동 자체는 판정이 아니다 — 하한을 깨는 감소는 그 층의 자체 게이트가 실패시킨다)*"
    )
    return lines


@dataclass(frozen=True, slots=True)
class Movement:
    """한 층의 한 수치가 기준 대비 어떻게 움직였는가 — 값의 이동은 **관찰**이고, 판정은 하한이 한다."""

    layer: str
    key: str
    kind: str
    before: int | None
    after: int | None

    @property
    def marker(self) -> str:
        return {
            MOVED_SAME: "=",
            MOVED_UP: "▲",
            MOVED_DOWN: "▼",
            MOVED_NEW: "+",
            MOVED_GONE: "−",
            MOVED_NONE: "?",
        }[self.kind]

    def describe(self) -> str:
        if self.kind == MOVED_NONE:
            return f"{self.layer} · 기준 없음(이 층을 처음 본다)"
        if not self.key:
            return f"{self.layer} · 이번 실행이 수치를 내지 않았다(기준에는 있었다)"
        if self.kind == MOVED_NEW:
            return f"{self.layer} · {self.key} {self.after} (기준에 없던 수)"
        if self.kind == MOVED_GONE:
            return f"{self.layer} · {self.key} {self.before} → 사라졌다"
        return f"{self.layer} · {self.key} {self.before} → {self.after} {self.marker}"

    def as_mapping(self) -> dict[str, object]:
        return {
            "layer": self.layer,
            "key": self.key,
            "kind": self.kind,
            "before": self.before,
            "after": self.after,
        }


def snapshot(outcomes: tuple[Outcome, ...]) -> dict[str, dict[str, int]]:
    """이번 실행이 본 수치 — **돌아간 층만** 담는다(못 돌린 층의 빈 값을 “그대로” 로 쓰지 않는다)."""

    return {
        outcome.stage.name: outcome.numbers_mapping
        for outcome in outcomes
        if outcome.kind in (KIND_PASS, KIND_FAIL) and outcome.numbers
    }


def movements(current: dict[str, dict[str, int]], baseline: dict[str, dict[str, int]] | None) -> list[Movement]:
    """기준 대비 움직임 — 층·수치 이름의 합집합을 보고, 한쪽에만 있는 수도 숨기지 않는다."""

    if baseline is None:
        return [Movement(layer, "", MOVED_NONE, None, None) for layer in sorted(current)]
    found: list[Movement] = []
    for layer in sorted(set(current) | set(baseline)):
        if layer not in baseline:
            found.append(Movement(layer, "", MOVED_NONE, None, None))
            continue
        if layer not in current:
            found.append(Movement(layer, "", MOVED_GONE, None, None))
            continue
        before, after = baseline[layer], current[layer]
        for key in sorted(set(before) | set(after)):
            if key not in before:
                found.append(Movement(layer, key, MOVED_NEW, None, after[key]))
            elif key not in after:
                found.append(Movement(layer, key, MOVED_GONE, before[key], None))
            elif after[key] > before[key]:
                found.append(Movement(layer, key, MOVED_UP, before[key], after[key]))
            elif after[key] < before[key]:
                found.append(Movement(layer, key, MOVED_DOWN, before[key], after[key]))
            else:
                found.append(Movement(layer, key, MOVED_SAME, before[key], after[key]))
    return found


def read_baseline(path: Path) -> tuple[dict[str, dict[str, int]], str]:
    """저장된 지난 승인 수치 — 없으면 빈 dict 와 “기준 없음”, 못 읽으면 빈 dict 와 이유."""

    if not path.exists():
        return {}, ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {}, f"{path} 를 읽지 못했다: {exc.msg}"
    if not isinstance(payload, dict):
        return {}, f"{path} 의 형태가 다르다(JSON object 가 아니다)"
    layers = payload.get("layers")
    if not isinstance(layers, dict) or not layers:
        return {}, f"{path} 에 층별 수치(`layers`)가 없다 — 기준으로 쓸 수 없다"
    snapshot: dict[str, dict[str, int]] = {}
    for layer, numbers in layers.items():
        if not isinstance(numbers, dict):
            return {}, f"{path} 의 {layer} 수치가 object 가 아니다"
        snapshot[str(layer)] = {
            str(k): int(v) for k, v in numbers.items() if isinstance(v, int) and not isinstance(v, bool)
        }
    return snapshot, ""


def baseline_payload(current: dict[str, dict[str, int]], *, method: str, recorded_on: str) -> dict[str, object]:
    """기준 파일의 내용 — **무엇을 보고 승인했는지**(method·날짜)를 수치와 함께 남긴다."""

    return {
        "command": ["python", "scripts/evidence_gate.py", "--record-baseline", "--method", method],
        "recorded_on": recorded_on,
        "method": method,
        "layers": {layer: dict(sorted(numbers.items())) for layer, numbers in sorted(current.items())},
    }


def load_canary_harnesses() -> tuple[str, ...]:
    """카나리아가 아는 harness 이름 — **게이트가 그 이름을 전부 돌리는지** 자기시험이 대조한다."""

    spec = importlib.util.spec_from_file_location("gate_canary_roster", SCRIPTS_DIR / "harness_canary.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("harness_canary.py 를 불러오지 못했다")
    module: ModuleType = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return tuple(str(name) for name in module.HARNESSES)


def self_probe(stages: tuple[Stage, ...] | None = None) -> Probe:
    """판정 규칙을 합성 결과로 다시 물어본다 — **측정은 하지 않는다**(리뷰가 돌릴 수 있어야 한다)."""

    stages = STAGES if stages is None else stages
    cases = Cases()

    def outcome_of(kind: str) -> Outcome:
        return Outcome(stages[0], kind, 0 if kind == KIND_PASS else 1, 0.0, "")

    # ① 종류 구분 — `pass` 만 통과다.
    cases.check("pass 는 통과다", outcome_of(KIND_PASS).ok)
    cases.check("fail 은 통과가 아니다", not outcome_of(KIND_FAIL).ok)
    cases.check("unrun(못 돌림)은 통과가 아니다", not outcome_of(KIND_UNRUN).ok)
    cases.check("outside_tier 는 통과가 아니다", not outcome_of(KIND_OUTSIDE).ok)
    cases.covers("결과 종류", KINDS, KINDS)

    # ② tier 필터 — `full` 은 `fast` 를 포함하고, `fast` 는 회귀 원장을 보지 않는다.
    fast = stages_for(TIER_FAST)
    full = stages_for(TIER_FULL)
    cases.check("fast tier 가 비어 있지 않다", len(fast) > 0)
    cases.equal("full tier 는 전체 stage 를 돈다", len(full), len(stages))
    cases.check("fast tier 는 full 전용 stage 를 돌지 않는다", all(stage.tier == TIER_FAST for stage in fast))
    cases.check(
        "fast 실행은 로컬 전용 stage 를 '보지 않은 층' 으로 적는다",
        any(stage.name == "regression_ledger" for stage in tier_outsiders(TIER_FAST)),
    )
    cases.check("full 영역에서는 보지 않은 층이 없다", tier_outsiders(TIER_FULL) == ())

    # ③ stage roster 고정 — 이름을 지우면 여기서 걸린다(상수 순회로는 지워진 이름이 안 보인다).
    cases.covers("stage", REQUIRED_STAGES, [stage.name for stage in stages])
    cases.equal("stage 이름에 중복이 없다", len({stage.name for stage in stages}), len(stages))
    cases.check("모든 stage 가 아는 tier 를 쓴다", all(stage.tier in TIERS for stage in stages))
    cases.check("모든 stage 에 스크립트가 있다", all((SCRIPTS_DIR / stage.script).exists() for stage in stages))

    # ④ 카나리아 ↔ 게이트 roster 정합 — 새 harness 를 카나리아에만 넣으면 여기서 걸린다.
    #    `SELF_EXEMPT`(게이트 자신)만 stage 에서 빠질 수 있고, 그 목록이 넓어져도 여기서 걸린다.
    stage_names = {stage.name for stage in stages}
    try:
        canary_names = load_canary_harnesses()
        cases.covers(
            "카나리아 harness", [name for name in canary_names if name not in SELF_EXEMPT], sorted(stage_names)
        )
        unaccounted = sorted(set(canary_names) - stage_names - set(SELF_EXEMPT))
        cases.equal("stage 가 아닌 harness 는 게이트 자신뿐이다", unaccounted, [])
    except Exception as exc:  # noqa: BLE001 - 정합을 못 물어봤으면 그 사실이 실패다(사고를 통과로 세지 않는다)
        cases.check(f"카나리아 harness 목록을 읽지 못했다: {type(exc).__name__}", False)

    # ⑤ 판정 문장 — 못 돌린 층이 통과로 읽히지 않고, 실패한 층 이름이 문장에 남는다.
    unrun = Outcome(stages[0], KIND_UNRUN, None, 0.1, "스크립트가 없다")
    failed = Outcome(stages[1], KIND_FAIL, 1, 0.2, "[FAIL] 판독 규칙이 깨졌다")
    report = describe(TIER_FAST, (unrun, failed), outsider_outcomes(TIER_FAST))
    cases.check("실패한 stage 이름이 보고서에 남는다", stages[1].name in report)
    cases.check("못 돌린 stage 이름이 보고서에 남는다", stages[0].name in report)
    cases.check("'못 돌림' 이 통과처럼 적히지 않는다", "못 돌림 1" in report)
    gate_problems = problems((unrun, failed), [])
    cases.equal("못 돌림·실패가 각각 문제로 잡힌다", len(gate_problems), 2)
    cases.check("못 돌림은 판정 문장에서 실패로 말한다", any("돌리지 못했다" in p for p in gate_problems))

    # ⑥ 하한 — 값·관측·근거가 함께 있어야 한다.
    floors = coverage_floors(stages)
    cases.check("하한이 있다", len(floors) > 0)
    cases.check("하한에 근거가 기록돼 있다", all(floor.why.strip() for floor in floors))
    cases.check("하한이 지금 stage 수를 넘지 않는다", not floor_problems(floors))
    cases.check("눈멀게 한 하한(관측 0)은 문다", bool(floor_problems([Floor("stage", 0, _MIN_STAGES, why="근거")])))

    # ⑦ 수치 읽기 — dict·list·int 를 펴고, 불리언과 모르는 키는 세지 않는다.
    payload = {
        "counts": {"a": 3, "flag": True},
        "coverage": {"b": [1, 2], "c": 5},
        "measured": {"d": 7},
        "ignored": {"e": 9},
    }
    cases.equal(
        "수치 추출이 지정한 키만 편다",
        numeric_snapshot(payload, ("counts", "coverage", "measured")),
        {"counts.a": 3, "coverage.b": 2, "coverage.c": 5, "measured.d": 7},
    )
    cases.equal("지목하지 않은 키는 세지 않는다", numeric_snapshot(payload, ("ignored",)), {"ignored.e": 9})
    cases.equal("수가 없으면 빈 dict 이다", numeric_snapshot("nope", ("counts",)), {})
    cases.check(
        "수치를 읽지 못하면 그 층은 문제로 적힌다",
        bool(problems((Outcome(stages[0], KIND_PASS, 0, 0.1, "", (), "JSON 이 아니다"),), [])),
    )

    # ⑧ 움직임 — 감소·증가·새 수·사라진 수·기준 없음을 구분한다(빈 값을 “그대로” 로 쓰지 않는다).
    cases.covers("움직임 종류", MOVEMENTS, MOVEMENTS)
    sample = movements({"a": {"x": 2, "y": 1}, "b": {"z": 5}}, {"a": {"x": 3}, "gone": {"q": 1}})
    kinds = {(move.layer, move.key): move.kind for move in sample}
    cases.equal("줄어든 수를 알아본다", kinds[("a", "x")], MOVED_DOWN)
    cases.equal("기준에 없던 수를 알아본다", kinds[("a", "y")], MOVED_NEW)
    cases.equal("기준에 있던 층이 수치를 안 내면 알아본다", kinds[("gone", "")], MOVED_GONE)
    cases.equal("처음 보는 층에 '그대로' 라고 말하지 않는다", kinds[("b", "")], MOVED_NONE)
    cases.equal("기준이 없으면 층마다 '기준 없음' 을 낸다", [m.kind for m in movements({"a": {}}, None)], [MOVED_NONE])
    sample_trend = trend_lines(sample, {"path": "b.json", "recorded_on": "2026-01-01"})
    cases.check("추이 줄에 줄어든 수가 먼저 나온다", sample_trend[1].find("▼") >= 0)
    steady = movements({"a": {"x": 3}}, {"a": {"x": 3}})
    cases.equal("움직이지 않은 수를 '그대로' 로 센다", [move.kind for move in steady], [MOVED_SAME])
    cases.equal("그대로인 수는 기본 추이에서 접힌다(헤더+요약만)", len(trend_lines(steady, {})), 2)
    cases.equal("`--trend-all` 이면 그대로인 수도 줄로 나온다", len(trend_lines(steady, {}, show_all=True)), 3)

    # ⑨ 기준 파일 — 깨진 기준은 "비교 불가" 로 삼기지 않는다.
    cases.equal("없는 기준 파일은 '기준 없음' 이다", read_baseline(REPO_ROOT / ".no-such-baseline.json"), ({}, ""))

    return cases.probe()


def _probe_or_failure() -> Probe:
    """자기시험이 예외로 죽으면 그 사실을 **실패**로 바꾼다(사고는 판정이 아니다)."""

    try:
        return self_probe()
    except Exception as exc:  # noqa: BLE001 - 자기시험이 죽는 것도 판정 대상이다
        return Probe(cases=1, failures=(f"자기시험이 예외로 죽었다: {type(exc).__name__}: {exc}",))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="여섯 층을 한 번에 돌리는 증거 게이트")
    parser.add_argument("--tier", choices=TIERS, default=TIER_FAST, help="도는 범위(기본: fast)")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="stage 별 제한 시간(초)")
    parser.add_argument("--json", type=Path, default=None, help="결과 JSON artifact 경로")
    parser.add_argument("--quiet", action="store_true", help="표를 출력하지 않는다")
    parser.add_argument("--baseline", type=Path, default=None, help="비교할 기준 파일(기본: 저장소의 기준)")
    parser.add_argument("--no-baseline", action="store_true", help="기준과 비교하지 않는다(추이 없음)")
    parser.add_argument("--trend-all", action="store_true", help="그대로인 수까지 전부 보여준다(기본은 움직인 수만)")
    parser.add_argument(
        "--record-baseline",
        action="store_true",
        help="이번 실행의 수치를 새 기준으로 기록한다(--method 필수, 사람이 내용을 본 뒤에만)",
    )
    parser.add_argument("--method", default="", help="--record-baseline 과 함께: 무엇을 보고 승인했는가")
    parser.add_argument("--list", action="store_true", help="stage 목록만 보고 끝낸다(아무것도 돌리지 않는다)")
    parser.add_argument("--self-test", action="store_true", help="자기시험만 돌리고 끝낸다(아무것도 돌리지 않는다)")
    args = parser.parse_args(argv)

    if args.list:
        for stage in STAGES:
            print(f"{stage.tier:5s} {stage.name:26s} scripts/{stage.script} {' '.join(stage.args)}")
        print(f"stage {len(STAGES)}개 · fast {len(stages_for(TIER_FAST))}개 · 하한 {_MIN_STAGES}개")
        return EXIT_OK

    probe = _probe_or_failure()
    if args.self_test:
        print(f"[self-probe] evidence_gate {probe.cases}건 재판정 — {'통과' if probe.ok else '실패'}")
        for failure in probe.failures:
            print(f"[FAIL] {failure}", file=sys.stderr)
        return EXIT_OK if probe.ok else EXIT_GATE

    floors = coverage_floors()
    outcomes = run(args.tier, timeout=args.timeout)
    outsiders = outsider_outcomes(args.tier)
    current = snapshot(outcomes)

    baseline_path = None if args.no_baseline else (args.baseline or BASELINE)
    baseline, baseline_problem = read_baseline(baseline_path) if baseline_path is not None else ({}, "")
    baseline_info: dict[str, object] = {
        "path": ""
        if baseline_path is None
        else str(baseline_path.relative_to(REPO_ROOT))
        if baseline_path.is_relative_to(REPO_ROOT)
        else str(baseline_path),
        "read": bool(baseline),
        "recorded_on": "",
        "method": "",
    }
    if baseline_path is not None and baseline_path.exists():
        try:
            stored = json.loads(baseline_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            stored = {}
        if isinstance(stored, dict):
            baseline_info["recorded_on"] = str(stored.get("recorded_on", ""))
            baseline_info["method"] = str(stored.get("method", ""))
    moves = movements(current, baseline if baseline else None) if baseline_path is not None else []

    if not args.quiet:
        print(describe(args.tier, outcomes, outsiders, moves=moves, baseline=baseline_info, trend_all=args.trend_all))

    if args.record_baseline:
        if not args.method.strip():
            print(
                "[FAIL] --record-baseline 에는 --method 가 필요하다 — 무엇을 보고 승인했는지 없이는 기준이 아니다",
                file=sys.stderr,
            )
            return EXIT_GATE
        if not current:
            print("[FAIL] 기록할 수치가 없다 — 돌아가지 않은 실행을 기준으로 삼지 않는다", file=sys.stderr)
            return EXIT_GATE
        target = args.baseline or BASELINE
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                baseline_payload(current, method=args.method.strip(), recorded_on=date.today().isoformat()),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"기준을 기록했다: {target} ({len(current)}개 층, method: {args.method.strip()})")
        return EXIT_OK

    found = problems(outcomes, floors) + probe_problems(probe, name="evidence_gate")
    if baseline_problem:
        found.append(f"기준 파일을 읽지 못했다: {baseline_problem} — 비교 불가를 '문제 없음' 으로 쓰지 않는다")
    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        payload = as_mapping(
            args.tier,
            outcomes,
            outsiders=outsiders,
            probe=probe,
            floors=floors,
            moves=moves,
            baseline=baseline_info,
        )
        payload["problems"] = found
        payload["ok"] = not found
        args.json.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if not args.quiet:
            print(f"wrote {args.json}")

    for problem in found:
        print(f"[FAIL] {problem}", file=sys.stderr)
    return EXIT_OK if not found else EXIT_GATE


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
