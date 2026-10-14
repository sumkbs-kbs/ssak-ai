"""Ssak-Ai Textual TUI — Main Application.

Terminal User Interface for local engineering agent with:
- Dual-channel chat log (left) + tool inspector (right)
- Slash command auto-completion popup
- Model status widget
- Hotkey help modal
"""

from __future__ import annotations

import logging
import time
from typing import Callable, ClassVar, Protocol, cast, final, override

import textual.worker as textual_worker
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import (
    Button,
    Header,
    Label,
    RichLog,
    Static,
)
from textual.worker import Worker

from antigravity_k import __version__
from antigravity_k.engine.mode_manager import ModeManager
from antigravity_k.engine.slash_commands import SlashCommandRegistry

from .widgets import (
    SlashInput,
    StatusFooter,
    SuggestionBar,
    SuggestionClicked,
    UserMessage,
    make_message_bubble,
)

logger = logging.getLogger("antigravity_k.tui")


class _WorkerController(Protocol):
    def cancel_group(self, node: object, group: str) -> object: ...


class HelpScreen(Screen[None]):
    """Modal screen showing available slash commands and keyboard shortcuts."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "dismiss", "Close"),
        Binding("q", "dismiss", "Quit"),
    ]

    @override
    def compose(self) -> ComposeResult:
        yield Container(
            Label("[bold]Ssak-Ai TUI Help[/bold]", id="help-title"),
            Static(
                "\n".join(
                    line
                    for line in (
                        "[bold]Keyboard Shortcuts[/bold]",
                        "  [dim]Ctrl+Space[/dim]    Show slash command completions",
                        "  [dim]Tab[/dim]            Cycle through completions",
                        "  [dim]Ctrl+C[/dim]         Clear input / Cancel task / Exit when idle",
                        "  [dim]Ctrl+L[/dim]         Clear chat",
                        "  [dim]Ctrl+P[/dim]         Open command palette",
                        "  [dim]Ctrl+Q[/dim] / [dim]Esc[/dim]   Close help / Quit",
                        "",
                        "[bold]Slash Commands[/bold]",
                        "  [dim]/help[/dim]           Show this help",
                        "  [dim]/tools[/dim]          List available tools",
                        "  [dim]/status /model[/dim]  System and model status",
                        "  [dim]/context /memory[/dim]  Context and working memory",
                        "  [dim]/self /compact[/dim]  Capabilities and context compression",
                        "  [dim]/session /skill[/dim]  Session and skill management",
                        "  [dim]/benchmark[/dim]      Run benchmarks",
                        "  [dim]/exit /clear[/dim]    Exit the TUI or clear chat",
                        "",
                        "[bold]Tips[/bold]: Type directly • use /commands • click follow-ups",
                    )
                ),
                id="help-content",
            ),
            Button("Close (Esc)", variant="primary", id="help-close"),
            id="help-container",
        )

    def on_mount(self) -> None:
        container = self.query_one("#help-container")
        container.styles.background = "#1a1a2e"
        container.styles.border = ("solid", "#00ff87")
        container.styles.padding = (2, 4)
        container.styles.margin = (2, 4)

    def on_button_pressed(self, _event: Button.Pressed) -> None:
        _ = self.dismiss()


class ChatScreen(Screen[None]):
    """Main chat screen with message list, input, and status bar."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+c", "interrupt", "Clear / Cancel / Exit", priority=True),
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+l", "clear_chat", "Clear"),
        Binding("ctrl+p", "open_help", "Help"),
        Binding("escape", "open_help", "Help"),
    ]

    def __init__(self) -> None:
        super().__init__()
        # Phase 1 D6: mode_manager 전달하여 /plan, /build, /status 명령어 동작
        from antigravity_k.engine.mode_manager import ModeManager

        self._mode_manager: ModeManager = ModeManager()
        self.slash_registry: SlashCommandRegistry = SlashCommandRegistry(mode_manager=self._mode_manager)
        self._processing: bool = False
        self.chat_log: RichLog = RichLog(
            id="chat-log",
            highlight=True,
            markup=True,
            wrap=True,
            min_width=80,
        )
        self.suggestion_bar: SuggestionBar = SuggestionBar()
        self.input: SlashInput = SlashInput()
        self.send_btn: Button = Button("Send", variant="primary", id="send-btn")
        self.send_btn.styles.width = 10

    @override
    def compose(self) -> ComposeResult:
        """Create the main chat layout."""
        yield Header(show_clock=True)

        with Container(id="main-container"):
            # Chat message area
            yield self.chat_log

            # Follow-up suggestion bar
            yield self.suggestion_bar

        # Input area
        with Horizontal(id="input-area"):
            yield self.input
            yield self.send_btn

        yield StatusFooter()

    def on_mount(self) -> None:
        """Initialize the chat screen."""
        self._setup_styles()
        self._print_welcome()

        # Initialize status footer
        footer = self.query_one(StatusFooter)
        footer.status_text = "Ready"
        footer.server_status = "online"
        footer.tools_count = len(self.slash_registry.get_completions("/"))
        _ = self.input.focus()

    def _setup_styles(self) -> None:
        """Apply styling to the layout."""
        main = self.query_one("#main-container")
        main.styles.height = "1fr"
        main.styles.overflow_y = "hidden"

        chat = self.query_one("#chat-log")
        chat.styles.height = "1fr"
        chat.styles.padding = (1, 2)
        chat.styles.background = "#0d1117"
        chat.styles.overflow_y = "auto"

        input_area = self.query_one("#input-area")
        input_area.styles.height = 3
        input_area.styles.padding = (0, 1)
        input_area.styles.background = "#161b22"
        input_area.styles.align_vertical = "middle"

    def _print_welcome(self) -> None:
        """Print welcome message."""
        welcome = "".join(
            (
                f"[bold #00ff87]Ssak-Ai TUI v{__version__}[/]\n\n",
                "[dim]Terminal UI for the Local Autonomous Engineering Agent[/dim]\n\n",
                "Type a [bold]message[/bold] for conversation, or use [bold]/commands[/bold]:\n",
                "  [dim]/help[/dim]   — Show available commands\n",
                "  [dim]/tools[/dim]  — List tools\n",
                "  [dim]/status[/dim] — System status\n",
                "  [dim]/exit[/dim]   — Quit\n\n",
                "[dim]Ctrl+Space[/dim] for command completion  |  [dim]Ctrl+P[/dim] for help\n",
                "─" * 50,
            ),
        )
        self._add_message(welcome, "system")

    def _add_message(self, content: str, sender: str) -> None:
        """Add a message to the chat log."""
        ts = time.strftime("%H:%M:%S")
        _ = self.chat_log.write(make_message_bubble(content, sender, timestamp=ts))

    def _set_suggestions(self, suggestions: list[str]) -> None:
        """Update follow-up suggestion buttons."""
        self.suggestion_bar.set_suggestions(suggestions)

    # ─── Event Handlers ───────────────────────────────────────────

    def on_user_message(self, event: UserMessage) -> None:
        """Handle input submission from SlashInput."""
        _ = self._process_input(event.text)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "send-btn":
            text = self.input.value.strip()
            if text:
                _ = self._process_input(text)
                self.input.value = ""

    def on_suggestion_clicked(self, event: SuggestionClicked) -> None:
        """Handle follow-up suggestion click."""
        _ = self._process_input(event.text)

    # ─── Actions ──────────────────────────────────────────────────

    def action_open_help(self) -> None:
        """Open the help screen."""
        app = cast(App[None], self.app)
        _ = app.push_screen(HelpScreen())

    def action_clear_chat(self) -> None:
        """Clear the chat log."""
        _ = self.chat_log.clear()
        self._print_welcome()

    def action_quit(self) -> None:
        """Exit the application."""
        app = cast(App[None], self.app)
        app.exit()

    def action_interrupt(self) -> None:
        if self.input.value:
            self.input.value = ""
            _ = self.input.focus()
            self.query_one(StatusFooter).status_text = "Input cleared · Ctrl+C again to exit"
            return

        if self._processing:
            workers = cast(_WorkerController, cast(object, self.workers))
            _ = workers.cancel_group(self, "task")
            self._processing = False
            self._update_input_state(False)
            self.query_one(StatusFooter).status_text = "Task cancelled · Ctrl+C again to exit"
            self._add_message("[yellow]Current task cancelled.[/yellow]", "system")
            return

        app = cast(App[None], self.app)
        app.exit()

    # ─── Input Processing ─────────────────────────────────────────

    @work(exclusive=True, group="task", thread=True)
    def _process_input(self, text: str) -> None:
        """Process user input (slash command or natural language)."""
        if self._processing:
            return
        self._processing = True
        get_worker = cast(Callable[[], Worker[None]], textual_worker.get_current_worker)
        worker = get_worker()
        app = cast(App[None], self.app)

        try:
            # Show user message
            _ = app.call_from_thread(self._add_message, text, "user")
            _ = app.call_from_thread(self._update_input_state, True)

            # Process
            if text.startswith("/"):
                response = self._handle_slash_command(text)
            else:
                response = self._handle_natural_language(text)

            if worker.is_cancelled:
                return

            # Phase 1 D6: Update status footer with current mode after slash command
            if text.startswith("/") and self._mode_manager:
                _ = app.call_from_thread(
                    self._update_footer_mode,
                    self._mode_manager.current_mode.value,
                )

            # Show response
            _ = app.call_from_thread(self._add_message, response, "assistant")
            _ = app.call_from_thread(self._update_input_state, False)

            # Generate follow-up suggestions
            suggestions = self._generate_suggestions(text, response)
            if not worker.is_cancelled:
                _ = app.call_from_thread(self._set_suggestions, suggestions)

        except Exception as e:
            logger.exception("Input processing error")
            _ = app.call_from_thread(
                self._add_message,
                f"[red]Error: {e}[/red]",
                "system",
            )
            _ = app.call_from_thread(self._update_input_state, False)
        finally:
            self._processing = False

    def _update_input_state(self, processing: bool) -> None:
        """Update input area state."""
        if processing:
            self.input.disabled = True
            self.input.placeholder = "Processing..."
            self.send_btn.disabled = True
            status = self.query_one(StatusFooter)
            status.status_text = "Processing..."
        else:
            self.input.disabled = False
            self.input.placeholder = "Type a message or /command...  (Ctrl+Space for completions)"
            _ = self.input.focus()
            self.send_btn.disabled = False
            status = self.query_one(StatusFooter)
            status.status_text = "Ready"

    def _update_footer_mode(self, mode_value: str) -> None:
        """StatusFooter의 mode_name을 현재 실행 모드로 업데이트합니다."""
        try:
            footer = self.query_one(StatusFooter)
            footer.mode_name = mode_value
        except Exception:
            logger.warning("예외 발생 (silent swallow 제거)", exc_info=True)

    def _handle_slash_command(self, text: str) -> str:
        """Execute a slash command and return the response."""
        command = text.strip()

        if command == "/exit":
            app = cast(App[None], self.app)
            _ = app.call_from_thread(app.exit)
            return "Goodbye! 👋"

        if command == "/clear":
            app = cast(App[None], self.app)
            _ = app.call_from_thread(self.action_clear_chat)
            return "Chat cleared."

        try:
            registry = self.slash_registry
            if registry.is_command(command):
                result = registry.execute(command)
                return result if isinstance(result, str) else "".join(result)
            return f"Unknown command: {command}. Use /help to see available commands."
        except Exception as e:
            logger.exception("Slash command error")
            return f"Error executing command: {e}"

    def _handle_natural_language(self, text: str) -> str:
        """Handle natural language input."""
        return (
            f"[bold]Natural language processing (simulated):[/bold]\n"
            f"Your message: {text[:200]}\n\n"
            f"[dim]Connect the orchestrator backend for full AI response.[/dim]\n"
            f"[dim]For now, try /commands like /help, /tools, /status.[/dim]"
        )

    def _generate_suggestions(self, user_input: str, _response: str) -> list[str]:
        """Generate contextual follow-up suggestions."""
        suggestions = []

        if user_input.startswith("/"):
            cmd = user_input.split()[0].lower()
            suggestion_map = {
                "/help": ["/tools", "/status", "/self"],
                "/tools": ["/help", "/context", "/status"],
                "/status": ["/help", "/model", "/memory"],
                "/model": ["/status", "/help", "/context"],
                "/context": ["/compact", "/status", "/help"],
                "/memory": ["/session", "/status", "/help"],
                "/self": ["/help", "/status", "/tools"],
                "/session": ["/help", "/status", "/context"],
            }
            suggestions = suggestion_map.get(cmd, ["/help", "/status", "/tools"])
        else:
            suggestions = [
                "Show me available tools",
                "Check system status",
                "Help / commands",
            ]

        return suggestions[:5]


# ─── Main App ─────────────────────────────────────────────────────────────────


@final
class AgkTUI(App[None]):
    """Ssak-Ai Terminal User Interface."""

    TITLE = f"Ssak-Ai TUI v{__version__}"
    CSS = """
    Screen {
        background: #0d1117;
    }

    Header {
        background: #161b22;
        color: #c9d1d9;
    }

    Footer {
        background: #161b22;
        color: #8b949e;
    }

    .suggestion-btn {
        min-width: 10;
        padding: 0 2;
    }

    .suggestion-btn:hover {
        background: #3a3a5e;
    }

    #send-btn {
        dock: right;
        margin: 0 0 0 1;
    }

    #chat-log {
        border: solid #30363d;
    }

    RichLog {
        scrollbar-size-vertical: 1;
    }

    Input {
        background: #0d1117;
        color: #c9d1d9;
        border: solid #30363d;
    }

    Input:focus {
        border: solid #2d7ff9;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+c", "interrupt", "Clear / Cancel / Exit", priority=True),
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+p", "show_help", "Help"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._model_name: str = "local"
        self.dark = True

    def on_mount(self) -> None:
        """Set up the app on startup."""
        _ = self.push_screen(ChatScreen())

    def action_show_help(self) -> None:
        """Show help screen."""
        screen = cast(Screen[None], self.screen)
        if isinstance(screen, ChatScreen):
            screen.action_open_help()

    def action_interrupt(self) -> None:
        screen = cast(Screen[None], self.screen)
        if isinstance(screen, ChatScreen):
            screen.action_interrupt()
            return
        self.exit()

    @override
    def action_toggle_dark(self) -> None:
        """Toggle dark mode (always dark for terminal)."""
        self.dark = True


def run_tui() -> None:
    """Entry point to run the TUI."""
    app = AgkTUI()
    app.run()
