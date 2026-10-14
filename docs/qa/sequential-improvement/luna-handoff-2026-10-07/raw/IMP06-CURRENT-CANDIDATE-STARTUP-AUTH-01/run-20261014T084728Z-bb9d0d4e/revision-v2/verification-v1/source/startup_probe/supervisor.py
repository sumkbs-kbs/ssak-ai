# /// script
# requires-python = ">=3.12"
# dependencies = ["pydantic>=2", "anyio", "httpx"]
# ///
# After parent approval ONLY: python startup_supervisor.py approval.json
"""One bounded external startup/auth observation; never retry requests or attempts."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

import anyio
import httpx

from startup_probe.contract import (
    Access,
    Cleanup,
    GuardReceipt,
    Health,
    ProbeError,
    SourcePlan,
    Started,
    Token,
    child_environment,
    remaining,
    require_approval,
    verify_sources,
)
from startup_probe.lifecycle import Process, SystemOperations, own_spawned


async def request_bytes(
    port: int, method: str, path: str, timeout: float, body: bytes | None, token: str | None
) -> tuple[int, bytes]:
    """Enforce a wall-clock deadline over connect, headers, and every body fragment."""
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    with anyio.fail_after(timeout):
        async with httpx.AsyncClient(
            trust_env=False, follow_redirects=False, timeout=timeout, transport=httpx.AsyncHTTPTransport(retries=0)
        ) as client:
            async with client.stream(
                method, f"http://127.0.0.1:{port}{path}", content=body, headers=headers
            ) as response:
                chunks = bytearray()
                async for chunk in response.aiter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) > 1_000_000:
                        raise ProbeError("Response exceeds capture bound")
                return response.status_code, bytes(chunks)


def request(
    owned: Path,
    port: int,
    name: str,
    method: str,
    path: str,
    timeout: float,
    body: bytes | None = None,
    token: str | None = None,
) -> tuple[int, bytes]:
    """Record the attempt before one request; never redirect or retry."""
    (owned / (name + ".attempt.json")).write_text(
        json.dumps({"method": method, "path": path, "host": "127.0.0.1", "port": port, "retry_budget": 0})
    )
    status, raw = anyio.run(request_bytes, port, method, path, timeout, body, token)
    private = owned / "auth-private"
    (private / (name + ".response.bin")).write_bytes(raw)
    receipt = {
        "name": name,
        "method": method,
        "path": path,
        "status": status,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    (owned / (name + ".receipt.json")).write_text(json.dumps(receipt, indent=2))
    return status, raw


def main() -> None:
    base = Path(__file__).resolve().parent.parent
    plan_path = base / "plan.json"
    harness = [
        base / "startup_probe" / name
        for name in ("__init__.py", "contract.py", "guard.py", "entry.py", "supervisor.py", "lifecycle.py")
    ]
    require_approval(plan_path, Path(sys.argv[1]), harness)
    plan = SourcePlan.model_validate_json(plan_path.read_bytes())
    verify_sources(plan)
    observed_head = subprocess.check_output(
        ["/usr/bin/git", "-C", str(plan.candidate), "rev-parse", "HEAD"], text=True
    ).strip()
    if observed_head != plan.candidate_head:
        raise ProbeError("Candidate HEAD drift; a newly approved plan is required")
    owned = base / "live-once"
    owned.mkdir(mode=0o700)
    private = owned / "auth-private"
    private.mkdir(mode=0o700)
    for name in (
        "tmp",
        "cache",
        "project_root",
        "models_dir",
        "data_dir",
        "documents_dir",
        "vectors_dir",
        "logs_dir",
        "wiki_dir",
    ):
        (owned / name).mkdir()
    (owned / "config.yaml").write_text("{}\n")
    (owned / "empty.env").write_text("")
    pin = secrets.token_hex(24)
    (private / "pin.txt").write_text(pin)
    env = child_environment(os.environ, plan, owned, pin)
    env["PYTHONPATH"] = str(base) + os.pathsep + env["PYTHONPATH"]
    started_at = time.monotonic()
    deadline = started_at + plan.total_seconds
    token_value = ""
    ops = SystemOperations(base / "outer-terminal.json")

    def observe(child: Process) -> None:
        nonlocal token_value
        ops.write(
            owned / "launch.json",
            json.dumps(
                {
                    "pid": child.pid,
                    "pgid": child.pid,
                    "cwd": str(owned),
                    "python": str(plan.python),
                    "candidate_head": plan.candidate_head,
                    "lifespan": "on",
                },
                indent=2,
            ),
        )
        startup_deadline = min(started_at + plan.startup_seconds, deadline - plan.graceful_seconds - plan.kill_seconds)
        while not (owned / "started.json").exists():
            remaining(startup_deadline, time.monotonic(), 0.05)
            if child.poll() is not None:
                raise ProbeError("Child exited before startup completed")
            time.sleep(0.05)
        marker = Started.model_validate_json((owned / "started.json").read_bytes())
        if marker.pid != child.pid or marker.version != plan.app_version or marker.lifespan != "on":
            raise ProbeError("Startup marker mismatch")

        def timeout() -> float:
            return remaining(
                deadline - plan.graceful_seconds - plan.kill_seconds, time.monotonic(), plan.request_seconds
            )

        status, _ = request(owned, marker.port, "unauthenticated", "GET", "/api/system/access-mode", timeout())
        if status != 401:
            raise ProbeError("Protected route did not reject missing credentials")
        login_body = json.dumps({"pin": pin}).encode()
        (private / "login.request.bin").write_bytes(login_body)
        status, raw = request(owned, marker.port, "login", "POST", "/api/auth/login", timeout(), body=login_body)
        if status != 200:
            raise ProbeError("PIN login failed")
        token = Token.model_validate_json(raw)
        token_value = token.access_token
        if token.token_type != "bearer":
            raise ProbeError("Login token type mismatch")
        status, raw = request(
            owned, marker.port, "authenticated", "GET", "/api/system/access-mode", timeout(), token=token_value
        )
        access = Access.model_validate_json(raw)
        if status != 200 or not access.ok or access.mode != "full_access":
            raise ProbeError("Bearer access failed")
        status, raw = request(owned, marker.port, "health", "GET", "/v1/health", timeout(), token=token_value)
        health = Health.model_validate_json(raw)
        if status != 200 or health.status != "ok" or health.version != plan.app_version:
            raise ProbeError("Health contract failed")
        verify_sources(plan)

    def assess(observed: Cleanup) -> bool:
        for name in ("stdout.log", "stderr.log"):
            text = (private / name).read_text(errors="replace").replace(pin, "[REDACTED_PIN]")
            if token_value:
                text = text.replace(token_value, "[REDACTED_TOKEN]")
            ops.write(owned / name, text)
        credential_files = {}
        for name in ("pin-hash", "token-secret"):
            path = private / name
            credential_files[name] = {
                "exists": path.exists(),
                "bytes": path.stat().st_size if path.exists() else 0,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None,
            }
        ops.write(owned / "credential-file-status.json", json.dumps(credential_files, indent=2))
        ops.write(
            owned / "request-counts.json",
            json.dumps(
                {
                    "attempts": len(list(owned.glob("*.attempt.json"))),
                    "responses": len(list(owned.glob("*.receipt.json"))),
                    "private_excluded": "auth-private/**",
                },
                indent=2,
            ),
        )
        guard = GuardReceipt.model_validate_json((owned / "guard.json").read_bytes())
        stderr_text = (owned / "stderr.log").read_text()
        verify_sources(plan)
        return (
            observed.passed()
            and guard.violations == []
            and guard.model_calls == 0
            and guard.binds == 1
            and "Application shutdown complete" in stderr_text
            and all(
                (private / name).is_file() and (private / name).stat().st_size > 0
                for name in ("pin-hash", "token-secret")
            )
        )

    with (private / "stdout.log").open("wb") as stdout, (private / "stderr.log").open("wb") as stderr:
        child = subprocess.Popen(
            [str(plan.python), "-m", "startup_probe.entry", str(plan_path), str(owned)],
            cwd=owned,
            env=env,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
        )
        terminal = own_spawned(child, plan, owned, started_at, deadline, ops, observe, assess)
    if terminal.outcome != "PASS_SCOPED_EXTERNAL_UVICORN_AUTH_LIFESPAN_ON":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
