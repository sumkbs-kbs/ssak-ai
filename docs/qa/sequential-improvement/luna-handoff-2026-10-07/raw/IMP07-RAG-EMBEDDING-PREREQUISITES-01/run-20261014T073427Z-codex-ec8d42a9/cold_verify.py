# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
# Run: .venv/bin/python cold_verify.py <owned attempt directory>
import json
import os
import importlib
from contextlib import asynccontextmanager
from types import ModuleType
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
model_attempts = []
def denied_model(*args, **kwargs):
    model_attempts.append(repr(args))
    raise AssertionError("Model loading is prohibited")
module_stub = ModuleType("sentence_transformers")
module_stub.SentenceTransformer = denied_model
sys.modules["sentence_transformers"] = module_stub
import pytest
bindings = {}
for name in ["antigravity_k.engine.embeddings", "antigravity_k.engine.provider_adapters.embedding_providers", "antigravity_k.api.dependencies", "antigravity_k.api.routes.models_api", "antigravity_k.engine.model_registry"]:
    module = importlib.import_module(name)
    assert module.__file__ is not None, name
    source = Path(module.__file__).resolve()
    assert source.is_relative_to(root / "src"), (name, source)
    bindings[name] = str(source)
(target / "import-bindings.json").write_text(json.dumps(bindings, indent=2))
from antigravity_k.api.server import app
@asynccontextmanager
async def offline_lifespan(app):
    yield
app.router.lifespan_context = offline_lifespan
selectors = ["tests/test_model_registry_config_precedence.py"] if os.environ.get("CONFIG_RED") == "1" else ["tests/test_embeddings.py", "tests/test_embeddings_model_contract.py", "tests/test_models_system_api.py", "tests/test_ollama_embedding_routing.py", "tests/test_model_registry_config_precedence.py", "tests/cognitive/test_r15_composition.py::test_r15_boot_attach_never_installs_active"]
code = pytest.main([*selectors, "-p", "pytest_asyncio.plugin", "-q", "--junitxml=" + str(target / "junit.xml")])
(target / "socket-attempts.json").write_text(json.dumps({"attempts": attempts, "pytest_exit": code, "model_attempts": model_attempts, "lifespan": "offline_noop_fixture"}, indent=2))
raise SystemExit(code)

