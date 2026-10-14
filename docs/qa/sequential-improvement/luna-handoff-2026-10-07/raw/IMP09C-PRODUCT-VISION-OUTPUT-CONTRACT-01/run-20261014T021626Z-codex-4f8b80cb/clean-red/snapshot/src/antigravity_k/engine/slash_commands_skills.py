"""Skills/capabilities/agent slash command handlers (mixin).

Provides: /self, /agentic, /mcp, /market, /capabilities, /codex, /evolve,
/approve, /browse, /skill.

These handlers access ``self._tool_registry``, ``self._skill_loader``, and
``self._model_manager``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import ClassVar, Protocol, cast

from antigravity_k.engine.slash_commands_base import SlashCommand
from antigravity_k.engine.slash_commands_session import ModelManagerProtocol, ToolRegistryProtocol

logger = logging.getLogger(__name__)


class CapabilityDecisionLike(Protocol):
    capability_id: str
    capability_type: str
    decision: str
    risk_level: str
    trust_level: str
    reason: str
    score: float


class ToolRegistryLike(Protocol):
    def __len__(self) -> int: ...
    def render_autonomous_policy(self) -> str: ...
    def get_autonomous_manifest(self, objective: str) -> list[CapabilityDecisionLike]: ...


class SkillLoaderLike(Protocol):
    def get_autonomous_manifest(self, objective: str) -> list[CapabilityDecisionLike]: ...


class SlashCommandSkillsMixin:
    """Skills, capabilities, and agent-related command handlers.

    Note: The following attributes are provided by ``SlashCommandRegistryBase``
    via cooperative multiple inheritance (MRO).
    """

    # Mixin-required attributes (resolved via MRO at runtime)
    _tool_registry: ClassVar[ToolRegistryProtocol | None]
    _skill_loader: ClassVar[SkillLoaderLike | None]
    _model_manager: ClassVar[ModelManagerProtocol | None]
    _commands: ClassVar[dict[str, SlashCommand]]

    def _cmd_self(self, args: list[str]) -> str:
        """런타임 기반 자기 능력 보고서."""
        _ = args
        from antigravity_k.engine.self_capability import SelfCapabilityEngine

        engine = SelfCapabilityEngine()
        snapshot = engine.build(
            tool_registry=cast(ToolRegistryLike | None, self._tool_registry),
            skill_loader=self._skill_loader,
            model_manager=self._model_manager,
            slash_commands=self._commands,
        )
        return engine.render_markdown(snapshot)

    def _cmd_agentic(self, args: list[str]) -> str:
        """최신 에이전틱 기술 레이더."""
        objective = " ".join(args).strip()
        from antigravity_k.engine.agentic_tech_radar import AgenticTechRadar

        radar = AgenticTechRadar()
        report = radar.evaluate(objective)
        return radar.render_markdown(report)

    def _cmd_mcp(self, args: list[str]) -> str:
        """MCP 최신 기능 레이더 및 설정 감사."""
        from antigravity_k.engine.mcp_capability import MCPCapabilityAdvisor

        advisor = MCPCapabilityAdvisor()
        subcommand = args[0].lower() if args else "radar"

        if subcommand == "template":
            return "```json\n" + advisor.render_template() + "\n```"

        if subcommand == "audit" or subcommand.endswith(".json"):
            path = args[1] if subcommand == "audit" and len(args) > 1 else subcommand
            if subcommand == "audit" and len(args) <= 1:
                path = ".mcp.json"
            config = advisor.load_config(path)
            report = advisor.audit_config(config, source=path)
            return advisor.render_markdown(report)

        if subcommand in {"radar", "capabilities", "latest"}:
            report = advisor.audit_config({}, source="latest-capability-radar")
            return advisor.render_markdown(report)

        return "Usage: `/mcp [radar|audit <path>|template]`"

    def _cmd_market(self, args: list[str]) -> str:
        """Skill Marketplace 명령어."""
        try:
            from antigravity_k.engine.skill_market_client import SkillMarketClient
            from antigravity_k.engine.skill_market_registry import LoaderProtocol, SkillMarketRegistry
        except ImportError as e:
            return f"❌ Market dependencies not available: {e}"

        market_client = SkillMarketClient()
        registry = SkillMarketRegistry(
            project_root=".",
            market_client=market_client,
            skill_loader=cast(LoaderProtocol | None, self._skill_loader),
        )

        if not args:
            return (
                "📦 **Skill Marketplace**\n\n"
                "Usage: `/market <subcommand>`\n\n"
                "`/market search <query>` — Search for skills\n"
                "`/market install <package>` — Install a skill\n"
                "`/market remove <name>` — Remove an installed skill\n"
                "`/market list` — List installed skills\n"
                "`/market info <name>` — Show skill details\n"
                "`/market update [name]` — Update a skill (or all if name omitted)"
            )

        sub = args[0].lower()
        rest = args[1:]

        if sub == "search":
            query = " ".join(rest).strip()
            if not query:
                return "Usage: `/market search <query>`"
            search_results = registry.search(query)
            if search_results and "error" not in search_results[0]:
                lines = ["🔍 **Skill Marketplace 검색 결과**", ""]
                for result in search_results[:15]:
                    name = str(result.get("name", "unknown"))
                    version = str(result.get("version", "0.0.0"))
                    description = str(result.get("description", ""))
                    installed_mark = "✅" if result.get("is_installed") else "📦"
                    if len(description) > 80:
                        description = description[:80] + "..."
                    lines.extend([f"  {installed_mark} `{name}@{version}`", f"     {description}", ""])
                if len(search_results) > 15:
                    lines.append(f"  ... 외 {len(search_results) - 15}개 결과")
                return "\n".join(lines)
            return "🔍 검색 결과가 없습니다."

        elif sub == "install":
            if not rest:
                return "Usage: `/market install <package>`"
            package = rest[0]
            install_result = registry.install(package)
            if install_result.get("success"):
                return f"✅ **Install complete**\n\n{install_result.get('summary', '')}"
            error = install_result.get("error", "Unknown error")
            warnings = install_result.get("warnings", [])
            msg = f"❌ Install failed: {error}"
            if warnings:
                msg += "\n\n**Warnings:**\n" + "\n".join(f"- {w}" for w in warnings)
            return msg

        elif sub == "remove":
            if not rest:
                return "Usage: `/market remove <name>`"
            name = rest[0]
            remove_result = registry.remove(name)
            if remove_result.get("success"):
                return f"✅ **Removed**\n\n{remove_result.get('summary', '')}"
            return f"❌ Remove failed: {remove_result.get('error', 'Unknown error')}"

        elif sub in ("list", "ls"):
            installed = registry.list_installed()
            return registry.format_list(installed)

        elif sub == "info":
            if not rest:
                return "Usage: `/market info <name>`"
            name = rest[0]
            skill_info = registry.get_info(name)
            if skill_info:
                return registry.format_info(skill_info)
            if name.startswith("@antigravity-k/skill-"):
                detail = market_client.get_detail(name)
                if detail:
                    lines = [
                        f"📦 **{detail.name}** `v{detail.version}`",
                        "",
                        f"설명: {detail.description}",
                        f"키워드: {', '.join(detail.keywords)}" if detail.keywords else "",
                        f"라이선스: {detail.license}" if detail.license else "",
                        f"npm: {detail.npm_url}" if detail.npm_url else "",
                    ]
                    if detail.is_agk_skill:
                        lines.extend(
                            [
                                "",
                                "**AGK 메타데이터:**",
                                f"  - 위험도: `{detail.agk_risk_level}`",
                                f"  - 신뢰수준: `{detail.agk_trust_level}`",
                                f"  - 승인필요: {'✅' if detail.agk_requires_approval else '❌'}",
                            ]
                        )
                        if detail.agk_mcp_server_id:
                            lines.append(f"  - MCP 서버: `{detail.agk_mcp_server_id}`")
                    return "\n".join(line for line in lines if line)
                return f"📦 `{name}`을(를) 찾을 수 없습니다."
            return f"❌ Skill `{name}`이(가) 설치되지 않았습니다."

        elif sub == "update":
            if rest:
                name = rest[0]
                update_result = registry.update(name)
                if update_result.get("success"):
                    return f"✅ **Updated**\n\n{update_result.get('summary', '')}"
                return f"❌ Update failed: {update_result.get('error', 'Unknown error')}"
            update_results = registry.update_all()
            updated = [r for r in update_results if r.get("success")]
            if updated:
                lines = ["✅ **업데이트 완료**", ""]
                for r in updated:
                    lines.append(f"  - `{r.get('skill_name', '?')}` → `{r.get('version', '?')}`")
                return "\n".join(lines)
            return "✅ 모든 스킬이 최신 상태입니다."

        return f"❓ 알 수 없는 하위 명령: `{sub}`.\n사용 가능: search, install, remove, list, info, update"

    def _cmd_capabilities(self, args: list[str]) -> str:
        """현재 등록된 capabilities의 자율 사용 가능성 표시."""
        objective = " ".join(args).strip()
        lines = [
            "# Autonomous Capability Manifest",
            "",
            f"**Objective:** `{objective or 'general'}`",
            "",
        ]

        tool_registry = cast(ToolRegistryLike | None, self._tool_registry)
        if tool_registry is not None:
            lines.append(tool_registry.render_autonomous_policy().strip())
            lines.append("")
            decisions = tool_registry.get_autonomous_manifest(objective)
            counts = {
                "allow": sum(1 for item in decisions if item.decision == "allow"),
                "prompt": sum(1 for item in decisions if item.decision == "prompt"),
                "deny": sum(1 for item in decisions if item.decision == "deny"),
            }
            lines.append(
                f"**Tools/MCP:** allow={counts['allow']}, prompt={counts['prompt']}, deny={counts['deny']}",
            )
            lines.append("")
            if not decisions:
                lines.append("- Tool registry is connected, but no executable tools are registered yet.")
            else:
                for decision in decisions[:30]:
                    lines.append(
                        f"- `{decision.capability_id}` [{decision.capability_type}] "
                        + f"→ **{decision.decision}** "
                        + f"(risk={decision.risk_level}, trust={decision.trust_level}) — {decision.reason}",
                    )
                if len(decisions) > 30:
                    lines.append(f"- ... {len(decisions) - 30} more capabilities")
        else:
            lines.append("**Tools/MCP:** Tool registry not connected.")

        if self._skill_loader is not None:
            skill_decisions = [
                decision for decision in self._skill_loader.get_autonomous_manifest(objective) if decision.score > 0
            ]
            lines.extend(["", "## Skills", ""])
            if not skill_decisions:
                lines.append("- No relevant skill candidates for this objective.")
            else:
                for decision in skill_decisions[:10]:
                    lines.append(
                        f"- `{decision.capability_id}` → **{decision.decision}** "
                        + f"(score={decision.score}, risk={decision.risk_level}) — {decision.reason}",
                    )
        else:
            lines.extend(["", "**Skills:** Skill loader not connected."])

        return "\n".join(lines)

    def _cmd_codex(self, args: list[str]) -> str:
        """Codex식 강점을 Ssak-Ai 실행 계약으로 표시합니다."""
        objective = " ".join(args).strip()
        connected_tools = len(self._tool_registry) if self._tool_registry else 0
        known_skills = 0
        if self._skill_loader is not None:
            known_skills = len(self._skill_loader.get_autonomous_manifest(objective))

        from antigravity_k.engine.codex_transfer import CodexTransferEngine

        engine = CodexTransferEngine()
        report = engine.build(
            objective=objective,
            connected_tools=connected_tools,
            known_skills=known_skills,
        )
        return engine.render_markdown(report)

    def _cmd_evolve(self, args: list[str]) -> str | Iterator[str]:
        if not self._model_manager:
            return "Error: Model manager is not connected."

        requirement = " ".join(args).strip()
        if not requirement:
            return "Usage: `/evolve <기능 고도화 요구사항>`"

        from antigravity_k.agents.meta_evolution_agent import MetaEvolutionAgent
        from antigravity_k.engine.orchestrator import OrchestratorAgent
        from antigravity_k.tools.tool_registry import ToolRegistry

        orch = OrchestratorAgent(
            model_manager=self._model_manager,
            tool_registry=cast(ToolRegistry | None, self._tool_registry),
        )
        agent = MetaEvolutionAgent(
            model_manager=self._model_manager,
            tool_executor=orch.ctx.tool_executor,
        )
        return agent.evolve(requirement)

    def _cmd_approve(self, args: list[str]) -> str:
        _ = args
        return "System command: /approve is managed by the orchestrator."

    def _cmd_browse(self, args: list[str]) -> str:
        _ = args
        return "System command: /browse is managed by the orchestrator."

    def _cmd_skill(self, args: list[str]) -> str:
        _ = args
        return "System command: /skill is managed by the orchestrator."
