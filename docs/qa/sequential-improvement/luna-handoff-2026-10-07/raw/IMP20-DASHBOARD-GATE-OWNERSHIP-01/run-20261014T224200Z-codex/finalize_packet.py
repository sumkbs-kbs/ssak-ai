from __future__ import annotations
import hashlib
import json
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

BASE = Path(__file__).resolve().parent
REPO = Path("/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai")
FILES = ["scripts/run_dashboard_e2e_ambient.py", "scripts/commercial_ga_gates.json", "tests/test_cr14_ambient_backend_gate_contract.py"]
BASELINE = "481a634195bd3924ed601f1b881958c75e5e6892"
sha = lambda data: hashlib.sha256(data).hexdigest()
patch = subprocess.check_output(["git", "diff", "--binary", BASELINE, "--", *FILES], cwd=REPO)
(BASE / "task-only.patch").write_bytes(patch)
with tempfile.TemporaryDirectory(prefix="dashboard-patch-replay-") as raw:
    replay = Path(raw)
    subprocess.run(["git", "init", "-q"], cwd=replay, check=True)
    for name in FILES:
        target = replay / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(subprocess.check_output(["git", "show", BASELINE + ":" + name], cwd=REPO))
    subprocess.run(["git", "apply", "--check", str(BASE / "task-only.patch")], cwd=replay, check=True)
    subprocess.run(["git", "apply", str(BASE / "task-only.patch")], cwd=replay, check=True)
    rows = [{"path": name, "byte_identical": (replay / name).read_bytes() == (REPO / name).read_bytes()} for name in FILES]
    assert all(row["byte_identical"] for row in rows)
    (BASE / "patch-reconstruction.json").write_text(json.dumps(rows, indent=2) + "\n")
bindings = [{"path": name, "sha256": sha((REPO / name).read_bytes())} for name in FILES]
(BASE / "source-binding-final.json").write_text(json.dumps(bindings, indent=2) + "\n")
root = ET.parse(BASE / "checks-attempt-2-static/junit.xml").getroot()
cases = root.findall(".//testcase")
assert all(not any(case.find(kind) is not None for kind in ("failure", "error", "skipped")) for case in cases)
manifest = json.loads((REPO / FILES[1]).read_bytes())
assert len([row for row in manifest["gates"] if row["required"]]) == 23
result = {
    "status": "GATE_OWNERSHIP_STATIC_VERIFIED_PRODUCT_FAILURES_REMAIN",
    "review": "PENDING",
    "baseline": BASELINE,
    "owned_paths": FILES,
    "required_gate_count": 23,
    "static_contract_passed": len(cases),
    "static_checks": json.loads((BASE / "checks-attempt-2-static/checks.json").read_bytes()),
    "prior_browser_gates": {"accessibility": {"passed": 33, "failed": 2}, "witnesses": {"passed": 18, "failed": 12}, "ambient": {"passed": 11, "failed": 5}},
    "prior_browser_source_binding": "checks-attempt-1/source-binding.json",
    "followup": "IMP20-DASHBOARD-RELEASE-SURFACE-01",
    "formal_23_gate_verdict": "NOT_RUN_ON_NEW_CANDIDATE",
    "live_model_inference": "NOT_CLAIMED_CLOSED_PROVIDER_ENDPOINTS",
}
(BASE / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
report = "# 대시보드 게이트 서버 소유권 수정\n\n접근성 required 게이트가 서버를 직접 기동하고 명시된 접근성 스펙을 실행하도록 기존 ambient wrapper를 재사용했습니다. 선택한 스펙의 exit code와 cleanup을 검증하고, 기존 ambient·disclosure·hub 단계는 기본 경로에 유지했습니다. required 23개, 실패 단언, axe 기준과 grep 선택 범위를 낮추지 않았습니다.\n\n정적 계약 " + str(len(cases)) + "개 및 Ruff·format·오류 수준 타입 검사 통과. 초기 format 실패와 수정 원문은 별도 시도 폴더에 보존했습니다. 세 파일 patch 재구성이 byte-identical입니다.\n\n실제 브라우저 첫 실행은 접근성 33/2, witnesses 18/12, ambient 11/5(통과/실패)입니다. 실패는 글자 대비 및 현재 화면과 어긋난 탐색·표시 계약입니다. 원문을 보존했고 후속 UI 수리에서 다룹니다. 이 패키지 자체를 제품 게이트 전체 PASS로 판단하지 않습니다. 격리 인증·스토리지와 비수신 모델 endpoint를 사용했고, 모델 추론 성공을 주장하지 않습니다. 독립 검수와 새 후보 전체 게이트는 대기 상태입니다.\n"
(BASE / "handoff-ko.md").write_text(report)
inventory = []
for path in sorted(BASE.rglob("*")):
    if not path.is_file() or {"runtime", "cache", "__pycache__"}.intersection(path.relative_to(BASE).parts) or path.name.startswith("artifact-manifest"):
        continue
    data = path.read_bytes()
    inventory.append({"path": str(path.relative_to(BASE)), "bytes": len(data), "sha256": sha(data)})
(BASE / "artifact-manifest.json").write_text(json.dumps(inventory, indent=2) + "\n")
print(json.dumps({"static_contract_passed": len(cases), "manifest_files": len(inventory), "patch_paths": len(rows)}))

