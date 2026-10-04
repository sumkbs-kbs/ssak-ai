# Authority boundary corrections — 2026-09-27

Scope: R01 protected-path relocation; R02 current ancestor attenuation. Changed only `engine/sandbox.py`, `engine/cognitive/protected_targets.py`, `engine/cognitive/authority.py`, and dedicated `tests/cognitive/test_final_authority_boundaries.py`. No commits. No real repository protected content was mutated. Other workers own independent changes.

## Root causes and corrections

R01: the default sandbox allowed shared temporary-tree writes but protected only a document and its immediate parent. Moving docs, workspace root, or an outer temporary container moved protected bytes outside the protected pathname. Existing ancestor `subpath` unlink denies additionally prevented legitimate sibling-file rename. All protected-target ancestors now receive literal unlink denies, including workspace and ancestors outside it; target write denies and ancestor denies follow every broad write allow. Explicit caller-supplied protected targets receive the same ancestor protection. Ordinary sibling rename and writes remain available. Failure constructing default protection no longer silently yields an empty policy.

R02: ancestry traversal checked scope, expiry and revocation but omitted operation subset, constraint retention, child expiry attenuation, and future issuance. It also selected the longest (often unrelated) parent scope. Every candidate chain now must preserve operations, constraints and expiry ceiling, and all grants must be issued by evaluation time. Any fully covering valid chain can authorize. `delegate()` also rejects parents with invalid ancestry and selects a genuinely covering parent candidate before issuing a child.

## Failing-first evidence

Initial dedicated scenarios: `12 failed, 3 passed in 0.65s`.
- Real Seatbelt returned `success=True, sandboxed=True, return_code=0` for root/docs/outer-container relocation under default read mode.
- Legitimate ordinary sibling rename failed due to overbroad parent subpath unlink rule.
- Child operation expansion, dropped constraints, future parent/child, unbounded child expiry, invalid grandparent, unrelated-parent selection, and delegation from invalid ancestry failed the desired contracts.

Second failing-first pair: `2 failed, 15 passed in 0.69s`.
- Custom protected target allowed root relocation.
- Default policy construction error was swallowed instead of refusing runner creation.

## Runtime verification

Command:

```sh
uv run --no-sync pytest tests/cognitive/test_final_authority_boundaries.py tests/cognitive/test_governance.py tests/cognitive/test_r01_protected_sandbox.py tests/cognitive/test_r01_residual.py tests/cognitive/test_r02_authority_lifecycle.py tests/cognitive/test_r02_cross_process.py tests/test_sandbox.py tests/test_sandbox_isolation.py tests/test_cr03_sandbox_read_boundary.py -q
```

Result: **123 passed in 8.67s** (rerun after test-only typing cleanup also passed).

The dedicated tests invoke real `SandboxRunner.execute` / macOS `sandbox-exec`, with disposable filesystem fixtures; no subprocess mock. Six relocation scenarios cover root/docs/outer-container under both read modes. Assertions require denied subprocess outcome, original file existence and identical SHA-256. Existing R01 tests additionally cover direct interpreter writes, replacement and symlink writes. Positive ordinary file and sibling rename/write scenarios pass. Separate authority tests use real models/profile operations with a fixed clock.

Ruff check on all four owned files: **all checks passed**. Targeted basedpyright: **0 errors**; five existing production warnings remain (pre-existing field/parameter annotations), and one new test warning flags the mandated exhaustive `assert_never` pattern as redundant. No new production type warnings.

The direct long-lived terminal profile consumer uses the returned profile as-is and appends no later Seatbelt allow rules. Linux/Docker was not live-tested on this macOS host; existing boundary unit coverage passed. This evidence is limited to the changed boundary and relevant suite, not the entire application's release qualification.

## Artifact hashes (SHA-256)

- sandbox.py: `3b3364714c8c2b354c527656b59d5416dc5ea35bda64e3fc8c1cfef018393f93`
- authority.py: `7317a39d7c40f65cbce3232d33a3954a36d6f5f541b5fde032fd14b7a5a83ecb`
- protected_targets.py: `d18548cfa59870667f5080b92bb218c6b7b7bb1ec310bc40a287f143bc9ceea8`
- test_final_authority_boundaries.py: `96a7622a86c6f1a5c2aa3bf8e3e8838b778a4514933759339248ecdce6fc6862`

Read-only protected source hashes:

- SSAK_AI_CONSTITUTION.md: `02251d03de38885d73c80d0f70fe68641614389b56a2a16492947bc09d07987d`
- SOURCE_MANIFEST.json: `0160eef9e5f2d9099f82bda11b32976a1898d83b337bddd3502a3d800d2d4688`
- MASTER_PROMPT_V2_SOURCE.md: `d13e2c051ba1c6de645b159f04e3f638379128f16fa5b8986f638a5bf3932391`

All mutation probes used pytest temporary directories; no debug source edits, daemons, or manual temporary scripts remain. Graph discovery used the indexed project `Users-mr.k-program-coding-ssak_comp-Ssak-Ai` after correcting the initial short project-name lookup.
