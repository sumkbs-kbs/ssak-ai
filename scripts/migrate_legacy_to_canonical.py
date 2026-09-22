#!/usr/bin/env python
"""P12 migration dry-run CLI — legacy SQLite를 별도 root의 canonical로 옮겨 관찰만 한다.

```sh
# dry-run (기본): source는 read-only, target은 별도 root
.venv/bin/python scripts/migrate_legacy_to_canonical.py \
    --source /path/agency.db --target /tmp/migration-dry-run --output /tmp/migration-report.json

# destructive 변환은 이 CLI가 하지 않는다(사람 결정)
.venv/bin/python scripts/migrate_legacy_to_canonical.py --source agency.db --target /tmp/x --apply   # exit 2
```

규칙:

- source·target이 겹치면 거부한다(migration.py guard).
- report에 source digest·counts, mapping digest·entries, index rebuild·digest 검증, idempotent replay,
  rollback rehearsal, `destructive_executed=false`를 남긴다.
- legacy enum을 옮길 수 없는 row는 사유와 함께 report.errors에 남기고 exit 1로 알린다(조용히 넘기지 않는다).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Final

from antigravity_k.engine.cognitive.migration import (
    DRY_RUN,
    DestructiveMigrationRefused,
    LegacyMigrationRunner,
    LegacySQLiteSource,
    MigrationError,
)

EXIT_OK: Final[int] = 0
EXIT_INCOMPLETE: Final[int] = 1
EXIT_USAGE: Final[int] = 2


def source_head() -> str:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="migrate_legacy_to_canonical",
        description="SSAK-AI legacy→canonical migration dry-run (source read-only)",
    )
    parser.add_argument("--source", type=Path, required=True, help="legacy PersistentAgency SQLite 경로")
    parser.add_argument("--target", type=Path, required=True, help="별도 canonical target root")
    parser.add_argument("--output", type=Path, default=None, help="report JSON artifact 경로")
    parser.add_argument("--apply", action="store_true", help="destructive 변환 요청(이 CLI는 거부한다)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.apply:
        print(
            "destructive migration은 이 CLI가 실행하지 않는다(NOT_RUN) — 별도 사람 승인 절차가 필요하다",
            file=sys.stderr,
        )
        return EXIT_USAGE
    try:
        runner = LegacyMigrationRunner(LegacySQLiteSource(args.source), args.target, mode=DRY_RUN)
    except (MigrationError, DestructiveMigrationRefused) as exc:
        print(f"migration 거부: {exc}", file=sys.stderr)
        return EXIT_USAGE
    report = runner.run()
    payload = {**report.as_mapping(), "source_head": source_head()}
    print(f"mode: {report.plan.mode} · source digest {report.plan.source.digest}")
    print(f"source counts: {dict(report.plan.source.counts)}")
    print(f"imported: {dict(report.imported)} · canonical records {report.canonical_record_count}")
    print(f"mapping entries {report.mapping_entries} · digest {report.mapping_digest}")
    print(
        f"index rebuilt {report.index_rebuilt} · digests verified {report.digests_verified} · "
        f"idempotent replay {report.idempotent_replay}"
    )
    print(
        f"source unchanged {report.source_unchanged} · rollback rehearsed {report.rollback_rehearsed} · "
        f"destructive executed {report.destructive_executed}"
    )
    for warning in report.warnings:
        print(f"  warning: {warning}")
    for error in report.errors:
        print(f"  error: {error}", file=sys.stderr)
    print(f"verdict: passed={report.passed} complete={report.complete}")
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {args.output}")
    return EXIT_OK if report.passed else EXIT_INCOMPLETE


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
