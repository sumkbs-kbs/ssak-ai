# Bounded static startup-path audit

READ_ONLY; no process/import/model/network execution. Current worktree source SHA is bound in source-binding.json; concurrent product fixes can change it. This is not exhaustive dynamic startup proof.

Observed failed chain: api/server.py -> routes/agency_api.py -> dependencies.py -> orchestrator/agent.py -> engine_context.py -> cognitive_loop.py -> failure_memory.py -> gbrain.py global_gbrain = GBrain(). Original guard denied ~/.antigravity/gbrain before bind; raw v2 artifacts remain unchanged.

## Additional blocking defaults
- Health -> get_orchestrator -> _build_project_runtime -> build_project_memory_manager -> GlobalMemoryProvider() (project_runtime.py:96). global_memory_provider.py:38-41 chooses ~/.antigravity-k/memory, mkdir eagerly; only explicit memory_dir parameter currently supported, no env override. The injected manager means EngineContext skips its separate default global-memory ctor, but does not avoid this factory call.
- _build_project_runtime -> OrchestratorAgent -> EngineContext -> ContextShaper() (engine_context.py:205). context_shaper.py:86-91 chooses ~/.antigravity/context_store and mkdir eagerly; only explicit storage_dir parameter currently supported, no env override.
- These are statically reachable on planned health/runtime path, not observed failures in the single v2 attempt. No additional live attempt authorized.

## Existing isolation paths and remaining bounds
- FailureMemory receives project_root in EngineContext; relative .antigravity/failure_log.jsonl stays under owned project. No separate env needed for this route.
- Project SessionManager receives project_sessions_dir(project_root), avoiding home default. Legacy SessionManager() still uses ~/.antigravity/sessions; not asserted safe for unrelated paths.
- ConversationStore supports AGK_CONVERSATION_STORE_DIR; current preparation does not set it. Lazy singleton creation is not proven reached by these four requests. Adding an owned override is available without HOME rewrite if parent approves.
- BackgroundTaskRunner supports AGK_TASK_DB_PATH; otherwise config.paths.data_dir (already AGK_PATH_DATA_DIR owned), then home only on OSError. TaskStateStore/PersistentAgencyStore/ScheduledJobStore also have home fallback on directory failure; guard must remain enabled rather than suppressing errors.
- Benchmark supports AGK_BENCHMARK_DB, otherwise relative path under owned cwd.
- AuditLogger defaults relative logs under owned cwd; home fallback on OSError remains guarded.
- Existing AGK_HOOK_VAULT_DIR, AGK_USAGE_DB, ANTIGRAVITY_VAULT_PATH, AGK_PATH_* and owned cwd cover intended hooks/usage/vault/config paths. This does not establish all deferred API paths safe.
- GBrain source already shows concurrent AGK_GBRAIN_DIR change; publication/final source freeze has not been supplied. revision-v3 plan rebinding remains deferred.

Next: parent resolves two health-path defaults and publishes/finalizes source; then new revision-v3 QA environment contract delta, immutable source-plan rebinding and independent review. No live GO and no original v2 modifications.
