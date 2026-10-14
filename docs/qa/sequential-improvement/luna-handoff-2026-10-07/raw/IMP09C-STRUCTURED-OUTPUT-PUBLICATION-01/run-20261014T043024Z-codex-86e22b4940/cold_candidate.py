# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
# Run using the root repository .venv/bin/python, with the candidate checkout as cwd.
import importlib
import json
import socket
import sys
from pathlib import Path

import pytest

candidate = Path.cwd().resolve()
evidence = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent
sys.path.insert(0, str(candidate / "src"))
attempts = []

def denied(*args, **kwargs):
    attempts.append(repr(args))
    raise AssertionError("Physical networking is forbidden in candidate verification")

socket.socket.connect = denied
socket.socket.connect_ex = denied
socket.create_connection = denied
bindings = {}
for name in ("antigravity_k.api.routes.chat", "antigravity_k.engine.protocol_translator", "antigravity_k.engine.structured_output", "antigravity_k.engine.model_manager", "antigravity_k.engine.provider_adapters.inference_providers"):
    module = importlib.import_module(name)
    assert module.__file__ is not None, name
    path = Path(module.__file__).resolve()
    assert path.is_relative_to(candidate / "src"), (name, path)
    bindings[name] = str(path)
(evidence / "import-bindings.json").write_text(json.dumps(bindings, indent=2))
code = pytest.main(["tests/test_chat_structured_output_contract.py", "tests/test_protocol_translator.py", "-q", "--junitxml=" + str(evidence / "junit.xml")])
(evidence / "socket-attempts.json").write_text(json.dumps({"physical_socket_attempts": attempts, "pytest_exit": code}, indent=2))
raise SystemExit(code)
