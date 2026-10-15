# Primary startup QA: execution prepared, not executed

Owner: primary session. Candidate: `/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai`, HEAD `7360c78544abeea41e38c65faa6eba2610a8a33b` plus the three source-bound startup root files.

Exact invocation:

```sh
/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai/.venv/bin/python -B /Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP20-STARTUP-PROJECT-ROOT-01/run-20261015T011000Z-codex/primary-startup/run_once.py
```

Before launch the script checks the existing three-file source binding and expected HEAD, creates a non-reusable `private-runtime/`, writes the exact Uvicorn and curl arguments to `execution-binding.json`, and pins the harness, environment contract, provider profile, isolated config, and tiny project input hashes. Runtime credentials are generated privately and excluded from public artifacts. Config model/provider addresses point to a reserved bound-not-listening endpoint. YAML model group order is retained with `sort_keys=False`.

## Scenarios and acceptance

1. **PS-01 / configured-root-startup**: real Uvicorn, `--loop asyncio --lifespan on`, configured project containing one Python function. Startup and RAG completion must appear within 60 seconds. Hook and audit startup logs must name `<configured-project>/vault_data` and corresponding files must exist while the process is alive. RAG's legacy log says `1 files indexed`; its returned count is actually chunks, so this establishes one chunk from the single input function, not a general distinct-file counter.
2. **PS-02 / public-health**: only after startup/RAG logs, `/usr/bin/curl -i --noproxy '*' --max-time 5 --silent --show-error http://127.0.0.1:<allocated-port>/health`. Exactly one invocation, no redirect or retry options, exit 0 and HTTP 200. Save full non-authenticated response headers and body.
3. **PS-03 / shutdown**: SIGTERM only the owned process group, wait up to 10 seconds; forced SIGKILL/reap after the deadline counts as failure. Require hook shutdown and application shutdown logs, process exit 0, reaped process and empty process group. Read audit SQLite integrity after exit using `mode=ro`; require `ok`. The `AuditDb.close` method itself is not instrumented; do not claim separate method-level proof.
4. **PS-04 / evidence-binding**: all three source hashes equal the pre-launch hashes. Record actual source, request count, status, exit, limits and owned project inventory. Product POST and inference requests issued by this client are 0. Global provider traffic is not independently instrumented and must not be reported as globally counted 0.

No source/test/Git changes, legacy successful tests, old native one-shots, IDE listener validation, full gate, soak, or release approval are part of this execution. A prior run directory is not reusable. On any failure preserve the existing attempt before deciding whether a new attempt is warranted.

After primary execution, write the manualQa matrix and Korean handoff against actual `result.json`, `health.http.txt`, `server.stderr.txt`, execution binding and launch record. Add a supplemental manifest; never replace the existing 158-item parent manifest. Exclude `private-runtime/**` from publication.
