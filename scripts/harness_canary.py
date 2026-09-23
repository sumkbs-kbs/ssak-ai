#!/usr/bin/env python
"""하한 카나리아 — **탐지력 하한이 실제로 무는가**를 저장소에서 지금 확인한다.

하한을 기록하고 검사하는 장치가 다 갖춰져도, 마지막 구멍이 하나 남는다: **하한이 장식일 수 있다.**
`minimum=0` 이거나 비교가 뒤집혀 있으면 “기록도 있고 자기시험도 통과” 하는데 아무것도 막지 못한다.
그래서 각 harness 의 하한을 **일부러 0으로 눈멀게 만든 사본**으로 평가해, 실제로 실패 문장이 나오는지 본다.

세 가지를 본다:

  1. **정상**: 실제 측정에서 만든 하한은 문제를 내지 않는다(하한이 멀쩡한 측정을 막으면 그것도 고장이다).
  2. **눈멀게 한 사본**: `observed=0` 으로 바꾼 하한은 **문제를 내야 한다** — 내지 않으면 그 하한은 장식이다.
  3. **하한의 근거**: 실패 문장에 기록된 근거(`why`)가 함께 실린다(값만 옮겨 적지 않는다).

**종료 코드도 판정이다.** 눈멀게 한 하한이 하나라도 있으면 `--emit-json` 도 exit 1 이다 — JSON 을 낸다고
성공을 알리면, 그 출력을 읽는 쪽(리뷰·CI)은 “돌았는데 통과했다” 와 “돌았지만 아무것도 못 막았다” 를
종료 코드로 구분할 수 없다. JSON 은 stdout 에 그대로 남으므로 **진단과 판정이 함께** 나온다.

```sh
.venv/bin/python scripts/harness_canary.py            # harness 별 표
.venv/bin/python scripts/harness_canary.py --gate      # 하나라도 안 물면 exit 1
.venv/bin/python scripts/harness_canary.py --emit-json # 리뷰 검사가 읽는다(문제가 있으면 exit 1 + JSON)
```
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
SCRIPTS_DIR: Final[Path] = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from harness_contract import Floor, floor_problems  # noqa: E402

EXIT_OK: Final[int] = 0
EXIT_GATE: Final[int] = 1

# 카나리아가 다루는 harness — 각자 하한을 어떻게 만드는지 여기에 적는다(계약의 단일 출처).
# `evidence_gate` 는 측정 harness 가 아니라 **여섯 층을 한 번에 도는 게이트**지만, 하한(`stage` 수)을 들고 있으므로
# 그 하한이 실제로 무는지도 여기서 본다 — 게이트 자신을 stage 로 넣으면 재귀라, 게이트를 못 보는 자리는 여기다.
HARNESSES: Final[tuple[str, ...]] = (
    "digest_drift",
    "regression_ledger",
    "audit_state_claims",
    "audit_enum_identity",
    "audit_test_namespace_purge",
    "measure_cognitive_surface",
    "evidence_gate",
    "red_rehearsal",
    "release_artifacts",
)


@dataclass(frozen=True, slots=True)
class CanaryResult:
    """한 harness 의 카나리아 관찰 — 정상 여부·눈멀게 한 사본이 무는지·근거가 실리는지."""

    name: str
    floors: int
    healthy: bool
    bites: bool
    carries_reason: bool
    problems: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return self.floors > 0 and self.healthy and self.bites and self.carries_reason

    def as_mapping(self) -> dict[str, object]:
        return {
            "name": self.name,
            "floors": self.floors,
            "healthy": self.healthy,
            "bites": self.bites,
            "carries_reason": self.carries_reason,
            "ok": self.ok,
            "problems": list(self.problems),
        }


def load_harness(name: str) -> ModuleType:
    """harness 스크립트를 파일 경로로 불러온다(설치된 package 가 아니라 저장소 도구다)."""

    spec = importlib.util.spec_from_file_location(f"canary_{name}", SCRIPTS_DIR / f"{name}.py")
    if spec is None or spec.loader is None:
        raise SystemExit(f"harness 를 불러오지 못했다: {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# 기록 artifact 가 있는 harness — 관측값의 출처가 저장본이다(리뷰가 읽는 것과 같은 자리).
ARTIFACT_FLOORS: Final[dict[str, str]] = {
    "digest_drift": "docs/ssak-ai-core/evidence/digest_drift.json",
    "regression_ledger": "docs/ssak-ai-core/evidence/regression_ledger.json",
    "audit_state_claims": "docs/ssak-ai-core/evidence/state_claims.json",
    # 배포 산출물 계약의 하한을 재려면 61초짜리 빌드가 필요하다 — fast tier 의 카나리아는 그 빌드를 감당할 수 없으므로
    # **마지막으로 승인된 기록**(`release_artifacts.py --record --method`)의 관측으로 본다. 그 기록이 없거나 낡았으면
    # 카나리아는 통과가 아니라 “하한이 없다” 고 말하며, 기록이 지금 판단과 같은지도 그 층이 게이트에서 스스로 대조한다.
    "release_artifacts": "docs/ssak-ai-core/evidence/release_artifacts.json",
}


def artifact_floors(name: str) -> list[Floor] | None:
    """저장본이 기록한 하한 — 없거나 읽히지 않으면 None(호출자가 실패로 처리).

    `regression_ledger` 처럼 회차 산출물(junit)이 있어야 관측값이 나오는 harness 는 **저장본이 기준**이다:
    카나리아가 빈 원장으로 기준을 만들면 “정상 측정을 막는다” 는 오탐이 난다(실제로 처음에 그랬다).
    """

    target = REPO_ROOT / ARTIFACT_FLOORS[name]
    if not target.exists():
        return None
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    records = payload.get("floors")
    if not isinstance(records, list) or not records:
        return None
    return [
        Floor(
            str(record.get("label")),
            int(record.get("observed", 0)),
            int(record.get("minimum", 0)),
            why=str(record.get("why", "")),
        )
        for record in records
        if isinstance(record, dict)
    ]


def harness_floors(name: str, module: ModuleType) -> list[Floor]:
    """그 harness 의 하한 — 기록이 있으면 저장본, 없으면 **저장소를 직접 재서** 관측값을 얻는다."""

    if name in ARTIFACT_FLOORS:
        return artifact_floors(name) or []
    if name in {"audit_enum_identity", "audit_test_namespace_purge"}:
        return list(module.coverage_floors())
    if name == "measure_cognitive_surface":
        return list(module.coverage_floors(module.measure_surface_reach()))
    if name in {"evidence_gate", "red_rehearsal"}:
        # 둘 다 저장소를 재지 않고 자기 roster 를 센다(게이트는 stage 수, 리허설은 심는 층 수).
        return list(module.coverage_floors())
    raise SystemExit(f"{name} 의 하한을 만드는 방법이 카나리아에 없다")


def blind(floor: Floor) -> Floor:
    """하한을 눈멀게 한 사본 — 관측을 0으로 낮춘다(최소값이 0이면 영원히 안 물므로 이 경우도 잡힌다)."""

    return Floor(floor.label, 0, floor.minimum, why=floor.why)


def inspect(name: str, module: ModuleType) -> CanaryResult:
    """한 harness 의 하한이 장식이 아닌지 본다."""

    floors = harness_floors(name, module)
    if not floors:
        return CanaryResult(
            name=name,
            floors=0,
            healthy=False,
            bites=False,
            carries_reason=False,
            problems=(
                f"{name} 에 하한이 없다 — 하한 없는 harness 는 빈손으로 결과도 통과한다"
                + ("(기록 artifact 가 없거나 `floors` 를 담지 않았다)" if name in ARTIFACT_FLOORS else ""),
            ),
        )

    healthy = not floor_problems(floors)
    blinded = [floor_problems([blind(floor)]) for floor in floors]
    bites = all(problems for problems in blinded)
    # 근거가 하나라도 비면 `carries_reason` 은 **거짓**이다 — 빈 목록에 대한 `all()` 은 참이라서
    # 그대로 두면 “근거가 없다” 는 문제를 적어 놓고도 `ok` 가 참이 되는 모순이 생긴다(시험이 실제로 잡았다).
    without_reason = [floor.label for floor in floors if not floor.why.strip()]
    carries_reason = not without_reason and all(
        any(floor.why in problem for problem in problems) for floor, problems in zip(floors, blinded, strict=True)
    )
    problems: list[str] = []
    if not healthy:
        problems.append(f"{name} 의 하한이 정상 측정을 막는다: {floor_problems(floors)}")
    if not bites:
        problems.append(f"{name} 의 하한이 눈멀게 한 사본을 막지 못한다(장식이다): {[floor.label for floor in floors]}")
    if without_reason:
        problems.append(f"{name} 의 하한에 근거가 없다: {without_reason}")
    if not carries_reason:
        problems.append(f"{name} 의 실패 문장이 하한 근거를 함께 내지 않는다")
    return CanaryResult(
        name=name,
        floors=len(floors),
        healthy=healthy,
        bites=bites,
        carries_reason=carries_reason,
        problems=tuple(problems),
    )


def run(names: tuple[str, ...] = HARNESSES) -> tuple[CanaryResult, ...]:
    """카나리아를 돌린다 — harness 하나가 예외로 죽어도 나머지는 계속 본다(한 번에 다 보고한다)."""

    results: list[CanaryResult] = []
    for name in names:
        try:
            results.append(inspect(name, load_harness(name)))
        except SystemExit:
            raise
        except Exception as exc:  # 자체 점검 도구는 harness 의 예외도 판정으로 바꾼다
            results.append(
                CanaryResult(
                    name=name,
                    floors=0,
                    healthy=False,
                    bites=False,
                    carries_reason=False,
                    problems=(f"{name} 카나리아가 예외로 죽었다: {type(exc).__name__}: {exc}",),
                )
            )
    return tuple(results)


def as_mapping(results: tuple[CanaryResult, ...]) -> dict[str, object]:
    return {
        "command": ["python", "scripts/harness_canary.py"],
        "harnesses": [result.as_mapping() for result in results],
        "counts": {
            "harnesses": len(results),
            "ok": sum(1 for result in results if result.ok),
            "blind": sum(1 for result in results if not result.bites),
            "unjustified": sum(1 for result in results if not result.carries_reason),
        },
    }


def describe(results: tuple[CanaryResult, ...]) -> str:
    lines = [f"[canary] harness {len(results)}개 — 하한이 실제로 무는지 지금 확인했다"]
    for result in results:
        state = "OK      " if result.ok else "BLIND   "
        source = "기록" if result.name in ARTIFACT_FLOORS else "직접 측정"
        lines.append(
            f"  {state}{result.name} · 하한 {result.floors}개({source}) · 정상 통과 {result.healthy} · "
            f"눈멀게 한 사본 차단 {result.bites} · 근거 동봉 {result.carries_reason}"
        )
        for problem in result.problems:
            lines.append(f"    - {problem}")
    lines.append("* 이 시험이 없으면 하한은 기록만 남고 아무것도 막지 못해도 통과한다(minimum=0 이면 영원히 안 문다).")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="탐지력 하한이 실제로 무는지 확인한다(카나리아)")
    parser.add_argument("--gate", action="store_true", help="하나라도 안 물거나 근거가 없으면 exit 1")
    parser.add_argument("--emit-json", action="store_true", help="결과만 stdout JSON 으로 낸다(리뷰 검사가 읽는다)")
    args = parser.parse_args(argv)

    results = run()
    problems = [problem for result in results for problem in result.problems]
    if args.emit_json:
        print(json.dumps(as_mapping(results), ensure_ascii=False, indent=2))
        # JSON 을 낸 실행도 **판정을 종료 코드로** 말한다 — 진단은 stdout 에 그대로 남는다.
        return EXIT_GATE if problems else EXIT_OK
    print(describe(results))
    if not args.gate:
        return EXIT_OK
    for problem in problems:
        print(f"[FAIL] {problem}", file=sys.stderr)
    return EXIT_GATE if problems else EXIT_OK


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
