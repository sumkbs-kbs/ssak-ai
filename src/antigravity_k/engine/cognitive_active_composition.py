"""Trusted project ACTIVE composition and committed canonical current heads.

Only server startup code supplies this configuration. HTTP bodies cannot select a
filesystem root, executor, principal, canonical lineage, or grant.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType

from antigravity_k.engine.cognitive.action_journal import SqliteActionJournal
from antigravity_k.engine.cognitive.actions import ToolExecutorPort
from antigravity_k.engine.cognitive.brain import BrainAdapter
from antigravity_k.engine.cognitive.governance import GovernanceGate
from antigravity_k.engine.cognitive.models import (
    Producer,
    ProducerKind,
)
from antigravity_k.engine.cognitive.store import CanonicalStore
from antigravity_k.engine.cognitive_active_heads import CanonicalCurrentHeads as CanonicalCurrentHeads
from antigravity_k.engine.cognitive_active_heads import CanonicalHeadAnchors as CanonicalHeadAnchors
from antigravity_k.engine.cognitive_active_requests import ActiveRequestBindings, TrustedCognitiveRequestBinding
from antigravity_k.engine.cognitive_surface import CognitiveSurfaceAdapter, DurableSurfaceHistoryStore
from antigravity_k.engine.cognitive_surface_brain import StructuredSurfaceBrainPort
from antigravity_k.engine.cognitive_surface_types import CognitiveCoreSettings, SurfaceNotReadyError, ThinkLike
from antigravity_k.engine.tool_executor import ToolExecutor, result_indicates_failure


@dataclass(frozen=True, slots=True)
class ProjectActiveConfiguration:
    """Application-owner injection; configuration itself does not activate a run."""

    settings: CognitiveCoreSettings
    project_root: Path
    runtime_root: Path
    owner_subject: str
    principal: str
    store: CanonicalStore
    executor: ToolExecutor
    anchors: CanonicalHeadAnchors
    prepared: Mapping[str, "PreparedCognitiveAction"]
    think: ThinkLike | None = None
    brain_adapter: BrainAdapter | None = None
    cognitive_requests: Mapping[str, TrustedCognitiveRequestBinding] = field(default_factory=dict)


def install_cognitive_active(app: "FastAPI", configuration: ProjectActiveConfiguration) -> None:
    """Install one project and reuse its existing executor across request adapters."""
    from antigravity_k.api.routes.cognitive_active_api import CognitiveActiveService

    config = configuration
    if config.settings.effective_mode.value != "active":
        return
    if (config.think is None) == (config.brain_adapter is None):
        raise SurfaceNotReadyError("Supply exactly one trusted Brain adapter or custom think port")
    if not config.owner_subject or not config.principal:
        raise SurfaceNotReadyError("Trusted owner and execution principal are required")
    if Path(config.executor.project_root).resolve() != config.project_root.resolve():
        raise SurfaceNotReadyError("ToolExecutor root does not match trusted project root")
    prepared = {
        key: replace(item, request=replace(item.request, decision_ref=config.anchors.decision_id))
        for key, item in config.prepared.items()
    }
    if any(
        item.project_id != config.settings.project_id or item.owner_subject != config.owner_subject
        for item in prepared.values()
    ):
        raise SurfaceNotReadyError("Prepared action crosses trusted project or owner")
    resolver = CanonicalCurrentHeads(config.store, config.settings.project_id, config.principal, config.anchors)
    bindings = ActiveRequestBindings(
        config.store,
        config.settings.project_id,
        config.principal,
        resolver,
        tuple(item.request.intent.to_intent().action_id for item in prepared.values() if item.request.intent),
        config.cognitive_requests,
    )
    journal = SqliteActionJournal(config.runtime_root / "action-claims.sqlite")
    history = DurableSurfaceHistoryStore(config.runtime_root / "surface-history.sqlite")
    port = ToolExecutorPort(config.executor, result_indicates_failure)

    def build_adapter(authorize: "ActivationAuthorizer") -> CognitiveSurfaceAdapter:
        structured = None
        if config.brain_adapter is not None:
            structured = StructuredSurfaceBrainPort(
                config.brain_adapter,
                project_id=config.settings.project_id,
                load_context_package=config.store.read,
                load_record=config.store.read,
                record_sink=config.store.commit_records,
                request_resolver=bindings.resolve,
            )
        adapter = CognitiveSurfaceAdapter(
            config.settings,
            think=structured if structured is not None else config.think,
            rethink=structured,
            governance=GovernanceGate(),
            dispatch_port=port,
            journal=journal,
            record_sink=config.store.commit_records,
            authority_resolver=bindings.authority,
            freshness_resolver=bindings.freshness,
            activation_authorizer=authorize,
            producer=Producer(kind=ProducerKind.BODY, actor_id=config.principal),
            history_store=history,
        )
        adapter.restore_experience_records(config.store.list_committed(config.settings.project_id))
        return adapter

    app.state.cognitive_active_service = CognitiveActiveService(
        prepared=MappingProxyType(prepared),
        build_adapter=build_adapter,
        load_record=config.store.read,
    )


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

    from antigravity_k.api.routes.cognitive_active_api import ActivationAuthorizer, PreparedCognitiveAction
