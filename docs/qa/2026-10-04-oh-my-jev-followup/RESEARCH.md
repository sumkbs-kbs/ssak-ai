---
title: oh-my-jev pinned source review and SSAK-AI application
date: 2026-10-04
tags: [research, decision, statistics, provenance]
---

## Source and discovery

Public remote HEAD and a shallow read-only clone both resolved to
`c03c182013b64223a9b3a15095e85ef17c002b56`. This is the same upstream commit as
the prior SSAK-AI analysis; this follow-up does not claim new upstream features.
Local full HEAD is `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`; existing shared
working-tree changes are preserved. Source identity must include file hashes
because HEAD alone does not identify this dirty checkout.

Graph-first discovery was attempted by Root, whose MCP connection returned
Transport closed. Read-only subagents successfully used the graph for the local
project and indexed the external temporary clone (fast, persistence=false).
Root then read their discovered files. GitHub CLI returned 401 Bad credentials;
public Git and official GitHub source pages supplied the evidence without
changing credentials. External code, tests, models and providers were not run.
The skill's Agent Reach update check returned a GitHub API rate-limit result;
no version change or installation was attempted.

## Adoption decisions

| Source finding | SSAK-AI action and constraint |
| --- | --- |
| [Wilson accuracy interval](https://github.com/iamupd/oh-my-jev/blob/c03c182013b64223a9b3a15095e85ef17c002b56/src/omj/bench/details.py#L23-L41), fixed z=1.96 | Independently implement a typed 95% interval for strictly valid labelled scored predictions; publish n and successes. Empty scored set returns null. No interval for ECE/Brier/NLL or selected risk. |
| [Tag diagnostics and max25](https://github.com/iamupd/oh-my-jev/blob/c03c182013b64223a9b3a15095e85ef17c002b56/src/omj/bench/details.py#L18-L117) | Accept bounded optional unique tags. Rank by tagged case count descending, then lexical tag. Expose at most25 groups and omitted count. Keep rare/universal tags visible with sample counts. |
| Original per-tag output is n, accuracy and mean confidence | Extend SSAK-AI groups with its own common typed summary: ECE/Brier/NLL, error/validity counts, ambiguity and empirical selective coverage, plus accuracy interval. These extra per-tag metrics are our extension, not an upstream feature. |
| [Coverage implementation](https://github.com/iamupd/oh-my-jev/blob/c03c182013b64223a9b3a15095e85ef17c002b56/src/omj/bench/metrics.py#L60-L73) | Retain SSAK-AI's existing whole-confidence-tie policy. Empirical selected risk does not certify future risk or grant execution permission. |
| [Gateway confidence](https://github.com/iamupd/oh-my-jev/blob/c03c182013b64223a9b3a15095e85ef17c002b56/src/omj/gateway/assemble.py#L29-L53) differs from benchmark max probability | Do not reinterpret runtime model confidence as a correctness probability. Preserve score_source=provided_probabilities and calibration_status=unverified. No model-manager adapter without a labelled probability contract. |
| [Reference comparison](https://github.com/iamupd/oh-my-jev/blob/c03c182013b64223a9b3a15095e85ef17c002b56/src/omj/bench/reference.py#L40-L101) is not a paired significance test or a strict dataset identity check | Defer reference comparison. A future comparison needs matched cases, source/dataset identity and a justified uncertainty method. |

Repeated/variant question rows are counted as observations upstream; neither
implementation establishes independence of samples. The interval describes the
submitted sample under its assumptions, not future generalization. Tags overlap,
so group totals cannot be added as independent global samples; no multiple
comparison correction is implemented.

The existing SSAK-AI quality gate assesses different properties from labelled
probability evaluation. This change does not prove Qwen accuracy, calibrate a
model, alter Constitution/Brain-Body/auth/tool approvals, or train/promote models.

The canonical empty-tag exclusion uses nested per-index `model_dump(exclude=...)`,
documented in [Pydantic 2.10 serialization](https://docs.pydantic.dev/2.10/concepts/serialization/#advanced-include-and-exclude).
Runtime tests used Python 3.13.12 and Pydantic 2.13.4; the minimum-version runtime
was not separately installed or tested.

## Copying and license boundary

The repository declares [Apache-2.0](https://github.com/iamupd/oh-my-jev/blob/c03c182013b64223a9b3a15095e85ef17c002b56/LICENSE).
[THIRD-PARTY.md](https://github.com/iamupd/oh-my-jev/blob/c03c182013b64223a9b3a15095e85ef17c002b56/THIRD-PARTY.md#L17-L43)
lists separate model/data provenance. A [confidence test](https://github.com/iamupd/oh-my-jev/blob/c03c182013b64223a9b3a15095e85ef17c002b56/tests/unit/test_confidence.py#L12-L15)
also declares verbatim inlining from another project. No external source, test,
model or dataset is copied into SSAK-AI; only the statistical method and diagnostic
ideas are independently implemented. No package installation was required.

## Before-change source fingerprint

Captured before the implementation workers edited these files:

| Repository-relative path | SHA256 |
| --- | --- |
| src/antigravity_k/engine/decision_evaluation_models.py | d839cada7ce41e20aaaf62510db385f121a88c581966d33f9ff4bf33f9e75659 |
| src/antigravity_k/engine/decision_evaluation.py | d0075b861e12897f17705074dfa812955989c83361a15ec7a4c41d1efae6e476 |
| src/antigravity_k/decision_evaluation_cli.py | 205500fb641d5f1319e60e7e20a1f278a00d5382ff696d2a6ce7a81e967291dc |
| src/antigravity_k/api/routes/decision_evaluation_api.py | bbedf21f9601a419e64d386e40bdca482ab1ce7fc3ef0e94ceede4e7088449db |
| tests/test_decision_evaluation.py | 43f3a590b4e2868916956b61e10bb47333d016ac2245bef279e7d04929a0d820 |
| tests/test_decision_evaluation_surfaces.py | c4836b0c0c82381ce1319ae424512e1caa5500ccd1126410c52d22a0580dad3b |
