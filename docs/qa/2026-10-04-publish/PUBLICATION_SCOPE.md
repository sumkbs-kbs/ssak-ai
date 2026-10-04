---
title: Public publication scope and evidence boundaries
date: 2026-10-04
tags: [publication, privacy, evidence, documentation]
---

The user selected all current SSAK-AI product changes for publication to
https://github.com/sumkbs-kbs/ssak-ai.git. Product Python source, dashboard source,
direct tests, dependency manifests and locks, matching rebuilt dashboard assets,
current implementation plans, public review summaries and the English/Korean
READMEs belong to this publication.

Personal authentication records, runtime data and vault contents, temporary
experiments, local tool stores, copied source baselines, browser captures and raw
QA command outputs remain local. Newly added raw machine evidence and compressed
archives are excluded. Existing tracked documentation contracts retain their
current updates. No historical commit was rewritten.

Historical Markdown reports may refer to local-only manifests, logs, screenshots,
receipts or archives. These references document the original investigation; a
fresh public clone does not contain those supporting raw artifacts. In particular,
the October 4 decision-diagnostics source snapshot and completion receipt remain
local. Do not interpret historical hashes, review verdicts or prior live trials
as certification of this publication commit.

The synthetic decision manual-cases file and its two isolation helpers are
included to keep the public usage commands reproducible without the user's
authentication or storage state. The core live plan contains no personal PIN.
The default English README links only to documents selected for the public tree.

Publication verification covers the commands recorded in the validation receipt.
It does not certify every core mechanism, real-model answer quality or a complete
browser workflow. The saved localhost browser denial was respected; no raw HTTP,
CDP or alternative browser was used to bypass it during publication.
