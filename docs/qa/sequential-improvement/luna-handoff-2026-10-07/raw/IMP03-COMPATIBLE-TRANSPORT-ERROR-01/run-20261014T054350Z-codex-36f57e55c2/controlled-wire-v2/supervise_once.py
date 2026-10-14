from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path


ROOT = Path("/Users/mr.k/program/coding/ssak_comp/Ssak-Ai")
OUT = Path(__file__).resolve().parent


def main() -> None:
    assert not (OUT / "launch-receipt.json").exists()
    command = [str(ROOT / ".venv/bin/python"), str(OUT / "observe_once.py")]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + str(ROOT)
    started = time.time()
    result = subprocess.run(command, cwd=OUT, env=env, capture_output=True, timeout=20, check=False)
    for name, raw in (("stdout.log", result.stdout), ("stderr.log", result.stderr)):
        with (OUT / name).open("xb") as stream:
            stream.write(raw)
    receipt = {
        "command": command,
        "cwd": str(OUT),
        "source_path": env["PYTHONPATH"],
        "started_unix": started,
        "ended_unix": time.time(),
        "exit_code": result.returncode,
        "timeout_seconds": 20,
        "stdout_sha256": hashlib.sha256(result.stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(result.stderr).hexdigest(),
        "observer_sha256": hashlib.sha256((OUT / "observe_once.py").read_bytes()).hexdigest(),
    }
    with (OUT / "launch-receipt.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(receipt, indent=2) + "\n")
    print(result.stdout.decode(errors="replace")[-2500:])
    print(result.stderr.decode(errors="replace")[-1500:])
    print(json.dumps({"exit_code": result.returncode, "receipt": str(OUT / "launch-receipt.json")}))
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()


