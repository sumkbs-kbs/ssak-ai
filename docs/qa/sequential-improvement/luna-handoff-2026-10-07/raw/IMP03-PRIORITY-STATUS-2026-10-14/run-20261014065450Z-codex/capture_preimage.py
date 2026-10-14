from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path("/Users/mr.k/program/coding/ssak_comp/Ssak-Ai")
RUN = Path(__file__).resolve().parent
DOCS = ROOT / "docs/qa/sequential-improvement/luna-handoff-2026-10-07"

def main() -> None:
    preimage = RUN / "source-preimage"
    preimage.mkdir()
    for name in ("STATUS.md", "tasks.json"):
        shutil.copyfile(DOCS / name, preimage / name)
    tasks = json.loads((DOCS / "tasks.json").read_text())
    legacy = {key: value for key, value in tasks.items() if key != "current_snapshot"}
    historical = (DOCS / "STATUS.md").read_text().split("## 역사 스냅샷", 1)[1]
    baseline = {
        "legacy_tasks_sha256": hashlib.sha256(json.dumps(legacy, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        "historical_status_sha256": hashlib.sha256(historical.encode()).hexdigest(),
        "staged_diff_sha256": hashlib.sha256(subprocess.check_output(["git", "-C", str(ROOT), "diff", "--cached", "--binary"])).hexdigest(),
        "root_head": subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"]).decode().strip(),
    }
    (RUN / "preservation-before.json").write_text(json.dumps(baseline, indent=2) + "\n")
    print(json.dumps(baseline))

if __name__ == "__main__":
    main()
