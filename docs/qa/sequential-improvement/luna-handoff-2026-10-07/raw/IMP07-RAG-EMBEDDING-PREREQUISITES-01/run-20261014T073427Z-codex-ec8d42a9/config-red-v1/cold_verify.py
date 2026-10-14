# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
# Run: .venv/bin/python cold_verify.py <owned attempt directory>
import json
import os
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
for name in ["antigravity_k.engine.embeddings", "antigravity_k.engine.provider_adapters.embedding_providers", "antigravity_k.api.dependencies", "antigravity_k.api.routes.models_api", "antigravity_k.engine.model_registry"]:
    module = importlib.import_module(name)
    assert module.__file__ is not None, name
    source = Path(module.__file__).resolve()
    assert source.is_relative_to(root / "src"), (name, source)
    bindings[name] = str(source)
(target / "import-bindings.json").write_text(json.dumps(bindings, indent=2))
selectors = ["tests/test_model_registry_config_precedence.py"] if os.environ.get("CONFIG_RED") == "1" else ["tests/test_embeddings.py", "tests/test_embeddings_model_contract.py", "tests/test_models_system_api.py", "tests/test_ollama_embedding_routing.py", "tests/test_model_registry_config_precedence.py"]
code = pytest.main([*selectors, "-p", "pytest_asyncio.plugin", "-q", "--junitxml=" + str(target / "junit.xml")])
(target / "socket-attempts.json").write_text(json.dumps({"attempts": attempts, "pytest_exit": code}, indent=2))
raise SystemExit(code)

