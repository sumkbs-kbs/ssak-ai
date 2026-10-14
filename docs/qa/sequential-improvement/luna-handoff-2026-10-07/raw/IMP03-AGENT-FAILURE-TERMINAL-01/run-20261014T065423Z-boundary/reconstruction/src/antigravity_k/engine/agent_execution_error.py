"""Public failure contract for a terminal agent execution."""


class AgentExecutionError(RuntimeError):
    def __str__(self) -> str:
        return "The agent execution failed. Please review the task before retrying."

    def detail(self) -> dict[str, str]:
        return {"type": "agent_execution_error", "code": "task_failed", "message": str(self)}
