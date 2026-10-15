from __future__ import annotations

import importlib.util
from pathlib import Path


BASE = Path(__file__).resolve().parent
ROOT = Path('/Users/mr.k/program/coding/ssak_comp/Ssak-Ai')
SOURCE = ROOT / 'docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP20-GATE-PREREQUISITES-PUBLICATION-01/run-20261014T231300Z-codex/integrate_surface.py'
spec = importlib.util.spec_from_file_location('owned_integration', SOURCE)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.__dict__['OLD'] = '302337877766a540a21dd42c61605dc590e4026b'
module.__dict__['NEW'] = '1e9dfb87b185f3d20792d3f4bff4a25189947c15'
module.__file__ = str(BASE / 'integration_round2.py')
module.__dict__['main']()
