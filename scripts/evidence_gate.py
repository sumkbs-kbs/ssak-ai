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

```sh
.venv/bin/python scripts/evidence_gate.py                  # fast tier — 8초 안에 끝난다
.venv/bin/python scripts/evidence_gate.py --tier full      # 회귀 원장까지(로컬 산출물 필요)
.venv/bin/python scripts/evidence_gate.py --json .artifacts/evidence-gate.json
.venv/bin/python scripts/evidence_gate.py --self-test      # 판정 규칙만 재판정(아무것도 돌리지 않는다)
```
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import time
from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class Stage:
    """한 층을 도는 방법 — 무엇을(script) 어떻게(args) 돌려 무엇을 보는지(describes)."""

    name: str
    tier: str
    script: str
    args: tuple[str, ...]
    describes: str
    requires: tuple[str, ...] = ()


# stage roster — 단일 출처. `REQUIRED_STAGES` 와 어긋나면 자기시험이 실패한다(이름을 지워도 잡힌다).
STAGES: Final[tuple[Stage, ...]] = (
    Stage("review", TIER_FAST, "architecture_review.py", ("--quiet",), "24원칙·§63·§52 매핑과 증거의 정합"),
    Stage("canary", TIER_FAST, "harness_canary.py", ("--gate",), "탐지력 하한이 실제로 무는가"),
    Stage("digest_drift", TIER_FAST, "digest_drift.py", ("--gate",), "증거가 못 박은 digest 의 현재 일치"),
    Stage("audit_state_claims", TIER_FAST, "audit_state_claims.py", ("--gate",), "산문의 현재-상태 주장 재판정"),
    Stage("audit_enum_identity", TIER_FAST, "audit_enum_identity.py", (), "enum identity 비교 감사"),
    Stage("audit_test_namespace_purge", TIER_FAST, "audit_test_namespace_purge.py", (), "import 시점 purge 감사"),
    Stage("measure_cognitive_surface", TIER_FAST, "measure_cognitive_surface.py", (), "legacy→core 도달 표 측정"),
    Stage(
        "regression_ledger",
        TIER_FULL,
        "regression_ledger.py",
        ("--gate",),
        "전량 회귀 원장(scope 별 seed 두 회차)",
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


@dataclass(frozen=True, slots=True)
class Outcome:
    """한 stage 의 관찰 — 종류·종료 코드·소요 시간·사람이 읽을 이유."""

    stage: Stage
    kind: str
    exit_code: int | None
    seconds: float
    detail: str = ""

    @property
    def ok(self) -> bool:
        """통과는 `pass` 뿐이다 — 못 돌린 것도, 이 tier 가 보지 않은 것도 통과가 아니다."""

        return self.kind == KIND_PASS

    def as_mapping(self) -> dict[str, object]:
        return {
            "name": self.stage.name,
            "tier": self.stage.tier,
            "kind": self.kind,
            "exit_code": self.exit_code,
            "seconds": round(self.seconds, 2),
            "detail": self.detail,
            "describes": self.stage.describes,
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


def run_stage(stage: Stage, *, timeout: float = DEFAULT_TIMEOUT) -> Outcome:
    """stage 하나를 독립 process 로 돌린다 — 예외도 삼키지 않고 **판정으로** 바꾼다."""

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

    started = time.monotonic()
    try:
        result = subprocess.run(
            [sys.executable, str(script), *stage.args],
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

    seconds = time.monotonic() - started
    if result.returncode == 0:
        return Outcome(stage, KIND_PASS, 0, seconds, "")
    return Outcome(
        stage,
        KIND_FAIL,
        result.returncode,
        seconds,
        first_failure_detail(result.stdout, result.stderr),
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
    return found + floor_problems(floors)


def as_mapping(
    tier: str,
    outcomes: tuple[Outcome, ...],
    *,
    outsiders: tuple[Outcome, ...] = (),
    probe: Probe,
    floors: list[Floor] | None = None,
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
        "probe": probe.as_mapping(),
        "floors": floor_records(records),
    }


def describe(tier: str, outcomes: tuple[Outcome, ...], outsiders: tuple[Outcome, ...]) -> str:
    """사람이 30초에 읽는 건강 보고서 — 층마다 한 줄, 못 본 층은 따로 적는다."""

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
    return "\n".join(lines)


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
    if not args.quiet:
        print(describe(args.tier, outcomes, outsiders))

    found = problems(outcomes, floors) + probe_problems(probe, name="evidence_gate")
    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        payload = as_mapping(args.tier, outcomes, outsiders=outsiders, probe=probe, floors=floors)
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
