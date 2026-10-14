from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path("/Users/mr.k/program/coding/ssak_comp/Ssak-Ai")
TARGET = Path("/Users/mr.k/.codex/worktrees/structured-output-publication/Ssak-Ai")
OUT = Path(__file__).resolve().parent


def main() -> None:
    manifest = json.loads((OUT / "publication-manifest.json").read_text())
    paths: list[str] = []
    for item in manifest["published"]:
        source = ROOT / item["path"]
        raw = source.read_bytes()
        if len(raw) != item["bytes"] or hashlib.sha256(raw).hexdigest() != item["sha256"]:
            raise RuntimeError("Publication source drift: " + item["path"])
        target = TARGET / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        paths.append(item["path"])
    dependency_records = []
    for folder in (
        "luna-review-2026-10-08-stream-options",
        "luna-review-2026-10-10-tool03-live",
        "luna-review-2026-10-10-messages-image-contract",
    ):
        for filename in ("review.md", "review.json", "verification.json"):
            name = "docs/qa/sequential-improvement/" + folder + "/" + filename
            source = ROOT / name
            if not source.is_file():
                continue
            raw = source.read_bytes()
            dependency_records.append({"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
            target = TARGET / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            paths.append(name)
    dependencies = {
        "scope": "Historical review reports directly referenced by current status; no historical runtime archive recreation",
        "files": dependency_records,
    }
    with (OUT / "publication-dependencies.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(dependencies, indent=2) + "\n")
    for filename in (
        "prepare_publication.py",
        "README.md",
        "publication-manifest.json",
        "publication-dependencies.json",
        "copy_publication.py",
    ):
        source = OUT / filename
        name = source.relative_to(ROOT).as_posix()
        target = TARGET / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        paths.append(name)
    with (OUT / "qa-commit-paths.txt").open("x", encoding="utf-8") as stream:
        stream.write("\n".join(paths) + "\n")
    print(
        json.dumps(
            {
                "copied_manifest_files": len(manifest["published"]),
                "historical_report_dependencies": len(dependency_records),
                "total_qa_paths": len(paths),
            }
        )
    )


if __name__ == "__main__":
    main()
