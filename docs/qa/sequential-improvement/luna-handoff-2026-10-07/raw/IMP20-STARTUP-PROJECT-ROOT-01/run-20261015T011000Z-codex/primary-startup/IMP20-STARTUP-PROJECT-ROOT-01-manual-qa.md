# manualQa

Overall verdict: **FAIL**. The primary session executed the real surface once; this QA executor independently read the saved command binding, logs, curl error and result. No second startup or request was issued by this executor.

## Exact invocation

Working directory: `/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai`.

```sh
/usr/bin/sandbox-exec -f /Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP20-FRESH-FULL-GATES-02/run-20261015T001700Z-codex/provider-boundary.sb /Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai/.venv/bin/python -B -m uvicorn antigravity_k.api.server:app --host 127.0.0.1 --port 49656 --loop asyncio --lifespan on --log-config /Users/mr.k/program/coding/ssak_comp/Ssak-Ai/docs/qa/sequential-improvement/luna-handoff-2026-10-07/raw/IMP20-STARTUP-PROJECT-ROOT-01/run-20261015T011000Z-codex/primary-startup/private-runtime/logging.json
/usr/bin/curl -i --noproxy '*' --max-time 5 --silent --show-error http://127.0.0.1:49656/health
```

Cleanup invocation in the executed harness: `os.killpg(95169, signal.SIGTERM)` then `process.wait(timeout=10)`; deadline exceeded, followed by `os.killpg(95169, signal.SIGKILL)` and `process.wait(timeout=5)`.

## surfaceEvidence

| scenario id | criterion reference | surface | exact invocation | verdict | artifactRefs |
|---|---|---|---|---|---|
| PS-01 | acceptance.md #1 configured-root-startup | Actual Uvicorn lifespan and filesystem | Uvicorn command above, once | PASS: startup completed, RAG log reports one chunk; hook and audit logs and files use configured project | A1, A2, A4 |
| PS-02 | acceptance.md #2 public-health | External HTTP via curl -i | curl command above, once | FAIL: curl exit 28 after 5002 ms, zero response bytes, no HTTP status | A1, A3, A4 |
| PS-03 | acceptance.md #3 shutdown | OS signal/wait plus process logs | Exact cleanup invocation above | FAIL: SIGKILL required, exit -9; hook/application shutdown not observed. Process was reaped and group empty | A2, A4, A5 |
| PS-04 | acceptance.md #4 evidence-binding | Source files and serialized receipts | Read-only SHA-256 comparison performed by run_once.py before and after the process | PASS: three source hashes unchanged; recorded harness matches executed source | A1, A4, A6 |

## adversarialCases

| scenario id | criterion reference | adversarial class | expected behavior | verdict | artifactRefs |
|---|---|---|---|---|---|
| ADV-01 | acceptance.md #1 | Configured project differs from installed checkout; hook override absent | Startup RAG/hook/audit use configured project | PASS for these startup consumers; downstream health storage separately fails ADV-03 | A1, A2, A4 |
| ADV-02 | acceptance.md #2/#3 | Slow lazy initialization under bounded request and cleanup deadlines | Health within 5 s and graceful shutdown within 10 s | FAIL: health timeout, forced cleanup | A2, A3, A4 |
| ADV-03 | acceptance.md #4 owned runtime boundary | Health lazily initializes additional services | Persistence and project selection remain inside owned configured roots | FAIL: ChromaDB log names candidate checkout .antigravity/vault_data/.chroma; PermissionGate logs checkout project root | A2, A5 |
| ADV-04 | task scope | Provider inference semantics and IDE listener | Not triggered by the one public health GET; no inference or IDE listener request was part of this change | not_applicable: neither inference behavior nor IDE listener behavior is being changed or exercised here | A1, A4 |

## artifactRefs

Paths below are relative to this matrix directory unless absolute.

| id | kind | description | path |
|---|---|---|---|
| A1 | JSON binding | Exact commands, source hashes, config/provider policy and request bounds | execution-binding.json |
| A2 | Process log | Actual startup, request start, lazy ModelManager and forced-shutdown lead-up | server.stderr.txt |
| A3 | HTTP client error | curl timeout and zero bytes received | health.stderr.txt |
| A4 | JSON result | Actual counters, exit, storage observations, source hashes | result.json |
| A5 | Correction | Corrects misleading unconditional audit-close description without overwriting it | qa-correction.json |
| A6 | JSON verification | Independent saved-file/source/manifest verification | stored-evidence-check.json |

`health.http.txt` is empty and is not used as a PASS artifact. Global provider requests were not independently counted; only this client's POST/inference request count is zero. IDE's generic startup log does not prove an IDE listener: the same log explicitly reports missing code-server. A SQLite integrity result after forced exit does not prove normal AuditDb.close execution.
