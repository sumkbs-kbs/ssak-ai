# Manual-probe transport limit

The primary manual probe's server log contains repeated accepted/closed `/v1/ws/events` connections. Their cause and transport contract were not verified by the primary's UI actions; this is not reported as a WebSocket PASS. The serve helper inherited the SourcePlan origin settings rather than the hermetic backend's per-port origin configuration, but no causal conclusion is established here. The owned server was terminated with observed exit -15 and reaped; graceful exit0 was not observed. The formal WebSocket and lifespan gates remain separate.
