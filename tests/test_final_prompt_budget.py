"""CTX-02: final serialized prompt budget and deterministic compression."""

from __future__ import annotations

import json

import pytest
from pydantic import JsonValue

from antigravity_k.engine.context_budget import (
    PromptBudgetExceededError,
    build_prompt_component_ledger,
    prompt_selection_digest,
    resolve_hard_token_limit,
)
from antigravity_k.engine.context_budget_enforcer import FinalPromptFit, fit_final_prompt, serialize_final_prompt
from antigravity_k.engine.tokenizer import TokenEstimator


def _config(*, context_length: int = 8_192, operator: int | None = 1_000) -> dict[str, JsonValue]:
    router: dict[str, JsonValue] = {}
    if operator is not None:
        router["context_token_limit"] = operator
    return {
        "defaults": {"reasoning": "qwen3.6:latest"},
        "models": {
            "reasoning": [
                {
                    "name": "qwen3.6:latest",
                    "context_length": context_length,
                },
            ],
        },
        "router": router,
    }


def test_ledger_counts_all_final_prompt_components() -> None:
    messages = [{"role": "user", "content": "a" * 18}]  # 5 tokens
    aux = "x" * 4018  # 1005 tokens
    ledger = build_prompt_component_ledger(
        system=aux[:2000],
        tools=aux[2000:3000],
        skills=aux[3000:3500],
        memory=aux[3500:3800],
        artifacts=aux[3800:],
        messages=messages,
        output_reserve=128,
    )
    assert ledger.system > 0
    assert ledger.tools > 0
    assert ledger.skills > 0
    assert ledger.memory > 0
    assert ledger.artifacts > 0
    assert ledger.messages == 5
    assert ledger.output_reserve == 128
    assert (
        ledger.input_total
        == ledger.system + ledger.tools + ledger.skills + ledger.memory + ledger.artifacts + ledger.messages
    )
    assert ledger.total_with_reserve == ledger.input_total + 128


def test_five_token_message_with_1005_system_tokens_fails_under_operator_limit() -> None:
    hard = resolve_hard_token_limit(_config(operator=1_000), "qwen3.6:latest")
    assert hard.input_budget == 1_000
    assert hard.operator == 1_000

    message = "a" * 18
    assert TokenEstimator.estimate_text(message) == 5
    aux = "x" * 4018
    assert TokenEstimator.estimate_text(aux) == 1005

    with pytest.raises(PromptBudgetExceededError) as raised:
        fit_final_prompt(
            system=aux,
            tools="",
            skills="",
            memory="",
            artifacts="",
            messages=[{"role": "user", "content": message}],
            hard_limit=hard,
        )
    assert raised.value.hard_limit == hard
    assert raised.value.ledger.system == 1005
    assert raised.value.ledger.input_total > hard.input_budget


def test_prompt_selection_digest_is_deterministic() -> None:
    messages = [{"role": "user", "content": "goal"}, {"role": "assistant", "content": "ok"}]
    first = prompt_selection_digest(system="sys", tools="tools", skills="sk", memory="mem", messages=messages)
    second = prompt_selection_digest(system="sys", tools="tools", skills="sk", memory="mem", messages=messages)
    assert first == second
    assert len(first) == 64
    third = prompt_selection_digest(system="sys2", tools="tools", skills="sk", memory="mem", messages=messages)
    assert first != third


def test_fit_preserves_prompt_cache_prefix_when_only_suffix_shrinks() -> None:
    hard = resolve_hard_token_limit(_config(operator=400), "qwen3.6:latest")
    system = "STABLE_SYSTEM_PREFIX_BYTES"
    tools = "STABLE_TOOL_GUIDE"
    skills = ""
    memory = "x" * 2000
    messages = [
        {"role": "user", "content": "BEGIN_CONSTRAINT keep-me END_CONSTRAINT"},
        {"role": "assistant", "content": "old " * 200},
    ]
    _, original_prefix = serialize_final_prompt(
        system=system,
        tools=tools,
        skills=skills,
        messages=messages,
        memory=memory,
    )
    fit = fit_final_prompt(
        system=system,
        tools=tools,
        skills=skills,
        memory=memory,
        messages=messages,
        hard_limit=hard,
    )
    assert fit.cache_prefix == original_prefix
    assert fit.serialized.startswith(original_prefix)
    assert "BEGIN_CONSTRAINT" in fit.serialized
    assert "END_CONSTRAINT" in fit.serialized
    assert TokenEstimator.estimate_text(fit.serialized) <= hard.input_budget


def test_structured_tool_evidence_survives_final_fit() -> None:
    hard = resolve_hard_token_limit(_config(operator=250), "qwen3.6:latest")
    evidence = (
        '<tool_response>\n[TOOL_EVIDENCE] {"tool":"run_bash_command","source":"verify.py"}\n'
        + "[UNTRUSTED_TOOL_RESULT]\n"
        + ("noise " * 400)
        + "\nVERIFIED_RESULT=5050\n[/UNTRUSTED_TOOL_RESULT]\n</tool_response>"
    )
    fit = fit_final_prompt(
        system="sys",
        tools="",
        skills="",
        messages=[
            {"role": "tool", "content": evidence},
            {"role": "user", "content": "use the verified result"},
        ],
        hard_limit=hard,
    )
    blob = "\n".join(message["content"] for message in fit.messages)
    assert "[TOOL_EVIDENCE]" in blob
    assert "VERIFIED_RESULT=5050" in blob
    assert fit.ledger.input_total <= hard.input_budget


def test_oversized_essential_components_raise_typed_error_without_partial_policies() -> None:
    hard = resolve_hard_token_limit(_config(operator=80), "qwen3.6:latest")
    huge = "Z" * 50_000
    with pytest.raises(PromptBudgetExceededError) as raised:
        fit_final_prompt(
            system=huge,
            tools="",
            skills="",
            messages=[{"role": "user", "content": "hi"}],
            hard_limit=hard,
            allow_typed_error=True,
        )
    assert raised.value.ledger.system == TokenEstimator.estimate_text(huge)
    assert raised.value.ledger.total_with_reserve > hard.effective

    with pytest.raises(PromptBudgetExceededError) as multi:
        fit_final_prompt(
            system=huge,
            tools=huge,
            skills=huge,
            memory=huge,
            artifacts=huge,
            messages=[{"role": "user", "content": huge}],
            hard_limit=hard,
            allow_typed_error=True,
        )
    assert multi.value.ledger.system == TokenEstimator.estimate_text(huge)
    assert multi.value.ledger.tools == TokenEstimator.estimate_text(huge)
    assert multi.value.ledger.messages >= TokenEstimator.estimate_text(huge)
    assert multi.value.ledger.total_with_reserve > hard.effective


def test_hard_limit_is_min_of_declared_empirical_operator(tmp_path) -> None:
    artifact = tmp_path / "mem.json"
    artifact.write_text(
        json.dumps(
            {
                "artifact_type": "model_memory_calibration",
                "schema_version": 1,
                "model": "qwen3.6:latest",
                "backend": "ollama",
                "source_sha256": "a" * 64,
                "headroom_ratio": 0.25,
                "measurements": [
                    {
                        "context_tokens": 1024,
                        "kv_cache_bytes": 1_000,
                        "peak_memory_bytes": 2_000,
                        "outcome": "success",
                    },
                    {
                        "context_tokens": 2048,
                        "kv_cache_bytes": 2_000,
                        "peak_memory_bytes": 3_000,
                        "outcome": "success",
                    },
                    {
                        "context_tokens": 4096,
                        "kv_cache_bytes": 4_000,
                        "peak_memory_bytes": 5_000,
                        "outcome": "oom",
                    },
                ],
            },
        ),
        encoding="utf-8",
    )
    config = _config(context_length=32_768, operator=2_000)
    config["router"] = {
        "context_token_limit": 2_000,
        "memory_calibration_artifact_paths": [str(artifact)],
    }
    hard = resolve_hard_token_limit(config, "qwen3.6:latest")
    assert hard.operator == 2_000
    assert hard.empirical is not None
    # input_budget is min(declared_input, empirical, operator, MAX)
    assert hard.input_budget == min(hard.empirical, hard.operator)
    assert hard.input_budget <= 2_000


def test_identical_inputs_yield_identical_fit_digest() -> None:
    hard = resolve_hard_token_limit(_config(operator=500), "qwen3.6:latest")

    def fit_once() -> FinalPromptFit:
        return fit_final_prompt(
            system="sys " * 50,
            tools="tool " * 40,
            skills="skill " * 30,
            memory="mem " * 80,
            messages=[
                {"role": "user", "content": "BEGIN " + ("detail " * 100) + " END"},
                {"role": "assistant", "content": "ack " * 60},
            ],
            hard_limit=hard,
        )

    first = fit_once()
    second = fit_once()
    assert first.digest == second.digest
    assert first.serialized == second.serialized
    assert first.ledger.as_dict() == second.ledger.as_dict()
