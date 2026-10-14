"""A single corrective generation for a model that omitted required tools."""


class RequiredToolRecovery:
    """Mutable turn-local budget; recovery never manufactures or executes a call."""

    __slots__ = ("_requested",)

    def __init__(self) -> None:
        self._requested = False

    def take_instruction(self, missing_tools: tuple[str, ...], user_task: str) -> str | None:
        """Give the model one chance to emit permitted calls with real arguments."""
        if not missing_tools or self._requested:
            return None
        self._requested = True
        names = ", ".join(missing_tools)
        return (
            "[REQUIRED TOOL RECOVERY]\n"
            f"Your previous response did not execute these required tools: {names}.\n"
            "Before answering, emit the missing tool calls using the exact files and arguments "
            "requested by the user. Respect the original scope and all permission rules. "
            "Do not invent tool results, substitute another tool, or claim an action succeeded. "
            "Use native tool calls when available, or valid JSON in this format:\n"
            '<tool_call>{"name":"tool_name","arguments":{"key":"value"}}</tool_call>\n'
            "When a tool returns an error, report that failure from its result. "
            "If no valid permitted call can be made, explain the limitation.\n"
            f"Original user request:\n{user_task}\n"
        )
