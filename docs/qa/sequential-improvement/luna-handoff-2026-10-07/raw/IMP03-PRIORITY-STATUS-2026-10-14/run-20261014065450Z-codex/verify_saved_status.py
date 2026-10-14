from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path("/Users/mr.k/program/coding/ssak_comp/Ssak-Ai")
RUN = Path(__file__).resolve().parent
DOCS = ROOT / "docs/qa/sequential-improvement/luna-handoff-2026-10-07"

def main() -> None:
    before = json.loads((RUN / "preservation-before.json").read_text())
    current = json.loads((DOCS / "tasks.json").read_text())
    legacy = {key: value for key, value in current.items() if key != "current_snapshot"}
    status = (DOCS / "STATUS.md").read_text()
    after: dict[str, object] = {
        "legacy_tasks_sha256": hashlib.sha256(json.dumps(legacy, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        "historical_status_sha256": hashlib.sha256(status.split("## 역사 스냅샷", 1)[1].encode()).hexdigest(),
        "staged_diff_sha256": hashlib.sha256(subprocess.check_output(["git", "-C", str(ROOT), "diff", "--cached", "--binary"])).hexdigest(),
    }
    assert all(after[key] == before[key] for key in after), after
    snapshot = current["current_snapshot"]
    assert f"**NEXT_TASK={snapshot['next_task']}." in status
    assert snapshot["parent_status"]["IMP-09"] == "PARTIAL"
    assert snapshot["parent_status"]["historical_ledger"] == "NOT_RECOVERED"
    after.update({
        "status": "CURRENT_STATUS_RECONCILED_HISTORICAL_FIELDS_UNCHANGED",
        "next_task": snapshot["next_task"],
        "docs": {name: hashlib.sha256((DOCS / name).read_bytes()).hexdigest() for name in ("STATUS.md", "tasks.json")},
    })
    with (RUN / "preservation-after.json").open("x") as stream:
        stream.write(json.dumps(after, indent=2) + "\n")
    print(json.dumps(after))

if __name__ == "__main__":
    main()
