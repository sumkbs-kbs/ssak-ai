"""Flight Deck Telemetry Renderer — Real-time cockpit visualization for 27B agent flight.

Renders live Rich terminal telemetry panels during autonomous flight:
1. Subgoal DAG Progress & Active Task Gauge
2. Live TDD Pass/Fail Telemetry
3. Active Reflexion Negative Constraints
4. Memory & Fast-Path Latency Metrics
"""

from dataclasses import dataclass

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


@dataclass
class FlightTelemetryState:
    """Snapshot of active autonomous flight metrics."""

    mission_goal: str
    active_step: str
    completed_steps: int
    total_steps: int
    tdd_passed: int
    tdd_failed: int
    active_negative_constraints: list[str]
    fast_path_latency_ms: float
    model_name: str = "qwen3.8"


class FlightDeckRenderer:
    """Renders structured, high-density Rich visual panels of the flight deck."""

    @staticmethod
    def render_panel(state: FlightTelemetryState) -> Panel:
        """Render a single high-density telemetry panel."""
        progress_pct = (state.completed_steps / max(state.total_steps, 1)) * 100

        # Header Info Table
        header_table = Table.grid(expand=True)
        header_table.add_column("Key", style="bold cyan", width=18)
        header_table.add_column("Value", style="white")

        header_table.add_row("🎯 Mission:", f"[bold yellow]{state.mission_goal}[/bold yellow]")
        header_table.add_row("🤖 Engine Model:", f"[bold green]{state.model_name}[/bold green] (Local / Single Core)")
        header_table.add_row("⚡ Active Subgoal:", f"[bold magenta]{state.active_step}[/bold magenta]")
        header_table.add_row(
            "📊 DAG Progress:", f"[cyan]{state.completed_steps}/{state.total_steps}[/cyan] ({progress_pct:.0f}%)"
        )

        tdd_status = f"[green]✅ {state.tdd_passed} Passed[/green]"
        if state.tdd_failed > 0:
            tdd_status += f"  [red]❌ {state.tdd_failed} Failed[/red]"
        header_table.add_row("🧪 TDD Telemetry:", tdd_status)
        header_table.add_row(
            "⚡ Fast-Path Latency:", f"[green]{state.fast_path_latency_ms:.2f}ms[/green] (Zero LLM Overhead)"
        )

        # Constraints Sub-panel
        if state.active_negative_constraints:
            constraint_text = "\n".join([f"🚨 [red]{c}[/red]" for c in state.active_negative_constraints[:3]])
        else:
            constraint_text = "[green]✓ No active failure constraints (Smooth trajectory)[/green]"

        constraint_panel = Panel(
            constraint_text,
            title="[bold red]Active Reflexion Constraints[/bold red]",
            border_style="red" if state.active_negative_constraints else "dim green",
        )

        content_group = Group(
            header_table,
            Text(""),
            constraint_panel,
        )

        return Panel(
            content_group,
            title=f"[bold cyan]🛸 ANTIGRAVITY-K FLIGHT DECK — {state.model_name.upper()}[/bold cyan]",
            border_style="cyan",
            padding=(1, 2),
        )

    @staticmethod
    def render_recommendations_panel(recommendations_text: str) -> Panel:
        """Render the proactive next-actions recommendation panel."""
        return Panel(
            recommendations_text,
            title="[bold yellow]🔮 PROACTIVE NEXT-ACTIONS (FREEBUFF INTEL)[/bold yellow]",
            border_style="yellow",
            padding=(1, 2),
        )
