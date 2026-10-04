# Independent authority review — 2026-09-27

## Verdict and scope

**REQUEST CHANGES at reviewed HEAD `8cc94cf51952e3bbb6cb3f627683ca6c9c2d0382`.** R01 and R02 each have a reproduced security boundary gap. This report pins pre-fix source; the parent has assigned fixes separately. It does not certify later dirty changes, production ACTIVE, multi-host behavior, cutover, or CR-14.

Read-only leaf review of R01/R02 plus trusted ACTIVE admission. Graph-first discovery used freshly indexed `Users-mr.k-program-coding-ssak_comp-Ssak-Ai`, then exact source reads. Read repository current-remediation R01/R02/R15 reports and summaries, R15 ENTRY_MATRIX, FAILURE_MODEL_RESIDUAL_REVIEW, and prior output-pack R01/R02/R15 task/evidence claims. No source edits, broad suite, production service, or actual protected file changes. Runtime probes used existing `uv run --no-sync python` and automatically cleaned TemporaryDirectory fixtures only.

## Findings

### P1 — R01: project-root relocation escapes protected writes

`sandbox.py:404-423`, `_protected_write_deny_section`, skips `real == project_root`; `_build_seatbelt_profile` gives broad temporary-directory writes in default `restrict_reads=False`. `protected_targets.py:277-301` deliberately omits project-root unlink protection, assuming the gate handles it. This is insufficient for interpreter/opaque commands already inside the OS execution boundary.

Reproduction: create disposable `<base>/project/docs/ssak-ai-core/SSAK_AI_CONSTITUTION.md` containing `ORIGINAL`; construct `SandboxRunner(project_root=<project>, enabled=True, require_sandbox=True)`; execute `/bin/mv <project> <base>/renamed && /bin/echo CHANGED > <base>/renamed/docs/ssak-ai-core/SSAK_AI_CONSTITUTION.md` with cwd `<base>`. Actual result: `success=True, sandboxed=True, return_code=0`; moved protected content is `CHANGED`.

Controls: direct protected write, write through symlink `project/alias`, and rename of `docs/ssak-ai-core` each return failure/rc1 with both restrict modes. Root rename succeeds only with `restrict_reads=False`; `True` denies. Thus the failure is not unavailable sandbox or a general failure of protected leaf rules. Add OS-level project-root/required ancestor unlink protection and retain normal allowed writes; test whole-root relocation, not only protected subdirectory rename.

### P1 — R02: ancestor operation, constraint and issuance validity are not reevaluated

`authority.py:221-253`, `_ancestor_failure`, checks ancestor revoke/expiry/scope but omits operation subset, inherited constraints and `issued_at`. Its subject-based selection also chooses `max(len(scope), revision)` without first finding a parent whose full capability contains the child.

Reproduction at current time: parent `body:p`, dimension TOOL_WRITE, scope `workspace`, operations `('read',)`, issuer `human:owner`, issued one hour ago, revision2; child `body:c`, same dimension, scope `workspace/x`, operations `('write',)`, issuer `body:p`, issued one hour ago, revision1. `AuthorityProfile.from_grants((parent, child), revision=2).evaluate(AuthorityQuery(subject='body:c', dimension=TOOL_WRITE, resource_scope='workspace/x', operation='write'), now=now)` returns `allowed=True, verdict=ALLOWED`.

Additional reproduced variants: changing an otherwise valid current parent to `issued_at=now+1h` still allows the child; adding parent constraint `human-check` while child constraints remain empty still allows the child. These are current-profile evaluation gaps, not stale-cache probes. Control: ordinary valid delegation inherits parent expiry; evaluation before expiry allows and after expiry returns EXPIRED.

Required correction: revalidate full parent capability subset and temporal validity through the entire current ancestry on evaluation and delegation. A restricted or invalid ancestor must not remain effective through an existing child. Preserve independent valid branches and test multiple parents/cycles explicitly.

## Other inspected boundaries

- Required-sandbox disabled mode refused command execution with `Sandbox is disabled by configuration; raw execution is refused.` Runtime probes confirmed this in both restrict modes. Static enabled paths refuse unavailable Darwin/Docker boundary; no successful raw fallback was observed in required mode. Explicit non-required disabled compatibility remains raw execution by design.
- `reuse_approval` requires matching nonempty digest, principal, scope, operation, and expiry. `GovernanceGate._reusable_human_decision` supplies the current action digest; `authorize_execution` rejects missing and mismatched digest. These checks are present; this leaf did not rerun their full test suite.
- `CognitiveActiveService` is installed through trusted app state. `/active/execute` accepts only request id, digest, reason (`extra=forbid`), loads a server-prepared action owned by verified bearer subject, compares current prepared digest and adapter project, and constructs the `human:<subject>` approver internally. Activation callback re-verifies token identity/project during activation and ACTIVE resolver callbacks. No client-injected authority, tool arguments, project root, or arbitrary approver route was found in this examined surface.
- `CognitiveSurfaceAdapter` requires durable journal, record sink, authority resolver, freshness resolver, and activation authorizer for ACTIVE. `action_admission.preconditions` invokes the live authority resolver, checks final grant fields and current freshness. The R02 ancestor gap still affects any resolver built on current AuthorityProfile evaluation.
- Low-level `AuthorityQuery.human_decision_id` and `issue_grant(actor_kind=HUMAN)` are trusted in-process inputs, not authenticated capabilities themselves. No untrusted ACTIVE request path to those inputs was demonstrated; do not describe their constructors alone as an HTTP exploit.
- R15 documentation explicitly says production ACTIVE service must still wire store-backed freshness. Presence of callbacks does not establish that a future composition supplies real store heads. Existing OFF/unconfigured behavior is not production ACTIVE acceptance. Full R15 integration/QA and multi-host safety remain outside this leaf verdict.

## Evidence output

Initial targeted probe:
```
ancestor narrowed operation: True ALLOWED
root rename True True 0
protected content CHANGED
```
Control matrix (`restrict_reads`, operation, success, sandboxed, rc):
```
False direct  False True 1
False symlink False True 1
False parent  False True 1
False root    True  True 0
True  direct  False True 1
True  symlink False True 1
True  parent  False True 1
True  root    False True 1
```
Additional authority controls:
```
expiry inherited True current True later EXPIRED
ancestor future True
ancestor added constraint True
```

## SHA-256 manifest of reviewed source

| Path under repository | SHA-256 |
|---|---|
| src/antigravity_k/engine/sandbox.py | 3f1a0aa4f2bb8d89b5d4d919f629e644595a9252c777357e3764ad7a8af9c04a |
| src/antigravity_k/engine/cognitive/authority.py | 7d39a4bc58ec9d21eea17a4b22ca5162fa86f8619f6e099479e08bb7025d3896 |
| src/antigravity_k/engine/cognitive/governance.py | 4fd1aaf79d7c8303e219a774d589aa81c7d9543aedff5b6cf20ba2ac2874a250 |
| src/antigravity_k/engine/cognitive_surface.py | b63cfb53c2e074ac51b688996a85567ab291b98fb30e591733c7c7d828691e4b |
| src/antigravity_k/engine/cognitive/action_admission.py | 3b3741310562ae86860f8c0bfb01b178628c3ec086da24d0a9d295d3f0191a53 |
| src/antigravity_k/api/routes/cognitive_active_api.py | dbe95e82e0088691cc80e211d22b3dcf19304802e9aed913994e919c1c46d000 |

The repository has pre-existing unrelated untracked artifacts and dirty nested vault state; they were not changed or cleaned by this reviewer. Report artifacts are in the separate conversation workspace. The two findings were sent immediately to the parent and assigned fix worker with reproduction details.
