from __future__ import annotations

"""One-shot product-vision supervisor contract.

The executable default remains offline-only. The concrete runtime factory is
reachable only after separate multi-field live authorization and independent
review, or an explicitly injected OFFLINE_MOCK loader. Both use the identical
supervise_once state machine and durable journal; this preparation grants no live authority.
"""

import base64
import binascii
import fcntl
import hashlib
import importlib
import json
import os
import re
import socket
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.parse import urlsplit

TASK_ID = "IMP-09-C-PRODUCT-VISION-FINAL-GATE-CLOSEOUT-01"
NEXT_REVIEW = "CODEX_REVIEW_IMP-09-C-PRODUCT-VISION-FINAL-GATE-CLOSEOUT-01"
PREPARATION_TASK_ID = "IMP-09-C-PRODUCT-VISION-RUNTIME-COMPATIBILITY-01"
FUTURE_TASK_ID = "IMP-09-B-PRODUCT-VISION-LIVE-OBSERVATION-01"
MODEL_ALIAS = "qwen3.8"
MODEL_REPO = "qwen3.8:latest"
APPROVED_MODEL_DIGEST = "22130167c4c20e20c7b71454612966ca8e8171e9b3cc8ab6ce8aa6cbfec79643"
PROMPT_PREFIX = "/offline-vision-contract-probe "
QUESTION = (
    "Count the visible shapes in the attached image. Return only one JSON object with keys red_circles and "
    "blue_squares, whose values are integers. Do not include explanations."
)
EXPECTED_COUNTS = {"red_circles": 2, "blue_squares": 1}
IMAGE_SHA256 = "f51d7d266d67b6458916a32ef610c83feddbacbfad72146bf94e29e7cf077098"
B64_SHA256 = "b37f9f02d1ad805f5004cc78ce9f5fd2da0a2780fbe6a2af591d57cd18abee31"
IMAGE_BYTES = 1338
IMAGE_SIZE = (384, 256)
TOTAL_DEADLINE_SECONDS = 120
READINESS_DEADLINE_SECONDS = 15
GRACEFUL_CLEANUP_SECONDS = 5
THINK_POLICY = "actual provider source emits think=false; any drift is a protocol failure"
FORMAT_POLICY = "actual provider source omits format absent response_format; format must remain absent"
PROVIDER_ORIGIN_EXPECTATION = "http://localhost:11434"
PROVIDER_ORIGIN_POLICY = "http:// loopback port 11434; exact host spellings localhost and 127.0.0.1 compare as 127.0.0.1; preserve request URL bytes"
SOURCE_EXPECTATIONS: dict[str, str] = {
    "src/antigravity_k/api/routes/chat.py": "21c07609c0fbd5d5cbe15f2704e56c5bb9cba9d7ec7b089af1780183b9e6cbe1",
    "src/antigravity_k/engine/conversation_store.py": "98dcbe3890dc4e1481ae2fa5a35cefeea328925a5d61e7572e60cb749c2db496",
    "src/antigravity_k/engine/protocol_translator.py": "891144e6311bac6764e9f139cd235ce5e706ad00abc179e2c238266668af500e",
    "src/antigravity_k/engine/model_manager.py": "cf0867a8b8a934eddfad3ffcfc204781089f5960e30765c8cba6c26802bf1b7a",
    "src/antigravity_k/engine/provider_adapters/inference_providers.py": "a23ce7e0f6a0f3e65d25831f7a1bd92b2dc1ddea9e18264a67c80eae7d619c1a",
    "src/antigravity_k/api/server.py": "2cf6b4e5808b3228878ddd7da07c864c80c223d503963a842e3daa9fef3379fb",
    "src/antigravity_k/api/dependencies.py": "64bcea9f345cce3ba85da4329bc83443720621b24e3ff6f0061adda0440eb1de",
    "src/antigravity_k/config.py": "6721ba3d22f9eb9ce509caf06fcca966f4605f3134d2c4a249aceea803549346",
    "src/antigravity_k/engine/project_registry.py": "f97c4d2f04f45dc7a8ca545aac05d24ce1fe445c4e4230f149c4a5b8e882df18",
    "src/antigravity_k/engine/model_registry.py": "8febe07ec3e0b00c87b83afd31475727c893885c97f760aadcf3f1409e0e6bda",
    "src/antigravity_k/api/project_binding.py": "a73892bc1027d88b38aa4fc2ac2bc9cbb502941e8a208611b080326bf93697c7",
    "src/antigravity_k/api/auth_routes.py": "280327194371a88baa7cc7c3840f400357014060571203a27a6352fdd469e46c",
    "src/antigravity_k/engine/session_manager.py": "a6fefeaba5d6c62d6bde13fa696987835925cd61bda59a6f8937598bf4720e22",
    "src/antigravity_k/engine/usage_tracker.py": "66ac28231d2e852a99f62cfd39273846d2475bb32ecbc522499da02b0640a2de",
    "src/antigravity_k/engine/audit_logger.py": "a9000330a45a647a981615ea0bf8124295215221b4b324260054bc9dcef24f41",
    "tests/test_chat_vision_routing_contract.py": "558857bb7a8b9a6a21f55d5d6552b4cdc6f90e2df2001732208c7bb83c85138c",
    "tests/fixtures/vision_shapes_384x256.png.b64": "b37f9f02d1ad805f5004cc78ce9f5fd2da0a2780fbe6a2af591d57cd18abee31",
    "config.yaml": "3948867a6b9ef51fc392e07d0015c45b7f881095942c4cbf64c503fdc08d8025",
}
IMPLEMENTATION_SOURCE_NAMES = (
    "run_harness.py",
    "runtime_adapter.py",
    "test_runtime_bridge_contract.py",
    "test_runtime_compatibility_contract.py",
    "run_offline_prechecks.py",
    "test_runtime_final_gate_contract.py",
)
EXECUTION_BINDING_SCHEMA_VERSION = 2
EXECUTION_BINDING_ATTEMPT_ID = "codex-final-gate-candidate-2"
ADDITIONAL_RUNTIME_SOURCES = {
    "src/antigravity_k/api/routes/system_api.py": "610334086c50b0b0e0ff09b57d3ae45e7b46739be8316baa7627ade67d35c7a6",
    "src/antigravity_k/api/auth_policy.py": "d99b35ca9a6ab458d1bf70879b92b1591d765cd09cc80e2d91e72bb46e69ef8c",
    "src/antigravity_k/tools/egress_policy.py": "c1b36445d9e906b1cb8b999bd772bf58d83b29d766d396fc1e0698f5d991a699",
}
BUDGETS = {
    "ollama_get_version_preflight": 1,
    "ollama_get_tags_preflight": 1,
    "ollama_get_ps_preflight": 1,
    "ollama_post_show_preflight": 1,
    "ollama_get_ps_postflight": 1,
    "product_internal_capability_show": 2,
    "product_authenticated_chat_post": 1,
    "ollama_chat_inference_wire": 1,
    "retry_wire": 0,
    "redirect_follow_wire": 0,
    "native_inference_wire": 0,
    "tool_execution": 0,
}
REQUIRED_GATES = (
    "source_request_authorization",
    "auth_unauthorized_401",
    "auth_bearer_200",
    "readiness",
    "model_version_tags_show_digest_capability",
    "product_status_content_type",
    "upstream_status_done_content_type",
    "input_options_think_format",
    "raw_response_equality",
    "semantic_counts",
    "accounting_lineage",
    "no_retry_redirect_native_tool",
    "cleanup_owned_exit",
    "protected_before_after",
    "execution_binding_immutable",
    "deadline_stage_contract",
    "postflight_deadline",
    "cleanup_deadline",
)
EXPECTED_UPSTREAM_SYSTEM = (
    "/no_think\nAnswer directly. Do not output hidden reasoning, thinking traces, <think>, or <thought> blocks."
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def strict_json_loads(data: str | bytes) -> object:
    return json.loads(
        data,
        object_pairs_hook=unique_json_object,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"invalid JSON constant {value}")),
    )


def parse_counts_strict(content: str) -> tuple[bool, str]:
    try:
        value = strict_json_loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        return False, f"invalid_json:{type(exc).__name__}"
    if not isinstance(value, dict) or set(value) != set(EXPECTED_COUNTS):
        return False, "expected_exact_count_object"
    if any(type(value[key]) is not int for key in EXPECTED_COUNTS):
        return False, "counts_must_be_strict_integers"
    if value != EXPECTED_COUNTS:
        return False, "count_mismatch"
    return True, "exact_counts_match"


def load_image(run: Path) -> tuple[bytes, str]:
    raw = (run / "fixture/vision_shapes_384x256.png.b64").read_bytes()
    if sha256(raw) != B64_SHA256:
        raise ValueError("approved b64 fixture source digest drift")
    encoded = raw.strip()
    try:
        image = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("approved b64 fixture is invalid") from exc
    if len(image) != IMAGE_BYTES or sha256(image) != IMAGE_SHA256:
        raise ValueError("decoded approved image bytes drift")
    if image[:8] != b"\x89PNG\r\n\x1a\n" or image[12:16] != b"IHDR" or struct.unpack(">II", image[16:24]) != IMAGE_SIZE:
        raise ValueError("approved PNG type/dimensions drift")
    return image, encoded.decode("ascii")


def build_request(project_id: str, encoded_image: str) -> dict[str, object]:
    if not isinstance(project_id, str) or re.fullmatch(r"proj_[0-9a-f]{8}", project_id) is None:
        raise ValueError("request project_id must be the isolated registry's actual id")
    try:
        image = base64.b64decode(encoded_image, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("request image is invalid base64") from exc
    if sha256(image) != IMAGE_SHA256 or len(image) != IMAGE_BYTES:
        raise ValueError("request image does not match approved image")
    return {
        "model": MODEL_ALIAS,
        "stream": False,
        "agent_mode": False,
        "plan_mode": False,
        "tdd_mode": False,
        "web_search": False,
        "max_tokens": 128,
        "temperature": 0,
        "project_id": project_id,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT_PREFIX + QUESTION},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64," + encoded_image}},
                ],
            }
        ],
    }


def accept_product_request(value: object, image: bytes) -> dict[str, object]:
    checks: dict[str, bool] = {}
    if not isinstance(value, dict):
        return {"checks": {"object": False}, "pass": False}
    request = cast(dict[str, object], value)
    checks["exact_request_keys"] = set(request) == {
        "model",
        "stream",
        "agent_mode",
        "plan_mode",
        "tdd_mode",
        "web_search",
        "max_tokens",
        "temperature",
        "project_id",
        "messages",
    }
    checks["registered_alias"] = request.get("model") == MODEL_ALIAS and type(request.get("model")) is str
    flags: dict[str, object] = {
        "stream": False,
        "agent_mode": False,
        "plan_mode": False,
        "tdd_mode": False,
        "web_search": False,
        "max_tokens": 128,
        "temperature": 0,
    }
    checks["fixed_options_exact_types"] = all(
        request.get(key) == expected and type(request.get(key)) is type(expected) for key, expected in flags.items()
    )
    messages = request.get("messages")
    messages_list = cast(list[object], messages) if isinstance(messages, list) else []
    checks["one_user_message"] = (
        isinstance(messages, list) and len(messages_list) == 1 and isinstance(messages_list[0], dict)
    )
    decoded = b""
    if checks["one_user_message"]:
        message = cast(dict[str, object], messages_list[0])
        checks["exact_message_shape"] = set(message) == {"role", "content"} and message.get("role") == "user"
        parts = message.get("content")
        parts_list = cast(list[object], parts) if isinstance(parts, list) else []
        checks["exact_text_then_image_parts"] = isinstance(parts, list) and len(parts_list) == 2
        if checks["exact_text_then_image_parts"]:
            text_part, image_part = parts_list
            checks["text_part_exact"] = (
                isinstance(text_part, dict)
                and set(text_part) == {"type", "text"}
                and text_part.get("type") == "text"
                and text_part.get("text") == PROMPT_PREFIX + QUESTION
            )
            url = None
            if (
                isinstance(image_part, dict)
                and set(image_part) == {"type", "image_url"}
                and image_part.get("type") == "image_url"
            ):
                img_obj = image_part.get("image_url")
                if isinstance(img_obj, dict) and set(img_obj) == {"url"}:
                    url = img_obj.get("url")
            if isinstance(url, str) and url.startswith("data:image/png;base64,"):
                try:
                    decoded = base64.b64decode(url.removeprefix("data:image/png;base64,"), validate=True)
                except (ValueError, binascii.Error):
                    decoded = b""
            checks["single_exact_png_part"] = bool(decoded) and decoded == image and sha256(decoded) == IMAGE_SHA256
        else:
            checks["text_part_exact"] = False
            checks["single_exact_png_part"] = False
    else:
        checks.update(
            {
                "exact_message_shape": False,
                "exact_text_then_image_parts": False,
                "text_part_exact": False,
                "single_exact_png_part": False,
            }
        )
    project_id = request.get("project_id")
    checks["isolated_project_id"] = (
        isinstance(project_id, str) and re.fullmatch(r"proj_[0-9a-f]{8}", project_id) is not None
    )
    result: dict[str, object] = {
        "checks": checks,
        "pass": all(checks.values()),
        "image_sha256": sha256(decoded) if decoded else None,
    }
    return result


def canonical_provider_origin(url: str) -> str:
    """Normalize an origin or provider URL under the exact two-host Ollama contract."""
    parsed = urlsplit(url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid provider URL port") from exc
    if (
        parsed.scheme != "http"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port != 11434
        or parsed.netloc not in {"localhost:11434", "127.0.0.1:11434"}
    ):
        raise ValueError("origin outside frozen localhost/127.0.0.1:11434 HTTP contract")
    return "http://127.0.0.1:11434"


def classify_upstream_request(
    url: str, method: str, body: bytes, *, expected_origin: str = PROVIDER_ORIGIN_EXPECTATION
) -> str:
    parsed = urlsplit(url)
    if (
        canonical_provider_origin(expected_origin) != canonical_provider_origin(url)
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("provider request origin is not the frozen local Ollama origin")
    if method != "POST" or parsed.path != "/api/chat":
        raise ValueError("only the product's one /api/chat inference may reach provider wire")
    try:
        payload_obj = strict_json_loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise ValueError("provider body is not strict JSON") from exc
    if not isinstance(payload_obj, dict):
        raise ValueError("provider body must be an object")
    payload = cast(dict[str, object], payload_obj)
    if set(payload) != {"model", "stream", "keep_alive", "think", "options", "messages"}:
        raise ValueError("provider payload keys differ from the bound native request shape")
    if (
        payload.get("model") != MODEL_ALIAS
        or type(payload.get("model")) is not str
        or payload.get("stream") is not False
        or type(payload.get("stream")) is not bool
    ):
        raise ValueError("provider model or stream differs from fixed profile")
    if payload.get("think") is not False or type(payload.get("think")) is not bool:
        raise ValueError("provider think must remain explicit false")
    if payload.get("keep_alive") != "30m" or type(payload.get("keep_alive")) is not str:
        raise ValueError("provider keep_alive differs from source-bound default")
    if "format" in payload or "tools" in payload:
        raise ValueError("format/tools are forbidden for this vision observation")
    options = payload.get("options")
    if (
        not isinstance(options, dict)
        or not {"num_ctx", "num_predict", "temperature", "repeat_penalty", "min_p"}.issubset(options)
        or set(options) - {"num_ctx", "num_predict", "temperature", "repeat_penalty", "min_p"}
    ):
        raise ValueError("provider options do not match the currently source-bound Ollama builder")
    if type(options.get("num_predict")) is not int or options.get("num_predict") != 128:
        raise ValueError("provider num_predict must be strict integer 128")
    temperature = options.get("temperature")
    if type(temperature) not in {int, float} or temperature != 0:
        raise ValueError("provider temperature must be numeric zero, not bool")
    if type(options.get("num_ctx")) is not int or options.get("num_ctx") != 32768:
        raise ValueError("provider num_ctx must be the source-bound strict integer 32768")
    if type(options.get("repeat_penalty")) not in {int, float} or options.get("repeat_penalty") != 1.0:
        raise ValueError("provider repeat_penalty differs from the frozen profile")
    if type(options.get("min_p")) not in {int, float} or options.get("min_p") != 0.0:
        raise ValueError("provider min_p differs from the frozen profile")
    messages = payload.get("messages")
    if not isinstance(messages, list):
        raise ValueError("provider messages must be an array")
    allowed = ["system", "user"] if len(messages) == 2 else ["user"]
    if [m.get("role") if isinstance(m, dict) else None for m in messages] != allowed:
        raise ValueError("provider must carry exactly one source-bound optional system and one user")
    user = cast(dict[str, object], messages[-1])
    if (
        set(user) != {"role", "content", "images"}
        or type(user.get("content")) is not str
        or user.get("content") != PROMPT_PREFIX + QUESTION
    ):
        raise ValueError("provider user text/shape differs from frozen product question")
    images = user.get("images")
    if not isinstance(images, list) or len(images) != 1 or type(images[0]) is not str:
        raise ValueError("provider must receive exactly one image on the same user message")
    try:
        image = base64.b64decode(images[0], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("provider image is invalid base64") from exc
    if len(image) != IMAGE_BYTES or sha256(image) != IMAGE_SHA256:
        raise ValueError("provider image bytes differ from frozen PNG")
    if len(messages) == 2:
        system = cast(dict[str, object], messages[0])
        if set(system) != {"role", "content"} or system.get("content") != EXPECTED_UPSTREAM_SYSTEM:
            raise ValueError("provider system message differs from source-bound no-think directive")
    return "ollama_chat_inference_wire"


def resolve_repository_root(start: Path | None = None) -> Path:
    origin = (start or Path(__file__).resolve()).resolve()
    for candidate in (origin, *origin.parents):
        if candidate.name == "Ssak-Ai" and (candidate / "src/antigravity_k").is_dir():
            return candidate
    raise RuntimeError("could not resolve explicit Ssak-Ai repository root")


def source_snapshot(root: Path) -> dict[str, object]:
    actual: dict[str, str] = {}
    drift: list[dict[str, object]] = []
    for rel, expected in {**SOURCE_EXPECTATIONS, **ADDITIONAL_RUNTIME_SOURCES}.items():
        path = root / rel
        got = sha256(path.read_bytes()) if path.is_file() else None
        if got is not None:
            actual[rel] = got
        if got != expected:
            drift.append({"path": rel, "expected": expected, "actual": got})
    return {
        "actual": actual,
        "expected": {**SOURCE_EXPECTATIONS, **ADDITIONAL_RUNTIME_SOURCES},
        "drift": drift,
        "ready": not drift,
    }


def request_gate(run: Path, root: Path, *, expected_request_sha256: str | None = None) -> dict[str, object]:
    binding, binding_raw, implementation_sources = validate_execution_binding(run, root)
    image, _ = load_image(run)
    raw = (run / "request.json").read_bytes()
    if expected_request_sha256 is not None and sha256(raw) != expected_request_sha256:
        raise ValueError("frozen request hash drift")
    request_obj = strict_json_loads(raw)
    if not isinstance(request_obj, dict):
        raise ValueError("frozen request must be a JSON object")
    request = cast(dict[str, object], request_obj)
    result = accept_product_request(request, image)
    source = source_snapshot(root)
    if source["ready"] is not True:
        raise ValueError("INCONCLUSIVE_SOURCE_DRIFT")
    if result["pass"] is not True:
        raise ValueError("fixed product request rejected")
    request_binding, request_binding_raw = read_request_binding(run)
    if request_binding.get("task_id") not in {TASK_ID, PREPARATION_TASK_ID} or request_binding.get(
        "request_sha256"
    ) != sha256(raw):
        raise ValueError("task request binding identity/hash mismatch")
    if (
        request_binding.get("project_id") != request.get("project_id")
        or request_binding.get("fixture_b64_sha256") != B64_SHA256
        or request_binding.get("fixture_png_sha256") != IMAGE_SHA256
        or request_binding.get("question") != QUESTION
    ):
        raise ValueError("task request binding scope differs from frozen request")
    registry_path = (run / str(request_binding.get("project_registry_path", ""))).resolve()
    workspace_path = (run / str(request_binding.get("project_workspace", ""))).resolve()
    if (
        registry_path == run.resolve()
        or run.resolve() not in registry_path.parents
        or run.resolve() not in workspace_path.parents
        or not registry_path.is_file()
        or not workspace_path.is_dir()
    ):
        raise ValueError("isolated request registry/workspace is missing or escapes owned run")
    if binding.get("request_binding_sha256") != sha256(request_binding_raw):
        raise ValueError("INCONCLUSIVE_SOURCE_DRIFT: request binding changed during validation")

    records = strict_json_loads(registry_path.read_bytes())
    matches = (
        [item for item in records if isinstance(item, dict) and item.get("id") == request.get("project_id")]
        if isinstance(records, list)
        else []
    )
    if len(matches) != 1 or Path(str(matches[0].get("path", ""))).resolve() != workspace_path.resolve():
        raise ValueError("request project ID is not issued by its bound isolated registry")
    return {
        "request": request,
        "request_raw": raw,
        "request_sha256": sha256(raw),
        "image": image,
        "source": source,
        "harness_sha256": implementation_sources["run_harness.py"],
        "execution_binding": binding,
        "execution_binding_raw": binding_raw,
        "execution_binding_sha256": sha256(binding_raw),
        "execution_binding_id": sha256(binding_raw)[:24],
        "binding_path": run / "execution-binding.json",
    }


def read_request_binding(run: Path) -> tuple[dict[str, object], bytes]:
    path = run / "request.binding.json"
    raw = path.read_bytes()
    obj = strict_json_loads(raw)
    if not isinstance(obj, dict):
        raise ValueError("request binding must be an object")
    return cast(dict[str, object], obj), raw


def expected_execution_binding(
    run: Path,
    root: Path,
    request_raw: bytes,
    request_binding_raw: bytes,
) -> tuple[dict[str, object], dict[str, str]]:
    request_obj = strict_json_loads(request_raw)
    request_binding_obj = strict_json_loads(request_binding_raw)
    if not isinstance(request_obj, dict) or not isinstance(request_binding_obj, dict):
        raise ValueError("INCONCLUSIVE_SOURCE_DRIFT: request binding inputs must be JSON objects")
    if run.resolve() not in (run / "endpoint-contract.json").resolve().parents:
        raise ValueError("INCONCLUSIVE_SOURCE_DRIFT: endpoint contract escapes owned run")
    source = source_snapshot(root)
    if source.get("ready") is not True:
        raise ValueError("INCONCLUSIVE_SOURCE_DRIFT: protected product source drift")
    implementation = {
        name: sha256((run / name).read_bytes()) if (run / name).is_file() else None
        for name in IMPLEMENTATION_SOURCE_NAMES
    }
    if any(value is None for value in implementation.values()):
        raise ValueError("INCONCLUSIVE_SOURCE_DRIFT: implementation source missing")

    request = cast(dict[str, object], request_obj)
    request_binding = cast(dict[str, object], request_binding_obj)
    expected = {
        "schema_version": EXECUTION_BINDING_SCHEMA_VERSION,
        "task_id": TASK_ID,
        "preparation_task_id": PREPARATION_TASK_ID,
        "run_id": run.name,
        "attempt_id": EXECUTION_BINDING_ATTEMPT_ID,
        "candidate_binding_sha256": sha256(canonical_json(implementation)),
        "request_sha256": sha256(request_raw),
        "request_binding_sha256": sha256(request_binding_raw),
        "endpoint_contract_sha256": sha256((run / "endpoint-contract.json").read_bytes()),
        "origin_contract_sha256": sha256((run / "runtime-bridge-contract.json").read_bytes()),
        "budgets_file_sha256": sha256((run / "budgets.json").read_bytes()),
        "fixture_contract_sha256": sha256(
            canonical_json(
                {
                    "question": QUESTION,
                    "image_sha256": IMAGE_SHA256,
                    "image_bytes": IMAGE_BYTES,
                    "image_size": IMAGE_SIZE,
                    "expected_counts": EXPECTED_COUNTS,
                }
            )
        ),
        "project_id": request.get("project_id"),
        "project_registry_path": request_binding.get("project_registry_path"),
        "project_workspace": request_binding.get("project_workspace"),
        "fixture_b64_sha256": B64_SHA256,
        "fixture_png_sha256": IMAGE_SHA256,
        "product_source_sha256": source["actual"],
        "implementation_source_sha256": implementation,
        "additional_runtime_source_sha256": ADDITIONAL_RUNTIME_SOURCES,
        "provider_origin_expectation": PROVIDER_ORIGIN_EXPECTATION,
        "provider_origin_policy": PROVIDER_ORIGIN_POLICY,
        "budget_sha256": sha256(canonical_json(BUDGETS)),
        "future_observation_task_id": FUTURE_TASK_ID,
        "next_review": NEXT_REVIEW,
        "model_expectation": {"repo": MODEL_REPO, "digest": APPROVED_MODEL_DIGEST, "observed": False},
        "authorization": {"status": "LIVE_AUTHORIZATION_NOT_ISSUED", "scope": "offline-fixture-only"},
        "think_policy": THINK_POLICY,
        "format_policy": FORMAT_POLICY,
    }
    return expected, cast(dict[str, str], implementation)


def validate_execution_binding(
    run: Path,
    root: Path,
    *,
    request_raw: bytes | None = None,
    request_binding_raw: bytes | None = None,
) -> tuple[dict[str, object], bytes, dict[str, str]]:
    """Validate the immutable source-bound contract using stdlib-only code before product imports."""
    run = run.resolve()
    try:
        raw_request = request_raw if request_raw is not None else (run / "request.json").read_bytes()
        raw_request_binding = (
            request_binding_raw if request_binding_raw is not None else (run / "request.binding.json").read_bytes()
        )
        path = run / "execution-binding.json"
        binding_raw = path.read_bytes()

        def reject_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError(f"duplicate execution binding key: {key}")
                result[key] = value
            return result

        binding_obj = json.loads(binding_raw, object_pairs_hook=reject_duplicate_pairs)
        if not isinstance(binding_obj, dict):
            raise ValueError("execution binding must be an object")
        if run.resolve() not in (run / "endpoint-contract.json").resolve().parents:
            raise ValueError("INCONCLUSIVE_SOURCE_DRIFT: endpoint contract escapes owned run")
        expected, implementation = expected_execution_binding(run, root, raw_request, raw_request_binding)
        expected_raw = json.dumps(expected, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
        if binding_raw != expected_raw:
            raise ValueError("bytes, schema, identity, scope, or SHA mismatch")
        if binding_obj.get("endpoint_contract_sha256") != sha256((run / "endpoint-contract.json").read_bytes()):
            raise ValueError("endpoint contract bytes differ from immutable execution binding")
        if binding_obj.get("origin_contract_sha256") != sha256((run / "runtime-bridge-contract.json").read_bytes()):
            raise ValueError("runtime contract bytes differ from immutable execution binding")
        if binding_obj.get("budgets_file_sha256") != sha256((run / "budgets.json").read_bytes()):
            raise ValueError("budget bytes differ from immutable execution binding")
        return cast(dict[str, object], binding_obj), binding_raw, implementation
    except (OSError, ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"INCONCLUSIVE_SOURCE_DRIFT: execution binding validation failed: {exc}") from exc


def build_execution_binding(run: Path, root: Path, request_raw: bytes, request_binding_raw: bytes) -> dict[str, object]:
    """Build the explicit preparation candidate; validation never invokes this writer."""
    return expected_execution_binding(run, root, request_raw, request_binding_raw)[0]


def freeze_execution_binding(run: Path, root: Path, *, supersede_existing: bool = False) -> tuple[bytes, str]:
    """Freeze a candidate binding; a superseding attempt must archive and identify its predecessor."""
    target = run / "execution-binding.json"
    previous_raw: bytes | None = None
    if target.exists():
        if not supersede_existing:
            raise ValueError("execution binding already exists; refusing rebind")
        previous_raw = target.read_bytes()
        previous = strict_json_loads(previous_raw)
        if not isinstance(previous, dict):
            raise ValueError("existing execution binding is corrupt; refusing supersede")
        if (
            previous.get("task_id") != TASK_ID
            or previous.get("run_id") != run.name
            or not isinstance(previous.get("attempt_id"), str)
            or re.fullmatch(
                r"(?:final-gate-closeout|codex-final-gate)-candidate-[1-9][0-9]*", str(previous.get("attempt_id"))
            )
            is None
            or previous.get("attempt_id") == EXECUTION_BINDING_ATTEMPT_ID
        ):
            raise ValueError("previous binding identity is not a distinct candidate in this task/run")
        request_raw = (run / "request.json").read_bytes()
        request_binding_raw = (run / "request.binding.json").read_bytes()
        archived_request = run / f"request-{previous['attempt_id']}.json"
        archived_request_binding = run / f"request.binding-{previous['attempt_id']}.json"
        request_matches_previous = previous.get("request_sha256") == sha256(request_raw)
        archived_inputs_match = (
            previous.get("request_sha256") == sha256(archived_request.read_bytes())
            if archived_request.is_file()
            else False
        ) and (
            previous.get("request_binding_sha256") == sha256(archived_request_binding.read_bytes())
            if archived_request_binding.is_file()
            else False
        )
        if not request_matches_previous and not archived_inputs_match:
            raise ValueError("request identity changed without matching archived candidate inputs")
        previous_attempt = previous.get("attempt_id")
        if not isinstance(previous_attempt, str) or re.fullmatch(r"[a-zA-Z0-9_-]+", previous_attempt) is None:
            raise ValueError("previous binding attempt identity is unsafe")
        archive = run / f"execution-binding-{previous_attempt}.json"
        if archive.exists() and archive.read_bytes() != previous_raw:
            archive = run / f"execution-binding-{previous_attempt}-{sha256(previous_raw)[:12]}.json"
        if archive.exists():
            if archive.read_bytes() != previous_raw:
                raise ValueError("previous binding digest archive exists with different bytes")
        else:
            write_once(archive, previous_raw)
        old_manifest = run / "implementation-source-manifest.json"
        if old_manifest.exists():
            manifest_archive = run / f"implementation-source-manifest-{previous['attempt_id']}.json"
            old_manifest_raw = old_manifest.read_bytes()
            if manifest_archive.exists() and manifest_archive.read_bytes() != old_manifest_raw:
                manifest_archive = run / (
                    f"implementation-source-manifest-{previous['attempt_id']}-{sha256(old_manifest_raw)[:12]}.json"
                )
            if manifest_archive.exists():
                if manifest_archive.read_bytes() != old_manifest_raw:
                    raise ValueError("previous manifest digest archive exists with different bytes")
            else:
                write_once(manifest_archive, old_manifest_raw)
            old_manifest.unlink()
    request_raw = (run / "request.json").read_bytes()
    request_binding_raw = (run / "request.binding.json").read_bytes()
    value = build_execution_binding(run, root, request_raw, request_binding_raw)
    raw = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    if previous_raw is None:
        write_once(target, raw)
    else:
        temporary = run / f".execution-binding-{uuid.uuid4().hex}.tmp"
        write_once(temporary, raw)
        os.replace(temporary, target)
        directory_fd = os.open(run, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    return raw, sha256(raw)


def write_implementation_source_manifest(run: Path, root: Path) -> dict[str, object]:
    """Write implementation provenance separately and prove the execution binding remained byte-identical."""
    context = request_gate(run, root)
    binding_path = cast(Path, context["binding_path"])
    binding_before = binding_path.read_bytes()
    manifest = {
        "task_id": TASK_ID,
        "run_id": run.name,
        "execution_binding_id": context["execution_binding_id"],
        "execution_binding_sha256": context["execution_binding_sha256"],
        "sources": {
            name: {"path": name, "bytes": (run / name).stat().st_size, "sha256": sha256((run / name).read_bytes())}
            for name in IMPLEMENTATION_SOURCE_NAMES
        },
    }
    target = run / "implementation-source-manifest.json"
    manifest_raw = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    if target.exists():
        if target.read_bytes() != manifest_raw:
            raise ValueError("implementation source manifest differs; refusing overwrite")
    else:
        write_once(target, manifest_raw)
    if binding_path.read_bytes() != binding_before:
        raise ValueError("execution binding changed while implementation manifest was written")
    return manifest


def write_once(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def append_jsonl_fsync(path: Path, event: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = canonical_json(dict(event)) + b"\n"
    fd = os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        if os.write(fd, raw) != len(raw):
            raise OSError("short journal append")
        os.fsync(fd)
    finally:
        os.close(fd)


class OneShotJournal:
    """Task-wide, locked append-only logical/wire/response ledger."""

    def __init__(self, path: Path, task_id: str = TASK_ID):
        self.path = path
        self.task_id = task_id

    def replay(self) -> list[dict[str, object]]:
        if not self.path.exists():
            return []
        events: list[dict[str, object]] = []
        logical: dict[tuple[str, str], str] = {}
        wires: set[tuple[str, str]] = set()
        responses: set[tuple[str, str]] = set()
        counts: dict[str, int] = {}
        for line_no, raw in enumerate(self.path.read_bytes().splitlines(), 1):
            event_obj = strict_json_loads(raw)
            if not isinstance(event_obj, dict) or event_obj.get("task_id") != self.task_id:
                raise ValueError(f"foreign/corrupt task journal line {line_no}")
            event = cast(dict[str, object], event_obj)
            kind, slot, logical_id = event.get("event"), event.get("slot"), event.get("logical_id")
            if not isinstance(slot, str) or slot not in BUDGETS or not isinstance(logical_id, str) or not logical_id:
                raise ValueError(f"invalid journal identity line {line_no}")
            key = (slot, logical_id)
            if kind == "logical_reserved":
                digest = event.get("request_sha256")
                if key in logical or not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                    raise ValueError(f"duplicate or unbound logical reservation line {line_no}")
                counts[slot] = counts.get(slot, 0) + 1
                if counts[slot] > BUDGETS[slot]:
                    raise ValueError(f"logical budget exhausted in retained journal: {slot}")
                logical[key] = digest
            elif kind == "wire_entered":
                if key not in logical or key in wires or event.get("request_sha256") != logical[key]:
                    raise ValueError(f"wire lacks matching unique reservation line {line_no}")
                wires.add(key)
            elif kind == "response_observed":
                if key not in wires or key in responses or event.get("request_sha256") != logical[key]:
                    raise ValueError(f"response lacks matching wire/reservation line {line_no}")
                responses.add(key)
            elif kind == "denied_before_wire":
                if event.get("wire_entered") is not False:
                    raise ValueError(f"denial claims a wire line {line_no}")
            else:
                raise ValueError(f"unknown journal event line {line_no}")
            events.append(event)
        return events

    def counts(self) -> dict[str, dict[str, int]]:
        events = self.replay()
        result = {name: {} for name in ("logical_reserved", "wire_entered", "response_observed", "denied_before_wire")}
        for event in events:
            kind, slot = cast(str, event["event"]), cast(str, event["slot"])
            result[kind][slot] = result[kind].get(slot, 0) + 1
        return result

    def reserve(self, slot: str, logical_id: str, request_bytes: bytes) -> bool:
        if slot not in BUDGETS:
            raise ValueError("unknown budget slot")
        events = self.replay()
        ordinal = sum(e.get("event") == "logical_reserved" and e.get("slot") == slot for e in events)
        duplicate = any(
            e.get("event") == "logical_reserved" and e.get("slot") == slot and e.get("logical_id") == logical_id
            for e in events
        )
        allowed = not duplicate and ordinal < BUDGETS[slot]
        if not allowed:
            append_jsonl_fsync(
                self.path,
                {
                    "task_id": self.task_id,
                    "event": "denied_before_wire",
                    "slot": slot,
                    "logical_id": logical_id,
                    "request_sha256": sha256(request_bytes),
                    "wire_entered": False,
                    "at_utc": utc_now(),
                    "reason": "duplicate logical id or task ceiling exhausted",
                },
            )
            return False
        append_jsonl_fsync(
            self.path,
            {
                "task_id": self.task_id,
                "event": "logical_reserved",
                "slot": slot,
                "logical_id": logical_id,
                "request_sha256": sha256(request_bytes),
                "at_utc": utc_now(),
            },
        )
        self.replay()
        return True

    def enter_wire(self, slot: str, logical_id: str, request_bytes: bytes) -> bool:
        events = self.replay()
        key_events = [e for e in events if e.get("slot") == slot and e.get("logical_id") == logical_id]
        reservation = next((e for e in key_events if e.get("event") == "logical_reserved"), None)
        already_wire = any(e.get("event") == "wire_entered" for e in key_events)
        if reservation is None or already_wire or reservation.get("request_sha256") != sha256(request_bytes):
            append_jsonl_fsync(
                self.path,
                {
                    "task_id": self.task_id,
                    "event": "denied_before_wire",
                    "slot": slot,
                    "logical_id": logical_id,
                    "request_sha256": sha256(request_bytes),
                    "wire_entered": False,
                    "at_utc": utc_now(),
                    "reason": "wire requires same unused logical reservation",
                },
            )
            return False
        append_jsonl_fsync(
            self.path,
            {
                "task_id": self.task_id,
                "event": "wire_entered",
                "slot": slot,
                "logical_id": logical_id,
                "request_sha256": sha256(request_bytes),
                "at_utc": utc_now(),
            },
        )
        return True

    def record_response(
        self, slot: str, logical_id: str, request_bytes: bytes, response_bytes: bytes, status: int | None
    ) -> None:
        append_jsonl_fsync(
            self.path,
            {
                "task_id": self.task_id,
                "event": "response_observed",
                "slot": slot,
                "logical_id": logical_id,
                "request_sha256": sha256(request_bytes),
                "response_sha256": sha256(response_bytes),
                "response_bytes": len(response_bytes),
                "status": status,
                "at_utc": utc_now(),
            },
        )
        self.replay()


class ResponseCapture:
    """Transparent response wrapper: read/iteration/context manager delegate and retain raw bytes."""

    def __init__(self, response: Any, sink: Callable[[bytes], None]):
        self._response = response
        self._sink = sink
        self.status = getattr(response, "status", None)
        self.code = getattr(response, "code", self.status)
        self.url = getattr(response, "url", "")
        self.reason = getattr(response, "reason", "")
        self.headers = response.headers
        self._closed = False

    def __enter__(self) -> "ResponseCapture":
        self._response.__enter__()
        return self

    def __exit__(self, *args: object) -> bool:
        self.close()
        result = self._response.__exit__(*args)
        return bool(result)

    def read(self, amount: int = -1) -> bytes:
        data = self._response.read(amount)
        if data:
            self._sink(data)
        return data

    def read1(self, amount: int = -1) -> bytes:
        method = getattr(self._response, "read1", self._response.read)
        data = method(amount)
        if data:
            self._sink(data)
        return data

    def __iter__(self):
        for chunk in self._response:
            if chunk:
                self._sink(chunk)
            yield chunk

    def __getattr__(self, name: str) -> object:
        return getattr(self._response, name)

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._response.close()


def parse_product_assistant_content(raw_body: bytes) -> tuple[str | None, str | None]:
    try:
        payload = strict_json_loads(raw_body)
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        return None, f"invalid_product_json:{type(exc).__name__}"
    if not isinstance(payload, dict) or set(payload) - {
        "choices",
        "model",
        "usage",
        "id",
        "object",
        "created",
        "system_fingerprint",
    }:
        return None, "unexpected_product_response_shape"
    choices = payload.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        return None, "expected_one_product_choice"
    choice = choices[0]
    message = choice.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        return None, "assistant_content_missing"
    if message.get("role") != "assistant":
        return None, "assistant_role_mismatch"
    return cast(str, message["content"]), None


def evaluate_semantic(content: str | None) -> dict[str, object]:
    if content is None:
        return {"status": "NOT_OBSERVED", "pass": False, "reason": "not_observed"}
    ok, reason = parse_counts_strict(content)
    return {"status": "PASS" if ok else "FAIL_SEMANTIC", "pass": ok, "reason": reason}


def reduce_observation(facts: Mapping[str, object], *, fixture_only: bool = False) -> dict[str, object]:
    """Reduce source/raw-bound facts; no expected values are copied into observed inputs."""
    observed = facts.get("gates")
    if not isinstance(observed, Mapping):
        observed = {}
    gates: dict[str, str] = {
        name: cast(str, observed.get(name))
        if isinstance(observed.get(name), str) and observed.get(name) in {"PASS", "FAIL", "INCONCLUSIVE"}
        else "UNKNOWN"
        for name in REQUIRED_GATES
    }

    content_obj = facts.get("assistant_content")
    semantic = evaluate_semantic(content_obj if isinstance(content_obj, str) else None)
    semantic_status = cast(str, semantic["status"])
    gates["semantic_counts"] = semantic_status if semantic_status in {"PASS", "FAIL_SEMANTIC"} else "UNKNOWN"
    if fixture_only:
        missing = [name for name, value in gates.items() if value != "PASS"]
        return {
            "verdict": "FIXTURE_ONLY",
            "pass": False,
            "gates": gates,
            "semantic": semantic,
            "missing_gates": missing,
        }
    missing = [name for name, value in gates.items() if value != "PASS"]
    if not missing:
        return {"verdict": "PASS", "pass": True, "gates": gates, "semantic": semantic, "missing_gates": []}
    if gates.get("auth_unauthorized_401") == "FAIL" or gates.get("auth_bearer_200") == "FAIL":
        verdict = "INCONCLUSIVE_PRODUCT_NOT_REACHED"
    elif semantic["status"] == "FAIL_SEMANTIC" and gates.get("upstream_status_done_content_type") == "PASS":
        verdict = "FAIL_SEMANTIC"
    elif gates.get("source_request_authorization") == "INCONCLUSIVE":
        verdict = "INCONCLUSIVE_SOURCE_DRIFT"
    else:
        verdict = (
            "INCONCLUSIVE_MANDATORY_GATE_UNKNOWN"
            if any(v == "UNKNOWN" for v in gates.values())
            else "FAIL_MANDATORY_GATE"
        )
    return {"verdict": verdict, "pass": False, "gates": gates, "semantic": semantic, "missing_gates": missing}


class ObservationAdapter(Protocol):
    def bootstrap(self, context: Mapping[str, object]) -> Mapping[str, object]: ...
    def readiness(self, context: Mapping[str, object]) -> Mapping[str, object]: ...
    def metadata(self, context: Mapping[str, object]) -> Mapping[str, object]: ...
    def dispatch_product(
        self,
        context: Mapping[str, object],
        provider_wire: Callable[[bytes, Callable[[], tuple[bytes, int, Mapping[str, str]]]], Mapping[str, object]],
    ) -> Mapping[str, object]: ...
    def postflight(self, context: Mapping[str, object]) -> Mapping[str, object]: ...
    def cleanup(self, context: Mapping[str, object]) -> Mapping[str, object]: ...


@dataclass
class SupervisorState:
    phase: str = "created"
    events: list[dict[str, object]] = field(default_factory=list)
    dispatches: int = 0
    provider_wires: int = 0
    product_request_bytes: bytes = b""
    product_response_bytes: bytes = b""
    provider_request_bytes: bytes = b""
    provider_response_bytes: bytes = b""
    error: str | None = None
    cleanup_calls: int = 0
    cleanup_receipt: dict[str, object] | None = None

    def transition(self, phase: str, **details: object) -> None:
        order = (
            "created",
            "prepared",
            "bootstrapped",
            "readiness",
            "metadata",
            "frozen",
            "reserved",
            "dispatched",
            "observed",
            "postflight",
            "cleanup_failed",
            "cleaned",
        )
        if phase not in order or order.index(phase) <= order.index(self.phase):
            raise RuntimeError(f"invalid supervisor transition {self.phase} -> {phase}")
        self.phase = phase
        self.events.append({"at_utc": utc_now(), "phase": phase, **details})


def supervise_once(
    *,
    run: Path,
    root: Path,
    adapter: ObservationAdapter,
    journal: OneShotJournal,
    authorization: Mapping[str, object] | None = None,
    state: SupervisorState | None = None,
) -> dict[str, object]:
    """Single state machine used by offline and future live adapters; callback failure never redispatches."""
    state = state or SupervisorState()
    if authorization is None or authorization.get("status") not in {
        "OFFLINE_ADAPTER_FIXTURE_ONLY",
        "VERIFIED_RUNTIME_AUTHORIZATION",
    }:
        return {
            "verdict": "INCONCLUSIVE_LIVE_AUTHORIZATION_NOT_ISSUED",
            "phase": state.phase,
            "dispatches": 0,
            "provider_wires": 0,
        }
    fixture_only = authorization.get("mode") != "LIVE"
    if authorization.get("status") == "VERIFIED_RUNTIME_AUTHORIZATION":
        verified = verify_runtime_authorization(
            run, root, authorization.get("descriptor"), mode=str(authorization.get("mode"))
        )
        if verified != dict(authorization):
            return {"verdict": "INCONCLUSIVE_AUTHORITY_DRIFT", "dispatches": 0, "provider_wires": 0}
    if authorization.get("scope") != TASK_ID:
        return {
            "verdict": "INCONCLUSIVE_FIXTURE_SCOPE_MISMATCH",
            "phase": state.phase,
            "dispatches": 0,
            "provider_wires": 0,
        }
    run = run.resolve()
    try:
        context = request_gate(run, root)
        binding_start = cast(str, context["execution_binding_sha256"])
        context["binding_path"] = run / "execution-binding.json"
        context["run"] = run
        context["journal"] = journal
        context["supervisor_state"] = state
        context["authorization"] = dict(authorization)
        context["fixture_only"] = fixture_only
        context["protected_before"] = context["source"]
        context["source_start"] = context["source"]
        source_obj = context.get("source")
        if not isinstance(source_obj, dict) or not isinstance(source_obj.get("actual"), dict):
            raise ValueError("source snapshot is not an object")
        source_start = cast(dict[str, str], source_obj["actual"])
        started_monotonic = time.monotonic()
        deadline = started_monotonic + TOTAL_DEADLINE_SECONDS
        readiness_deadline = started_monotonic + READINESS_DEADLINE_SECONDS
        cleanup_deadline = deadline + GRACEFUL_CLEANUP_SECONDS
        context["deadline_monotonic"] = deadline
        context["readiness_deadline_monotonic"] = readiness_deadline
        context["cleanup_deadline_monotonic"] = cleanup_deadline
        context["cleanup_required"] = False
        context["repository_root"] = root
        context["readiness_deadline_seconds"] = READINESS_DEADLINE_SECONDS
        context["cleanup_grace_seconds"] = GRACEFUL_CLEANUP_SECONDS
        context["adapter_timeout_seconds"] = max(0.0, deadline - time.monotonic())
        attempts_root = (run / "attempts").resolve()
        if attempts_root.parent != run.resolve():
            raise ValueError("attempts path escapes owned run")
        context["attempts_root"] = attempts_root
        context["attempt_id"] = EXECUTION_BINDING_ATTEMPT_ID
        state.transition("prepared", source_sha256=source_start, request_sha256=context["request_sha256"])
        if time.monotonic() >= deadline:
            _mark_timeout(context, state, "before_bootstrap", started_monotonic)
            return _finish_failure("INCONCLUSIVE_TIMEOUT_BEFORE_BOOTSTRAP", state, adapter, context)
        context["adapter_timeout_seconds"] = max(0.0, min(deadline, readiness_deadline) - time.monotonic())
        try:
            boot = dict(adapter.bootstrap(context))
        except Exception:
            context["cleanup_required"] = True
            raise
        context["bootstrap_receipt"] = boot
        context["cleanup_required"] = boot.get("worker_owned") is True or boot.get("auth_state_owned") is True
        if time.monotonic() >= deadline:
            _mark_timeout(context, state, "bootstrap", started_monotonic)
            return _finish_failure("INCONCLUSIVE_TIMEOUT_BOOTSTRAP", state, adapter, context)
        if boot.get("worker_owned") is not True or boot.get("auth_state_owned") is not True:
            return _finish_failure("INCONCLUSIVE_BOOTSTRAP_NOT_LIVE_OBSERVED", state, adapter, context)
        if boot.get("source") not in {
            "OFFLINE_FIXTURE",
            "OFFLINE_CAPTURED_FACTS",
            "OFFLINE_MOCK",
            "RUNTIME_OBSERVATION",
        }:
            return _finish_failure("INCONCLUSIVE_BOOTSTRAP_NOT_LIVE_OBSERVED", state, adapter, context)
        state.transition(
            "bootstrapped", worker_owned=boot.get("worker_owned"), auth_state_owned=boot.get("auth_state_owned")
        )
        readiness_started = time.monotonic()
        if time.monotonic() >= min(deadline, readiness_deadline):
            _mark_timeout(context, state, "before_readiness", started_monotonic, deadline=readiness_deadline)
            return _finish_failure("INCONCLUSIVE_TIMEOUT_BEFORE_READINESS", state, adapter, context)
        context["adapter_timeout_seconds"] = max(0.0, min(deadline, readiness_deadline) - time.monotonic())
        readiness = dict(adapter.readiness(context))
        readiness_finished = time.monotonic()
        readiness_elapsed = readiness_finished - readiness_started
        if readiness_finished >= deadline or readiness_finished >= readiness_deadline:
            _mark_timeout(context, state, "readiness", started_monotonic, deadline=min(deadline, readiness_deadline))
            return _finish_failure("INCONCLUSIVE_TIMEOUT_READINESS", state, adapter, context)
        state.transition(
            "readiness",
            elapsed_seconds=readiness_elapsed,
            unauthenticated_status=readiness.get("unauthenticated_status"),
            bearer_status=readiness.get("bearer_status"),
            ready=readiness.get("ready"),
        )
        if readiness.get("source") == "OFFLINE_FIXTURE":
            return _finish_failure("INCONCLUSIVE_READINESS_FIXTURE_ONLY", state, adapter, context)
        if readiness_elapsed > READINESS_DEADLINE_SECONDS:
            return _finish_failure("INCONCLUSIVE_READINESS_TIMEOUT", state, adapter, context)
        if (
            readiness.get("unauthenticated_status") != 401
            or readiness.get("bearer_status") != 200
            or readiness.get("ready") is not True
        ):
            return _finish_failure("INCONCLUSIVE_PRODUCT_NOT_REACHED", state, adapter, context)
        if time.monotonic() >= deadline:
            _mark_timeout(context, state, "before_metadata", started_monotonic)
            return _finish_failure("INCONCLUSIVE_TIMEOUT_BEFORE_METADATA", state, adapter, context)
        state.transition("metadata", metadata_entered=True, remaining_seconds=max(0.0, deadline - time.monotonic()))
        context["adapter_timeout_seconds"] = max(0.0, deadline - time.monotonic())
        metadata = dict(adapter.metadata(context))
        if time.monotonic() >= deadline:
            _mark_timeout(context, state, "metadata", started_monotonic)
            return _finish_failure("INCONCLUSIVE_TIMEOUT_METADATA", state, adapter, context)
        if metadata.get("source") == "OFFLINE_FIXTURE":
            return _finish_failure("INCONCLUSIVE_METADATA_FIXTURE_ONLY", state, adapter, context)
        state.events[-1].update(
            observed_model_digest=metadata.get("model_digest"), metadata_source=metadata.get("source")
        )
        if (
            metadata.get("complete") is not True
            or metadata.get("version") is None
            or metadata.get("tags") is None
            or metadata.get("capabilities") is None
        ):
            return _finish_failure("INCONCLUSIVE_METADATA_NOT_READY", state, adapter, context)
        if metadata.get("model_repo") != MODEL_REPO or metadata.get("model_digest") != APPROVED_MODEL_DIGEST:
            return _finish_failure("INCONCLUSIVE_MODEL_DRIFT", state, adapter, context)
        acceptance = {
            "task_id": TASK_ID,
            "frozen_at_utc": utc_now(),
            "request_sha256": context["request_sha256"],
            "source_sha256": source_start,
            "harness_sha256": context["harness_sha256"],
            "authorization_sha256": sha256(canonical_json(dict(authorization))),
            "metadata_sha256": sha256(canonical_json(metadata)),
            "readiness_sha256": sha256(canonical_json(readiness)),
            "options": {"stream": False, "max_tokens": 128, "temperature": 0},
            "think": False,
            "format": "omitted",
            "image_sha256": IMAGE_SHA256,
        }
        frozen_bytes = json.dumps(acceptance, ensure_ascii=False, indent=2).encode() + b"\n"
        write_once(run / "acceptance.json", frozen_bytes)
        state.transition("frozen", acceptance_sha256=sha256(frozen_bytes))
        if time.monotonic() >= deadline:
            _mark_timeout(context, state, "before_reservation", started_monotonic)
            return _finish_failure("INCONCLUSIVE_TIMEOUT_BEFORE_RESERVATION", state, adapter, context)
        request_bytes = cast(bytes, context["request_raw"])
        product_id = f"product:{uuid.uuid4().hex}"
        attempt_id = cast(str, context["attempt_id"])
        attempts_root = cast(Path, context["attempts_root"])
        attempt_path = (attempts_root / attempt_id).resolve()
        if attempt_path.parent != attempts_root.resolve():
            raise ValueError("attempt path escapes owned run")
        attempt_path.mkdir(parents=True, exist_ok=False)
        write_once(attempt_path / "product-request.bin", request_bytes)
        if not journal.reserve("product_authenticated_chat_post", product_id, request_bytes):
            return _finish_failure("INCONCLUSIVE_BUDGET_DENIED", state, adapter, context)
        state.product_request_bytes = request_bytes
        context["product_logical_id"] = product_id
        context["product_request_bytes"] = request_bytes
        state.transition("reserved", product_logical_id=product_id, request_sha256=sha256(request_bytes))

        provider_context = cast(dict[str, object], context)

        def provider_wire(
            provider_request: bytes, send: Callable[[], tuple[bytes, int, Mapping[str, str]]]
        ) -> Mapping[str, object]:
            if time.monotonic() >= deadline:
                _mark_timeout(context, state, "before_provider_reservation", started_monotonic)
                raise TimeoutError("deadline expired before provider reservation; no wire")
            if state.provider_wires:
                journal.reserve("retry_wire", f"provider-retry:{uuid.uuid4().hex}", provider_request)
                raise RuntimeError("provider dispatch is one-shot; second wire denied")
            origin = str(metadata.get("ollama_origin", ""))
            slot = classify_upstream_request(origin + "/api/chat", "POST", provider_request, expected_origin=origin)
            provider_id = f"provider:{product_id.split(':', 1)[1]}"
            write_once(attempt_path / "provider-request.bin", provider_request)
            guard = ProviderWireGuard(run, root, journal, product_id, deadline, time.monotonic)
            if time.monotonic() >= deadline:
                _mark_timeout(context, state, "before_provider_wire", started_monotonic)
                raise TimeoutError("deadline expired before provider wire; no send")
            provider_context["provider_wire_timeout_seconds"] = max(0.0, deadline - time.monotonic())
            send_started = time.monotonic()
            if send_started >= deadline:
                _mark_timeout(context, state, "before_provider_send", started_monotonic)
                raise TimeoutError("deadline expired before provider send; no send")
            slot, provider_id = guard.enter(provider_request, url=origin + "/api/chat")
            state.provider_wires += 1
            state.provider_request_bytes = provider_request
            response_bytes, status, headers = send()
            state.provider_response_bytes = response_bytes
            write_once(attempt_path / "provider-response.bin", response_bytes)
            provider_headers = json.dumps(
                {
                    "status": status,
                    "safe_headers": {
                        key: value
                        for key, value in headers.items()
                        if key.casefold() in {"content-type", "content-length", "date"}
                    },
                },
                ensure_ascii=False,
                indent=2,
            ).encode() + bytes([10])
            write_once(attempt_path / "provider-response-headers.json", provider_headers)
            journal.record_response(slot, provider_id, provider_request, response_bytes, status)
            if time.monotonic() >= deadline:
                timeout_receipt = {
                    "task_id": TASK_ID,
                    "attempt_id": attempt_id,
                    "execution_binding_id": context["execution_binding_id"],
                    "execution_binding_sha256": binding_start,
                    "stage": "provider_wire",
                    "deadline_seconds": TOTAL_DEADLINE_SECONDS,
                    "deadline_elapsed_seconds": max(0.0, time.monotonic() - started_monotonic),
                    "verdict": "INCONCLUSIVE_RESULT_UNKNOWN_NO_REDISPATCH",
                    "raw_provider_response_sha256": sha256(response_bytes),
                    "provider_status": status,
                    "provider_wires": state.provider_wires,
                    "product_dispatches": state.dispatches,
                }
                context["timeout_receipt"] = timeout_receipt
                timeout_path = attempt_path / "timeout-receipt.json"
                if not timeout_path.exists():
                    write_once(timeout_path, json.dumps(timeout_receipt, ensure_ascii=False, indent=2).encode() + b"\n")
                state.events.append(
                    {
                        "at_utc": utc_now(),
                        "phase": "timeout",
                        **timeout_receipt,
                    }
                )
                raise TimeoutError("provider returned after deadline; result unknown, no retry")
            content_type = next((value for key, value in headers.items() if key.casefold() == "content-type"), "")
            return {
                "logical_id": provider_id,
                "slot": slot,
                "status": status,
                "response_sha256": sha256(response_bytes),
                "content_type": content_type,
                "done": status == 200,
            }

        if sha256(cast(bytes, context["product_request_bytes"])) != context["request_sha256"]:
            raise ValueError("product request bytes drifted immediately before adapter dispatch")
        dispatch_started = time.monotonic()
        if dispatch_started >= deadline:
            _mark_timeout(context, state, "before_product_dispatch", started_monotonic)
            return _finish_failure("INCONCLUSIVE_TIMEOUT_BEFORE_PRODUCT_DISPATCH", state, adapter, context)
        product_dispatch_id = cast(str, context["product_logical_id"])
        if not getattr(adapter, "terminal_wire_owner", False):
            request_gate(run, root)
            if not journal.enter_wire("product_authenticated_chat_post", product_dispatch_id, request_bytes):
                return _finish_failure("INCONCLUSIVE_BUDGET_DENIED", state, adapter, context)
            state.dispatches += 1
        context["adapter_timeout_seconds"] = max(0.0, deadline - dispatch_started)
        product_response = dict(adapter.dispatch_product(context, provider_wire))
        state.product_response_bytes = cast(bytes, product_response.get("raw_body", b""))
        product_dispatch_late = time.monotonic() >= deadline
        if product_dispatch_late:
            timeout_receipt = {
                "task_id": TASK_ID,
                "attempt_id": attempt_id,
                "execution_binding_id": context["execution_binding_id"],
                "execution_binding_sha256": binding_start,
                "stage": "product_dispatch",
                "deadline_seconds": TOTAL_DEADLINE_SECONDS,
                "deadline_elapsed_seconds": max(0.0, time.monotonic() - started_monotonic),
                "verdict": "INCONCLUSIVE_RESULT_UNKNOWN_NO_REDISPATCH",
                "raw_product_response_sha256": sha256(state.product_response_bytes),
                "raw_provider_response_sha256": sha256(state.provider_response_bytes)
                if state.provider_response_bytes
                else None,
                "product_dispatches": state.dispatches,
                "provider_wires": state.provider_wires,
            }
            context["timeout_receipt"] = timeout_receipt
            if attempt_path.exists():
                if state.product_response_bytes:
                    write_once(attempt_path / "product-response.bin", state.product_response_bytes)
                    write_once(
                        attempt_path / "product-response-headers.json",
                        json.dumps(
                            {
                                "status": product_response.get("status"),
                                "safe_headers": {"content-type": product_response.get("content_type", "")},
                            },
                            ensure_ascii=False,
                            indent=2,
                        ).encode()
                        + b"\n",
                    )
                if state.provider_response_bytes and not (attempt_path / "provider-response.bin").exists():
                    write_once(attempt_path / "provider-response.bin", state.provider_response_bytes)
            provider_id = f"provider:{product_id.split(':', 1)[1]}"
            provider_response_recorded = any(
                event.get("event") == "response_observed"
                and event.get("slot") == "ollama_chat_inference_wire"
                and event.get("logical_id") == provider_id
                for event in journal.replay()
            )
            if (
                not getattr(adapter, "terminal_wire_owner", False)
                and state.provider_wires
                and state.provider_response_bytes
                and not provider_response_recorded
            ):
                journal.record_response(
                    "ollama_chat_inference_wire",
                    f"provider:{product_id.split(':', 1)[1]}",
                    state.provider_request_bytes,
                    state.provider_response_bytes,
                    None,
                )
            if state.dispatches and state.product_response_bytes:
                journal.record_response(
                    "product_authenticated_chat_post",
                    product_id,
                    request_bytes,
                    state.product_response_bytes,
                    cast(int | None, product_response.get("status")),
                )
            result = _finish_failure("INCONCLUSIVE_RESULT_UNKNOWN_NO_REDISPATCH", state, adapter, context)
            result["timeout_receipt"] = timeout_receipt
            state.events[-1].update(
                stage="product_dispatch",
                deadline_elapsed_seconds=timeout_receipt["deadline_elapsed_seconds"],
                raw_product_response_preserved=bool(state.product_response_bytes),
                raw_provider_response_preserved=bool(state.provider_response_bytes),
            )
            if attempt_path.exists():
                timeout_path = attempt_path / "timeout-receipt.json"
                if not timeout_path.exists():
                    write_once(timeout_path, json.dumps(timeout_receipt, ensure_ascii=False, indent=2).encode() + b"\n")
            result["raw_response_preserved"] = {
                "product_bytes": len(state.product_response_bytes),
                "provider_bytes": len(state.provider_response_bytes),
            }
            return result
        if time.monotonic() >= deadline:
            timeout_receipt = {
                "task_id": TASK_ID,
                "attempt_id": attempt_id,
                "execution_binding_id": context["execution_binding_id"],
                "execution_binding_sha256": binding_start,
                "stage": "product_response_record",
                "deadline_seconds": TOTAL_DEADLINE_SECONDS,
                "deadline_elapsed_seconds": max(0.0, time.monotonic() - started_monotonic),
                "verdict": "INCONCLUSIVE_RESULT_UNKNOWN_NO_REDISPATCH",
                "raw_product_response_sha256": sha256(state.product_response_bytes),
                "raw_provider_response_sha256": sha256(state.provider_response_bytes)
                if state.provider_response_bytes
                else None,
                "product_dispatches": state.dispatches,
                "provider_wires": state.provider_wires,
            }
            context["timeout_receipt"] = timeout_receipt
            provider_id = f"provider:{product_id.split(':', 1)[1]}"
            provider_response_recorded = any(
                event.get("event") == "response_observed"
                and event.get("slot") == "ollama_chat_inference_wire"
                and event.get("logical_id") == provider_id
                for event in journal.replay()
            )
            if (
                not getattr(adapter, "terminal_wire_owner", False)
                and state.provider_wires
                and state.provider_response_bytes
                and not provider_response_recorded
            ):
                journal.record_response(
                    "ollama_chat_inference_wire",
                    provider_id,
                    state.provider_request_bytes,
                    state.provider_response_bytes,
                    None,
                )
            if state.dispatches and state.product_response_bytes:
                journal.record_response(
                    "product_authenticated_chat_post",
                    product_id,
                    request_bytes,
                    state.product_response_bytes,
                    cast(int | None, product_response.get("status")),
                )
                write_once(attempt_path / "product-response.bin", state.product_response_bytes)
                write_once(
                    attempt_path / "product-response-headers.json",
                    json.dumps(
                        {
                            "status": product_response.get("status"),
                            "safe_headers": {"content-type": product_response.get("content_type", "")},
                        },
                        ensure_ascii=False,
                        indent=2,
                    ).encode()
                    + b"\n",
                )
            result = _finish_failure("INCONCLUSIVE_RESULT_UNKNOWN_NO_REDISPATCH", state, adapter, context)
            timeout_path = attempt_path / "timeout-receipt.json"
            if not timeout_path.exists():
                write_once(timeout_path, json.dumps(timeout_receipt, ensure_ascii=False, indent=2).encode() + b"\n")
            result["timeout_receipt"] = timeout_receipt
            result["raw_response_preserved"] = {
                "product_bytes": len(state.product_response_bytes),
                "provider_bytes": len(state.provider_response_bytes),
            }
            return result
        write_once(attempt_path / "product-response.bin", state.product_response_bytes)
        product_headers = json.dumps(
            {
                "status": product_response.get("status"),
                "safe_headers": {"content-type": product_response.get("content_type", "")},
            },
            ensure_ascii=False,
            indent=2,
        ).encode() + bytes([10])
        write_once(attempt_path / "product-response-headers.json", product_headers)
        state.transition(
            "dispatched",
            product_logical_id=product_id,
            product_status=product_response.get("status"),
            provider_wires=state.provider_wires,
        )
        journal.record_response(
            "product_authenticated_chat_post",
            product_id,
            request_bytes,
            state.product_response_bytes,
            cast(int | None, product_response.get("status")),
        )
        source_end = source_snapshot(root)
        source_unchanged = source_end.get("ready") is True and source_end.get("actual") == source_start
        upstream_body = state.provider_response_bytes
        upstream_obj: object | None = None
        try:
            upstream_obj = strict_json_loads(upstream_body) if upstream_body else None
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            upstream_obj = None
        upstream_record = cast(dict[str, object], upstream_obj) if isinstance(upstream_obj, dict) else {}
        upstream_message_obj = upstream_record.get("message")
        upstream_message = (
            cast(dict[str, object], upstream_message_obj) if isinstance(upstream_message_obj, dict) else {}
        )
        upstream_content = upstream_message.get("content")
        upstream_done = upstream_record.get("done")
        product_content, product_parse_error = parse_product_assistant_content(state.product_response_bytes)
        binding_before_postflight = cast(Path, context["binding_path"]).read_bytes() == cast(
            bytes, context["execution_binding_raw"]
        )
        dispatch_stage_late = time.monotonic() >= deadline
        if dispatch_stage_late:
            timeout_receipt = {
                "task_id": TASK_ID,
                "attempt_id": attempt_id,
                "execution_binding_id": context["execution_binding_id"],
                "execution_binding_sha256": binding_start,
                "stage": "product_dispatch",
                "deadline_seconds": TOTAL_DEADLINE_SECONDS,
                "deadline_elapsed_seconds": max(0.0, time.monotonic() - started_monotonic),
                "verdict": "INCONCLUSIVE_RESULT_UNKNOWN_NO_REDISPATCH",
                "raw_product_response_sha256": sha256(state.product_response_bytes),
                "raw_provider_response_sha256": sha256(state.provider_response_bytes)
                if state.provider_response_bytes
                else None,
                "product_dispatches": state.dispatches,
                "provider_wires": state.provider_wires,
            }
            context["timeout_receipt"] = timeout_receipt
            if (
                not getattr(adapter, "terminal_wire_owner", False)
                and state.provider_wires
                and state.provider_response_bytes
            ):
                provider_id = f"provider:{product_id.split(':', 1)[1]}"
                provider_response_recorded = any(
                    event.get("event") == "response_observed"
                    and event.get("slot") == "ollama_chat_inference_wire"
                    and event.get("logical_id") == provider_id
                    for event in journal.replay()
                )
                if not provider_response_recorded:
                    journal.record_response(
                        "ollama_chat_inference_wire",
                        provider_id,
                        state.provider_request_bytes,
                        state.provider_response_bytes,
                        None,
                    )
            if state.product_response_bytes:
                write_once(attempt_path / "product-response.bin", state.product_response_bytes)
                write_once(
                    attempt_path / "product-response-headers.json",
                    json.dumps(
                        {
                            "status": product_response.get("status"),
                            "safe_headers": {"content-type": product_response.get("content_type", "")},
                        },
                        ensure_ascii=False,
                        indent=2,
                    ).encode()
                    + b"\n",
                )
            timeout_path = attempt_path / "timeout-receipt.json"
            if not timeout_path.exists():
                write_once(timeout_path, json.dumps(timeout_receipt, ensure_ascii=False, indent=2).encode() + b"\n")
            raise TimeoutError("product dispatch returned after deadline; result unknown, no retry")
        gates: dict[str, str] = {
            "source_request_authorization": "PASS"
            if source_unchanged
            and product_response.get("source_sha256_before_wire") == source_start
            and product_response.get("request_sha256_before_wire") == context["request_sha256"]
            and authorization.get("scope") == TASK_ID
            else "FAIL",
            "auth_unauthorized_401": "PASS" if readiness.get("unauthenticated_status") == 401 else "FAIL",
            "auth_bearer_200": "PASS" if readiness.get("bearer_status") == 200 else "FAIL",
            "readiness": "PASS" if readiness.get("ready") is True else "FAIL",
            "model_version_tags_show_digest_capability": "PASS"
            if metadata.get("source") != "OFFLINE_FIXTURE"
            and metadata.get("version") is not None
            and metadata.get("tags") is not None
            and metadata.get("show") is not None
            and metadata.get("model_repo") == MODEL_REPO
            and metadata.get("model_digest") == APPROVED_MODEL_DIGEST
            and metadata.get("capabilities") is not None
            else "FAIL",
            "product_status_content_type": "PASS"
            if product_response.get("status") == 200
            and str(product_response.get("content_type", "")).split(";", 1)[0].lower() == "application/json"
            else "FAIL",
            "upstream_status_done_content_type": "PASS"
            if product_response.get("upstream_status") == 200
            and upstream_done is True
            and str(product_response.get("upstream_content_type", "")).split(";", 1)[0].lower() == "application/json"
            else "FAIL",
            "input_options_think_format": "PASS" if product_response.get("provider_contract_pass") is True else "FAIL",
            "raw_response_equality": "PASS"
            if isinstance(upstream_content, str) and upstream_content == product_content
            else "FAIL",
            "accounting_lineage": "PASS"
            if state.dispatches == 1
            and state.provider_wires == 1
            and product_response.get("product_logical_id") == product_id
            and product_response.get("provider_logical_id") == f"provider:{product_id.split(':', 1)[1]}"
            else "FAIL",
            "no_retry_redirect_native_tool": "PASS"
            if product_response.get("retry_wires", 0) == 0
            and product_response.get("redirect_wires", 0) == 0
            and product_response.get("native_wires", 0) == 0
            and product_response.get("tool_calls", 0) == 0
            and state.provider_wires == 1
            else "FAIL",
            "cleanup_owned_exit": "UNKNOWN",
            "protected_before_after": "INCONCLUSIVE",
            "execution_binding_immutable": "PASS" if binding_before_postflight else "FAIL",
            "deadline_stage_contract": "INCONCLUSIVE" if product_dispatch_late else "PASS",
        }
        assistant_content = product_content if isinstance(product_content, str) else None
        if product_parse_error is not None:
            gates["product_status_content_type"] = "FAIL"
        context["adapter_timeout_seconds"] = max(0.0, deadline - time.monotonic())
        postflight_late = time.monotonic() >= deadline
        if postflight_late:
            context["timeout_receipt"] = {
                "task_id": TASK_ID,
                "attempt_id": attempt_id,
                "execution_binding_id": context["execution_binding_id"],
                "execution_binding_sha256": binding_start,
                "stage": "postflight",
                "deadline_seconds": TOTAL_DEADLINE_SECONDS,
                "deadline_elapsed_seconds": max(0.0, time.monotonic() - started_monotonic),
                "verdict": "INCONCLUSIVE_RESULT_UNKNOWN_NO_REDISPATCH",
                "raw_product_response_sha256": sha256(state.product_response_bytes),
                "raw_provider_response_sha256": sha256(state.provider_response_bytes)
                if state.provider_response_bytes
                else None,
                "product_dispatches": state.dispatches,
                "provider_wires": state.provider_wires,
            }
        postflight_started = time.monotonic()
        if postflight_late:
            postflight = {"status": "NOT_CALLED_DEADLINE_EXPIRED"}
        else:
            context["adapter_timeout_seconds"] = max(0.0, deadline - postflight_started)
            try:
                postflight = dict(adapter.postflight(context))
            except Exception as postflight_exc:
                postflight = {"status": "ERROR", "error": f"{type(postflight_exc).__name__}: {postflight_exc}"}
            postflight_late = time.monotonic() >= deadline
            if postflight_late:
                context["timeout_receipt"] = {
                    "task_id": TASK_ID,
                    "attempt_id": attempt_id,
                    "execution_binding_id": context["execution_binding_id"],
                    "execution_binding_sha256": binding_start,
                    "stage": "postflight",
                    "deadline_seconds": TOTAL_DEADLINE_SECONDS,
                    "deadline_elapsed_seconds": max(0.0, time.monotonic() - started_monotonic),
                    "verdict": "INCONCLUSIVE_RESULT_UNKNOWN_NO_REDISPATCH",
                    "raw_product_response_sha256": sha256(state.product_response_bytes),
                    "raw_provider_response_sha256": sha256(state.provider_response_bytes)
                    if state.provider_response_bytes
                    else None,
                    "product_dispatches": state.dispatches,
                    "provider_wires": state.provider_wires,
                }
        context["observed_gates"] = gates
        context["postflight_receipt"] = postflight
        context["postflight_late"] = postflight_late
        state.transition("postflight", postflight_status=postflight.get("status"), late=postflight_late)
        context["adapter_timeout_seconds"] = max(0.0, cleanup_deadline - time.monotonic())
        context["cleanup_timeout_seconds"] = min(GRACEFUL_CLEANUP_SECONDS, context["adapter_timeout_seconds"])
        cleanup = _call_cleanup_once(adapter, context, state)
        cleanup_after = time.monotonic()
        if cleanup.get("timed_out") is True or cleanup_after >= cleanup_deadline:
            context["timeout_receipt"] = {
                "task_id": TASK_ID,
                "attempt_id": attempt_id,
                "execution_binding_id": context["execution_binding_id"],
                "execution_binding_sha256": binding_start,
                "stage": "cleanup",
                "deadline_seconds": cleanup.get("timeout_seconds"),
                "deadline_elapsed_seconds": cleanup.get("elapsed_seconds"),
                "total_elapsed_seconds": max(0.0, cleanup_after - started_monotonic),
                "verdict": "INCONCLUSIVE_RESULT_UNKNOWN_NO_REDISPATCH",
                "raw_product_response_sha256": sha256(state.product_response_bytes),
                "raw_provider_response_sha256": sha256(state.provider_response_bytes)
                if state.provider_response_bytes
                else None,
                "product_dispatches": state.dispatches,
                "provider_wires": state.provider_wires,
            }
        context["cleanup_receipt"] = cleanup
        context["cleanup_observed_at"] = cleanup_after
        source_final = source_snapshot(root)
        cleanup_gate = _cleanup_gate(cleanup, postflight, postflight_late, cleanup_after, cleanup_deadline)
        source_final_matches = source_final.get("ready") is True and source_final.get("actual") == source_start
        gates["cleanup_owned_exit"] = cleanup_gate
        gates["protected_before_after"] = "PASS" if source_final_matches else "FAIL"
        gates["execution_binding_immutable"] = (
            "PASS"
            if cast(Path, context["binding_path"]).read_bytes() == cast(bytes, context["execution_binding_raw"])
            else "FAIL"
        )
        gates["deadline_stage_contract"] = (
            "FAIL"
            if product_dispatch_late
            or postflight_late
            or cleanup.get("timed_out") is True
            or cleanup_after >= cleanup_deadline
            else "PASS"
        )
        gates["postflight_deadline"] = "FAIL" if postflight_late else "PASS"
        gates["cleanup_deadline"] = (
            "FAIL" if cleanup.get("timed_out") is True or cleanup_after >= cleanup_deadline else "PASS"
        )
        if state.phase == "observed":
            state.transition("postflight", postflight_status=postflight.get("status"), late=postflight_late)
        if postflight_late or cleanup_after >= cleanup_deadline:
            gates["deadline_stage_contract"] = "FAIL"
        facts = {"gates": gates, "assistant_content": assistant_content}
        verdict = reduce_observation(facts, fixture_only=fixture_only)

        gates = cast(dict[str, str], verdict["gates"])
        if fixture_only:
            gates["semantic_counts"] = "FAIL_SEMANTIC"
            cast(dict[str, object], verdict["gates"])["semantic_counts"] = "FAIL_SEMANTIC"
        if gates["postflight_deadline"] == "FAIL" or gates["cleanup_deadline"] == "FAIL":
            verdict["verdict"] = "FAIL_MANDATORY_GATE"
            verdict["pass"] = False
        if cleanup_gate == "PASS" and gates["protected_before_after"] == "PASS":
            state.transition("cleaned", cleanup=cleanup, source_sha256_end=source_final.get("actual"))
        else:
            state.transition("cleanup_failed", cleanup=cleanup, source_sha256_end=source_final.get("actual"))
        result_verdict = (
            "INCONCLUSIVE_RESULT_UNKNOWN_NO_REDISPATCH"
            if context.get("timeout_receipt") is not None or postflight.get("status") == "ERROR"
            else verdict["verdict"]
            if gates["cleanup_owned_exit"] == "PASS"
            else "INCONCLUSIVE_CLEANUP_NOT_CONFIRMED"
        )
        attempt_result = {
            "task_id": TASK_ID,
            "attempt_id": attempt_id,
            "execution_binding_id": context["execution_binding_id"],
            "execution_binding_sha256": binding_start,
            "cleanup_receipt": cleanup,
            "postflight_receipt": postflight,
            "timeout_receipt": context.get("timeout_receipt"),
            "final_reducer_gates": gates,
            "logical_ids": {"product": product_id, "provider": f"provider:{product_id.split(':', 1)[1]}"},
            "verdict": result_verdict,
            "gates": gates,
            "semantic": verdict["semantic"],
            "real_observation_status": "NOT_RUN" if fixture_only else "OBSERVED",
            "source_sha256_start": source_start,
            "source_sha256_end": source_final.get("actual"),
            "request_sha256": context["request_sha256"],
            "provider_request_sha256": sha256(state.provider_request_bytes) if state.provider_request_bytes else None,
            "provider_response_sha256": sha256(upstream_body) if upstream_body else None,
            "product_response_sha256": sha256(state.product_response_bytes),
            "dispatches": state.dispatches,
            "provider_wires": state.provider_wires,
            "cleanup_calls": state.cleanup_calls,
        }
        timeout_receipt = context.get("timeout_receipt")
        if isinstance(timeout_receipt, Mapping):
            timeout_path = attempt_path / "timeout-receipt.json"
            if not timeout_path.exists():
                write_once(
                    timeout_path,
                    json.dumps(dict(timeout_receipt), ensure_ascii=False, indent=2).encode() + b"\n",
                )
        attempt_result_path = attempt_path / "attempt-result.json"
        if not attempt_result_path.exists():
            write_once(attempt_result_path, json.dumps(attempt_result, ensure_ascii=False, indent=2).encode() + b"\n")
        return {
            "verdict": result_verdict,
            "pass": verdict["pass"] and gates["cleanup_owned_exit"] == "PASS",
            "gates": gates,
            "semantic": verdict["semantic"],
            "real_observation_status": "NOT_RUN" if fixture_only else "OBSERVED",
            "state": state,
            "metadata": metadata,
            "readiness": readiness,
            "product_response": product_response,
            "upstream_sha256": sha256(upstream_body) if upstream_body else None,
            "product_sha256": sha256(state.product_response_bytes),
            "source_sha256_start": source_start,
            "source_sha256_end": source_final.get("actual"),
            "execution_binding_id": context["execution_binding_id"],
            "execution_binding_sha256": binding_start,
            "postflight": postflight,
            "cleanup": cleanup,
            "timeout_receipt": context.get("timeout_receipt"),
            "attempt_id": attempt_id,
            "dispatches": state.dispatches,
            "provider_wires": state.provider_wires,
            "cleanup_calls": state.cleanup_calls,
            "attempt_result": attempt_result,
        }
    except Exception as exc:
        context_obj = locals().get("context", {})
        failure_context: Mapping[str, object] = context_obj if isinstance(context_obj, Mapping) else {}
        timeout_receipt = failure_context.get("timeout_receipt")
        if isinstance(timeout_receipt, Mapping):
            state.error = f"TimeoutError: {timeout_receipt.get('stage', 'unknown')} exceeded deadline"
        else:
            state.error = f"{type(exc).__name__}: {exc}"
        state.events.append(
            {
                "at_utc": utc_now(),
                "phase": "exception",
                "error": state.error,
                "dispatches": state.dispatches,
                "provider_wires": state.provider_wires,
            }
        )
        failure_verdict = (
            "INCONCLUSIVE_RESULT_UNKNOWN_NO_REDISPATCH"
            if isinstance(timeout_receipt, Mapping) or state.dispatches
            else "INCONCLUSIVE_PREPARATION"
        )
        result = _finish_failure(failure_verdict, state, adapter, failure_context)
        result["error"] = state.error
        result["timeout_receipt"] = dict(timeout_receipt) if isinstance(timeout_receipt, Mapping) else None
        result["raw_response_preserved"] = {
            "product_bytes": len(state.product_response_bytes),
            "provider_bytes": len(state.provider_response_bytes),
            "product_sha256": sha256(state.product_response_bytes) if state.product_response_bytes else None,
            "provider_sha256": sha256(state.provider_response_bytes) if state.provider_response_bytes else None,
        }
        return result


def _mark_timeout(
    context: dict[str, object],
    state: SupervisorState,
    stage: str,
    started_monotonic: float,
    *,
    deadline: float | None = None,
) -> dict[str, object]:
    elapsed = max(0.0, time.monotonic() - started_monotonic)
    receipt: dict[str, object] = {
        "task_id": TASK_ID,
        "attempt_id": context.get("attempt_id"),
        "execution_binding_id": context.get("execution_binding_id"),
        "execution_binding_sha256": context.get("execution_binding_sha256"),
        "stage": stage,
        "deadline_seconds": (deadline - started_monotonic) if deadline is not None else TOTAL_DEADLINE_SECONDS,
        "deadline_elapsed_seconds": elapsed,
        "verdict": "INCONCLUSIVE_RESULT_UNKNOWN_NO_REDISPATCH"
        if state.dispatches or state.provider_wires
        else "INCONCLUSIVE_TIMEOUT_NO_DISPATCH",
        "product_dispatches": state.dispatches,
        "provider_wires": state.provider_wires,
        "raw_product_response_sha256": sha256(state.product_response_bytes) if state.product_response_bytes else None,
        "raw_provider_response_sha256": sha256(state.provider_response_bytes)
        if state.provider_response_bytes
        else None,
    }
    context["timeout_receipt"] = receipt
    state.events.append({"at_utc": utc_now(), "phase": "timeout", **receipt})
    return receipt


def _cleanup_gate(
    cleanup: Mapping[str, object],
    postflight: Mapping[str, object],
    postflight_late: bool,
    observed_at: float,
    deadline: float,
) -> str:
    if (
        cleanup.get("timed_out") is True
        or postflight_late
        or observed_at >= deadline
        or postflight.get("status") in {"ERROR", "NOT_CALLED_DEADLINE_EXPIRED"}
    ):
        return "INCONCLUSIVE"
    if cleanup.get("error") is not None or cleanup.get("owned_cleanup") is not True:
        return "FAIL"
    if cleanup.get("source") not in {"OFFLINE_FAKE", "OFFLINE_MOCK", "RUNTIME_OBSERVATION"}:
        return "INCONCLUSIVE"
    if type(cleanup.get("callback_calls")) is not int or cleanup.get("callback_calls") != 1:
        return "INCONCLUSIVE"
    if cleanup.get("worker_started") is not True:
        return "INCONCLUSIVE"
    if cleanup.get("exit_observation") != "OBSERVED" or type(cleanup.get("exit_code")) is not int:
        return "INCONCLUSIVE"
    if cleanup.get("reaped") is not True:
        return "INCONCLUSIVE"
    return "PASS"


def _call_cleanup_once(
    adapter: ObservationAdapter, context: Mapping[str, object], state: SupervisorState
) -> dict[str, object]:
    if state.cleanup_calls:
        if state.cleanup_receipt is None:
            raise RuntimeError("cleanup callback consumed without receipt; refusing retry")
        return state.cleanup_receipt
    started = time.monotonic()
    absolute = context.get("cleanup_deadline_monotonic")
    deadline = (
        min(float(absolute), started + GRACEFUL_CLEANUP_SECONDS)
        if isinstance(absolute, (int, float))
        else started + GRACEFUL_CLEANUP_SECONDS
    )
    cleanup_context = dict(context)
    cleanup_context["cleanup_timeout_seconds"] = max(0.0, deadline - started)
    cleanup_context["adapter_timeout_seconds"] = cleanup_context["cleanup_timeout_seconds"]
    state.cleanup_calls += 1
    result: dict[str, object]
    try:
        result = dict(adapter.cleanup(cleanup_context))
    except Exception as exc:
        result = {"owned_cleanup": False, "error": f"{type(exc).__name__}: {exc}"}
    finished = time.monotonic()
    result.update(
        {
            "callback_calls": state.cleanup_calls,
            "elapsed_seconds": max(0.0, finished - started),
            "timed_out": finished >= deadline,
            "timeout_seconds": cleanup_context["cleanup_timeout_seconds"],
        }
    )
    state.cleanup_receipt = result
    return result


def _finish_failure(
    verdict: str, state: SupervisorState, adapter: ObservationAdapter, context: Mapping[str, object]
) -> dict[str, object]:
    context_obj = context if isinstance(context, dict) else dict(context)
    existing_cleanup = state.cleanup_receipt or context_obj.get("cleanup_receipt")
    cleanup_required = context_obj.get("cleanup_required") is True
    if state.cleanup_calls and isinstance(existing_cleanup, Mapping):
        cleanup = dict(existing_cleanup)
    elif state.cleanup_calls:
        cleanup = {
            "owned_cleanup": False,
            "error": "cleanup result unavailable; refusing second callback",
            "callback_calls": state.cleanup_calls,
        }
    elif cleanup_required:
        cleanup = _call_cleanup_once(adapter, context_obj, state)
    else:
        cleanup = {
            "owned_cleanup": False,
            "status": "NOT_REQUIRED_WORKER_NOT_STARTED",
            "callback_calls": 0,
        }
    cleanup_observed_at = time.monotonic()
    context_obj["cleanup_receipt"] = cleanup
    context_obj["cleanup_observed_at"] = cleanup_observed_at
    binding_path = (
        cast(Path, context_obj["binding_path"]) if isinstance(context_obj.get("binding_path"), Path) else None
    )
    binding_unchanged = (
        binding_path is not None
        and binding_path.is_file()
        and sha256(binding_path.read_bytes()) == cast(str, context_obj.get("execution_binding_sha256", ""))
    )
    try:
        final_source = source_snapshot(cast(Path, context_obj.get("repository_root", resolve_repository_root())))
    except Exception:
        final_source = {"ready": False, "actual": {}}
    source_start_obj = context_obj.get("source_start", context_obj.get("source"))
    source_start = source_start_obj.get("actual") if isinstance(source_start_obj, Mapping) else None
    source_matches = (
        final_source.get("ready") is True
        and isinstance(source_start, Mapping)
        and final_source.get("actual") == source_start
    )
    postflight_obj = context_obj.get("postflight_receipt", {})
    postflight = postflight_obj if isinstance(postflight_obj, Mapping) else {}
    timeout_obj = context_obj.get("timeout_receipt")
    timeout_stage = timeout_obj.get("stage") if isinstance(timeout_obj, Mapping) else None
    postflight_late = context_obj.get("postflight_late") is True or timeout_stage == "postflight"
    cleanup_deadline_obj = context_obj.get("cleanup_deadline_monotonic")
    cleanup_deadline = cleanup_deadline_obj if isinstance(cleanup_deadline_obj, (int, float)) else cleanup_observed_at
    cleanup_gate = _cleanup_gate(cleanup, postflight, postflight_late, cleanup_observed_at, float(cleanup_deadline))
    deadline_failed = (
        isinstance(timeout_obj, Mapping)
        or "TIMEOUT" in verdict
        or postflight_late
        or cleanup.get("timed_out") is True
        or cleanup_observed_at >= float(cleanup_deadline)
    )
    previous_gates = context_obj.get("observed_gates", {})
    failure_gates = {
        name: str(previous_gates.get(name, "UNKNOWN")) if isinstance(previous_gates, Mapping) else "UNKNOWN"
        for name in REQUIRED_GATES
    }
    failure_gates.update(
        {
            "cleanup_owned_exit": cleanup_gate,
            "protected_before_after": "PASS" if source_matches else "FAIL",
            "execution_binding_immutable": "PASS" if binding_unchanged else "FAIL",
            "deadline_stage_contract": "FAIL" if deadline_failed else "INCONCLUSIVE",
            "postflight_deadline": "FAIL" if postflight_late else "INCONCLUSIVE",
            "cleanup_deadline": "FAIL"
            if cleanup.get("timed_out") is True or cleanup_observed_at >= float(cleanup_deadline)
            else "INCONCLUSIVE",
        }
    )
    if state.phase not in {"cleaned", "cleanup_failed"}:
        state.transition(
            "cleanup_failed",
            cleanup=cleanup,
            cleanup_gate=cleanup_gate,
            failure=verdict,
            source_sha256_end=final_source.get("actual"),
        )
    try:
        attempt_path = cast(Path, context_obj["attempts_root"]) / str(context_obj["attempt_id"])
        attempt_path.mkdir(parents=True, exist_ok=True)
        for filename, payload in (
            ("product-response.bin", state.product_response_bytes),
            ("provider-response.bin", state.provider_response_bytes),
        ):
            if payload and not (attempt_path / filename).exists():
                write_once(attempt_path / filename, payload)
        timeout_receipt = context_obj.get("timeout_receipt")
        if isinstance(timeout_receipt, Mapping):
            timeout_path = attempt_path / "timeout-receipt.json"
            if not timeout_path.exists():
                write_once(
                    timeout_path,
                    json.dumps(dict(timeout_receipt), ensure_ascii=False, indent=2).encode() + b"\n",
                )
        failed_result_path = attempt_path / "attempt-result.json"
        if not failed_result_path.exists():
            write_once(
                failed_result_path,
                json.dumps(
                    {
                        "task_id": TASK_ID,
                        "attempt_id": context.get("attempt_id"),
                        "execution_binding_id": context_obj.get("execution_binding_id"),
                        "execution_binding_sha256": context_obj.get("execution_binding_sha256"),
                        "verdict": verdict,
                        "failure": True,
                        "cleanup_receipt": cleanup,
                        "cleanup_gate": cleanup_gate,
                        "gates": failure_gates,
                        "final_reducer_gates": failure_gates,
                        "timeout_receipt": context_obj.get("timeout_receipt"),
                        "postflight_receipt": postflight,
                        "post_cleanup_source_sha256": final_source.get("actual"),
                        "cleanup_calls": state.cleanup_calls,
                        "dispatches": state.dispatches,
                        "provider_wires": state.provider_wires,
                        "provider_request_bytes": len(state.provider_request_bytes),
                        "provider_response_bytes": len(state.provider_response_bytes),
                        "product_request_bytes": len(state.product_request_bytes),
                        "product_response_bytes": len(state.product_response_bytes),
                        "provider_response_sha256": sha256(state.provider_response_bytes)
                        if state.provider_response_bytes
                        else None,
                        "product_response_sha256": sha256(state.product_response_bytes)
                        if state.product_response_bytes
                        else None,
                        "binding_unchanged": binding_unchanged,
                        "protected_before_after": failure_gates["protected_before_after"],
                        "source_sha256_start": dict(source_start) if isinstance(source_start, Mapping) else None,
                        "source_sha256_end": final_source.get("actual"),
                        "state_events": state.events,
                    },
                    ensure_ascii=False,
                    indent=2,
                ).encode()
                + b"\n",
            )
    except (OSError, ValueError, KeyError, TypeError):
        state.events.append({"at_utc": utc_now(), "phase": "failure-receipt-write-error"})
    return {
        "verdict": verdict,
        "pass": False,
        "state": state,
        "attempt_id": context_obj.get("attempt_id"),
        "cleanup_gate": cleanup_gate,
        "gates": failure_gates,
        "final_reducer_gates": failure_gates,
        "timeout_receipt": dict(timeout_obj) if isinstance(timeout_obj, Mapping) else None,
        "binding_unchanged": binding_unchanged,
        "source_sha256_end": final_source.get("actual"),
        "cleanup": cleanup,
        "dispatches": state.dispatches,
        "provider_wires": state.provider_wires,
        "cleanup_calls": state.cleanup_calls,
        "phase": state.phase,
    }


class OfflineAdapter:
    """Deterministic in-memory terminal adapter; makes no product/network/process call."""

    def __init__(
        self,
        *,
        response: str = "offline-stub-only",
        fail_at: str | None = None,
        metadata_digest: str = APPROVED_MODEL_DIGEST,
    ):
        self.response = response
        self.fail_at = fail_at
        self.metadata_digest = metadata_digest
        self.events: list[str] = []
        self.product_calls = 0
        self.provider_calls = 0
        self.cleaned = False
        self.raw_request = b""
        self.raw_upstream = b""

    def _stage(self, name: str) -> None:
        self.events.append(name)
        if self.fail_at == name:
            raise RuntimeError(f"injected {name} failure")

    def bootstrap(self, context: Mapping[str, object]) -> Mapping[str, object]:
        self._stage("bootstrap")
        return {"worker_owned": False, "auth_state_owned": True, "auth_token_value_recorded": False}

    def readiness(self, context: Mapping[str, object]) -> Mapping[str, object]:
        self._stage("readiness")
        return {"unauthenticated_status": 401, "bearer_status": 200, "ready": True, "source": "OFFLINE_FIXTURE"}

    def metadata(self, context: Mapping[str, object]) -> Mapping[str, object]:
        self._stage("metadata")
        return {
            "complete": True,
            "version": {"version": "fixture-only"},
            "tags": {"models": [{"name": MODEL_REPO, "digest": self.metadata_digest}]},
            "show": {"capabilities": ["vision"]},
            "model_repo": MODEL_REPO,
            "model_digest": self.metadata_digest,
            "capabilities": ["vision"],
            "source": "OFFLINE_FIXTURE",
            "ollama_origin": "http://127.0.0.1:11434",
        }

    def dispatch_product(
        self,
        context: Mapping[str, object],
        provider_wire: Callable[[bytes, Callable[[], tuple[bytes, int, Mapping[str, str]]]], Mapping[str, object]],
    ) -> Mapping[str, object]:
        self._stage("dispatch")
        self.product_calls += 1
        req = cast(bytes, context["product_request_bytes"])
        if sha256(req) != context["request_sha256"]:
            raise ValueError("product request bytes are not the frozen reservation bytes")
        payload = strict_json_loads(req)
        if not isinstance(payload, dict):
            raise ValueError("frozen product request must be a JSON object")
        product_id = cast(str, context["product_logical_id"])
        # This body matches current provider's source-bound, non-streaming native builder.
        provider_body_obj = {
            "model": MODEL_ALIAS,
            "stream": False,
            "keep_alive": "30m",
            "think": False,
            "options": {"num_ctx": 32768, "num_predict": 128, "temperature": 0.0, "repeat_penalty": 1.0, "min_p": 0.0},
            "messages": [
                {"role": "system", "content": EXPECTED_UPSTREAM_SYSTEM},
                {
                    "role": "user",
                    "content": PROMPT_PREFIX + QUESTION,
                    "images": [base64.b64encode(cast(bytes, context["image"])).decode("ascii")],
                },
            ],
        }
        self.raw_request = canonical_json(provider_body_obj)
        acceptance = classify_upstream_request("http://127.0.0.1:11434/api/chat", "POST", self.raw_request)
        if acceptance != "ollama_chat_inference_wire":
            raise RuntimeError("offline generated provider request rejected")
        self.raw_upstream = canonical_json({"message": {"role": "assistant", "content": self.response}, "done": True})
        send_calls = 0

        def send() -> tuple[bytes, int, Mapping[str, str]]:
            nonlocal send_calls
            send_calls += 1
            self.provider_calls += 1
            if send_calls != 1:
                raise RuntimeError("offline provider adapter forbids retry")
            return self.raw_upstream, 200, {"content-type": "application/json"}

        lineage = provider_wire(self.raw_request, send)
        product_body = canonical_json(
            {
                "choices": [{"message": {"role": "assistant", "content": self.response}, "finish_reason": "stop"}],
                "model": MODEL_ALIAS,
            }
        )
        return {
            "status": 200,
            "content_type": "application/json",
            "raw_body": product_body,
            "upstream_status": lineage["status"],
            "upstream_content_type": lineage["content_type"],
            "provider_contract_pass": True,
            "product_logical_id": product_id,
            "provider_logical_id": lineage["logical_id"],
            "retry_wires": 0,
            "redirect_wires": 0,
            "native_wires": 0,
            "tool_calls": 0,
            "owned_cleanup": True,
            "worker_exit": "FIXTURE_NOT_STARTED",
            "source_sha256_before_wire": cast(dict[str, object], context["source"])["actual"],
            "request_sha256_before_wire": context["request_sha256"],
            "source": "OFFLINE_FIXTURE",
        }

    def postflight(self, context: Mapping[str, object]) -> Mapping[str, object]:
        self._stage("postflight")
        return {"status": "NOT_RUN_OFFLINE"}

    def cleanup(self, context: Mapping[str, object]) -> Mapping[str, object]:
        self.cleaned = True
        self.events.append("cleanup")
        if context.get("cleanup_required") is not True:
            return {"owned_cleanup": False, "status": "NOT_REQUIRED_WORKER_NOT_STARTED", "source": "OFFLINE_FAKE"}
        return {
            "owned_cleanup": True,
            "worker_started": False,
            "exit_observation": "NOT_OBSERVED",
            "reaped": False,
            "source": "OFFLINE_FAKE",
        }


def install_cold_guards() -> dict[str, int]:
    """Install deny guards before any pytest collection or product import."""
    counters = {"socket_connect": 0, "socket_bind": 0, "socket_listen": 0, "worker_dispatch": 0}

    def denied(name: str):
        def guard(*_args: object, **_kwargs: object):
            counters[name] += 1
            raise RuntimeError(f"blocked before {name.replace('_', ' ')}")

        return guard

    for method, counter in (
        ("connect", "socket_connect"),
        ("connect_ex", "socket_connect"),
        ("bind", "socket_bind"),
        ("listen", "socket_listen"),
        ("sendall", "socket_connect"),
    ):
        setattr(socket.socket, method, denied(counter))
    setattr(socket, "create_connection", denied("socket_connect"))
    setattr(subprocess, "Popen", denied("worker_dispatch"))

    return counters


def dispatch_owned_worker(
    argv: Sequence[str], *, popen: Callable[..., object] | None = None, allow_live: bool = False
) -> object:
    """A worker can start only through a separately approved live adapter."""
    if not allow_live or popen is None:
        raise RuntimeError("blocked before worker dispatch")
    return popen(list(argv), stdin=subprocess.DEVNULL, start_new_session=True)


def build_execution_receipt(
    *,
    argv: Sequence[str],
    cwd: Path,
    started: str,
    finished: str,
    exit_code: int | None,
    env_delta: Mapping[str, str],
    source_sha256: Mapping[str, str],
) -> dict[str, object]:
    return {
        "argv": list(argv),
        "cwd": str(cwd),
        "started_at_utc": started,
        "finished_at_utc": finished,
        "exit_code": exit_code,
        "env_changed_names": sorted(env_delta),
        "source_sha256": dict(source_sha256),
    }


def precheck_before_pytest(
    root: Path, *, expected_source: Mapping[str, str], expected_request_sha256: str | None = None
) -> dict[str, object]:
    """stdlib-only drift check; caller must do this before pytest import/collection."""
    run = Path(__file__).resolve().parent
    before = source_snapshot(root)
    request_path = run / "request.json"
    request_ok = expected_request_sha256 is None or (
        request_path.is_file() and sha256(request_path.read_bytes()) == expected_request_sha256
    )
    source_ok = dict(expected_source) == SOURCE_EXPECTATIONS and all(
        cast(dict[str, str], before["actual"]).get(path) == digest for path, digest in SOURCE_EXPECTATIONS.items()
    )
    fixture_path = run / "fixture/vision_shapes_384x256.png.b64"
    fixture_ok = fixture_path.is_file() and sha256(fixture_path.read_bytes()) == B64_SHA256
    binding_ok = False
    binding_error: str | None = None
    binding_sha256: str | None = None
    try:
        if (
            request_path.is_file()
            and (run / "request.binding.json").is_file()
            and (run / "execution-binding.json").is_file()
        ):
            _binding, binding_raw, _sources = validate_execution_binding(
                run, root, request_raw=request_path.read_bytes()
            )
            binding_ok = True
            binding_sha256 = sha256(binding_raw)
        else:
            binding_error = "execution/request binding or request is missing"
    except (OSError, ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        binding_error = f"{type(exc).__name__}: {exc}"
    status = "READY" if source_ok and fixture_ok and request_ok and binding_ok else "INCONCLUSIVE_SOURCE_DRIFT"
    report: dict[str, object] = {
        "status": status,
        "pytest_started": False,
        "product_imported": False,
        "selected_case_skipped": False,
        "source": before,
        "fixture_sha256": sha256(fixture_path.read_bytes()) if fixture_path.is_file() else None,
        "request_sha256": sha256(request_path.read_bytes()) if request_path.is_file() else None,
        "request_binding_ok": binding_ok,
        "execution_binding_sha256": binding_sha256,
        "binding_error": binding_error,
    }
    if status != "READY":
        blocked_path = run / "precheck-blocked.json"
        if not blocked_path.exists():
            write_once(blocked_path, json.dumps(report, ensure_ascii=False, indent=2).encode() + bytes([10]))
    return report


def run_cold_pytest(
    root: Path,
    selector: Path,
    *,
    expected_source: Mapping[str, str],
    expected_request_sha256: str,
    state_root: Path,
    parent_invocation_id: str | None = None,
    parent_capture_id: str | None = None,
    owned_output_path: Path | None = None,
) -> int:
    """Cold entry; no conftest/plugin/product imports precede the stdlib gates."""
    invocation = owned_output_path or Path(__file__).resolve().parent / "attempts" / f"selector-exec-{uuid.uuid4().hex}"
    attempts_root = (Path(__file__).resolve().parent / "attempts").resolve()
    invocation = invocation.resolve()
    if invocation.parent != attempts_root or invocation.exists():
        raise ValueError("child invocation output must be a new, directly-owned attempts directory")
    if not all(isinstance(value, str) and value for value in (parent_invocation_id, parent_capture_id)):
        raise ValueError("explicit parent/capture invocation identities are required")
    invocation.mkdir(parents=True, exist_ok=False)
    if parent_capture_id is None:
        raise ValueError("explicit parent capture identity is required")
    parent_capture = attempts_root / parent_capture_id
    parent_record = parent_capture / "capture-start.json"
    if parent_capture.parent != attempts_root or not parent_record.is_file():
        raise ValueError("explicit parent capture-start receipt is missing or not owned")
    parent_record_raw = parent_record.read_bytes()
    parent_receipt_sha256 = sha256(parent_record_raw)
    supplied_parent_sha = os.environ.get("IMP09C_PARENT_CAPTURE_START_SHA256")
    if supplied_parent_sha != parent_receipt_sha256:
        raise ValueError("parent capture-start receipt SHA differs from caller-bound dispatch input")
    parent_start = strict_json_loads(parent_record_raw)
    if (
        not isinstance(parent_start, dict)
        or parent_start.get("capture_id") != parent_capture_id
        or parent_start.get("invocation_id") != parent_invocation_id
    ):
        raise ValueError("parent capture-start identity mismatch")
    parent_dispatch_path = parent_capture / "parent-dispatch.json"
    if not parent_dispatch_path.is_file() or parent_dispatch_path.is_symlink():
        raise ValueError("explicit parent dispatch record is missing")
    parent_dispatch_raw = parent_dispatch_path.read_bytes()
    parent_dispatch_obj = strict_json_loads(parent_dispatch_raw)
    if not isinstance(parent_dispatch_obj, dict):
        raise ValueError("parent dispatch receipt is not an object")
    parent_dispatch_sha256 = sha256(parent_dispatch_raw)
    if os.environ.get("IMP09C_PARENT_DISPATCH_SHA256") != parent_dispatch_sha256:
        raise ValueError("caller-bound parent dispatch SHA mismatch")
    if (
        parent_dispatch_obj.get("parent_invocation_id") != parent_invocation_id
        or parent_dispatch_obj.get("parent_capture_id") != parent_capture_id
        or parent_dispatch_obj.get("parent_capture_start_sha256") != parent_receipt_sha256
    ):
        raise ValueError("parent dispatch identity or capture-start binding mismatch")
    expected_nodeids = parent_dispatch_obj.get("expected_nodeids")
    source_sha256_at_dispatch = parent_dispatch_obj.get("source_sha256_at_dispatch")
    if not isinstance(expected_nodeids, list) or any(not isinstance(node, str) for node in expected_nodeids):
        raise ValueError("parent dispatch expected-node inventory is missing")
    implementation_source_sha256 = {
        name: sha256((Path(__file__).resolve().parent / name).read_bytes()) for name in IMPLEMENTATION_SOURCE_NAMES
    }
    if not isinstance(source_sha256_at_dispatch, dict):
        raise ValueError("parent dispatch source inventory is missing")
    if any(
        source_sha256_at_dispatch.get(str((Path(__file__).resolve().parent / name).relative_to(root))) != source_hash
        for name, source_hash in implementation_source_sha256.items()
    ):
        raise ValueError("implementation sources drifted after parent dispatch")
    dispatch_sources = {
        str((Path(__file__).resolve().parent / name).relative_to(root)): source_hash
        for name, source_hash in implementation_source_sha256.items()
    }
    if source_sha256_at_dispatch != dispatch_sources:
        raise ValueError("parent dispatch source inventory must match the complete implementation inventory")
    owned_output_path_rel = invocation.relative_to(Path(__file__).resolve().parent).as_posix()
    selector_sha256_at_dispatch = sha256(selector.read_bytes())
    harness_sha256_at_dispatch = sha256(Path(__file__).read_bytes())
    dispatch_started_at = utc_now()
    dispatch_argv = [
        sys.executable,
        "-B",
        str(Path(__file__).resolve()),
        "--offline-tests",
        str(selector),
        str(state_root),
    ]
    dispatch_path = invocation / "dispatch.json"
    child_dispatch = {
        "argv": dispatch_argv,
        "cwd": str(root),
        "started_at_utc": dispatch_started_at,
        "harness_sha256_at_dispatch": harness_sha256_at_dispatch,
        "selector_sha256_at_dispatch": selector_sha256_at_dispatch,
        "source_sha256_at_dispatch": dispatch_sources,
        "expected_nodeids": expected_nodeids,
        "parent_invocation_id": parent_invocation_id,
        "parent_capture_id": parent_capture_id,
        "parent_capture_start_sha256": parent_receipt_sha256,
        "parent_dispatch_sha256": parent_dispatch_sha256,
        "child_invocation_id": invocation.name,
        "owned_output_path": owned_output_path_rel,
    }
    dispatch_path.write_text(
        json.dumps(child_dispatch, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if not parent_capture_id or child_dispatch.get("parent_dispatch_sha256") != parent_dispatch_sha256:
        raise ValueError("caller-bound parent dispatch SHA mismatch")
    dispatch_sha256 = sha256(dispatch_path.read_bytes())
    child_started_at = dispatch_started_at

    def finish_child(status_code: int) -> int:
        completion = {
            "parent_invocation_id": parent_invocation_id,
            "parent_capture_id": parent_capture_id,
            "parent_capture_start_sha256": parent_receipt_sha256,
            "parent_dispatch_sha256": parent_dispatch_sha256,
            "child_invocation_id": invocation.name,
            "owned_output_path": owned_output_path_rel,
            "dispatch_sha256": dispatch_sha256,
            "source_sha256_at_dispatch": dispatch_sources,
            "expected_nodeids": expected_nodeids,
            "started_at_utc": child_started_at,
            "finished_at_utc": utc_now(),
            "exit_code": int(status_code),
        }
        (invocation / "completion.json").write_text(
            json.dumps(completion, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return int(status_code)

    (invocation / "parent-link.json").write_text(
        json.dumps(
            {
                "parent_invocation_id": parent_invocation_id,
                "parent_capture_id": parent_capture_id,
                "parent_capture_start_sha256": parent_receipt_sha256,
                "parent_dispatch_sha256": parent_dispatch_sha256,
                "child_invocation_id": invocation.name,
                "owned_output_path": owned_output_path_rel,
                "source_sha256_at_dispatch": dispatch_sources,
                "expected_nodeids": expected_nodeids,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    report = precheck_before_pytest(
        root, expected_source=expected_source, expected_request_sha256=expected_request_sha256
    )
    source_report = report.get("source")
    actual_source = source_report.get("actual") if isinstance(source_report, dict) else None
    report = {
        **report,
        "attempt_id": invocation.name,
        "selector_sha256": sha256(selector.read_bytes()),
        "source_sha256_at_gate": cast(dict[str, str], actual_source),
        "source_sha256_at_dispatch": dispatch_sources,
        "expected_nodeids": expected_nodeids,
    }
    (invocation / "precheck.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if report["status"] != "READY":
        return finish_child(3)
    if selector.resolve() != (Path(__file__).resolve().parent / "test_runtime_final_gate_contract.py").resolve():
        return finish_child(3)
    state_root.mkdir(parents=True, exist_ok=True)
    isolated_environment = isolate_worker_environment(state_root, root)
    os.environ.clear()
    os.environ.update(isolated_environment)
    protected_test_paths = json.loads(os.environ.get("IMP09C_PROTECTED_TEST_PATHS", "[]"))
    if not isinstance(protected_test_paths, list) or any(not isinstance(item, str) for item in protected_test_paths):
        return finish_child(3)
    protected_hashes = {
        item: sha256((root / item).read_bytes()) if (root / item).is_file() else None for item in protected_test_paths
    }
    config_path = state_root / "config" / "owned-config.yaml"
    if not config_path.exists():
        write_once(config_path, (root / "config.yaml").read_bytes())
    os.environ["AGK_CONFIG_FILE"] = str(config_path)
    os.chdir(state_root)
    counters = install_cold_guards()
    prepare_owned_request(root, Path(__file__).resolve().parent, state_root)
    bound_request = request_gate(Path(__file__).resolve().parent, root)
    if bound_request["request_sha256"] != expected_request_sha256:
        return finish_child(3)
    import pytest

    (invocation / "pytest-started.json").write_text(
        json.dumps(
            {
                "started_at_utc": utc_now(),
                "selector": str(selector),
                "selector_sha256": sha256(selector.read_bytes()),
                "guard_counters_before": dict(counters),
                "source_sha256_at_dispatch": dispatch_sources,
                "expected_nodeids": expected_nodeids,
                "parent_invocation_id": parent_invocation_id,
                "parent_capture_id": parent_capture_id,
                "child_invocation_id": invocation.name,
                "dispatch_sha256": dispatch_sha256,
                "execution_binding_sha256": bound_request["execution_binding_sha256"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    selected_ids = (
        "imp09c_fg_"
        if os.environ.get("IMP09C_SELECTOR_SCOPE") == "final-gate-only"
        else "imp09c_rc_"
        if os.environ.get("IMP09C_FORCE_NEW_SELECTOR") == "1"
        else "imp09c_rb_"
    )
    started_nodeids: list[str] = []

    class SelectorResult:
        def pytest_runtest_logstart(self, nodeid: str, location: object) -> None:
            started_nodeids.append(nodeid)

    code = pytest.main(
        [
            str(selector),
            "-k",
            selected_ids,
            "-q",
            "-p",
            "no:cacheprovider",
            "-p",
            "no:randomly",
            "--basetemp",
            str(invocation / "fixtures"),
            "--junitxml",
            str(invocation / "junit.xml"),
        ],
        plugins=[SelectorResult()],
    )
    receipt = {
        "finished_at_utc": utc_now(),
        "exit_code": int(code),
        "guard_counters": counters,
        "product_imported": any(
            name.startswith("antigravity_k.api") or name.startswith("antigravity_k.engine") for name in sys.modules
        ),
        "pytest_started": True,
        "selector": str(selector),
        "selector_sha256": sha256(selector.read_bytes()),
        "selected_nodeids": started_nodeids,
        "started_at_utc": child_started_at,
        "precheck_status": report["status"],
        "execution_binding_sha256": bound_request["execution_binding_sha256"],
        "parent_invocation_id": parent_invocation_id,
        "parent_capture_id": parent_capture_id,
        "child_invocation_id": invocation.name,
        "dispatch_sha256": dispatch_sha256,
    }
    receipt["source_sha256_at_dispatch"] = dispatch_sources
    receipt["expected_nodeids"] = expected_nodeids
    (invocation / "pytest-result.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    after_protected_hashes = {
        item: sha256((root / item).read_bytes()) if (root / item).is_file() else None for item in protected_test_paths
    }
    violations = [item for item in protected_test_paths if protected_hashes[item] != after_protected_hashes[item]]
    (invocation / "state-guard.json").write_text(
        json.dumps(
            {
                "protected_paths": protected_test_paths,
                "before_sha256": protected_hashes,
                "after_sha256": after_protected_hashes,
                "violations": violations,
                "guard_counters": counters,
                "source_sha256_at_dispatch": dispatch_sources,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    if violations:
        return finish_child(5)
    if any(counters.values()):
        return finish_child(4)
    return finish_child(int(code))


def prepare_owned_request(root: Path, run: Path, state: Path, *, new_candidate: bool = False) -> dict[str, object]:
    """Create/validate owned request inputs; rebinding requires an explicit new-candidate invocation."""
    if (run / "execution-binding.json").exists() and not new_candidate:
        context = request_gate(run, root)
        return {
            "request": context["request"],
            "request_sha256": context["request_sha256"],
            "image_sha256": sha256(cast(bytes, context["image"])),
            "project_id": cast(dict[str, object], context["request"])["project_id"],
        }
    fixture_source = (
        root
        / "docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP09C-PRODUCT-VISION-HARNESS-READY-01/run-20261012T042113Z-ca049d74-d50e-43b1-8c15-317f2e3cf53e/fixture/vision_shapes_384x256.png.b64"
    )
    fixture_target = run / "fixture/vision_shapes_384x256.png.b64"
    run.mkdir(parents=True, exist_ok=True)
    if not fixture_target.exists():
        write_once(fixture_target, fixture_source.read_bytes())
    image, encoded = load_image(run)
    owned_state = run / "offline-state"
    registry_path = owned_state / "registry/projects.json"
    workspace = owned_state / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    if registry_path.exists():
        projects = strict_json_loads(registry_path.read_bytes())
        if not isinstance(projects, list):
            raise ValueError("owned registry schema invalid")
        matches = [
            item
            for item in projects
            if isinstance(item, dict)
            and item.get("name") == "imp09c-product-vision"
            and item.get("path") == str(workspace.resolve())
        ]
        if len(matches) != 1:
            raise ValueError("owned registry identity missing or ambiguous; refusing repair")
        project_id = str(matches[0]["id"])
    else:
        if (run / "execution-binding.json").exists():
            raise ValueError("binding exists without owned registry; refusing repair")
        project_id = "proj_" + uuid.uuid4().hex[:8]
        write_once(
            registry_path,
            canonical_json(
                [
                    {
                        "id": project_id,
                        "name": "imp09c-product-vision",
                        "path": str(workspace.resolve()),
                        "is_active": True,
                        "last_accessed_at": None,
                        "tasks": [],
                    }
                ]
            ),
        )
    request = build_request(project_id, encoded)
    request_bytes = canonical_json(request)
    request_path = run / "request.json"
    if (run / "execution-binding.json").is_file() and not request_path.is_file():
        raise ValueError("frozen execution binding exists but request file is missing")
    if request_path.exists() and request_path.read_bytes() != request_bytes:
        if not new_candidate:
            raise ValueError("existing request/project identity differs; refusing automatic rebind")
        archive = run / "request-candidate-3.json"
        if archive.exists() and archive.read_bytes() != request_path.read_bytes():
            raise ValueError("existing request archive differs; refusing candidate transition")
        if not archive.exists():
            write_once(archive, request_path.read_bytes())
        temporary = run / f".request-{uuid.uuid4().hex}.tmp"
        write_once(temporary, request_bytes)
        os.replace(temporary, request_path)
    elif not request_path.exists():
        write_once(request_path, request_bytes)

    binding = {
        "task_id": TASK_ID,
        "project_id": project_id,
        "project_registry_path": registry_path.relative_to(run).as_posix(),
        "project_workspace": workspace.relative_to(run).as_posix(),
        "fixture_b64_sha256": B64_SHA256,
        "fixture_png_sha256": IMAGE_SHA256,
        "question": QUESTION,
        "request_sha256": sha256(request_bytes),
    }
    binding_path = run / "request.binding.json"
    binding_bytes = json.dumps(binding, ensure_ascii=False, indent=2).encode() + bytes([10])

    if (run / "execution-binding.json").is_file() and not binding_path.is_file():
        raise ValueError("frozen execution binding exists but request binding is missing")
    if binding_path.exists() and binding_path.read_bytes() != binding_bytes:
        if not new_candidate:
            raise ValueError("existing request binding differs; refusing automatic rebind")
        archive = run / "request.binding-candidate-3.json"
        if archive.exists() and archive.read_bytes() != binding_path.read_bytes():
            raise ValueError("existing request binding archive differs; refusing candidate transition")
        if not archive.exists():
            write_once(archive, binding_path.read_bytes())
        temporary = run / f".request-binding-{uuid.uuid4().hex}.tmp"
        write_once(temporary, binding_bytes)
        os.replace(temporary, binding_path)
    elif not binding_path.exists():
        write_once(binding_path, binding_bytes)
    execution_binding_path = run / "execution-binding.json"
    if execution_binding_path.exists():
        if new_candidate:
            freeze_execution_binding(run, root, supersede_existing=True)
        else:
            request_gate(run, root)
    else:
        freeze_execution_binding(run, root)
    return {
        "request": request,
        "request_sha256": sha256(request_bytes),
        "image_sha256": sha256(image),
        "project_id": project_id,
        "registry_path": str(registry_path),
        "workspace": str(workspace),
    }


def write_capture_pair(attempt: Path, logical_id: str, request: bytes, response: bytes) -> dict[str, object]:
    request_path = attempt / f"{logical_id}-request.bin"
    response_path = attempt / f"{logical_id}-response.bin"
    write_once(request_path, request)
    write_once(response_path, response)
    return {
        "logical_id": logical_id,
        "request": {"path": request_path.name, "bytes": len(request), "sha256": sha256(request)},
        "response": {"path": response_path.name, "bytes": len(response), "sha256": sha256(response)},
    }


def aggregate_scoped_counts(invocation: Path, parent: Path, task_history: Mapping[str, object]) -> dict[str, object]:
    def count(path: Path) -> int:
        return len(list(path.rglob("*-request.bin")))

    previous_total = task_history.get("previous_actual_total", "UNKNOWN")
    if previous_total == "UNKNOWN":
        current_total: object = count(invocation)
    elif isinstance(previous_total, int) and not isinstance(previous_total, bool) and previous_total >= 0:
        current_total = previous_total + count(invocation)
    else:
        raise ValueError("retained historical request count must be a nonnegative integer or UNKNOWN")
    retained = {"previous_actual_total": previous_total, "current_invocation_total": current_total}
    return {
        "invocation": {"logical_count": count(invocation)},
        "parent_cumulative": {"logical_count": count(parent)},
        "task_retained_history": retained,
    }


def load_protected_before(path: Path) -> dict[str, object]:
    baseline = json.loads(path.read_text(encoding="utf-8"))
    return {item["path"]: item for item in baseline["protected_files"]}


def protected_snapshot(root: Path, protected: Mapping[str, Mapping[str, object]]) -> dict[str, object]:
    rows = []
    for rel, _record in protected.items():
        path = root / rel
        if not path.is_file():
            rows.append({"path": rel, "exists": False})
            continue
        raw = path.read_bytes()
        rows.append(
            {
                "path": rel,
                "exists": True,
                "bytes": len(raw),
                "sha256": sha256(raw),
                "mode": oct(path.stat().st_mode & 0o777),
            }
        )
    return {"captured_at_utc": utc_now(), "files": rows}


def compare_protected(before: Mapping[str, Mapping[str, object]], after: Mapping[str, object]) -> dict[str, object]:
    after_rows = {cast(str, row["path"]): row for row in cast(list[dict[str, object]], after["files"])}
    changed = []
    for rel, record in before.items():
        current = after_rows.get(rel, {})
        if record != current:
            changed.append({"path": rel, "before": dict(record), "after": dict(current)})
    return {"changed": changed, "protected_files": list(before), "protected_file_count": len(before)}


def no_prior_run_mutation(start_record: Path) -> bool:
    baseline = json.loads(start_record.read_text(encoding="utf-8"))
    root = Path(str(baseline.get("root", "")))
    if not root.is_absolute():
        root = start_record.resolve().parents[7]
    if not root.is_dir() or not (root / "src/antigravity_k").is_dir():
        root = resolve_repository_root(start_record)
    return all(
        (root / path["path"]).is_file() and sha256((root / path["path"]).read_bytes()) == path["sha256"]
        for path in baseline.get("existing_prior_run_inventory", [])
        if path.get("exists", True)
    )


class ProviderWireGuard:
    """One durable provider entry shared by callbacks and the child observer."""

    def __init__(
        self,
        run: Path,
        root: Path,
        journal: OneShotJournal,
        product_id: str,
        deadline: float,
        clock: Callable[[], float],
    ):
        self.run, self.root, self.journal = run, root, journal
        self.product_id, self.deadline, self.clock = product_id, deadline, clock

    def enter(self, raw: bytes, *, url: str = "http://127.0.0.1:11434/api/chat") -> tuple[str, str]:
        request_gate(self.run, self.root)
        if self.clock() >= self.deadline:
            raise TimeoutError("provider deadline expired before wire guard")
        slot = classify_upstream_request(url, "POST", raw)
        logical_id = "provider:" + self.product_id.split(":", 1)[1]
        if not self.journal.reserve(slot, logical_id, raw):
            raise RuntimeError("provider reservation denied before sink")
        if self.clock() >= self.deadline:
            raise TimeoutError("provider deadline expired after reservation")
        if not self.journal.enter_wire(slot, logical_id, raw):
            raise RuntimeError("provider terminal wire denied")
        return slot, logical_id


def runtime_authorization_descriptor(run: Path, root: Path) -> dict[str, object]:
    binding, raw, _ = validate_execution_binding(run, root)
    return {
        "status": "APPROVED_FOR_SEPARATE_LIVE_OBSERVATION",
        "scope": FUTURE_TASK_ID,
        "preparation_task": TASK_ID,
        "candidate_id": binding["attempt_id"],
        "binding_sha256": sha256(raw),
        "request_sha256": binding["request_sha256"],
        "fixture_png_sha256": IMAGE_SHA256,
        "model": MODEL_REPO,
        "model_digest": APPROVED_MODEL_DIGEST,
        "budget_sha256": binding["budget_sha256"],
        "independent_review": "ACCEPTED_OFFLINE_RUNTIME_BRIDGE",
        "revoked": False,
    }


def verify_runtime_authorization(run: Path, root: Path, descriptor: object, *, mode: str) -> dict[str, object] | None:
    if not isinstance(descriptor, Mapping) or mode not in {"LIVE", "OFFLINE_MOCK"}:
        return None
    expected = runtime_authorization_descriptor(run, root)
    if any(
        descriptor.get(key) != value or type(descriptor.get(key)) is not type(value) for key, value in expected.items()
    ):
        return None
    if descriptor.get("fixture_only") is not (mode == "OFFLINE_MOCK"):
        return None
    try:
        issued = datetime.fromisoformat(str(descriptor["issued_at"]))
        expires = datetime.fromisoformat(str(descriptor["expires_at"]))
        if issued.tzinfo is None or expires.tzinfo is None or not issued <= datetime.now(UTC) < expires:
            return None
    except (ValueError, KeyError):
        return None
    if mode == "LIVE":
        contract = strict_json_loads((run / "runtime-bridge-contract.json").read_bytes())
        if not isinstance(contract, dict):
            return None
        approval_path = (root / str(contract["approval_file"])).resolve()
        review_path = (root / str(contract["review_file"])).resolve()
        if root.resolve() not in approval_path.parents or root.resolve() not in review_path.parents:
            return None
        if not approval_path.is_file() or not review_path.is_file():
            return None
        trusted = strict_json_loads(approval_path.read_bytes())
        review = strict_json_loads(review_path.read_bytes())
        if trusted != dict(descriptor) or not isinstance(review, dict):
            return None
        if (
            review.get("verdict") != "ACCEPTED_OFFLINE_RUNTIME_BRIDGE"
            or review.get("execution_binding_sha256") != expected["binding_sha256"]
            or descriptor.get("review_sha256") != sha256(review_path.read_bytes())
        ):
            return None
    return {"status": "VERIFIED_RUNTIME_AUTHORIZATION", "scope": TASK_ID, "mode": mode, "descriptor": dict(descriptor)}


def evidence_json(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"bytes": len(value), "sha256": sha256(value)}
    if isinstance(value, Mapping):
        return {str(key): evidence_json(item) for key, item in value.items() if key != "state"}
    if isinstance(value, (list, tuple)):
        return [evidence_json(item) for item in value]
    return value


def runtime_cli(
    argv: Sequence[str],
    *,
    run: Path | None = None,
    root: Path | None = None,
    authorization_loader: Callable[[], object] | None = None,
    resources: Any = None,
) -> int:
    """Factory is reached only after stdlib binding and multi-field authority checks."""
    args = list(argv)
    run = run or Path(__file__).resolve().parent
    root = root or resolve_repository_root()
    if "--worker" in args:
        print(json.dumps({"status": "REFUSED_DIRECT_WORKER", "adapter_constructed": False}))
        return 3
    mode = "OFFLINE_MOCK" if "--mock-runtime" in args else "LIVE"
    try:
        validate_execution_binding(run, root)
        if authorization_loader is not None:
            if mode != "OFFLINE_MOCK" or resources is None or resources.mock is not True:
                raise PermissionError("fixture loader cannot authorize actual CLI")
            descriptor = authorization_loader()
        else:
            contract = strict_json_loads((run / "runtime-bridge-contract.json").read_bytes())
            approval_file = contract.get("approval_file") if isinstance(contract, dict) else None
            path = root / approval_file if isinstance(approval_file, str) else None
            descriptor = strict_json_loads(path.read_bytes()) if path is not None and path.is_file() else None

        authorization = verify_runtime_authorization(run, root, descriptor, mode=mode)
        if authorization is None:
            raise PermissionError("live authorization NOT_ISSUED or mismatched scope/candidate")
        if mode == "OFFLINE_MOCK" and (resources is None or resources.mock is not True):
            raise PermissionError("offline mode requires explicit mocked resources")
        runtime_adapter = importlib.import_module("runtime_adapter")

        journal = OneShotJournal(run / "task-wire-journal.jsonl")
        adapter = runtime_adapter.concrete_adapter_factory(run, root, journal, resources)
        result = supervise_once(run=run, root=root, adapter=adapter, journal=journal, authorization=authorization)
        summary = evidence_json(result)
        write_once(run / "runtime-cli-result.json", canonical_json(summary))
        print(json.dumps(summary, ensure_ascii=False, default=str))
        return 0 if result.get("verdict") == "FIXTURE_ONLY" or result.get("pass") is True else 4
    except (OSError, ValueError, PermissionError, KeyError) as exc:
        print(
            json.dumps(
                {"status": "REFUSED_BEFORE_ADAPTER", "adapter_constructed": False, "reason": str(exc)},
                ensure_ascii=False,
            )
        )
        return 3


def live_mode_guard(
    *, requested: bool, authorization: Mapping[str, object] | None, adapter_factory: Callable[[], object]
) -> tuple[bool, str]:
    """Reject --live before constructing an adapter unless separate explicit scope is supplied."""
    if not requested:
        return False, "offline-only entrypoint"
    if (
        authorization is None
        or authorization.get("status") != "VERIFIED_RUNTIME_AUTHORIZATION"
        or authorization.get("mode") != "LIVE"
        or authorization.get("scope") != TASK_ID
    ):
        return False, "live authorization missing; adapter not constructed"
    _ = adapter_factory
    return True, "separately verified live authority; concrete factory may be constructed"


def bounded_metadata_request(
    url: str, *, slot: str, journal: OneShotJournal, opener: Any
) -> tuple[int, dict[str, str], bytes]:
    """Future live metadata transport helper: no redirects, no proxy inheritance, no retry."""
    parsed = urlsplit(url)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("metadata request outside frozen loopback allowlist")
    request_bytes = canonical_json({"method": "GET", "url": url})
    logical_id = f"metadata:{slot}"
    if not journal.reserve(slot, logical_id, request_bytes) or not journal.enter_wire(slot, logical_id, request_bytes):
        raise RuntimeError("metadata budget exhausted before transport")
    request = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
    try:
        response = opener.open(request, timeout=5)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        headers = {
            str(k).lower(): str(v)
            for k, v in exc.headers.items()
            if str(k).lower() in {"content-type", "content-length", "date"}
        }
        journal.record_response(slot, logical_id, request_bytes, raw, exc.code)
        return exc.code, headers, raw
    with response:
        raw = response.read()
        headers = {
            str(k).lower(): str(v)
            for k, v in response.headers.items()
            if str(k).lower() in {"content-type", "content-length", "date"}
        }
        status = int(response.status)
    journal.record_response(slot, logical_id, request_bytes, raw, status)
    return status, headers, raw


def isolate_worker_environment(state: Path, root: Path) -> dict[str, str]:
    """Build a scrubbed child env without exporting secrets or inheriting the user's .env."""
    state = state.resolve()
    for name in ("config", "data", "logs", "vault", "sessions", "audit", "auth", "registry", "captures", "home"):
        (state / name).mkdir(parents=True, exist_ok=True)
    empty_env = state / "env.empty"
    if not empty_env.exists():
        write_once(empty_env, b"")
    env = {
        key: value
        for key, value in os.environ.items()
        if not any(
            token in key.upper()
            for token in (
                "API_KEY",
                "ACCESS_TOKEN",
                "BEARER",
                "SECRET",
                "OLLAMA_HOST",
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "ALL_PROXY",
            )
        )
    }
    env.update(
        {
            "HOME": str(state / "home"),
            "AGK_ENV_FILE": str(empty_env),
            "AGK_CONFIG_FILE": str(root / "config.yaml"),
            "PYTHONPATH": str(root / "src"),
            "AGK_AUTO_DISCOVER_LOCAL_MODELS": "false",
            "AGK_ALLOWED_ROOTS": str(state),
            "AGK_PATH_PROJECT_ROOT": str(state),
            "AGK_PATH_DATA_DIR": str(state / "data"),
            "AGK_PATH_MODELS_DIR": str(state / "models"),
            "AGK_PATH_LOGS_DIR": str(state / "logs"),
            "AGK_USAGE_DB": str(state / "usage.json"),
            "ANTIGRAVITY_VAULT_PATH": str(state / "vault"),
            "AGK_SESSION_BASE_DIR": str(state / "sessions"),
            "AGK_AUDIT_LOG_DIR": str(state / "audit"),
            "AGK_AUTH_PIN_HASH_FILE": str(state / "auth/pin-hash.json"),
            "AGK_AUTH_TOKEN_SECRET_FILE": str(state / "auth/token-secret"),
            "AGK_HOOK_VAULT_DIR": str(state / "hook-vault"),
            "AGK_VAULT_DIR": str(state / "auth/vault-keys"),
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "AGK_PATH_ROOT": str(state),
            "AGK_WORKSPACE_ROOT": str(state / "workspace"),
        }
    )
    return env


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if "--live" in args or "--supervise" in args or "--mock-runtime" in args or "--worker" in args:
        return runtime_cli(args)
    if args and args[0] == "--offline-tests" and len(args) == 3:
        try:
            root = resolve_repository_root()
            run = Path(__file__).resolve().parent
            request_hash = sha256((run / "request.json").read_bytes())
            if len(args) != 3:
                return 2
            return run_cold_pytest(
                root,
                Path(args[1]).resolve(),
                expected_source=SOURCE_EXPECTATIONS,
                expected_request_sha256=request_hash,
                state_root=Path(args[2]).resolve(),
                parent_invocation_id=os.environ.get("IMP09C_PARENT_INVOCATION_ID"),
                parent_capture_id=os.environ.get("IMP09C_PARENT_CAPTURE_ID"),
                owned_output_path=Path(os.environ["IMP09C_CHILD_OUTPUT_PATH"])
                if os.environ.get("IMP09C_CHILD_OUTPUT_PATH")
                else None,
            )
        except Exception as exc:
            print(
                json.dumps(
                    {
                        "status": "INCONCLUSIVE_PREPARATION",
                        "reason": f"{type(exc).__name__}: {exc}",
                        "pytest_started": False,
                        "product_imported": False,
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            return 3
    if args == ["--offline-verify"]:
        try:
            root = resolve_repository_root()
            run = Path(__file__).resolve().parent
            state_root = run / "offline-state"
            owned = prepare_owned_request(root, run, state_root)
            request = strict_json_loads((run / "request.json").read_bytes())
            binding = strict_json_loads((run / "request.binding.json").read_bytes())
            if (
                not isinstance(request, dict)
                or not isinstance(binding, dict)
                or owned["project_id"] != binding.get("project_id")
            ):
                raise ValueError("owned registry request binding mismatch")
            result = {
                "task_id": TASK_ID,
                "status": "PREPARED_REQUEST_BOUND",
                "request_sha256": owned["request_sha256"],
                "source_sha256": source_snapshot(root)["actual"],
                "live_observations": "NOT_RUN",
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        except Exception as exc:
            print(
                json.dumps(
                    {"status": "INCONCLUSIVE_PREPARATION", "reason": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False
                )
            )
            return 3
    if args == ["--owned-rebind"]:
        try:
            root = resolve_repository_root()
            run = Path(__file__).resolve().parent
            state_root = run / "offline-state"
            owned = prepare_owned_request(root, run, state_root, new_candidate=True)
            context = request_gate(run, root)
            raw_before = cast(bytes, context["execution_binding_raw"])
            manifest = write_implementation_source_manifest(run, root)
            result = {
                "task_id": TASK_ID,
                "status": "OWNED_NEW_CANDIDATE_READY",
                "project_id": owned["project_id"],
                "request_sha256": owned["request_sha256"],
                "execution_binding_id": context["execution_binding_id"],
                "execution_binding_sha256": sha256(raw_before),
                "previous_binding_archived": True,
                "implementation_manifest": manifest,
                "actual_calls": {"http": 0, "socket": 0, "worker": 0, "uvicorn": 0, "ollama": 0, "inference": 0},
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        except Exception as exc:
            print(
                json.dumps(
                    {"status": "INCONCLUSIVE_PREPARATION", "reason": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False
                )
            )
            return 3
    if args == ["--owned-prepare"]:
        try:
            root = resolve_repository_root()
            run = Path(__file__).resolve().parent
            state_root = run / "offline-state"
            owned = prepare_owned_request(root, run, state_root)
            context = request_gate(run, root)
            raw_before = cast(bytes, context["execution_binding_raw"])
            implementation_manifest = write_implementation_source_manifest(run, root)
            if cast(Path, context["binding_path"]).read_bytes() != raw_before:
                raise ValueError("execution binding changed during final implementation manifest creation")
            result = {
                "task_id": TASK_ID,
                "status": "OWNED_PREPARATION_READY",
                "project_id": owned["project_id"],
                "request_sha256": owned["request_sha256"],
                "execution_binding_id": context["execution_binding_id"],
                "execution_binding_sha256": sha256(raw_before),
                "implementation_manifest": implementation_manifest,
                "execution_binding_immutable": True,
                "product_observation": "NOT_RUN",
                "actual_calls": {"http": 0, "socket": 0, "worker": 0, "uvicorn": 0, "ollama": 0, "inference": 0},
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        except Exception as exc:
            print(
                json.dumps(
                    {"status": "INCONCLUSIVE_PREPARATION", "reason": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False
                )
            )
            return 3
    if args != ["--self-check"]:
        print(
            "offline-only: supported modes are --self-check, --offline-verify and --offline-tests; live observation requires independent authorization",
            file=sys.stderr,
        )
        return 2
    try:
        root = resolve_repository_root()
        request_raw = (Path(__file__).resolve().parent / "request.json").read_bytes()
        precheck = precheck_before_pytest(
            root, expected_source=SOURCE_EXPECTATIONS, expected_request_sha256=sha256(request_raw)
        )
        if precheck["status"] != "READY":
            raise ValueError("INCONCLUSIVE_SOURCE_DRIFT")
        context = request_gate(Path(__file__).resolve().parent, root, expected_request_sha256=sha256(request_raw))
        result = {
            "status": "OFFLINE_CONTRACT_READY",
            "task_id": TASK_ID,
            "source_sha256": cast(dict[str, object], context["source"])["actual"],
            "request_sha256": context["request_sha256"],
            "actual_calls": {"http": 0, "socket": 0, "worker": 0, "uvicorn": 0, "ollama": 0, "inference": 0},
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(
            json.dumps(
                {
                    "status": "INCONCLUSIVE_PREPARATION",
                    "reason": f"{type(exc).__name__}: {exc}",
                    "actual_calls": {"http": 0, "socket": 0, "worker": 0, "uvicorn": 0, "ollama": 0, "inference": 0},
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 3


if __name__ == "__main__":
    sys.modules["run_harness"] = sys.modules[__name__]
    raise SystemExit(main())
