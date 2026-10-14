"""Session/context slash command handlers (mixin).

Provides: /help, /tools, /context, /memory, /model, /status, /compact,
/session, /resume, /project.

These handlers access ``self._session_manager``, ``self._context_shaper``,
``self._tool_registry``, and ``self._model_manager`` which are initialized by
``SlashCommandRegistryBase.__init__``.
"""

from __future__ import annotations

import logging
from typing import Callable, ClassVar, Protocol, TypedDict, cast

from antigravity_k.engine.slash_commands_base import SlashCommand

logger = logging.getLogger(__name__)


class _Usage(TypedDict):
    usage_pct: float
    total_tokens: int
    max_tokens: int
    budget_remaining: int
    by_role: dict[str, int]


class _SessionInfo(TypedDict):
    id: str
    turn_count: int
    message_count: int
    memory_keys: list[str]


class _SessionLike(Protocol):
    _current_session: dict[str, object]

    def get_messages(self) -> list[dict[str, object]]: ...

    def get_memory(self, key: str) -> object | None: ...

    def get_all_memory(self) -> dict[str, object]: ...

    def get_session_info(self) -> _SessionInfo | None: ...

    def list_sessions(self) -> list[dict[str, object]]: ...

    def save(self) -> None: ...

    def load_session(self, session_id: str) -> bool: ...

    def start_session(self, *, project_path: str, resume: bool) -> None: ...


class _ContextShaperLike(Protocol):
    def get_token_usage(self, messages: list[dict[str, object]]) -> _Usage: ...

    def get_stats(self) -> dict[str, int]: ...

    def shape(self, messages: list[dict[str, object]]) -> list[dict[str, object]]: ...

    def _estimate_tokens(self, messages: list[dict[str, object]]) -> int: ...


class _ModelManagerLike(Protocol):
    def set_model(self, model_name: str) -> None: ...

    def get_model_info(self) -> object: ...


class _ValueLike(Protocol):
    value: str


class _ToolLike(Protocol):
    category: _ValueLike
    risk_level: _ValueLike
    icon: str
    name: str
    description: str


class _ToolRegistryLike(Protocol):
    def get_all(self) -> list[_ToolLike]: ...

    def set_project_root(self, path: str) -> None: ...

    def __len__(self) -> int: ...


ModelManagerProtocol = _ModelManagerLike
ToolRegistryProtocol = _ToolRegistryLike


class SlashCommandSessionMixin:
    """Session and context management command handlers.

    Note: The following attributes are provided by ``SlashCommandRegistryBase``
    via cooperative multiple inheritance (MRO).
    """

    # Mixin-required attributes (resolved via MRO at runtime)
    _commands: ClassVar[dict[str, SlashCommand]]
    _tool_registry: ClassVar[_ToolRegistryLike | None]
    _session_manager: ClassVar[_SessionLike | None]
    _context_shaper: ClassVar[_ContextShaperLike | None]
    _model_manager: ClassVar[_ModelManagerLike | None]

    def _cmd_help(self, _args: list[str]) -> str:
        """도움말 표시."""
        lines = ["📚 **Ssak-Ai 슬래시 커맨드**", ""]

        categories: dict[str, list[SlashCommand]] = {}
        for cmd in self._commands.values():
            categories.setdefault(cmd.category, []).append(cmd)

        for cat, cmds in sorted(categories.items()):
            lines.append(f"### {cat.upper()}")
            for cmd in sorted(cmds, key=lambda c: c.name):
                lines.append(f"  `{cmd.usage}` — {cmd.description}")
            lines.append("")

        return "\n".join(lines)

    def _cmd_tools(self, args: list[str]) -> str:
        """도구 목록 표시."""
        if not self._tool_registry:
            return "Tool registry not connected."

        lines = ["🔧 **등록된 도구 목록**", ""]

        tools = self._tool_registry.get_all()
        if args:
            tools = [t for t in tools if t.category.value == args[0]]

        for tool in tools:
            risk_icon = {
                "safe": "🟢",
                "low": "🟡",
                "medium": "🟠",
                "high": "🔴",
                "critical": "⛔",
            }.get(tool.risk_level.value, "⚪")
            lines.append(f"  {tool.icon} `{tool.name}` {risk_icon} — {tool.description[:60]}")

        lines.append(f"\n총 {len(tools)}개 도구 등록됨")
        return "\n".join(lines)

    def _cmd_context(self, _args: list[str]) -> str:
        """컨텍스트 토큰 사용량 분석."""
        if not self._context_shaper:
            return "Context shaper not connected."
        if not self._session_manager:
            return "Session manager not connected."

        messages = self._session_manager.get_messages()
        usage = self._context_shaper.get_token_usage(messages)
        stats = self._context_shaper.get_stats()

        bar_len = 20
        filled = int(bar_len * usage["usage_pct"] / 100)
        bar = "█" * filled + "░" * (bar_len - filled)

        lines = [
            "📊 **컨텍스트 토큰 사용량**",
            "",
            f"  [{bar}] {usage['usage_pct']}%",
            f"  사용: {usage['total_tokens']:,} / {usage['max_tokens']:,} tokens",
            f"  잔여: {usage['budget_remaining']:,} tokens",
            "",
            "  **역할별 사용량:**",
        ]
        for role, tokens in sorted(usage["by_role"].items()):
            lines.append(f"    {role}: {tokens:,} tokens")

        lines.extend(
            [
                "",
                "  **압축 통계:**",
                f"    총 압축: {stats.get('total_shaped', 0)}회",
                f"    절약 토큰: {stats.get('tokens_saved', 0):,}",
                f"    콘텐츠 축소: {stats.get('collapses', 0)}건",
            ]
        )
        return "\n".join(lines)

    def _cmd_memory(self, args: list[str]) -> str:
        """Working Memory 조회."""
        if not self._session_manager:
            return "Session manager not connected."

        if args:
            value = self._session_manager.get_memory(args[0])
            if value is None:
                return f"Memory key '{args[0]}' not found."
            return f"**{args[0]}:** {value}"

        memory = self._session_manager.get_all_memory()
        if not memory:
            return "Working Memory is empty."

        lines = ["🧠 **Working Memory**", ""]
        for key, value in memory.items():
            val_str = str(value)[:100]
            lines.append(f"  `{key}`: {val_str}")
        return "\n".join(lines)

    def _cmd_model(self, args: list[str]) -> str:
        """모델 정보/변경."""
        if not self._model_manager:
            return "Model manager not connected."

        if args:
            try:
                self._model_manager.set_model(args[0])
                return f"✅ 모델이 `{args[0]}`로 변경되었습니다."
            except Exception as e:
                logger.exception("Unhandled exception")
                return f"모델 변경 실패: {e}"

        try:
            info = self._model_manager.get_model_info()
            return f"🤖 **현재 모델:** {info}"
        except Exception:
            logger.exception("Unhandled exception")
            return "모델 정보를 가져올 수 없습니다."

    def _cmd_status(self, _args: list[str]) -> str:
        """전체 상태 요약."""
        lines = ["⚡ **Ssak-Ai 상태**", ""]

        if self._session_manager:
            info = self._session_manager.get_session_info()
            if info:
                lines.extend(
                    [
                        f"  **세션:** {info['id']}",
                        f"  **턴 수:** {info['turn_count']}",
                        f"  **메시지:** {info['message_count']}",
                        f"  **메모리 키:** {len(info['memory_keys'])}개",
                        "",
                    ]
                )

        if self._tool_registry:
            lines.append(f"  **도구:** {len(self._tool_registry)}개 등록됨")

        if self._context_shaper:
            stats = self._context_shaper.get_stats()
            lines.append(f"  **압축 횟수:** {stats.get('total_shaped', 0)}회")
            lines.append("")

        try:
            from antigravity_k.engine.tracing import AgentTracer

            readiness_fn = getattr(AgentTracer, "get_readiness_score", None)
            if callable(readiness_fn):
                readiness = readiness_fn()
                if isinstance(readiness, dict):
                    readiness_data = cast(dict[str, object], readiness)
                    status = str(readiness_data.get("status", "unknown"))
                    score = readiness_data.get("score", 0)
                    status_emoji = "🟢" if status == "ready" else "🟡" if status == "degraded" else "🔴"
                    lines.append(
                        f"  {status_emoji} **시스템 준비도(Readiness):** {score}/100 ({status})",
                    )
        except Exception:
            logger.exception("Unhandled exception")

        return "\n".join(lines)

    def _cmd_compact(self, _args: list[str]) -> str:
        """수동 컨텍스트 압축 — CTX-01 revision CAS when conversation binding is known."""
        # Prefer authoritative conversation store when project/conversation are bound.
        # F1/F3: CAS failures must NOT fall through to session_manager success path;
        # always CAS against client expected revision (ctx.conversation_revision).
        ctx = None
        try:
            from antigravity_k.api.contracts.errors import StaleConversationRevisionError
            from antigravity_k.api.project_binding import get_bound_request_execution_context
            from antigravity_k.engine.conversation_store import get_conversation_store

            ctx = get_bound_request_execution_context()
            if ctx is not None:
                store = get_conversation_store()
                before = store.get(project_id=ctx.project_id, conversation_id=ctx.conversation_id)
                tokens_before = before.estimate_tokens() if before else 0
                try:
                    snap = store.compact(
                        project_id=ctx.project_id,
                        conversation_id=ctx.conversation_id,
                        expected_revision=ctx.conversation_revision,
                        retain_tail=6,
                    )
                except StaleConversationRevisionError as exc:
                    current = exc.context.get("current_revision", "?")
                    return (
                        "❌ 압축 충돌 (stale_conversation_revision)\n"
                        f"  conversation: `{ctx.conversation_id}`\n"
                        f"  expected_revision: {ctx.conversation_revision}\n"
                        f"  current_revision: {current}\n"
                        "  다른 탭/요청에서 이미 변경됨 — refresh 후 재시도하세요."
                    )
                after = store.get(project_id=ctx.project_id, conversation_id=ctx.conversation_id)
                tokens_after = after.estimate_tokens() if after else 0
                retained = ", ".join(snap.retained_message_ids[:12]) or "(none)"
                summary_preview = (snap.summary or "")[:200]
                # One-way store → session projection only after successful CAS.
                if self._session_manager and after is not None:
                    current_session = cast(
                        dict[str, object], getattr(self._session_manager, "_current_session", {}) or {}
                    )
                    if current_session is not None:
                        current_session["messages"] = after.prompt_messages()
                        try:
                            self._session_manager.save()
                        except Exception:
                            logger.exception("session_manager.save after compact failed")
                return (
                    "✅ 컨텍스트 압축 완료! (authoritative store CAS)\n"
                    f"  conversation: `{snap.conversation_id}`\n"
                    f"  revision: {ctx.conversation_revision} → {snap.revision}\n"
                    f"  messages: {(len(before.messages) if before else 0)} → {snap.message_count}\n"
                    f"  tokens: {tokens_before} → {tokens_after} (−{max(0, tokens_before - tokens_after)})\n"
                    f"  retained IDs: {retained}\n"
                    f"  summary: {summary_preview}"
                )
        except Exception as exc:
            if ctx is not None:
                # Bound protocol path: never mutate session_manager as a success fallback.
                logger.exception("authoritative compact failed (no legacy fallback)")
                return f"❌ 압축 실패 (authoritative store): {exc}"
            logger.exception("authoritative compact unavailable; using session shaper")
            _ = exc

        if not self._context_shaper or not self._session_manager:
            return "Context shaper or session manager not connected."

        messages = self._session_manager.get_messages()
        original_count = len(messages)
        shaped = self._context_shaper.shape(messages)
        current_session = cast(dict[str, object], getattr(self._session_manager, "_current_session"))
        current_session["messages"] = shaped
        self._session_manager.save()

        estimate_tokens = cast(
            Callable[[list[dict[str, object]]], int], getattr(self._context_shaper, "_estimate_tokens")
        )

        return (
            f"✅ 컨텍스트 압축 완료!\n"
            f"  메시지: {original_count} → {len(shaped)}\n"
            f"  토큰: {estimate_tokens(messages)} → "
            f"{estimate_tokens(shaped)}"
        )

    def _cmd_session(self, args: list[str]) -> str:
        """세션 관리."""
        if not self._session_manager:
            return "Session manager not connected."
        if not args:
            return self._cmd_help(["session"])

        sub = args[0]
        if sub == "list":
            sessions = self._session_manager.list_sessions()
            if not sessions:
                return "저장된 세션이 없습니다."
            lines = ["📁 **세션 목록**", ""]
            for s in sessions:
                lines.append(f"  `{s['id']}` — 턴: {s['turn_count']}, 경로: {s['project_path']}")
            return "\n".join(lines)
        elif sub == "save":
            self._session_manager.save()
            return "✅ 세션이 저장되었습니다."
        elif sub == "load" and len(args) > 1:
            success = self._session_manager.load_session(args[1])
            if success:
                return f"✅ 세션 `{args[1]}`이 로드되었습니다."
            return f"세션 `{args[1]}`을 찾을 수 없습니다."
        elif sub == "info":
            info = self._session_manager.get_session_info()
            if not info:
                return "현재 활성 세션이 없습니다."
            lines = ["📋 **세션 정보**", ""]
            for k, v in info.items():
                lines.append(f"  {k}: {v}")
            return "\n".join(lines)
        return f"알 수 없는 세션 명령: {sub}"

    def _cmd_resume(self, args: list[str]) -> str:
        """Durable Checkpoint 기반 상태 복구 및 재개."""
        import json
        import sqlite3

        db_path = ".agk_context.db"
        trace_id = args[0] if args else None

        try:
            with sqlite3.connect(db_path) as conn:
                if trace_id:
                    cursor = conn.execute(
                        "SELECT * FROM checkpoints WHERE trace_id = ? ORDER BY timestamp DESC LIMIT 1",
                        (trace_id,),
                    )
                else:
                    cursor = conn.execute("SELECT * FROM checkpoints ORDER BY timestamp DESC LIMIT 1")
                row = cast(tuple[object, ...] | None, cursor.fetchone())

            if not row:
                return "❌ 복구할 수 있는 체크포인트를 찾지 못했습니다."

            recovered_trace_id = row[0]
            label = row[1]
            state = row[2]
            task_type = row[3]
            context_json = cast(dict[str, object], json.loads(str(row[5])))

            if self._session_manager and "messages" in context_json:
                current_session = cast(dict[str, object], getattr(self._session_manager, "_current_session"))
                current_session["messages"] = context_json["messages"]
                self._session_manager.save()

            recovered_messages = context_json.get("messages", [])
            message_count = len(cast(list[object], recovered_messages)) if isinstance(recovered_messages, list) else 0

            return (
                f"✅ **[Durable Recovery 성공]**\n\n"
                f"- **Trace ID**: `{recovered_trace_id}`\n"
                f"- **Checkpoint**: `{label}`\n"
                f"- **State**: `{state}`\n"
                f"- **Task Type**: `{task_type}`\n"
                f"- **Messages**: {message_count}개 복원됨\n\n"
                f"컨텍스트가 성공적으로 복원되었습니다. 작업을 이어서 진행할 수 있습니다."
            )
        except sqlite3.OperationalError:
            return "❌ 체크포인트 데이터베이스(`.agk_context.db`)가 아직 생성되지 않았거나 존재하지 않습니다."
        except Exception as e:
            logger.exception("Unhandled exception")
            return f"❌ 체크포인트 복구 중 오류 발생: {str(e)}"

    def _cmd_project(self, args: list[str]) -> str:
        """프로젝트 초기화 및 샌드박싱."""
        import os

        if not args:
            return "Usage: `/project <folder_path>`"

        folder_path = os.path.abspath(args[0])

        try:
            os.makedirs(folder_path, exist_ok=True)
        except Exception as e:
            logger.exception("Unhandled exception")
            return f"❌ 폴더 생성 실패: {e}"

        if self._tool_registry:
            self._tool_registry.set_project_root(folder_path)

        if self._session_manager:
            self._session_manager.start_session(project_path=folder_path, resume=False)

        conductor_dir = os.path.join(folder_path, "conductor")
        os.makedirs(conductor_dir, exist_ok=True)

        files_to_create = {
            "product.md": "# Product Definition\n\n프로젝트의 목표와 정의를 작성하세요.\n",
            "tech-stack.md": "# Tech Stack\n\n사용 기술 스택 정의.\n",
            "workflow.md": "# Workflow\n\n개발 및 검증 워크플로우 정의.\n",
            "tracks.md": "# Tracks Registry\n\n진행 중인 트랙 목록.\n",
        }

        for fname, content in files_to_create.items():
            fpath = os.path.join(conductor_dir, fname)
            if not os.path.exists(fpath):
                try:
                    with open(fpath, "w", encoding="utf-8") as f:
                        _ = f.write(content)
                except Exception:
                    logger.exception("Failed to create scaffolding file %s", fpath)

        return (
            f"✅ 프로젝트가 성공적으로 설정되었습니다!\n\n"
            f"**디렉토리:** `{folder_path}`\n"
            f"**샌드박스:** 활성화됨 (이 폴더 밖의 파일 수정은 엄격히 차단됩니다.)\n"
            f"**스캐폴딩:** `conductor/` 구조 생성 완료.\n\n"
            f"이제 이 폴더 내에서 안전하게 작업을 진행할 수 있습니다."
        )
