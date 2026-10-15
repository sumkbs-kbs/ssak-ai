from __future__ import annotations

import importlib.util
from pathlib import Path

BASE = Path(__file__).resolve().parent
SOURCE = BASE.parents[1] / 'IMP20-GATE-PREREQUISITES-PUBLICATION-01/run-20261014T231300Z-codex/integrate_surface.py'
spec = importlib.util.spec_from_file_location('reviewed_integration', SOURCE)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.__dict__['OLD'] = 'a7c1dc2f8fe4959dbc6a6df47bb2a628d35c449c'
module.__dict__['NEW'] = '302337877766a540a21dd42c61605dc590e4026b'
module.__file__ = str(BASE / 'integration.py')
module.__dict__['main']()
