from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
OUT = Path(__file__).resolve().parent
PATHS = (
    "docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP09C-PRODUCT-VISION-OUTPUT-CONTRACT-01/run-20261014T021626Z-codex-4f8b80cb",
    "docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP09B-PRODUCT-VISION-STRUCTURED-OBSERVATION-01/run-20261014T040632Z-codex-5697c22846df",
    "docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP09C-PRODUCT-VISION-ACCEPTANCE-METADATA-CONTRACT-01/run-20261014T043024Z-codex-86e22b4940",
    "docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP09C-STATUS-RECONCILIATION-2026-10-14/run-20261014T043024Z-codex-86e22b4940",
    "docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP09C-STRUCTURED-OUTPUT-PUBLICATION-01/run-20261014T043024Z-codex-86e22b4940",
    "docs/qa/sequential-improvement/luna-review-2026-10-14-acceptance-metadata",
)


def main() -> None:
    files = sorted(p for name in PATHS for p in (ROOT / name).rglob("*") if p.is_file() or p.is_symlink())
    names = [p.relative_to(ROOT).as_posix() for p in files]
    ignored_result = subprocess.run(
        ["git", "check-ignore", "-z", "--stdin"],
        cwd=ROOT,
        input=b"\0".join(n.encode() for n in names) + b"\0",
        stdout=subprocess.PIPE,
        check=False,
    )
    if ignored_result.returncode not in (0, 1):
        raise RuntimeError("git check-ignore failed")
    ignored = set(ignored_result.stdout.decode().split("\0"))
    published: list[dict[str, object]] = []
    omitted: list[dict[str, str]] = []
    for path, name in zip(files, names, strict=True):
        reason = None
        if path.is_symlink():
            reason = "local fixture symlink"
        elif "auth" in path.parts:
            reason = "ephemeral authentication material"
        elif ".git" in path.parts:
            reason = "nested local repository state"
        elif any(part in path.parts for part in ("__pycache__", ".pytest_cache", ".locks")):
            reason = "cache or lock"
        elif path.suffix in (".db", ".sqlite", ".sqlite3", ".lock") or path.name.endswith(("-wal", "-shm")):
            reason = "derived runtime database or lock"
        elif name in ignored:
            reason = "repository ignore rule"
        if reason is not None:
            omitted.append({"path": name, "reason": reason})
            continue
        raw = path.read_bytes()
        published.append({"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    manifest = {
        "scope": "Owned structured-output implementation QA, structured live observation, metadata fix and publication candidate only",
        "published_count": len(published),
        "published_bytes": sum(int(str(item["bytes"])) for item in published),
        "omitted_count": len(omitted),
        "published": published,
        "omitted": omitted,
        "local_sealed_manifests": "Original local manifests cover a larger private runtime inventory; omitted files remain unchanged locally.",
        "acceptance": "Fresh structured observation PASS_SCOPED; historical format-omitted FAIL_SEMANTIC unchanged; overall IMP09 PARTIAL",
    }
    with (OUT / "publication-manifest.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    helper_names = [
        (OUT / n).relative_to(ROOT).as_posix()
        for n in ("prepare_publication.py", "README.md", "publication-manifest.json")
    ]
    with (OUT / "commit-paths.txt").open("x", encoding="utf-8") as stream:
        stream.write("\n".join([str(item["path"]) for item in published] + helper_names) + "\n")
    print(json.dumps({k: manifest[k] for k in ("published_count", "published_bytes", "omitted_count")}))


if __name__ == "__main__":
    main()
