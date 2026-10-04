# Independent context/provenance review — 2026-09-27

Verdict: **REQUEST CHANGES for blanket R00–R23 completion / current PASS claims.** This is an independent read-only provenance and requirement audit, not a test execution or universal R*-V sign-off. No suite was duplicated. No source or operational state was changed.

Scope: repository `/Users/mr.k/program/coding/ssak_comp/Ssak-Ai`, HEAD `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`, branch `codex/m1-task-events`. Relevant tracked source was clean at inspection; `vault_data` submodule and many pre-existing untracked artifacts remain outside this verdict. Reviewed original pack tasks/contracts/checklist, repository R00–R23 report declarations, R19–R22 raw evidence, current status, independent checklist, and latest Git history. Git Master HISTORY/STATUS and codebase-memory graph-first guidance were used. Current evidence hashes below bind the actual inspected bytes.

## Findings

### P1 — R19 is a scripted contract result, not completion of the registered live experiment

Original task R19 requires a fresh local-model smoke, preregistered real Fresh/Mature experiment, raw trial closure, independent recomputation and ablation. It expressly permits an unfavorable result to complete the experiment. Current report says no live 108-generation smoke was run. `scripts/benchmark_cognitive_growth.py:146–211` freezes a manifest, returns NOT_RUN unless `SSAK_LIVE_SCRIPTED=1`, and otherwise constructs `ScriptedModelPort(mode="correct")`. No actual live result/ledger is present in R19 evidence, only suite/probe/report/manifest files. This is honest harness evidence but the PASS title and checked A1–A4 must be scoped to the scripted contract. Local provider wiring and an actual frozen bounded run remain work. A currently unavailable provider would be an external dependency only after an actual fresh availability/smoke result; a historical model listing is insufficient. Paid-provider budget is a genuine approval boundary if a paid fallback is proposed. A prescribed 108 slots is a starting proposal, not an immutable mandatory sample size.

### P1 — C01–C09 contract artifacts and consumer acceptance are missing

`IMPLEMENTATION_CONTRACTS.md` explicitly names nine versioned contract files and requires types, source/spec hashes, authority source, failure codes, serialized examples, producer/consumer nodes and reviewer. The repository `docs/ssak-ai-core/evidence/current-remediation/contracts/` contains only `context-v1-r06-note.md`, a short two-field schema delta. Expected `context-v1.md`, `feedback-v1.md`, `freshness-v1.md`, `transaction-v1.md`, `lifecycle-v1.md`, `experience-v1.md`, `policy-v1.md`, `trial-ledger-v1.md`, and `composition-v1.md` are absent. This is normal implementation/documentation acceptance work. The contract states producer completion cannot stand in for missing consumer integration. In particular C03 requires real CanonicalStore heads, R09 writer integration and R15 boot acceptance; CURRENT_REMEDIATION_STATUS still names production store-backed freshness resolver as open. Providing an opt-in trusted composition is implementation work; authorizing real production effects is a separate Human decision.

### P1 — R21 no longer satisfies its own current-bytes binding

The real source `.antigravity_k/agency.db` remains byte-identical: sha256 `6bc93092b6b476f25f6d4af402a95c4963b4d6d79a04afd2f9df12c8c4aa4fd5`, 26,206,208 bytes. Historical report records 56,961 observation events, zero objectives/tasks, stable replay and rollback; these are valid historical observations. However rehearsal pins for migration.py, legacy_adapter.py and test_migration.py no longer match current bytes. R00 explicitly requires all source/test/spec pins to match or the result becomes HISTORICAL. A current read-only consistent-source rehearsal into a disposable separate target can close this without cutover approval. The provenance sample file records only source IDs/types (1, 28481, 56961); it does not exhibit source payload → canonical record payload equality/recovery. Include that concrete comparison in refreshed evidence. The report distribution field was added after execution (explicit note), so distinguish postprocessed annotation from raw runner output. Real objective/task distribution remains absent and must stay labeled synthetic coverage; vector/RAG semantic completeness is not established by counts.

### P2 — self-review checkboxes and inventory contradict explicit limitations

Original pack ACCEPTANCE_CHECKLIST and task files mark R00–R07, R09 and R10 V checked despite their report limitations and the independent checklist saying no V has occurred. R09 even has checked V and independent reviewer pending on the same line. R20–R23 use nonstandard `[~]`, which is not an independent approval. R22 inventory still labels its own card IN_PROGRESS and report absent while report says pack closed. CURRENT_REMEDIATION_STATUS headline pins 5c8fcf55, its front surface table says R02–R23 OPEN, later logs say self-review PASS, and independent checklist reviews 78c2c8f6 although latest changes are at 8cc94cf5. Preserve history, but create one authoritative current table, bind final reviewers to full HEAD plus actual dirty hashes, and only check V for the scope a separate reviewer actually assessed. Independent review is not intrinsically Human-only: original cards require separation from implementer, not a human identity for all code review.

### P2 — R20 value classification is correct; historical validation needs scoped refresh

Current gbrain.py and GBRAIN_REWARD_POLICY.md exactly match R20 pins. `experimental_storage_metadata` accurately classifies write recency/frequency; reward is not authority, semantic truth, maturity or measured task utility. No production reward-selection consumer is claimed; original R20-A3 expressly permits documented consumer absence, so do not invent a consumer or demand a utility experiment to close this metadata-scope card. The recorded 40-pair latency sample (~53.7 ms average) supports only that fixed-scale measurement, not production economics or reward benefit. tests/test_gbrain.py pin differs, so strict R00 current PASS needs matching fresh test/evidence. The official wiki SQLite KGBinaryValidator is not a GBrain GraphML gate; retaining NOT_RUN is correct, not reason to install an always-OK substitute.

## What can close now, and what remains external

| Scope | Correct treatment |
|---|---|
| R00–R18, R23 implementation evidence | Historical/self-review evidence exists; independent current code/QA reviewers may close the exact tested and inspected scopes. This context audit does not certify all behavior. |
| R01 live Docker residual | Latest 5c8fcf55 records real daemon RO write refusal; do not continue labeling that specific attack NOT_RUN. Native non-Darwin validation is separate. |
| R03/R04/R10 single-host behavior | Assess against supported single-host target. Multi-host/NFS is an unclaimed deployment scope, not an invented completion prerequisite. |
| R08/R09/R15 composition | Store-backed current-head resolver and contracted integration are substantive implementation/evidence work; switching global defaults or enabling real effects is not required for routine completion. |
| R19 | Harness can close as scripted contract; real preregistered experiment remains NOT_RUN until executed or explicitly scoped/deferred. No efficacy claim follows from fixture success. |
| R20 | Metadata semantics/absence of consumer can close on independent inspection plus refreshed matching verification. No task-value claim. |
| R21 | Rerun read-only migration and payload provenance on current bytes, retain real/synthetic distinction. Human cutover is unnecessary for this rehearsal. |
| R22 | Synchronize contract/evidence inventory and current review results, then close implementation acceptance only for supported scopes. |
| Human/external only | Destructive migration/cutover, production effect enablement outside current authorization, paid-provider budget if needed, release/CR-14 owner's actual sign-off. Provider unavailability and missing native target host are environment constraints, not substitute explanations for missing ordinary code/evidence. |

Historical Git evidence: `52af3bfa40ded5d72f3865f1fc4205282ddeb4e5` added R04 snapshot race seam/tests; `d56cf1c90074f4fcc2ac270224e38b4b6538b266` and `e4add6b638dcc414d5a5a6fa6ec11aafae4d2051` added R08/R10 multiprocess evidence; `6a1d4e4233dea489e32720b1fe57c3b94a07b1e2` added R02 grant cache evidence; `5c8fcf55525ebb186cf9f21f5ce22f80bcb263c8` added live Docker evidence. These are evidence changes, not independent V approvals.

## Current SHA256 scope

```json
{
  "scripts/benchmark_cognitive_growth.py": "51786ea7c3774239c468315b60c462f19a4ffdc35c900d619d59563a5de846b6",
  "src/antigravity_k/engine/cognitive/live_pilot.py": "08ec7fb4e9a091e0da4ef1a834d2a4aa1f2a11999f9c5b4cd5ad4df0992f1f44",
  "src/antigravity_k/engine/gbrain.py": "c59a19563e773a1d61bbe648b1c69f75080babdc58922d1cd6cc00aae6402201",
  "docs/ssak-ai-core/GBRAIN_REWARD_POLICY.md": "6d478f0681075a19c497e603b2693fa61b2f34a7518d730c1f6472bf3ef36c43",
  "tests/test_gbrain.py": "cc843b926f066cd139ffcdb8eb4c46d994a6bf06f8892219fe74cbd2233ad728",
  "src/antigravity_k/engine/cognitive/migration.py": "8995543bac39a7c0b519038eea7b217b5f34892846a004844d35760fdf554395",
  "src/antigravity_k/engine/cognitive/legacy_adapter.py": "dba13d0f5102bb3ab7b30b703932f41df7895edeb6ebe9d4cd09705b627b5279",
  "src/antigravity_k/engine/cognitive/store.py": "58a02a89cd66fca9ab4430ce6db0f042156d758ba35a3b1a163f0303fa777b78",
  "tests/cognitive/test_migration.py": "e5f9fbaa3a1d8e4d4d6591c9b9a5507251296804ff3193ca0f88806f53a8a445",
  "docs/ssak-ai-core/CURRENT_REMEDIATION_STATUS.md": "c7d11ad55fb05984856e6339607fc55ca6568b749dd25656e0657777dcb4d4ac",
  "docs/ssak-ai-core/evidence/current-remediation/R00/report.md": "c19ccc9f1d8de40d4d622657d83123b687860298f62493a03af0010002c6046b",
  "docs/ssak-ai-core/evidence/current-remediation/R01/report.md": "3eecb7113c899b70acddead7ae7edfa557c0c23d75fbdd500a52cf76a6a4a1a7",
  "docs/ssak-ai-core/evidence/current-remediation/R02/report.md": "89abdda2b75302273b013f4e7b4bde4d2f6ffe81983e00eb04639889d9521538",
  "docs/ssak-ai-core/evidence/current-remediation/R03/report.md": "1446cfbc68ec72469933be10c250c201506e7530f09db1028366cff41df53d3d",
  "docs/ssak-ai-core/evidence/current-remediation/R04/report.md": "54c9a791d6cda3121dcd52c651b17bc7a3d2716763f588aef7385f94cc381e90",
  "docs/ssak-ai-core/evidence/current-remediation/R05/report.md": "47de2f5da071405cb5ae9df0aa3b56ed6a873269b6ad25ee9e017c9370851de4",
  "docs/ssak-ai-core/evidence/current-remediation/R06/report.md": "ef0d471117832a25d7fd82bdbc3b3e8d6251ee7205f049a06b2029e691cea2ed",
  "docs/ssak-ai-core/evidence/current-remediation/R07/report.md": "fe1ebb60e0f97309d09756c1b50ac44c07c64128ffcaddd94b1622d58a428e7a",
  "docs/ssak-ai-core/evidence/current-remediation/R08/report.md": "1f13e820f94cab52c7c7c1047273e4a8d60aba670b6918e5850a694f2e6812de",
  "docs/ssak-ai-core/evidence/current-remediation/R09/report.md": "87ea015577801515dbb675867f197708137d948520793068e03ea8a825df602c",
  "docs/ssak-ai-core/evidence/current-remediation/R10/report.md": "c7640a64dcaa77301da4b410c39a0a47002625583e70f3f192f95c62b27091d7",
  "docs/ssak-ai-core/evidence/current-remediation/R11/report.md": "d0ef771861159eea7597a4451b6eaf72c1be8c8f33fc0556ff3eb19c19044323",
  "docs/ssak-ai-core/evidence/current-remediation/R12/report.md": "2c5503693ad507c56dcb4608bf24bb02549042562609aa488295080c2deb60f5",
  "docs/ssak-ai-core/evidence/current-remediation/R13/report.md": "cdf158e02daecf4b61d4550639ad57bebbe5c45a8af680e7e456fc5b817df4d3",
  "docs/ssak-ai-core/evidence/current-remediation/R14/report.md": "08be87b5e314605ca0366f9510e468c15f218ea24958a83123896ba373813cba",
  "docs/ssak-ai-core/evidence/current-remediation/R15/report.md": "9e8d91b0d59478dafb2059e4680a20544c8c318b2315976dd0b707765a4a5df9",
  "docs/ssak-ai-core/evidence/current-remediation/R16/report.md": "bc9c77a391e62d31bd19d97a174ee0512509be212310f37553d35c5ee17eac46",
  "docs/ssak-ai-core/evidence/current-remediation/R17/report.md": "ba1d214a6bec9e65ef0d95a0ef365079d96fcf000266d76d04dfac49f7506beb",
  "docs/ssak-ai-core/evidence/current-remediation/R18/report.md": "44fc671854c5de9aad7054b4e28f205245a4aae62df7021614878119a5c90cb7",
  "docs/ssak-ai-core/evidence/current-remediation/R19/report.md": "1d6eb29b904e042855213b6ad8057273451dde0b09f83c5bbdb35a55ee60b66c",
  "docs/ssak-ai-core/evidence/current-remediation/R20/report.md": "0e814702e24bb80640ce3060e95947974ea83c1d1d29a2ad14bac66dd1324ed3",
  "docs/ssak-ai-core/evidence/current-remediation/R21/report.md": "52e13d665bcd3a9993a827b7e7c2c82b6409dd90529e369dcaaa3dddc4b6b250",
  "docs/ssak-ai-core/evidence/current-remediation/R22/report.md": "42065710062fdc1dce41b4dd90149e46e0d6bd7b7865be165e781ddf7cd81186",
  "docs/ssak-ai-core/evidence/current-remediation/R23/report.md": "40aa53273ba75ab80a2013c089640d12c0f1c80dc89c69e4437b7e8c9dfc0b23",
  "docs/ssak-ai-core/evidence/current-remediation/R21/migration-report.json": "1d7fd27a4234088f680a0890b6803f3e70321bffc6dc1ab5d51ec70440dd8bc9",
  "docs/ssak-ai-core/evidence/current-remediation/R22/inventory.json": "139055f923850f357a7773353a22943aa2a754342a3d3fe6bcce2de2bc9e33e2"
}
```
