from pathlib import Path
import hashlib,json,shutil
ROOT=Path("/Users/mr.k/program/coding/ssak_comp/Ssak-Ai")
CANDIDATE=Path("/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai")
BASE=Path(__file__).resolve().parent
PACKETS=[["/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP20-DASHBOARD-RELEASE-SURFACE-01/run-20261014T230500Z-surface","artifact-manifest.json","/Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP20-DASHBOARD-RELEASE-SURFACE-01/run-20261014T230500Z-surface"]]
PRIVATE={"runtime","private-runtime","cache","__pycache__","auth-private","private-raw"}
inventory={}
for directory,name,content_root in PACKETS:
    source=Path(directory)
    content=Path(content_root)
    document=json.loads((source/name).read_bytes())
    if isinstance(document,list):
        rows=document
    elif "files" in document:
        rows=document["files"]
    else:
        rows=[{"path":p,**v} for p,v in document.items()]
    for row in rows:
        rel=Path(row["path"])
        assert not rel.is_absolute() and ".." not in rel.parts
        forbidden=PRIVATE - {"runtime"} if source.name=="run-20261015T004000Z-runtime" else PRIVATE
        assert not forbidden.intersection(rel.parts),str(rel)
        path=content/rel
        assert path.is_file() and not path.is_symlink(),str(path)
        data=path.read_bytes()
        assert len(data)==row["bytes"] and hashlib.sha256(data).hexdigest()==row["sha256"],str(path)
        destination=path.relative_to(ROOT)
        inventory[str(destination)]={"bytes":len(data),"sha256":row["sha256"]}
    manifest_data=(source/name).read_bytes()
    inventory[str((source/name).relative_to(ROOT))]={"bytes":len(manifest_data),"sha256":hashlib.sha256(manifest_data).hexdigest()}
for relative,row in inventory.items():
    source=ROOT/relative
    destination=CANDIDATE/relative
    destination.parent.mkdir(parents=True,exist_ok=True)
    if destination.exists():
        assert destination.read_bytes()==source.read_bytes(),str(destination)
    else:
        shutil.copyfile(source,destination)
    assert hashlib.sha256(destination.read_bytes()).hexdigest()==row["sha256"]
receipt={"operation":"copy_manifest_verified_public_evidence_only","packets":len(PACKETS),"files":len(inventory),"bytes":sum(r["bytes"] for r in inventory.values()),"private_subtrees_excluded":sorted(PRIVATE),"inventory":inventory}
target=BASE/"public-ui-copy-receipt.json"
assert not target.exists()
target.write_text(json.dumps(receipt,indent=2)+"\n")
print(json.dumps({k:v for k,v in receipt.items() if k!="inventory"}))
