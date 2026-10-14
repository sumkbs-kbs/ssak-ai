from pathlib import Path
import hashlib,json
base=Path(__file__).resolve().parent
rows=[]
for p in sorted(base.rglob("*")):
    rel=p.relative_to(base)
    if not p.is_file() or {"runtime","cache","__pycache__"}.intersection(rel.parts) or p.name.startswith("artifact-manifest"):
        continue
    data=p.read_bytes()
    rows.append({"path":str(rel),"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()})
(base/"artifact-manifest.json").write_text(json.dumps(rows,indent=2)+"\n")
print(json.dumps({"public_files":len(rows),"dependency_cache_files_excluded":41314}))

