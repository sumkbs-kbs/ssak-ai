import hashlib
import json
import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parent
REPO = Path("/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai")
paths = {
    "tests/conftest.py": [(1, 320)],
    "tests/test_ssak_browser_loop.py": [(880, 912)],
    "tests/cognitive/test_local_live_model.py": [(1, 46)],
    "src/antigravity_k/engine/local_model_discovery.py": [(97, 128), (385, 416)],
    "scripts/ga_gate.py": [(47, 57), (289, 294)],
}
entries = []
for relative, ranges in paths.items():
    path = REPO / relative
    data = path.read_bytes()
    lines = data.decode().splitlines()
    entries.append({"path": relative, "sha256": hashlib.sha256(data).hexdigest(), "excerpts": [{"start": start, "end": end, "lines": lines[start - 1:end]} for start, end in ranges]})
(BASE / "static-source-excerpts.json").write_text(json.dumps(entries, indent=2) + "\n")
command = ["rg", "-n", "-i", "(getenv|environ|skipif).*(live|integration|ollama)|(live|integration|ollama).*(getenv|environ|skipif)", "tests", "--glob", "*.py"]
result = subprocess.run(command, cwd=REPO, capture_output=True, check=False)
(BASE / "live-flag-search.stdout.txt").write_bytes(result.stdout)
(BASE / "live-flag-search.stderr.txt").write_bytes(result.stderr)
(BASE / "static-audit-receipt.json").write_text(json.dumps({"command": command, "cwd": str(REPO), "exit_code": result.returncode, "scope": "Bounded source audit, not exhaustive call graph or runtime no-inference proof", "original_manifest_sha256": hashlib.sha256((BASE / "artifact-manifest.json").read_bytes()).hexdigest()}, indent=2) + "\n")
names = ["full-suite-boundary-audit.md", "capture_static_audit.py", "static-source-excerpts.json", "live-flag-search.stdout.txt", "live-flag-search.stderr.txt", "static-audit-receipt.json"]
manifest = [{"path": name, "bytes": (BASE / name).stat().st_size, "sha256": hashlib.sha256((BASE / name).read_bytes()).hexdigest()} for name in names]
(BASE / "static-audit-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(json.dumps({"exit_code": result.returncode, "supplement_files": len(names)}))
