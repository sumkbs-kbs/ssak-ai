# IMP07-CHROMA-STARTUP-DIAGNOSTIC-01

**PASS_FRESH_OWNED_NATIVE_LIFECYCLE_ONLY.** One fresh Python process, PID 76383, completed the direct current VectorStore/RAGIndexer lifecycle with ChromaDB 1.5.9. Exit 0, no signal or timeout, no remaining owned process-group members. The successful probe was not replayed.

This result does **not** explain, reproduce, or repair the previous mocked-route fixture's Rust count SIGSEGV. That fixture's initialization and lifetime differ from this fresh, isolated direct-store scenario. No native backend fix or route-integration PASS is claimed.

| Scenario | Binary observable | Artifact |
| --- | --- | --- |
| Fresh owned VectorStore → RAGIndexer construction → get_stats | Constructor/manifest native count path completes; explicit count=0 | `probe.stdout`: `fresh_empty:*`; `result.json` |
| Close then reopen empty store | Close reports `_closed=true`, `client=None`; new store/indexer completes with count=0 | `probe.stdout`: close and `reopened_empty:*` phases |
| Explicit deterministic precomputed row | Collection.upsert receives exactly one 3D vector `[1,0,0]`; get_stats count=1 | `probe.py`, `probe.stdout`: `precomputed_count_verified` |
| Close then reopen persisted store | New store/indexer native count completes with count=1, then closes | `probe.stdout`: `reopened_persisted:*`; owned `runtime/persist/` |
| Safe ordering | Every recorded count belongs to an open store. Client/collection Python identities and closed flags are logged before count/close. No count is deliberately invoked on a closed native collection. | `probe.stdout`, `probe.py` |
| Bounded OS cleanup | Dedicated process group, 30-second outer deadline, OS child close event reaps the process; process-group lookup returns no members | `invocation.json`, `supervisor.mjs` |
| Network and model isolation | Inherited sitecustomize installed before imports; AF_INET/AF_INET6 connect/bind/sendto/listen and DNS denied. No physical-network or external executable attempts observed. Telemetry disabled; model caches owned/offline; embeddings supplied explicitly, no embedding-generation call | `guard-76383.jsonl`, `invocation.json`, `result.json` |
| Source/index preservation | VectorStore, RAGIndexer, chroma_lifecycle, long_context_fusion, dependencies SHA256 unchanged; staged file count remains 97 and staged binary patch SHA256 unchanged | `before.json`, `after.json`, `result.json` |

The exact executable, argv, cwd, environment overrides, timing, PID/group and exit are in `invocation.json`. Raw stdout/stderr are `probe.stdout`/`probe.stderr`. This is a direct diagnostic helper, not a pytest suite; no pytest or JUnit count is claimed. `module-bindings.json` records the actual imported project and installed Chroma/native-binding file paths and hashes. `source/` contains only the five scoped source preimages. No product/test source, configuration, Git staging, commit or push was changed.

The project and persistent-store roots started empty under this owned run. HOME and CODEX_HOME were preserved. All probe configuration/state/cache paths point into `runtime/`; its persisted evidence is about 208 KB. Concurrent tool-loop/API work is intentionally excluded from the diagnostic's source binding to avoid attributing another agent's changes to this run.

Graph discovery returned `Transport closed`; direct source reads established the constructor and close APIs before invocation. The Python socket guard is a Python-level guard, not an OS sandbox; this local native Chroma path made no observed network attempts. No claim is made about concurrent client lifetimes, historical fixture shutdown ordering, retrieval quality, embedding quality, live providers, or full application readiness. `artifact-manifest.json` seals this small diagnostic run.
