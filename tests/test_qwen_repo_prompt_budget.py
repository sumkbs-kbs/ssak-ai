"""Regression coverage for registered model repo prompt ceilings."""

from __future__ import annotations

import json
from collections.abc import MutableMapping
from pathlib import Path

import pytest
from pydantic import JsonValue

from antigravity_k.engine.context_budget import PromptBudgetExceededError, resolve_hard_token_limit
from antigravity_k.engine.context_budget_enforcer import fit_final_prompt


@pytest.fixture
def qwen_repo_config() -> MutableMapping[str, JsonValue]:
    # Given: the current bundled Qwen profile has a distinct name and repo.
    return {
        "models": {"reasoning": [{"name": "qwen3.8", "repo": "qwen3.8:latest", "context_length": 262_144}]},
        "router": {},
    }


def test_read_result_fits_when_live_delegate_uses_registered_qwen_repo(
    qwen_repo_config: MutableMapping[str, JsonValue],
) -> None:
    from pydantic import BaseModel, ConfigDict

    class ReadPromptFixture(BaseModel):
        model_config = ConfigDict(frozen=True)
        system: str
        tools: str
        skills: str
        messages: list[dict[str, str]]

    # Given: actual source prompt contracts, built-in schemas, source document,
    # request preservation and sanitized read-file result composition.
    fixture_path = Path(__file__).resolve().parents[1] / "docs/qa/2026-10-04-full-live/budget-r2-05-prompt-fixture.json"
    fixture = ReadPromptFixture.model_validate_json(fixture_path.read_text(encoding="utf-8"))
    hard = resolve_hard_token_limit(qwen_repo_config, "qwen3.8:latest")

    # When: the production final gate retains the latest file-read result.
    fit = fit_final_prompt(**fixture.model_dump(), hard_limit=hard)

    # Then: the complete mandatory payload is admitted under the real window.
    assert not fit.compressed
    assert fit.ledger.input_total <= hard.input_budget
    assert fit.ledger.total_with_reserve <= 32_768


def test_qwen_repo_limit_reserves_completion_inside_provider_window(
    qwen_repo_config: MutableMapping[str, JsonValue],
) -> None:
    # Given: the provider caps the loaded profile at a 32,768-token window.
    # When: resolving a final input ceiling through its repo identifier.
    hard = resolve_hard_token_limit(qwen_repo_config, "qwen3.8:latest")

    # Then: completion space stays inside that same provider window.
    assert hard.declared == 262_144
    assert hard.input_budget == 28_672
    assert hard.effective == 32_768


def test_explicit_operator_limit_still_halts_required_read_payload(
    qwen_repo_config: MutableMapping[str, JsonValue],
) -> None:
    # Given: the same realistic read payload with a deliberate operator ceiling.
    fixture = json.loads(
        (
            Path(__file__).resolve().parents[1] / "docs/qa/2026-10-04-full-live/budget-r2-05-prompt-fixture.json"
        ).read_text(encoding="utf-8"),
    )
    qwen_repo_config["router"] = {"context_token_limit": 8_000}
    hard = resolve_hard_token_limit(qwen_repo_config, "qwen3.8:latest")

    # When / Then: required components cannot fit, so no partial policy is returned.
    with pytest.raises(PromptBudgetExceededError):
        fit_final_prompt(**fixture, hard_limit=hard)
    assert hard.operator == 8_000
    assert hard.input_budget == 8_000


@pytest.mark.parametrize("delegate", ["qwen3.8", "qwen3.8:latest"])
@pytest.mark.parametrize("artifact_model", ["qwen3.8", "qwen3.8:latest"])
def test_alias_cannot_bypass_empirical_model_ceiling(
    tmp_path: Path,
    qwen_repo_config: MutableMapping[str, JsonValue],
    delegate: str,
    artifact_model: str,
) -> None:
    # Given: a lower measured budget for the same registered profile identity.
    artifact = tmp_path / "measured-memory.json"
    artifact.write_text(
        json.dumps(
            {
                "artifact_type": "model_memory_calibration",
                "schema_version": 1,
                "model": artifact_model,
                "backend": "ollama",
                "source_sha256": "a" * 64,
                "headroom_ratio": 0.25,
                "measurements": [
                    {"context_tokens": 8_000, "kv_cache_bytes": 1_000, "peak_memory_bytes": 2_000, "outcome": "success"}
                ],
            }
        ),
        encoding="utf-8",
    )
    qwen_repo_config["router"] = {"memory_calibration_artifact_paths": [str(artifact)]}

    # When: resolving either registered identifier.
    hard = resolve_hard_token_limit(qwen_repo_config, delegate)

    # Then: no alias can escape the measured ceiling.
    assert hard.empirical == 6_000
    assert hard.input_budget == 6_000


def test_required_payload_cannot_consume_provider_completion_reserve(
    qwen_repo_config: MutableMapping[str, JsonValue],
) -> None:
    # Given: a mandatory system body at the former 32,768 input ceiling.
    hard = resolve_hard_token_limit(qwen_repo_config, "qwen3.8")

    # When / Then: the input must leave room for the provider's completion.
    with pytest.raises(PromptBudgetExceededError):
        fit_final_prompt(
            system="X" * (32_000 * 4),
            tools="",
            skills="",
            messages=[{"role": "user", "content": "go"}],
            hard_limit=hard,
        )
