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
from pathlib import Path
from typing import Final

from antigravity_k.engine.cognitive_surface import (
    measure_surface_reach,
)

EXIT_OK: Final[int] = 0


def source_head() -> str:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="measure_cognitive_surface",
        description="SSAK-AI cognitive surface reach measurement (static import graph)",
    )
    parser.add_argument("--output", type=Path, default=None, help="결과 JSON artifact 경로")
    parser.add_argument("--source-root", type=Path, default=None, help="패키지 source root(기본: 저장소 src)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    measurement = measure_surface_reach(source_root=args.source_root)
    payload = {**measurement.as_mapping(), "source_head": source_head()}
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
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"wrote {args.output}")
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
