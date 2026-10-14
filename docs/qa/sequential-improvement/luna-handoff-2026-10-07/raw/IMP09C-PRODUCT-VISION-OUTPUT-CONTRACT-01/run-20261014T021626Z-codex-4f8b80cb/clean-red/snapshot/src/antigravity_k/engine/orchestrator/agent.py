"""OrchestratorAgent — CEO 기반 멀티 에이전트 오케스트레이터 클래스."""

import logging
import os
import re
from collections.abc import Generator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Protocol, TypeAlias, cast, final, runtime_checkable

from antigravity_k.agents.personas import get_orchestrator_prompt
from antigravity_k.engine.capacity_flow import CapacityCheckpoint
from antigravity_k.engine.ceo_analyzer import ceo_analyze as _ceo_analyze_fn
from antigravity_k.engine.code_tree_indexer_models import CodeTreeStats
from antigravity_k.engine.context_budget import context_budget_for_model
from antigravity_k.engine.direct_task_execution import MaxEnginePort
from antigravity_k.engine.engine_context import EngineContext
from antigravity_k.engine.long_context_policy import LongContextExecutionPlan, LongContextPlanner
from antigravity_k.engine.memory_provider import MemoryManager
from antigravity_k.engine.memory_recorder import MemoryRecorder
from antigravity_k.engine.orchestrator.setup import (
    PLANNING_MODE_BLOCK,
    create_artifact_engine,
    create_evolution_coordinator,
    create_fact_appender,
    create_state_graph,
    create_watchdog,
    load_agent_models,
)
from antigravity_k.engine.session_manager import SessionManager, SessionPersistenceError
from antigravity_k.engine.task_state_store import (
    TaskExecutionContext,
    TaskStateStore,
    bind_task_execution_context,
)
from antigravity_k.engine.vault import VaultEngine
from antigravity_k.tools.tool_registry import ToolRegistry

logger = logging.getLogger("antigravity_k.orchestrator")


class ModelManagerPort(Protocol):
    pass


@runtime_checkable
class _GeneratingModelManager(Protocol):
    def generate(self, prompt: str, target: str, **kwargs: object) -> str: ...


AgentMessage: TypeAlias = dict[str, str]
JsonObject: TypeAlias = dict[str, object]


class _CodeTreeIndexer(Protocol):
    def build_tree(self) -> str: ...

    def stats(self) -> CodeTreeStats: ...


class _ClosableVectorStore(Protocol):
    def close(self) -> None: ...


class _RagIndexer(Protocol):
    vector_store: _ClosableVectorStore


def _object_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    raw = cast(dict[object, object], value)
    return {str(key): item for key, item in raw.items()}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    raw = cast(list[object], value)
    return [item for item in raw if isinstance(item, str)]


@final
class OrchestratorAgent:
    """CEO 기반 멀티 에이전트 오케스트레이터.

    사용자 명령 흐름:
    1. CEO 분석 (빠른 모델) → 태스크 유형 판별
    2. 역할별 모델 위임 → 전문 에이전트 실행
    3. 도구 호출 (ReAct 루프) → 실제 작업 수행
    4. 결과 스트리밍 → 대시보드 표시
    """

    def __init__(
        self,
        model_manager: ModelManagerPort | None,
        vault_engine: VaultEngine | None = None,
        project_root: str | None = None,
        tool_registry: ToolRegistry | None = None,
        session_manager: SessionManager | None = None,
        memory_manager: MemoryManager | None = None,
        project_id: str | None = None,
    ):
        """Initialize the OrchestratorAgent.

        Args:
            model_manager: model manager.
            vault_engine: vault engine.
            project_root: project root.
            tool_registry: tool registry.
            session_manager: 외부 SessionManager (작업 1: chat.py와 인스턴스 통일).
            project_id: WS-03 project identity for runtime cache keying.

        """
        self.manager = model_manager
        self.vault_engine = vault_engine
        self.project_root = project_root or os.getcwd()
        self.project_id = (project_id or "").strip() or None

        self.ctx = EngineContext(
            model_manager=model_manager,
            vault_engine=vault_engine,
            project_root=self.project_root,
            tool_registry=tool_registry,
            session_manager=session_manager,
            memory_manager=memory_manager,
        )

        # Shortcut references
        self.config = self.ctx.config
        self.agent_models = load_agent_models(self.config)
        self.tool_registry = self.ctx.tool_registry
        self.session_manager = self.ctx.session_manager
        self.context_shaper = self.ctx.context_shaper
        self.persistent_agency = self.ctx.persistent_agency

        self._memory_recorder = MemoryRecorder(
            self.vault_engine,
            self.manager,
            self._get_model_for_role,
        )

        # Capacity Flow 가드레일
        self._capacity_checkpoint = CapacityCheckpoint()

        # ─── Mode Manager (Plan/Build/Interactive) ───
        self.mode_manager = self.ctx.mode_manager

        # ─── Setup: Optional Components ───
        self.watchdog = create_watchdog(
            self.config,
            self.project_root,
            self.manager,
            self.vault_engine,
        )
        self._state_graph = create_state_graph()
        self.artifact_engine = create_artifact_engine(self.project_root)
        self.fact_appender = create_fact_appender(self.manager, self.project_root)

        # ─── Self-Evolution Coordinator ───
        self._evolution_coordinator = self._init_evolution_coordinator()

        # 연속 에러 카운터
        self.ctx.tool_executor.reset_error_counter()
        self._shared_tool_registry = tool_registry is not None

        # 상태 추적
        self._last_agent_output = ""
        self._task_execution_context: ContextVar[TaskExecutionContext | None] = ContextVar(
            "task_execution_context",
            default=None,
        )

        # ─── Freebuff-Style Proactive: Code Tree Indexer (P0) ───
        self._code_tree_indexer: _CodeTreeIndexer | None = None
        self._rag_indexer: _RagIndexer | None = None

        # ─── P4: MAX Mode Parallel Engine (지연 초기화) ───
        self._max_engine: MaxEnginePort | None = None

        # Lazy-init Heavy Components
        self._skill_auto_learner_initialized = False
        self._skill_auto_learner_instance = None
        self._trajectory_compressor_initialized = False
        self._trajectory_compressor_instance = None
        self._context_compressor_initialized = False
        self._context_compressor_instance = None
        self._prompt_components_cache: dict[str, str] = {}
        # 모델별 ContextCompressor 캐시 (스텝당 디스크 재독 방지)
        self._context_compressor_by_model: dict[str, object] = {}

        # 세션 자동 시작
        try:
            _ = self.session_manager.start_session(project_path=self.project_root)
        except SessionPersistenceError:
            # CR-02: 저장 실패를 "non-critical"로 숨기지 않는다. 세션이 디스크에
            # 없을 수 있음을 명시적으로 남기고, 다음 저장에서 재시도한다.
            logger.error("Session persistence failed during agent init", exc_info=True)
        except (RuntimeError, ConnectionError, AttributeError):
            logger.warning("Session start failed (non-critical)", exc_info=True)

    def _init_evolution_coordinator(self):
        """Self-Evolution Coordinator를 초기화합니다. (self 참조 필요)"""

        def _sec_verify_fn(prompt: str) -> str:
            manager = self.manager
            if isinstance(manager, _GeneratingModelManager):
                try:
                    return manager.generate(
                        prompt=prompt,
                        target=self._get_model_for_role("QA"),
                        max_tokens=256,
                    )
                except (RuntimeError, ValueError):
                    return ""
            return ""

        return create_evolution_coordinator(
            project_root=self.project_root,
            model_manager=self.manager,
            verify_fn=_sec_verify_fn if self.manager else None,
        )

    def _get_model_for_role(self, role: str) -> str:
        """역할에 맞는 모델을 반환합니다. config.yaml 매핑 우선."""
        return self.agent_models.get(role, self.agent_models.get("default", "qwen3.8"))

    def get_model_for_role(self, role: str) -> str:
        return self._get_model_for_role(role)

    @property
    def task_execution_context(self) -> TaskExecutionContext | None:
        return self._task_execution_context.get()

    @contextmanager
    def bind_task_execution(self, task_id: str, state_store: TaskStateStore) -> Generator[None, None, None]:
        execution_context = TaskExecutionContext(task_id, state_store)
        token = self._task_execution_context.set(execution_context)
        try:
            with bind_task_execution_context(execution_context):
                yield
        finally:
            self._task_execution_context.reset(token)

    # ─── Lazy Properties ─────────────────────────────────────────────

    def _default_reasoning_model(self) -> str:
        defaults = self.config.get("defaults")
        if isinstance(defaults, dict):
            model_name = defaults.get("reasoning")
            if isinstance(model_name, str) and model_name:
                return model_name
        return "qwen3.6:latest"

    def _compression_budget(self, target_model: str | None = None):
        return context_budget_for_model(self.config, target_model or self._default_reasoning_model())

    def _compression_summarize_fn(self):
        manager = self.manager
        if not isinstance(manager, _GeneratingModelManager):
            return None
        model_name = self._default_reasoning_model()

        def _summarize(prompt: str) -> str:
            return manager.generate(
                prompt=prompt,
                target=model_name,
                max_tokens=512,
            )

        return _summarize

    def _build_trajectory_compressor(self, target_model: str | None = None):
        from antigravity_k.engine.trajectory_compressor import TrajectoryCompressor

        budget = self._compression_budget(target_model)
        return TrajectoryCompressor(
            summarize_fn=self._compression_summarize_fn(),
            max_messages=budget.trajectory_max_messages,
            max_chars=budget.trajectory_max_chars,
            # 토큰 상한의 80%에서 트리거 — chars*4 가정이 한국어를 과대 허용해
            # 실제 컨텍스트 초과가 발생하기 전에 요약한다.
            max_tokens=int(budget.token_limit * 0.8),
        )

    def _build_context_compressor(self, target_model: str | None = None):
        from antigravity_k.engine.context_compressor import ContextCompressor

        budget = self._compression_budget(target_model)
        return ContextCompressor(
            token_limit=budget.token_limit,
            keep_last_n=10,
            summarize_fn=self._compression_summarize_fn(),
            persistence_dir=os.path.join(self.project_root, "data", "context_memory"),
        )

    @property
    def skill_auto_learner(self):
        """SkillAutoLearner 지연 초기화 (첫 접근 시 생성)."""
        if not self._skill_auto_learner_initialized:
            self._skill_auto_learner_initialized = True
            try:
                from antigravity_k.engine.skill_auto_learner import SkillAutoLearner

                self._skill_auto_learner_instance = SkillAutoLearner(
                    self.project_root,
                    self.manager,
                )
                logger.info("[Orchestrator] SkillAutoLearner (Closed Learning Loop) 활성화 완료")
            except (ImportError, RuntimeError, AttributeError):
                logger.warning("SkillAutoLearner init failed", exc_info=True)
                self._skill_auto_learner_instance = None
        return self._skill_auto_learner_instance

    @property
    def trajectory_compressor(self):
        """TrajectoryCompressor 지연 초기화 (첫 접근 시 생성)."""
        if not self._trajectory_compressor_initialized:
            self._trajectory_compressor_initialized = True
            try:
                self._trajectory_compressor_instance = self._build_trajectory_compressor()
                logger.info("[Orchestrator] TrajectoryCompressor 활성화 완료")
            except (ImportError, RuntimeError, AttributeError, ValueError):
                logger.warning("TrajectoryCompressor init failed", exc_info=True)
                self._trajectory_compressor_instance = None
        return self._trajectory_compressor_instance

    def trajectory_compressor_for(self, target_model: str):
        if target_model == self._default_reasoning_model():
            return self.trajectory_compressor
        try:
            return self._build_trajectory_compressor(target_model)
        except (ImportError, RuntimeError, AttributeError, ValueError):
            logger.warning("TrajectoryCompressor init failed", exc_info=True)
            return None

    @property
    def context_compressor(self):
        """ContextCompressor 지연 초기화 (토큰 예산 기반 적응형 압축).

        TrajectoryCompressor(메시지 수 기반)보다 정교한 토큰 예산 기반 압축을 수행합니다.
        작업 유형별로 keep_last_n과 max_tool_chars를 다르게 적용하며,
        pruned 메시지를 장기 기억 JSON으로 영속화합니다.
        summarize_fn이 없으면 휴리스틱 폴백으로 동작합니다 (LLM 호출 없음).
        """
        if not self._context_compressor_initialized:
            self._context_compressor_initialized = True
            try:
                self._context_compressor_instance = self._build_context_compressor()
                logger.info(
                    "[Orchestrator] ContextCompressor 활성화 완료 (token_limit=%s)",
                    self._context_compressor_instance.token_limit,
                )
            except (ImportError, RuntimeError, AttributeError, ValueError):
                logger.warning("ContextCompressor init failed", exc_info=True)
                self._context_compressor_instance = None
        return self._context_compressor_instance

    def context_compressor_for(self, target_model: str):
        if target_model == self._default_reasoning_model():
            return self.context_compressor
        # 모델별 인스턴스를 캐싱한다 — 도구 루프가 스텝마다 이 함수를 호출하는데
        # 매번 새로 만들면 long_term_memory.json을 디스크에서 다시 읽는다.
        cached = self._context_compressor_by_model.get(target_model)
        if cached is not None:
            return cached
        try:
            compressor = self._build_context_compressor(target_model)
        except (ImportError, RuntimeError, AttributeError, ValueError):
            logger.warning("ContextCompressor init failed", exc_info=True)
            return None
        if compressor is not None:
            self._context_compressor_by_model[target_model] = compressor
        return compressor

    # ─── 툴 프롬프트 ─────────────────────────────────────────────────

    def _build_tool_prompt(self, task_type: str = "") -> str:
        """도구 목록을 프롬프트에 주입합니다. few-shot 예시 포함."""
        tool_section = (
            "## Tool Usage Instructions\n"
            "You are a function calling AI model. You may call one or more functions to assist with the user query.\n"
            "Don't make assumptions about what values to plug into functions.\n"
            "To use a tool, you MUST use the <scratch_pad> XML tags to record your reasoning and planning before"
            "you call the function.\n\n"
            "<scratch_pad>\n"
            "Goal: <state task assigned by user>\n"
            "Actions: <describe what tools you will call>\n"
            "Observation: <set observation 'None' if you haven't called yet, or summarize previous tool results>\n"
            "Reflection: <evaluate if tools are relevant and if you have all required parameters>\n"
            "</scratch_pad>\n\n"
            "After the scratch_pad, output a JSON block wrapped in XML tags exactly like this:\n"
            "<tool_call>\n"
            '{"name": "tool_name", "arguments": {"arg1": "value1"}}\n'
            "</tool_call>\n\n"
            "CRITICAL RULES:\n"
            "- You can output MULTIPLE tool_call blocks sequentially if they can be executed in parallel.\n"
            "- Wait for ALL <tool_response> tags before making another batch of tool calls.\n"
            "- If no tool is needed, just answer directly without any tool_call or scratch_pad tags.\n"
            "OUTPUT QUALITY GATES:\n"
            "1. You MUST include Korean explanations even when asked for code. Do not just output code blocks.\n"
            "2. Provide Big-O notation (Time/Space complexity) for algorithmic tasks.\n"
            "3. Provide reasoning for your technical choices before or after code blocks.\n"
            "4. Use Markdown Tables when comparing 3 or more methods.\n"
            "5. Never repeat the same paragraph twice.\n\n"
            "### Example Usage:\n"
            "User: Show me the contents of main.py\n"
            "Assistant: \n"
            "<scratch_pad>\n"
            "Goal: Read the contents of main.py to answer the user.\n"
            "Actions: I will call read_file tool on main.py.\n"
            "Observation: None\n"
            "Reflection: I have the required file path. Ready to call.\n"
            "</scratch_pad>\n"
            "<tool_call>\n"
            '{"name": "read_file", "arguments": {"file_path": "main.py"}}\n'
            "</tool_call>\n\n"
            "## Available Tools\n"
        )
        tool_section += "\n" + self.ctx.prompt_builder.response_contract() + "\n"
        if hasattr(self.tool_registry, "render_autonomous_policy"):
            tool_section += "\n" + self.tool_registry.render_autonomous_policy() + "\n"
        try:
            from antigravity_k.engine.codex_transfer import CodexTransferEngine

            tool_section += "\n" + CodexTransferEngine().render_prompt_contract() + "\n"
        except ImportError:
            logger.debug("CodexTransferEngine 미설치 — prompt contract 생략")
        except (AttributeError, RuntimeError) as e:
            logger.warning("Codex operating contract unavailable: %s", e)
        try:
            from antigravity_k.engine.self_capability import SelfCapabilityEngine

            engine = SelfCapabilityEngine()
            snapshot = engine.build(
                tool_registry=self.tool_registry,
                skill_loader=self.ctx.skill_loader,
                model_manager=self.manager,
                project_root=self.project_root,
                slash_commands=getattr(self.ctx.slash_commands, "_commands", {}),
            )
            tool_section += "\n" + engine.render_prompt_contract(snapshot) + "\n"
        except ImportError:
            logger.debug("SelfCapabilityEngine 미설치 — prompt contract 생략")
        except (AttributeError, RuntimeError, ValueError) as e:
            logger.warning("Self-capability contract unavailable: %s", e)
        # ── 30B Model Amplification: Dynamic Tool Masking ──
        raw_schemas = self.tool_registry.to_llm_schemas()
        schemas_to_render: Sequence[object] = raw_schemas
        try:
            from antigravity_k.engine.tool_masker import ActiveToolMasker

            masker = ActiveToolMasker(mode=self.mode_manager.current_mode)
            phase = masker.phase_for_task_type(task_type)
            schemas_to_render = masker.filter_tools(raw_schemas, phase=phase)
        except Exception:
            schemas_to_render = raw_schemas

        for schema_value in schemas_to_render:
            schema = _object_mapping(schema_value)
            params = _object_mapping(schema.get("input_schema", {}))
            required = _string_list(params.get("required"))
            tool_section += f"- **{schema['name']}**: {schema['description']}\n"
            props = _object_mapping(params.get("properties"))
            if props:
                param_strs: list[str] = []
                for k, v in props.items():
                    p_type = _object_mapping(v).get("type", "any")
                    p_req = "required" if k in required else "optional"
                    param_strs.append(f"{k} ({p_type}, {p_req})")
                tool_section += f"  Parameters: {', '.join(param_strs)}\n"
        return tool_section

    def _requires_planning_mode(self, task_type: str, messages: list[dict[str, str]]) -> bool:  # pyright: ignore[reportUnusedFunction]
        """복잡한 구조 변경에만 Planning Mode를 강제합니다.

        ModeManager의 should_enforce_plan_mode()에 위임합니다.
        """
        if hasattr(self, "mode_manager") and self.mode_manager:
            user_text = self._latest_user_text(messages)
            return self.mode_manager.should_enforce_plan_mode(task_type, user_text)

        # Fallback (ModeManager 미연결 시 레거시 로직)
        if task_type == "complex":
            return True
        if task_type != "coding":
            return False
        request_text = "\n".join(str(msg.get("content", "")) for msg in messages if msg.get("role") == "user").lower()
        return bool(
            re.search(
                "(아키텍처|구조|전면|대규모|마이그레이션|프레임워크|리팩토링|"
                + "architecture|refactor|migrate|framework|plugin system)",
                request_text,
            ),
        )

    def _execute_tool(self, name: str, args: dict[str, object]) -> str:  # pyright: ignore[reportUnusedFunction]
        """ToolExecutor에 위임합니다. (Phase 1 D3: execution_mode 전달)"""
        mode = self._get_execution_mode()
        return self.ctx.tool_executor.execute(name, args, execution_mode=mode)

    def _get_execution_mode(self) -> str:
        """현재 실행 모드 문자열을 반환합니다. ("plan", "build", "interactive")

        ModeManager가 없으면 기본값 "interactive" 반환.
        PlanGuard, GatePipeline, QualityGate에 execution_mode를 전달하는 소스 역할.
        """
        if hasattr(self, "mode_manager") and self.mode_manager:
            try:
                return self.mode_manager.current_mode.value
            except (AttributeError, ValueError):
                logger.debug("mode_manager.current_mode 조회 실패 — interactive로 폴백")
        return "interactive"

    def _inject_mode_prompt(
        self,
        system_prompt: str,
        _task_type: str,
        _messages: list[dict[str, str]],
        delegate_to: str,
    ) -> str:
        """현재 실행 모드에 따라 system prompt에 모드별 지시사항을 주입합니다.

        PLAN 모드:
          - ArtifactEngine.inject_planning_prompt() 또는 PLANNING_MODE_BLOCK 추가
          - 읽기 전용 도구만 사용하도록 강제

        BUILD 모드:
          - Plan이 검증되었음을 명시
          - Plan 태스크를 실행할 것을 지시
          - 모든 도구 사용 가능

        INTERACTIVE 모드:
          - 기존 동작 유지 (추가 주입 없음)

        Args:
            system_prompt: 원본 system prompt
            task_type: 태스크 유형
            messages: 대화 메시지
            delegate_to: 위임 대상 역할

        Returns:
            모드별 지시사항이 추가된 system prompt
        """
        mode = self._get_execution_mode()

        if mode == "plan" and delegate_to != "CEO":
            # PLAN 모드: 계획 수립 프롬프트 주입
            if hasattr(self, "artifact_engine") and self.artifact_engine:
                planning_mode_enforcement = self.artifact_engine.inject_planning_prompt()
            else:
                planning_mode_enforcement = PLANNING_MODE_BLOCK
            system_prompt += planning_mode_enforcement

        elif mode == "build" and delegate_to != "CEO":
            # BUILD 모드: 실행 중심 프롬프트 주입
            plan_path = ""
            if hasattr(self.mode_manager, "plan_artifact_path") and self.mode_manager.plan_artifact_path:
                plan_path = self.mode_manager.plan_artifact_path

            build_prompt = (
                "\n\n[EXECUTION MODE: BUILD]\n"
                "You are now in BUILD MODE. The plan has been validated and approved.\n"
                "1. Execute the tasks defined in the plan using all available tools.\n"
                "2. You have full access to all tools — read, write, execute, and manage files.\n"
                "3. Follow the plan's implementation steps in order.\n"
                "4. After completing each task, update the task status in the Kanban board.\n"
                "5. If you encounter unexpected issues, document them and adjust the approach.\n"
            )
            if plan_path:
                build_prompt += f"\nReference Plan: `{plan_path}`\n"

            system_prompt += build_prompt

        # INTERACTIVE 모드와 CEO 역할은 추가 주입 없음

        return system_prompt

    def _latest_user_text(self, messages: Sequence[Mapping[str, object]]) -> str:
        """최근 user 메시지의 텍스트만 반환합니다."""
        for msg in reversed(messages):
            if msg.get("role") != "user":
                continue
            content = msg.get("content", "")
            if isinstance(content, str):
                return content.strip()
            if isinstance(content, list):
                parts = cast(list[object], content)
                text_parts = [
                    str(part_map.get("text", ""))
                    for part in parts
                    if (part_map := _object_mapping(part)).get("type") == "text"
                ]
                return " ".join(text_parts).strip()
        return ""

    def _render_self_capability_response(self) -> str:  # pyright: ignore[reportUnusedFunction]
        """런타임 사실 기반 자기 능력 보고서를 생성합니다."""
        from antigravity_k.engine.self_capability import SelfCapabilityEngine

        engine = SelfCapabilityEngine()
        snapshot = engine.build(
            tool_registry=self.tool_registry,
            skill_loader=self.ctx.skill_loader,
            model_manager=self.manager,
            project_root=self.project_root,
            slash_commands=getattr(self.ctx.slash_commands, "_commands", {}),
        )
        return engine.render_markdown(snapshot)

    def _register_claw_tools(self) -> None:  # pyright: ignore[reportUnusedFunction]
        """ToolExecutor에 도구를 등록합니다."""
        self.ctx.tool_executor.register_default_tools()

    # ─── CEO 분석 단계 ───────────────────────────────────────────────

    def _ceo_analyze(  # pyright: ignore[reportUnusedFunction]
        self,
        user_message: str,
        target_model: str,
    ) -> Generator[str | JsonObject, None, None]:
        """CEO 분석을 ceo_analyzer 모듈에 위임합니다."""
        result = _ceo_analyze_fn(
            user_message=user_message,
            target_model=target_model,
            ceo_prompt_template=get_orchestrator_prompt("CEO"),
            model_manager=self.manager,
        )
        yield from result

    def _rebuild_prompt(  # pyright: ignore[reportUnusedFunction]
        self,
        system_prompt: str,
        tool_prompt: str,
        skill_prompts: str,
        messages: list[dict[str, str]],
    ) -> str:
        """컨텍스트 압축 후 프롬프트를 재구성합니다."""
        prompt = f"System: {system_prompt}\n{skill_prompts}\n"
        if tool_prompt:
            prompt += f"\n{tool_prompt}\n"
        prompt += "\n"
        for msg in messages:
            prompt += f"{msg['role'].capitalize()}: {msg['content']}\n"
        prompt += "Assistant: "
        return prompt

    def _prepare_agent_prompt(  # pyright: ignore[reportUnusedFunction]
        self,
        messages: list[dict[str, str]],
        delegate_to: str,
        task_type: str,
    ) -> tuple[str, str, str, str, str, list[dict[str, str]]]:
        """에이전트 실행에 필요한 프롬프트와 컨텍스트를 준비합니다.

        Returns:
            (delegate_model, system_prompt, tool_prompt, skill_prompts,
             prompt, shaped_messages)

        """
        delegate_model = self._get_model_for_role(delegate_to)
        system_prompt = get_orchestrator_prompt(delegate_to)

        # 실행 모드에 따라 system prompt 분기 (Phase 1 D5)
        system_prompt = self._inject_mode_prompt(system_prompt, task_type, messages, delegate_to)

        tool_prompt = self._build_tool_prompt(task_type) if delegate_to != "CEO" else ""

        # 에러 카운터 리셋
        self.ctx.tool_executor.reset_error_counter()
        user_objective = messages[-1].get("content", "") if messages else ""
        if hasattr(self.ctx.tool_executor, "set_objective"):
            self.ctx.tool_executor.set_objective(user_objective)

        # 인지 루프 초기화
        if self.ctx.cognitive_loop:
            self.ctx.cognitive_loop.reset()
        if self.ctx.quality_gate:
            self.ctx.quality_gate.reset()

        # 실패 학습 컨텍스트 주입
        failure_context = ""

        # Skill injection
        skill_prompts = ""
        if hasattr(self.ctx, "skill_loader") and self.ctx.skill_loader:
            skill_prompts = self.ctx.skill_loader.get_active_prompts()

        # IDE Context injection
        ide_prompt = self.ctx.ide_manager.format_prompt() if hasattr(self.ctx, "ide_manager") else ""
        if ide_prompt:
            skill_prompts += "\n" + ide_prompt

        # ── 30B Model Amplification: Deterministic Structural Context & Working Memory ──
        pinned_context = ""
        try:
            from antigravity_k.engine.structural_snapshot import StructuralSnapshotBuilder
            from antigravity_k.engine.working_memory_compactor import WorkingMemoryCompactor

            snapshot = StructuralSnapshotBuilder.build(self.project_root)
            working_mem = WorkingMemoryCompactor.compact(messages)
            pinned_context = (
                snapshot.format_pinned_block() + "\n\n" + working_mem.format_pinned_working_memory() + "\n\n"
            )
        except Exception as se:
            logger.debug("StructuralSnapshot/WorkingMemory build skipped: %s", se)

        # ── KV-cache 안정 접두사 ──
        # pinned_context(구조 스냅샷+작업 메모리)는 매 턴 내용이 바뀐다 —
        # 접두사에 두면 시스템 프롬프트·도구 가이드가 포함된 캐시 가능한
        # 접두사 전체가 무효화된다. 변동 블록을 후미(recency)로 옮겨
        # 접두사를 바이트 단위로 안정화한다. 후미 배치는 주의 집중
        # (recency) 관점에서도 유리하다.
        prompt = f"System: {system_prompt}\n{skill_prompts}\n"
        if failure_context:
            prompt += f"\n{failure_context}\n"
        if tool_prompt:
            prompt += f"\n{tool_prompt}\n"
        prompt += "\n"

        # Context Shaper 적용 — aux(system/tools/skills/pinned)를 메시지 예산에서 선공제 (CTX-02)
        execution_plan: LongContextExecutionPlan | None = None
        manager = self.manager
        if isinstance(manager, LongContextPlanner):
            execution_plan = manager.long_context_plan(delegate_model)
        from antigravity_k.engine.tokenizer import TokenEstimator

        _aux_overhead = TokenEstimator.estimate_text(
            f"System: {system_prompt}\n{skill_prompts}\n"
            + (f"\n{tool_prompt}\n" if tool_prompt else "")
            + (f"<working_context>\n{pinned_context}</working_context>\n" if pinned_context else ""),
        )
        shaped_messages = self.context_shaper.shape_for_model(
            messages,
            self.config,
            delegate_model,
            execution_plan=execution_plan,
            aux_token_overhead=_aux_overhead,
        )
        shaped_messages = self.context_shaper.clear_old_tool_results(shaped_messages)

        # Decision Anchor 주입
        decision_anchor = self.ctx.decision_anchor
        if decision_anchor:
            shaped_messages = decision_anchor.inject_into_messages(shaped_messages)

        # Budget Awareness 주입
        shaped_messages = self.context_shaper.inject_budget_awareness(shaped_messages)

        for msg in shaped_messages:
            prompt += f"{msg['role'].capitalize()}: {msg['content']}\n"
        if pinned_context:
            prompt += f"<working_context>\n{pinned_context}</working_context>\n"
        prompt += "Assistant: "

        # 컨텍스트 압축/재구축 경로에서 원본 프롬프트 구조(고정 컨텍스트 포함)를
        # 보존할 수 있도록 구성요소를 캐시한다.
        self._prompt_components_cache = {
            "pinned_context": pinned_context,
            "system_prompt": system_prompt,
            "tool_prompt": tool_prompt,
            "skill_prompts": skill_prompts,
        }

        return (
            delegate_model,
            system_prompt,
            tool_prompt,
            skill_prompts,
            prompt,
            shaped_messages,
        )

    # ─── 실행 ─────────────────────────────────────────────────────────

    @property
    def code_tree_indexer(self) -> _CodeTreeIndexer | None:
        """CodeTreeIndexer 지연 초기화 (Freebuff-Style 자동 컨텍스트).

        최초 접근 시 1회 빌드되며, 이후 변경 감지로 증분 갱신됩니다.
        빌드 실패 시 None을 반환하여 메인 플로우에 영향을 주지 않습니다.
        """
        if self._code_tree_indexer is None:
            try:
                from antigravity_k.engine.code_tree_indexer import CodeTreeIndexer

                self._code_tree_indexer = cast(
                    _CodeTreeIndexer,
                    CodeTreeIndexer(project_root=self.project_root),
                )
                logger.info("[Proactive] CodeTreeIndexer 활성화 완료")
            except (ImportError, RuntimeError, AttributeError):
                logger.debug("CodeTreeIndexer init failed (non-critical)")
                self._code_tree_indexer = None

            # 최초 1회는 try/except 밖에서 백그라운드 빌드 시도
            if self._code_tree_indexer:
                try:
                    _ = self._code_tree_indexer.build_tree()
                    stats = self._code_tree_indexer.stats()
                    logger.info(
                        "[Proactive] Code tree built: %s files, %s KB",
                        stats["files_indexed"],
                        stats["tree_size_kb"],
                    )
                except (RuntimeError, KeyError):
                    logger.debug("CodeTree 초기 빌드 실패 (non-critical)")

        return self._code_tree_indexer

    @property
    def max_engine(self) -> MaxEnginePort | None:
        """MaxModeEngine 지연 초기화 (P4: MAX Mode 병렬 편집).

        여러 워커를 병렬로 실행하고 Selector가 최적 결과를 선정합니다.
        실패 시 None을 반환하여 메인 플로우에 영향 없음.
        """
        if self._max_engine is None:
            try:
                from antigravity_k.engine.max_engine import MaxModeEngine

                manager = self.manager
                if not isinstance(manager, _GeneratingModelManager):
                    return None
                self._max_engine = MaxModeEngine(
                    model_manager=manager,
                    project_root=self.project_root,
                )

                # 워커 수 설정 (config에서 또는 기본값)
                max_workers = 3
                max_mode = self.ctx.config.get("max_mode")
                if isinstance(max_mode, dict):
                    configured_workers = max_mode.get("max_workers")
                    if isinstance(configured_workers, int):
                        max_workers = configured_workers
                self._max_engine.set_max_workers(max_workers)

                logger.info("[MAX] MaxModeEngine 활성화 완료 (%s workers)", max_workers)
            except (ImportError, RuntimeError, AttributeError):
                logger.debug("MaxModeEngine init failed (non-critical)")
                self._max_engine = None

        return self._max_engine

    def shutdown(self) -> None:
        """Release project-scoped watchers, caches, and closable handles (WS-03).

        Safe to call multiple times. Does not delete on-disk persistence under
        ``project_root`` — only process-local resources are closed so another
        project's runtime stays intact.
        """
        watchdog = getattr(self, "watchdog", None)
        if watchdog is not None:
            stop = getattr(watchdog, "stop", None)
            if callable(stop):
                try:
                    stop()
                except Exception:
                    logger.exception("AmbientWatchdog stop failed during orchestrator shutdown")
            self.watchdog = None

        rag = getattr(self, "_rag_indexer", None)
        if rag is not None:
            vector_store = getattr(rag, "vector_store", None)
            if vector_store is not None:
                close = getattr(vector_store, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception:
                        logger.exception("RAG vector_store close failed during orchestrator shutdown")
            self._rag_indexer = None

        self._context_compressor_by_model.clear()
        self._context_compressor_initialized = False
        self._context_compressor_instance = None
        self._trajectory_compressor_initialized = False
        self._trajectory_compressor_instance = None
        self._prompt_components_cache = {}
        self._code_tree_indexer = None
        self._skill_auto_learner_initialized = False
        self._skill_auto_learner_instance = None

    def run_stream(
        self,
        messages: list[dict[str, str]],
        target_model: str,
        max_steps: int = 15,
        ephemeral_message: str | None = None,
    ) -> Generator[str, None, None]:
        """State Graph 기반 멀티 에이전트 스트리밍 실행.

        내부 구현은 orchestrator.stream 모듈에 위임됩니다.
        """
        from antigravity_k.engine.orchestrator.stream import run_stream as _stream_run

        yield from _stream_run(self, messages, target_model, max_steps, ephemeral_message)

    def run_sync(
        self,
        messages: list[dict[str, str]],
        target_model: str,
        max_steps: int = 15,
    ) -> str:
        """동기식 실행 (커맨드 팔레트 등에서 사용)."""
        from antigravity_k.engine.orchestrator.stream import run_sync as _sync_run

        return _sync_run(self, messages, target_model, max_steps)
