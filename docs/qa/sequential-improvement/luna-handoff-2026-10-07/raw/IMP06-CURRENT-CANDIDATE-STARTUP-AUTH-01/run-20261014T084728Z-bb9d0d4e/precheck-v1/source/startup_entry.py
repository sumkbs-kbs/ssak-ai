# /// script
# requires-python = ">=3.12"
# dependencies = ["uvicorn", "pydantic>=2"]
# ///
# Only the approved supervisor starts this entry: python startup_entry.py PLAN OWNED.
"""Genuine product lifespan and Uvicorn entry, with observation-only guards."""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

import uvicorn

from startup_contract import ProbeError, SourcePlan, Started, verify_sources
from startup_guard import Guard


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
                        (owned / "started.json").write_text(marker.model_dump_json(indent=2))

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
            server.run(sockets=[listener])
            (owned / "child-complete.json").write_text('{"server_run_returned": true}')
    finally:
        guard.save()


if __name__ == "__main__":
    main()
