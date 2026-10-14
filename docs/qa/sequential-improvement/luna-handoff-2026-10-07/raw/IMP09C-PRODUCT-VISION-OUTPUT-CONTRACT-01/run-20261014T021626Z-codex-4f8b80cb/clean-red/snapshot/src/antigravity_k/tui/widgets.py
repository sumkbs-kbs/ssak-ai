"""Ssak-Ai TUI — Custom Widgets.

MessageBubble:        Renders a chat message bubble (user/assistant/system).
SlashInput:           Input widget with /slash command auto-completion.
SuggestionBar:        Horizontal bar of clickable follow-up suggestion buttons.
StatusFooter:         Bottom status bar showing system state.
ProgressScreen:       Modal overlay with progress bar.
"""

from __future__ import annotations

from typing import final, override

from textual import events
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.message import Message
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, ProgressBar, Static

# ─── Colors ────────────────────────────────────────────────────────────────────
USER_COLOR = "#2d7ff9"
ASSISTANT_COLOR = "#1a1a2e"
SYSTEM_COLOR = "#6c757d"
FOLLOWUP_BG = "#2a2a3e"
STATUS_BG = "#0d1117"

# ─── Messages ──────────────────────────────────────────────────────────────────


@final
class SuggestionClicked(Message):
    """Emitted when a follow-up suggestion is clicked."""

    def __init__(self, text: str) -> None:
        self.text = text
        super().__init__()


@final
class UserMessage(Message):
    """Text submitted by the user."""

    def __init__(self, text: str) -> None:
        self.text = text
        super().__init__()


# ─── Message Bubble ────────────────────────────────────────────────────────────


def make_message_bubble(content: str, sender: str, timestamp: str = "") -> str:
    """Create a Rich-markup formatted message string for the chat log.

    Args:
        content: Message text content.
        sender: One of 'user', 'assistant', 'system'.
        timestamp: Optional HH:MM:SS timestamp string.

    Returns:
        A string with Rich markup for the chat log.
    """
    role_label = {"user": "You", "assistant": "AGK", "system": "System"}.get(sender, "Agent")
    ts = f" [{timestamp}]" if timestamp else ""

    if sender == "user":
        label = f"[bold]{role_label}[/bold]{ts}"
        prefix = "[#2d7ff9]┃[/#2d7ff9] "
    elif sender == "assistant":
        label = f"[bold #00ff87]{role_label}[/]{ts}"
        prefix = "[#00ff87]┃[/#00ff87] "
    else:
        label = f"[italic]{role_label}[/italic]{ts}"
        prefix = "  "

    return f"{label}\n{prefix}{content}\n"


# ─── Slash Input ──────────────────────────────────────────────────────────────

COMPLETION_COMMANDS = [
    "/help",
    "/tools",
    "/context",
    "/memory",
    "/model",
    "/status",
    "/self",
    "/compact",
    "/session",
    "/project",
    "/resume",
    "/approve",
    "/browse",
    "/skill",
    "/qa",
    "/evolve",
    "/goal",
    "/agentic",
    "/mcp",
    "/capabilities",
    "/codex",
    "/dialectic",
    "/finance",
    "/comps",
    "/dcf",
    "/aishell",
    "/benchmark",
    "/spec",
    "/plan",
    "/build",
    "/test",
    "/review",
    "/code-simplify",
    "/ship",
    "/clear",
    "/exit",
]


@final
class SlashInput(Input):
    """Input widget with /slash command auto-completion."""

    def __init__(self) -> None:
        super().__init__(placeholder="Type a message or /command...  (Ctrl+Space)")
        self._completion_index = -1
        self._completion_matches: list[str] = []

    def action_show_completions(self) -> None:
        """Show command completions for current input."""
        text = self.value.strip()
        if text.startswith("/"):
            prefix = text.lower()
            self._completion_matches = [cmd for cmd in COMPLETION_COMMANDS if cmd.startswith(prefix)]
        else:
            self._completion_matches = []

        if self._completion_matches:
            self._completion_index = 0
            self._show_completion()
        else:
            self._completion_index = -1

    def action_next_completion(self) -> None:
        """Cycle to next completion."""
        if not self._completion_matches:
            self.action_show_completions()
            return
        self._completion_index = (self._completion_index + 1) % len(self._completion_matches)
        self._show_completion()

    def _show_completion(self) -> None:
        if 0 <= self._completion_index < len(self._completion_matches):
            self.value = self._completion_matches[self._completion_index] + " "
            self.cursor_position = len(self.value)

    def on_key(self, event: events.Key) -> None:
        """Handle key events: Ctrl+Space for completions, Tab to cycle, Enter to submit."""
        if event.key == "ctrl+space":
            self.action_show_completions()
            _ = event.stop()
            return
        if event.key == "tab":
            self.action_next_completion()
            _ = event.stop()
            return
        if event.key == "enter":
            text = self.value.strip()
            if text:
                _ = self.post_message(UserMessage(text))
                self.value = ""
            _ = event.stop()


# ─── Suggestion Bar ───────────────────────────────────────────────────────────


@final
class SuggestionBar(Container):
    """Horizontal bar of clickable follow-up suggestion buttons."""

    def __init__(self) -> None:
        super().__init__()
        self.styles.overflow_x = "auto"
        self.styles.overflow_y = "hidden"
        self.styles.max_height = 3

    def set_suggestions(self, suggestions: list[str]) -> None:
        """Replace all buttons with new suggestions."""
        # Remove existing children
        for child in list(self.children):
            _ = child.remove()
        # Add new buttons
        for text in suggestions:
            display = text[:50] + "..." if len(text) > 50 else text
            btn = Button(display, variant="default", classes="suggestion-btn")
            btn.styles.max_width = 40
            btn.styles.margin = (0, 1, 0, 0)
            btn.styles.background = FOLLOWUP_BG
            btn.styles.border = ("solid", "#3a3a5e")
            _ = self.mount(btn)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle suggestion button click."""
        _ = self.post_message(SuggestionClicked(str(event.button.label)))


# ─── Status Footer ────────────────────────────────────────────────────────────


@final
class StatusFooter(Container):
    """Bottom status bar showing system state."""

    status_text = reactive("Initializing...")
    model_name = reactive("—")
    tools_count = reactive(0)
    server_status = reactive("offline")
    mode_name = reactive("interactive")  # Phase 1 D6: Plan/Build/Interactive

    _status_label: Static
    _mode_label: Static
    _model_label: Static
    _tools_label: Static
    _server_label: Static

    def __init__(self) -> None:
        super().__init__()
        self._status_label = Static("", id="status-label")
        self._mode_label = Static("", id="mode-label")
        self._model_label = Static("", id="model-label")
        self._tools_label = Static("", id="tools-label")
        self._server_label = Static("", id="server-label")

    @override
    def compose(self) -> ComposeResult:
        self.styles.background = STATUS_BG
        self.styles.height = 1
        self.styles.padding = (0, 1)

        with Horizontal():
            yield self._status_label
            yield self._mode_label
            yield self._model_label
            yield self._tools_label
            yield self._server_label

    def watch_status_text(self, value: str) -> None:
        if hasattr(self, "_status_label"):
            self._status_label.update(f"⚡ {value}")

    def watch_mode_name(self, value: str) -> None:
        if hasattr(self, "_mode_label"):
            mode_icon = {"plan": "📋", "build": "🔨", "interactive": "💬"}.get(value, "❓")
            color = {"plan": "yellow", "build": "green", "interactive": "cyan"}.get(value, "white")
            self._mode_label.update(f"[{color}]{mode_icon} {value.upper()}[/{color}]")

    def watch_model_name(self, value: str) -> None:
        if hasattr(self, "_model_label"):
            self._model_label.update(f"🤖 {value}")

    def watch_tools_count(self, value: int) -> None:
        if hasattr(self, "_tools_label"):
            self._tools_label.update(f"🔧 {value} tools")

    def watch_server_status(self, value: str) -> None:
        if hasattr(self, "_server_label"):
            icon = {"online": "🟢", "offline": "🔴", "busy": "🟡"}.get(value, "⚪")
            self._server_label.update(f"Server: {icon}")


# ─── Progress Overlay ─────────────────────────────────────────────────────────


@final
class ProgressScreen(ModalScreen[None]):
    """Modal overlay showing a progress bar."""

    def __init__(self, message: str = "Processing...") -> None:
        self.task_message = message
        super().__init__()

    @override
    def compose(self) -> ComposeResult:
        yield Container(
            Label(f"[bold]{self.task_message}[/bold]", id="progress-label"),
            ProgressBar(),
            id="progress-container",
        )

    def on_mount(self) -> None:
        container = self.query_one("#progress-container")
        container.styles.background = "#1a1a2e"
        container.styles.border = ("solid", "#00ff87")
        container.styles.padding = (2, 4)
        container.styles.align_vertical = "middle"
        container.styles.margin = (10, 10)
