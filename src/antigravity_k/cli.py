"""Ssak-Ai command-line interface (Typer-based)."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, cast

import typer
from rich.console import Console
from rich.table import Table

from antigravity_k import __version__
from antigravity_k.config import config
from antigravity_k.engine.model_registry import ModelProfile, ModelRegistry
from antigravity_k.engine.secure_key import (
    VALID_SERVICES,
    get_api_key,
    get_key_source,
    remove_api_key,
    rotate_master_key,
    store_api_key,
)
from antigravity_k.engine.skill_market_client import SkillDetail, SkillMarketClient
from antigravity_k.engine.skill_market_registry import (
    InstallResponse,
    RegistrySkillInfo,
    SkillMarketRegistry,
)

app = typer.Typer(help="Ssak-Ai command line interface", no_args_is_help=True)
key_app = typer.Typer(help="Manage encrypted API keys in vault")
memory_app = typer.Typer(help="Manage project-scoped memory configuration")
task_app = typer.Typer(help="Inspect and resume durable agent tasks")
app.add_typer(key_app, name="key", help="Manage API keys")
app.add_typer(memory_app, name="memory", help="Manage project memory")
app.add_typer(task_app, name="task", help="Manage durable agent tasks")
error_app = typer.Typer(help="Inspect runtime error journal and AI agent fix prompts")
app.add_typer(error_app, name="error", help="Inspect runtime errors for agentic AI")
diagnostics_app = typer.Typer(help="Export safe support diagnostics (allowlist ZIP)")
app.add_typer(diagnostics_app, name="diagnostics", help="Export safe support diagnostics")
cognitive_app = typer.Typer(help="Inspect the opt-in cognitive core surface (read-only)")
app.add_typer(cognitive_app, name="cognitive", help="Inspect cognitive surface")
console = Console()


@app.callback(invoke_without_command=True)
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Print the Ssak-Ai version and exit.",
        ),
    ] = False,
) -> None:
    """Run the main entry point.

    Args:
        version (bool): bool version.

    """
    if version:
        console.print(f"ssak-ai {__version__}")
        raise typer.Exit()


@app.command()
def serve(
    host: Annotated[str | None, typer.Option("--host", help="Host to bind.")] = None,
    port: Annotated[int | None, typer.Option("--port", help="Port to bind.")] = None,
    reload: Annotated[bool, typer.Option("--reload", help="Enable uvicorn reload.")] = False,
    seed_budget: Annotated[
        str | None,
        typer.Option(
            "--seed-budget",
            help="Seed budget spend for disclosure testing: dollar amount (15.0), percent (30%), or preset (healthy/warning/exhausted).",
        ),
    ] = None,
    seed_level: Annotated[
        str | None,
        typer.Option(
            "--seed-level",
            help="Shortcut preset level for disclosure testing: healthy (30%), warning (88%), or exhausted (100%).",
        ),
    ] = None,
    seed_actions: Annotated[
        int | None,
        typer.Option(
            "--seed-actions",
            help="Optional override for hourly action count in disclosure testing.",
        ),
    ] = None,
) -> None:
    """Run the FastAPI server with optional session limits seeding."""
    import uvicorn

    from antigravity_k.api.startup_security import validate_startup_security

    bind_host = host or config.server.host
    target_port = port or config.server.port

    validate_startup_security(
        host=bind_host,
        environment=os.environ.get("AGK_ENV", "development"),
        access_pin=config.security.access_pin,
        pin_hash_file=Path(config.security.pin_hash_file),
    )

    if seed_budget or seed_level or seed_actions is not None:
        if seed_budget:
            os.environ["AGK_SEED_BUDGET"] = str(seed_budget)
        if seed_level:
            os.environ["AGK_SEED_LEVEL"] = str(seed_level)
        if seed_actions is not None:
            os.environ["AGK_SEED_ACTIONS"] = str(seed_actions)

        # 사전 진단/배너 출력용 미리보기
        from antigravity_k.engine.cost_guard import CostGuard
        from antigravity_k.engine.session_disclosure import seed_cost_guard

        preview_guard = CostGuard(
            daily_budget_usd=float(os.getenv("AGK_DAILY_BUDGET_USD", "50.0") or 0.0),
            hourly_action_limit=int(os.getenv("AGK_HOURLY_ACTION_LIMIT", "100") or 0),
            enabled=True,
        )
        spend, acts, lvl = seed_cost_guard(
            preview_guard,
            seed_budget=seed_budget,
            seed_level=seed_level,
            seed_actions=seed_actions,
        )
        level_style = {"healthy": "green", "warning": "yellow", "exhausted": "red"}.get(lvl, "cyan")
        console.print(
            f"[bold cyan]🌱 Disclosure Seeding Active:[/bold cyan] "
            f"Spend=[yellow]${spend:.2f}/{preview_guard.daily_budget_usd:.2f}[/yellow] "
            f"Actions=[yellow]{acts}/{preview_guard.hourly_action_limit}[/yellow] "
            f"Level=[bold {level_style}]{lvl}[/bold {level_style}]"
        )

    uvicorn.run(
        "antigravity_k.api.server:app",
        host=bind_host,
        port=target_port,
        reload=reload,
    )


@app.command("dev", help="Run local development server with auto-reload and optional seed limits.")
def dev(
    host: Annotated[str | None, typer.Option("--host", help="Host to bind.")] = None,
    port: Annotated[int | None, typer.Option("--port", help="Port to bind.")] = None,
    reload: Annotated[bool, typer.Option("--reload", help="Enable uvicorn reload.")] = True,
    seed_budget: Annotated[
        str | None,
        typer.Option(
            "--seed-budget",
            help="Seed budget spend for disclosure testing: dollar amount (15.0), percent (30%), or preset (healthy/warning/exhausted).",
        ),
    ] = None,
    seed_level: Annotated[
        str | None,
        typer.Option(
            "--seed-level",
            help="Shortcut preset level for disclosure testing: healthy (30%), warning (88%), or exhausted (100%).",
        ),
    ] = None,
    seed_actions: Annotated[
        int | None,
        typer.Option(
            "--seed-actions",
            help="Optional override for hourly action count in disclosure testing.",
        ),
    ] = None,
) -> None:
    """Run server in development mode (reload defaults to True)."""
    serve(
        host=host,
        port=port,
        reload=reload,
        seed_budget=seed_budget,
        seed_level=seed_level,
        seed_actions=seed_actions,
    )


@app.command("models")
def list_models() -> None:
    """List configured model profiles."""
    registry = ModelRegistry()
    _ = registry.refresh_local_models()
    table = Table(title="Configured Models")
    table.add_column("Name")
    table.add_column("Roles")
    table.add_column("Repo")
    table.add_column("Tier")
    table.add_column("Provider")
    table.add_column("Local")
    table.add_column("Memory GB", justify="right")

    for model in registry.list_models():
        table.add_row(
            model.name,
            ", ".join(model.supported_roles),
            model.repo,
            model.capability_tier,
            model.backend,
            "yes" if model.is_local else "no",
            f"{model.estimated_memory_gb:g}",
        )
    console.print(table)


@app.command()
def status() -> None:
    """Print mode status and basic project configuration."""
    from rich.panel import Panel

    from antigravity_k.engine.mode_manager import ModeManager

    mgr = ModeManager()

    # Mode status
    mode_lines = mgr.format_status().split("\n")
    console.print(
        Panel.fit(
            "\n".join(mode_lines),
            title="Execution Mode",
            border_style="cyan",
        ),
    )

    # Basic config
    console.print(
        {
            "version": __version__,
            "project_root": str(config.paths.project_root),
            "server": f"{config.server.host}:{config.server.port}",
            "api_engine": config.model.api_engine,
            "api_base": config.model.api_base,
        },
    )


@cognitive_app.command("status")
def cognitive_status(
    as_json: Annotated[bool, typer.Option("--json", help="Print the raw status JSON instead of a table.")] = False,
) -> None:
    """Show whether user surfaces run the legacy loop or the opt-in cognitive core.

    Read-only: no episode is executed and no store is written. ``cognitive_core`` 설정이 없으면
    기본 OFF이며 legacy 경로가 그대로 동작한다.
    """
    from antigravity_k.engine.cognitive_surface import CognitiveCoreSettings, CognitiveSurfaceAdapter

    settings = CognitiveCoreSettings.from_config(config)
    status = CognitiveSurfaceAdapter(settings).status()
    payload = status.as_mapping()
    if as_json:
        console.print_json(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return
    lines = [
        ("설정 섹션", "cognitive_core"),
        ("enabled", str(status.enabled)),
        ("requested mode", status.requested_mode or "(없음)"),
        ("effective mode", status.mode.value),
        ("surface source", status.source.value),
        ("legacy path", status.legacy_module),
        ("core path", status.core_module),
        ("policy target", status.policy_target or "(미설정)"),
        ("last episode", status.last_episode_id or "(없음)"),
        ("last termination", status.last_termination or "(없음)"),
        ("dispatched / refused", f"{status.dispatched_actions} / {status.refused_actions}"),
    ]
    table = Table(title="Cognitive surface (opt-in)")
    table.add_column("항목", style="cyan")
    table.add_column("값")
    for key, value in lines:
        table.add_row(key, value)
    console.print(table)
    for note in status.notes:
        console.print(f"[yellow]· {note}[/yellow]")


@cognitive_app.command("surface")
def cognitive_surface(
    output: Annotated[Path | None, typer.Option("--output", help="Write the measurement JSON artifact.")] = None,
) -> None:
    """Measure which entrypoints reach the legacy loop vs the cognitive core (static import graph)."""
    from antigravity_k.engine.cognitive_surface import measure_surface_reach

    measurement = measure_surface_reach()
    table = Table(title="Surface reach (static import graph)")
    table.add_column("surface", style="cyan")
    table.add_column("legacy")
    table.add_column("core")
    table.add_column("reached via")
    for item in measurement.entrypoints:
        via = " → ".join(item.legacy_via[1:]) if item.legacy_via else "-"
        table.add_row(item.label, str(item.reaches_legacy), str(item.reaches_core), via)
    console.print(table)
    console.print(
        f"legacy 도달 {measurement.legacy_count}/{len(measurement.entrypoints)} · "
        f"core 도달 {measurement.core_count}/{len(measurement.entrypoints)}"
    )
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(measurement.to_json() + "\n", encoding="utf-8")
        console.print(f"wrote {output}")


@app.command("run")
def run_agent(
    prompt: Annotated[str, typer.Argument(help="Prompt to run through the canonical agent runtime.")],
    model: Annotated[str, typer.Option("--model", help="Optional target model override.")] = "",
) -> None:
    from antigravity_k.api.dependencies import get_agent_runtime

    runtime = get_agent_runtime()
    tracked_stream = runtime.start_stream([{"role": "user", "content": prompt}], target_model=model)
    if tracked_stream.task_id:
        console.print(f"Task: {tracked_stream.task_id}")
    for chunk in tracked_stream.chunks:
        console.print(chunk, end="")
    console.print()


@app.command("recipes", help="List training data-recipe presets (unsloth Data Recipes style).")
def recipes_list() -> None:
    """데이터 레시피 카탈로그 출력."""
    from antigravity_k.engine.data_recipes import list_recipes

    table = Table(title="Data Recipes")
    table.add_column("Name")
    table.add_column("Format")
    table.add_column("Min")
    table.add_column("Description")
    for recipe in list_recipes():
        table.add_row(
            str(recipe["name"]),
            str(recipe["format"]),
            str(recipe["min_records"]),
            str(recipe["description"]),
        )
    console.print(table)


@app.command("train-recipe", help="Apply a data recipe: source → dataset → training config.")
def train_recipe(
    recipe: Annotated[str, typer.Argument(help="Recipe name (see: agk recipes)")],
    base_model: Annotated[
        str, typer.Option("--model", help="Base model (HF ID or local path)")
    ] = "mlx-community/Qwen2.5-Coder-32B-Instruct-4bit",
    source: Annotated[str, typer.Option("--source", help="File path(s) csv/jsonl/txt/md, or 'harvest'")] = "",
    output_dir: Annotated[str, typer.Option("--out", help="Output directory")] = "data/recipe_output",
    platform: Annotated[str, typer.Option("--platform", help="mlx / unsloth / auto")] = "auto",
    pdf_pages: Annotated[
        str, typer.Option("--pdf-pages", help="PDF only: page ranges, e.g. '1-5,8' (default: all)")
    ] = "",
    pdf_header_filter: Annotated[
        str, typer.Option("--pdf-header-filter", help="PDF only: header regex ('!' prefix excludes non-matching pages)")
    ] = "",
    pdf_question_template: Annotated[
        str,
        typer.Option(
            "--pdf-question-template",
            help="PDF/DOCX only: force question from template with {page} {title} {header} {body} placeholders",
        ),
    ] = "",
) -> None:
    """레시피를 적용해 데이터셋과 학습 설정을 생성한다."""
    import json as _json

    from antigravity_k.engine.data_recipes import UnknownRecipeError
    from antigravity_k.engine.lora_pipeline import LoRAPipeline

    pipeline = LoRAPipeline()
    try:
        result = pipeline.apply_recipe(
            recipe,
            base_model=base_model,
            output_dir=output_dir,
            source=source,
            platform=platform,
            pdf_pages=pdf_pages,
            pdf_header_filter=pdf_header_filter,
            pdf_question_template=pdf_question_template,
        )
    except (UnknownRecipeError, FileNotFoundError, ValueError) as exc:
        console.print(f"[red]✗ {exc}[/red]")
        raise typer.Exit(code=2) from exc

    warn = "" if result["sufficient"] else " ⚠️ 최소 레코드 미달"
    console.print(
        f"[green]✓ {result['recipe']}[/green] — {result['records']}건{warn}\n"
        f"  데이터셋: {result['dataset_path']}\n"
        f"  설정: {result['config_path']}",
    )
    hyper = result["config"].get("hyperparameters")
    if isinstance(hyper, dict) and hyper:
        console.print(f"  하이퍼파라미터: {_json.dumps(hyper, ensure_ascii=False, sort_keys=True)}")


@app.command("fuse-and-serve", help="Fuse LoRA adapter with base model and register into Ollama.")
def fuse_and_serve(
    base_model: Annotated[
        str, typer.Option("--model", "-m", help="Base model (HF ID or local snapshot path)")
    ] = "mlx-community/Qwen2.5-0.5B-4bit",
    adapter_path: Annotated[
        str, typer.Option("--adapter", "-a", help="Trained LoRA adapter directory")
    ] = "data/lora_e2e_out/adapters",
    output_dir: Annotated[
        str, typer.Option("--out", "-o", help="Output directory for merged model")
    ] = "data/lora_e2e_out/merged",
    ollama_name: Annotated[
        str, typer.Option("--ollama-name", help="Target Ollama model tag")
    ] = "ssak-finetuned:qwen2.5-0.5b",
    de_quantize: Annotated[
        bool, typer.Option("--de-quantize", help="De-quantize weights to float16 during fuse")
    ] = False,
    skip_fuse: Annotated[
        bool, typer.Option("--skip-fuse", help="Skip fuse step if merged model/GGUF already exists")
    ] = False,
    gguf_path: Annotated[str, typer.Option("--gguf", help="Path to pre-converted GGUF file if available")] = "",
    system_prompt: Annotated[str, typer.Option("--system-prompt", help="System prompt to embed into Modelfile")] = "",
) -> None:
    """LoRA 어댑터를 베이스 모델과 병합하고 Ollama에 등록하여 서빙을 준비합니다."""
    from antigravity_k.engine.lora_pipeline import LoRAPipeline

    console.print("[bold cyan]⚡ Ssak-Ai Train-to-Serve Fuse & Ollama Registration[/bold cyan]")
    console.print(f"  Base Model: [yellow]{base_model}[/yellow]")
    console.print(f"  Adapter:    [yellow]{adapter_path}[/yellow]")
    console.print(f"  Output Dir: [yellow]{output_dir}[/yellow]")
    console.print(f"  Ollama Tag: [green]{ollama_name}[/green]")

    pipeline = LoRAPipeline()
    result = pipeline.fuse_and_register_ollama(
        base_model=base_model,
        adapter_path=adapter_path,
        output_dir=output_dir,
        ollama_model_name=ollama_name,
        de_quantize=de_quantize,
        skip_fuse=skip_fuse,
        gguf_path=gguf_path if gguf_path else None,
        system_prompt=system_prompt,
        on_log=lambda line: console.print(f"  [dim]{line}[/dim]"),
    )

    if not result.get("success"):
        stage = result.get("stage", "unknown")
        err = result.get("error", "Unknown error")
        console.print(f"\n[red]✗ Train-to-Serve failed at stage '{stage}': {err}[/red]")
        raise typer.Exit(code=1)

    console.print("\n[bold green]✓ Train-to-Serve Complete![/bold green]")
    console.print(f"  Merged Model: {result.get('merged_path')}")
    console.print(f"  Modelfile:    {result.get('modelfile_path')}")
    console.print(f"  Ollama Model: [bold green]{result.get('ollama_model_name')}[/bold green]")
    console.print(f"  Elapsed Time: {result.get('elapsed_sec', 0.0):.2f}s")
    console.print(f"\n[dim]Verify inference with:[/dim] [yellow]ollama run {ollama_name}[/yellow]")


@app.command("session", help="Show session limits and data-use disclosure before you start.")
def session_disclosure(
    seed_budget: Annotated[
        str | None,
        typer.Option(
            "--seed-budget",
            help="Seed budget amount ($15.0), percent (30%), or preset (healthy/warning/exhausted).",
        ),
    ] = None,
    seed_level: Annotated[
        str | None,
        typer.Option(
            "--seed-level",
            help="Shortcut preset: healthy (30%), warning (88%), or exhausted (100%).",
        ),
    ] = None,
    seed_actions: Annotated[
        int | None,
        typer.Option(
            "--seed-actions",
            help="Optional override for hourly action count.",
        ),
    ] = None,
) -> None:
    """세션 한도·데이터 사용 고지 (벤치마킹: freebuff 사전 고지 UX)."""
    import os

    from rich.panel import Panel

    from antigravity_k.engine.cost_guard import CostGuard
    from antigravity_k.engine.session_disclosure import build_session_disclosure, seed_cost_guard

    daily_budget = float(os.getenv("AGK_DAILY_BUDGET_USD", "50.0") or 0.0)
    hourly_limit = int(os.getenv("AGK_HOURLY_ACTION_LIMIT", "100") or 0)
    guard = CostGuard(daily_budget_usd=daily_budget, hourly_action_limit=hourly_limit, enabled=True)

    if seed_budget or seed_level or seed_actions is not None:
        seed_cost_guard(
            guard,
            seed_budget=seed_budget,
            seed_level=seed_level,
            seed_actions=seed_actions,
        )

    disclosure = build_session_disclosure(guard.get_daily_stats())

    border = {"healthy": "green", "warning": "yellow", "exhausted": "red"}.get(disclosure.level, "cyan")
    console.print(Panel.fit(disclosure.to_markdown(), title="Session Limits", border_style=border))


@app.command("start", help="Connect an external coding agent (claude/codex/...) to local models.")
def start_agent_bridge(
    agent: Annotated[str, typer.Argument(help="Agent to bridge: claude, codex, opencode, openclaw, hermes")],
    model: Annotated[
        str, typer.Option("--model", help="Model to expose to the agent. Defaults to routing default.")
    ] = "",
    api_base: Annotated[str, typer.Option("--api-base", help="Ssak-Ai API base URL. Defaults to config server.")] = "",
) -> None:
    """원커맨드 에이전트 브리지 (벤치마킹: unsloth start)."""
    from antigravity_k.engine.agent_bridges import UnknownAgentError, format_bridge_plan, resolve_bridge

    resolved_base = api_base or f"http://{config.server.host}:{config.server.port}"
    default_model = ""
    context_window = 0
    try:
        registry = ModelRegistry()
        default_model = getattr(config.model, "main_model", "") or ""
        if not default_model:
            models = registry.list_models()
            default_model = models[0].name if models else ""
        # Phase 36: Claude Code CLAUDE_CODE_MAX_CONTEXT_TOKENS용 실제 윈도 조회.
        # 레지스트리 이름은 태그 없는 경우가 많아(qwen3.8) ollama 태그(qwen3.8:latest)를
        # 정규화해 대조한다.
        effective_model = (model or default_model).strip()
        if effective_model:
            requested = effective_model.split(":", 1)[0].strip().casefold()
            for entry in registry.list_models():
                entry_name = str(getattr(entry, "name", ""))
                if entry_name.split(":", 1)[0].strip().casefold() == requested:
                    context_window = int(getattr(entry, "context_length", 0) or 0)
                    break
    except Exception:  # noqa: BLE001
        default_model = ""

    try:
        spec, env = resolve_bridge(
            agent,
            model=model,
            api_base=resolved_base,
            default_model=default_model,
            context_window=context_window,
        )
    except UnknownAgentError as exc:
        console.print(f"[red]✗ {exc}[/red]")
        raise typer.Exit(code=2) from exc

    console.print(format_bridge_plan(spec, env))


@task_app.command("list", help="List recent durable agent tasks.")
def task_list(limit: Annotated[int, typer.Option("--limit", min=1, max=200)] = 20) -> None:
    from antigravity_k.api.dependencies import get_agent_runtime

    table = Table(title="Durable Tasks")
    table.add_column("Task ID")
    table.add_column("Status")
    table.add_column("Prompt")
    for task in get_agent_runtime().list_tasks(limit=limit):
        table.add_row(
            str(task.get("task_id", "")),
            str(task.get("status", "unknown")),
            str(task.get("prompt", "")),
        )
    console.print(table)


@task_app.command("status", help="Show the durable state of one task.")
def task_status(task_id: str) -> None:
    from antigravity_k.api.dependencies import get_agent_runtime

    status = get_agent_runtime().get_task_status(task_id)
    if status is None:
        console.print(f"[red]Task not found:[/red] {task_id}")
        raise typer.Exit(code=1)
    console.print(status)


@task_app.command("output", help="Print the accumulated output of one task.")
def task_output(task_id: str) -> None:
    from antigravity_k.api.dependencies import get_agent_runtime

    output = get_agent_runtime().get_task_output(task_id)
    if output is None:
        console.print(f"[red]Task output not found:[/red] {task_id}")
        raise typer.Exit(code=1)
    console.print(output, end="")
    if not output.endswith("\n"):
        console.print()


@task_app.command("resume", help="Resume a failed or paused task and wait for its result.")
def task_resume(
    task_id: str,
    model: Annotated[str, typer.Option("--model", help="Optional target model override.")] = "",
    timeout: Annotated[float, typer.Option("--timeout", min=0.1, help="Maximum wait time in seconds.")] = 300.0,
) -> None:
    from antigravity_k.api.dependencies import get_agent_runtime

    runtime = get_agent_runtime()
    if not runtime.resume_task(task_id, target_model=model):
        console.print(f"[red]Task is not resumable or has no checkpoint:[/red] {task_id}")
        raise typer.Exit(code=1)
    status = runtime.wait_task(task_id, timeout=timeout)
    if status is None:
        console.print(f"[red]Task not found after resume:[/red] {task_id}")
        raise typer.Exit(code=1)
    state = str(status.get("status", "unknown"))
    console.print(f"Status: {state}")
    output = runtime.get_task_output(task_id)
    if output:
        console.print(output, end="")
        if not output.endswith("\n"):
            console.print()
    if state != "done":
        raise typer.Exit(code=2)


@memory_app.command("aliases")
def memory_aliases() -> None:
    from antigravity_k.engine.project_memory_keys import read_project_alias_schema
    from antigravity_k.engine.project_memory_paths import project_memory_dir

    schema = read_project_alias_schema(project_memory_dir(Path.cwd()))
    table = Table(title="Project Memory Aliases")
    table.add_column("Canonical Key")
    table.add_column("Aliases")
    for canonical, aliases in sorted(schema.aliases.items()):
        table.add_row(canonical, ", ".join(aliases))
    console.print(table)


@memory_app.command("alias-set")
def memory_alias_set(canonical: str, alias: str) -> None:
    from pydantic import ValidationError

    from antigravity_k.engine.project_memory_keys import (
        ProjectAliasConfigError,
        set_project_alias,
    )
    from antigravity_k.engine.project_memory_paths import project_memory_dir

    try:
        schema = set_project_alias(project_memory_dir(Path.cwd()), canonical, alias)
    except (ProjectAliasConfigError, ValidationError, ValueError) as error:
        console.print(f"[red]Invalid project alias: {error}[/red]")
        raise typer.Exit(code=1) from error
    console.print(f"[green]Project alias saved:[/green] {alias} -> {canonical}")
    console.print(f"Aliases for {canonical}: {', '.join(schema.aliases[canonical])}")


@memory_app.command("alias-remove")
def memory_alias_remove(alias: str) -> None:
    from pydantic import ValidationError

    from antigravity_k.engine.project_memory_keys import (
        ProjectAliasConfigError,
        remove_project_alias,
    )
    from antigravity_k.engine.project_memory_paths import project_memory_dir

    try:
        _ = remove_project_alias(project_memory_dir(Path.cwd()), alias)
    except (ProjectAliasConfigError, ValidationError, ValueError) as error:
        console.print(f"[red]Invalid project alias: {error}[/red]")
        raise typer.Exit(code=1) from error
    console.print(f"[green]Project alias removed:[/green] {alias}")


@memory_app.command("list")
def memory_list(top: int = 20) -> None:
    """메모리 팩트를 중요도 점수 순으로 나열합니다."""
    from antigravity_k.api.dependencies import get_memory_manager

    ranked = get_memory_manager().ranked_facts(top_k=max(1, top))
    if not ranked:
        console.print("[yellow]저장된 메모리 팩트가 없습니다.[/yellow]")
        raise typer.Exit()
    table = Table(title=f"Memory Facts (top {len(ranked)})")
    table.add_column("Key")
    table.add_column("Source")
    table.add_column("Scope")
    table.add_column("Authority")
    table.add_column("Score")
    table.add_column("Value")
    for fact, score in ranked:
        table.add_row(
            fact.key,
            fact.source,
            fact.scope,
            str(int(fact.authority)),
            f"{score:.1f}",
            fact.value[:80],
        )
    console.print(table)


@memory_app.command("remove")
def memory_remove(provider: str, key: str) -> None:
    """개별 메모리 항목을 삭제합니다 (예: project decision:db, global identity:name)."""
    from antigravity_k.api.dependencies import get_memory_manager

    if not get_memory_manager().delete_entry(provider, key):
        console.print(f"[red]삭제 실패:[/red] {provider} {key} (항목 없음 또는 미지원)")
        raise typer.Exit(code=1)
    console.print(f"[green]삭제 완료:[/green] {provider} {key}")


@memory_app.command("retain")
def memory_retain(days: int) -> None:
    """지정 일수보다 오래된 메모리를 TTL 정리합니다."""
    from antigravity_k.api.dependencies import get_memory_manager

    if days < 0:
        console.print("[red]days는 0 이상이어야 합니다.[/red]")
        raise typer.Exit(code=1)
    report = get_memory_manager().apply_retention(days)
    total = sum(report.values())
    console.print(f"[green]TTL 정리 완료:[/green] {total}건 제거")
    for provider, count in report.items():
        console.print(f"  {provider}: {count}")


@app.command()
def doctor(
    heal: Annotated[
        bool, typer.Option("--heal", "-h", help="Automatically repair detected issues and clean stale caches.")
    ] = False,
) -> None:
    """Run a full environment diagnostic with automated self-healing capabilities."""
    from rich.panel import Panel
    from rich.table import Table

    if heal:
        from antigravity_k.engine.self_healing_doctor import SelfHealingDoctor

        doc = SelfHealingDoctor(project_root=".")
        rep = doc.run_health_check(auto_heal=True)
        console.print(
            f"[bold cyan]🏥 Self-Healing Doctor Results:[/bold cyan] {rep.healthy_count}/{rep.total_checks} Healthy ({rep.repaired_count} Auto-Repaired)"
        )
        for c in rep.checks:
            icon = "✅" if c.status in ("HEALTHY", "REPAIRED") else "⚠️"
            console.print(f"  {icon} [bold]{c.name}:[/bold] {c.message}")
        return

    results: list[tuple[str, str, str]] = []  # (check, status, detail)
    passed = 0
    warnings = 0
    failed = 0

    def check(name: str, ok: bool, detail: str = "", is_warning: bool = False):
        nonlocal passed, warnings, failed
        if ok:
            status = "[green]✅ PASS[/green]"
            passed += 1
        elif is_warning:
            status = "[yellow]⚠️  WARN[/yellow]"
            warnings += 1
        else:
            status = "[red]❌ FAIL[/red]"
            failed += 1
        results.append((name, status, detail))

    # ── 1. Python & System Tools ──
    import sys

    check(
        "Python version",
        sys.version_info >= (3, 12),
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro} (requires ≥3.12)",
    )

    import shutil

    for tool in ("git", "node"):
        path = shutil.which(tool)
        check(f"{tool} in PATH", path is not None, path or "not found")

    # ── 2. Configuration ──
    check(
        "config.yaml exists",
        config.config_path.is_file(),
        str(config.config_path),
    )

    problems = config.validate()
    check(
        "Config validation",
        len(problems) == 0,
        f"{len(problems)} problem(s)" if problems else "all checks passed",
        is_warning=bool(problems),
    )

    # ── 3. API Keys ──
    for service in ("openrouter", "anthropic", "nvidia"):
        key = get_api_key(service)
        check(
            f"API key: {service}",
            key is not None,
            get_key_source(service) if key else "not set (optional)",
            is_warning=key is None,
        )

    # ── 4. Model Registry ──
    registry: ModelRegistry | None = None
    models: list[ModelProfile] = []
    try:
        registry = ModelRegistry()
        models = registry.list_models()
        check(
            "Model registry loaded",
            len(models) > 0,
            f"{len(models)} model(s) registered",
        )
    except Exception as e:
        check("Model registry loaded", False, str(e))

    # ── 4b. Local Providers (ollama / lmstudio / mlx) ──
    if registry is not None:
        from antigravity_k.engine.provider_capabilities import (
            LocalProviderCapabilityProbe,
            remediation_hint,
        )

        local_backends = {"ollama", "lmstudio", "lm_studio", "mlx"}
        representative_models: dict[str, ModelProfile] = {}
        for model in models:
            backend = model.backend.casefold() if model.backend else ""
            if backend in local_backends:
                _ = representative_models.setdefault(backend, model)
        capability_probe = LocalProviderCapabilityProbe(registry)
        for profile in representative_models.values():
            capability = capability_probe.observe(profile)
            available = capability["runtime_status"] == "available"
            detail = (
                f"provider={capability['provider']} · "
                f"native_tools={capability['native_tool_calling']} · "
                f"{capability['source']} · {capability['detail']}"
            )
            hint = remediation_hint(profile, capability)
            if hint:
                detail += f" · fix={hint}"
            # 로컬 프로바이더는 선택적이므로 도달 실패는 FAIL이 아닌 WARN으로 처리한다.
            check(f"Local model health: {profile.name}", available, detail, is_warning=not available)

    # ── 5. Port Availability ──
    import socket

    port = config.server.port
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    try:
        result = sock.connect_ex(("127.0.0.1", port))
        check(
            f"Port {port} available",
            result != 0,
            f"port {'in use' if result == 0 else 'free'}",
            is_warning=result == 0,
        )
    finally:
        sock.close()

    # ── 6. Data Directories ──
    import os

    vault_env = os.environ.get("ANTIGRAVITY_VAULT_PATH", "vault_data")
    vault_path = Path(vault_env)
    try:
        vault_path.mkdir(parents=True, exist_ok=True)
        test_file = vault_path / ".doctor_write_test"
        _ = test_file.write_text("ok")
        test_file.unlink()
        check("Vault directory writable", True, str(vault_path.resolve()))
    except Exception as e:
        check("Vault directory writable", False, str(e))

    logs_dir = Path(config.paths.logs_dir)
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        check("Logs directory writable", True, str(logs_dir.resolve()))
    except Exception as e:
        check("Logs directory writable", False, str(e), is_warning=True)

    # ── 7. Amplification (CoV / cognitive / self-consistency / decomposition) ──
    # 작은 모델 성능 증폭 서브시스템의 현재 설정을 사용자에게 보여준다.
    # doctor는 읽기 전용 진단이므로 설정값은 표시만 하고 통과 처리한다.
    import yaml as _yaml

    def _object_dict(value: object) -> dict[str, object]:
        if not isinstance(value, dict):
            return {}
        raw = cast(Mapping[object, object], value)
        return {str(key): item for key, item in raw.items()}

    amp_section: dict[str, object] = {}
    _cfg_path = config.config_path
    if _cfg_path.exists():
        try:
            with _cfg_path.open() as _f:
                _raw: object = cast(object, _yaml.safe_load(_f) or {})
            if isinstance(_raw, dict):
                raw_config = cast(Mapping[str, object], _raw)
                amp_section = _object_dict(raw_config.get("amplification"))
        except Exception:
            amp_section = {}

    _cov = _object_dict(amp_section.get("cognitive"))
    _cov_enabled = bool(_cov.get("enabled", True))
    check(
        "Amplification: cognitive loop",
        True,
        f"{'on' if _cov_enabled else 'off'} · retries={_cov.get('max_retries', 2)} dialectic={_cov.get('dialectic_enabled', True)}",
    )

    _cog = _object_dict(amp_section.get("cov"))
    _cog_enabled = bool(_cog.get("enabled", True))
    check(
        "Amplification: chain-of-verification",
        True,
        f"{'on' if _cog_enabled else 'off'} · revise={_cog.get('max_revise_iterations', 2)} threshold={_cog.get('complexity_threshold', 0.4)}",
    )

    _sc = _object_dict(amp_section.get("self_consistency"))
    _sc_enabled = bool(_sc.get("enabled", False))
    check(
        "Amplification: self-consistency",
        True,
        f"{'on' if _sc_enabled else 'off'} · n={_sc.get('n_samples', 5)} gate={_sc.get('complexity_threshold', 'null')}",
    )

    _td = _object_dict(amp_section.get("task_decomposition"))
    _td_enabled = bool(_td.get("enabled", False))
    check(
        "Amplification: task decomposition",
        True,
        f"{'on' if _td_enabled else 'off'} · steps={_td.get('min_steps', 2)}-{_td.get('max_steps', 6)} escalate={'on' if _td.get('escalate_on_revision_failure', False) else 'off'}",
    )

    # ── Output ──
    table = Table(title="🩺 Ssak-Ai Doctor", show_header=True, header_style="bold cyan")
    table.add_column("Check", style="bold")
    table.add_column("Status", justify="center")
    table.add_column("Detail", style="dim", overflow="fold")

    for name, status_text, detail in results:
        table.add_row(name, status_text, detail)

    console.print(table)
    console.print()

    summary_color = "red" if failed else ("yellow" if warnings else "green")
    console.print(
        Panel.fit(
            f"[bold]{passed} passed[/bold] · [yellow]{warnings} warnings[/yellow] · [red]{failed} failed[/red]",
            title=f"[{summary_color}]Diagnostic Summary[/{summary_color}]",
            border_style=summary_color,
        ),
    )

    if failed > 0:
        console.print("\n[red]❌ Issues detected. Fix the failing checks above before proceeding.[/red]")
        raise typer.Exit(code=1)
    elif warnings > 0:
        console.print("\n[yellow]⚠️  Some warnings detected. The app may work but check the items above.[/yellow]")


# ─── Key Management Commands ──────────────────────────────────────


def _validate_service(service: str) -> str:
    """서비스 이름을 검증하고 정규화합니다."""
    svc = service.lower().strip()
    if svc not in VALID_SERVICES:
        console.print(f"[red]❌ 지원하지 않는 서비스: '{svc}'[/red]")
        console.print(f"   유효한 서비스: {', '.join(VALID_SERVICES)}")
        raise typer.Exit(code=1)
    return svc


_SOURCE_ICON = {
    "env": "🌐 환경변수",
    "dotenv": "📄 .env 파일",
    "config": "⚙️  config.yaml",
    "vault": "🔐 vault 암호화",
    "none": "—",
}


@key_app.command("set")
def key_set(
    service: Annotated[str, typer.Argument(help="Service name (anthropic, openai, openrouter)")],
    key: Annotated[str, typer.Argument(help="API key to store")],
) -> None:
    """암호화하여 API 키를 vault 저장소에 저장합니다.

    키는 머신 고유 키로 PBKDF2 + Fernet 암호화되어

    .agk_vault/keys.enc에 저장됩니다 (git 무시됨).

    우선순위: 환경변수 > .env 파일 > config.yaml > vault 저장소
    """
    svc = _validate_service(service)

    if len(key) < 8:
        console.print("[red]❌ API 키가 너무 짧습니다 (최소 8자).[/red]")
        raise typer.Exit(code=1)

    # 이미 환경변수에 설정되어 있는지 확인
    env_var = f"AGK_{svc.upper()}_KEY"
    import os

    if os.environ.get(env_var):
        console.print(
            f"[yellow]⚠️  환경변수 {env_var}가 이미 설정되어 있습니다.[/yellow]\n   vault 저장소에 저장해도 환경변수가 우선 적용됩니다."
        )

    success = store_api_key(svc, key)
    if success:
        # 마스킹된 키 출력
        masked = key[:4] + "*" * min(len(key) - 4, 16)
        console.print("[green]✅ API 키 저장 완료[/green]")
        console.print(f"   서비스: {svc}")
        console.print(f"   키     : {masked}")
        console.print("   위치  : .agk_vault/keys.enc (암호화)")
        console.print("")
        console.print(
            f"[dim]팁: 키를 환경변수로도 설정하려면:  export {env_var}=your-key[/dim]",
        )
    else:
        console.print("[red]❌ 키 저장 실패[/red]")
        raise typer.Exit(code=1)


@key_app.command("list")
def key_list() -> None:
    """설정된 API 키 상태를 확인합니다.

    모든 소스(환경변수, .env, config.yaml, vault)를 확인하여

    각 서비스별로 키 설정 여부와 출처를 표시합니다.
    """
    table = Table(title="API Key Status")
    table.add_column("Service")
    table.add_column("Status")
    table.add_column("Source")
    table.add_column("Key (masked)")

    for svc in VALID_SERVICES:
        source = get_key_source(svc)
        key = get_api_key(svc)

        if key:
            masked = key[:4] + "*" * min(len(key or "") - 4, 16)
            table.add_row(svc, "✅ 설정됨", _SOURCE_ICON.get(source, source), masked)
        else:
            table.add_row(
                svc,
                "❌ 미설정",
                "—",
                f"[dim]export AGK_{svc.upper()}_KEY=... 또는 agk key set {svc} <key>[/dim]",
            )

    console.print(table)
    console.print(
        "\n[dim]키 우선순위: 환경변수 > .env 파일 > config.yaml > vault[/dim]",
    )


@key_app.command("remove")
def key_remove(
    service: Annotated[str, typer.Argument(help="Service name to remove from vault (anthropic, openai, openrouter)")],
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-f",
            help="확인 없이 삭제",
        ),
    ] = False,
) -> None:
    """Vault 저장소에서 API 키를 삭제합니다.

    환경변수나 .env 파일에 설정된 키는 삭제되지 않습니다.

    (해당 소스에서 직접 제거해야 함)
    """
    svc = _validate_service(service)

    # vault에 키가 있는지 확인
    source = get_key_source(svc)
    key = get_api_key(svc)

    if source != "vault":
        if source == "none":
            console.print(f"[yellow]⚠️  vault에 {svc} 키가 저장되어 있지 않습니다.[/yellow]")
        else:
            icon = _SOURCE_ICON.get(source, source)
            msg = f"[yellow]⚠️  {svc} 키는 {icon}에 설정되어 있어 vault에서 삭제할 수 없습니다.[/yellow]"
            console.print(f"{msg}\n   해당 소스({icon})에서 직접 제거하세요.")
        return

    if not force:
        masked = (key or "")[:4] + "*" * min(len(key or "") - 4, 16)
        console.print("[yellow]⚠️  다음 키를 vault에서 삭제합니다:[/yellow]")
        console.print(f"   서비스: {svc}")
        console.print(f"   키     : {masked}")
        confirm = typer.confirm("계속하시겠습니까?")
        if not confirm:
            console.print("[dim]취소됨[/dim]")
            raise typer.Exit()

    if remove_api_key(svc):
        console.print(f"[green]✅ vault에서 {svc} 키가 삭제되었습니다.[/green]")
    else:
        console.print(f"[yellow]⚠️  vault에 {svc} 키가 없습니다.[/yellow]")


@key_app.command("rotate")
def key_rotate(
    seed: Annotated[
        str | None,
        typer.Option(
            "--seed",
            "-s",
            help="새 머신 시드 (지정하지 않으면 현재 시드 재사용, 동일 키 유지)",
        ),
    ] = None,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-f",
            help="키가 동일해도 강제 재암호화",
        ),
    ] = False,
) -> None:
    """마스터 키를 순환(rotation)하고 vault 데이터를 재암호화합니다.

    --seed를 지정하면 새 시드로 새 키가 생성됩니다.

    --seed를 생략하면 현재 시드를 재사용하므로 동일한 키가 유지됩니다.
    (의미 있는 순환을 위해서는 --seed를 지정하세요.)

    --force를 사용하면 키가 동일해도 강제로 재암호화합니다.
    """
    result = rotate_master_key(new_seed=seed, force=force)

    if not result["success"]:
        console.print(f"[red]❌ 키 순환 실패: {result.get('error')}[/red]")
        raise typer.Exit(code=1)

    if not result["rotated"]:
        console.print(
            "[yellow]⚠️  키가 변경되지 않았습니다.[/yellow]\n   --seed <새 시드>를 지정하여 새 키를 생성하세요.",
        )
        return

    svc_count = result["services_count"]
    console.print("[green]✅ 마스터 키 순환 완료[/green]")
    console.print(f"   재암호화된 서비스: {svc_count}개")
    if svc_count > 0:
        console.print("   위치: .agk_vault/keys.enc (새 키로 암호화)")
    if seed:
        console.print("   키체인에 새 시드 저장됨")


# ─── Model Command ────────────────────────────────────────────────────────


model_app = typer.Typer(help="Manage models: list, set defaults")
app.add_typer(model_app, name="model", help="Manage models and set defaults")


def _quant_cell(quantization: str) -> str:
    """양자화 토큰 + 등급 한 글자(색상) rich 셀 — 대시보드 Model Hub 배지와 동일 체계."""
    from antigravity_k.engine.quant_quality import quant_quality

    info = quant_quality(quantization)
    if info.level == "unknown":
        return "[dim]—[/dim]"
    color = {"premium": "green", "high": "cyan", "balanced": "magenta", "compact": "dark_orange"}[info.level]
    return f"{quantization} [{color}]{info.grade}[/{color}]"


@model_app.command("list")
def model_list(
    min_quality: Annotated[
        str,
        typer.Option(
            "--min-quality",
            "-q",
            help="이 품질 등급 이상 모델만 표시 (compact < balanced < high < premium). "
            "대시보드 Model Hub의 품질 pill과 동일한 LEVEL_ORDER 랭킹 (Phase 45).",
            show_default=False,
        ),
    ] = "",
) -> None:
    """List all available models with role grouping, quant quality grades, and defaults."""
    from rich.panel import Panel
    from rich.table import Table

    from antigravity_k.engine.quant_quality import LEVEL_ORDER, quant_quality

    min_level = (min_quality or "").strip().lower()
    if min_level and min_level not in LEVEL_ORDER:
        valid = " < ".join(k for k in LEVEL_ORDER if k != "unknown")
        console.print(f"[red]❌ 알 수 없는 품질 등급 '{min_quality}'. 사용 가능: {valid}, unknown[/red]")
        raise typer.Exit(code=2)
    min_rank = LEVEL_ORDER.get(min_level, 0) if min_level else 0

    registry = ModelRegistry()
    _ = registry.refresh_local_models()
    defaults = registry.defaults

    roles = ["reasoning", "coding", "embedding", "vision"]
    role_labels = {
        "reasoning": "🧠 Reasoning",
        "coding": "💻 Coding",
        "embedding": "📐 Embedding",
        "vision": "👁️ Vision",
    }

    total_shown = 0
    for role in roles:
        models = registry.find_by_role(role)
        if min_level:
            # LEVEL_ORDER 랭킹 필터 — unknown(0)은 어떤 하한보다도 낮아 자동 제외.
            # 대시보드와 달리 CLI는 실행 중 모델 면제가 없다: 출력이 정적 스냅샷이라
            # 사용자가 명시적으로 품질 하한을 요청하면 그 기준을 유지한다.
            models = [m for m in models if LEVEL_ORDER[quant_quality(m.quantization).level] >= min_rank]
        if not models:
            continue
        total_shown += len(models)

        default_name = cast(str | None, getattr(defaults, role, None))
        label = role_labels.get(role, role)

        table = Table(title=f"{label} Models ({len(models)}개)", box=None, show_header=False)
        table.add_column("", style="dim", width=3)
        table.add_column("Name", style="cyan")
        table.add_column("Quant", width=16)
        table.add_column("Description", style="dim")

        for m in models:
            is_default = m.name == default_name
            marker = "⭐" if is_default else ""
            desc = m.description or ""
            table.add_row(marker, m.name, _quant_cell(m.quantization), desc)

        console.print(table)
        console.print()

    if min_level and total_shown == 0:
        console.print(
            f"[yellow]⚠️ 품질 '{min_level}' 이상 모델이 없습니다. 'agk model list'로 전체를 확인하세요.[/yellow]"
        )
        return

    console.print(
        Panel.fit(
            "[dim]⭐ = 현재 기본 모델\n"
            "품질 등급 (unsloth Dynamic 가이드): "
            "[green]P[/green]=프리미엄 [cyan]H[/cyan]=높음 [magenta]B[/magenta]=균형 [dark_orange]C[/dark_orange]=컴팩트 — 대시보드 Model Hub 배지와 동일\n"
            + (f"필터: '{min_level}' 이상 표시 중 ({total_shown}개)\n" if min_level else "")
            + "사용법: [bold]agk model list --min-quality balanced[/bold] — 품질 필터\n"
            "사용법: [bold]agk model set <모델명>[/bold] — 기본 모델 변경",
            border_style="dim",
        )
    )


@model_app.command("set")
def model_set(
    name: Annotated[
        str, typer.Argument(help="Set a model as default for its role (e.g. 'nvidia/nemotron-3-ultra-550b-a55b:free')")
    ],
) -> None:
    """Set a model as the default for its role in config.yaml.

    레지스트리에 등록된 모델 중 하나를 선택하여

    해당 역할(role)의 기본 모델로 설정합니다.

    config.yaml의 defaults 섹션이 업데이트되며,

    서버 재시작 시 자동으로 반영됩니다.
    """
    registry = ModelRegistry()
    _ = registry.refresh_local_models()
    model = registry.get_model(name)

    if not model:
        console.print(f"[red]❌ 모델 '{name}'을(를) 레지스트리에서 찾을 수 없습니다.[/red]")
        console.print("[yellow]📋 등록된 모델 목록은 'agk model list'로 확인하세요.[/yellow]")
        raise typer.Exit(code=1)

    # config.yaml 업데이트
    from pathlib import Path

    import yaml

    project_root = Path(__file__).resolve().parents[2]
    config_path = project_root / "config.yaml"

    if not config_path.exists():
        console.print(f"[red]❌ config.yaml 파일을 찾을 수 없습니다: {config_path}[/red]")
        raise typer.Exit(code=1)

    try:
        loaded = cast(object, yaml.safe_load(config_path.read_text(encoding="utf-8")) or {})
        raw: dict[str, object] = (
            {str(key): value for key, value in cast(Mapping[object, object], loaded).items()}
            if isinstance(loaded, dict)
            else {}
        )
    except Exception as e:
        console.print(f"[red]❌ config.yaml 파싱 실패: {e}[/red]")
        raise typer.Exit(code=1)

    role = model.role
    defaults_value = raw.get("defaults")
    defaults: dict[str, object] = (
        {str(key): value for key, value in cast(Mapping[object, object], defaults_value).items()}
        if isinstance(defaults_value, dict)
        else {}
    )
    raw["defaults"] = defaults

    old_default = defaults.get(role, "(없음)")
    defaults[role] = name

    try:
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(raw, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    except Exception as e:
        console.print(f"[red]❌ config.yaml 쓰기 실패: {e}[/red]")
        raise typer.Exit(code=1)

    console.print(f"[green]✅ 기본 {role} 모델 변경 완료[/green]")
    console.print(f"   [dim]{old_default}[/dim] → [bold cyan]{name}[/bold cyan]")
    console.print()
    console.print("[dim]💡 서버를 재시작하면 새로운 기본 모델이 적용됩니다:[/dim]")
    console.print("[dim]   agk serve --reload  (또는 서버 재시작)[/dim]")


# ─── Mode Command ──────────────────────────────────────────────────────────


@app.command()
def mode(
    target: Annotated[str, typer.Argument(help="Target mode: plan, build, interactive, or status")] = "status",
    reason: Annotated[
        str | None,
        typer.Option(
            "--reason",
            "-r",
            help="Reason for mode switch",
        ),
    ] = None,
    plan_path: Annotated[
        str | None,
        typer.Option(
            "--plan",
            "-p",
            help="Plan artifact path (for build mode)",
        ),
    ] = None,
) -> None:
    """Manage execution mode (Plan/Build/Interactive).

    Plan mode: Only read-only tools and write_artifact are allowed.
    Build mode: All tools are allowed (post-plan execution).
    Interactive: Default conversational mode.
    """
    from rich.panel import Panel

    from antigravity_k.engine.mode_manager import ModeManager

    mgr = ModeManager()
    target_lower = target.lower()

    if target_lower == "status":
        console.print(mgr.format_status())
        return

    if target_lower == "plan":
        rsn = reason or "CLI: agk mode plan"
        if mgr.switch_to_plan(rsn):
            console.print(mgr.format_status())
        else:
            console.print("[red]❌ Plan 모드 전환 실패[/red]")
        return

    if target_lower == "build":
        rsn = reason or "CLI: agk mode build"
        if plan_path:
            mgr.set_plan_artifact(plan_path)
            mgr.set_plan_quality_passed(True)
            rsn = f"Plan artifact: {plan_path}"
        if mgr.switch_to_build(plan_artifact_path=plan_path, reason=rsn):
            console.print(mgr.format_status())
        else:
            if mgr.is_plan:
                console.print(
                    Panel.fit(
                        "[yellow]❌ Build 모드 전환 실패:[/yellow]\n\nPlan → Build 자동 전환 조건이 충족되지 않았습니다.\n1. Plan 아티팩트(`implementation_plan.md`) 생성 필요\n2. Plan 품질 검증(QualityGate) 통과 필요\n3. 강제 전환: [bold]agk mode build --plan <path>[/bold]",
                        title="Build Mode",
                    ),
                )
            else:
                console.print("[red]❌ Build 모드 전환 실패[/red]")
        return

    if target_lower == "interactive":
        rsn = reason or "CLI: agk mode interactive"
        if mgr.switch_to_interactive(rsn):
            console.print(mgr.format_status())
        else:
            console.print("[red]❌ Interactive 모드 전환 실패[/red]")
        return

    console.print(f"[red]알 수 없는 모드: '{target}'[/red]")
    console.print("사용법: agk mode [plan|build|interactive|status]")


# ─── TUI Command ──────────────────────────────────────────────────────────


@app.command()
def tui(
    dev: Annotated[
        bool,
        typer.Option(
            "--dev",
            "-d",
            help="Launch with development tools enabled.",
        ),
    ] = False,
) -> None:
    """Launch the Textual Terminal UI (TUI).

    Interactive terminal interface with chat, slash commands, and system monitoring.
    """
    _ = dev
    try:
        from antigravity_k.tui import run_tui

        run_tui()
    except ImportError as e:
        console.print(f"[red]TUI dependencies not installed: {e}[/red]")
        console.print("  Install with: [yellow]pip install textual[/yellow]")
        raise typer.Exit(code=1) from e


# ─── Ask (Unified Agent) Command ────────────────────────────────────────────


@app.command()
def ask(
    task: Annotated[str, typer.Argument(help="Task or question for the unified agent.")],
    model: Annotated[str | None, typer.Option("--model", "-m", help="Override model id.")] = None,
    test: Annotated[
        str | None,
        typer.Option("--test", "-t", help="Path to a pytest file to verify code tasks (enables adaptive repair)."),
    ] = None,
    no_adaptive: Annotated[bool, typer.Option("--no-adaptive", help="Disable adaptive stability routing.")] = False,
) -> None:
    """Run the unified agent: explores code, searches web, writes/fixes code, or answers."""
    from pathlib import Path

    from antigravity_k.engine.model_manager import ModelManager
    from antigravity_k.engine.model_registry import ModelRegistry
    from antigravity_k.engine.unified_agent import UnifiedAgent

    registry = ModelRegistry()
    target_model = model or registry.defaults.reasoning or registry.defaults.coding
    if target_model is None:
        console.print("[red]No reasoning or coding model configured.[/red]")
        raise typer.Exit(code=1)
    test_code = None
    if test:
        test_path = Path(test)
        if not test_path.is_file():
            console.print(f"[red]Test file not found: {test}[/red]")
            raise typer.Exit(code=1)
        test_code = test_path.read_text(encoding="utf-8")
    agent = UnifiedAgent(ModelManager(registry).generate, target_model, project_root=Path.cwd())
    mode_tag = "adaptive" if (test_code and not no_adaptive) else "standard"
    console.print(f"[cyan]SSAK-AI unified agent[/cyan] (model={target_model}, mode={mode_tag})\n")
    outcome = agent.run(task, test_code=test_code, adaptive=bool(test_code) and not no_adaptive)
    tools = []
    if outcome.used_web:
        tools.append("web")
    if outcome.used_graphify:
        tools.append("graphify")
    if outcome.passed is not None:
        tools.append("passed" if outcome.passed else "failed")
    console.print(
        f"[dim]tools=[{','.join(tools) or '-'}] steps={len(outcome.steps)} {outcome.total_seconds:.1f}s[/dim]\n"
    )
    console.print(outcome.answer)


# ─── Market Commands ────────────────────────────────────────────────────────


def _market_search(registry: SkillMarketRegistry, market_client: SkillMarketClient, query: str) -> None:
    """Search the marketplace for skills."""
    console.print(f"[bold]🔍 Searching for '{query}'...[/bold]\n")
    results = registry.search(query)
    _ = market_client
    if results and "error" not in results[0]:
        lines = ["🔍 **Skill Marketplace 검색 결과**", ""]
        for result in results[:15]:
            name = result.get("name", "")
            version = result.get("version", "")
            description = result.get("description", "")
            lines.append(f"  📦 `{name}@{version}`")
            lines.append(f"     {str(description)[:80]}")
            lines.append("")
        console.print("\n".join(lines))
    else:
        console.print("[yellow]No results found or marketplace unreachable.[/yellow]")
        if results and "error" in results[0]:
            console.print(f"[red]  Error: {results[0].get('error', 'unknown')}[/red]")


def _market_install(registry: SkillMarketRegistry, package: str) -> None:
    """Install a skill package."""
    console.print(f"[bold]📦 Installing '{package}'...[/bold]")
    result: InstallResponse = registry.install(package)
    if result.get("success"):
        console.print(f"[green]✅ {result.get('summary', 'Install complete')}[/green]")
    else:
        console.print(f"[red]❌ Install failed: {result.get('error', 'Unknown error')}[/red]")
    warnings = result.get("warnings", [])
    if warnings:
        for w in warnings:
            console.print(f"[yellow]⚠️  {w}[/yellow]")


def _market_remove(registry: SkillMarketRegistry, name: str) -> None:
    """Remove an installed skill."""
    console.print(f"[bold]🗑️  Removing '{name}'...[/bold]")
    result: InstallResponse = registry.remove(name)
    if result.get("success"):
        console.print(f"[green]✅ {result.get('summary', 'Removed')}[/green]")
    else:
        console.print(f"[red]❌ Remove failed: {result.get('error', 'Unknown error')}[/red]")


def _market_info(registry: SkillMarketRegistry, market_client: SkillMarketClient, name: str) -> None:
    """Show detailed skill information."""
    skill_info: RegistrySkillInfo | None = registry.get_info(name)
    if skill_info:
        console.print(registry.format_info(skill_info))
        return
    # Try searching the package directly.
    if name.startswith("@antigravity-k/skill-"):
        detail: SkillDetail | None = market_client.get_detail(name)
        if detail:
            from rich.panel import Panel

            lines = [
                f"📦 **{detail.name}** `v{detail.version}`",
                "",
                f"설명: {detail.description}",
                f"키워드: {', '.join(detail.keywords)}",
                f"라이선스: {detail.license}",
                f"홈페이지: {detail.homepage}",
                f"npm: {detail.npm_url}",
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
            console.print(Panel.fit("\n".join(lines), title="Skill Detail"))
        else:
            console.print(f"[yellow]⚠️  '{name}' not found in marketplace.[/yellow]")
    else:
        console.print(f"[yellow]⚠️  Skill '{name}' is not installed.[/yellow]")
        console.print(f"   Search: [bold]agk market --search {name}[/bold]")


def _market_list(registry: SkillMarketRegistry) -> None:
    """List installed skills."""
    installed: list[RegistrySkillInfo] = registry.list_installed()
    console.print(registry.format_list(installed))


def _market_update(registry: SkillMarketRegistry, name: str) -> None:
    """Update a specific skill."""
    console.print(f"[bold]⬆️  Updating '{name}'...[/bold]")
    result: InstallResponse = registry.update(name)
    if result.get("success"):
        console.print(f"[green]✅ {result.get('summary', 'Update complete')}[/green]")
    else:
        console.print(f"[red]❌ Update failed: {result.get('error', 'Unknown error')}[/red]")


def _market_update_all(registry: SkillMarketRegistry) -> None:
    """Update all outdated skills."""
    console.print("[bold]⬆️  Checking for updates across all skills...[/bold]")
    results: list[Mapping[str, object]] = registry.update_all()
    updated = [r for r in results if r.get("success")]
    if updated:
        for r in updated:
            console.print(f"[green]  ✅ {r.get('skill_name', '?')} → {r.get('version', '?')}[/green]")
    else:
        console.print("[green]✅ All skills are up to date.[/green]")


def _market_publish_npm(skill_name: str, dry_run: bool) -> None:
    """Publish a local skill to npm."""
    console.print(f"[bold]📦 Publishing '{skill_name}' to npm...[/bold]")
    try:
        from antigravity_k.engine.skill_publisher import SkillPublisher

        publisher = SkillPublisher(project_root=".")
        result = publisher.publish_to_npm(skill_name, dry_run=dry_run)
        if result.success:
            console.print(f"[green]{result.summary()}[/green]")
        else:
            console.print(f"[red]❌ Publish failed: {'; '.join(result.errors)}[/red]")
        for w in result.warnings:
            console.print(f"[yellow]⚠️  {w}[/yellow]")
    except ImportError as e:
        console.print(f"[red]❌ Publisher not available: {e}[/red]")


def _market_publish_github(skill_name: str, repo: str, dry_run: bool) -> None:
    """Publish a local skill via GitHub PR."""
    console.print(f"[bold]🔀 Creating PR for '{skill_name}' → {repo}...[/bold]")
    try:
        from antigravity_k.engine.skill_publisher import SkillPublisher

        publisher = SkillPublisher(project_root=".")
        result = publisher.publish_to_github(skill_name, repo=repo, dry_run=dry_run)
        if result.success:
            console.print(f"[green]{result.summary()}[/green]")
            if result.pr_url:
                console.print(f"   🔗 {result.pr_url}")
        else:
            console.print(f"[red]❌ PR failed: {'; '.join(result.errors)}[/red]")
        for w in result.warnings:
            console.print(f"[yellow]⚠️  {w}[/yellow]")
    except ImportError as e:
        console.print(f"[red]❌ Publisher not available: {e}[/red]")


def _market_show_help() -> None:
    """Print the marketplace command help."""
    from rich.panel import Panel

    help_lines = [
        "[bold]Marketplace Commands[/bold]",
        "",
        "  [cyan]--search, -s[/cyan]    <query>          Search for skills",
        "  [cyan]--install, -i[/cyan]   <package>        Install a skill",
        "  [cyan]--remove, -r[/cyan]    <name>           Remove an installed skill",
        "  [cyan]--list, -l[/cyan]                        List installed skills",
        "  [cyan]--info[/cyan]          <name>           Show skill details",
        "  [cyan]--update, -u[/cyan]    <name>           Update a skill",
        "  [cyan]--update-all, -U[/cyan]                  Update all outdated skills",
        "  [cyan]--publish-npm[/cyan]   <name>           Publish local skill to npm",
        "  [cyan]--publish-github[/cyan] <name>          Publish local skill via GitHub PR",
        "  [cyan]--publish-repo[/cyan]  <org/repo>       Target repo for --publish-github",
        "  [cyan]--dry-run[/cyan]                         Validate without publishing",
        "",
        "Examples:",
        '  [dim]agk market --search "code review"[/dim]',
        "  [dim]agk market --install @antigravity-k/skill-code-review[/dim]",
        "  [dim]agk market --list[/dim]",
        "  [dim]agk market --publish-npm my-skill[/dim]",
        "  [dim]agk market --publish-npm my-skill --dry-run[/dim]",
        "  [dim]agk market --publish-github my-skill --publish-repo org/skills-repo[/dim]",
    ]
    console.print(Panel.fit("\n".join(help_lines), title="agk market"))


def market(
    search: Annotated[str | None, typer.Option("--search", "-s", help="Search for skills in the marketplace")] = None,
    install: Annotated[str | None, typer.Option("--install", "-i", help="Install a skill package")] = None,
    remove: Annotated[str | None, typer.Option("--remove", "-r", help="Remove an installed skill")] = None,
    info: Annotated[str | None, typer.Option("--info", help="Show detailed skill information")] = None,
    update: Annotated[str | None, typer.Option("--update", "-u", help="Update a specific skill")] = None,
    list_skills: Annotated[bool, typer.Option("--list", "-l", help="List installed skills")] = False,
    update_all: Annotated[bool, typer.Option("--update-all", "-U", help="Update all outdated skills")] = False,
    publish_npm: Annotated[
        str | None, typer.Option("--publish-npm", help="Publish a local skill to npm (e.g. 'code-review')")
    ] = None,
    publish_github: Annotated[
        str | None, typer.Option("--publish-github", help="Publish a local skill via GitHub PR (e.g. 'code-review')")
    ] = None,
    publish_repo: Annotated[
        str | None,
        typer.Option("--publish-repo", help="Target GitHub repo for --publish-github (e.g. 'org/skills-repo')"),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Validate without publishing")] = False,
) -> None:
    """Manage skills from the Ssak-Ai Marketplace.

    Search, install, remove, list, update, and publish skills.

    Examples:
        agk market --search "code review"
        agk market --install @antigravity-k/skill-code-review
        agk market --list
        agk market --info code-review
        agk market --remove code-review
        agk market --update code-review
        agk market --update-all
        agk market --publish-npm my-skill
        agk market --publish-npm my-skill --dry-run
        agk market --publish-github my-skill --publish-repo org/skills-repo
    """
    # ── Lazy imports ────────────────────────────────────────────────
    try:
        from antigravity_k.engine.skill_market_client import SkillMarketClient
        from antigravity_k.engine.skill_market_registry import SkillMarketRegistry
    except ImportError as e:
        console.print(f"[red]❌ Market dependencies not available: {e}[/red]")
        raise typer.Exit(code=1) from e

    market_client = SkillMarketClient()
    registry = SkillMarketRegistry(project_root=".", market_client=market_client)

    # ── Dispatch to sub-command handlers ──────────────────────────
    if search:
        _market_search(registry, market_client, search)
    elif install:
        _market_install(registry, install)
    elif remove:
        _market_remove(registry, remove)
    elif info:
        _market_info(registry, market_client, info)
    elif list_skills:
        _market_list(registry)
    elif update:
        _market_update(registry, update)
    elif update_all:
        _market_update_all(registry)
    elif publish_npm:
        _market_publish_npm(publish_npm, dry_run)
    elif publish_github:
        if not publish_repo:
            console.print("[red]❌ --publish-repo <org/repo> is required for --publish-github[/red]")
            raise typer.Exit(code=1)
        _market_publish_github(publish_github, publish_repo, dry_run)
    else:
        _market_show_help()


@app.command()
def autopilot(
    goal: Annotated[str, typer.Argument(help="High-level engineering mission to execute autonomously.")],
    max_turns: Annotated[int, typer.Option("--max-turns", "-m", help="Maximum autonomous flight turns.")] = 10,
    execute: Annotated[
        bool,
        typer.Option("--execute", help="스텝을 오케스트레이터 실행 엔진으로 실제 수행합니다 (기본: 시뮬레이션)."),
    ] = False,
) -> None:
    """Launch full autonomous self-driving flight mission for Qwen3.8-27B."""
    from antigravity_k.engine.flight_controller import AutonomousFlightController, SubgoalInput

    console.print(f"[bold cyan]🚀 Launching Autonomous Autopilot Mission:[/bold cyan] {goal}")

    controller = AutonomousFlightController(project_root=".", max_flight_turns=max_turns)

    # Initial starter subgoals inferred from goal
    subgoals: list[SubgoalInput] = [
        {"id": "plan", "desc": f"Formulate implementation plan for '{goal}'"},
        {"id": "code", "desc": "Implement required changes and patches", "depends_on": ["plan"]},
        {"id": "verify", "desc": "Run TDD tests and static audits", "depends_on": ["code"]},
    ]

    from typing import Any

    _orchestrator_cache: dict[str, Any] = {}

    def _get_orchestrator() -> Any:
        if "orch" not in _orchestrator_cache:
            from antigravity_k.api.dependencies import get_orchestrator

            _orchestrator_cache["orch"] = get_orchestrator()
        return _orchestrator_cache["orch"]

    def _execute_step(step_id: str, desc: str) -> bool:
        console.print(f"  [yellow]⚡ Step [{step_id}]:[/yellow] {desc}")
        if not execute:
            # 실행 엔진 미연결 — 시뮬레이션 스텝임을 명시한다 (항상 성공 보고로
            # 실제 수행이 일어난 것처럼 오인시키지 않는다).
            console.print("    [dim](simulation — 실행 엔진 미연결)[/dim]")
            return True
        try:
            orch = _get_orchestrator()
            output_parts: list[str] = []
            for chunk in orch.run_stream(
                [{"role": "user", "content": f"미션 스텝을 수행하세요: {desc}"}],
                target_model="default",
                max_steps=15,
            ):
                output_parts.append(str(chunk))
            # 성공 기준: 스트림이 예외 없이 완료되고 출력이 비지 않은 경우
            return bool("".join(output_parts).strip())
        except Exception as exc:
            console.print(f"    [red]스텝 실패: {exc}[/red]")
            return False

    if execute:
        console.print("[green]⚙️ 실행 모드 — 스텝을 오케스트레이터로 실제 수행합니다.[/green]")
    else:
        console.print(
            "[yellow]⚠️ Autopilot은 현재 시뮬레이션 모드입니다 — 스텝이 실제로 "
            "실행되지 않습니다. 실제 실행은 --execute 옵션을 사용하세요.[/yellow]"
        )

    report = controller.launch_mission(
        goal=goal,
        initial_subgoals=subgoals,
        step_executor=_execute_step,
    )

    if report.is_success:
        console.print(
            f"[bold green]✅ Mission '{goal}' Completed Successfully in {report.total_steps_executed} turns![/bold green]"
        )

        # ── Proactive Next-Action Recommendations (Freebuff-style) ──
        try:
            from antigravity_k.engine.flight_deck_renderer import FlightDeckRenderer
            from antigravity_k.engine.next_action_recommender import NextActionRecommender

            recommender = NextActionRecommender(project_root=".")
            rec_batch = recommender.synthesize_recommendations(
                completed_goal=goal, touched_files=["src/antigravity_k/engine/flight_controller.py"]
            )
            rec_panel = FlightDeckRenderer.render_recommendations_panel(rec_batch.format_cli_panel())
            console.print(rec_panel)
        except Exception as ex:
            console.print(f"[dim yellow]Notice: NextActionRecommender skipped ({ex})[/dim yellow]")
    else:
        console.print(f"[bold red]❌ Mission '{goal}' stopped after {report.total_steps_executed} turns.[/bold red]")


@app.command()
def fast(
    query: Annotated[str, typer.Argument(help="Deterministic query to resolve instantly (e.g. 'where is ClassName').")],
) -> None:
    """Execute direct fast-path kernel query with <5ms latency (Zero LLM overhead)."""
    from antigravity_k.engine.fast_path_kernel import FastPathKernel

    kernel = FastPathKernel(project_root=".")
    res = kernel.try_execute(query)

    if res.handled:
        console.print(res.response)
    else:
        console.print(f"[yellow]⚡ Query '{query}' requires full LLM generation loop.[/yellow]")


# ─── Error Journal Commands ───────────────────────────────────────────────


@error_app.command("list")
def list_errors(
    limit: Annotated[int, typer.Option("--limit", "-n", help="Maximum number of errors to list.")] = 20,
    component: Annotated[str | None, typer.Option("--component", "-c", help="Filter by component.")] = None,
) -> None:
    """List recent runtime errors captured in the Agent Error Journal."""
    from antigravity_k.engine.agent_error_journal import get_agent_error_journal

    journal = get_agent_error_journal()
    errors = journal.list_errors(limit=limit, component=component)

    if not errors:
        console.print("[green]✓ No runtime errors recorded in journal.[/green]")
        return

    table = Table(title=f"Runtime Errors ({len(errors)} records)")
    table.add_column("Error ID", style="bold cyan", no_wrap=True)
    table.add_column("Timestamp", style="dim")
    table.add_column("Component", style="magenta")
    table.add_column("Error Type", style="red")
    table.add_column("Location")
    table.add_column("Message")

    for err in errors:
        loc = f"{Path(err.failing_file).name}:{err.failing_line}" if err.failing_file else "N/A"
        msg = err.message.splitlines()[0][:60] if err.message else ""
        table.add_row(err.error_id, err.timestamp[:19], err.component, err.error_type, loc, msg)

    console.print(table)


@error_app.command("inspect")
def inspect_error(
    error_id: Annotated[str, typer.Argument(help="ID of the error to inspect (e.g. ERR-20260903-...)")],
) -> None:
    """Inspect detailed diagnostics and code context of a runtime error."""
    from rich.panel import Panel
    from rich.syntax import Syntax

    from antigravity_k.engine.agent_error_journal import get_agent_error_journal

    journal = get_agent_error_journal()
    err = journal.get_error(error_id)

    if not err:
        console.print(f"[red]Error ID '{error_id}' not found in journal.[/red]")
        raise typer.Exit(code=1)

    summary = (
        f"[bold red]Error Type:[/bold red] {err.error_type}\n"
        f"[bold]Message:[/bold] {err.message}\n"
        f"[bold]Component:[/bold] {err.component}\n"
        f"[bold]Timestamp:[/bold] {err.timestamp}\n"
        f"[bold]Correlation ID:[/bold] {err.correlation_id or 'N/A'}\n"
        f"[bold]Failure Point:[/bold] {err.failing_file}:{err.failing_line} ({err.failing_function})"
    )
    console.print(Panel(summary, title=f"🚨 Incident Diagnostic: {err.error_id}", expand=False))

    if err.code_context:
        console.print("\n[bold cyan]💻 Source Code Context:[/bold cyan]")
        syntax = Syntax(err.code_context, "python", theme="monokai", line_numbers=False)
        console.print(syntax)

    console.print("\n[bold cyan]📜 Stack Trace:[/bold cyan]")
    console.print(Panel(err.stack_trace.strip(), border_style="dim"))

    console.print(
        f"\n[dim]Markdown card saved at: logs/agent_diagnostics/{err.error_id}.md[/dim]\n"
        f"[dim]Run 'agk error prompt {err.error_id}' to output full AI agent fix prompt.[/dim]"
    )


@error_app.command("prompt")
def prompt_error(
    error_id: Annotated[str, typer.Argument(help="ID of the error to generate fix prompt for.")],
) -> None:
    """Output the ready-to-run AI agent fix prompt for autonomous remediation."""
    from antigravity_k.engine.agent_error_journal import get_agent_error_journal

    journal = get_agent_error_journal()
    err = journal.get_error(error_id)

    if not err:
        console.print(f"[red]Error ID '{error_id}' not found in journal.[/red]")
        raise typer.Exit(code=1)

    print(err.ai_fix_prompt)


# ─── Diagnostics Commands (Phase 4) ─────────────────────────────────────────


@diagnostics_app.command("export")
def diagnostics_export(
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="ZIP path (default: ~/Library/Logs/Ssak-Ai/diagnostics-YYYYMMDD-HHMMSS.zip on macOS).",
        ),
    ] = None,
) -> None:
    """Export an allowlist diagnostics ZIP (no secrets / .env values / vault_data)."""
    from antigravity_k.engine.diagnostics_export import export_diagnostics_zip

    try:
        zip_path = export_diagnostics_zip(output)
    except (OSError, ValueError) as err:
        console.print(f"[red]Diagnostics export failed: {err}[/red]")
        raise typer.Exit(code=1) from err

    console.print(f"[green]Diagnostics ZIP written:[/green] {zip_path}")


if __name__ == "__main__":
    app()
