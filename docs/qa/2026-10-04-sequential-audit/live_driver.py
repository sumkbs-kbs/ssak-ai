#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["uvicorn>=0.32,<1"]
# ///
# ─── How to run ───
# .venv/bin/python docs/qa/2026-10-04-sequential-audit/live_driver.py
# Uses installed repository dependencies and local Ollama. No installs.
# ──────────────────
"""Real production UI/routes/model with disposable synthetic stores and auth."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Final

HELPERS: Final = Path(__file__).resolve().parents[1] / "2026-10-04-full-live"
sys.path.insert(0, str(HELPERS))

from manual_api_fixture import isolated_home

CONFIG: Final = """model:
  main_model: qwen3.8
  code_model: qwen3.8
  vision_model: qwen3.8
  api_engine: ollama
  max_tokens: 4096
  temperature: 0.1
  complex_task_thinking: false
models:
  reasoning:
    - name: qwen3.8
      repo: qwen3.8:latest
      role: reasoning
      provider: ollama
      context_length: 262144
      estimated_memory_gb: 18
defaults:
  reasoning: qwen3.8
  coding: qwen3.8
  vision: qwen3.8
providers:
  ollama:
    base_url: http://127.0.0.1:11434
tool_loop:
  native_function_calling: true
persistent_agency:
  enabled: false
cognitive_core:
  mode: off
"""


def main() -> None:
    """Serve the real app; lifecycle background services remain explicitly off."""
    with isolated_home() as root:
        (root / "config.yaml").write_text(CONFIG, encoding="utf-8")
        project = root / "project"
        (project / "qa-source.txt").write_text("QA_MARKER=blue\nQA_VALUE=47\n", encoding="utf-8")
        (project / "docs").mkdir()
        (project / "docs" / "qa-contract.md").write_text(
            "---\ntitle: Synthetic QA contract\ntags: [qa]\n---\n"
            "Context Package v1: GOAL, CURRENT_STATE, HARD_CONSTRAINTS, "
            "CRITICAL_EVIDENCE, MATERIAL_UNKNOWNS.\n", encoding="utf-8",
        )
        os.environ["AGK_SERVER_PORT"] = "8000"
        import uvicorn

        from antigravity_k.api import dependencies
        from antigravity_k.api.auth_routes import get_token_service
        from antigravity_k.api.server import app
        from antigravity_k.engine.audit_db import init_audit_db
        from antigravity_k.engine.hook_event_bus import init_hook_event_bus
        from antigravity_k.engine.model_manager import ModelManager
        from antigravity_k.engine.model_registry import ModelRegistry
        from antigravity_k.engine.usage_tracker import UsageTracker
        from antigravity_k.engine.vault import VaultEngine

        manager = ModelManager(ModelRegistry(str(root / "config.yaml")), tracker=UsageTracker(str(root / "usage.json")))
        dependencies.model_manager = manager
        vault = VaultEngine(str(project / "vault"), sync_rag=False)
        vault.write_note("seed.md", {"title": "QA seed", "tags": ["qa"], "date": "2026-10-04"}, "QA_SEED_TEXT")
        dependencies.vault_engine = vault
        _ = init_hook_event_bus(str(root / "hook-vault"))
        _ = init_audit_db(str(root / "hook-vault"))
        header = root / "request-header"
        with os.fdopen(os.open(header, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as handle:
            handle.write("Authorization: Bearer " + get_token_service().issue_token("synthetic-qa") + "\n")
        print(f"QA_ROOT={root}", flush=True)
        print("QA_URL=http://127.0.0.1:8000; lifespan=off; model=real-local-ollama; stores=temporary", flush=True)
        uvicorn.run(app, host="127.0.0.1", port=8000, lifespan="off", access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
