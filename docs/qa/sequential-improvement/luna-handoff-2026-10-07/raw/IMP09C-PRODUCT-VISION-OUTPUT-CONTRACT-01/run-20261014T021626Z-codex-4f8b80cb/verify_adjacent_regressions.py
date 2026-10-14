# /// script
# requires-python = ">=3.12"
# dependencies = ["pytest>=9,<10"]
# ///
# Run: .venv/bin/python -B verify_adjacent_regressions.py
from __future__ import annotations

import hashlib
import json
import os
import socket
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import NoReturn

RUN = Path(__file__).resolve().parent
ROOT = next(p for p in RUN.parents if (p / "pyproject.toml").is_file())
FILES = (
    "src/antigravity_k/api/routes/chat.py",
    "src/antigravity_k/engine/protocol_translator.py",
    "src/antigravity_k/engine/structured_output.py",
    "tests/test_chat_structured_output_contract.py",
    "pyproject.toml",
    "uv.lock",
)


def hashes() -> dict[str, str]:
    return {n: hashlib.sha256((ROOT / n).read_bytes()).hexdigest() for n in FILES}


def main() -> int:
    attempt = RUN / "adjacent-regressions"
    attempt.mkdir(exist_ok=False)
    os.environ.update(
        AGK_AUTO_DISCOVER_LOCAL_MODELS="false",
        AGK_ALLOWED_ROOTS=str(attempt),
        AGK_WORKSPACE_ROOT=str(attempt),
        VISION_CONTRACT_RUN_ROOT=str(attempt / "vision-captures"),
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
        PYTHONDONTWRITEBYTECODE="1",
    )
    import pytest

    attempts = 0

    def blocked[T](*_args: T, **_kwargs: T) -> NoReturn:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("Physical socket operation forbidden in adjacent offline regression")

    before = hashes()
    argv = [
        "-q",
        "-o",
        "addopts=",
        "-o",
        "testpaths=",
        "tests/test_protocol_translator.py",
        "tests/test_chat_vision_routing_contract.py",
        "--junitxml=" + str(attempt / "junit.xml"),
    ]
    with pytest.MonkeyPatch.context() as guard:
        for name in ("connect", "connect_ex", "bind", "listen"):
            guard.setattr(socket.socket, name, blocked)
        guard.setattr(socket, "create_connection", blocked)
        with (attempt / "stdout.txt").open("x", encoding="utf-8") as out:
            with (attempt / "stderr.txt").open("x", encoding="utf-8") as err:
                with redirect_stdout(out), redirect_stderr(err):
                    exit_code = int(pytest.main(argv))
    after = hashes()
    receipt = {
        "scope": "Adjacent existing protocol and vision regressions; not a replay of the new 36-case selector",
        "argv": argv,
        "cwd": str(ROOT),
        "exit_code": exit_code,
        "socket_attempts": attempts,
        "source_sha256_before": before,
        "source_sha256_after": after,
        "source_unchanged": before == after,
        "junit": "junit.xml",
        "stdout": "stdout.txt",
        "stderr": "stderr.txt",
    }
    with (attempt / "receipt.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"exit_code": exit_code, "socket_attempts": attempts, "source_unchanged": before == after}))
    return exit_code if exit_code else int(attempts != 0 or before != after)


if __name__ == "__main__":
    raise SystemExit(main())
