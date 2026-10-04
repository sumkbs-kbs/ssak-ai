"""Credential and shell contracts for copy-only agent bridge plans."""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import tomllib
from pathlib import Path
from typing import Final

import pytest

TOKEN_REFERENCE: Final[str] = "${SSAK_ACCESS_TOKEN:?set a token issued by /api/auth/login}"
AGENTS: Final[tuple[str, ...]] = ("claude", "codex", "opencode", "openclaw", "hermes")


@pytest.fixture(autouse=True)
def isolate_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch home before any product import without replacing HOME or CODEX_HOME."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)


def _bash_blocks(plan: str) -> list[str]:
    return re.findall(r"```bash\n(.*?)\n```", plan, re.DOTALL)


def _shell_environment(token: str | None = None) -> dict[str, str]:
    """Preserve system home variables and supply only a synthetic test token."""
    environment = {key: os.environ[key] for key in ("HOME", "CODEX_HOME") if key in os.environ}
    if token is not None:
        environment["SSAK_ACCESS_TOKEN"] = token
    return environment


@pytest.mark.parametrize("agent", AGENTS)
def test_bridge_uses_named_token_reference_without_reading_credentials(
    agent: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from antigravity_k.engine.agent_bridges import format_bridge_plan, resolve_bridge

    synthetic_token = "qa-synthetic-token-do-not-print"
    monkeypatch.setenv("SSAK_ACCESS_TOKEN", synthetic_token)
    spec, env = resolve_bridge(agent, model="qa-model", api_base="http://127.0.0.1:9")
    credential_key = "ANTHROPIC_AUTH_TOKEN" if spec.protocol == "anthropic" else "OPENAI_API_KEY"
    assert env[credential_key] == TOKEN_REFERENCE
    assert "ANTHROPIC_API_KEY" not in env
    plan = format_bridge_plan(spec, env)
    assert f'export {credential_key}="{TOKEN_REFERENCE}"' in plan
    assert synthetic_token not in plan
    assert "ssak-ai-local" not in plan


@pytest.mark.parametrize("agent", AGENTS)
def test_configuration_requires_token_when_user_later_runs_exports(agent: str) -> None:
    from antigravity_k.engine.agent_bridges import format_bridge_plan, resolve_bridge

    spec, env = resolve_bridge(agent, model="qa-model", api_base="http://127.0.0.1:9")
    config = _bash_blocks(format_bridge_plan(spec, env))[0]
    result = subprocess.run(
        ["/bin/sh", "-c", config],
        env=_shell_environment(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "SSAK_ACCESS_TOKEN" in result.stderr
    assert "/api/auth/login" in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize("agent", AGENTS)
def test_configuration_passes_synthetic_token_in_environment_only(agent: str) -> None:
    from antigravity_k.engine.agent_bridges import format_bridge_plan, resolve_bridge

    spec, env = resolve_bridge(agent, model="qa-model", api_base="http://127.0.0.1:9")
    credential_key = "ANTHROPIC_AUTH_TOKEN" if spec.protocol == "anthropic" else "OPENAI_API_KEY"
    config = _bash_blocks(format_bridge_plan(spec, env))[0]
    environment = _shell_environment("qa-synthetic-only")
    environment["ANTHROPIC_API_KEY"] = "qa-stale-key"
    check = f'test "${credential_key}" = "$SSAK_ACCESS_TOKEN"'
    if spec.protocol == "anthropic":
        check += '\ntest -z "${ANTHROPIC_API_KEY+x}"'
    result = subprocess.run(
        ["/bin/sh", "-c", f"{config}\n{check}"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == result.stderr == ""


def test_renderer_never_embeds_supplied_credential_value() -> None:
    from antigravity_k.engine.agent_bridges import format_bridge_plan, resolve_bridge

    spec, env = resolve_bridge("codex", model="qa-model")
    env["OPENAI_API_KEY"] = "qa-synthetic-mapping-token"
    assert "qa-synthetic-mapping-token" not in format_bridge_plan(spec, env)


def test_shell_metacharacters_in_model_remain_literal(tmp_path: Path) -> None:
    from antigravity_k.engine.agent_bridges import format_bridge_plan, resolve_bridge

    marker = tmp_path / "unexpected-shell-command"
    model = f"qa; /usr/bin/touch {marker}; #"
    spec, env = resolve_bridge("codex", model=model)
    config = _bash_blocks(format_bridge_plan(spec, env))[0]
    result = subprocess.run(
        ["/bin/sh", "-c", f'{config}\nprintf "%s" "$AGK_BRIDGE_MODEL"'],
        env=_shell_environment("qa-synthetic-only"),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == model
    assert not marker.exists()


def test_codex_command_has_resolved_base_and_quoted_model() -> None:
    from antigravity_k.engine.agent_bridges import format_bridge_plan, resolve_bridge

    model = 'qa model; $(printf injected) "quoted"'
    base = 'http://127.0.0.1:9/path"quoted/😀'
    spec, env = resolve_bridge("codex", model=model, api_base=base)
    plan = format_bridge_plan(spec, env)
    command = _bash_blocks(plan)[1].replace("\\\n", "")
    argv = shlex.split(command)
    assert argv[:2] == ["codex", "exec"]
    assert argv[argv.index("-m") + 1] == model
    settings = [argv[index + 1] for index, value in enumerate(argv[:-1]) if value == "-c"]
    base_setting = f"model_providers.ssak.base_url={json.dumps(base + '/v1', ensure_ascii=False)}"
    assert base_setting in settings
    assert tomllib.loads(base_setting) == {"model_providers": {"ssak": {"base_url": base + "/v1"}}}
    assert 'model_providers.ssak.env_key="OPENAI_API_KEY"' in settings
    assert "<BASE_URL>" not in plan
    assert "/v1/responses" in plan


def test_anthropic_base_strips_v1_suffix() -> None:
    from antigravity_k.engine.agent_bridges import resolve_bridge

    _, env = resolve_bridge("claude", model="qa-model", api_base="http://127.0.0.1:9/v1/")
    assert env["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:9"


def test_claude_model_picker_remains_valid_json() -> None:
    from antigravity_k.engine.agent_bridges import format_bridge_plan, resolve_bridge

    model = 'qa-"model\\name'
    spec, env = resolve_bridge("claude", model=model)
    plan = format_bridge_plan(spec, env)
    match = re.search(r"```json\n(.*?)\n```", plan, re.DOTALL)
    assert match is not None
    assert json.loads(match.group(1)) == {
        "modelPicker": {"options": [{"model": model, "behavesAs": "claude-sonnet-4-6"}]},
    }
