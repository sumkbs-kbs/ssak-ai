import sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from startup_probe.guard import Guard
root=Path(sys.argv[2]).resolve();guard=Guard(root);guard.install()
import pytest
class OwnedWorkspace:
    @pytest.hookimpl(wrapper=True)
    def pytest_fixture_setup(self,fixturedef,request):
        result=yield
        if fixturedef.argname=="mock_orch":
            result.project_root=str(root/"project_root")
        return result
try:code=pytest.main(sys.argv[3:],plugins=[OwnedWorkspace()])
finally:guard.save()
sys.exit(code)

