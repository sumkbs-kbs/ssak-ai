"""SlashCommands — 슬래시 커맨드 레지스트리.

==========================================
Claw Code의 CommandRegistry 아키텍처 이식.

에이전트 세션을 제어하는 `/` 접두사 명령어 시스템.
채팅 입력에서 `/`로 시작하는 명령을 감지하여 처리합니다.

사용 예:
    registry = SlashCommandRegistry(...)
    if registry.is_command("/tools"):
        result = registry.execute("/tools")

아키텍처 (믹스인 기반 분할):
- ``slash_commands_base`` — SlashCommand DTO + registry mechanics + _register_defaults
- ``slash_commands_session`` — /help /tools /context /memory /model /status /compact /session /resume /project
- ``slash_commands_skills`` — /self /agentic /mcp /market /capabilities /codex /evolve /approve /browse /skill
- ``slash_commands_workflow`` — /qa /goal /mode /plan /build /aishell /benchmark /dialectic /finance /lifecycle

이 파일은 하위 호환을 위해 ``SlashCommand``와 ``SlashCommandRegistry``를 재수출한다.
"""

from __future__ import annotations

from antigravity_k.engine.slash_commands_base import SlashCommand, SlashCommandRegistryBase
from antigravity_k.engine.slash_commands_session import SlashCommandSessionMixin
from antigravity_k.engine.slash_commands_skills import SlashCommandSkillsMixin
from antigravity_k.engine.slash_commands_workflow import SlashCommandWorkflowMixin

__all__ = ["SlashCommand", "SlashCommandRegistry"]


class SlashCommandRegistry(
    SlashCommandRegistryBase,
    SlashCommandSessionMixin,
    SlashCommandSkillsMixin,
    SlashCommandWorkflowMixin,
):
    """슬래시 커맨드 중앙 레지스트리.

    모든 명령 핸들러는 세 개의 믹스인에 분산되어 있으며, 다중 상속을 통해
    단일 클래스로 조합된다. ``_register_defaults`` (베이스에 있음)는
    ``getattr(self, "_cmd_*")`` 로 바운드 메서드를 해결하므로 믹스인의
    메서드가 자동으로 등록된다.
    """
