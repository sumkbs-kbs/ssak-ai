from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path("/Users/mr.k/program/coding/ssak_comp/Ssak-Ai")
OLD = "1c872d6d47adff3785ea8164be5283b254559f1d"
NEW = "b91fa86cebff0bdfd7af1b1f0d9681c8f6392e5f"
BRANCH = "refs/heads/codex/m1-task-events"
EXPECTED_STAGED_SHA = "84297d5d47940af4560187d6b9f531b3b1eed5a7fa6cd1dca20c4da48fddab6f"


def git(*args: str, data: bytes | None = None) -> bytes:
    return subprocess.check_output(["git", "-C", str(ROOT), *args], input=data)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    assert git("symbolic-ref", "HEAD").decode().strip() == BRANCH
    assert git("rev-parse", "HEAD").decode().strip() == OLD
    git("merge-base", "--is-ancestor", OLD, NEW)
    staged_before = git("diff", "--cached", "--binary")
    assert digest(staged_before) == EXPECTED_STAGED_SHA
    staged_paths = set(git("diff", "--cached", "--name-only", "-z").split(b"\0")) - {b""}
    changed = set(git("diff", "--name-only", "--no-renames", "-z", OLD, NEW).split(b"\0")) - {b""}
    assert changed.isdisjoint(staged_paths), "Publication overlaps somebody else's staged paths"
    index_tree_before = git("write-tree").decode().strip()
    tracked_dirty = set(git("diff", "HEAD", "--name-only", "-z").split(b"\0")) - {b""}
    observed_paths = tracked_dirty | changed
    before_bytes = {
        p.decode(): digest((ROOT / p.decode()).read_bytes())
        for p in observed_paths
        if (ROOT / p.decode()).is_file()
    }
    rows = []
    for record in git("ls-tree", "-r", "-z", NEW).split(b"\0"):
        if not record:
            continue
        metadata, path = record.split(b"\t", 1)
        if path in changed:
            mode, kind, oid = metadata.split(b" ")
            assert kind == b"blob"
            rows.append(mode + b" " + oid + b"\t" + path + b"\0")
    assert len(rows) == len(changed), "This integration only accepts additions/modifications"
    assert digest(git("diff", "--cached", "--binary")) == EXPECTED_STAGED_SHA
    git("update-index", "-z", "--index-info", data=b"".join(rows))
    git("update-ref", BRANCH, NEW, OLD)
    staged_after = git("diff", "--cached", "--binary")
    assert staged_after == staged_before, "Unrelated staged diff changed"
    assert git("rev-parse", "HEAD").decode().strip() == NEW
    changed_working_bytes = [
        p for p, sha in before_bytes.items()
        if not (ROOT / p).is_file() or digest((ROOT / p).read_bytes()) != sha
    ]
    assert not changed_working_bytes, changed_working_bytes
    result = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "operation": "fast_forward_ref_and_owned_index_entries_only",
        "old_head": OLD,
        "new_head": NEW,
        "changed_committed_paths": len(changed),
        "preserved_staged_paths": len(staged_paths),
        "preserved_staged_binary_sha256": digest(staged_after),
        "recovery_index_tree": index_tree_before,
        "working_file_hashes_checked": len(before_bytes),
        "working_files_changed_by_integration": changed_working_bytes,
    }
    receipt = Path(__file__).with_name("integration-receipt.json")
    assert not receipt.exists()
    receipt.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()

