# /// script
# requires-python = ">=3.12"
# dependencies = ["uvicorn", "pydantic>=2"]
# ///
# Only the approved supervisor starts this entry: python startup_entry.py PLAN OWNED.
"""Genuine product lifespan and Uvicorn entry, with observation-only guards."""

from __future__ import annotations

import importlib.metadata
import json
import os
import socket
import sys
import threading
from pathlib import Path

import uvicorn

from startup_probe.contract import ProbeError, SourcePlan, Started, verify_sources
from startup_probe.guard import Guard


def main() -> None:
    plan = SourcePlan.model_validate_json(Path(sys.argv[1]).read_bytes())
    owned = Path(sys.argv[2]).resolve()
    verify_sources(plan)
    guard = Guard(owned)
    guard.install()
    try:
        from antigravity_k.api import server as product

        app_source = Path(product.__file__).resolve()
        if app_source != plan.candidate / "src/antigravity_k/api/server.py":
            raise ProbeError("Wrong product module imported")
        if product.app.version != plan.app_version:
            raise ProbeError("Product version drift")
        (owned / "runtime-metadata.json").write_text(
            json.dumps(
                {
                    "app_source": str(app_source),
                    "app_version": str(product.app.version),
                    "python": sys.executable,
                    "candidate_head": plan.candidate_head,
                    "versions": {
                        name: importlib.metadata.version(name)
                        for name in ("uvicorn", "fastapi", "python-dotenv", "pydantic")
                    },
                    "source_derived_rag_root": str(app_source.parents[3]),
                    "configured_project_root": str(product.config.paths.project_root),
                    "configured_data_dir": str(product.config.paths.data_dir),
                    "configured_vectors_dir": str(product.config.paths.vectors_dir),
                    "configured_pin_hash_file": product.config.security.pin_hash_file,
                    "configured_token_secret_file": product.config.security.token_secret_file,
                    "lifespan": "on",
                    "dependency_overrides": len(product.app.dependency_overrides),
                },
                indent=2,
            )
        )
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(128)
            port = listener.getsockname()[1]

            class ObservedServer(uvicorn.Server):
                async def startup(self, sockets: list[socket.socket] | None = None) -> None:
                    await super().startup(sockets=sockets)
                    if self.started:
                        marker = Started(
                            pid=os.getpid(),
                            port=port,
                            version=str(product.app.version),
                            app_source=app_source,
                            lifespan="on",
                        )
                        temporary = owned / "started.pending"
                        temporary.write_text(marker.model_dump_json(indent=2))
                        temporary.replace(owned / "started.json")

            config = uvicorn.Config(
                product.app,
                host="127.0.0.1",
                port=port,
                lifespan="on",
                loop="asyncio",
                http="h11",
                access_log=False,
                timeout_graceful_shutdown=8,
            )
            server = ObservedServer(config)
            watcher_stop = threading.Event()

            def watch_shutdown() -> None:
                while not watcher_stop.wait(0.05):
                    if (owned / "stop.requested").exists():
                        server.should_exit = True
                        return

            watcher = threading.Thread(target=watch_shutdown, name="owned-shutdown-watch", daemon=True)
            watcher.start()
            try:
                server.run(sockets=[listener])
            finally:
                watcher_stop.set()
                watcher.join(timeout=1)
            (owned / "child-complete.json").write_text('{"server_run_returned": true}')
    finally:
        guard.save()


if __name__ == "__main__":
    main()
