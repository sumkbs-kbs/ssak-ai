# Actual startup/auth observation: components PASS; isolation NO_SUCCESS

Clean candidate 7482ebb8b76c7c686e729e68c48f7258e2cc7e66, fresh approved revision-v3, one invocation. Child PID 20393 exit 0, reaped, process group empty, no forced shutdown or cleanup errors. Root supervisor exit 1 and terminal NO_SUCCESS are preserved. Elapsed 7.052709125 seconds.

Four actual non-retried requests completed: protected GET without credentials 401; actual temporary PIN login 200; protected Bearer GET 200; authenticated health 200. Genuine lifespan logs show Application startup complete and Application shutdown complete. No model call or scheduled tick was observed; one owned listener bound.

Overall isolation did not pass. Guard violations were: a read-only stdlib platform command `file` rejected by the overly narrow subprocess allowlist; EventBus persistent-agency construction attempted the source checkout's .antigravity_k directory instead of config.paths.project_root. The guard blocked the nonowned mkdir; the product caught that hook exception, continued serving, and logged it. HTTP success is not evidence that the startup hook initialized correctly.

Root assigned a minimal caller fix in server lifespan to supply configured project_root to the existing EventBus bridge. A new QA guard revision will allow only the verified stdlib `file -b <resolved interpreter>` probe under fixed system PATH, rejecting arbitrary commands, options and targets. This does not disable mutation/model/network guards. Original four successful requests remain source-bound to this candidate; any later observation needs a fresh source plan and attempt after the startup change.

Original root-tool-receipt, result, guard, request receipts, sanitized logs and private raw credentials remain preserved. auth-private/** is local only and must not be published. No public or GA release approval follows from these component results.
