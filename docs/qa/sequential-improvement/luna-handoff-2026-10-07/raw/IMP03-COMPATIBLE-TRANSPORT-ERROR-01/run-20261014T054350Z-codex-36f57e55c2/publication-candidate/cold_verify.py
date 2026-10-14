# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
# Run: .venv/bin/python cold_verify.py <owned attempt directory>
import json
import importlib
import socket
import sys
from pathlib import Path

root = Path.cwd().resolve()
target = Path(sys.argv[1]).resolve()
sys.path[:0] = [str(root), str(root / "src")]
attempts = []
def denied(*args, **kwargs):
    attempts.append(repr(args))
    raise AssertionError("No physical socket operation permitted")
socket.socket.connect = denied
socket.socket.connect_ex = denied
socket.socket.bind = denied
socket.socket.listen = denied
socket.create_connection = denied
import pytest
bindings = {}
for name in ["antigravity_k.api.routes.chat", "antigravity_k.api.routes.messages_api", "antigravity_k.engine.protocol_translator", "antigravity_k.engine.model_manager", "antigravity_k.engine.provider_adapters.inference_providers", "antigravity_k.tools.egress_policy"]:
    module = importlib.import_module(name)
    assert module.__file__ is not None, name
    source = Path(module.__file__).resolve()
    assert source.is_relative_to(root / "src"), (name, source)
    bindings[name] = str(source)
(target / "import-bindings.json").write_text(json.dumps(bindings, indent=2))
code = pytest.main(["tests/test_compatible_transport_error_contract.py", "tests/test_native_stream_terminal_contract.py", "tests/test_native_transport_error_contract.py", "tests/test_inference_providers.py", "-p", "pytest_asyncio.plugin", "-q", "--junitxml=" + str(target / "junit.xml")])
(target / "socket-attempts.json").write_text(json.dumps({"attempts": attempts, "pytest_exit": code}, indent=2))
raise SystemExit(code)

