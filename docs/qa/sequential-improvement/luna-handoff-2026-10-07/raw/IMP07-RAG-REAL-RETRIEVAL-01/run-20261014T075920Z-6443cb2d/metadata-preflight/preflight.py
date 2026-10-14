# /// script
# requires-python = ">=3.13"
# dependencies = ["httpx"]
# ///
# How to run: node supervisor.mjs; uses installed dependencies without installation.
"""Exactly four local metadata requests; no inference or model mutation."""

import json
from pathlib import Path
import time

import httpx

output = Path(__file__).resolve().parent
requests = (
    ("version", "GET", "/api/version", None),
    ("tags", "GET", "/api/tags", None),
    ("show", "POST", "/api/show", {"model": "nomic-embed-text:latest"}),
    ("ps", "GET", "/api/ps", None),
)
with httpx.Client(
    trust_env=False,
    follow_redirects=False,
    timeout=httpx.Timeout(10.0),
    transport=httpx.HTTPTransport(retries=0, trust_env=False),
) as client:
    for label, method, endpoint, body in requests:
        started = time.time()
        receipt = {"label": label, "method": method, "url": "http://127.0.0.1:11434" + endpoint, "body": body, "started": started}
        try:
            response = client.request(method, str(receipt["url"]), json=body)
            (output / f"{label}.response.bin").write_bytes(response.content)
            receipt.update({"status": response.status_code, "headers": dict(response.headers), "raw_file": f"{label}.response.bin", "error": None})
        except httpx.HTTPError as error:
            receipt.update({"status": None, "error": {"type": type(error).__name__, "message": str(error)}})
        receipt.update({"ended": time.time(), "elapsed_seconds": time.time() - started})
        with (output / "requests.jsonl").open("a", encoding="utf-8") as log:
            log.write(json.dumps(receipt) + "\n")
        print(json.dumps(receipt), flush=True)
