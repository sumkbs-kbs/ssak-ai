"""Models & Health API — 헬스체크, OpenAI 호환 모델 목록, 임베딩, Wake 이벤트."""

import json
import logging
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Annotated, ClassVar, TypedDict, cast

import yaml
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError

from antigravity_k import __version__
from antigravity_k.api import dependencies as api_dependencies
from antigravity_k.api.dependencies import (
    get_agent_runtime,
    get_embedding_engine,
    get_model_manager,
    get_orchestrator,
    get_vault_engine,
)
from antigravity_k.api.models import EmbeddingData, EmbeddingRequest, EmbeddingResponse, UsageStats
from antigravity_k.build_info import get_build_info
from antigravity_k.config import config
from antigravity_k.engine.agent_runtime import AgentRuntime
from antigravity_k.engine.audit_logger import get_audit_logger
from antigravity_k.engine.embeddings import EmbeddingEngine
from antigravity_k.engine.model_manager import ModelManager
from antigravity_k.engine.model_registry import ModelRegistry
from antigravity_k.engine.provider_capabilities import ProviderCapability
from antigravity_k.engine.vault import VaultEngine
from antigravity_k.tools.tool_registry import ToolRegistry

get_tool_registry = cast(Callable[[], ToolRegistry], getattr(api_dependencies, "__get_tool_registry"))


def _as_object_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    items = cast(Mapping[object, object], value).items()
    return {str(key): item for key, item in items}


class OperationalMetric(TypedDict):
    model: str
    outcome_count: int
    task_success_rate: float | None
    tool_accuracy: float | None
    retry_rate: float | None


class QualityCalibrationStatus(TypedDict):
    enabled: bool
    eligible_models: list[str]
    ineligible_models: list[str]
    operational_metrics: list[OperationalMetric]


class ModelOperationsResponse(TypedDict):
    provider_capabilities: dict[str, ProviderCapability]
    quality_calibration: QualityCalibrationStatus


router = APIRouter()
logger = logging.getLogger("antigravity_k.api.routes.models")


@router.get("/health")
@router.get("/v1/health")
def health_check() -> dict[str, object]:
    """Health Check."""
    manager = get_model_manager()
    info = manager.status() if manager else {}
    backends = info.get("loaded_models", {})

    # 시스템 상태 추가 (RAG, CoV)
    orchestrator = get_orchestrator()
    rag_files = 0
    cov_active = False
    if orchestrator:
        rag_indexer: object = getattr(cast(object, orchestrator), "_rag_indexer", None)
        if rag_indexer:
            file_hashes = getattr(rag_indexer, "_file_hashes", {})
            rag_files = len(cast(Mapping[object, object], file_hashes)) if isinstance(file_hashes, Mapping) else 0
        if getattr(cast(object, orchestrator), "_cov_engine", None):
            cov_active = True

    return {
        "status": "ok",
        "version": __version__,
        # CR-10: 실제 실행 중인 빌드 provenance(미기록 값은 None).
        "build": get_build_info(),
        "backends": backends,
        "rag_index_files": rag_files,
        "cov_active": cov_active,
    }


class WakeRequest(BaseModel):
    """Wakerequest.

    Bases: BaseModel
    """

    event_type: str = Field(
        ...,
        description="Type of event (e.g. 'file_changed', 'lint_error', 'comment')",
    )
    payload: dict[str, object] = Field(..., description="Detailed payload for the event")
    target_model: str = Field(
        default="qwen3.6:latest",
        description="Model to use for the wake task",
    )


class _SetDefaultModelRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", strict=True)

    name: StrictStr | None = None
    role: StrictStr | None = None


@router.post("/api/agent/wake")
async def wake_agent(
    req: WakeRequest,
    manager: Annotated[ModelManager, Depends(get_model_manager)],
    registry: Annotated[ToolRegistry, Depends(get_tool_registry)],
    vault: Annotated[VaultEngine | None, Depends(get_vault_engine)],
) -> dict[str, object]:
    """Paperclip의 Comment-driven Wake 개념을 포팅.

    특정 시스템 이벤트 발생 시 에이전트가 백그라운드에서 즉시 기상하여 태스크를 수행합니다.
    """
    _ = (manager, registry, vault)
    runtime: AgentRuntime = get_agent_runtime()

    payload_str = json.dumps(req.payload, ensure_ascii=False)
    prompt = (
        f"System Wake Event Triggered:\n- Type: {req.event_type}\n- Details:"
        f"{payload_str}\n\nPlease analyze this event and"
        f" take any necessary actions."
    )

    task_id = runtime.submit_task(
        prompt=prompt,
        target_model=req.target_model,
        context={"wake_event": req.event_type, "use_worktree": False},
    )

    return {
        "status": "woken",
        "task_id": task_id,
        "message": f"Agent woken by '{req.event_type}' event and assigned background task {task_id}.",
    }


@router.get("/v1/models")
def list_models(manager: Annotated[ModelManager, Depends(get_model_manager)]) -> dict[str, object]:
    """설치/로드된 모델 목록 반환."""
    import time

    _ = manager.discover_local_models()
    model_registry = cast(ModelRegistry, getattr(cast(object, manager), "_registry"))
    models = model_registry.list_models()
    provider_capabilities = manager.provider_capabilities()
    # Ensure it follows OpenAI-like format
    formatted_data: list[dict[str, object]] = []
    for m in models:
        formatted_data.append(
            {
                "id": m.name,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "system",
                "role": m.role,
                "description": m.description,
                "provider_capability": provider_capabilities.get(m.name),
                **m.routing_metadata(),
            },
        )
    return {"object": "list", "data": formatted_data}


@router.get("/api/models/local")
def list_local_models(
    manager: Annotated[ModelManager, Depends(get_model_manager)],
    refresh: bool = False,
) -> dict[str, object]:
    """본 PC에 실제로 설치 및 실행 중이거나 캐시된 로컬 모델 목록만 실시간으로 검색하여 반환합니다."""
    from antigravity_k.engine.local_model_discovery import LocalModelDiscovery

    discovery = LocalModelDiscovery()
    discovered_models = discovery.discover()

    # 발견된 로컬 모델들을 레지스트리에도 병합하여 시스템에서 사용 가능하도록 함
    model_registry = cast(ModelRegistry, getattr(cast(object, manager), "_registry"))
    model_registry.merge_discovered_models(discovered_models)

    local_models: list[dict[str, object]] = []
    for m in discovered_models:
        tier = "unknown"
        if m.parameter_count_b > 40:
            tier = "70B"
        elif m.parameter_count_b > 15:
            tier = "30B"
        elif m.parameter_count_b > 0:
            tier = "7B"

        local_models.append(
            {
                "id": m.name,
                "name": m.name,
                "provider": m.provider,
                "role": m.role,
                "description": f"{m.name} ({m.provider} / {m.status})",
                "parameter_count_b": m.parameter_count_b,
                "is_local": True,
                "context_length": m.context_length,
                "quantization": m.quantization,
                "status": m.status,  # "running" | "installed" | "cached"
                "disk_path": m.disk_path,
                "disk_size_gb": round(m.disk_size_gb, 2),
                "source": m.source,
                "tier": tier,
            }
        )

    configured_default = model_registry.get_default("reasoning")
    configured_local = next(
        (
            model
            for model in discovered_models
            if configured_default is not None
            and model.role in ("reasoning", "coding", "general")
            and model.parameter_count_b > 0
            and model_registry.get_model(model.name) is configured_default
        ),
        None,
    )
    recommended_default: str | None = None
    running_models = [m for m in local_models if m.get("status") == "running"]
    primary_running = [
        m
        for m in running_models
        if m.get("role") in ("reasoning", "coding", "general") and cast(float, m.get("parameter_count_b", 0)) > 0
    ]
    if configured_local is not None:
        recommended_default = configured_local.name
    elif primary_running:
        primary_running.sort(key=lambda x: cast(float, x.get("parameter_count_b", 0)), reverse=True)
        recommended_default = cast(str, primary_running[0]["id"])
    elif running_models:
        recommended_default = cast(str, running_models[0]["id"])
    elif local_models:
        primary_cached = [
            m
            for m in local_models
            if m.get("role") in ("reasoning", "coding", "general") and cast(float, m.get("parameter_count_b", 0)) > 0
        ]
        if primary_cached:
            primary_cached.sort(key=lambda x: cast(float, x.get("parameter_count_b", 0)), reverse=True)
            recommended_default = cast(str, primary_cached[0]["id"])
        else:
            recommended_default = cast(str, local_models[0]["id"])

    message = (
        f"본 PC에서 {len(local_models)}개의 실제 로컬 모델(실행 중: {len(running_models)}개, 캐시/다운로드됨: {len(local_models) - len(running_models)}개)이 감지되었습니다."
        if local_models
        else "본 PC에서 실행 중이거나 다운로드된 로컬 모델을 찾을 수 없습니다."
    )

    return {
        "ok": True,
        "total": len(local_models),
        "recommended_default": recommended_default,
        "models": local_models,
        "message": message,
    }


class _LoadModelRequest(BaseModel):
    model: str


@router.post("/api/models/load")
def load_local_model(
    request: _LoadModelRequest,
    manager: Annotated[ModelManager, Depends(get_model_manager)],
) -> dict[str, object]:
    """로컬 모델(Unsloth GGUF, MLX, Ollama 등)을 메모리/런타임에 실제로 로드합니다."""
    model_name = request.model.strip()
    if not model_name:
        raise HTTPException(status_code=400, detail="모델 이름이 필요합니다.")

    model_registry = cast(ModelRegistry, getattr(cast(object, manager), "_registry"))
    profile = model_registry.get_model(model_name)
    if profile is None:
        from antigravity_k.engine.local_model_discovery import LocalModelDiscovery

        discovery = LocalModelDiscovery()
        model_registry.merge_discovered_models(discovery.discover())
        profile = model_registry.get_model(model_name)

    if profile is None:
        raise HTTPException(status_code=404, detail=f"모델 '{model_name}'을 레지스트리에서 찾을 수 없습니다.")

    try:
        _ = manager.load(model_name)
        return {
            "ok": True,
            "model": model_name,
            "provider": profile.provider,
            "status": "running",
            "message": f"모델 '{model_name}'이 성공적으로 로드되었습니다.",
        }
    except Exception as e:
        logger.error("모델 로드 실패 [%s]: %s", model_name, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"모델 로드 중 오류가 발생했습니다: {str(e)}")


@router.get("/v1/models/operations", response_model=None)
def model_operations_status(
    manager: Annotated[ModelManager, Depends(get_model_manager)],
    refresh: bool = False,
) -> ModelOperationsResponse:
    routing_status = manager.router.status()
    quality_calibration = cast(QualityCalibrationStatus, routing_status.get("quality_calibration", {}))
    return {
        "provider_capabilities": manager.provider_capabilities(refresh=refresh),
        "quality_calibration": quality_calibration,
    }


@router.post("/v1/embeddings", response_model=EmbeddingResponse)
async def create_embeddings(
    request: EmbeddingRequest,
    engine: Annotated[EmbeddingEngine, Depends(get_embedding_engine)],
) -> EmbeddingResponse:
    """Create embeddings.

    Args:
        request (EmbeddingRequest): EmbeddingRequest request.
        engine (EmbeddingEngine): EmbeddingEngine engine.

    """
    audit = get_audit_logger()
    audit.log_event("embedding_request", {"model": request.model, "input_len": len(request.input)})

    try:
        # Generate embeddings
        embeddings = engine.embed(request.input, request.model)

        # Format response
        data: list[EmbeddingData] = []
        for i, emb in enumerate(embeddings):
            data.append(EmbeddingData(embedding=emb, index=i))

        # Basic usage tracking (dummy for now)
        tokens = sum(len(t) // 4 for t in request.input) if isinstance(request.input, list) else len(request.input) // 4

        return EmbeddingResponse(
            data=data,
            model=request.model,
            usage=UsageStats(prompt_tokens=tokens, total_tokens=tokens),
        )
    except (ValueError, RuntimeError, KeyError) as e:
        logger.error("Embedding error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/models/default")
async def set_default_model(request: Request) -> dict[str, object]:
    """Set default model for a role in config.yaml.

    Body:
        name: model slug (e.g. "nvidia/nemotron-3-ultra-550b-a55b:free")
        role: optional role override (default: auto-detect from registry)
    """
    try:
        raw_body = cast(object, await request.json())
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

    try:
        body = _SetDefaultModelRequest.model_validate(raw_body)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail="Request body must be an object") from exc

    try:
        name = body.name or ""
        if not name:
            raise HTTPException(status_code=400, detail="'name' is required")

        from antigravity_k.engine.model_registry import ModelRegistry

        registry = ModelRegistry()
        model = registry.get_model(name)
        if not model:
            raise HTTPException(status_code=404, detail=f"Model '{name}' not found in registry")

        role = body.role if body.role is not None else model.role
        config_file = Path(config.paths.project_root) / "config.yaml"

        with config_file.open(encoding="utf-8") as f:
            cfg = _as_object_mapping(cast(object, yaml.safe_load(f) or {}))

        defaults_value = cfg.get("defaults")
        defaults = _as_object_mapping(defaults_value)
        cfg["defaults"] = defaults

        old_default = defaults.get(role, "(없음)")
        defaults[role] = name

        with config_file.open("w", encoding="utf-8") as f:
            yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        # Re-registry reload
        registry.reload()

        return {
            "ok": True,
            "role": role,
            "old_default": old_default,
            "new_default": name,
            "message": f"기본 {role} 모델이 {name}(으)로 변경되었습니다.",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to set default model: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
