# Cognitive core commit-group review

- Review scope: the 63 paths in `/tmp/ssak-publish-cognitive-20261004.paths`, compared with Git baseline `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.
- Candidate aggregate SHA-256 (sorted `sha256  path` lines below): `b979ed3e7ff4c0e7038b4c70e2383b10fd163d148905643867be655949aaa7a2`.
- Diff inspected: 5,749 insertions and 1,101 deletions across the explicit source/test list. `git diff --cached --check` produced no whitespace errors.
- This is a source review snapshot, not evidence for a future commit SHA. It does not replace the running isolated test result or post-hook validation.

## Finding summary

### CRITICAL

None.

### HIGH

None. The reviewed connections are complete: server lifespan calls the opt-in bootstrap; bootstrap only installs a trusted `ProjectActiveConfiguration`; the installed service has durable journal/history and canonical-store dependencies; the active routes use that service. The recovery path retains compare-and-set publication and refuses stale or foreign claims. The live adapter uses a per-trial workspace and checks its resolved target before dispatch.

### MEDIUM

1. The strict `programming` skill perspective is not fully met by the existing and touched Brain wire contract. `src/antigravity_k/engine/cognitive/brain.py:81,110,149,183,189,217,428,433,446,478,523` exposes `Mapping[str, object]` payloads. These are JSON/wire-boundary values, so this review found no concrete dispatch or parsing failure; however, they remain untyped escape hatches and make a schema change less discoverable. This is a follow-up typing-debt item, not a release blocker for this already tested compatibility boundary.

2. `src/antigravity_k/engine/cognitive_surface_legacy_brain.py:29` retains the earlier legacy behavior of translating every generator exception into a failed thought. The extraction does not introduce that behavior, and the caller deliberately uses the failed-thought outcome, but it still conflicts with the strict programming preference for named exceptions. Keep it as compatibility debt unless the model-port error contract is narrowed in a separately tested change.

### LOW

1. Several large legacy cognitive modules remain over the remove-ai-slops 250-pure-LOC guideline (including `growth.py`, `learning.py`, `runtime.py`, and `migration.py`). This group moves cohesive units out of two such modules rather than adding another layer. No unnecessary extraction, deletion-only test, tautological test, prose-pinning test, or implementation-constant-only test was found in the reviewed additions.

## Skill perspective

The `programming` and `remove-ai-slops` skills were consulted before review. The diff does not violate the remove-ai-slops perspective: new modules separate concrete responsibilities (active composition, head resolution, request binding, recovery records, live context/training/execution) and tests cover observable safety boundaries such as canonical-head drift, one-effect execution, recovery compare-and-set, workspace jailing, and provider-derived output. It partially violates the programming perspective through the MEDIUM wire-shape annotations and the extracted compatibility broad catch above; no `Any`, `cast`, or `type: ignore` was found in this candidate group.

## Recommendation

- codeQualityStatus: **WATCH**
- recommendation: **APPROVE**
- blockers: **None**

Proceed only after the root-owned isolated regression suite and post-hook type check complete against the staged bytes or their resulting formatted bytes.

## Candidate file SHA-256 manifest

+07b94e056b0289ade4e2ffcf62c685017167728bad5dc86d8c7acc4faf5d9f2f  scripts/benchmark_cognitive_growth.py
274a057b06492e9f4ca1c09bbb6da72a48430aa22fdc75f0fcccce47c20e77c0  src/antigravity_k/api/dependencies.py
524496f292b9b1ea56f8f5ec60ae08d1d28d356d6847179e39474e2ab0546046  src/antigravity_k/api/routes/cognitive_active_api.py
8cdafc0f69b4a65ceda843d48626e5350c344a622b7aa570c5b804f8b5b03ae3  src/antigravity_k/api/server.py
f46b654bd5088ca72b600ff06f7687118c778522243df9edc6c7bfcbb9e74b39  src/antigravity_k/engine/cognitive/action_admission.py
60bdf4f853368a195d20b0557dbb29a20e55fb293ae1df1b986fcdd3cc04dbf4  src/antigravity_k/engine/cognitive/action_journal.py
26811552ea5cad1e970fe7eda7867a02a2bc8994ae5f597011bde156ba7d2db2  src/antigravity_k/engine/cognitive/action_lifecycle.py
52ea1fad166a1837ea5e4f31ef8474354aa91025f6dec77a1f711e7e3e857bf8  src/antigravity_k/engine/cognitive/action_recovery.py
f485d135885ffc701b1fe4a525b7bc128bdee492246c1f8e6dfe0b62c3b9da1c  src/antigravity_k/engine/cognitive/action_recovery_records.py
a2c254eb0f16792e377b68059188a49faa1903a48d66560f59048e2c3a7109c7  src/antigravity_k/engine/cognitive/action_types.py
6feda593081a7eead98630ebe7e726d4d184d7debde77358a2c66871864ed38a  src/antigravity_k/engine/cognitive/actions.py
7317a39d7c40f65cbce3232d33a3954a36d6f5f541b5fde032fd14b7a5a83ecb  src/antigravity_k/engine/cognitive/authority.py
422cb28624be5c166c130f4a6705d81dc4b3c0a989da3d1f44578dc1fea2e393  src/antigravity_k/engine/cognitive/brain.py
bb3e1d677ece3580228091a0b682bbf4fb58cb4f3c64e8088e50fa701e59c4c1  src/antigravity_k/engine/cognitive/brain_context_render.py
6649051f932ffb4b5ee1912a6e25c5d0cbe2441984b069f696d28957bb19991d  src/antigravity_k/engine/cognitive/experience.py
c472511c2dfe4436f79f80b7dbd1fa354cf024d3b72d32eb1756384ebe689816  src/antigravity_k/engine/cognitive/growth.py
8b4b7b78ff36e8a5cceb606d2c3f52fbad8d753187bcc9d767f91e1e6f687d0b  src/antigravity_k/engine/cognitive/learning.py
58e67d1d67c8060b02de6d1c57c77dcf03dc3aff0835a9d5e588bc2ec2ac0a58  src/antigravity_k/engine/cognitive/live_context.py
99e2c949975e643c085ab9cb58d85f96d094839c70275c0e2f2aabd824b99551  src/antigravity_k/engine/cognitive/live_learning.py
a02433a607a6c07997d44ef1bea8dd957f796bc6fd353d4b8fef9da69e9fc8ab  src/antigravity_k/engine/cognitive/live_pilot.py
dd7d88dad9bf36f574b879edd98da7c0600e4d8659c35dddae78dff28573601f  src/antigravity_k/engine/cognitive/live_provenance.py
b2eedca7110f903b37385b0057a2bee4a0c177ea9e2f036325c58eeb95c25b8c  src/antigravity_k/engine/cognitive/live_training.py
bbad1e0f4020e43a7d9a455212fd2f42a8be4538ad7272a2b9323f18b40f0a6f  src/antigravity_k/engine/cognitive/live_trial_adapter.py
501a5f9ffc5ee95c76d2591c6fa900da45cbdb2e247262d0070a080b0e1532e2  src/antigravity_k/engine/cognitive/live_trial_execution.py
4465576fdf5bd75667be53b92f39bf4fdae08d7d015dbfe570739147060a09c5  src/antigravity_k/engine/cognitive/live_trial_types.py
5ea53f88a9544baed6d58da672b9a63f595d766b4f5114d942ff7656908307a9  src/antigravity_k/engine/cognitive/migration.py
afe99ffae7ebb74d29e34a82aab34da2a119317e437529ddcca53e89be204945  src/antigravity_k/engine/cognitive/models.py
d18548cfa59870667f5080b92bb218c6b7b7bb1ec310bc40a287f143bc9ceea8  src/antigravity_k/engine/cognitive/protected_targets.py
0ff93d8ee9e32b1f0b01dca53069c166baf2569a39545faca2674adfc4ee2683  src/antigravity_k/engine/cognitive/runtime.py
a92476d93628bd71b488ada19e925809fb7223d3b037d2f17832052783cbf8c0  src/antigravity_k/engine/cognitive_active_composition.py
6734b842a2540bc46b283bad686d6f53ca399aa478b62b10e9f0ba16eb7840a1  src/antigravity_k/engine/cognitive_active_heads.py
2d66862941a20743168f52ee27fe639de74b9509d2218a990a1b73a4923c69db  src/antigravity_k/engine/cognitive_active_requests.py
d1f9533cb1f2eecb49b770af2efd810e730afad3bea294c21e2b7e5600b54d79  src/antigravity_k/engine/cognitive_surface.py
54d0fff11a328608014c7fbbfd41e8d770f9b792bc4c2c1b44aa6ec81663a2f9  src/antigravity_k/engine/cognitive_surface_brain.py
454e4c5f0f96d8e42fb3c04c139617887fd751021bb41052c22830a2d2109b34  src/antigravity_k/engine/cognitive_surface_legacy_brain.py
9d62e2afd5c52a7edbcf6c0accb358ce71a579f956607f54ef97338c89be783d  src/antigravity_k/engine/cognitive_surface_recovery.py
5707fb63aa8d0beca3b6806ab42886e2c42fd3b0a095a05ba6c97595ad5b8211  src/antigravity_k/engine/cognitive_surface_types.py
2b7085b8ff1c2a27bddc8d40f48c127f65c1fe9a213d24486ee09b89f3d6377f  src/antigravity_k/engine/local_live_model.py
f108c119c0375557925d35888869d24b6c7f0f4cd0a7530a7d6c3ec3a5d59e62  src/antigravity_k/engine/registered_live_cli.py
c3be7410b445969b713e3f87bf42755d5ff24abfbfcf499e4391cbad72c912b5  tests/cognitive/test_action_journal_schema.py
0d1cbdf1122180864b603dd945127c07f7d4f3571a81f96a03c582f249ad5057  tests/cognitive/test_active_api.py
b2f1f53af5653140881645107aa1780fa74519ec758e0b567780d911a96b16cd  tests/cognitive/test_active_composition.py
b2e1bcaed628c849874b27897724365b08250d011fa5b09972fcc6ede9740c8c  tests/cognitive/test_active_expansion.py
38c31ac70f2854681fcaa16bd3f3b255daebbe451e7802503bf3bcfd18f58fca  tests/cognitive/test_additive_wire_compatibility.py
544e3104813aa282dea796390b089cef0131db4c606535c088501713d16b6def  tests/cognitive/test_brain.py
6440cc146f6f7f5fc4b87720df11fb67e1a387d1194dd10fd34ee4de95dd0bd4  tests/cognitive/test_brain_bridge_regressions.py
d813ab7d494a5a789ca19720a10491945eb8fa4974df9e1e5a04d88f69470c10  tests/cognitive/test_brain_receipt_bridge.py
71c4f7d7887bec8bfb2d74bb89df356118fc51c971fec103e996c9abb512b732  tests/cognitive/test_episode.py
8046fd840fd527d88a0a8703393a46be610a21c09dd97b6071d8f418570484cf  tests/cognitive/test_episode_plan_binding.py
e190ce506f3f879af0f64f17612da0501f951c3f323f95e89976b5d720286bbf  tests/cognitive/test_experience_roundtrip.py
96a7622a86c6f1a5c2aa3bf8e3e8838b778a4514933759339248ecdce6fc6862  tests/cognitive/test_final_authority_boundaries.py
da761fc1cd56fd2cab5644ed438715e68fd6e27af55c8412b1cb0aa8861c0a02  tests/cognitive/test_learning_experience_binding.py
1b16d29a68e78ebd74e1e8394eadf78d9afb401d124c3d39700046f0350910a2  tests/cognitive/test_live_context.py
ee67925afc308322edf035c654c9775b8303dc8a8972ad4a2880e5dc36781e81  tests/cognitive/test_live_mechanisms.py
452b68a4fef2fd434c4e92a6d27a642f557e79bc07e040efa3fe5d29389075e6  tests/cognitive/test_live_pilot.py
0b827f5b01a924756cd5b04999638ab3853ce00e58c3941ebf3f952f873ff0c2  tests/cognitive/test_live_policy_ledger.py
502a28f672db0f78871098c2eec8373a54860ac6aad2be948256a5359faee4d6  tests/cognitive/test_live_trial_adapter.py
c7caab79468f9b56596df581481d381fc5c7052253f0aa67854f08ab39835ad0  tests/cognitive/test_local_live_model.py
067c335d195cfb0f686ee7d423abb028d873c6a88f1d9321e6938a3fec385820  tests/cognitive/test_migration.py
380b62abc771499dabfb75b9f57968ea535606e91863c76a068357de9d4ac1b4  tests/cognitive/test_migration_snapshot_lineage.py
00e6ccd76376d7a815c9ef0a24216094c0b368f83ef28023f7ddbf91a5e0c6f3  tests/cognitive/test_observation_atomicity.py
242112134840c270dc26705e305884e234ac53933fb1636932fa520e7f07d15b  tests/cognitive/test_runtime_experience_lineage.py
bddd77a7f2957947f705c391a7233e590715e89adebd0e64b30e74c780ab1878  tests/cognitive/test_surface_lifecycle.py
