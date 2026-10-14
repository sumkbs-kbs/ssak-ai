import hashlib,json,shutil
from pathlib import Path
BASE=Path(__file__).resolve().parent;PRE=BASE/"revision-v2";OUT=BASE/"revision-v3";OUT.mkdir()
for name in ("browser_entry.py","supervise_browser.py","browser_cli.mjs","scope.md","fixture-boundary.md"):shutil.copyfile(PRE/name,OUT/name)
(OUT/"parent-before.json").write_text(json.dumps({str(p.relative_to(PRE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in PRE.rglob("*") if p.is_file() and not p.is_symlink() and "browser-profile" not in p.parts},indent=2)+"\n")
print("Created fresh browser candidate v3; v2 evidence preserved")

