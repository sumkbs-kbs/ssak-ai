import hashlib,json,shutil
from pathlib import Path
BASE=Path(__file__).resolve().parent;OUT=BASE/"revision-v2";OUT.mkdir()
for name in ("browser_entry.py","supervise_browser.py","browser_cli.mjs","scope.md"):shutil.copyfile(BASE/name,OUT/name)
(OUT/"parent-before.json").write_text(json.dumps({name:hashlib.sha256((BASE/name).read_bytes()).hexdigest() for name in ("browser_entry.py","supervise_browser.py","browser_cli.mjs","scope.md","runtime/guard-final.json","runtime/supervisor-receipt.json","browser-actions.jsonl")},indent=2)+"\n")
print("New isolated browser fixture candidate prepared")

