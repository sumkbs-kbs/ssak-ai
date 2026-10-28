"""Context acquisition handlers for the orchestrator state graph."""

import logging
from collections.abc import Callable, Generator, Mapping, Sequence
from typing import Protocol, TypedDict, cast

from antigravity_k.engine import multimodal
from antigravity_k.engine.codebase_file_selection import (
    CodebaseMemorySearch,
    CodeTreeSearch,
    select_relevant_files,
)
from antigravity_k.engine.state_graph import AgentState, StateContext

logger = logging.getLogger("antigravity_k.engine.orchestrator_handlers")


class _FormatContextKwargs(TypedDict, total=False):
    n_results: int
    mode: str
    candidate_pool: int


class _WatchdogLike(Protocol):
    def pop_notifications(self) -> Sequence[str]: ...


class _KiEngineLike(Protocol):
    def build_ki_prompt(self) -> str: ...


class _KnowledgeGapLike(Protocol):
    topic: str


class _LearnedKnowledgeLike(Protocol):
    ki_id: str
    topic: str
    summary: str


class _KiEngineDirectoryLike(Protocol):
    ki_dir: str


class _AutonomousLearnerLike(Protocol):
    ki_engine: _KiEngineDirectoryLike | None

    def should_learn(self, message: str) -> bool: ...
    def analyze_knowledge_gap(self, message: str) -> Sequence[_KnowledgeGapLike]: ...
    def auto_learn(self, gaps: Sequence[_KnowledgeGapLike]) -> Sequence[_LearnedKnowledgeLike]: ...
    def format_context(self, learned: Sequence[_LearnedKnowledgeLike]) -> str: ...


class _SkillLoaderLike(Protocol):
    def auto_match(self, message: str, max_skills: int) -> Sequence[str]: ...


class _OrchestratorContextLike(Protocol):
    ki_engine: _KiEngineLike
    autonomous_learner: _AutonomousLearnerLike
    skill_loader: _SkillLoaderLike | None


class _RagIndexerLike(Protocol):
    def format_context(
        self,
        query: str,
        n_results: int = 5,
        max_chars: int = 6000,
        mode: str = "hybrid",
        candidate_pool: int | None = None,
    ) -> str: ...


class _VectorStoreLike(Protocol):
    def search(self, query: str, n_results: int) -> Sequence[Mapping[str, object]]: ...


class _VaultEngineLike(Protocol):
    sync_rag: bool
    vector_store: _VectorStoreLike


class _OrchestratorLike(Protocol):
    project_root: str
    ctx: _OrchestratorContextLike
    manager: object | None
    vault_engine: _VaultEngineLike | None
    watchdog: _WatchdogLike | None
    code_tree_indexer: CodeTreeSearch | None


def init_handler(ctx: StateContext, orch: object) -> Generator[str, None, None]:
    """초기화: 사용자 메시지 추출 + Watchdog 알림 확인."""
    orchestrator = cast(_OrchestratorLike, orch)
    # 사용자 메시지 추출
    ctx.user_message = ""
    for msg in reversed(ctx.messages):
        if msg.get("role") == "user":
            # NX-09-F03: content 는 보통 문자열이지만, OpenAI 호환 표면으로 **파트 배열**이
            # 들어올 수 있다 — 그대로 쓰면 `.strip()`/정규식에서 죽는다.
            ctx.user_message = multimodal.flatten_content(msg.get("content", "")) or ""
            break

    if not ctx.user_message.strip():  # noqa: SIO110 - ctx.user_message 는 위에서 문자열로 접었다
        yield "메시지를 입력해주세요."
        ctx.transition_to(AgentState.COMPLETE)
        return

    # Ambient Watchdog 프로액티브 알림
    if orchestrator.watchdog:
        notifs = orchestrator.watchdog.pop_notifications()
        for notif in notifs:
            yield f"{notif}\n\n"

    ctx.custom_messages = list(ctx.messages)


class _ProjectRagSkipped(Exception):
    """Project RAG intentionally skipped by policy (no search, no fallback)."""


# ─── CONTEXT_ENRICH 핸들러 ────────────────────────────────────────


def context_enrich_handler(ctx: StateContext, orch: object) -> None:
    """RAG + KI + 벡터 스토어 + AST-RAGIndexer + 코드 트리 컨텍스트 주입."""
    orchestrator = cast(_OrchestratorLike, orch)
    rag_context: str = ""
    segments: dict[str, str] = {}
    rag_status = "skipped"

    # KIs 주입
    ki_context = orchestrator.ctx.ki_engine.build_ki_prompt()
    if ki_context:
        segments["ki"] = ki_context
        rag_context += ki_context

    # ─── AST 기반 RAGIndexer 코드 검색 ───
    try:
        from antigravity_k.engine.project_embedding_binding import project_rag_policy
        from antigravity_k.engine.rag_indexer import RAGIndexer

        rag_mode, rag_reason = project_rag_policy()
        indexer: _RagIndexerLike | None = None
        if rag_mode == "disabled":
            logger.info("[RAGIndexer] Project RAG disabled: %s", rag_reason)
        else:
            indexer = cast(_RagIndexerLike | None, getattr(orchestrator, "_rag_indexer", None))
            bound = getattr(getattr(indexer, "vector_store", None), "embedding_binding", None) is not None
            if rag_mode == "enabled" and not bound:
                logger.info("[RAGIndexer] Project RAG enabled but not ready: bound indexer missing")
                indexer = None
            elif indexer is None:
                indexer = RAGIndexer(project_root=orchestrator.project_root)
                setattr(orchestrator, "_rag_indexer", indexer)
            elif rag_mode == "enabled":
                # Bound (explicitly enabled) project RAG has no startup auto-index; bring the
                # project index up to date here (incremental, hash-based) before searching.
                sync = getattr(indexer, "sync", None)
                if callable(sync):
                    synced = cast(Callable[[], int], sync)()
                    logger.warning("[RAGIndexer] Bound project index synced: %s chunks updated", synced)
        if indexer is None:
            raise _ProjectRagSkipped
        format_kwargs: _FormatContextKwargs = {}
        manager = orchestrator.manager
        plan_provider = getattr(manager, "long_context_plan", None) if manager is not None else None
        if callable(plan_provider) and ctx.target_model:
            provider = cast(Callable[[str], Mapping[str, object]], plan_provider)
            raw_plan = provider(ctx.target_model)
            # A model without a long-context plan returns None: fall back to the default
            # retrieval instead of aborting project RAG enrichment.
            execution_plan: Mapping[str, object] = raw_plan if isinstance(raw_plan, Mapping) else {}
            if execution_plan.get("retrieval_mode") == "long_context":
                format_kwargs = {"n_results": 5, "mode": "long_context"}
                candidate_pool = execution_plan.get("candidate_pool")
                if isinstance(candidate_pool, int) and candidate_pool > 0:
                    format_kwargs["candidate_pool"] = candidate_pool
        code_context = indexer.format_context(ctx.user_message, **format_kwargs)
        segments["rag_code"] = code_context or ""
        rag_status = "injected" if code_context else "empty"
        if code_context:
            rag_context += "\n" + code_context
            logger.warning("[RAGIndexer] Code context injected (%s chars)", len(code_context))
            import antigravity_k.engine.llm_input_audit as llm_input_audit

            if llm_input_audit.enabled():
                llm_input_audit.audit_retrieval(
                    project_root=str(orchestrator.project_root),
                    project_id=_audit_project_id(ctx, str(orchestrator.project_root)),
                    path=f"graph:{getattr(ctx, 'task_type', '')}:rag={rag_mode}",
                    sources=list(getattr(indexer, "last_context_sources", []) or []),
                )
    except _ProjectRagSkipped:
        pass
    except Exception as e:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK - optional indexer boundary
        rag_status = f"error:{type(e).__name__}"
        logger.exception("RAGIndexer enrichment failed (rag_status=%s; not recorded as RAG success)", rag_status)
        logger.debug(
            "RAGIndexer enrichment skipped: %s", e
        )  # ─── Freebuff-Style: Code Tree 기반 자동 파일 컨텍스트 (P1+P2) ───
    try:
        code_tree = orchestrator.code_tree_indexer
        memory_search = cast(CodebaseMemorySearch | None, vars(orchestrator).get("codebase_memory_search"))
        selection = select_relevant_files(
            orchestrator.project_root,
            ctx.user_message,
            memory_search=memory_search,
            fallback_search=code_tree,
        )
        if selection.files:
            related_files = [candidate.model_dump(mode="python") for candidate in selection.files]
            if related_files:
                from antigravity_k.engine.file_summarizer import FileSummarizer

                summarizer = FileSummarizer(model_manager=orchestrator.manager)
                file_context = summarizer.summarize_files(related_files, orchestrator.project_root, ctx.user_message)

                if file_context:
                    segments["file_selection"] = file_context
                    rag_context += "\n" + file_context
                    logger.info(
                        "[FileSelection:%s] Auto-injected %s files for: %s",
                        selection.source.value,
                        len(related_files),
                        ctx.user_message[:50],
                    )
    except Exception as e:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK - optional code-tree boundary
        logger.warning("[CodeTree] 컨텍스트 자동 주입 실패 (non-critical): %s", e, exc_info=True)

    # 벡터 스토어 검색 (과거 메모리) — r39: 비에이전트 chat 경로와 같은 구현을 공유한다.
    if orchestrator.vault_engine and orchestrator.vault_engine.sync_rag:
        from antigravity_k.engine.past_memory import build_past_memory_block

        block, past_status, _n = build_past_memory_block(
            orchestrator.vault_engine, ctx.user_message, project_root=orchestrator.project_root
        )
        if block:
            rag_context += block
            segments["past_memory"] = block
        elif past_status == "error":
            segments["past_memory_status"] = ""

    # ── RAG 블롭 상한 ──
    # 이 블롭은 "마지막 사용자 메시지"에 합쳐져 모든 트리머의 최상위 보호를
    # 받는다 — 상한 없으면 과대 검색 결과가 예산을 초과해도 축소되지 않는다.
    # 주입 시점에 토큰 상한(기본 3000토큰)으로 자른다.
    _RAG_CONTEXT_MAX_TOKENS = 3000
    if rag_context:
        from antigravity_k.engine.tokenizer import TokenEstimator

        if TokenEstimator.estimate_text(rag_context) > _RAG_CONTEXT_MAX_TOKENS:
            keep_chars = int(
                len(rag_context) * _RAG_CONTEXT_MAX_TOKENS / max(TokenEstimator.estimate_text(rag_context), 1)
            )
            rag_context = rag_context[:keep_chars] + "\n...[RAG 컨텍스트 축약 — 상한 도달]..."
            logger.info("[ContextEnrich] RAG 컨텍스트를 %d토큰 상한으로 축약", _RAG_CONTEXT_MAX_TOKENS)

    ctx.rag_context = rag_context
    import antigravity_k.engine.llm_input_audit as _audit

    if _audit.enabled():
        segments["question"] = ctx.user_message
        segments["ephemeral"] = ctx.ephemeral_message or ""
        _audit.register_segments(segments, rag_status=rag_status)

    # 컨텍스트 주입
    if rag_context or ctx.ephemeral_message:
        new_content = ctx.user_message
        if rag_context:
            new_content += rag_context
        if ctx.ephemeral_message:
            new_content += f"\n\n<EPHEMERAL_MESSAGE>\n{ctx.ephemeral_message}\n</EPHEMERAL_MESSAGE>\n"
        # NX-09-F03: 메시지를 **새 딕셔너리로 갈아치우면** images/image_mimes 같은 구조화
        # 필드가 조용히 사라진다(첨부가 여기서 죽었다). 기존 키를 보존하며 내용만 바꾼다.
        ctx.custom_messages[-1] = {**ctx.custom_messages[-1], "role": "user", "content": new_content}


# ─── AUTO_LEARN 핸들러 ────────────────────────────────────────────


def auto_learn_handler(ctx: StateContext, orch: object) -> Generator[str, None, None]:
    """자율 학습 파이프라인."""
    orchestrator = cast(_OrchestratorLike, orch)
    try:
        learner = orchestrator.ctx.autonomous_learner
        if learner.should_learn(ctx.user_message):
            yield "🔬 **[자율 학습]** 필요한 지식을 인터넷에서 수집 중...\n"
            gaps = learner.analyze_knowledge_gap(ctx.user_message)
            if gaps:
                yield f"📚 {len(gaps)}개 지식 갭 감지: {', '.join(g.topic[:30] for g in gaps)}\n"
                learned = learner.auto_learn(gaps)
                if learned:
                    learn_context = learner.format_context(learned)
                    ctx.custom_messages[-1] = {
                        **ctx.custom_messages[-1],
                        "role": "user",
                        "content": ctx.custom_messages[-1]["content"] + learn_context,
                    }
                    import os

                    msg = f"✅ **[자율 학습 완료]** {len(learned)}건 학습 → Wiki 저장 완료\n"
                    ki_dir = os.path.abspath(learner.ki_engine.ki_dir) if learner.ki_engine else ""
                    for item in learned:
                        summary_preview = item.summary[:60].replace("\n", " ") + "..."
                        if ki_dir:
                            file_path = os.path.join(ki_dir, f"{item.ki_id}_metadata.json")
                            msg += f"> **[{item.topic}](file://{file_path})**: {summary_preview}\n"
                        else:
                            msg += f"> **{item.topic}**: {summary_preview}\n"
                    yield msg + "\n"
                else:
                    yield "ℹ️ *학습 대상 없음 — 기존 지식으로 진행*\n\n"
    except Exception:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK - optional learning boundary
        logger.exception("Autonomous learning pipeline error")


# ─── SKILL_MATCH 핸들러 ───────────────────────────────────────────


def skill_match_handler(ctx: StateContext, orch: object) -> Generator[str, None, None]:
    """스킬 자동 매칭."""
    orchestrator = cast(_OrchestratorLike, orch)
    skill_loader = orchestrator.ctx.skill_loader
    if skill_loader:
        try:
            auto_activated = skill_loader.auto_match(ctx.user_message, max_skills=2)
            if auto_activated:
                skills_str = ", ".join(auto_activated)
                yield f"🧠 *스킬 자동 활성화: {skills_str}*\n"
                logger.info("[AutoSkill] Auto-activated: %s", auto_activated)
        except Exception as e:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK - skill boundary
            logger.exception("Unhandled exception")
            logger.debug("Auto skill matching failed: %s", e)


def _audit_project_id(ctx: object, project_root: str) -> str:
    """r30: link the retrieval audit to the selected project (request binding, then registry by root)."""
    explicit = str(getattr(ctx, "project_id", "") or "")
    if explicit:
        return explicit
    try:
        from antigravity_k.api.project_binding import get_request_project_id

        bound = get_request_project_id()
        if bound:
            return str(bound)
    except Exception:  # noqa: BLE001 - audit enrichment must not break the chat path
        pass
    try:
        import os

        from antigravity_k.engine.project_registry import get_project_registry

        root = os.path.realpath(project_root)
        for record in get_project_registry().list_projects():
            path = str(record.get("path") or record.get("root") or "")
            if path and os.path.realpath(path) == root:
                return str(record.get("id") or record.get("project_id") or "")
    except Exception:  # noqa: BLE001
        pass
    return ""
