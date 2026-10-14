# /// script
# requires-python = ">=3.11"
# ///
# Usage: python -B preserve_inputs.py
from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

RUN = Path(__file__).resolve().parent
ROOT = next(parent for parent in RUN.parents if parent.name == "Ssak-Ai")
INPUT = (
    ROOT
    / "docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP09C-PRODUCT-VISION-FINAL-GATE-CLOSEOUT-01/run-20261013T232642Z-549e2e47-9d69-4fd7-95d2-ff660a38d3d2"
)
RAW = RUN.parent.parent
PARENT = (
    RAW / "IMP09C-PRODUCT-VISION-RUNTIME-COMPATIBILITY-01" / "run-20261012T233025Z-526f7458-a984-4e89-97c7-7f509a59addc"
)
GATE = RAW / "IMP09C-PRODUCT-VISION-FINAL-OFFLINE-GATE-01"
HANDOFF = RAW.parent


def inventory(base: Path) -> list[dict[str, str | int]]:
    records: list[dict[str, str | int]] = []
    pending = [base]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in sorted(entries, key=lambda item: item.name):
                path = Path(entry.path)
                rel = path.relative_to(ROOT).as_posix()
                if entry.is_symlink():
                    records.append({"path": rel, "type": "symlink", "target": os.readlink(path)})
                elif entry.is_dir(follow_symlinks=False):
                    pending.append(path)
                elif entry.is_file(follow_symlinks=False):
                    raw = path.read_bytes()
                    records.append(
                        {"path": rel, "type": "file", "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
                    )
    return sorted(records, key=lambda item: str(item["path"]))


def main() -> int:
    roots = [path for path in RUN.parent.iterdir() if path.is_dir() and path != RUN]
    roots.extend([PARENT, GATE])
    for name in ("reviews", "codex-review"):
        if (HANDOFF / name).is_dir():
            roots.append(HANDOFF / name)
    records = [item for base in roots for item in inventory(base)]
    for name in ("STATUS.md", "tasks.json", "runs.jsonl", "changes.jsonl"):
        path = HANDOFF / name
        if path.is_file():
            raw = path.read_bytes()
            records.append(
                {
                    "path": path.relative_to(ROOT).as_posix(),
                    "type": "file",
                    "bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
            )
    records = sorted(records, key=lambda item: str(item["path"]))
    target = RUN / "baseline" / "preserved-inputs-before.json"
    with target.open("x", encoding="utf-8") as stream:
        stream.write(
            json.dumps(
                {
                    "captured_at_utc": datetime.now(UTC).isoformat(),
                    "roots": [str(p.relative_to(ROOT)) for p in roots],
                    "items": records,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
    for name in ("execution-binding.json", "request.json", "request.binding.json"):
        raw = (INPUT / name).read_bytes()
        with (RUN / "baseline" / ("input-" + name)).open("xb") as stream:
            stream.write(raw)
    print(json.dumps({"preserved_items": len(records), "input_run": str(INPUT.relative_to(ROOT))}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
