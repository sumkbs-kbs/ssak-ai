from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path


ROOT = Path("/Users/mr.k/program/coding/ssak_comp/Ssak-Ai")
WORKTREE = Path("/Users/mr.k/.codex/worktrees/structured-output-publication/Ssak-Ai")
RUN = Path(__file__).resolve().parent
MANIFEST = RUN / "publication-manifest.json"
LIST = RUN / "publication-commit-paths.txt"
SKIP_PARTS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", "state", "pytest-temp", ".venv", "reconstruction"}


def main() -> None:
    assert not MANIFEST.exists()
    items = []
    omitted = []
    for path in sorted(RUN.rglob("*")):
        if not path.is_file():
            continue
        local = path.relative_to(RUN)
        reason = None
        if path.is_symlink():
            reason = "local_symlink"
        elif SKIP_PARTS.intersection(local.parts):
            reason = "runtime_state_cache_or_nested_git"
        elif "token_secret" in path.name or "auth_hash" in path.name or path.suffix in {".db", ".sqlite", ".sqlite3"}:
            reason = "private_auth_or_runtime_database"
        if reason:
            omitted.append({"path": str(local), "reason": reason})
            continue
        if path in {MANIFEST, LIST}:
            continue
        repository_path = path.relative_to(ROOT).as_posix()
        ignored = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", repository_path], check=False).returncode == 0
        if ignored:
            omitted.append({"path": str(local), "reason": "gitignored"})
            continue
        raw = path.read_bytes()
        items.append({"path": repository_path, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    document = {
        "scope": "Published owned RAG identity QA subset; immutable worker manifest describes local source-bound scope",
        "feature_commit": "4de2ef8b3df692e36f2e39230e6428e041c158d4",
        "files": items,
        "omitted_local_files": omitted,
        "omitted_files_preserved_locally": True,
    }
    MANIFEST.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    paths = [item["path"] for item in items] + [MANIFEST.relative_to(ROOT).as_posix()]
    for name in paths:
        destination = WORKTREE / name
        assert not destination.exists(), name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    LIST.write_text("\n".join(paths) + "\n", encoding="utf-8")
    print(json.dumps({"published_files": len(paths), "omitted_local_files": len(omitted), "manifest": str(MANIFEST)}))


if __name__ == "__main__":
    main()
