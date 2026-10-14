import hashlib
import json
from pathlib import Path

base = Path(__file__).resolve().parent
manifest = {}
for path in sorted(base.rglob("*")):
    relative = path.relative_to(base)
    if path.is_file() and "private-runtime" not in relative.parts and "__pycache__" not in relative.parts and relative.name != "final-artifact-manifest.json":
        manifest[str(relative)] = {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
(base / "final-artifact-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
assert all((base / name).stat().st_size == entry["bytes"] and hashlib.sha256((base / name).read_bytes()).hexdigest() == entry["sha256"] for name, entry in manifest.items())
print(len(manifest))
