# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict


class Artifact(TypedDict):
    path: str
    bytes: int
    sha256: str


def collect(root: Path) -> list[Artifact]:
    artifacts: list[Artifact] = []
    for directory, directories, files in os.walk(root, followlinks=False):
        current = Path(directory)
        for name in directories:
            if (current / name).is_symlink():
                raise ValueError(f"Symlink directory is not sealable: {current / name}")
        for name in files:
            path = current / name
            relative = path.relative_to(root).as_posix()
            if relative == "artifact-manifest.json":
                continue
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(descriptor, "rb") as handle:
                before = os.fstat(handle.fileno())
                if not path.is_file():
                    raise ValueError(f"Non-file artifact: {relative}")
                digest = hashlib.file_digest(handle, "sha256").hexdigest()
                after = os.fstat(handle.fileno())
            fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
            if any(getattr(before, field) != getattr(after, field) for field in fields):
                raise ValueError(f"Artifact changed during seal: {relative}")
            artifacts.append({"path": relative, "bytes": after.st_size, "sha256": digest})
    return sorted(artifacts, key=lambda artifact: artifact["path"])


def verify(root: Path) -> None:
    manifest_path = root / "artifact-manifest.json"
    if manifest_path.is_symlink():
        raise ValueError("Manifest must be a regular file")
    recorded: object = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(recorded, dict) or recorded.get("schema_version") != 1:
        raise ValueError("Invalid manifest schema")
    artifacts = collect(root)
    if recorded.get("files") != artifacts:
        raise ValueError("Manifest differs from current artifacts or coverage")
    print(
        json.dumps(
            {
                "status": "PASS",
                "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                "files": len(artifacts),
                "total_bytes": sum(artifact["bytes"] for artifact in artifacts),
                "mismatches": [],
                "coverage": "ALL_REGULAR_FILES_EXCEPT_MANIFEST",
            }
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("seal", "verify"))
    args = parser.parse_args()
    root = Path(__file__).absolute().parent
    if root.is_symlink():
        raise ValueError("Owned root must not be a symlink")
    if args.mode == "seal":
        artifacts = collect(root)
        manifest = {
            "schema_version": 1,
            "created_at": datetime.now(UTC).isoformat(),
            "scope": "All regular files in this owned run; manifest self-excluded",
            "files": artifacts,
        }
        with (root / "artifact-manifest.json").open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    verify(root)


if __name__ == "__main__":
    main()
