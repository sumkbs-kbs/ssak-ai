# /// script
# requires-python = ">=3.11"
# ///
# Usage: python -B seal_observation.py
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

RUN = Path(__file__).resolve().parent


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    phase = RUN / "history/final-driver-phase/artifact-manifest.json"
    if (RUN / "artifact-manifest.json").is_file() and not phase.exists():
        phase.parent.mkdir(parents=True, exist_ok=True)
        with phase.open("xb") as stream:
            stream.write((RUN / "artifact-manifest.json").read_bytes())
    files: list[dict[str, str | int]] = []
    symlinks: list[dict[str, str]] = []
    for directory, directories, names in os.walk(RUN, followlinks=False):
        for name in sorted([*directories, *names]):
            path = Path(directory) / name
            rel = path.relative_to(RUN).as_posix()
            if rel == "artifact-manifest.json":
                continue
            if path.is_symlink():
                symlinks.append({"path": rel, "target": os.readlink(path)})
            elif path.is_file():
                raw = path.read_bytes()
                files.append({"path": rel, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    manifest = {
        "schema": "ssak.imp09c.codex.final-delivery-manifest.v1",
        "run_id": RUN.name,
        "sealed_at_utc": datetime.now(UTC).isoformat(),
        "scope": "CLOSED_OUTPUTS_STORED_ARTIFACTS_ONLY",
        "exclusion": "artifact-manifest.json self-reference",
        "prior_driver_phase": {"path": str(phase.relative_to(RUN)), "sha256": digest(phase)}
        if phase.exists()
        else None,
        "files": sorted(files, key=lambda item: str(item["path"])),
        "symlinks": sorted(symlinks, key=lambda item: item["path"]),
    }
    temporary = RUN / (".manifest-" + uuid.uuid4().hex)
    with temporary.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    os.replace(temporary, RUN / "artifact-manifest.json")
    mismatches = [
        str(record["path"])
        for record in files
        if digest(RUN / str(record["path"])) != record["sha256"]
        or (RUN / str(record["path"])).stat().st_size != record["bytes"]
    ]
    alias_mismatches = [record["path"] for record in symlinks if os.readlink(RUN / record["path"]) != record["target"]]
    print(
        json.dumps(
            {
                "status": "PASS" if not mismatches and not alias_mismatches else "FAIL",
                "files": len(files),
                "symlinks": len(symlinks),
                "file_mismatches": mismatches,
                "symlink_mismatches": alias_mismatches,
                "manifest_sha256": digest(RUN / "artifact-manifest.json"),
            }
        )
    )
    return 1 if mismatches or alias_mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
