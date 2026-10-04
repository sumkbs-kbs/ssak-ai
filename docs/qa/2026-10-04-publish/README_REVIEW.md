---
title: English README publication review
date: 2026-10-04
tags: [publication, documentation, readme]
scope: README.md and README.ko.md
---

# English README

The GitHub homepage README is now English. Its clone and CI links target
`sumkbs-kbs/ssak-ai`. The complete pre-edit Korean README was read and preserved
byte-for-byte as `README.ko.md`; it remains a historical introduction, including
its original repository links and dated claims.

The English introduction documents local inference, Brain/Body responsibility,
workspace UI, retrieval and memory, execution safeguards, optional financial and
voice interfaces, and decision-probability diagnostics. Installation uses the
locked uv environment. Runtime guidance asks users to inspect installed models
rather than promising that a configured model identifier can be downloaded.
Private PINs, credentials, operational logs, and user-specific configurations are
not included in the new introduction.

## Grounding and checks

- Python, extras, CLI entry point, and license: `pyproject.toml`, `LICENSE`.
- Node/pnpm requirements and dashboard commands: `dashboard/package.json`.
- Development targets: `Makefile`.
- Product host/port and authentication: graph-discovered `ServerConfig`,
  `SecurityConfig`, and `validate_startup_security`, with exact source snippets.
- Local default profile: shipped `src/antigravity_k/config.yaml`.
- Feature scope: current core plans and the external-feature improvement plan.
- Wilson intervals, tag bounds, and interpretation: the October 4 decision
  implementation contract, usage, and result report.
- Support and verification status: links to the status owner and dated plans;
  no release-candidate SHA, gate inventory, or aggregate PASS copied into README.

All 28 relative Markdown links in the English README resolve in this checkout.
Code fences are balanced, the target clone and CI URLs are present, and the old
`ssak-comp` repository URL is absent from the English README. Scoped
`git diff --check` passed. The edited English README was read in full after
writing. No dependencies were installed and no application or user data was
changed for this documentation task.

Publication-time hashes:

| File | SHA-256 |
| --- | --- |
| `README.md` | `0135eeb1a0b82a22ad3513c39bec7da61e1953efa0195b2388719c2de301fd18` |
| `README.ko.md` | `6b701157b2f62129ae0f17a18438547db998dfc9a4be3353519b32a5f0b5c846` |

## Limits

The documentation does not establish whole-program production readiness,
actual model accuracy, calibration, or completed browser verification. The
existing `.env.example` retains different example provider/port values from
product defaults; README explicitly instructs users to review them. Dashboard
development uses Vite's printed URL instead of repeating a stale port. Full
fresh-machine installation was not performed as part of this documentation
change. Root owns final release inspection, staging, commit, and push.
