# Live experiment terminal evidence — 2026-09-27

Local loopback Ollama provider only; synthetic append corpus; not a general-intelligence or autonomous-learning claim.
All numbers below are copied from the independent recomputation artifacts, not from harness self-report alone.

## Registered Fresh/Mature run (`registered-local-v8`)

- Harness status: **COMPLETED**; ledger rows 216; 108-slot closure: True; reported ledger gaps: 0.
- Raw provider calls: total 192 (FINAL 183); every response confirmed loaded context ['40960'].
- Frozen first-party source files: 560; changed after run: 0.
- Reconciliation issues (brain_calls/tokens/effective policy vs raw trace): 0.
- TRAIN/VALIDATION gate: {"train_successes": 2, "train_total": 2, "validation_successes": 4, "validation_total": 4, "validation_minimum": 0.5, "promoted_version": "live-validated-v1", "candidate_version": "live-candidate-v1", "force_validation_fail": false}.
- MATURE effective policy on non-negative-transfer tasks: ['live-validated-v1'].

| arm | slots | successes | retries (sum) | brain_calls | tool_calls | tokens | safety | non-completed |
|---|---|---|---|---|---|---|---|---|
| FRESH | 54 | 45 | 54 | 108 | 45 | 977044 | 0 | 0 |
| MATURE | 54 | 45 | 21 | 75 | 45 | 865260 | 0 | 0 |

Task-level paired recomputation (unit = 18 tasks): retries mean diff MATURE−FRESH = -0.611 (mature better 11, worse 0, equal 7); success mean diff = 0.000 (better 0, worse 0).

Harness verdict passed: **True** (scope LIVE_PILOT_PILOT_ONLY); independent recalculated verdict passed: **True**. Reasons: ['확증 표본 크기가 등록되지 않았다 — 이 결과는 pilot이며 확증이 아니다'].

Success 45/54 in both arms: the 3 AUTHORITY_RESHAPE tasks (PT-06, PT-07, GT-F4) ended `BLOCKED_READINESS` with nothing written in every slot of both arms — the guarded high-risk reshape path refuses effect without authority, by design; this is not a model failure and is identical across arms. Negative-transfer tasks (PT-10, PT-11, GT-F6) received baseline policy (`None`) in MATURE as preregistered.

Interpretation limits: pilot without registered confirmatory sample size; within-arm state carries across trials so results are not independent cold-start replicas; latency shares a host with other work.

## Preregistered conditional consumption ablation (`ablation-live-v1`)

- Mode: LIVE_CONDITIONAL_ABLATION; driver result status: **COMPLETED**; execution complete: True; ledger STARTED/terminal 54/54.
- Raw provider calls: total 100 (FINAL 91); loaded context [40960].
- Active validated policy: {"policy_id": "policy:9299b700-acd4-4eb2-b019-01b77149ba89", "version": "live-validated-v1", "target": "CONTEXT_DEPTH", "rule": "Increase context selection depth", "parameters": {"extra_depth": 2}, "candidate_id": "policy:9299b700-acd4-4eb2-b019-01b77149ba89", "validation_report_id": "validation_report:31c2f44a-8b38-4393-bb48-d96cd3a03d51", "lifecycle": "CANDIDATE"}.
- Sources changed after run: 0; reconciliation issues: 0.

| condition | tasks | mean retries | success | mean brain_calls | mean tool_calls | mean tokens | safety |
|---|---|---|---|---|---|---|---|
| full | 18 | 0.389 | 15/18 | 1.389 | 0.833 | 14606.722 | 0 |
| no_policy | 18 | 1.000 | 15/18 | 2.000 | 0.833 | 18401.444 | 0 |
| no_experience_exposure | 18 | 0.667 | 15/18 | 1.667 | 0.833 | 14628.667 | 0 |

Model-input audit (`input-audit.jsonl`, FINAL calls): Experience records were present in 19/25 `full` inputs (absent only for the 3 negative-transfer tasks, which receive baseline policy), and in 0/30 `no_experience_exposure` and 0/36 `no_policy` inputs. The ablated conditions therefore actually withheld Experience; the no-policy condition did so because the baseline selector has no L2 depth.

Prespecified paired contrasts (primary metric retries; negative = first condition needs fewer retries):

- **full - no_experience_exposure**: paired tasks 18; retries mean diff -0.278 (better 5, worse 0, equal 13); success mean diff 0.000 (better 0, worse 0).
- **no_experience_exposure - no_policy**: paired tasks 18; retries mean diff -0.333 (better 6, worse 0, equal 12); success mean diff 0.000 (better 0, worse 0).
- **full - no_policy**: paired tasks 18; retries mean diff -0.611 (better 11, worse 0, equal 7); success mean diff 0.000 (better 0, worse 0).

Interpretation limits: Paired per-task contrasts: full minus no_experience_exposure estimates Experience consumption contribution with policy/depth held; no_experience_exposure minus no_policy estimates policy/depth contribution with observed Experience absent in both; full minus no_policy is combined. Descriptive conditional effects only, no factorial/general significance claim

## Historical NOT_COMPLETE registration (`registered-local-v7`)

The prior operator session ended externally during FINAL trials (169 FINAL provider responses, 100/108 trial slots reached, no ledger closure). Its raw trace remains under `work/finalize-2026-09-27/registered-local-v7/`; the result file is preserved here. Its partial numbers are not used for any claim.

## Files

Copied artifacts and SHA-256 values are listed in [copied-sha256.json](copied-sha256.json). The three raw provider traces (>1 MB) are stored gzip-compressed (`*.jsonl.gz`) with both compressed and uncompressed digests recorded; `gunzip -k` restores the exact bytes the audit scripts consumed. Uncompressed originals remain in `work/finalize-2026-09-27/`. Main run source fingerprint (560 first-party files) matches the v7 freeze: `28f55eece8deaef32990db302edb899ded59f761128f2839e54443b372d6bd48` (source-hashes.json sha256).
