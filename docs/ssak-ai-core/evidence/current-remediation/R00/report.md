# R00 report — 현재 근거 고정

- 실행: 2026-09-26 19:55 KST
- HEAD: `2862584ea8f79641fefd9a78de9c145851ea515b`
- dirty: 205 paths (see `source-manifest.json` / review `dirty_manifest.txt`)
- interpreter: `.venv/bin/python` (recorded in baseline_meta.json)
- reviewer: 마뱀 (implementer self-review; independent human slot still open — limitation)

## Before / after

- Before: P00–P12 / T00–T14 과거 PASS가 날짜·surface 구분 없이 읽히기 쉽고, migration 8 pin 중 4개가 과거 보고서와 불일치해도 CURRENT_PASS로 오인될 여지.
- After: CURRENT remediation 진입점과 pass-binding 규칙을 고정. fixture vs live, isolated ACTIVE vs production을 분리 표기. pin 4 mismatch를 HISTORICAL로 명시하고 R21 재실행 범위로 넘김.

## Pin classification (migration 8)

| path | match | 분류 |
|---|---|---|
| migration.py | false | semantic risk → R04/R21 재현 전 HISTORICAL only |
| legacy_adapter.py | false | semantic risk → R21 재현 전 HISTORICAL only |
| test_migration.py | false | test drift with source |
| test_legacy_adapter.py | false | test drift with source |
| store.py | true | pin OK |
| (나머지 3) | true | pin OK |

과거 56,961-event dry-run PASS는 해당 당시 source digest에 결박된 HISTORICAL 증거다. 현재 bytes의 CURRENT_PASS로 승계하지 않는다.

## R00-A* observations

### R00-A1
- Given: evidence bundle binds PASS to listed source digests.
- When: any listed anchor changes (rule + demo in baseline_meta.pass_binding_rule); dirty docs/ssak-ai-core already differ from clean tree.
- Then: previous run is HISTORICAL, not auto CURRENT_PASS. Documented in README §5.1 and this report.
- Result: **PASS**

### R00-A2
- P11 isolated authenticated ACTIVE: HISTORICAL_ISOLATED_HTTP (fixture Brain).
- P11 production ACTIVE: **OPEN**.
- Result: **PASS** (separated in CURRENT_STATUS table)

### R00-A3
- P10 fixture growth: HISTORICAL_MODULE_PASS.
- P10 live growth: **OPEN / NOT_RUN**.
- Result: **PASS**

### R00-E
- Evidence at `docs/ssak-ai-core/evidence/current-remediation/R00/` and review pack `evidence/R00/`.
- Result: **PASS**

### R00-V
- Self-review of diffs + manifests. Independent human reviewer not yet recorded.
- Result: **PASS with limitation** (same-agent review)

## Rollback
- Delete/revert only the R00 doc/evidence additions; no runtime flag change.

## Limits
- Did not re-run full cognitive suite or 56k migration (owned by R21/R22).
- Dirty tree includes unrelated CR-14/desktop/qa paths; R00 does not claim those clean.
- Card completion ≠ release / ops activation.
