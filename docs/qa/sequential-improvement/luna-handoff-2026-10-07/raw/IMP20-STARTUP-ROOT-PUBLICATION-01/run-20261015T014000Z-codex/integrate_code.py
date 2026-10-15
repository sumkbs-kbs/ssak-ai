import importlib.util
from pathlib import Path

ROOT = Path('/Users/mr.k/program/coding/ssak_comp/Ssak-Ai')
source = ROOT / 'docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP20-GATE-PREREQUISITES-PUBLICATION-01/run-20261014T231300Z-codex/integrate_surface.py'
spec = importlib.util.spec_from_file_location('startup_root_integration', source)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.__dict__['OLD'] = '7360c78544abeea41e38c65faa6eba2610a8a33b'
module.__dict__['NEW'] = '58d941b340a29a8717dcfbc87348b8542fe0bd77'
module.__file__ = __file__
module.__dict__['main']()
