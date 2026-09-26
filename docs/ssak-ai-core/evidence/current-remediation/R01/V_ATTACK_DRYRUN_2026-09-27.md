# R01 Independent V — attack dry-run (NOT Independent R01-V)

```
╔══════════════════════════════════════════════════════════════════╗
║  BANNER: NOT Independent R01-V                                   ║
║  Label: implementer / secondary dry-run                          ║
║  Role: attack evidence for a future independent reviewer         ║
║  Do NOT treat this file as R01-V PASS, ops GO, or CR-14 GO.      ║
╚══════════════════════════════════════════════════════════════════╝
```

Prepared: 2026-09-27 04:55 KST  
Executor tip (docs commit parent): `13c651172a8849b70f280e44e3da48f1394f620b` on `codex/m1-task-events` (**no push**)  
Residual-close pin (unchanged): `84210aec` (`fix(ssak-ai): R01 seatbelt deny + gate digest residual`)  
Playbook: [../INDEPENDENT_V_ATTACK_NOTES.md](../INDEPENDENT_V_ATTACK_NOTES.md) § R01  
Verdict slots in ATTACK_NOTES: **left blank / OPEN** (this dry-run does not fill them)

## Pytest baseline (ATTACK_NOTES §4)

Working directory: `/Users/mr.k/program/coding/ssak_comp/Ssak-Ai`

```bash
.venv/bin/python -m pytest tests/cognitive/test_r01_residual.py tests/cognitive/test_r01_protected_sandbox.py tests/cognitive/test_protection_boundaries.py tests/cognitive/test_protection.py tests/test_sandbox_isolation.py -q -p no:cacheprovider
# → 62 passed in 1.22s  exit 0
# evidence: pytest_baseline_r01_2026-09-27.txt
```

Targeted attack nodes (also green):

```bash
.venv/bin/python -m pytest \
  tests/cognitive/test_r01_residual.py::test_r01_seatbelt_deny_follows_broad_allow \
  tests/cognitive/test_r01_residual.py::test_r01_non_darwin_without_docker_is_fail_closed \
  tests/cognitive/test_r01_residual.py::test_r01_docker_cmd_includes_readonly_protected_mounts \
  tests/cognitive/test_r01_residual.py::test_r01_protection_action_digest_binds_approval \
  tests/cognitive/test_r01_protected_sandbox.py::test_r01_a1_write_bytes_os_replace_parent_rename_symlink_immutable \
  tests/cognitive/test_r01_protected_sandbox.py::test_r01_a4_unavailable_or_disabled_sandbox_is_fail_closed \
  tests/cognitive/test_r01_protected_sandbox.py::test_r01_a3_approval_does_not_reuse_across_args \
  -v -p no:cacheprovider
# → 7 passed in 0.59s  exit 0
# evidence: pytest_r01_attack_nodes_2026-09-27.txt
```

Inspection transcript: `attack_inspection_2026-09-27.txt`  
Host: Darwin arm64 (release 25.6.0); `sandbox-exec` present; Docker daemon reachable (`_is_docker_available()=True`) but **live RO remount not exercised**.

## Per-attack observed results

| # | Scenario (ATTACK_NOTES) | Status | Observed |
|---|-------------------------|--------|----------|
| 1 | Seatbelt profile: protected deny **after** broad `/tmp`·`/var/folders` allow | **RUN** | `build_seatbelt_profile()`: allow root idx &lt; `/private/var/folders` allow idx &lt; deny CONSTITUTION subpath. Marker `;; 보호 경로 deny (넓은 allow 이후…)` present. Residual test `test_r01_seatbelt_deny_follows_broad_allow` green. |
| 2 | Sandboxed write/unlink/rename/symlink against protected path under `/var/folders` tmp | **RUN** | Live `sandbox-exec`: write_bytes to CONSTITUTION → `success=False`, sandboxed=True, bytes unchanged. Suite A1 also denies os.replace / parent rename / symlink write. |
| 3 | Docker `docker_cmd` `:ro` remount over `/workspace/{rel}` | **RUN** (cmd-shape only) | Forced Linux+Docker available with mocked `_run_limited_process`: cmd includes multiple `-v host:/workspace/…:ro` for protected paths (`ssak-ai-core` present). |
| 3b | Live Docker daemon RO remount proof | **NOT_RUN** | Reason: dry-run scoped to cmd-shape per ATTACK_NOTES §5.3 / pass bar (“`:ro` live daemon optional but required for claiming Docker mount V”). Daemon was available but not used for mount V. |
| 4 | `enabled=False, require_sandbox=True` → refuse, no raw fallback | **RUN** | Error exact: `Sandbox is disabled by configuration; raw execution is refused.` |
| 5 | Non-Darwin without Docker → fail-closed | **RUN** (patched path) | Forced `_platform=Linux` + `_is_docker_available=False` on Darwin host → `Sandbox is unavailable on Linux; raw execution is disabled.` Actual non-Darwin host not used. |
| 6 | `protection_action_digest` bound approval reused for path/args B → deny | **RUN** | Same args → ALLOW; mutated content → DENY (`APPROVAL_DIGEST_MISMATCH`). Residual + A3 nodes green. |

## Remaining OPEN items (for future independent reviewer)

1. **Independent R01-V** itself — this file is dry-run evidence only; Verdict slot stays OPEN.
2. **Live Docker daemon** RO remount against a real container (Attack 3b).
3. Fail-closed on a **real non-Darwin** host (Attack 5 was path-patched on Darwin).
4. Treating shell-regex hints as the boundary when seatbelt disabled — still out of scope / must remain open.
5. Multi-host sandbox policy.
6. **Ops / CR-14 / production enablement** — still **NO-GO**.

## Explicit non-claims

- **No Independent R01-V PASS**
- **No ops GO / cutover GO / CR-14 GO**
- Suite green ≠ V PASS
- Implementer/secondary ≠ independent reviewer
- Docker cmd-shape ≠ live-daemon mount V

## Pointers

- Card report (self-review): [report.md](./report.md) — Limits should point here; R01-V remains OPEN there.
- Checklist: [../INDEPENDENT_REVIEW_CHECKLIST.md](../INDEPENDENT_REVIEW_CHECKLIST.md)
