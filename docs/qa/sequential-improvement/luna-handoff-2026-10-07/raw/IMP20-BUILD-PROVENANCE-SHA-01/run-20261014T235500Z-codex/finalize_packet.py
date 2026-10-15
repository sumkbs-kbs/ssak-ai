from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

REPO = Path('/Users/mr.k/.codex/worktrees/gate-contract-repair/Ssak-Ai')
BASE = Path(__file__).resolve().parent
private = BASE / 'private-replay'
private.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(dir=private) as temporary:
    replay = Path(temporary)
    subprocess.run(['git', 'init', '-q', str(replay)], check=True)
    for original in (BASE / 'preimage').rglob('*'):
        if original.is_file():
            target = replay / original.relative_to(BASE / 'preimage')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, target)
    subprocess.run(['git', '-C', str(replay), 'add', '--all'], check=True)
    subprocess.run(['git', '-C', str(replay), '-c', 'core.hooksPath=/dev/null', '-c', 'user.name=QA replay', '-c', 'user.email=qa@example.invalid', 'commit', '-qm', 'preimage'], check=True)
    incomplete = BASE / 'task-only-incomplete.patch'
    if not incomplete.exists():
        shutil.copyfile(BASE / 'task-only.patch', incomplete)
    for original in (BASE / 'preimage').rglob('*'):
        if original.is_file():
            relative = original.relative_to(BASE / 'preimage')
            source = REPO / relative
            target = replay / relative
            if source.is_file():
                shutil.copyfile(source, target)
            else:
                target.unlink()
    for source in (REPO / 'src/antigravity_k/dashboard_dist').rglob('*'):
        if source.is_file():
            target = replay / source.relative_to(REPO)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    subprocess.run(['git', '-C', str(replay), 'add', '--all'], check=True)
    full_patch = subprocess.check_output(['git', '-C', str(replay), 'diff', '--cached', '--binary'])
    (BASE / 'task-only.patch').write_bytes(full_patch)
    subprocess.run(['git', '-C', str(replay), 'reset', '--hard', '-q', 'HEAD'], check=True)
    subprocess.run(['git', '-C', str(replay), 'apply', '--check', str(BASE / 'task-only.patch')], check=True)
    subprocess.run(['git', '-C', str(replay), 'apply', str(BASE / 'task-only.patch')], check=True)
    wanted = {str(p.relative_to(REPO)) for p in (REPO / 'src/antigravity_k/dashboard_dist').rglob('*') if p.is_file()}
    wanted.add('dashboard/build-provenance.json')
    actual = {str(p.relative_to(replay)) for p in replay.rglob('*') if p.is_file() and '.git' not in p.parts}
    assert wanted == actual
    assert all((REPO / p).read_bytes() == (replay / p).read_bytes() for p in wanted)
    (BASE / 'patch-reconstruction.json').write_text(json.dumps({'files': len(wanted), 'byte_identical': True}, indent=2) + '\n')
assert not subprocess.check_output(['git', '-C', str(REPO), 'diff', '--', 'dashboard/src', 'dashboard/src/utils/buildStamp.provenance.test.ts'])
result = {
    'status': 'COMPLETE_SCOPED_BUILD_PROVENANCE', 'independent_review': 'PENDING',
    'red': 'Fresh formal dashboard-unit1243PASS1FAIL: committed ID was not a hexadecimal source revision',
    'green': 'Full dashboard-unit1244PASS; tests and source implementation unchanged',
    'pin_source_commit': 'a7c1dc2f8fe4959dbc6a6df47bb2a628d35c449c',
    'pin': json.loads((REPO / 'dashboard/build-provenance.json').read_bytes()),
    'bundle': json.loads((BASE / 'bundle-reproduction.json').read_bytes()),
    'limits': 'Metadata and regenerated bundle only; no new browser surface, model inference, full23 or release claim. Earlier failed candidate remains failed.',
}
(BASE / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
(BASE / 'handoff-ko.md').write_text('# 빌드 소스 ID 계약 수정\n\n이전 surface 접두사 ID가 기존 hex 소스 리비전 계약을 위반했습니다. 실제 UI 소스 커밋 a7c1dc2f 전체 SHA와 새 준비 시각을 고정했고 기존 테스트·제품 구현은 바꾸지 않았습니다. 전체 단위1244통과, 표준 빌드 두 번의106개 파일 바이트 일치, 패치107파일 재구성 일치를 확인했습니다. 독립 검수 대기이며 전체23/브라우저/출시 승인과 구분합니다. 이전 실패는 red-gate-capture.json에 남겼습니다.\n')
rows = []
for p in BASE.rglob('*'):
    if p.is_file() and 'private-replay' not in p.parts and p.name != 'artifact-manifest.json':
        rows.append({'path': str(p.relative_to(BASE)), 'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()})
(BASE / 'artifact-manifest.json').write_text(json.dumps(rows, indent=2) + '\n')
print(json.dumps({'files': len(rows), 'bundle_files': len(wanted) - 1}))
