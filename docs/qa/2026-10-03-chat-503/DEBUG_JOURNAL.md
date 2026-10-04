---
title: "503 복구 및 선행 통합 점검 journal 보존"
date: 2026-10-03
tags: [qa, debug-journal]
---

# Debug journal — remaining work closure
Date: 2026-10-03 (Asia/Seoul)
Baseline HEAD: 8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382
User scope: finish residual work after reviewing completed tests/documents.
Existing staged cognitive source/tests/docs are preserved; no commits or rollout.
References: programming/python README; debugging/python runtime, setup, investigate, fix.

## Hypotheses
1. View freshness is still mtime-based and skips committed journal turns after a restored view; distinguish using existing F2 contracts and sequence/mtime fixture.
2. FLUSH2 was already applied under another implementation; distinguish current symbols/knobs and existing ten-contract runtime results.
3. Pending claims are documentation-only and current evidence matches source; distinguish source manifest hashes and raw test artifacts.

## Artifacts
- .debug-journal.md: temporary task journal; remove after durable handoff.
- docs/qa/2026-10-03-residual-close/: durable closure evidence and logs (keep).
- pytest tempfile fixtures: created by harness and cleaned by harness.
- No live user vault/auth/migration or paid provider operations.

## Findings
- Existing F2 contract root-run: 8failed/2passed; restored view returns journal_seq1 although tail3.
- Current ConversationStore SHA256 exactly matches rehearsed F1 preimage c9029151ccbdb76a821698fb13b65a1c02773a8a6ed5df6444b12e1ac9ac03dc.
- No relevant running Python/soak process was listed in environment check.
- F2 staged patch owns only clean ConversationStore; backup will move to durable evidence.
- Additional cross-instance flush/delete safety must be verified; staged implementation only tests same-instance deletion.

## Additional artifact intents
- Apply prevalidated F2 patch to ConversationStore and preserve preimage backup in closure evidence.
- New tests/test_view_freshness_contract.py: strict behavioral regression contracts (not source/prose assertions).
- Existing cognitive staged files unchanged by root; latest saved suite had12failures and needs current-node recheck.

## Live desktop chat 503 — 2026-10-03
User requested screen inspection and restoration of conversation service.
Plan: identify actual 503; inspect migration dry-run and preserve originals; stop owned host, migrate and verify; restart and test real chat through browser; record results.
Hypotheses:
1. Provider unavailable: /health initially had qwen3.8-flash-next:125b-mlx registered; Ollama tags contain it. No inference evidence yet.
2. Route/provider mismatch: source investigator suggested MLX selection mismatch, unconfirmed; do not change selected model on this evidence.
3. Unmigrated conversation store: real store has four legacy records; current ConversationStore.storage_layout_state() returned legacy_requires_migration. API request without credentials returned 401; authenticated 503 reproduction pending.
Artifact intents:
- Temporary browser tab at localhost8000, PIN unlock pending; do not reset authentication.
- /private/tmp/ssak-chat-503-20261003/: private dry-run/apply/verify reports and read-only original hashes.
- Keep automatic conversation migration backup outside the storage root; preserve all legacy originals. No destructive cleanup.
- Restart only Electron PID12387 and owned API PID12410 after confirming ownership.
- Runtime fix only unless actual chat reveals a source defect; existing full core QA remains scoped to its unchanged source manifest.
References: debugging setup/investigate/fix and Python/Playwright runtime references; CR01 migration runbook.
Findings: dry-run conflicts=[]; apply=applied; verify=verified; original and backup hashes all match; layout=v2. Backup: /Users/mr.k/.antigravity/conversations.migration-backup-20261002T234359Z.
Post-migration live125B chat reached Ollama; server.log reports runtime OOM detected / Metal Insufficient Memory. User explicitly chose installed qwen3.8 27B. Browser model selector changed to qwen3.8:latest; actual reply pending.
Verification attempts: initial pytest collection denied home GBrain lock; in-process Path.home isolation yielded31passed/1failed because spawn workers do not inherit the patch. No source defect is inferred from this sandbox failure.
Additional artifact intent: temporary /private/tmp/ssak-chat-503-20261003/isolation/sitecustomize.py patches Path.home for test parent and spawn processes only; SSAK_QA_HOME points to temporary fixture root. HOME is unchanged. No production process uses this helper.
Later findings: new store preference red4/5 then green23/23; dashboard full938passed/buildexit0. Fresh bundle index-Bh-w7yNi.js; manual27B selection survives reload. New backend configured-default selection has13passing endpoint regressions; broader suite66passed/1preexisting bundled-config copy drift (configs unchanged).
Artifact intent: final restart only owned Electron22390, uv22409, API22410 to activate configured-default route; preserve browser token/model preference, user originals and migration backup. Keep generated bundle preimage at /private/tmp/ssak-chat-503-20261003/dashboard-dist-before. New bundle already built and served.

Final findings: latest-source 27B chat after restart returned 정상 연결입니다.; Ollama HTTP200 at09:10:33; model retained after refresh and restart. Independent functional and visual/CJK passes both HIGH/PASS, BLOCKING0. All source/capture/bundle hashes match. Optional TSchecker wording corrected to recorded resolution error. Existing config-copy failure remains outside this fix.
Cleanup: preserve this owned journal in durable QA evidence, then remove its root scratch copy; preserve startup isolation helper as text evidence, then remove the owned temporary helper. Keep private migration reports, backup snapshots and test results; keep the launched user program and browser deliverable. No .git writes or user-original deletion.
