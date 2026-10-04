# Explicit search request contract

Parent-supplied base/candidate HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`. This report verifies the current shared working tree, not a newly created commit. No Git operations were performed.

## Confirmed production path

ChatPage sends `new_turn`, `use_conversation_store`, conversation revision and the `web_search` toggle. `chat.py:767` disables legacy fast search for the revision protocol. Search ON makes the safe search tool available through request policy; it did not establish a required tool contract. DirectTaskExecution only recognized literal registry tool names, so `웹 검색으로 확인` and `search the web` did not produce checkpoint `expected_tools`. ToolLoop accepted a final answer without a search call. Citation checks only apply after citation-bearing tool evidence exists.

Legacy fast-search WebSearchTool execution is outside the ToolLoop receipt path but is unreachable for this revision request. AUTO_LEARN can search outside the receipt path, but its static learning predicate does not match the exact R2-12 prompt (one trigger, no full URL). Memory prefetch, context enrichment, and preflight do not issue web search here. This static trace and root-provided metadata support **search unverified** for R2-12; they are not a global proof of absent HTTP traffic.

## Change and controlled runtime proof

- Natural explicit Korean/English search requests now bind registered, request-allowed `web_search` into the existing durable expected-tools contract. Search OFF, quoted/code material, negation, optional search and mere availability do not bind it. Named non-search tool behavior is preserved. This is a bounded explicit-request heuristic, not a general natural-language parser.
- The production missing-required-tool guard previously marked failure while retaining an unverified answer as durable output and leaving `last_output` empty. The controlled runtime test reproduced that defect after contract binding. It now records a truthful failure as canonical output, and the existing production streaming boundary emits its FinalChunk.
- Tests run actual `orchestrator.stream.run_stream` → `ToolLoopEngine` → task checkpoint/state/citation checks → canonical FinalChunk. Only model generation and search execution are controlled adapters. A search call records its name and query before returning synthetic official-document evidence. A model that skips search receives no adapter receipt, failed task status and a truthful replacement final. FinalChunk equals durable task output in both cases.

## Evidence

- `search-request-contract-red.txt`: original source, 10 failed / 12 passed. Natural request recognition, quote exclusion, denial and durable contract tests exposed the bug.
- `search-request-contract-guard-red.txt`: after parser change, 1 failed / 32 passed. The sole failure showed unverified draft persisted despite `required_tools_missing`.
- `search-request-contract-green.txt`: final 46 focused tests passed, including the actual production stream and controlled search receipt scenarios.
- `search-request-contract-regression.txt`: final 189 tests passed across focused contract tests, AgentRuntime, ToolLoop and request-preservation tests; one existing unawaited MCPToolLoader coroutine warning in the AgentRuntime fixture.
- `search-request-contract-types.txt`: 0 errors / 0 warnings / 0 notes for both changed source modules and new tests.
- Ruff check and format check passed on all three files.

Isolation was established before application imports: synthetic Path.home/expanduser, cwd, AGK/config/data/task/vault paths and environment, preserving HOME/CODEX_HOME. Every Python socket connect was blocked. No real model, provider, network request, private home/SQLite/log/auth reads or Git operations were performed. Temporary TaskStateStore databases were newly created synthetic test fixtures.

The existing expected-tools guard counts parsed `used_tools` names before executor completion; successful provider-result provenance remains a separate citation/quality boundary. This patch proves the no-call bypass is prevented, not that every attempted search succeeded.

Root owns the actual Search ON R2-12 browser/model retest after restart. That live result is not yet verified by this report.

## Current file SHA-256

- `src/antigravity_k/engine/direct_task_execution.py`: `a0c186aedfe53a8b2c1ed4f95ee6a3807cf5823860e83f4f9fa752abd004f1f7`
- `src/antigravity_k/engine/tool_loop.py`: `bfe26cc91815554a19796312cc60eae9103765517d49dc2509f0dc575222f8bf`
- `tests/test_search_request_contract.py`: `f52b1351dfacf2ec4df9b4b96d5538372e887293ed9694d5ed674e39e3712d35`


The later citation source-link change supersedes the ToolLoop/test fingerprints below; its final fingerprints and combined 243-test verification are in `citation-source-links-report.md`. The explicit-search contract production implementation is unchanged.
