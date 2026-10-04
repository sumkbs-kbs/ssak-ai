# Current finalization review — 2026-09-27

## 현재 결론

지원 범위인 **단일 호스트·명시적 opt-in 실행 경로의 수정과 통합 QA는 통과**했다. 최종 QA는 **1,125 passed / 의도된 skip 1 / 실패0**이며, source freeze는 아래 manifest에 고정되어 있다. 동결 소스로 **실제 로컬 모델 Fresh/Mature 등록 실험(v8, 108 slots)과 별도 54-slot 소비 ablation이 모두 종료**됐고 원시 trace와 독립 재계산이 일치한다([LIVE_RESULTS](live/LIVE_RESULTS.md)). 결과는 synthetic append pilot 범위의 조건부 효과이며 확증 표본이나 일반 성능 주장이 아니다.

| 검증 | 실제 관찰 / 한계 |
|---|---|
| 통합 테스트 | 1,061 cognitive +65 runtime =1,126 collected; 1,125 passed,1 skipped, 기존 warning1. 서로 겹치는 선행 suite 수를 합산하지 않음 |
| Skip | 공통 harness 계약 자체에는 소비자의 판독 규칙이 없어 제외된 self-probe1건; 환경 부족이나 Docker 생략 아님 |
| 실제 HTTP·재시작 | 인증 없는 요청401, 최초 dispatch1, 재시작 뒤 DUPLICATE_ACTION/추가 dispatch0; canonical6건·digest6건 |
| 실제 migration | 56,961건 import/replay/index/digest/rollback 및 전량 payload mapping 비교; 원본 unchanged, 실제 objective/task0/0은 synthetic와 구분 |
| 정적 검사 | 변경 Python64파일 Ruff 통과; production39파일의 type error11건은 모두 baseline과 동일, 신규 error0·import cycle0; warning470건은 별도 공개 |
| 실험 해석 | operator가 사전 지정한 HUMAN_REQUEST context-depth 가설을 실제 TRAIN/held-out validation으로 검증; 자율 의미 가설 발견이나 일반 지능 향상 증거로 확대하지 않음 |
| 실제 모델 v8 | 192 provider calls(FINAL 183), 108/108 closure, 재계산 issue 0; task 단위 retries MATURE−FRESH −0.611(11 better/0 worse/7 equal), success 45/54 동일(AUTHORITY_RESHAPE 3 task는 양 arm 모두 BLOCKED_READINESS로 미기록), safety 0; verdict PASS(pilot-only, 확증 표본 미등록) |
| 실제 ablation | 54/54 slots, 100 calls, issue 0; retries full 0.389 / no_experience 0.667 / no_policy 1.000; Experience 기여 −0.278(5 task), policy/depth 기여 −0.333(6 task), 결합 −0.611(11 task); success 15/18 모든 조건 동일; 입력 감사에서 ablated 조건 Experience 노출 0 |
| 운영 경계 | global ACTIVE·파괴적 cutover·CR-14 운영 승인은 별도. Multi-host/NFS는 지원·검증 주장에 포함하지 않음 |



**Status: final integrated QA PASS; registered live run (v8) and conditional ablation COMPLETED with independent raw-trace reconciliation.** v7 was NOT_COMPLETE (external session termination at 169 FINAL calls; preserved, unused). Base HEAD: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382` plus uncommitted fixes. Unified source snapshot: [final-source-manifest.json](final-source-manifest.json), 1,465 files, fingerprint `ed6c1e7176ace5d90952117cce865e4ca8bfe7f6a4cc7859f70409b8228631e2`. It includes the concurrent-schema fix, material final-plan guard, corrected live Context/Experience evidence, and v7 registration/package inventory. [V5 source snapshot](v5-source-manifest.json) and prior registrations remain historical; their results are never silently transferred to the final tree. Individual scoped reviews apply at their recorded dependency hashes.

The first independent reviews found actual defects and returned FAIL/REQUEST CHANGES. These reports remain historical evidence. Scoped corrected findings now have separate independent PASS reports. The earlier self-review PASS labels and checked V boxes are not independent acceptance.

| Card | Scope | Current verdict and actual limit |
|---|---|---|
| R00 | Source/evidence provenance | Unified manifest and C01–C09 source/test/spec pins are current; old self-review checkboxes no longer substitute for independent results. Final live artifact index: [live/copied-sha256.json](live/copied-sha256.json). |
| R01 | Protected OS execution boundary | Scoped independent PASS: real local Seatbelt relocation/direct/symlink attacks refuse; allowed sibling operations remain. No universal-OS claim. |
| R02 | Authority attenuation/lifetime | Scoped independent PASS: current ancestry operations/constraints/issuance/expiry checked; replay/digest and revoke tests remain in final suite. |
| R03 | Transaction identity | PASS for supported single-host store identity/recovery cases; unchanged store bytes and final suite. Distributed locking unclaimed. |
| R04 | Migration snapshot lineage | Independent PASS for immutable SQLite capture and WAL ABA; final real-source rehearsal retained. |
| R05 | Required context | Independent PASS: required selected content and missing-record refusal verified; provider call0 on incomplete input. |
| R06 | Relevance/history/budget | Independent PASS for complete selected L0–L3 payloads, conservative serialized budget and explicit omission; not arbitrary provider-context proof. |
| R07 | Feedback and final plan | Independent PASS: typed feedback/receipt reaches Primary; material risk/action change without explicit prepared plan defers; no stale final effect. |
| R08 | Current authoritative admission | Independent PASS: canonical heads/digest/readiness re-read before effect; actual state successor at admission refuses. Not an atomic distributed external-effect transaction. |
| R09 | Durable action records | Independent PASS: stable receipts/intent and canonical result detail, persistence failure ordering and restart linkage. |
| R10 | UNKNOWN/reconciliation | Independent PASS for observation CAS/crash/replay/receipt-less recovery; concurrent schema initialization fixed and included in final integrated PASS. |
| R11 | Experience continuity | Independent PASS: operational-only/deferred/selected distinction, full lineage, real-store restart, stable material replay and no duplicate publication. |
| R12 | Evaluation axes | PASS: observed outcome/execution and semantic decision assessment separated; missing assessment stays UNKNOWN and no-read failure is not MATCH. |
| R13 | Policy and actual consumption | PASS in pilot scope: validated policy `live-validated-v1` (extra_depth 2) actually drove MATURE selection; live ablation measured Experience consumption −0.278 retries/task and policy/depth −0.333 retries/task, success unchanged. Hypothesis remains operator-prespecified. |
| R14 | Brain adapter | Independent PASS for structured context/digest/material delta/request and receipt feedback; final local protocol driver2calls0external confirms actual bridge/store path. |
| R15 | Trusted ACTIVE composition | Independent PASS for opt-in production bootstrap, auth/owner/digest refusals and actual governed read→receipt→rethink; global default unchanged. |
| R16 | Durable surface status | PASS: restart retains claims/history/status; read paths do not dispatch. Current real HTTP effect/restart evidence linked below. |
| R17 | Registration and raw ledger | PASS: real v8 terminal ledger 216 rows/108 closure/0 gaps; raw trace brain_calls/tokens/effective policy reconciled with 0 issues; v7 partial ledger preserved as NOT_COMPLETE. |
| R18 | Real trial adapter | PASS: real model bytes drove tool/store in 108+54 slots; guarded reshape refused in both arms (BLOCKED_READINESS, nothing written); negative-transfer tasks received baseline policy; loaded context 40,960 confirmed on every response. |
| R19 | Registered experiment and ablation | PASS (pilot scope only): v8 harness and independent recalculated verdict both pass (success non-inferior, retries improved, negative transfer absent, safety/duplicate 0); 54-slot ablation complete with prespecified contrasts. Not confirmatory; see [LIVE_RESULTS](live/LIVE_RESULTS.md). |
| R20 | GBRAIN metadata scope | PASS in metadata-only scope: current35tests; reward is write recency/frequency, no selection consumer/authority/maturity or task-value claim. |
| R21 | Current-byte real-source rehearsal | PASS at final recorded pins:56,961 payload mapping matches/source unchanged/replay/rollback; real objectives/tasks absent, destructive apply not run. |
| R22 | Integrated acceptance/docs | Integrated QA PASS1125/1skip, architecture PASS at QA snapshot. Live results packaged under [live/](live/LIVE_RESULTS.md) with per-file SHA-256; architecture review re-run after doc update (see below). |
| R23 | CLI/type/lint | Changed-scope PASS: CLI refusal behavior, Ruff64files, new type errors0/cycles0;11 baseline errors disclosed, not whole-repo type-clean. |

## Actual current surface evidence

- [Root-run unified final HTTP artifact](manual-active-v7-result.json) and [reproducible harness](manual_active_http_current.py): anonymous401, first dispatch1, real HTTP process restart, restart DUPLICATE_ACTION and dispatch0, 6 canonical records/digests, 4 Git commits, exit0. Real ToolExecutor and durable store; live_brain=false.
- [Structured Brain protocol driver](brain_contract_driver.py), rerun on unified final bytes in [final driver proof](brain-contract-v7.txt): production port → canonical judgment → typed feedback/receipt → new judgment, 2 protocol calls, 0 external-provider calls, 2 canonical judgments, exit0 (corrected PYTHONPATH=src:. invocation). This is an actual local provider-contract surface, not live LLM efficacy.
- [Independent composition review](composition-review-final.md): authentication/owner/injected-claims/digest refusals, 30 final selected tests; canonical NOT_READY and READY-with-UNKNOWN check refuse effect. Actual governed read expansion, canonical receipt body, Primary rethink and restart were independently verified at recorded hashes; final live-scope freeze is separate.
- [Independent goal rereview](goal-review-final.md): G1 selected-content bridge and G5 runtime formation/replay scoped PASS; G2 initially PARTIAL. Subsequent review independently closed executed-without-receipt refusal and authoritative learning-integrity lookup; 39 scoped tests passed. Unbound requests now refuse as REQUEST_UNBOUND; supported trusted request mapping subsequently passed actual governed HTTP expansion with durable receipt readback (50 owner tests / 30 independent tests reported by integration owner).
- Baseline full suite reported 910 passed,16 failed,1 skipped. Those failures include stale metadata and enum/import gates; the final integrated run below passed after correction. **This is a baseline count, not the final suite result.**

## Actual implementation follow-up queue

Only unresolved behavior and unsupported paths belong here; ordinary independent review is tracked by its concrete scoped report, not treated as a permanent generic blocker.

Queue empty for the supported scope. The live run and ablation completed on the frozen source (560-file inventory unchanged before/after both runs), were independently recomputed from raw ledgers/traces, and are packaged with hashes. The contrasts measure conditional removal effects, not full-factorial interactions. Remaining items are operational decisions listed in the next section, plus a future confirmatory experiment with a registered sample size if efficacy beyond pilot scope is ever to be claimed.

Closed during reconciliation: [old-wire additive-field compatibility](wire-compatibility-review.md) independently reaffirmed PASS (38 compatibility/recovery/composition tests); final models hash `afe99ffae7ebb74d29e34a82aab34da2a119317e437529ddcca53e89be204945`. Final-byte R21 rerun passed in 227.338s with all 56,961 source-payload mapping digests matching and source unchanged. Trusted canonical request binding now drives real governed read→durable receipt body→Primary rethink and restart; unbound requests fail closed. Missing executed receipt now refuses before the next provider call; malformed/missing/incomplete authoritative Experience and bypassed summaries are rejected at learning boundaries (goal reviewer scoped PASS). The runtime now also defers material risk/action changes without an explicit updated EpisodePlan; ground-only changes retain the prepared plan by explicit policy. Independent preflight closed fabricated advisory/selection/execution observations: actual selected content and Experience payload reach the model, selection reasons persist, and no-read failures cannot be MATCH/file.read_text observations. The first final local registration was NOT_COMPLETE during TRAIN_VALIDATION due to a truncated 128-token response; that failed attempt remains preserved. Subsequent registered v8 and 54-slot conditional ablation runs completed as recorded in [LIVE_RESULTS](live/LIVE_RESULTS.md); their results apply to the frozen source and pilot scope.

Items leave this queue as their actual fixes and final scoped verdicts arrive. Scoped PASS does not require reopening a blanket independent-V slot. Deployment permissions remain separate below.

## Scope and operational decisions

Normal completion includes finishing supported code, contracted producer/consumer integration, read-only rehearsals and independent verification. These are not Human-only blockers. Independent review requires separation from implementation; it need not always be a human reviewer.

Production effect enablement outside the existing authorization, destructive migration/cutover, and release/CR-14 owner's actual sign-off remain separate decisions. The local-provider v8 and ablation executions were authorized and have completed. Global rollout and distributed multi-host/NFS support are not prerequisites for the supported single-host implementation. No operation was enabled by editing these documents. OFF/SHADOW remains the default; no Human grants or protected authority were fabricated.

R21 preserves source and mapping provenance, not full source JSON verbatim in canonical EventPayload. `source_unchanged` means captured logical input equals final logical observation; transient A→B→A writes do not contaminate the private snapshot used for import. No semantic completeness of vector/RAG is inferred from record counts.

## Evidence binding and provenance

- Historical reviewed base: `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.
- Current interface source/test/spec snapshot: [contract-source-manifest.json](../current-remediation/contracts/contract-source-manifest.json). A hash mismatch means that contract snapshot needs refresh before current acceptance.
- Scoped independent review manifests are embedded in authority-final-review.md and code-review-final.md.
- Final migration before/after code and source hashes are inside migration-final-results.json; migration-current-results.json remains historical.
- Baseline QA snapshot, corrected current tree, scripted contracts, real local provider execution and production activation are distinct surfaces. Do not transfer PASS between them.
- Final integration owner must record executed commands/exit codes, final independent goal/QA verdict and live-run terminal status here before changing the overall status.

## Static type scope

The changed-production audit found 11 errors matching the baseline 8cc94cf5 clone in unchanged statements. The newly identified surface/Brain import cycle was repaired by extracting the unchanged legacy port (69 Brain/surface tests passed; scoped type audit0 errors/0cycle), then independently verified with16 scoped tests PASS. [Current diagnostics](final-types.json), [baseline diagnostics](baseline-types.json), and [comparison](type-diagnostic-comparison.json) preserve the distinction. Do not describe the entire repository as typecheck-clean. The amended frozen source audit completed: 64 changed Python files passed Ruff (exit0); aggregate 39-production-file type audit has 11 errors identical to baseline, **new type errors0, import cycles0**. The 11 baseline static errors remain explicitly reported. The final basedpyright run also reports 470 warnings across its selected scope; warning counts are not claimed baseline-equivalent or clean. [Final Ruff output](final-ruff.txt) and the comparison above bind this result.

## V5 full-suite terminal result (historical source snapshot; defect repaired)

1,035 passed,1 failed,1 skipped across1,037 collected tests. The failure is a genuine concurrent schema initialization race (duplicate SQLite ALTER TABLE column), subsequently repaired and covered by 37 targeted tests; the unified final integrated run below then passed. This is not a metadata-only failure and not a final PASS. The skipped case must retain its reason in the final QA report. Subsequent affected-source verification must be bound to the final manifest; do not merge overlapping suite counts into a fabricated total.

## Unified final QA evidence

[Terminal log](qa/v7-final-full.log), [JUnit XML](qa/v7-final-full.xml), [exit0](qa/v7-final-full.exit), [architecture report](qa/v7-final-architecture.json), [architecture exit0](qa/v7-final-architecture.exit), [pre-run hashes](qa/v7-full-pre-hashes.txt), [post-run hashes](qa/v7-full-post-hashes.txt). Terminal run:1,125 passed,1 intentional skipped,1 baseline Starlette/httpx warning in1,240.45s. The XML contains1,126 cases:1,061 cognitive plus65 runtime,0 failures/errors. Runtime and unit subsets reported elsewhere overlap this sweep and are not added to the total.

[Source correspondence](qa/v7-final-source-correspondence.txt) preserves the generated packaging SOURCES.txt difference; the final QA report explains it rather than silently treating generated metadata as a consumed-source change. Source acceptance is bound to the frozen manifest and tested pre/post correspondence, not to test counts alone.

## Live run terminal status (2026-09-27, after QA)

Executed on the frozen source after the integrated QA PASS; neither run changed any first-party file (hash check before/after inside each driver and in the audit scripts).

- `registered-local-v8`: `PYTHONPATH=src .venv/bin/python -c "...run_local_registered(...)"` → exit 0, 14:49 KST. Audit: [registered-local-v8-audit.json](live/registered-local-v8-audit.json). Harness result: [registered-local-v8-result.json](live/registered-local-v8-result.json).
- `ablation-live-v1`: `PYTHONPATH=src .venv/bin/python work/finalize-2026-09-27/run-live-ablation.py --root work/finalize-2026-09-27/ablation-live-v1` → exit 0, 15:27 KST. Analysis: [ablation-live-v1-analysis.json](live/ablation-live-v1-analysis.json).
- `registered-local-v7`: NOT_COMPLETE, [preserved result](live/registered-local-v7-result.json); raw 5 MB trace kept in `work/`.
- Post-live documentation gate: `scripts/architecture_review.py` re-run after these edits → [post-live-architecture.json](qa/post-live-architecture.json), [exit0](qa/post-live-architecture.exit); 16/16 checks pass (links, citation tracking, digest, state claims). Focused regression after doc edits: 172 passed (architecture/digest/canary/live_pilot/live_trial_adapter). The 1,465-file frozen source manifest still matches byte-for-byte; no first-party source changed during or after the live runs.
- Summary with interpretation limits: [LIVE_RESULTS.md](live/LIVE_RESULTS.md). Recomputation scripts: [live/scripts/](live/scripts/audit-live-results.py).

Scope statement: this is a local synthetic append pilot with an operator-prespecified context-depth hypothesis. It establishes that the learned policy and Experience consumption each reduced retries on this corpus without changing success or safety; it does not establish general capability growth, and no confirmatory sample size was registered.
