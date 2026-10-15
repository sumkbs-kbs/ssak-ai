---
title: IMP20 bounded candidate continuation preparation
date: 2026-10-15
status: READY_NOT_LAUNCHED
---

Prepared continuation.py (189 lines) and collector_proxy.py; no wrapper, collector, controller, gate, model, or HTTP request was launched in this preparation. This artifact is outside product execution and reuses the existing FRESH3 finalizer, guarded soak helper, controller, and real collector. No product/source/Git/status/previous evidence edits were made by this executor.

Parent launch command is the exact argv in prepared-plan.json.launch_command. It starts one detached `/usr/bin/caffeinate -i` supervisor with owned stdout/stderr and a minimal environment. It persists an exclusive start claim before Popen and launch PID receipt afterward. Claims are never removed or retried. Input hashes and wrapper hash are fixed before the claim and verified again inside the supervisor. The supervisor checks the claimed plan digest as well.

The supervisor polls existing FRESH3 terminal receipts every 30 seconds for at most 44,400 seconds (the 23 original gate timeouts plus 1,200). It never launches or requests a gate. It reuses an existing result; otherwise it calls the existing finalizer once. Parent has agreed not to manually finalize after this wrapper owns continuation. Arbitrary noncooperating concurrent manual finalizers cannot be locked by this wrapper. A missing terminal receipt, actual nonzero exit, failed check, merged report, or source drift cannot launch soak.

Eligible full23 results invoke the reviewed helper exactly once, using assigned WT3 Python with `-I -B --launch`. Helper SHA is `0b529e92543e320137bb00280c2a6186e0ce96a365baeee6b72f31d37c26f677`. The controller owns its unchanged default 60-second preflight and launches its existing detached harvest. The parent connected the real collector adapter through the existing NX10_JUDGE hook. The adapter runs the real WT3 collector exactly once with inherited environment/stdout/stderr, and records exclusive claim, actual child PID, source hash, actual exit including negative signals, and propagated exit (128 + signal when terminated by signal).

The supervisor waits up to 43,800 seconds for recovery JSON and the actual collector receipt, tolerating absent/partially written JSON. It then invokes the exact official final verifier argv from the helper execution plan once, enforcing the current full report, owned soak artifact, and minimum 28,800 seconds. PASS requires all six exact SC scenarios passing, measured SC6 duration and runner wall duration both at least 28,800 seconds, actual collector/verifier exits zero, recovery PASS with all six checks true, matching runner/current/commit fingerprints, frozen input hashes, and unchanged gate evidence. PASS is scoped to this candidate's full23 and SC1–6 storage soak; global GA/release/activation approval remains NOT_ISSUED.

Each owned subprocess records a claim, actual PID, and waited exit receipt. On child timeout, the receipt records unknown exit and PID; no effectful retry or kill follows. Existing gates/soak may remain running; this is UNOBSERVED, never success. The supervisor-terminal receipt records the supervisor return decision, not a fabricated reaped process exit.

Preparation scenario: in-memory Python compilation plus read-only AST/source/hash checks. Exact invocation, actual exit 0, 22 true binary checks, and artifact hashes are recorded in `.omo/evidence/preparation-evidence.json`; full captured output is `.omo/evidence/preparation.stdout.json`. These checks prove preparation only. Gate completion, detached operation, collector completion, official verification, and 8-hour metrics remain NOT_RUN/UNOBSERVED until launched and captured.

Expected runtime evidence: `launch-receipt.json`, append-only `events.jsonl`, atomic `state.json`, child `*-pid.json` / `*-receipt.json`, `result.json`, and `supervisor-terminal-receipt.json`; the existing owned soak directory retains `collector-claim.json`, `collector-pid.json`, `collector-receipt.json`, `soak-exit.txt`, `soak-recovery-latest.json`, and `soak-28800.json`. No final runtime PASS is claimed here.
