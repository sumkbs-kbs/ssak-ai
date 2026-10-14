# IMP20 revision v2: remove prompt prose pin

Changed only candidate tests/test_execution_request_preservation.py. The appended guard now asserts role=system and the routing marker at the beginning; exactly-one guard and captured-model-prompt propagation assertions remain. Original user content, image/MIME, feedback and exact history checks are unchanged. This is an assertion contract correction, not a product change. v1 preimage/postimage evidence is preserved.

Exact invocation: ROOT/.venv/bin/python RUN/revision-v2/run_checks.py postimage. Child argv, exit codes and elapsed times: postimage/checks.json. Source digest/HEAD: postimage/source-binding.json. Exact case list and binary results: scenario-results.json and postimage/junit.xml. Delta from v1: delta.patch; complete execution-request patch from HEAD: candidate.patch.

Scenarios: initial request retention for agent/MAX fallback/MAX error fallback (3); retry feedback/history retention for agent/MAX fallback (2); unchanged original with no auxiliary context (1); existing test_no_files_prevents_artifact_write_and_unsolicited_approval (4 combinations). Total 10 passed, 5 deselected. The 4 denial cases observe zero executor calls, no artifact directory, no approval, completed chat output and only permitted read/command schemas. They supply actual deny behavior rather than pinning the English instruction sentence.

Ruff check, Ruff format --check and git diff --check all exit 0. The programming skill's additional no-excuse audit exits 1 for two pre-existing generic exceptions on lines 30 and 64. preimage-audit.json reproduces the same two findings in the v1 saved file; no new audit findings. No suppression or unrelated fixture refactor was introduced.

Scope limits: purge and compaction files were not edited or rerun in v2; their v1 results remain separately recorded. No HTTP/full-suite/live-model/network result is claimed. MAX fallback retry still uses its pre-existing exact-history assertion; the missing evaluation_user_task guard behavior is not silently asserted or fixed. No product-source or ROOT user-file changes, staging or commits.

Review: the helper owns conversation-boundary extraction and is reused; no new parsing boundary, variant branch, escape hatch, defensive layer, parameters, resources or logging was added. Verification checks guard structure/propagation plus existing deny behavior, not prompt prose.
