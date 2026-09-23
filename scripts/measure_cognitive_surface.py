#!/usr/bin/env python
"""P11 진입 실측 — 어떤 사용자 표면이 legacy loop와 신규 core에 도달하는가.

정적 import 그래프 기준이며 실행 trace가 아니다. 결과는 JSON artifact로 남겨 P11 통합 전후를 비교한다.

```sh
.venv/bin/python scripts/measure_cognitive_surface.py --output /tmp/surface-before.json
.venv/bin/python scripts/measure_cognitive_surface.py            # 표만 출력
```
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Final

from antigravity_k.engine.cognitive_surface import (
    DEFAULT_SURFACE_ENTRYPOINTS,
    measure_surface_reach,
)

# 공통 harness 계약(자기시험 · 탐지력 하한) — scripts/ 는 저장소 안의 도구 모음이라 직접 import 한다.
_SCRIPTS_DIR: Final[Path] = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from harness_contract import Cases, Floor, Probe, describe_self_test, floor_problems, probe_problems  # noqa: E402

EXIT_OK: Final[int] = 0
EXIT_FAIL: Final[int] = 1
# 탐지력 하한 — 표면 표가 비면 “legacy 도달 0/0” 이 아니라 “볼 수 없음” 이다.
_MIN_ENTRYPOINTS: Final[int] = 1
_MIN_PRESENT: Final[int] = 1
# 자기시험이 요구하는 성질 — 표면 하나는 실제로 core 에 도달해야 한다(그래야 판독기가 살아 있다).
_PROBE_CORE_MODULE: Final[str] = "antigravity_k.api.routes.cognitive_surface_api"
_PROBE_MISSING_MODULE: Final[str] = "antigravity_k.definitely_not_here_7c1f"


def source_head() -> str:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def self_probe() -> Probe:
    """매 실행 자기시험 — 도달 판독(실재 모듈·없는 모듈)과 entrypoint 표를 다시 물어본다."""

    cases = Cases()
    probes = (
        ("probe-core", _PROBE_CORE_MODULE),
        ("probe-missing", _PROBE_MISSING_MODULE),
    )
    try:
        measurement = measure_surface_reach(entrypoints=probes)
    except Exception as exc:  # 자기시험은 판독기 예외도 실패로 보고한다(예외로 죽지 않는다)
        cases.check(f"도달 판독이 예외를 냈다: {exc}", False)
        return cases.probe()

    by_label = {item.label: item for item in measurement.entrypoints}
    core_item = by_label.get("probe-core")
    missing_item = by_label.get("probe-missing")
    cases.equal("entrypoint 수만큼 판독한다", len(measurement.entrypoints), 2)
    cases.check("실재 모듈을 알아본다", core_item is not None and core_item.exists)
    cases.check("신규 core 도달을 본다", core_item is not None and core_item.reaches_core)
    cases.check("없는 모듈은 exists=False", missing_item is not None and not missing_item.exists)
    cases.check("없는 모듈은 도달 없음", missing_item is not None and not missing_item.reaches_core)
    cases.check("기본 entrypoint 표가 살아 있다", len(DEFAULT_SURFACE_ENTRYPOINTS) >= _MIN_ENTRYPOINTS)
    return cases.probe()


def coverage_floors(measurement: object) -> list[Floor]:
    """이번 실측이 실제로 무엇을 봤는지 — 표가 비면 “도달 0” 이 아니라 “못 봄” 이다."""

    entrypoints = tuple(getattr(measurement, "entrypoints", ()))
    present = sum(1 for item in entrypoints if getattr(item, "exists", False))
    return [
        Floor("entrypoint", len(entrypoints), _MIN_ENTRYPOINTS),
        Floor("실재하는 entrypoint", present, _MIN_PRESENT),
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="measure_cognitive_surface",
        description="SSAK-AI cognitive surface reach measurement (static import graph)",
    )
    parser.add_argument("--output", type=Path, default=None, help="결과 JSON artifact 경로")
    parser.add_argument("--source-root", type=Path, default=None, help="패키지 source root(기본: 저장소 src)")
    parser.add_argument("--self-test", action="store_true", help="자기시험만 돌리고 끝낸다(실측 artifact 없음)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    probe = self_probe()
    if args.self_test:
        print(describe_self_test("measure_cognitive_surface", probe))
        return EXIT_OK if probe.ok else EXIT_FAIL

    measurement = measure_surface_reach(source_root=args.source_root)
    payload = {
        **measurement.as_mapping(),
        "source_head": source_head(),
        "probe": probe.as_mapping(),
        "coverage": {
            "entrypoints": len(measurement.entrypoints),
            "present": sum(1 for item in measurement.entrypoints if item.exists),
            "min_entrypoints": _MIN_ENTRYPOINTS,
        },
    }
    header = f"{'surface':28s} {'legacy':6s} {'core':5s}  reached via (legacy)"
    print(header)
    print("-" * len(header))
    for item in measurement.entrypoints:
        via = " → ".join(item.legacy_via[1:]) if item.legacy_via else "-"
        exists = "" if item.exists else " (모듈 없음)"
        print(f"{item.label:28s} {str(item.reaches_legacy):6s} {str(item.reaches_core):5s}  {via}{exists}")
    print()
    print(f"legacy 도달 {measurement.legacy_count}/{len(measurement.entrypoints)} · core 도달 {measurement.core_count}")
    print(f"legacy={measurement.legacy_module} · core={measurement.core_module}")
    print(describe_self_test("measure_cognitive_surface", probe))
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"wrote {args.output}")

    problems = probe_problems(probe, name="measure_cognitive_surface") + floor_problems(coverage_floors(measurement))
    for problem in problems:
        print(f"[FAIL] {problem}", file=sys.stderr)
    return EXIT_FAIL if problems else EXIT_OK


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
