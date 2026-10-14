"""SlashCommand DTO and registry mechanics.

Extracted from ``slash_commands.py``. This module contains the data model
(``SlashCommand``), the registry core (init, register, dispatch, completions),
and a data-driven ``_register_defaults`` that replaces the former 337-line
boilerplate with a compact table.

The actual ``_cmd_*`` handler methods live in the mixin modules
(``slash_commands_session``, ``slash_commands_workflow``, ``slash_commands_skills``)
and are composed into ``SlashCommandRegistry`` via multiple inheritance in
``slash_commands.py``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from functools import partial
from typing import Protocol, cast, final

logger = logging.getLogger(__name__)


Message = dict[str, object]


class _ModelManagerLike(Protocol):
    def get_model_info(self) -> object: ...


class _SessionManagerLike(Protocol):
    def get_messages(self) -> list[Message]: ...


class _AgentRuntimeLike(Protocol):
    def complete(self, messages: list[Message], *, target_model: str) -> str: ...


@final
class SlashCommand:
    """슬래시 커맨드 정의."""

    def __init__(
        self,
        name: str,
        description: str,
        handler: Callable[[list[str]], str | Iterator[str]],
        usage: str = "",
        category: str = "general",
    ):
        self.name: str = name
        self.description: str = description
        self.handler: Callable[[list[str]], str | Iterator[str]] = handler
        self.usage: str = usage or f"/{name}"
        self.category: str = category


# ---------------------------------------------------------------------------
# Default command catalog — a compact data table that drives _register_defaults.
# Each tuple: (name, description, method_attr, usage, category)
# "method_attr" is resolved via getattr(self, ...) at registration time, so the
# bound methods from any mixin are picked up automatically.
# ---------------------------------------------------------------------------
_DEFAULT_COMMANDS: list[tuple[str, str, str, str, str]] = [
    # Session / context
    ("help", "사용 가능한 슬래시 커맨드 목록을 표시합니다.", "_cmd_help", "/help", "general"),
    ("tools", "등록된 도구 목록과 상태를 표시합니다.", "_cmd_tools", "/tools [category]", "tools"),
    ("context", "현재 컨텍스트 토큰 사용량을 분석합니다.", "_cmd_context", "/context", "context"),
    ("memory", "세션 Working Memory 내용을 조회합니다.", "_cmd_memory", "/memory [key]", "session"),
    ("model", "현재 모델 정보를 확인하거나 변경합니다.", "_cmd_model", "/model [model_name]", "model"),
    ("status", "에이전트 전체 상태를 요약합니다.", "_cmd_status", "/status", "general"),
    ("compact", "수동으로 컨텍스트 압축을 트리거합니다.", "_cmd_compact", "/compact", "context"),
    ("session", "세션 관리 (list/save/load/info).", "_cmd_session", "/session [list|save|load <id>|info]", "session"),
    (
        "project",
        "새 프로젝트를 초기화하고 해당 폴더로 컨텍스트를 바인딩합니다.",
        "_cmd_project",
        "/project <folder_path>",
        "session",
    ),
    (
        "resume",
        "최신 DB 체크포인트에서 상태를 복구하여 작업을 이어서 진행합니다.",
        "_cmd_resume",
        "/resume [trace_id]",
        "session",
    ),
    # Skills / capabilities
    (
        "self",
        "현재 런타임 기준으로 Ssak-Ai가 할 수 있는 일과 한계를 표시합니다.",
        "_cmd_self",
        "/self",
        "general",
    ),
    (
        "agentic",
        "최신 에이전틱 기술 레이더와 Ssak-Ai 업그레이드 우선순위를 표시합니다.",
        "_cmd_agentic",
        "/agentic [objective]",
        "autonomy",
    ),
    (
        "mcp",
        "MCP 최신 기능 레이더, 서버 설정 감사, 안전 템플릿을 표시합니다.",
        "_cmd_mcp",
        "/mcp [radar|audit <path>|template]",
        "tools",
    ),
    (
        "market",
        "Skill Marketplace: search, install, remove, list, info, update skills.",
        "_cmd_market",
        "/market [search|install|remove|list|info|update]",
        "tools",
    ),
    (
        "capabilities",
        "현재 PC/도구/MCP/Skills의 자율 사용 가능 여부를 판단합니다.",
        "_cmd_capabilities",
        "/capabilities [objective]",
        "autonomy",
    ),
    (
        "codex",
        "Codex식 강점과 운영 루프를 Ssak-Ai 업그레이드 계약으로 변환합니다.",
        "_cmd_codex",
        "/codex [objective]",
        "autonomy",
    ),
    (
        "evolve",
        "본 프로그램 스스로 코드를 수정, 검증하고 문서를 업데이트하는 메타 진화를 수행합니다.",
        "_cmd_evolve",
        "/evolve <기능 고도화 요구사항>",
        "autonomy",
    ),
    # Workflow / mode
    ("qa", "DOM 파싱 도구를 사용해 대시보드 UI를 자가 점검합니다.", "_cmd_qa", "/qa [url]", "system"),
    (
        "goal",
        "자율 목표를 성공 기준, 실행 루프, 검증 게이트로 변환합니다.",
        "_cmd_goal",
        "/goal <objective>",
        "autonomy",
    ),
    (
        "mode",
        "현재 실행 모드(Plan/Build/Interactive) 상태를 표시하거나 변경합니다.",
        "_cmd_mode",
        "/mode [plan|build|interactive|status]",
        "system",
    ),
    ("plan", "Plan 모드로 전환합니다. 읽기 전용 도구만 허용됩니다.", "_cmd_plan", "/plan [이유]", "system"),
    (
        "build",
        "Build 모드로 전환합니다. 모든 도구 실행이 허용됩니다.",
        "_cmd_build",
        "/build [plan_artifact_path]",
        "system",
    ),
    (
        "aishell",
        "자연어 지시를 파싱하여 터미널(Bash) 커맨드로 즉시 변환 후 실행합니다.",
        "_cmd_aishell",
        "/aishell <명령어>",
        "system",
    ),
    (
        "benchmark",
        "collective-council vs 단일 모델 품질/속도 벤치마크를 실행하거나 누적 비교표를 출력합니다.",
        "_cmd_benchmark",
        "/benchmark [run [suite|case-id] | report [suite] | clear]",
        "system",
    ),
    (
        "dialectic",
        "Hegelion 변증법적 추론 (Thesis→Antithesis→Synthesis) 으로 문제를 심층 분석합니다.",
        "_cmd_dialectic",
        "/dialectic <질문 또는 문제>",
        "autonomy",
    ),
    (
        "finance",
        "금융 숫자 추출은 가능하며 DCF·Comps·3-Statement 계산 미지원 상태를 안내합니다.",
        "_cmd_finance",
        "/finance <분석 대상 및 상황>",
        "finance",
    ),
    (
        "comps",
        "Comps 계산 미지원 — 기업 자료에서 명시적 금융 숫자만 추출합니다.",
        "_cmd_finance",
        "/comps <기업명>",
        "finance",
    ),
    (
        "dcf",
        "DCF 계산 미지원 — 기업 자료에서 명시적 금융 숫자만 추출합니다.",
        "_cmd_finance",
        "/dcf <기업명>",
        "finance",
    ),
    # System passthroughs
    ("approve", "대기 중인 도구 실행을 승인합니다.", "_cmd_approve", "/approve <tool_name>", "system"),
    (
        "browse",
        "특화된 서브 에이전트를 통해 웹 브라우저를 자율 탐색합니다.",
        "_cmd_browse",
        "/browse <url> [지시사항]",
        "system",
    ),
    (
        "skill",
        "특정 스킬(Markdown 지침서)을 에이전트 시스템 프롬프트에 주입하거나 관리합니다.",
        "_cmd_skill",
        "/skill [list|activate <id>|deactivate <id>|clear]",
        "system",
    ),
]

# Lifecycle commands use a shared handler with the command name as first arg.
_LIFECYCLE_COMMANDS: list[tuple[str, str]] = [
    ("spec", "Spec before code. Write a PRD covering objectives."),
    ("plan-lifecycle", "Small, atomic tasks. Decompose specs into implementable units."),
    ("build-lifecycle", "One slice at a time. Implement incrementally."),
    ("test", "Tests are proof. Red-Green-Refactor."),
    ("review", "Improve code health. Five-axis code review."),
    ("code-simplify", "Clarity over cleverness. Reduce complexity."),
    ("ship", "Faster is safer. Pre-launch checks and staged rollouts."),
]


class SlashCommandRegistryBase:
    """Core registry mechanics — init, register, dispatch, completions.

    Subclasses (via mixin composition in ``slash_commands.py``) provide the
    ``_cmd_*`` handler methods. This base only manages the command table and
    the dispatch loop.
    """

    def __init__(
        self,
        tool_registry: object | None = None,
        session_manager: object | None = None,
        context_shaper: object | None = None,
        model_manager: object | None = None,
        skill_loader: object | None = None,
        mode_manager: object | None = None,
        agent_runtime: object | None = None,
    ) -> None:
        setattr(self, "_commands", {})
        setattr(self, "_tool_registry", tool_registry)
        setattr(self, "_session_manager", session_manager)
        setattr(self, "_context_shaper", context_shaper)
        setattr(self, "_model_manager", model_manager)
        setattr(self, "_skill_loader", skill_loader)
        setattr(self, "_mode_manager", mode_manager)
        setattr(self, "_agent_runtime", agent_runtime)

        self._register_defaults()

    def bind_runtime(self, runtime: object) -> None:
        setattr(self, "_agent_runtime", runtime)

    def _register_defaults(self) -> None:
        """Register all default slash commands from the data table."""
        for name, desc, method_attr, usage, category in _DEFAULT_COMMANDS:
            handler = cast(Callable[[list[str]], str | Iterator[str]] | None, getattr(self, method_attr, None))
            if handler is None:
                logger.warning("Slash command /%s has no handler method %s", name, method_attr)
                continue
            self.register(SlashCommand(name=name, description=desc, handler=handler, usage=usage, category=category))

        # Lifecycle commands share a single handler, parameterized by name.
        for cmd_name, desc in _LIFECYCLE_COMMANDS:
            # Use a distinct registration name to avoid collision with
            # plan/build mode commands. The original code registered them
            # as "plan", "build" etc., which collided — here we use the
            # skill-name as-is but route through _cmd_lifecycle.
            real_name = cmd_name.replace("-lifecycle", "")
            lifecycle_handler = cast(
                Callable[[str, list[str]], str | Iterator[str]], object.__getattribute__(self, "_cmd_lifecycle")
            )
            self.register(
                SlashCommand(
                    name=real_name,
                    description=desc,
                    handler=partial(lifecycle_handler, real_name),
                    usage=f"/{real_name} [arguments]",
                    category="lifecycle",
                ),
            )

    def register(self, command: SlashCommand):
        """커맨드를 등록합니다."""
        commands = cast(dict[str, SlashCommand], getattr(self, "_commands"))
        commands[command.name] = command

    def is_command(self, text: str) -> bool:
        """텍스트가 슬래시 커맨드인지 확인합니다."""
        if not text.startswith("/"):
            return False
        cmd_name = text.split()[0][1:]  # / 제거
        commands = cast(dict[str, SlashCommand], getattr(self, "_commands"))
        return cmd_name in commands

    def execute(self, text: str) -> str | Iterator[str]:
        """슬래시 커맨드를 실행하거나 자연어 의도를 처리합니다."""
        text = (text or "").strip()
        if not text:
            return "Error: Empty command."

        if not text.startswith("/"):
            return self._execute_natural_language(text)

        parts = text.split()
        if not parts:
            return "Error: Empty command."

        cmd_name = parts[0][1:]  # / 제거
        args = parts[1:]

        commands = cast(dict[str, SlashCommand], getattr(self, "_commands"))
        command = commands.get(cmd_name)
        if not command:
            return f"Unknown command: /{cmd_name}. Use /help to see available commands."

        try:
            return command.handler(args)
        except Exception as e:
            logger.error("Slash command error: %s", e, exc_info=True)
            return f"Error executing /{cmd_name}: {e}"

    def _execute_natural_language(self, text: str) -> str:
        """슬래시가 없는 자연어를 받아서 로컬 모델을 통해 자율적으로 도구를 실행하고 답변을 반환합니다."""
        model_manager = cast(_ModelManagerLike | None, getattr(self, "_model_manager", None))
        if model_manager is None:
            return "Error: Model manager is not available for natural language execution."

        info = model_manager.get_model_info()
        target_model: str
        if isinstance(info, dict):
            info_mapping = cast(dict[str, object], info)
            target_model = cast(str, info_mapping.get("active_model", "default"))
        else:
            target_model = cast(str, getattr(info, "active_model", "default"))
        if target_model == "default" or not target_model:
            target_model = "local-model"

        messages: list[Message] = []
        session_manager = cast(_SessionManagerLike | None, getattr(self, "_session_manager", None))
        if session_manager is not None:
            session_msgs = session_manager.get_messages()
            messages = session_msgs[-5:] if len(session_msgs) > 5 else session_msgs

        messages.append({"role": "user", "content": text})

        try:
            agent_runtime = cast(_AgentRuntimeLike | None, getattr(self, "_agent_runtime", None))
            if agent_runtime is not None:
                return agent_runtime.complete(messages, target_model=target_model)
            from antigravity_k.engine.orchestrator import OrchestratorAgent
            from antigravity_k.engine.orchestrator.agent import ModelManagerPort

            orchestrator = OrchestratorAgent(model_manager=cast(ModelManagerPort | None, model_manager))
            return orchestrator.run_sync(cast(list[dict[str, str]], messages), target_model=target_model)
        except Exception as e:
            logger.error("Natural language execution error: %s", e, exc_info=True)
            return f"자연어 처리 중 오류 발생: {e}"

    def get_completions(self, prefix: str) -> list[str]:
        """자동완성 후보를 반환합니다."""
        if not prefix.startswith("/"):
            return []
        cmd_prefix = prefix[1:]  # / 제거
        commands = cast(dict[str, SlashCommand], getattr(self, "_commands"))
        return [f"/{cmd.name}" for cmd in commands.values() if cmd.name.startswith(cmd_prefix)]
