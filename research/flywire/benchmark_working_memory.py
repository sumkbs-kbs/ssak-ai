#!/usr/bin/env python3
"""task 26 (B04) — 목표 중심 작업 기억 대조 실험.

    uv run research/flywire/benchmark_working_memory.py --seeds 3 \
        --output .omo/evidence/ssak-ai-web-integration/<run>/task-26/working-memory.json

## 이 스크립트가 답하는 질문

**둘을 따로 잰다** — 하나로 뭉개면 "점수가 좋아서"와 "상한을 두어서"가 구분되지 않는다.

  1. `bounded_selection` : 목표 기반 선택(+보고/외부화) vs **현재 동작**(최근 창을 그대로 밀어 넣기)
  2. `goal_scoring`     : 같은 상한에서 목표 기반 **점수**가 단순 핀 baseline 보다 나은가

2번이 기각되어도 완료다 — 그때 채택되는 것은 점수가 아니라 **상한과 불변식**이다.

## 불변식 (하나라도 깨지면 exit 4 — 품질 이득이 이를 상쇄하지 않는다)

  1. 제약(사용자 목표·승인 범위·금지)은 삭제 불가.  2. 세션 경계 침범 0.
  3. 초과는 보고하거나 외부화(조용한 폐기 0).  4. 악성 페이지 지시문은 그대로 나르지 않는다.

`--inject` 는 이 문들을 **실제로 열어** 검출되는지 확인한다. 주입이 검출되지 않으면 그 자체가 실패다.

## 종료코드

`memory_contract.EXIT_MEANINGS` — 0 채택 가능한 결론 있음 · 3 fixture 거절 · 4 불변식 위반/미검출 ·
5 산출물 실패 · 10 기각/불충분(정상 완료).
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import memory_contract as contract  # noqa: E402  # pyright: ignore[reportImplicitRelativeImport]
import memory_selector as selector  # noqa: E402  # pyright: ignore[reportImplicitRelativeImport]

DEFAULT_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "flywire" / "memory" / "scenarios.json"

# 승격 판정을 받는 후보(베이스라인은 판정 대상이 아니다).
CANDIDATE = "selector"
# 비교쌍 — (이름, 후보, 베이스라인, 무엇을 판정하는가)
COMPARISONS: tuple[tuple[str, str, str, str], ...] = (
    (
        "bounded_selection",
        "selector",
        "fifo_window",
        "상한을 두고 고르는 것이 최근 창을 그대로 넣는 현재 동작보다 나은가",
    ),
    (
        "goal_scoring",
        "selector",
        "pinned",
        "같은 상한에서 목표 관련성 점수가 단순 핀보다 나은가",
    ),
    (
        # 방향에 주의: "요약이 후보"다. 요약이 토큰을 적게 쓰는 것은 사실이므로, 요약을 후보로 두고
        # **성공 하락** 축에서 떨어지는지 본다(방향을 뒤집으면 "토큰을 더 쓴다"는 엉뚱한 사유가 나온다).
        "summary_quality",
        "summary",
        "selector",
        "같은 상한에서 요약 압축(출처 상실)이 필수 증거를 지키는가",
    ),
)

INJECTIONS: dict[str, dict[str, bool]] = {
    "constraint-drop": {"enforce_constraints": False},
    "session-leak": {"enforce_scope": False},
    "silent-drop": {"report_overflow": False},
    "malicious-verbatim": {"quarantine_malicious": False},
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    _ = parser.add_argument("--seeds", type=int, default=3, help="최소 3 (계획 요구)")
    _ = parser.add_argument("--output", type=Path, default=Path("task-26-working-memory.json"))
    _ = parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    _ = parser.add_argument("--inject", choices=tuple(INJECTIONS), default=None)
    _ = parser.add_argument("--smoke", action="store_true", help="seed 1~2 허용 — 판정 대신 NOT_RUN")
    _ = parser.add_argument("--print-json", action="store_true")
    _ = parser.add_argument("--quiet", action="store_true")
    return parser


def run_condition(
    condition: str,
    *,
    cases: Sequence[contract.WMCase],
    injections: Mapping[str, bool],
) -> tuple[dict[str, Any], list[dict[str, object]]]:
    per_case: list[dict[str, object]] = []
    flags = dict(injections)
    for case in cases:
        selection = selector.select(
            condition,
            case,
            report_overflow=flags.get("report_overflow"),
            enforce_scope=flags.get("enforce_scope", True),
            enforce_constraints=flags.get("enforce_constraints", True),
            quarantine_malicious=flags.get("quarantine_malicious", True),
        )
        per_case.append(selector.evaluate_selection(case, selection))
    return selector.aggregate(condition, per_case), per_case


def injection_outcome(injection: str | None, violations: Sequence[str]) -> tuple[int, str]:
    """주입 하나의 결말 — 판단을 함수 하나에 모아 시험이 직접 잴 수 있게 한다.

    주입이 **검출되지 않으면 그 자체가 실패**다: 검사가 그 문을 보고 있지 않다는 뜻이고,
    그 사실을 "통과"로 넘기면 주입은 장식이 된다.
    """
    if injection is None:
        return contract.EXIT_OK, ""
    if not violations:
        return contract.EXIT_SAFETY_VIOLATION, f"주입 {injection} 이 검출되지 않았다 — 그 자체가 실패다"
    return contract.EXIT_SAFETY_VIOLATION, ""


def invariant_violations(condition: str, aggregate: Mapping[str, Any]) -> list[str]:
    violations: list[str] = []
    if int(aggregate.get("constraint_omissions", 0)) != 0:
        violations.append(f"{condition}:constraint_omissions={aggregate['constraint_omissions']}")
    if int(aggregate.get("cross_session_leaks", 0)) != 0:
        violations.append(f"{condition}:cross_session_leaks={aggregate['cross_session_leaks']}")
    if int(aggregate.get("silent_drops", 0)) != 0:
        violations.append(f"{condition}:silent_drops={aggregate['silent_drops']}")
    if int(aggregate.get("malicious_verbatim", 0)) != 0:
        violations.append(f"{condition}:malicious_verbatim={aggregate['malicious_verbatim']}")
    return violations


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.seeds < 3 and not args.smoke:
        print("--seeds 는 최소 3 이다(계획 요구).", file=sys.stderr)
        return contract.EXIT_USAGE
    try:
        cases = selector.load_cases(args.fixture)
    except FileNotFoundError as missing:
        print(f"입력 부재: {missing}", file=sys.stderr)
        return contract.EXIT_INPUT_MISSING
    except selector.SelectorFixtureError as broken:
        print(f"fixture 거절: {broken}", file=sys.stderr)
        return contract.EXIT_FIXTURE_REJECTED

    injections: dict[str, bool] = dict(INJECTIONS.get(args.inject or "", {}))
    aggregates: dict[str, dict[str, Any]] = {}
    details: dict[str, list[dict[str, object]]] = {}
    for condition in selector.CONDITIONS:
        aggregate, per_case = run_condition(condition, cases=cases, injections=injections)
        aggregates[condition] = aggregate
        details[condition] = per_case

    candidate_violations = invariant_violations(CANDIDATE, aggregates[CANDIDATE])
    baseline_violations = {
        condition: invariant_violations(condition, aggregates[condition])
        for condition in selector.CONDITIONS
        if condition != CANDIDATE
    }
    outcome, reason = injection_outcome(args.inject, candidate_violations)
    if outcome != contract.EXIT_OK and not candidate_violations:
        _write(
            args.output,
            {
                "task": "task-26",
                "experiment": "working_memory",
                "inject": args.inject,
                "decision": str(contract.Decision.NOT_RUN),
                "injection_not_detected": True,
                "aggregates": aggregates,
            },
        )
        print(f"{reason}(검사가 그 문을 보고 있지 않다).", file=sys.stderr)
        return outcome
    if candidate_violations:
        _write(
            args.output,
            {
                "task": "task-26",
                "experiment": "working_memory",
                "inject": args.inject,
                "decision": str(contract.Decision.REJECTED),
                "invariant_violations": candidate_violations,
                "aggregates": aggregates,
            },
        )
        print("불변식 위반 — 실행 실패:\n  " + "\n  ".join(candidate_violations), file=sys.stderr)
        return contract.EXIT_SAFETY_VIOLATION

    verdicts: list[dict[str, Any]] = []
    for name, candidate, baseline, question in COMPARISONS:
        verdict = contract.decide_working_memory(
            condition=candidate,
            baseline_success=float(aggregates[baseline]["success_rate"]),
            condition_success=float(aggregates[candidate]["success_rate"]),
            baseline_tokens=float(aggregates[baseline]["mean_tokens"]),
            condition_tokens=float(aggregates[candidate]["mean_tokens"]),
            constraint_omissions=int(aggregates[candidate]["constraint_omissions"]),
            cross_session_leaks=int(aggregates[candidate]["cross_session_leaks"]),
            silent_drops=int(aggregates[candidate]["silent_drops"]),
        )
        verdicts.append(
            {
                "name": name,
                "question": question,
                "candidate": candidate,
                "baseline": baseline,
                "decision": str(verdict.decision),
                "reasons": list(verdict.reasons),
                "token_reduction": verdict.token_reduction,
                "success": verdict.success,
                "baseline_success": verdict.baseline_success,
                "constraint_omissions": verdict.constraint_omissions,
                "cross_session_leaks": verdict.cross_session_leaks,
                "silent_drops": verdict.silent_drops,
            }
        )

    accepted = [verdict for verdict in verdicts if verdict["decision"] == str(contract.Decision.ACCEPTED)]
    rejected_names = [verdict["name"] for verdict in verdicts if verdict["decision"] != str(contract.Decision.ACCEPTED)]
    if args.smoke:
        decision = contract.Decision.NOT_RUN
    elif accepted:
        decision = contract.Decision.ACCEPTED
    else:
        decision = contract.Decision.REJECTED

    report = {
        "task": "task-26",
        "experiment": "working_memory",
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "inject": args.inject,
        "smoke": bool(args.smoke),
        "decision": str(decision),
        "adopted": [verdict["name"] for verdict in accepted],
        "rejected": rejected_names,
        "manifest": {
            "task": "task-26/B04",
            "fixture": {
                "path": str(args.fixture),
                "sha256": contract.sha256_file(args.fixture),
                "cases": len(cases),
                "kinds": sorted({case.kind for case in cases}),
            },
            "weights_version": selector.WEIGHTS_VERSION,
            "weights": dict(selector.SELECTOR_WEIGHTS),
            "summary_ratio": selector.SUMMARY_RATIO,
            "tokenizer": "char/4",
            "code": {
                "path": str(Path(__file__).resolve()),
                "sha256": contract.sha256_file(Path(__file__).resolve()),
            },
            "budget": {"seeds": args.seeds},
            "machine": {"platform": platform.platform(), "python": platform.python_version()},
        },
        "aggregates": {
            condition: {key: value for key, value in aggregate.items() if key != "cases"}
            for condition, aggregate in aggregates.items()
        },
        "cases": {condition: details[condition] for condition in selector.CONDITIONS},
        "baseline_violations": baseline_violations,
        "verdicts": verdicts,
        "limitations": (["스모크 실행 — 판정하지 않는다."] if args.smoke else [])
        + [
            '"성공"은 **결정적 커버리지 프록시**다(필수 증거 보존 + 출처 보존 + 악성 미승격). '
            "모델이 낸 실제 task success 는 재지 않았다(model_success=NOT_RUN).",
            "fixture 는 8개 합성 시나리오이며 상한은 필수+잡음 25% 로 구성된다 — 토큰 감소는 구조적이다.",
            "fifo_window 는 상한 없이 돈다(현재 동작 재현). 그래서 토큰 비교는 '압축하지 않음 vs 압축함'이다.",
            "세션 격리는 fixture 안에서만 잰다(실제 동시 세션 프로세스는 범위 밖).",
        ],
        "reproduction_command": f"uv run research/flywire/benchmark_working_memory.py --seeds {args.seeds} --output {args.output}",
    }
    _write(args.output, report)
    if not args.quiet:
        _print_summary(report)
    if args.print_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return contract.EXIT_OK if decision is contract.Decision.ACCEPTED else contract.EXIT_REJECTED_EXPERIMENT


def _write(path: Path, payload: Mapping[str, object]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as error:
        print(f"산출물 쓰기 실패: {error}", file=sys.stderr)


def _print_summary(report: Mapping[str, Any]) -> None:
    print(f"task-26/B04 작업 기억 — 결정 {report['decision']} · 채택 {report['adopted'] or '없음'}")
    for condition, aggregate in report["aggregates"].items():
        print(
            f"  {condition:<12} success {aggregate['success_rate']:.3f} tokens {aggregate['mean_tokens']:.1f} "
            f"constraint {aggregate['constraint_omissions']} cross {aggregate['cross_session_leaks']} "
            f"silent {aggregate['silent_drops']} verbatim {aggregate['malicious_verbatim']} "
            f"overflow {aggregate['overflow_reported']}"
        )
    print("  ── 판정 ──")
    for verdict in report["verdicts"]:
        print(f"  {verdict['name']} ({verdict['candidate']} vs {verdict['baseline']}): {verdict['decision']}")
        for reason in verdict["reasons"]:
            print(f"    · {reason}")


if __name__ == "__main__":
    raise SystemExit(main())
