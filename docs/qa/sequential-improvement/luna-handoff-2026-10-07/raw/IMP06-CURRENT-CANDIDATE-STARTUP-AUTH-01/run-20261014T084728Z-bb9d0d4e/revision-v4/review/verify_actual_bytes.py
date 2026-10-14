from __future__ import annotations

import hashlib
import json
from pathlib import Path
from pydantic import BaseModel, TypeAdapter

class Entry(BaseModel):
    bytes: int
    sha256: str

class Manifest(BaseModel):
    files: dict[str, Entry]

class Plan(BaseModel):
    candidate: Path
    candidate_head: str
    source_hashes: dict[str, str]

class RequestReceipt(BaseModel):
    status: int
    bytes: int
    sha256: str

class LoginRequest(BaseModel):
    pin: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str

class AccessResponse(BaseModel):
    ok: bool
    mode: str

class HealthResponse(BaseModel):
    status: str
    version: str

def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def main() -> None:
    base = Path(__file__).resolve().parent.parent
    manifest = Manifest.model_validate_json((base / "final-live-manifest.json").read_bytes())
    for name, row in manifest.files.items():
        path = (base / name).resolve()
        assert path.is_relative_to(base.resolve()) and "auth-private" not in path.parts
        raw = path.read_bytes()
        assert len(raw) == row.bytes and digest(raw) == row.sha256, name
    plan = Plan.model_validate_json((base / "plan.json").read_bytes())
    for name, sha in plan.source_hashes.items():
        assert digest((plan.candidate / name).read_bytes()) == sha, name
    live = base / "live-once"
    private = live / "auth-private"
    statuses: list[int] = []
    for name in ("unauthenticated", "login", "authenticated", "health"):
        receipt = RequestReceipt.model_validate_json((live / (name + ".receipt.json")).read_bytes())
        raw = (private / (name + ".response.bin")).read_bytes()
        assert len(raw) == receipt.bytes and digest(raw) == receipt.sha256
        statuses.append(receipt.status)
    assert statuses == [401, 200, 200, 200]
    login = LoginRequest.model_validate_json((private / "login.request.bin").read_bytes())
    assert login.pin == (private / "pin.txt").read_text()
    token = LoginResponse.model_validate_json((private / "login.response.bin").read_bytes())
    assert token.access_token and token.token_type == "bearer"
    access = AccessResponse.model_validate_json((private / "authenticated.response.bin").read_bytes())
    health = HealthResponse.model_validate_json((private / "health.response.bin").read_bytes())
    assert access.ok and access.mode == "full_access" and health.status == "ok" and health.version == "0.1.0"
    result = TypeAdapter(dict[str, object]).validate_json((live / "result.json").read_bytes())
    guard = TypeAdapter(dict[str, object]).validate_json((live / "guard.json").read_bytes())
    assert result["outcome"] == "PASS_SCOPED_EXTERNAL_UVICORN_AUTH_LIFESPAN_ON"
    assert guard["violations"] == [] and guard["binds"] == 1 and guard["model_calls"] == 0
    cleanup = TypeAdapter(dict[str, object]).validate_python(result["cleanup"])
    observed = TypeAdapter(dict[str, object]).validate_python(cleanup["observed"])
    assert observed == {"exit_code": 0, "reaped": True, "group_empty": True, "forced": False}
    print(json.dumps({"scope": "main-session byte-only verification; no backend/native/HTTP replay", "public_manifest_entries": len(manifest.files), "candidate_sources": len(plan.source_hashes), "candidate": plan.candidate_head, "http_statuses": statuses, "private_schema_pin_match": True, "credential_values_exported": False, "cleanup_verified": True, "guard_violations": 0, "model_calls": 0}))
if __name__ == "__main__":
    main()
