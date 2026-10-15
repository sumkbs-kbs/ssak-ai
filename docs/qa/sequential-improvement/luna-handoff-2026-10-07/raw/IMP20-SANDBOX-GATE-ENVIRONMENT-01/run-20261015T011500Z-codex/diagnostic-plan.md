# Nested sandbox diagnostic

Ownership is limited to this evidence directory. Product sources, fixtures, formal gate reports and historical records are read-only.

Hypotheses:
1. The artificial outer provider Seatbelt profile prevents the product from applying its own mandatory Seatbelt profile. The same safe workspace Python test will fail with `sandbox_apply` under the outer profile and pass without that additional layer.
2. Interpreter runtime allow-list discovery is incomplete. The test would fail in both modes with Python startup/import denial.
3. Owned storage/auth fixture initialization is the failure. It would fail before the workspace test reaches `run_sandboxed_argv`.

Execute only `TestWorkspaceStillRuns::test_python_runs_inside_workspace`, once per mode, with identical source and interpreter. Its child code only prints `PYTHON_OK`; product sandbox remains enabled and network=none in both cases. Test-process socket connect/bind audit guards deny any accidental network activity. Preserve stdout, stderr, JUnit, subprocess/socket audit, runtime paths and source hashes. This is diagnostic evidence, not a replacement or pass for the full formal gate.

Artifacts created by the diagnostic launcher: per-mode owned storage under `private-runtime/`, per-mode stdout/stderr/JUnit/audit and receipts, source binding and final result. All are retained as requested evidence; no debugger or daemon is started.
