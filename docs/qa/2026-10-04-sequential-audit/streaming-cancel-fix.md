# Streaming cancellation ownership — 2026-10-04

Status: worker implementation and actual production-path regressions PASS; independent final transport reviewer CLEAR / APPROVE with 32 focused cases passed and unchanged source hashes. Root's fresh browser/Qwen replay also PASS. Earlier 44-case reviewer approval predates the response-ownership extension; the new 32-case review covers it explicitly in `backend-fix-review.md` and `.omo/evidence/backend-transport-review-*.txt`.

Root's real browser QA11 cancelled after 223 displayed digits, but the saved task `direct_18f1039f992c` was `failed` with a ContextVar token reset from a different context. Evidence: `cancel-mid-token-task-before-fix.json` and `live-final-confirmed.log`. QA12 still returned 42; that followup did not prove QA11 cleaned up.

Three causes were reproduced independently. SSE policy/event tokens crossed async generator yields and could be reset from another task. Synchronous AgentRuntime iteration used a copied context for `next`, but its generator was not explicitly closed there. Starlette's real ASGI disconnect paths did not close the response body iterator, so a retained iterator left the durable task `running` after the transport exited. A response-header failure also left the session active because an unstarted generator's `aclose` cannot execute its `finally`.

The new `chat_agent_stream_generator.py` gives synchronous stream creation, each `next`, and `close` one private Context. A lock serializes them; shielded worker cleanup waits for the model pull and closes the actual runtime generator in its owner Context. This safely closes after an in-flight synchronous pull returns; it does not preempt a blocking model/network call. Its `AgentStreamingResponse` closes the async body in a shielded `stream_response` finally, including ASGI2.3 disconnect and ASGI2.4 send failures. The agent route uses this response, activates its session only when the body starts, and closes the adapter explicitly. Context reset errors are not caught or hidden. DirectTaskExecution's existing cancelled CAS now writes `task.status` atomically with `record_event=True`; its existing winner check still controls the domain event.

Production ownership: agent streaming branch of `api/routes/chat.py`, the new helper, and one cancelled-transition option in `engine/direct_task_execution.py`. No AgentRuntime, orchestrator binding, ToolLoop, citation, search, or task_runner edit was needed in this cancellation patch. The existing paused-route test helper captures the new response as well as ordinary StreamingResponse, preserving all previous boundary tests.

The tests instantiate the real FastAPI route, AgentRuntime, OrchestratorAgent graph, ToolLoop, DirectTaskExecution and SQLite store. Only the model port is replaced by deterministic/blocking generation; sockets are denied. Root's real Qwen replay is separate. Assertions retain the response iterator until after transport completion, require `cancelled`, exact partial output `42`, `error is None`, exactly one cancelled lifecycle and domain event, contiguous event sequence and terminal version, inactive/error-null session, no leaked execution/event/tool-policy context, repeat-close unchanged event ledger, and a subsequent same-conversation `done`/output42/error-null turn. A header disconnect requires no model calls or task rows.

Retained checks:

- `streaming-cancel-red.txt`: original context regression, 3 failed. Setup-only harness errors are retained separately in `streaming-cancel-setup.txt` and are not product evidence.
- `streaming-cancel-disconnect-red.txt`: real ASGI2.3/2.4, 2 failed; immediate durable status remained running while response references were retained.
- `streaming-cancel-headers-red.txt`: header-stage gap, 1 failed / 2 passed; session remained active without a model/task.
- `streaming-cancel-green.txt`: final six cancellation cases passed. Unraisable pytest warnings promoted to errors.
- `streaming-cancel-regression.txt`: 87 passed in 5.56s across eight cancellation/runtime/CAS/output/search-boundary suites. One pre-existing Starlette/httpx deprecation warning; no unraisable warning.
- `streaming-cancel-types.txt`: new helper and two regression modules, 0 errors / 0 warnings / 0 notes.
- `streaming-cancel-ruff.txt`, `streaming-cancel-format.txt`: six owned changed modules passed. `streaming-cancel-noexcuse.txt`: three new modules passed.
- `streaming-cancel-lsp.json`: fresh diagnostics for the three new modules, none found.
- `streaming-cancel-manifest.json`: exact six source/test SHA256 hashes, dependency hashes, pure LOC and artifact hashes. Root's selected source manifest must include the new helper, route and direct execution hashes.

Reproduce the worker check from Ssak-Ai:

```sh
PYTHON_DOTENV_DISABLED=1 .venv/bin/python docs/qa/2026-10-03-oh-my-jev-upgrade/isolated_entry.py pytest tests/test_chat_stream_cancel_cleanup.py tests/test_chat_stream_disconnect_cleanup.py tests/test_chat_stream_output_boundary.py tests/test_chat_search_boundary.py tests/test_agent_runtime.py tests/test_direct_stream_channels.py tests/test_dat01_task_transition_cas.py tests/test_real_runtime_task_events.py -q --tb=short -W error::pytest.PytestUnraisableExceptionWarning
```

No server/Ollama action, dependency install, credential output, temporary instrumentation, real user-store/config write, commit or push occurred in this worker lane. The isolated entry removes its temporary home; pytest owns the standard per-test tmp_path retention. Its fixtures restore home/cwd/config and socket patches. Permanent failure injection exists only in regression fixtures.

Root independently restarted the actual production UI with real local Qwen. After receiving numbered output, Root clicked Stop and observed the toast, preserved partial output and restored input. Task `direct_51ff7d4d8990` persisted cancelled/error-null/version3, exactly one cancelled terminal event and one interactive-cancelled event; task event sequences are contiguous. The same conversation's next turn returned exactly42 and persisted done/error-null. No tool/search activity appeared in either turn. The server log has zero different-Context, ignored-generator or unhandled-task cleanup errors. Actual-model receipts: [durable check](cancel-final-durable.json), [events](cancel-final-events.json), [stop state](cancel-final-after.jpg), [followup](cancel-final-followup.jpg), [source snapshot](source-citation-diagnostic-before.json). These receipts are separate from synthetic generation-port tests; safe cleanup does not preempt a blocking model pull.
