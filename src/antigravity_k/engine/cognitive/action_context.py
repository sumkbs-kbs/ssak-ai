"""Structural context for action admission and lifecycle helpers."""

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Protocol

from antigravity_k.engine.cognitive.action_journal import ActionJournal
from antigravity_k.engine.cognitive.action_types import (
    ActionIntent,
    ActionReceipt,
    ActionRefusal,
    ActionRun,
    ToolDispatchPort,
)
from antigravity_k.engine.cognitive.authority import AuthorityDecision
from antigravity_k.engine.cognitive.models import Record


class ActionContext(Protocol):
    @property
    def port(self) -> ToolDispatchPort | None: ...

    @property
    def authority_resolver(self) -> Callable[[ActionIntent, datetime], AuthorityDecision] | None: ...

    @property
    def journal(self) -> ActionJournal | None: ...

    @property
    def _receipts(self) -> dict[str, ActionReceipt]: ...

    @property
    def _attempts(self) -> dict[str, int]: ...

    def _now(self) -> datetime: ...

    def _persist(self, records: Sequence[Record]) -> None: ...

    def _refuse(
        self, intent: ActionIntent, refusal: ActionRefusal, reason: str, *, receipt: ActionReceipt | None = None
    ) -> ActionRun: ...
