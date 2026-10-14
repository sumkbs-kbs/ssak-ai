# Independent preparation review: REQUEST_CHANGES

Scope: priority-6 startup/auth/lifespan preparation only. Actual startup remains NOT_RUN.

The independent reviewer found one HIGH ownership defect in startup_probe/supervisor.py: launch.json was written after Popen but before the cleanup-protected try; stop.requested write errors and ProcessLookupError signal races could bypass kill/reap; cleanup exceptions could bypass the terminal result. Put every post-spawn operation inside ownership try/finally, use bounded fallback when stop-file writing fails, handle disappearance races without inventing exit values, and persist truthful cleanup status even if diagnostics fail. Preserve one shared cleanup deadline.

The 24 saved PASS cases cover supplied Cleanup values, not those process lifecycle branches. Add fake-child/clock regressions for launch-receipt failure, stop-file failure, disappearance during signal, unreaped timeout and output persistence failure. No actual process or server is required.

The reviewer otherwise accepted the five-file approval binding, source verification, exclusive live-once, genuine lifespan and authentication, four non-retried requests, absolute AnyIO timeout, isolated environment and credentials, and documented Python-guard limits.

Reviewed supervisor SHA prefix 2752e653; plan 128c4c13; candidate 7802aa1b. Changed preparation needs a new binding and review. No actual startup approval was issued. Original sources and receipts must remain preserved.

Source: terminal report from /root/closeout_code_audit, read-only independent review. Worker has been assigned these repairs in a new revision directory.
