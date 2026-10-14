# Dashboard gate prerequisites and server ownership

- Prior d868 diagnostics: accessibility failed on connection refusal at fixed8012, witness30 failed because the project venv lacked uvicorn, ambient6 failed including the same nested backend cause. Preserve those reports.
- Parent security/dependency candidate481a634 is independently approved and pushed. No full GA claim.
- First prepare this owned candidate's frozen project venv and dashboard install. This restores the prerequisite expected by the existing uv --no-sync browser backend helper without modifying it.
- Reuse run_dashboard_e2e_ambient.py to give accessibility's required gate an owned backend and ephemeral loopback URL, keeping its complete selector and existing default ambient/seeded suites unchanged.
- Never use a shared user listener or infer a pass from static coverage. Record actual browser gate outputs and bounded cleanup.
