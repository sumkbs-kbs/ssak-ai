"""Registered local-only live experiment entry point."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path
from tempfile import mkdtemp

import httpx
from pydantic import ValidationError

from antigravity_k.engine.cognitive.growth import MechanismSet, RunKind, default_corpus_tasks, default_spec
from antigravity_k.engine.cognitive.learning import LearningContractError
from antigravity_k.engine.cognitive.live_pilot import (
    LivePilotHarness,
    LivePilotPlan,
    LivePilotStatus,
    LiveTrialTimeout,
    freeze_registered_manifest,
    run_registered_live_experiment,
)
from antigravity_k.engine.cognitive.live_trial_adapter import LiveTrialAdapter
from antigravity_k.engine.growth_fixture_tools import fixture_tool_port
from antigravity_k.engine.local_live_model import LocalModelError, LocalOllamaModelPort


def run_local_registered(output: Path | None, store_root: Path | None) -> int:
    """Freeze before TRAIN, preserve actual failures, then execute 18 x 3 x 2 FINAL trials."""
    root = (store_root or Path(mkdtemp(prefix="ssak-local-live-"))).resolve()
    root.mkdir(parents=True, exist_ok=True)
    output = output or root / "registered-result.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        model = LocalOllamaModelPort(os.environ.get("SSAK_LIVE_MODEL", "qwen3.8:latest"), root / "model-trace.jsonl")
    except (httpx.HTTPError, ValidationError, LocalModelError) as error:
        output.write_text(json.dumps({"status": "NOT_RUN", "reason": str(error), "mixed_with_fixture": False}) + "\n")
        return 2
    tasks = default_corpus_tasks()
    spec = default_spec(experiment_id="growth-real-local-v7", run_kind=RunKind.LIVE_PILOT)
    engine = Path(__file__).parent
    # Pin the whole first-party package, including modules loaded lazily by tool dispatch.
    sources = sorted(engine.parent.rglob("*.py"))
    source_hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(set(sources))}
    fingerprint = hashlib.sha256(json.dumps(source_hashes, sort_keys=True).encode()).hexdigest()
    (root / "source-hashes.json").write_text(json.dumps(source_hashes, indent=2) + "\n")
    plan = LivePilotPlan(
        code_fingerprint=fingerprint, trials_per_task=3, seed=20260927, budget_calls=216, budget_tokens=9000000
    )
    frozen = freeze_registered_manifest(
        spec=spec, plan=plan, tasks=tasks, mechanisms=MechanismSet(), attestation=model.attestation
    )
    manifest_path = root / "registered-manifest.json"
    with manifest_path.open("x", encoding="utf-8") as handle:
        json.dump(frozen.as_mapping(), handle, indent=2)
    transport_limits = {
        "model_input_utf8_bytes": 32768,
        "num_ctx": 40960,
        "output_tokens_per_call": 512,
        "protocol_token_reserve": 2048,
        "train_validation_max_calls": 2 * sum(task.split.value in {"TRAIN", "VALIDATION"} for task in tasks),
        "train_validation_max_tokens": 40960 * 2 * sum(task.split.value in {"TRAIN", "VALIDATION"} for task in tasks),
        "final_max_calls": plan.budget_calls,
        "final_max_tokens": plan.budget_tokens,
        "scope": "TRAIN/VALIDATION bounds are separate from FINAL harness budget; both arms share transport limits",
    }
    with (root / "transport-limits.json").open("x", encoding="utf-8") as handle:
        json.dump(transport_limits, handle, indent=2)
    adapter = LiveTrialAdapter(root / "workspace", model, executor_factory=fixture_tool_port)
    try:
        gate = adapter.run_train_validation()
    except (
        httpx.HTTPError,
        ValidationError,
        LocalModelError,
        LearningContractError,
        LiveTrialTimeout,
        ValueError,
    ) as error:
        output.write_text(
            json.dumps(
                {
                    "status": "NOT_COMPLETE",
                    "phase": "TRAIN_VALIDATION",
                    "reason": str(error),
                    "manifest": frozen.as_mapping(),
                    "model_trace": str(model.trace_path),
                },
                indent=2,
            )
            + "\n"
        )
        return 2
    result = run_registered_live_experiment(LivePilotHarness(spec, plan, tasks=tasks), adapter)
    payload = dict(result.as_mapping())
    payload["training_validation"] = asdict(gate)
    payload["experiment_limits"] = [
        "Real local inference on a synthetic append corpus, not a general intelligence demonstration",
        "Operator-prespecified context-depth hypothesis evaluated against separate validation tasks",
    ]
    payload["model_trace"] = str(model.trace_path)
    output.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"wrote {output}")
    if result.report.status is not LivePilotStatus.COMPLETED or result.ledger_gaps:
        return 2
    return 0 if result.report.verdict and result.report.verdict.passed else 1
