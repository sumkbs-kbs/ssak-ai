"""Declarative agent capabilities and spawn contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Final, cast, final, override

from pydantic import BaseModel, ConfigDict, Field, model_validator

from antigravity_k.engine.capability_policy import CapabilityDecision
from antigravity_k.tools.base_tool import BaseTool
from antigravity_k.tools.permission_gate import PermissionGate
from antigravity_k.tools.tool_contracts import Permission
from antigravity_k.tools.tool_registry import ToolRegistry

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]

DEFAULT_WORKER_TOOLS: Final[frozenset[str]] = frozenset(
    {
        "apply_patch",
        "auto_lint",
        "edit_file",
        "git_diff",
        "git_log",
        "git_status",
        "glob_search",
        "grep_search",
        "hashline_edit",
        "impact_analyzer",
        "interactive_pty",
        "list_directory",
        "multi_replace_file_content",
        "read_file",
        "read_hash_file",
        "replace_file_content",
        "run_bash_command",
        "test_runner",
        "write_artifact",
        "write_file",
    },
)


class AgentDefinition(BaseModel):
    """Validated capabilities for one runtime agent."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    role: str = Field(min_length=1, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    system_prompt: str = Field(min_length=1)
    allowed_tools: frozenset[str]
    spawnable_agents: frozenset[str] = frozenset()

    def allows_tool(self, tool_name: str) -> bool:
        return tool_name in self.allowed_tools

    def allows_spawn(self, agent_name: str) -> bool:
        return agent_name in self.spawnable_agents


@dataclass(frozen=True, slots=True)
@final
class AgentContractViolation(Exception):
    """Structured denial raised before an agent action is dispatched."""

    agent_name: str
    action: str
    target: str

    @override
    def __str__(self) -> str:
        return f"Agent '{self.agent_name}' cannot {self.action} '{self.target}'."


@dataclass(frozen=True, slots=True)
@final
class ResolvedAgentSpawn:
    """Child definition and the exact tools exposed to its runtime."""

    definition: AgentDefinition
    allowed_tools: tuple[str, ...]


class AgentSpawnContract(BaseModel):
    """Validated parent-to-child delegation contract."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    parent: AgentDefinition
    definitions: tuple[AgentDefinition, ...]

    @model_validator(mode="after")
    def definitions_have_unique_names(self) -> AgentSpawnContract:
        names = tuple(definition.name for definition in self.definitions)
        if len(names) != len(set(names)):
            duplicate = next(name for name in names if names.count(name) > 1)
            raise AgentContractViolation(
                agent_name=self.parent.name,
                action="register duplicate agent",
                target=duplicate,
            )
        return self

    def resolve(self, agent_name: str, requested_tools: tuple[str, ...]) -> ResolvedAgentSpawn:
        if not self.parent.allows_spawn(agent_name):
            raise AgentContractViolation(
                agent_name=self.parent.name,
                action="spawn",
                target=agent_name,
            )

        definition = next(
            (candidate for candidate in self.definitions if candidate.name == agent_name),
            None,
        )
        if definition is None:
            raise AgentContractViolation(
                agent_name=self.parent.name,
                action="spawn undeclared agent",
                target=agent_name,
            )

        denied_tool = next(
            (tool_name for tool_name in requested_tools if not definition.allows_tool(tool_name)),
            None,
        )
        if denied_tool is not None:
            raise AgentContractViolation(
                agent_name=definition.name,
                action="use tool",
                target=denied_tool,
            )
        return ResolvedAgentSpawn(definition=definition, allowed_tools=requested_tools)


class AgentSpawnRequest(BaseModel):
    """Parsed LLM tool-call payload for spawning a child agent."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    task: str = Field(min_length=1)
    agent: str = Field(default="WORKER", min_length=1)
    tools: tuple[str, ...] = ("read_file", "glob_search", "grep_search")
    max_tokens: int = Field(default=4096, ge=1, le=131_072)


@final
class AgentToolRegistry:
    """Non-owning ToolRegistry view restricted to one child execution."""

    def __init__(
        self,
        source: ToolRegistry,
        definition: AgentDefinition,
        requested_tools: tuple[str, ...],
    ) -> None:
        self._source = source
        self._definition = definition
        self._allowed_tools = frozenset(requested_tools)

    def _allows(self, tool_name: str) -> bool:
        return tool_name in self._allowed_tools and self._definition.allows_tool(tool_name)

    @property
    def permission_gate(self) -> PermissionGate:
        return self._source.permission_gate

    def get(self, name: str) -> BaseTool | None:
        return self._source.get(name) if self._allows(name) else None

    def get_all(self) -> list[BaseTool]:
        return self._source.get_by_names(
            [name for name in sorted(self._allowed_tools) if self._allows(name)],
        )

    def get_names(self) -> list[str]:
        return [tool.name for tool in self.get_all()]

    def get_by_names(self, names: list[str]) -> list[BaseTool]:
        return self._source.get_by_names([name for name in names if self._allows(name)])

    def execute_with_permission(
        self,
        tool_name: str,
        args: dict[str, JsonValue],
        objective: str = "",
    ) -> tuple[Permission, str]:
        if not self._allows(tool_name):
            violation = AgentContractViolation(
                agent_name=self._definition.name,
                action="use tool",
                target=tool_name,
            )
            return Permission.DENY, f"[DENIED] {violation}"
        return self._source.execute_with_permission(tool_name, args, objective=objective)

    def execute_approved(self, tool_name: str, args: dict[str, JsonValue]) -> str:
        if not self._allows(tool_name):
            violation = AgentContractViolation(
                agent_name=self._definition.name,
                action="use tool",
                target=tool_name,
            )
            return f"[DENIED] {violation}"
        return self._source.execute_approved(tool_name, args)

    def decide_tool_use(
        self,
        tool_name: str,
        args: dict[str, JsonValue] | None = None,
        objective: str = "",
    ) -> CapabilityDecision | None:
        if not self._allows(tool_name):
            return None
        return self._source.decide_tool_use(tool_name, args=args, objective=objective)

    def render_autonomous_policy(self) -> str:
        return self._source.render_autonomous_policy()

    def to_llm_schemas(self, names: list[str] | None = None) -> list[dict[str, JsonValue]]:
        selected = self._allowed_names(names)
        return self._source.to_llm_schemas(selected)

    def to_openai_schemas(self, names: list[str] | None = None) -> list[dict[str, JsonValue]]:
        selected = self._allowed_names(names)
        return self._source.to_openai_schemas(selected)

    def to_metadata_list(self) -> list[dict[str, JsonValue]]:
        return [cast(dict[str, JsonValue], tool.to_metadata()) for tool in self.get_all()]

    def _allowed_names(self, names: list[str] | None) -> list[str]:
        candidates = names if names is not None else sorted(self._allowed_tools)
        return [name for name in candidates if self._allows(name)]

    def __len__(self) -> int:
        return len(self.get_all())

    def __contains__(self, name: str) -> bool:
        return self._allows(name) and name in self._source


def default_agent_spawn_contract() -> AgentSpawnContract:
    return AgentSpawnContract(
        parent=AgentDefinition(
            name="ORCHESTRATOR",
            role="ORCHESTRATOR",
            system_prompt="Coordinate work and delegate bounded tasks.",
            allowed_tools=frozenset({"agent_spawn"}),
            spawnable_agents=frozenset({"WORKER"}),
        ),
        definitions=(
            AgentDefinition(
                name="WORKER",
                role="WORKER",
                system_prompt=(
                    "You are a focused sub-agent. Complete the task efficiently and return only the essential result."
                ),
                allowed_tools=DEFAULT_WORKER_TOOLS,
            ),
        ),
    )
