# FINAL independent authority rereview — 2026-09-27

## Verdict

**PASS for the two scoped R01/R02 corrections at HEAD `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382` plus the exact dirty file hashes below.** The two findings in `authority-review.md` are closed at this byte snapshot. No remaining actionable defect found in the changed scope. This is not blanket R15, production ACTIVE, multi-host, release, cutover or CR-14 approval.

Read the implementer `work/finalize-2026-09-27/fix-authority.md`, all changed source sections and new regression scenarios. Reran original independent attack logic rather than relying solely on implementer tests. No source edits. Only disposable TemporaryDirectory fixtures were mutated and automatically cleaned; actual protected files and services untouched.

## Independent reproduction results

Executed via `PYTHONDONTWRITEBYTECODE=1 uv run --no-sync python` on the current repository environment. This was a real macOS `SandboxRunner.execute`/Seatbelt execution, not a mocked subprocess.

```
authority control True ALLOWED
authority operations False DELEGATION_NOT_SUBSET
authority future False NOT_GRANTED
authority constraints False DELEGATION_NOT_SUBSET
sandbox False direct False True 1 protected_unchanged True
sandbox False symlink False True 1 protected_unchanged True
sandbox False root False True 1 protected_unchanged True
sandbox False sibling True True 0 protected_unchanged True
sandbox True direct False True 1 protected_unchanged True
sandbox True symlink False True 1 protected_unchanged True
sandbox True root False True 1 protected_unchanged True
sandbox True sibling True True 0 protected_unchanged True
INDEPENDENT PROBES PASS
```

Sandbox columns: restrict_reads, operation, success, sandboxed, return code, protected SHA-256 unchanged. Original root relocation command was `/bin/mv <temp>/project <temp>/renamed && /bin/echo CHANGED > <temp>/renamed/docs/ssak-ai-core/SSAK_AI_CONSTITUTION.md`. It now fails in both restrict modes and preserves the original digest. Direct and symlink mutation also fail. Ordinary sibling `notes.txt` rename plus append succeeds in both modes; final ordinary content is exactly `notesok\n`.

Authority probes reused a valid current parent+child, then independently changed only the parent operations to read-only, issuance to one hour in the future, or constraints to include `human-check`. Each originally vulnerable variant is now refused; unchanged valid chain remains allowed.

Also independently ran the focused new regression file:

```
uv run --no-sync pytest tests/cognitive/test_final_authority_boundaries.py -q -p no:cacheprovider
17 passed in 0.74s
```

This covers root/docs/outer container relocation across both restrict modes, ordinary sibling writes, custom protected targets, failed policy initialization, operation and constraint attenuation, future issuance, parent expiry ceiling, invalid grandparent/delegation, and multiple parent coverage. Broad QA remains owned by the QA lane; the implementer's separate 123-test result is not represented as this leaf's execution.

## Source assessment

- Protected directory ancestors now receive literal unlink denies through the filesystem root. They follow broad allow rules. Literal matching avoids denying ordinary sibling updates. Explicit protected paths get ancestor protection too.
- Protected-policy initialization failures propagate rather than silently constructing a runner with no default protection.
- Current ancestry evaluation checks operation subset, inherited constraints, expiry attenuation and issuance time at every candidate chain. It accepts an actually covering valid chain rather than choosing an unrelated narrow parent solely by string length.
- Delegation invokes ancestry validation before issuing another child. Current trusted ACTIVE route/principal findings in the earlier report remain unchanged; this fix does not add production composition or expand admission scope.

## Exact reviewed dirty SHA-256 manifest

| Repository path | SHA-256 |
|---|---|
| src/antigravity_k/engine/sandbox.py | 3b3364714c8c2b354c527656b59d5416dc5ea35bda64e3fc8c1cfef018393f93 |
| src/antigravity_k/engine/cognitive/authority.py | 7317a39d7c40f65cbce3232d33a3954a36d6f5f541b5fde032fd14b7a5a83ecb |
| src/antigravity_k/engine/cognitive/protected_targets.py | d18548cfa59870667f5080b92bb218c6b7b7bb1ec310bc40a287f143bc9ceea8 |
| tests/cognitive/test_final_authority_boundaries.py | 96a7622a86c6f1a5c2aa3bf8e3e8838b778a4514933759339248ecdce6fc6862 |

Hashes measured after independent probes and match the implementer manifest. The prior report remains historical evidence of the failing snapshot; this final report supersedes its scoped REQUEST CHANGES only for these exact corrected bytes. Linux/Docker live isolation and multi-host grant persistence were not independently exercised here.
