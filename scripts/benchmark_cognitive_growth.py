#!/usr/bin/env python
"""P10 성장 평가 CLI — checklist가 요구하는 ``--output/--seed/--mode/--manifest/--store-root`` 계약.

사용:

```sh
# 1) 실행 전에 spec을 등록한다(기준 사전 등록)
.venv/bin/python scripts/benchmark_cognitive_growth.py --print-spec --output spec.json

# 2) 등록된 spec으로 fresh/mature/demo를 실행한다
.venv/bin/python scripts/benchmark_cognitive_growth.py --mode fresh --manifest spec.json --store-root /tmp/growth
.venv/bin/python scripts/benchmark_cognitive_growth.py --mode demo --manifest spec.json --store-root /tmp/growth --output demo.json

# 3) mechanism 하나만 끄는 ablation
.venv/bin/python scripts/benchmark_cognitive_growth.py --mode ablation --mechanism RISK_SHAPING \
    --manifest spec.json --store-root /tmp/growth --output ablation-risk-shaping.json
```

규칙:

- live pilot는 이 CLI가 실행하지 않는다(``--mode live-pilot``은 명시적 미구현, exit 2).
- 기준(spec)을 바꾸면 digest가 달라지고, 등록 digest와 다르면 실행하지 않는다(exit 2).
- output은 JSON artifact이며, fixture 결과를 live 성능으로 주장하지 않는다.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from antigravity_k.engine.cognitive.growth import (
    BenchmarkSpec,
    GrowthBenchmarkError,
    GrowthRunner,
    Mechanism,
    RunKind,
    default_spec,
)
from antigravity_k.engine.growth_fixture_tools import fixture_tool_port

EXIT_OK: Final[int] = 0
EXIT_VERDICT_FAILED: Final[int] = 1
EXIT_USAGE: Final[int] = 2

MODES: Final[tuple[str, ...]] = ("fresh", "mature", "ablation", "demo")


def source_head() -> str:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="benchmark_cognitive_growth",
        description="SSAK-AI cognitive growth paired benchmark (deterministic fixture demo)",
    )
    parser.add_argument("--mode", choices=(*MODES, "live-pilot"), default="demo")
    parser.add_argument("--manifest", type=Path, default=None, help="사전 등록한 spec JSON")
    parser.add_argument("--output", type=Path, default=None, help="결과 JSON artifact 경로")
    parser.add_argument("--store-root", type=Path, default=None, help="격리된 실행 root(production vault 아님)")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--mechanism", choices=[item.value for item in Mechanism], default=None)
    parser.add_argument("--source-head", default=None)
    parser.add_argument("--print-spec", action="store_true", help="등록용 spec을 출력하고 종료한다")
    return parser


def dump_spec(spec: BenchmarkSpec, output: Path | None) -> None:
    payload = json.dumps({"spec_digest": spec.digest(), "spec": spec.as_mapping()}, ensure_ascii=False, indent=2)
    if output is None:
        print(payload)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(payload + "\n", encoding="utf-8")
    print(f"registered spec: {output} ({spec.digest()})")


def load_spec(path: Path | None, *, seed: int | None) -> BenchmarkSpec:
    if path is None:
        spec = default_spec(seed=seed if seed is not None else 20260922)
        if spec.run_kind is not RunKind.DETERMINISTIC_FIXTURE:  # pragma: no cover - 방어적
            raise GrowthBenchmarkError("기본 spec은 deterministic fixture다")
        return spec
    data = json.loads(path.read_text(encoding="utf-8"))
    if "spec" not in data:
        raise GrowthBenchmarkError(f"spec 형식이 아니다: {path}")
    spec = BenchmarkSpec.from_json(json.dumps(data["spec"]))
    recorded = str(data.get("spec_digest", ""))
    if recorded and recorded != spec.digest():
        raise GrowthBenchmarkError(
            "등록된 spec digest와 내용이 다르다 — 기준을 바꾸려면 새 experiment ID로 다시 등록한다"
        )
    if seed is not None and seed != spec.seed:
        raise GrowthBenchmarkError(f"--seed {seed}가 등록된 seed {spec.seed}와 다르다")
    return spec


def write_output(payload: Mapping[str, object], output: Path | None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    if output is None:
        print(text)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text + "\n", encoding="utf-8")
    print(f"wrote {output}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.mode == "live-pilot":
        # live pilot는 실제 provider port를 결선한 실행기(engine/cognitive/live_pilot.py)에서만 돈다.
        # 이 CLI는 수치를 만들지 않고 NOT_RUN artifact만 남긴다.
        payload: dict[str, object] = {
            "run_kind": "LIVE_PILOT",
            "status": "NOT_RUN",
            "reason": (
                "이 CLI는 deterministic fixture harness다 — live pilot는 실제 provider port를 결선한\n"
                "실행기에서 LivePilotHarness로 돌린다. fixture 수치를 live 결과로 쓰지 않는다."
            ),
            "mixed_with_fixture": False,
        }
        write_output(payload, args.output)
        print("live pilot는 이 CLI가 실행하지 않는다(NOT_RUN) — fixture 결과로 대체하지 않는다", file=sys.stderr)
        return EXIT_USAGE
    try:
        spec = load_spec(args.manifest, seed=args.seed)
    except (GrowthBenchmarkError, KeyError, ValueError) as exc:
        print(f"spec 오류: {exc}", file=sys.stderr)
        return EXIT_USAGE
    if args.print_spec:
        dump_spec(spec, args.output)
        return EXIT_OK
    if args.mode == "ablation" and args.mechanism is None:
        print("--mode ablation에는 --mechanism이 필요하다", file=sys.stderr)
        return EXIT_USAGE

    store_root = args.store_root
    if store_root is None:
        store_root = Path(tempfile.mkdtemp(prefix="growth-benchmark-"))
    store_root.mkdir(parents=True, exist_ok=True)
    runner = GrowthRunner(
        store_root,
        spec,
        source_head=args.source_head if args.source_head is not None else source_head(),
        executor_factory=fixture_tool_port,
    )
    try:
        if args.mode == "fresh":
            write_output(runner.run_fresh().as_mapping(), args.output)
            return EXIT_OK
        phase = runner.growth_phase()
        if args.mode == "mature":
            write_output(
                {"growth_phase": phase.as_mapping(), "arm": runner.run_mature(phase).as_mapping()}, args.output
            )
            return EXIT_OK
        if args.mode == "ablation":
            mature = runner.run_mature(phase)
            ablation = runner.run_ablation(Mechanism(args.mechanism), phase=phase, baseline=mature)
            write_output({"growth_phase": phase.as_mapping(), "ablation": ablation.as_mapping()}, args.output)
            return EXIT_OK
        demo = runner.run_growth_demo()
        write_output(demo.as_mapping(), args.output)
        return EXIT_OK if demo.comparison.verdict.passed else EXIT_VERDICT_FAILED
    except GrowthBenchmarkError as exc:
        print(f"실행 거부: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
