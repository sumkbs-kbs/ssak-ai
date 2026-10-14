from __future__ import annotations
import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from startup_probe.guard import Guard
root=Path(sys.argv[2]).resolve()
guard=Guard(root);guard.install()
import pytest
try:
    code=pytest.main(sys.argv[3:])
finally:
    guard.save()
sys.exit(code)

