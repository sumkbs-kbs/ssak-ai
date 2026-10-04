#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
# How to run:
# Install uv if absent: curl -LsSf https://astral.sh/uv/install.sh | sh
# With this repository's already-installed dependencies:
# .venv/bin/python docs/qa/2026-10-03-oh-my-jev-upgrade/isolated_entry.py cli [ARGS]
# .venv/bin/python docs/qa/2026-10-03-oh-my-jev-upgrade/isolated_entry.py pytest [ARGS]
# .venv/bin/python docs/qa/2026-10-03-oh-my-jev-upgrade/isolated_entry.py http PORT
# uv run --active isolated_entry.py [MODE] [ARGS] also uses the project environment.

"""Run production entry points with a temporary home before any project import."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


def main() -> None:
    mode = sys.argv[1]
    arguments = sys.argv[2:]
    with TemporaryDirectory(prefix="ssak-jev-root-home-") as temporary_home:
        home = Path(temporary_home)
        os.environ["AGK_SEC_PIN_HASH_FILE"] = str(home / "auth-hash")
        os.environ["AGK_SEC_TOKEN_SECRET_FILE"] = str(home / "auth-secret")
        os.environ["AGK_SEC_ACCESS_PIN"] = "synthetic-local-qa-pin"
        os.environ["AGK_SEC_DEV_NO_PIN_ALLOW"] = "false"
        if mode != "pytest":
            os.environ["AGK_CONFIG_FILE"] = str(home / "absent-config.yaml")
        else:
            bootstrap = home / "python-bootstrap"
            bootstrap.mkdir()
            _ = shutil.copyfile(Path(__file__).with_name("subprocess_home.py"), bootstrap / "sitecustomize.py")
            os.environ["SSAK_JEV_QA_HOME"] = str(home)
            os.environ["UV_CACHE_DIR"] = str(home / "uv-cache")
            os.environ["PYTHONPATH"] = os.pathsep.join((str(bootstrap), os.environ.get("PYTHONPATH", "")))
        for setting in ("MODELS", "DATA", "DOCUMENTS", "VECTORS", "LOGS", "WIKI"):
            os.environ[f"AGK_PATH_{setting}_DIR"] = str(home / setting.lower())
        with patch.object(Path, "home", return_value=home):
            if mode == "cli":
                from antigravity_k.cli import app

                sys.argv = ["agk", *arguments]
                app()
            elif mode == "pytest":
                import pytest

                raise SystemExit(pytest.main(arguments))
            elif mode == "http":
                import uvicorn

                from antigravity_k.api.auth_routes import get_token_service
                from antigravity_k.api.server import app as server_app
                from antigravity_k.config import config

                config.server.host = "127.0.0.1"
                header = home / "request-header"
                _ = header.write_text(
                    "Authorization: Bearer " + get_token_service().issue_token("synthetic-evaluation-qa") + "\n",
                    encoding="utf-8",
                )
                header.chmod(0o600)
                print(f"QA_HEADER_FILE={header}", flush=True)
                uvicorn.run(
                    server_app,
                    host="127.0.0.1",
                    port=int(arguments[0]),
                    lifespan="off",
                    access_log=False,
                    log_level="warning",
                )
            else:
                raise SystemExit("Supported modes: cli, pytest, http")


if __name__ == "__main__":
    main()
