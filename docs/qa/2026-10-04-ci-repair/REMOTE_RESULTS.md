# Remote validation after the first CI repair push

Source: `28f02124b69492207f9e1f3d01972565637f0418` on `sumkbs-kbs/ssak-ai/main`, verified against `git ls-remote`. This is the first repair snapshot; the later nested Trivy reference correction requires its own run. Old failed runs remain historical results.

## Published increments

| Commit | Change |
| --- | --- |
| `dfb8fd65` | Strict optional numeric parsing and policy pin validation |
| `ec27e127` | Output-preserving symbol extraction and indexing optimization |
| `4738a33c` | CI setup, readiness, reporting, and benchmark test discovery |
| `28f02124` | Public evidence links and scoped source reverification |

All four commits passed their applicable pre-commit hooks. The pre-existing 97 staged historical raw evidence paths were excluded, as were unrelated dashboard/runtime changes, private state, and local benchmark output.

## Observed matching jobs

Job states below were retrieved through the authenticated GitHub connector after the push, rather than inferred from local checks.

| Run/job | Observed result | Meaning |
| --- | --- | --- |
| [Docs Evidence Gate](https://github.com/sumkbs-kbs/ssak-ai/actions/runs/37171830892/job/111346166180) | SUCCESS | The public checkout passes its fast evidence gate. |
| [CI Type Check](https://github.com/sumkbs-kbs/ssak-ai/actions/runs/37171830925/job/111346166668) | SUCCESS | The strict CI checker passes. |
| [Dashboard Lint & Build](https://github.com/sumkbs-kbs/ssak-ai/actions/runs/37171830925/job/111346166545) | SUCCESS | Lint, tests, rebuilt wheel bundle and provenance checks pass. |
| [CI Evidence Gate](https://github.com/sumkbs-kbs/ssak-ai/actions/runs/37171830925/job/111346166732) | SUCCESS | The code-change evidence gate also passes. |
| [Clean-machine Ubuntu](https://github.com/sumkbs-kbs/ssak-ai/actions/runs/37171830925/job/111346166765) | SUCCESS | The existing Linux clean-machine reproduction succeeds. |
| [Build Package](https://github.com/sumkbs-kbs/ssak-ai/actions/runs/37171830925/job/111346206296) | SUCCESS | Package build and its bundle verification succeed. |
| [Security Scan](https://github.com/sumkbs-kbs/ssak-ai/actions/runs/37171830925/job/111346166780) | FAILURE | Gitleaks passes; dependency audit rejects 20 unresolved advisories across five packages. Bandit/internal scanning remain skipped in this remote job. |
| [E2E](https://github.com/sumkbs-kbs/ssak-ai/actions/runs/37171830925/job/111346166807) | IN_PROGRESS | Rebuilt bundle, backend startup, and Python smoke steps pass; Playwright accessibility was still running when observed. |
| [Container Scan](https://github.com/sumkbs-kbs/ssak-ai/actions/runs/37171830890/job/111346166224) | FAILURE | Trivy v0.28.0 resolves, but its upstream nested setup-trivy v0.2.1 tag is unavailable. This prompted the follow-up maintained-action correction. |

The full test matrix and Pages deployment were still running or queued; they are not counted as passes. The PR-only benchmark comparison did not run from this main push. Its strict 500ms criterion therefore remains unresolved, as documented in BENCHMARK.md.

The follow-up Trivy correction pins v0.36.0's actual commit `ed142fd0673e97e23eac54620cfb913e5ce36c25`. Its signed annotated tag was peeled to the commit before publication; seven action/installer references were checked using both the exact Git commit API and raw source URLs. All returned HTTP 200. Scan inputs and rejection thresholds are unchanged. Reference checks do not establish the container's scan result.

## Remaining acceptance work

- Adopt verified compatible dependency upgrades, regenerate the lock and rerun the real dependency auditor. OAuthLib requires compatibility work for its major-version candidate.
- Resolve the reviewed Bandit cases and repository-scanner classification while retaining their hard rejection behavior and credential coverage.
- Observe the corrected container action's actual build/scan outcome and final test/accessibility matrix results.
- Run the unchanged full benchmark gate on a matching PR execution. Local semantic equivalence and reduced work are not a latency acceptance result.

These residual checks prevent a full green-CI claim. No severity, latency limit, detection floor, fixture expectation, or public evidence baseline was relaxed to hide a failing check.
