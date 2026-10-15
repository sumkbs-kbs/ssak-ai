import difflib
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

RUN = Path(__file__).resolve().parent
WORKTREE = Path('/Users/mr.k/.codex/worktrees/gate-contract-repair/Ssak-Ai')
SOURCE = WORKTREE / 'dashboard/src/styles/index.css'
before = (RUN / 'preimage/index.css').read_bytes()
after = SOURCE.read_bytes()
old = b'.model-empty-notice {\n  padding: 12px 8px;\n  font-size: 12px;\n  color: #6b7280;'
new = old.replace(b'#6b7280', b'var(--text-muted)')
assert before.count(old) == 1
assert after == before.replace(old, new, 1)
patch = ''.join(difflib.unified_diff(before.decode().splitlines(True), after.decode().splitlines(True), fromfile='a/dashboard/src/styles/index.css', tofile='b/dashboard/src/styles/index.css'))
(RUN / 'task-only.patch').write_text(patch)
(RUN / 'postimage.css').write_bytes(after)

def luminance(hex_color: str) -> float:
    channels = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return sum(c * w for c, w in zip(linear, (0.2126, 0.7152, 0.0722), strict=True))

def contrast(fg: str, bg: str) -> float:
    light, dark = sorted((luminance(fg), luminance(bg)), reverse=True)
    return (light + 0.05) / (dark + 0.05)

css = after.decode()
dark_fg = re.search(r'--text-muted: (#[0-9a-f]+);', css)
dark_bg = re.search(r'--bg-primary: (#[0-9a-f]+);', css)
light_fg = re.search(r':root\[data-theme="light"\] \{\s*--text-muted: (#[0-9a-f]+);', css)
assert dark_fg and dark_bg and light_fg
ratios = {'dark_base_before': contrast('#6b7280', dark_bg[1]), 'dark_base_after': contrast(dark_fg[1], dark_bg[1]), 'light_token_on_reference_white': contrast(light_fg[1], '#ffffff')}
assert ratios['dark_base_before'] < 4.5 <= ratios['dark_base_after']
assert ratios['light_token_on_reference_white'] >= 4.5
check = subprocess.run(['git', 'diff', '--check', '--', 'dashboard/src/styles/index.css'], cwd=WORKTREE, text=True, capture_output=True, check=False)
(RUN / 'diff-check.stdout.txt').write_text(check.stdout)
(RUN / 'diff-check.stderr.txt').write_text(check.stderr)
assert check.returncode == 0
result = {
    'status': 'IMPLEMENTED_STATIC_VERIFIED_BROWSER_PENDING',
    'invocation': sys.executable + ' ' + str(Path(__file__).resolve()),
    'source': str(SOURCE),
    'preimage_sha256': hashlib.sha256(before).hexdigest(),
    'postimage_sha256': hashlib.sha256(after).hexdigest(),
    'observable': 'Exactly one color declaration changed; all other source bytes identical',
    'selector': '.model-empty-notice',
    'color': 'var(--text-muted)',
    'source_tokens': {'dark_text': dark_fg[1], 'dark_background': dark_bg[1], 'light_text': light_fg[1]},
    'static_contrast_ratios': ratios,
    'contrast_limit': 'Static base CSS arithmetic only; white is a reference background, not an observed light runtime. Browser cascade and current bundle await parent validation.',
    'git_diff_check_exit': check.returncode,
    'actual_http_or_model_calls': 0,
    'bundle_build': 'NOT_RUN_PARENT_OWNED',
    'biome': 'NOT_INSTALLED_PREEXISTING_USER_DECLINED',
    'graph': 'search_code returned project not indexed; prior 300-second index timeout supplied by parent; exact known files used',
}
(RUN / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
files = {str(p.relative_to(RUN)): {'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(RUN.rglob('*')) if p.is_file() and p.name != 'artifact-manifest.json'}
(RUN / 'artifact-manifest.json').write_text(json.dumps(files, indent=2) + '\n')
print(json.dumps(result, indent=2))
