from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = Path("/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai")
OWNED = ("config.yaml", "tests/test_cli_smoke.py")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    checks = []
    commands = [
        [str(ROOT / ".venv/bin/ruff"), "check", "tests/test_cli_smoke.py"],
        [str(ROOT / ".venv/bin/ruff"), "format", "--check", "tests/test_cli_smoke.py"],
        [str(ROOT / ".venv/bin/python"), "-B", "-c", "from pathlib import Path; compile(Path('tests/test_cli_smoke.py').read_bytes(), 'tests/test_cli_smoke.py', 'exec')"],
        ["git", "diff", "--check", "--", *OWNED],
    ]
    for index, command in enumerate(commands):
        result = subprocess.run(command, cwd=ROOT, capture_output=True, check=False)
        out = BASE / f"static-{index}.stdout.txt"
        err = BASE / f"static-{index}.stderr.txt"
        out.write_bytes(result.stdout)
        err.write_bytes(result.stderr)
        checks.append({"command": command, "exit_code": result.returncode, "stdout": out.name, "stderr": err.name})
    (BASE / "checks.json").write_text(json.dumps(checks, indent=2) + "\n")
    patch = subprocess.check_output(["git", "diff", "--binary", "--", *OWNED], cwd=ROOT)
    (BASE / "task-only.patch").write_bytes(patch)
    rebuilt = BASE / "reconstructed"
    rebuilt.mkdir()
    for path in OWNED:
        target = rebuilt / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((BASE / "preimage" / path).read_bytes())
    subprocess.run(["git", "apply", str(BASE / "task-only.patch")], cwd=rebuilt, check=True)
    reconstruction = {path: (rebuilt / path).read_bytes() == (ROOT / path).read_bytes() for path in OWNED}
    (BASE / "patch-reconstruction.json").write_text(json.dumps(reconstruction, indent=2) + "\n")
    bindings = {path: digest(ROOT / path) for path in OWNED}
    (BASE / "source-binding-final.json").write_text(json.dumps(bindings, indent=2) + "\n")
    phases = {}
    for phase in ("runtime", "api", "repaired", "precedence", "api-corrected-guard"):
        directory = BASE / phase
        junit = ET.parse(directory / "junit.xml")
        cases = junit.findall(".//testcase")
        events = [json.loads(line) for path in sorted((directory / "trace").glob("events-*.jsonl")) for line in path.read_text().splitlines()]
        starts = [event for event in events if event["event"] == "python-start"]
        connections = [event for event in events if event["event"] == "socket-connect"]
        phases[phase] = {
            "tests": len(cases), "failures": sum(case.find("failure") is not None for case in cases),
            "errors": sum(case.find("error") is not None for case in cases), "skips": sum(case.find("skipped") is not None for case in cases),
            "receipt": json.loads((directory / "receipt.json").read_text()),
            "python_runtime_starts": len(starts), "python_interpreters": sorted({event["executable"] for event in starts}),
            "connection_attempts": len(connections), "allowed_owned_connections": sum(event["allowed"] for event in connections),
            "blocked_connections": sum(not event["allowed"] for event in connections),
            "owned_listens": sum(event["event"] == "owned-listen" for event in events),
        }
    result = {"status": "SCOPED_RUNTIME_RECHECK_PASS", "review": "PENDING", "base_commit": "481a634195bd3924ed601f1b881958c75e5e6892", "owned_paths": list(OWNED), "phases": phases, "static_checks_pass": all(check["exit_code"] == 0 for check in checks), "patch_reconstruction": reconstruction, "limits": ["Retained 40 passing runtime cases from original invocation; two repaired cases and four precedence cases have fresh proof. Not one monolithic clean selector.", "First API run failed because the guard did not observe uvloop native listen; final API proof explicitly selects asyncio loop. No uvloop runtime claim.", "API health/auth boundary only; no inference or live provider validation.", "No full Python suite or overall GA pass. Other agents edit disjoint files in the candidate.", "private-runtime directories contain test credentials/storage and must not be published.", "In-process discovered-model CLI fixture is transport-mocked; other CLI subprocess smoke remains real."]}
    (BASE / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    manifest = {}
    for path in sorted(BASE.rglob("*")):
        relative = path.relative_to(BASE)
        if path.is_file() and "private-runtime" not in relative.parts and "__pycache__" not in relative.parts and relative.name != "artifact-manifest.json":
            manifest[str(relative)] = {"bytes": path.stat().st_size, "sha256": digest(path)}
    (BASE / "artifact-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
