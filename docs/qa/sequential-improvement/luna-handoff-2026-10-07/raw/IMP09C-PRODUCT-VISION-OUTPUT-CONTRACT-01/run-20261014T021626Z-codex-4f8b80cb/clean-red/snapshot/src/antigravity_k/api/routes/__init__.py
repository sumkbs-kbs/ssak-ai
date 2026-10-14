"""Routes package — OpenAPI 태그가 포함된 API 라우트 집계.

각 라우터는 적절한 tags와 함께 등록되어 Swagger UI에서 그룹화됩니다.
"""

from typing import cast

from fastapi import APIRouter

from . import agency_api, artifact_api
from .agent_activity import router as agent_activity_router
from .agent_ask import router as agent_ask_router
from .agent_stream_api import router as agent_stream_router
from .agent_tools import router as agent_tools_router
from .approval_api import router as approval_router
from .chat import router as chat_router
from .code_api import router as code_router
from .code_intel_api import router as code_intel_router
from .cognitive_surface_api import router as cognitive_surface_router
from .conversation_api import router as conversation_router
from .decision_evaluation_api import router as decision_evaluation_router
from .disclosure_api import router as disclosure_router
from .events import router as events_router
from .evolution_api import router as evolution_router
from .filesystem import router as filesystem_router
from .gateway_api import router as gateway_api_router
from .git_api import router as git_router
from .job_api import router as job_api_router
from .kanban_api import router as kanban_api_router
from .messages_api import router as messages_router
from .models_api import router as models_router
from .network_access_api import router as network_access_router
from .operational_alerts import router as operational_alerts_router
from .recipes_api import router as recipes_router
from .remote_pairing_api import router as remote_pairing_router
from .responses_api import router as responses_router
from .search_api import router as search_router
from .security_api import router as security_router
from .system_api import router as system_api_router
from .task_api import router as task_api_router
from .training_jobs_api import router as training_jobs_router
from .unsloth_studio_api import router as unsloth_studio_router
from .unsloth_training_api import router as unsloth_training_router
from .vault_api import router as vault_api_router
from .vault_privacy import router as vault_privacy_router
from .voice_api import router as voice_api_router
from .workspace_links import router as workspace_links_router
from .workspace_services import router as workspace_services_router

agency_router = cast(APIRouter, getattr(agency_api, "router"))

api_router = APIRouter()

# ─── OpenAPI 태그 그룹 — Swagger UI에서 라우트 그룹화 ───

api_router.include_router(chat_router, tags=["chat"])
api_router.include_router(conversation_router, tags=["conversation"])
api_router.include_router(events_router, tags=["events"])
api_router.include_router(filesystem_router, tags=["filesystem"])
api_router.include_router(system_api_router, tags=["system"])
api_router.include_router(search_router, tags=["search"])
api_router.include_router(vault_privacy_router, tags=["memory"])
api_router.include_router(task_api_router, tags=["tasks"])
api_router.include_router(decision_evaluation_router, tags=["benchmarks"])
api_router.include_router(artifact_api.router, tags=["artifacts"])
api_router.include_router(job_api_router, tags=["jobs"])
api_router.include_router(gateway_api_router, tags=["gateway"])
api_router.include_router(voice_api_router, tags=["voice"])
api_router.include_router(unsloth_studio_router, tags=["unsloth"])
api_router.include_router(unsloth_training_router, tags=["unsloth"])
api_router.include_router(training_jobs_router, tags=["training"])
api_router.include_router(kanban_api_router, tags=["kanban"])
api_router.include_router(agent_stream_router, tags=["agent_stream"])
api_router.include_router(security_router, tags=["security"])
api_router.include_router(models_router, tags=["models"])
api_router.include_router(messages_router, tags=["messages"])
api_router.include_router(operational_alerts_router, tags=["operations"])

api_router.include_router(agent_tools_router, tags=["agent_tools"])
api_router.include_router(agency_router, tags=["agency"])
api_router.include_router(evolution_router, tags=["agent_tools"])
api_router.include_router(agent_activity_router, tags=["agent_activity"])
api_router.include_router(agent_ask_router, tags=["agent"])
api_router.include_router(workspace_links_router, tags=["workspaces"])
api_router.include_router(workspace_services_router, tags=["workspaces"])
api_router.include_router(remote_pairing_router, tags=["remote"])
api_router.include_router(network_access_router)
api_router.include_router(approval_router, tags=["approval"])
api_router.include_router(git_router, tags=["git"])
api_router.include_router(code_router, tags=["code"])
api_router.include_router(code_intel_router, tags=["code"])
api_router.include_router(disclosure_router, tags=["session"])
api_router.include_router(cognitive_surface_router, tags=["cognitive"])
api_router.include_router(recipes_router, tags=["recipes"])
api_router.include_router(responses_router, tags=["responses"])
api_router.include_router(vault_api_router, tags=["vault"])
