# GitHub Actions repair — 2026-10-04

Scope: diagnose the failures on the published SSAK-AI repository, fix their causes, and observe new remote runs. Existing local private evidence and unrelated changes remain outside publication.

1. completed — identify failed jobs and their concrete log errors on main and representative Dependabot runs.
2. completed — repair workflow prerequisites/readiness, strict typing, public evidence consistency, and investigate benchmark regression without weakening gates. The strict 500ms result remains unproven; newly reachable security findings are recorded separately.
3. in_progress — reproduce relevant checks on an exported publication snapshot; commit explicit repair paths and push to SSAK-AI main.
4. pending — inspect matching new GitHub Actions jobs and record their actual terminal outcomes or external blockers.

Confirmed failure sources:

- Evidence Gate: broken links to omitted raw local artifacts; stale digest measurement.
- Type Check: two Optional type errors hidden by the local no-strict-optional hook.
- Dashboard wheel verification: uv missing from this job.
- E2E startup: curl connection error aborts bash -e before retry.
- Gitleaks: shallow checkout cannot resolve the requested revision range; zero bytes scanned.
- Container Scan: nonexistent aquasecurity/trivy-action@0.28.0; published tag is v0.28.0.
- Benchmark: context enrichment 1261.4ms exceeds unchanged 500ms limit; Dependabot comment receives 403.

Remote source logs: https://github.com/sumkbs-kbs/ssak-ai/actions/runs/37167142002 and https://github.com/sumkbs-kbs/ssak-ai/actions/runs/37167176754 .
