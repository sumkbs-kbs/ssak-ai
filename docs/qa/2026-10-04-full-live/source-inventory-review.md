---
title: Current-pass owned source inventory review
date: 2026-10-04
tags: [qa, inventory, ownership, report-derived]
status: inventory-collected
owner: core_batch_review
evidence_scope: owner reports and reported SHA-256 values only
---

# Current-pass source inventory

This inventory collects **26 production files and 25 test files (51 unique paths)**
from the current pass's owner reports and SHA-256 records. It does not infer ownership
from the repository's large pre-existing dirty tree. All paths are relative to
`/Users/mr.k/program/coding/ssak_comp/Ssak-Ai`.

Parent-provided HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.
The earlier core review independently checked that full HEAD. This collection did
not use Git, import the application, read private home data/raw application logs,
or invoke any model/provider/network call.

The values below are **owner-reported hashes**, not a replacement for root's final
source freeze/hash manifest. The explicit-search worker's report appeared during
collection; its three paths are included as a reported candidate pending root's
final freeze and actual Search ON retest. No overall PASS is asserted here.

## Ownership and reported hashes

### Quality output contract

Evidence: [quality-verification.md](quality-verification.md), [core-batch-review.md](core-batch-review.md).

| Kind | Owned changed path | Reported SHA-256 |
| --- | --- | --- |
| production | `src/antigravity_k/engine/quality_gate.py` | `1d905c500a60a7f2f722b8d9118e73c8910ee73e766082e8336669e4de2bfd55` |
| test | `tests/test_quality_output_contract.py` | `2df7fdad881dde21a937d187c7cfcd26661411cedc1d2bf54252d8a5d236891a` |

### Qwen repository prompt budget

Evidence: [budget-report.md](budget-report.md), [budget-sha256.json](budget-sha256.json).

| Kind | Owned changed path | Reported SHA-256 |
| --- | --- | --- |
| production | `src/antigravity_k/engine/context_budget.py` | `9eea0d25f007f1cb803f90ac0f437d74b72742822972da7b295020e8aa945621` |
| test | `tests/test_qwen_repo_prompt_budget.py` | `a61c338523b00bdce4cbf763658e34bb5bb0a908838b957b0523e6d64717e29f` |

### Read-only profile durability

Evidence: [profile-findings.md](profile-findings.md).

| Kind | Owned changed path | Reported SHA-256 |
| --- | --- | --- |
| production | `src/antigravity_k/engine/user_model.py` | `ecfb1629dc4ad9e586c2c32ba7c1b2ada60c12960b824d1488ee74e6a43110ee` |
| test | `tests/test_user_model_request_policy.py` | `6f4ab1cdd55f1a568545c9ef5e881b4097144ff2ab2167b8f5a48ed821b6157a` |

### Notes keyword search

Evidence: [notes-search-report.md](notes-search-report.md).

| Kind | Owned changed path | Reported SHA-256 |
| --- | --- | --- |
| production | `src/antigravity_k/api/routes/vault_api.py` | `54bc1e8527adb8dc5e98e6041ca412fab857edc2f37b1ba7a63915f49c92fa7a` |
| test | `tests/test_vault_keyword_search_api.py` | `7adcf5f9714ea167041cc9edb1f30d9aaeb537f8268656275aebbf26a5260576` |

### System API boundaries

Evidence: [system-boundary-findings.md](system-boundary-findings.md).

| Kind | Owned changed path | Reported SHA-256 |
| --- | --- | --- |
| production | `src/antigravity_k/api/routes/system_api.py` | `610334086c50b0b0e0ff09b57d3ae45e7b46739be8316baa7627ade67d35c7a6` |
| test | `tests/test_system_api_boundaries.py` | `31727d560cfffb0d299c6fd640ca73d2703f30628bdd6fc5b796e980de220c67` |

### Conversation append/compact/fork validation

Evidence: [conversation-validation-report.md](conversation-validation-report.md), [conversation-validation-sha256.json](conversation-validation-sha256.json).

| Kind | Owned changed path | Reported SHA-256 |
| --- | --- | --- |
| production | `src/antigravity_k/api/routes/conversation_api.py` | `2f78dae05b39f192e37cec047e5fb88a7f08bf77b451314b04f5a5af60889a69` |
| test | `tests/test_conversation_compact_validation.py` | `2d2242c3dc54b7e5ff339715cd64e9d98008372c5b51aebd204f3df4d63ea01f` |
| test | `tests/test_conversation_request_validation.py` | `b639122c2ebc740ba58dc83d7c6c0dfd4ce2d0b4754571239a0117fd02df8758` |

### Skills catalog/search authentication

Evidence: [skills-auth-report.md](skills-auth-report.md), [skills-auth-hashes.txt](skills-auth-hashes.txt).

| Kind | Owned changed path | Reported SHA-256 |
| --- | --- | --- |
| production | `dashboard/src/pages/SkillsPage.tsx` | `e46238380772d817a34ca6aa42b2941aae34ef5aac325afb58cb9e77013a51db` |
| production | `dashboard/src/pages/skills/skillsApi.ts` | `2f0f008319da35f141386d4a0ee18c69b3787765f6fa8d54836d0d4f25a21e2e` |
| production | `dashboard/src/pages/skills/useSkillsCatalog.ts` | `51e1101608a032cf3c4adba391324ad33765605eab078dedf60e0e485a5d7f07` |
| production | `dashboard/src/pages/skills/SearchTab.tsx` | `8460fedd18c419f576651c3dff7034ca16b889bcb022095b34a765919e6c456a` |
| test | `dashboard/src/pages/SkillsPage.test.tsx` | `ff907c12f94a4198144ceec53733dacb0eb21e69692dacbf78b4ea9a5d6d595f` |
| test | `dashboard/src/pages/skills/skillsApi.test.ts` | `2306d1ebad41608644807ed33586a3bbe7339bbaa48e06f4e5e25d9c1f7c7d3c` |
| test | `dashboard/src/pages/skills/useSkillsCatalog.test.ts` | `5d1b8e67f346e86933d3c085f0004267fb3ef51dab7d5dc19c867693e9df6109` |

### Skills publish authentication

Evidence: [skills-publish-auth-report.md](skills-publish-auth-report.md), [skills-publish-auth-hashes.txt](skills-publish-auth-hashes.txt).

| Kind | Owned changed path | Reported SHA-256 |
| --- | --- | --- |
| production | `dashboard/src/pages/skills/PublishTab.tsx` | `202d127b4f6df7bdb83b12ae17c3ed69565966efe0efec7258977059e1922d64` |
| production | `dashboard/src/pages/skills/publishSkillsApi.ts` | `5f4efd2b554f43d716343b137577944b7f2dc474c9d4ca362a0ec3e54902132c` |
| test | `dashboard/src/pages/skills/__tests__/PublishTab.auth.test.tsx` | `8b4801838100706f1dae69d399e528f75a36c41a44137bc5d6843f25568e8889` |
| test | `dashboard/src/pages/skills/__tests__/PublishTab.requests.test.tsx` | `85c8d1f91aad1514f26a3e1538e92f22e6de49c3d634005681a507d9148d0e67` |
| test | `dashboard/src/pages/skills/__tests__/PublishTab.test.tsx` | `a8009442b93c6a43c8c50047a2058c649a532f65f05d9180f24d49a0945db2b5` |

### Bridge CLI/auth and palette contracts

Evidence: [bridge-cli-auth-contract.md](bridge-cli-auth-contract.md), [bridge-palette-contract.md](bridge-palette-contract.md).

| Kind | Owned changed path | Reported SHA-256 |
| --- | --- | --- |
| production | `src/antigravity_k/engine/agent_bridges.py` | `2707235869471bfb990a47f5d8e6e10a03710b779efaacf136484b2df85da258` |
| test | `tests/test_agent_bridge_auth_plan.py` | `ff6707a16af0e74556f037931029afc60b9cd01322bb10ee6477f2f2c1cd98e3` |
| production | `dashboard/src/pages/AgentStartPage.tsx` | `b25399815bac5f949f64c40a3c90a0c936ee2e79021c281bc418b627ac9221cb` |
| test | `dashboard/src/pages/AgentStartPage.test.tsx` | `76671be4f5962c74d544ffe6fee29a388b04449c3dc4fa65b22a7b97550431d0` |
| production | `dashboard/src/pages/WikiPage.tsx` | `cc962f102c7732cd117d34a820721fb1e4d40accc9a9963e6de24e57dde940cb` |
| test | `dashboard/src/pages/WikiPage.commandActions.test.tsx` | `b37bffcec16443c19c964f826f16034aa83cac845a16b7cf7d73c8357e977601` |
| production | `dashboard/src/features/command-palette/commandRegistry.ts` | `b2d2c947c615c568d9e4abc3d9e53ccb040e87d302cae19ea8454f277ba20bfd` |
| test | `dashboard/src/features/command-palette/commandRegistry.test.ts` | `cda38becbc81566102f2e1d92ba2cc71445ea6923dc3381d7ee47934b3cc751d` |
| test | `dashboard/src/features/command-palette/commandRegistry.auth.test.ts` | `bf90d75aa0318ed00d69dfb5c66867e8d4a49ad5cffbdf5234d4790c8c114679` |
| test | `dashboard/src/features/command-palette/commandRegistry.selectionRace.test.ts` | `e75d3cbe9f99dab893b02406f257dd6309ee4011d7ffe38d6a275cf1808eb496` |

### Studio truthful state

Evidence: [studio-implementation.md](studio-implementation.md), [studio-code-review.md](studio-code-review.md).

| Kind | Owned changed path | Reported SHA-256 |
| --- | --- | --- |
| production | `dashboard/src/pages/StudioPage.tsx` | `63fc39c0ab8aca62c8a80cfb8c1d8d4c59c07e18920cdf5c520b25f135b70c92` |
| production | `dashboard/src/pages/StudioPage.css` | `e633e1934db65065e8bb5a59d3999b13cd5951cb58ba504b49b46fa7b6a6c6d9` |
| production | `dashboard/src/pages/studioCapabilities.ts` | `860001ed1fee34025e35d09e92f6b4b05c5cc4a3991f79abddce632231b9d3d9` |
| test | `dashboard/src/pages/StudioPage.test.tsx` | `d729490d2e67e5f28795f5e652185a847ce5b4c4a428a2c3584c6622ca9325ff` |
| test | `dashboard/src/pages/StudioPageTruthfulState.test.tsx` | `dd074d5edfa008650b4bc6a6ce0939ae2c4d240eb1254ed2f0c60775611c80b3` |

### Model runtime status

Evidence: [model-status-findings.md](model-status-findings.md), [model-status-source-hashes.txt](model-status-source-hashes.txt).

| Kind | Owned changed path | Reported SHA-256 |
| --- | --- | --- |
| production | `src/antigravity_k/engine/local_model_discovery.py` | `1023e489d4eb0460e330736c5b70f4a3ffb2af3ae4f2b500e28d9d8d259ea818` |
| production | `src/antigravity_k/engine/ollama_process_snapshot.py` | `45137a8920e649b01b866fff6fa19c0fd5d57e5ebb5c05f0cda6e902872d3db8` |
| production | `dashboard/src/pages/ModelHubPage.tsx` | `787705754d1d979d1d708aa9e73d4150b9251bc12a669b45a6031766f87d8417` |
| test | `tests/test_ollama_runtime_status.py` | `002bfcf6c01c496a3e1a85cecb3d6dd4cf60d1ce9c11d5173f934a96bca38039` |
| test | `dashboard/src/pages/ModelHubPage.status.test.tsx` | `281b24108c9365b8c300f1a605daed2714c2719b4e31bb4e2f00037c3f299fc9` |

### Data extraction authentication

Evidence: [extraction-fix.md](extraction-fix.md), [extraction-source-hashes.txt](extraction-source-hashes.txt).

| Kind | Owned changed path | Reported SHA-256 |
| --- | --- | --- |
| production | `dashboard/src/pages/DataExtractionPage.tsx` | `bb692638a7796301f4af27681bfc598302c137342ab1498f07d5e91364060a58` |
| production | `dashboard/src/pages/dex/extractionApi.ts` | `fd76e2267c471d86bfb939d4d34f9a877653f9a908aea6f53be2941b964eec83` |
| test | `dashboard/src/pages/DataExtractionPage.test.tsx` | `ee2c17f471778d1032d7501ae537381eb0c6a9184da50757deab3c4f5cb6ba66` |

### Explicit search request contract (reported candidate; root freeze pending)

Evidence: [search-request-contract-report.md](search-request-contract-report.md).

| Kind | Owned changed path | Reported SHA-256 |
| --- | --- | --- |
| production | `src/antigravity_k/engine/direct_task_execution.py` | `a0c186aedfe53a8b2c1ed4f95ee6a3807cf5823860e83f4f9fa752abd004f1f7` |
| production | `src/antigravity_k/engine/tool_loop.py` | `bfe26cc91815554a19796312cc60eae9103765517d49dc2509f0dc575222f8bf` |
| test | `tests/test_search_request_contract.py` | `f52b1351dfacf2ec4df9b4b96d5538372e887293ed9694d5ed674e39e3712d35` |

## Reconciliation and exclusions

- The final `conversation-validation-report.md` and matching JSON supersede
  `compact-validation-report.md`'s compact-only source hash
  `ba5f8cdbd77ea0445780ae65b13fb69119348d3fc39563d941948d59f2fa5f53`.
  The current conversation source hash is
  `2f78dae05b39f192e37cec047e5fb88a7f08bf77b451314b04f5a5af60889a69`.
  Both new validation tests are included. The model contract
  `src/antigravity_k/api/contracts/conversation.py` is explicitly unchanged and
  is excluded even though the worker fingerprinted it.
- `tests/test_final_prompt_budget.py` was exercised and fingerprinted by the
  budget worker but remained byte-identical to that worker's captured baseline.
  It is excluded from this pass's changed-file inventory even if it differs from
  the repository HEAD due to earlier work.
- Both `StudioPage.test.tsx` and `StudioPageTruthfulState.test.tsx` are included:
  the scoped Studio code review explicitly inspected the current diff for both,
  and the implementation report supplies their final hashes. The scoped
  `StudioPage.css` is included; shared global styles are not.
- Existing regression-only references are excluded, including
  `tests/test_vault.py`, `tests/test_data_extractor.py`,
  `tests/test_search_extract_e2e.py`,
  `dashboard/src/pages/skills/__tests__/publishHistory.test.ts`,
  `dashboard/src/pages/__tests__/StudioPageRecipePreset.test.tsx`, and other
  existing ModelHub tests. Running or fingerprinting a dependency does not
  establish that its owner edited it during this pass.
- Shared API clients, CLI entry points, auth-policy modules, `wikiStore.ts`,
  backend Studio/training contracts, `src/antigravity_k/api/server.py`, and
  `src/antigravity_k/api/auth_routes.py` appear as dependencies or harness
  production seams, not as edited owner files in these reports. They are excluded.
- Generic feature-inventory source paths in `INVENTORY.md` are inspection
  references, not ownership claims. Unrelated dirty files and any unowned path
  are excluded.

## Retained QA harness source, separate from product/test edits

The following ten scripts are retained QA harness source in
`harness-source-manifest.json`. They are separate evidence artifacts and are
not counted among the 51 product/test paths above:

```text
docs/qa/2026-10-04-full-live/manual_api_cases.py
docs/qa/2026-10-04-full-live/manual_api_driver.py
docs/qa/2026-10-04-full-live/manual_api_fixture.py
docs/qa/2026-10-04-full-live/manual_boundary_cases.py
docs/qa/2026-10-04-full-live/manual_boundary_fixture.py
docs/qa/2026-10-04-full-live/manual_browser_cases.py
docs/qa/2026-10-04-full-live/manual_browser_fixture.py
docs/qa/2026-10-04-full-live/manual_cli_driver.py
docs/qa/2026-10-04-full-live/manual_extra_cases.py
docs/qa/2026-10-04-full-live/manual_extra_fixture.py
```

## Collection limits

Ownership and hashes were collected once from owner evidence, with a second
read-only reviewer independently covering bridge, Studio, model-status, extraction
and harness evidence. No request was sent to all workers to repeat their investigation.
The knowledge graph was attempted for the three parent-provided pending search
filenames and returned transport failure; bounded exact-filename fallback only
confirmed those paths. All other source ownership came directly from reports.

Root owns the final full manifest, current source hash confirmation, actual live
browser/Qwen/API retests, and the overall acceptance decision.
