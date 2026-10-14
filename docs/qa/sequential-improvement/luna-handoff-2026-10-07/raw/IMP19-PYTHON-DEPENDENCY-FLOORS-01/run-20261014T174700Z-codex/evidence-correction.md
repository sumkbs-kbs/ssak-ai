# Audit-input artifact correction

The first verification driver exported AGK_AUDIT_RECORD to both the real audit and pytest. The old _run_audit helper inherited that path when a fixture requested the legacy AUDIT_RECORD name. Consequently checks-attempt-1/audit-inputs.json was later replaced by fixture output (one-package input). It is not the real audit input record and must not support the audit PASS claim. The first regression FAIL and the overwritten JSON are preserved.

The real audit stdout still contains its original AUDIT-INPUTS line (base 74 / shipped rag union 150), five already-excepted chromadb findings and unresolved=[]; the real command receipt is exit 0. A separately named audit-inputs-from-stdout.json is derived from that retained stdout, with its SHA recorded, without modifying the overwritten JSON or rerunning the audit.

The test helper now drops inherited record-path variables before each fixture's explicit environment is applied. Both parent-name variants check that an existing parent evidence sentinel stays unchanged. The affected bootstrap selector passes 20 cases. The other 214 passing cases from the unchanged first selector remain distinct evidence; the superseded bootstrap rows are not counted twice. This does not constitute a single clean full-suite run.
