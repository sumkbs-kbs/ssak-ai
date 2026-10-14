from pathlib import Path
import hashlib,json,subprocess,tempfile,xml.etree.ElementTree as ET
BASE=Path(__file__).resolve().parent
REPO=Path("/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai")
files=["src/antigravity_k/release/python.cdx.json","src/antigravity_k/release/THIRD_PARTY_NOTICES.txt"]
patch=subprocess.check_output(["git","diff","--binary","f3a42e6f","--",*files],cwd=REPO)
(BASE/"task-only.patch").write_bytes(patch)
with tempfile.TemporaryDirectory(prefix="sbom-replay-") as raw:
    target=Path(raw)
    subprocess.run(["git","init","-q"],cwd=target,check=True)
    for name in files:
        p=target/name;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_bytes((BASE/"preimage"/name).read_bytes())
    subprocess.run(["git","apply",str(BASE/"task-only.patch")],cwd=target,check=True)
    assert all((target/name).read_bytes()==(REPO/name).read_bytes() for name in files)
cases=ET.parse(BASE/"checks-attempt-1/junit.xml").getroot().findall(".//testcase")
assert all(all(case.find(kind) is None for kind in ("failure","error","skipped")) for case in cases)
result={"status":"GENERATED_CURRENT_LOCK_SCOPED_REGRESSION_PASS","review":"PENDING","changed_files":files,"regression_passed":len(cases),"patch_reconstruction":"2_BYTE_IDENTICAL","dashboard_sbom_unchanged":(BASE/"preimage/src/antigravity_k/release/dashboard.cdx.json").read_bytes()==(REPO/"src/antigravity_k/release/dashboard.cdx.json").read_bytes(),"lock_sha256":hashlib.sha256((REPO/"uv.lock").read_bytes()).hexdigest(),"release_approval":"NOT_APPROVED"}
(BASE/"result.json").write_text(json.dumps(result,indent=2)+"\n")
(BASE/"handoff-ko.md").write_text("# 갱신 의존성 SBOM\n\n기존 release_sbom generate 명령으로 현재 잠금 파일의 Python SBOM과 notices를 생성했습니다. 대시보드 SBOM은 불변입니다. 생성 영수증 및 잠금 파일 SHA를 보존했고, 관련27개 회귀가 통과했습니다. 변경된 두 파일의 패치를 시작 preimage에서 재구성해 바이트 일치를 확인했습니다. 전체 wheel/sdist 소비·GA 승인은 이 집중 검사로 주장하지 않습니다.\n")
rows=[]
for p in sorted(BASE.rglob("*")):
    rel=p.relative_to(BASE)
    if not p.is_file() or {"runtime","cache","__pycache__"}.intersection(rel.parts) or p.name=="artifact-manifest.json":continue
    data=p.read_bytes();rows.append({"path":str(rel),"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()})
(BASE/"artifact-manifest.json").write_text(json.dumps(rows,indent=2)+"\n")
print(json.dumps({"cases":len(cases),"public_files":len(rows),"changed_generated_files":len(files)}))

