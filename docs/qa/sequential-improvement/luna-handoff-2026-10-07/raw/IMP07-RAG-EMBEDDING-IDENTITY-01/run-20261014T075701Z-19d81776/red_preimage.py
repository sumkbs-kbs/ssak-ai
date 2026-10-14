import os,sys,importlib.util
from pathlib import Path

def pytest_sessionstart(session):
    name=os.environ["RED_MODULE"]
    source=Path(os.environ["RED_SOURCE"])
    qualified="antigravity_k.engine."+name
    spec=importlib.util.spec_from_file_location(qualified,source)
    module=importlib.util.module_from_spec(spec)
    sys.modules[qualified]=module
    spec.loader.exec_module(module)
