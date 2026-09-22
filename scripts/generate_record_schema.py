#!/usr/bin/env python3
"""canonical record JSON Schema 생성기 (P01).

envelope 계약(contracts/record-envelope.schema.json)의 entity enum을 typed payload union으로 확장한
기계 판독 schema를 생성한다. schema는 생성물이며 원본은 src/antigravity_k/engine/cognitive/models.py다.

사용:
    .venv/bin/python scripts/generate_record_schema.py            # 파일 생성
    .venv/bin/python scripts/generate_record_schema.py --check    # 현재 파일과 일치하는지 검사
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "docs/ssak-ai-core/contracts/record-entities.schema.json"

if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))


def build_schema() -> dict[str, object]:
    from antigravity_k.engine.cognitive.models import Record

    schema = Record.model_json_schema()
    schema["title"] = "SSAK-AI Canonical Record v1"
    schema["description"] = (
        "Generated from engine/cognitive/models.py. Envelope와 typed payload union을 포함한다. "
        "reference 존재 여부/권한은 저장소(P02) 검증 대상이며 이 schema가 보장하지 않는다."
    )
    return schema


def render(schema: dict[str, object]) -> str:
    return json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="생성 결과가 현재 파일과 같은지 검사만 한다")
    args = parser.parse_args(argv)

    rendered = render(build_schema())
    if args.check:
        current = args.output.read_text(encoding="utf-8") if args.output.exists() else ""
        if current != rendered:
            print(f"schema drift: {args.output}")
            return 1
        print(f"schema up to date: {args.output}")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(f"wrote {args.output} ({len(rendered)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
