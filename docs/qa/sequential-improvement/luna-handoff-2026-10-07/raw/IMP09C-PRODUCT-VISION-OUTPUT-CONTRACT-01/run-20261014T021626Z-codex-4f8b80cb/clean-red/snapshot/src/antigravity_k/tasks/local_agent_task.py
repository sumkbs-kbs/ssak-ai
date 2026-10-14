"""Local Agent Task module."""

import logging
import threading
import traceback
from collections.abc import Callable
from typing import override

logger = logging.getLogger(__name__)


class LocalAgentTask(threading.Thread):
    """A wrapper around threading.Thread for executing agent tasks in parallel.

    Captures the return value and any exceptions raised during execution.
    """

    def __init__(
        self,
        name: str,
        target: Callable[..., object],
        args: tuple[object, ...] = (),
        kwargs: dict[str, object] | None = None,
    ) -> None:
        """Initialize the LocalAgentTask.

        Args:
            name (str): str name.
            target (Callable): Callable target.
            args (tuple): tuple args.
            kwargs (dict | None): dict | None kwargs.

        """
        super().__init__(name=name)
        self.target: Callable[..., object] = target
        self.args: tuple[object, ...] = args
        self.kwargs: dict[str, object] = kwargs or {}
        self.result: object = None
        self.error: str | None = None
        self.status: str = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED

    @override
    def run(self) -> None:
        """Execute the local agent task and return the result."""
        self.status = "RUNNING"
        try:
            self.result = self.target(*self.args, **self.kwargs)
            self.status = "COMPLETED"
        except Exception as e:
            self.error = f"{type(e).__name__}: {e!s}\n{traceback.format_exc()}"
            self.status = "FAILED"
            logger.exception("Task '%s' failed: %s", self.name, self.error)
