# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
# Run: .venv/bin/python cold_verify.py <owned attempt directory>
import json
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
code = pytest.main(["tests/test_native_transport_error_contract.py", "tests/test_inference_providers.py", "tests/test_chat_structured_output_contract.py", "-q", "--junitxml=" + str(target / "junit.xml")])
(target / "socket-attempts.json").write_text(json.dumps({"attempts": attempts, "pytest_exit": code}, indent=2))
raise SystemExit(code)

