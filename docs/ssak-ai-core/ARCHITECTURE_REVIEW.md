---
title: "SSAK-AI 최종 Architecture Review (T14)"
date: 2026-09-22
version: "1.0"
status: implementation-review
tags: [ssak-ai, cognitive-core, architecture, review]
---

# SSAK-AI 최종 Architecture Review (T14)

## 0. 이 문서의 성격과 재현 방법

T14의 산출물이다. 이 문서는 서술 문서이면서 동시에 **기계 검증 대상**이다. 자유 서술만 있으면 drift를 막을 수
없으므로, 헌법 24원칙·원문 §63 질문·§52 drift 질문을 카드·시험·증거·module에 매핑하고 그 매핑 자체를
`scripts/architecture_review.py`가 검사한다. 검사 항목은 다음과 같다.

1. 헌법 원칙·§63 질문·§52 질문과 매핑이 **같은 수**인가(`source_alignment`).
2. 매핑이 인용한 증거 문서·시험 파일·module이 실제로 존재하는가(`artifacts_exist`).
3. `docs/ssak-ai-core` 안의 상대 link가 전부 해석되는가(`doc_links_resolve`).
4. 인수 체크리스트의 모든 항목(T00a~T14)이 원칙 매핑에 등장하고, 매핑의 카드 ID가 실재하는가
   (`checklist_coverage`).
5. `evidence/` 의 문서가 모두 인용되는가(고아 증거 방지 — `evidence_referenced`).
6. 문서가 **문장으로 인용한 저장소 경로**가 실재하고 **git 에 추적**되는가(`citation_tracking`). 실재만 보면
   이 체크아웃을 잃었을 때 사라지는 근거가 통과한다 — 실제로 그런 인용이 있었다(§1.3). 해석과 축약 표기 처리는
   그 절에 있고, 해석되지 않거나
   추적되지 않는 인용은 등록부에 **이유·소유자·재검토 기한**을 두고, 등록이 추적되는 경로를 가리키거나
   기한이 지나면 그쪽도 실패한다.
7. `tests/cognitive` 의 수집 개수를 실제로 세는가(`test_collection`).
8. 전량 회귀 원장(`evidence/regression_ledger.json`)이 **scope 별로 두 회차**를 갖고, 결정적 실패에 전부
   소유자가 있는가(`regression_ledger`). 서로 다른 variant 두 회차가 없는 scope 는 "결정적"과 "variant 민감"을
   구분하지 못하므로 수치로 쓰지 않는다.
9. 이 문서가 24원칙(`**P{n}**`)·§63 질문(`**Q-key**`)·§52 질문(`**D-key**`)을 모두 다루고, 매핑의 artifact 경로를
   그대로 담고 있는가(`review_document`).
10. 증거가 못 박은 sha256 의 현재 일치 여부가 **측정 artifact 로 최신**으로 남아 있는가(`digest_report`) —
    저장본이 낡았거나, 파일 없는 pin 이 있거나, 재확인 뒤에 파일이 또 바뀌어 그 재확인이 무효가 됐으면 실패한다
    (움직임 자체는 실패가 아니다 — 그것은 관찰이다).
11. 산문이 지금 트리에 대해 한 **상태 주장**(“이 시험은 실패한다” 류, test node 지정)이 방금 돌린 시험과
    일치하는가(`state_claims`) — 낡은 주장은 정정 표기로 해결하고, 정정 없이 남으면 실패한다. 감사자의
    **자기시험이 없거나 실패하면 판정과 무관하게 실패**하고, node 를 지목한 산문이 하한보다 적으면
    (“눈이 멀었을 수 있다”) 실패한다.
12. 하한이 **지금 저장소에서 실제로 무는가**(`harness_canary`) — 각 harness 를 일부러 눈멀게 한 사본
    (`observed=0`)이 막히는지, 차단 문장이 그 harness 가 기록한 근거를 함께 내는지 본다.
13. 층들이 **한 번에 도는 명령**(`scripts/evidence_gate.py`)으로 묶여 있는가(`evidence_gate`) — stage 가
    비어 있지 않고 요구된 이름이 전부 있으며 각 스크립트가 실재하는가, tier 가 아는 값인가, 게이트의
    **자기시험**(종류 구분·tier 필터·roster 정합·수치 추출)이 있고 통과하는가, 하한의 근거가 적혀 있는가,
    그리고 **비교할 기준 파일이 기록돼 있는가**(무엇을 보고 승인했는지·언제인지가 없으면 기준이 아니다 —
    깨진 기준을 “기준 없음” 으로 삼키지 않는다).
    리뷰는 게이트를 **돌리지 않고 명세만 읽는다** — 게이트의 stage 중 하나가 이 리뷰라서 돌리면 서로를
    불러 끝나지 않는다(단방향 계약).
14. “위반 0건” 이 **관찰**인지 **미관찰**인지 — 저장소 밖 트리에 **진짜 파일로 위반을 심어** 그 감사가
    실제로 빨간을 내는지 확인했는가(`red_rehearsal`). 심은 트리는 exit 1 이고 **심은 파일을 지목**해야 하며
    (JSON 과 사람이 보는 출력 양쪽), 같은 자리에 허용 형태를 넣은 **대조군은 초록**이어야 하고, 없는 트리는
    차단(exit 1)돼야 한다. 리허설되지 않는 층은 **이유와 함께 선언**돼야 하며(게이트 자기시험이 stage·카나리아
    roster 와 대조한다), 이유 없는 생략 · 대조군 오탐 · 사고(traceback)로 죽는 것은 모두 실패다.
15. 이 문서의 `<!-- measured:key=value -->` 마커가 실제 측정값과 일치하는가(`measured_markers`).

```sh
.venv/bin/python scripts/architecture_review.py                 # 검사 + 요약 표
.venv/bin/python scripts/architecture_review.py --output /tmp/t14.json
.venv/bin/python -m pytest tests/cognitive/test_architecture_review.py -q
```

측정 마커(이 값이 어긋나면 검사가 실패한다):

| key | value | 의미 |
|---|---|---|
| principles | 24 | 헌법 원칙 수(원문 §3에서 그대로 분리) |
| principles_covered | 15 | 증거로 닫힌 원칙 |
| principles_partial | 9 | 관찰됐으나 실환경·사람 결정이 남은 원칙 |
| principles_gap | 0 | 근거가 전혀 없는 원칙 |
| source_questions | 12 | 원문 §63 최종 리뷰 질문 |
| drift_questions | 10 | 원문 §52 Constitution Drift 질문 |
| drift_triggered | 0 | "YES가 있다"로 Architecture Review 대상이 된 질문 |
| evidence_docs | 16 | `docs/ssak-ai-core/evidence/*.md` 문서 수 |
| cognitive_tests | 579 | `tests/cognitive` 수집 시험 수 |
| regression_scopes | 9 | 전량 회귀를 나눠 잰 scope 수(flat 8구간 + subdir) |
| regression_runs | 21 | scope 당 두 회차 이상 · 3 scope 는 **수집 순서를 뒤집은 variant** 도 포함 · 중단 회차는 판정에서 제외 · 중단된 회차는 자동으로 한 번 다시 돌리고 그 횟수·로그를 남긴다 |
| regression_deterministic | 11 | 두 회차 모두에서 같은 실패 |
| regression_drift | 0 | seed 를 바꾸면 달라지는 실패 |
| regression_unowned | 0 | 소유자 없는 결정적 실패 |
| digest_pinned | 50 | 증거 문서가 파일에 못 박은 sha256 수 |
| digest_reverified | 22 | 그 뒤에 바뀌었지만 재확인 기록이 있고 그 뒤로 바뀌지 않은 pin |
| digest_drifted | 0 | 재확인 없이 지나간 revision 을 가리키는 pin |
| digest_stale | 0 | 재확인 뒤에 파일이 또 바뀌어 무효가 된 재확인 |
| digest_missing | 0 | 파일이 없는데 digest 를 못 박은 항목 |
| state_claims | 4 | 산문이 지금 트리에 대해 한 상태 주장(test node 지정) 수 |
| state_claims_fixed | 4 | 그중 실제와 달라 정정 표기를 붙인 주장 |
| state_claims_stale | 0 | 정정 없이 남은 낡은 주장 |
| state_claim_mentions | 6 | node 를 지목한 산문 줄 수 — 상태 어휘가 없어도 세는 상한 집합(탐지력 하한 1) |
| state_claim_probe_cases | 17 | 매 실행 자기시험이 다시 재판정한 항목 수(어휘·요구 어휘·펜스·정정 창·상태 계산) — 0이면 검사하지 않은 것이다 |
| canary_harnesses | 8 | 하한 카나리아가 눈멀게 한 사본으로 시험한 harness 수(여섯 측정 harness + 증거 게이트 + red 리허설) |
| canary_ok | 8 | 그중 정상 통과·사본 차단·근거 동봉을 모두 만족한 harness 수 |
| evidence_gate_stages | 9 | 한 번에 도는 증거 게이트의 stage 수(여섯 harness + 리뷰 + red 리허설 + 로컬 전용 회귀 원장) |
| rehearsal_layers | 2 | 저장소 밖 트리에 **진짜 위반을 심어** red 재현을 확인한 층 수(위반 0건이던 두 감사) |
| rehearsal_ok | 2 | 그중 심은 트리 exit 1·지목·대조군 초록·빈 트리 차단을 모두 만족한 층 수 |

<!-- measured:principles=24 -->
<!-- measured:principles_covered=15 -->
<!-- measured:principles_partial=9 -->
<!-- measured:principles_gap=0 -->
<!-- measured:source_questions=12 -->
<!-- measured:drift_questions=10 -->
<!-- measured:drift_triggered=0 -->
<!-- measured:evidence_docs=16 -->
<!-- measured:cognitive_tests=601 -->
<!-- measured:regression_scopes=9 -->
<!-- measured:regression_runs=21 -->
<!-- measured:regression_deterministic=11 -->
<!-- measured:regression_drift=0 -->
<!-- measured:regression_unowned=0 -->
<!-- measured:digest_pinned=50 -->
<!-- measured:digest_reverified=22 -->
<!-- measured:digest_drifted=0 -->
<!-- measured:digest_stale=0 -->
<!-- measured:digest_missing=0 -->
<!-- measured:state_claims=4 -->
<!-- measured:state_claims_fixed=4 -->
<!-- measured:state_claims_stale=0 -->
<!-- measured:state_claim_mentions=6 -->
<!-- measured:state_claim_probe_cases=17 -->
<!-- measured:canary_harnesses=8 -->
<!-- measured:canary_ok=8 -->
<!-- measured:evidence_gate_stages=9 -->
<!-- measured:rehearsal_layers=2 -->
<!-- measured:rehearsal_ok=2 -->

상태 정의:

- **covered** — 계약·시험이 있고, 이 source head에서 실제로 관찰했다.
- **partial** — 구현·시험은 있으나 실 환경(모델·vault·사람 승인)이 필요해 전체 인수가 닫히지 않았다. 남은 조건을 `한계` 열에 적는다.
- **gap** — 근거가 없다. 현재 **0건**이며, 0건이라는 사실 자체를 검사한다(gap이 생기면 리뷰가 실패한다).

## 1. 회귀 (T14 요구: 기존 test / lint / type / build)

`.venv`의 고정 환경에서 실행한 결과다. 이 표의 값은 CI job이 아니라 이 체크아웃에서 직접 실행해 얻은 관찰이다.

| 회귀 | 명령 | exit | 관찰 |
|---|---|---|---|
| 테스트(전체 · **과거 회차 이력**) | `.venv/bin/python -m pytest tests/ -m 'not slow and not benchmark' -q` | 1 | **세 번 쟀고 회차마다 달랐다**(트리·수집 오염·실행 선택이 함께 달랐던 비교 — 현재 기준선은 이 표의 아래 원장 행이다) — ①(수정 전 · random) 7723 수집 · **94 failed / 7571 passed / 14 skipped / 20 xfailed**(26:31) ②(random) 7726 수집 · **10 failed / 7660 passed** ③(**고정 순서** `-p no:randomly`) 7726 수집 · **7 failed / 7663 passed / 14 skipped / 24 deselected / 20 xfailed**(21:21) ④(**고정 순서 · 정리 뒤**) 7726 수집 · **5 failed / 7666 passed / 14 skipped / 24 deselected / 20 xfailed**(20:13). 그 차이는 seed 효과가 아니라 트리·오염·실행 선택의 차이였고, seed 를 가른 측정은 §1.2 의 원장이다, ③·④의 실패도 전부 기존 항목이다(그중 둘은 §1.5에서 등록으로 닫았다) |
| 테스트(cognitive core) | `.venv/bin/python -m pytest tests/cognitive -q` | 0 | 600 passed · 1 skipped (수집 601 — 원장 subdirs scope 2회에서도 결정적 실패 0) |
| lint | `.venv/bin/python -m ruff check src/ tests/ scripts/` | 0 | All checks passed |
| format | `.venv/bin/python -m ruff format --check src/ tests/ scripts/` | 0 | 1162 files already formatted |
| type | `.venv/bin/python -m mypy <cognitive·surface·cli·5 scripts>` | 0 | Success: no issues found in 29 source files |
| schema | `.venv/bin/python scripts/generate_record_schema.py --check` | 0 | schema up to date (record-entities/record-envelope) |
| architecture review | `.venv/bin/python scripts/architecture_review.py` | 0 | 15 checks PASS(회귀 원장 · 인용 추적 · digest 측정 · 상태 주장 재판정 · 하한 카나리아 · red 리허설 · 증거 게이트) |
| red 리허설 | `.venv/bin/python scripts/red_rehearsal.py --gate` | 0 | 층 2개에 진짜 파일로 위반을 심어 red 재현 — 심은 트리 exit 1·지목, **대조군(허용 형태) 초록**, 없는 트리 차단 |
| 증거 게이트(층 전부 한 번에) | `.venv/bin/python scripts/evidence_gate.py --tier full` | 0 | stage 9개 전부 PASS(리뷰 · 카나리아 · digest · 상태 주장 · enum · namespace · 표면 · red 리허설 · 회귀 원장) + **층별 수치를 기준과 대조** — `--tier fast` 는 로컬 회차가 필요한 회귀 원장을 **'보지 않은 층'** 으로 적는다 |
| 회귀 원장 | `.venv/bin/python scripts/regression_ledger.py --from-junit .regression-ledger --gate` | 0 | 9 scope · 21 회차(seed 101·202 + 순서 뒤집은 3회) · **결정적 11 · variant 민감 0 · 무소유 0** — 같은 scope 를 variant 를 바꿔 돌려 교집합/대칭차로 분리(§1.2) |
| enum identity 감사 | `.venv/bin/python scripts/audit_enum_identity.py` | 0 | 위반 0건 (cognitive core 95곳을 `same_enum`으로 통일) |
| namespace purge 감사 | `.venv/bin/python scripts/audit_test_namespace_purge.py` | 0 | 위반 0건 (수집 대상 시험 파일에 조건 없는 import 시점 purge 없음) |
| build(wheel/sdist) | `uv build --no-sources` + 배포 검증 | NOT_RUN | 릴리스 CI job 소관이며 이 체크아웃에서 실행하지 않았다 |

### 1.1 회귀가 찾아낸 것 — 네 부류를 발견해 고쳤다

전체 회귀를 돌린 목적은 통과 확인이 아니라 **깨지는 조건을 찾는 것**이었고, 실제로 cognitive core에서 한 건이 깨졌다.

**① `AuthorityProfile.evaluate`의 dimension identity 비교 (제품 코드).** 전체 `tests/` collection 문맥에서
`tests/cognitive/test_governance.py::test_tool_executor_requires_guard_reshaped_call`이 RESHAPE 대신 DEFER(권한 부족)를
받았다. 원인은 권한 판정이 값이 아니라 **class identity**로 이뤄진 것이었다. 프로세스 안에 `AuthorityDimension` class가
두 번 만들어지면(같은 이름·같은 값이지만 다른 객체) `grant.dimension is query.dimension`이 False가 되어, 유효한 grant가
"권한 없음"으로 잘못 흘러간다. dimension 비교를 값 동등성으로 바꾸고(`authority.py`), 중복 class 상황을 재현하는 회귀
시험(`test_dimension_equality_survives_a_duplicate_enum_class`)을 추가했다. **이것은 권한 판정이 조용히 약해질 수 있는
부류의 결함**이며, 회귀를 돌리지 않았다면 발견되지 않았을 것이다.

**② 중복 module 상황에서 patch가 엉뚱한 객체를 건드리던 시험 (시험 격리).** 같은 시험이
`patch("antigravity_k.engine.cognitive.governance.risk_profile_for")`처럼 경로 문자열로 patch하고 있었다. module이 두 번
로드되면 adapter는 옛 객체의 전역을 읽으므로 patch가 아무 효과가 없다. adapter의 `admit.__globals__`를 직접 patch하여
중복 여부와 무관하게 정확하게 만들었다.

**③ 같은 부류를 전수 점검했다 (구조적 보강).** ①은 한 자리만 고친 것이므로, cognitive core의 모든 enum 비교를
같은 기준으로 맞췄다. `models.same_enum(left, right)`은 **정의 module 이름·class 이름·값**을 함께 본다 —
module 중복 로드에는 관대하고(같은 이름·같은 값이면 매칭), 정의 module이 다른 enum에는 엄격하다(예: cognitive
`RiskLevel`과 도구 `RiskLevel`). `X is Enum.MEMBER` / `is not` 형태 **95곳**을 이 helper로 바꿨고, 이후 같은 패턴이
다시 들어오면 실패하는 감사(scripts/audit_enum_identity.py)와 계약 시험(tests/cognitive/test_enum_identity.py, 8건)을
추가했다. 감사는 지금 위반 0건이다.

sweep 후 전체 회귀를 다시 측정했다: **94 failed / 7571 passed / 14 skipped / 20 xfailed**(26:31). 실패 목록은 sweep 이전 회귀와 **완전히 동일**하고(신규 실패 0), 통과 수는 추가한 8건만큼 늘었으며, `tests/cognitive` 실패는 0이다. 즉 95곳 치환은 동작을 바꾸지 않고 판정의 전제만 강하게 만들었다.

**④ 오염원 자체를 제거했다 (시험 격리).** ③까지는 "중복 class가 생겨도 판정이 견디게" 만든 것이고,
중복을 **만들던 원인**은 남아 있었다 — `tests/test_flush_budget_contract.py` 가 **import 시점에** `sys.modules` 의
`antigravity_k.*` 를 전부 지우고 있었다(미러 리허설이 다른 트리의 바이트를 검사하기 위한 정당한 의도). 승격된 이 파일은
일반 suite 가 함께 수집하므로, 먼저 import 된 시험 파일은 옛 class 객체를 잡고 뒤에 import 되는 module 은 같은 이름의
새 객체가 되어 **판정이 실행 순서에 따라** 달라진다. 조건화(`NX10_FLUSH_TREE` 를 지정한 미러 리허설에서만 비운다)로
원인을 없애고, 승격본과 staged 쌍둥이(`docs/qa/.../fsync/`)·아직 승격되지 않은 fsync2(F2)까지 같은 형태로 맞췄다.
재발 방지는 감사(`scripts/audit_test_namespace_purge.py`, 위반 0건)와 계약 시험
(`tests/cognitive/test_module_namespace_isolation.py`, 5건 — 파일 순서에 기대지 않는 행위 확인을 포함)이다.
**미러 리허설은 그대로 돈다**: `rehearse_flush.sh` PASS 17 · FAIL 0(P1 적용 전 3 failed 로 이빨이 물고, P2 적용 뒤 9 passed).
재현·수정·리허설 관찰 전문은 `evidence/T14_namespace_isolation.md` 에 있다.

### 1.2 전량 회귀 — variant 원장으로 측정한 현재 기준선

회귀 수치는 **서술이 아니라 원장에서만** 인용한다. `scripts/regression_ledger.py` 가 같은 scope 를 **variant 를 바꿔**
(기본 `seed-101`·`seed-202`, 일부 scope 는 **수집 순서를 뒤집은** `rev-seed-101` 도)로 돌리고 junit XML 만 읽어 **교집합(결정적)** 과 **대칭차(variant 민감)** 를 계산한다. 502개 파일을 8구간 +
subdir 로 나눠 **21회**(그중 3회는 수집 순서를 뒤집었다) 쟀다.

| 항목 | 값 | 의미 |
|---|---|---|
| scope / 회차 | 9 / 21 | scope 당 두 회차 이상(variant: seed·수집 순서) · 중단 회차는 판정 제외(중단되면 같은 조건으로 한 번 자동 재시도하고 횟수·로그를 남긴다) |
| 결정적 실패 | **11** | 두 회차 모두에서 같은 실패(전부 소유자 지정) |
| variant 민감 실패 | **0** | seed 또는 수집 순서를 바꾸면 달라지는 실패 |
| 무소유 | **0** | 소유자가 없는 결정적 실패 |

회차별 `failed` 수도 variant 쌍마다 같았다(예: `flat-221-314` 는 두 회차 모두 `3 failed, 1283 passed`,
`flat-081-220` 은 두 회차 모두 `2 failed, 1837 passed`). **수집 순서를 뒤집은 회차도 같은 집합을 냈다** — 3 scope
(`flat-001-080` 0건 · `flat-081-220` 2건 · `flat-457-502` 5건)에서 파일 목록을 역순으로 돌렸고, 결정적 실패도
수집 수도 같았다. 즉 이 체크아웃에서 **빨간 합이 seed 로도 순서로도 움직이지 않는다** — "순서 artifact" 라는 이전
서술은 그 효과를 분리한 측정이 아니었고, 이 원장으로 **대체**한다.

| 결정적 실패 | 건수 | 소유자 |
|---|---|---|
| `test_cr14_fence_movement_detection.py` | 2 | cr14-lane(커밋 이력·트리 지문) |
| `test_nx07_doc_consistency.py` | 2 | release-owner(EX-05 대장 행 두 단계 분리) |
| `test_model_registry.py` | 1 | config-owner(번들 기본값 ≠ 저장소 `config.yaml`) |
| `test_ws01_project_binding.py` | 5 | ws01/cr01-lane(대화 저장소 v2 마이그레이션 전 · 단독 재현) |
| `test_trn02_timeout_resource.py` | 1 | trn02-lane(학습 job cancel API · 단독 재현) |

ws01·trn02 6건은 이전 회차 기준선(5건)에 없던 항목이다. 같은 트리에서 단독 실행으로도 재현되므로 회차 조건 탓이
아니지만(6 failed / 32 passed), "무관하다"고 단정하지 않고 **레인 이름을 붙여 원장에 남겼다**. 방법·이빨·한계·중단된
회차 처리는 `evidence/T14_regression_ledger.md` 에 있다(중단 재현·죽는 사이트·probe 실패 이유는 §5a).

#### 과거 회차(94 → 10 → 7 → 5)의 재해석

실패 94건은 **cognitive core 밖**이며, 변경 전 회귀(95 failed)와 실패 목록이 **완전히 동일**하다(유일한 차이는 위 ①이
고쳐져 빠진 1건). 즉 이번 변경이 만든 실패는 없다.

이 목록은 회차마다 **달랐다** — 다만 그 비교는 트리 변화·수집 오염·실행 선택이 함께 달라진 상태의 비교였고, seed 효과를 가른 측정은 아니었다. 같은 명령을 뒤에 다시 돌렸을 때(random 순서가 달라짐) 실패는
**10건**으로 줄었고, **고정 순서**(`-p no:randomly`)로 돌린 세 번째 회귀에서는 **7건**이었다 — 브라우저·diff·API 인증·
ctx/cr 게이트의 대부분은 suite 순서·동시 실행에서 오는 artifact이고, 고정된 baseline이 아니다.

가장 보수적인 고정 순서 회귀 두 번(③ 21:21 · ④ 20:13)의 실패는 **7건 → 5건**이었다. 그 5개 파일을 단독 실행해도
같은 집합이 재현된다(정리 전 86 passed / 7 failed · 정리 뒤 89 passed / 5 failed · `-p no:randomly`). 아래 표의 7건 중
둘은 §1.5 에서 닫았고, 나머지 5건은 그 소유자의 결정이 필요한 항목으로 남긴다.

| 실패 | 건수 | 관찰된 원인 | 이 작업과의 관계 |
|---|---|---|---|
| `test_cr14_fence_movement_detection.py` | 2 | git 이력 기반: 선언 후보 커밋 뒤에 코드 스코프 커밋이 움직였고, HEAD 트리 지문이 선언값과 다르다 | 무관 — 커밋을 만들지 않았고 두 시험은 **커밋 객체**를 비교한다 |
| `test_cr14_gate_skip_register.py` | 1 | `dashboard/e2e/ssak-web-integration.spec.ts:191` 의 조건부 skip 마커가 등록 없이 남아 있다 | 무관 — §1.5 에서 **등록으로 닫았다** |
| `test_model_registry.py` | 1 | 번들 `config.yaml` 에 저장소 설정의 `search:` 절이 없다 | 무관 — config 는 다른 작업자가 편집 중인 파일이다 |
| `test_nx07_doc_consistency.py` | 2 | `docs/20_CURRENT_STATUS.md`·CR-14 대장의 **기준선 자체가 이미 위반**(EX-05 상태 셀) | 무관 — 기존 문서 기준선 |
| `test_tool_sandbox_coverage.py` | 1 | `tools/ssak_bundle_store.py` 의 `subprocess.run` 이 ALLOWLIST 미등록 | 무관 — §1.5 에서 **등록으로 닫았다** |

### 1.3 인용이 추적되는지까지 본다 — 증거로 인용된 파일이 git 에 없던 건을 닫았다

`evidence/T11_surface.md` 는 `tests/test_cognitive_surface_api.py` 를 **sha256(`2cccfed8d5f499c1…`)과 11 시험**까지
적어 인용하고 있었는데, 그 파일이 **추적되지 않았다**(내용은 인용된 digest 와 정확히 일치했고 11 시험 모두 통과한다).
실재만 보는 검사(`artifacts_exist`)로는 이 상태가 통과한다 — 이 체크아웃을 잃으면 근거가 사라지는데도 그렇다.

그래서 검사를 하나 붙였다: 문서가 문장으로 인용한 저장소 경로(`tests`·`scripts`·`src`·`dashboard`·`tools`·`config`·
`data` 아래의 파일)를 축약 표기까지 해석해서(`tools/ssak_bundle_store.py` → `src/antigravity_k/tools/ssak_bundle_store.py`),
**실재 + 추적**을
요구한다. glob·생략 표기(`tests/test_cr14_*.py` · `docs/qa/.../x.py`)는 파일이 아니라 패턴이라 세지 않는다.

등록이 필요한 미추적 인용은 여섯 건이고 성격이 서로 다르다 — 그 차이를 코드에 남겼다:

| 인용 | 왜 추적되지 않는가 |
|---|---|
| `tools/ssak_bundle_store.py` · `tools/cowork_delegate.py` | 축약 표기 — 검사가 `src/antigravity_k/` 아래로 해석한다(등록 불필요) |
| `evidence/benchmark_spec.md` | 아직 만들지 않은 **목표** 산출물(ROADMAP 이 그렇게 명시) |
| `src/innocent.md` | T01b 의 symlink **예시** 경로 — 실재하는 파일이 아니다 |
| `tests/test_aa_purge_probe.py` | 순서 오염 재현용 **임시 진단** — 명령 기록만 남기고 파일은 지우는 것이 의도 |
| `docs/qa/2026-09-16-followup/nx10/fsync{,2}/*` 3건 | 다른 레인의 미추적 QA 산출물 — 이 카드가 커밋 여부를 결정하지 않는다 |

등록은 **면죄부가 아니다**: 등록된 경로가 추적되면 낡은 등록으로 실패하고, 재검토 기한이 지나도 실패한다.
그 이빨을 시험 여섯 건으로 고정했다(미추적 인용 · 낡은 등록 · 기한 경과 · 축약 해석 · glob/생략 제외 · 저장소 통과).
현재 검사 대상은 **214건**이고 모두 실재·추적된다.

### 1.4 증거의 digest 는 시점 스냅샷이다 — 21개 pin 이 지금 파일과 다르다

증거 문서는 인용한 파일의 sha256 을 함께 적는다(`models.py (sha256 65abe58b…)`). 그 digest 는 "내가 이 파일을
봤다" 는 **그 시점의 기록**이고, 파일이 그 뒤에 바뀌면 그 증거는 **지나간 revision 을 가리키게 된다**. 문서만
읽어서는 알 수 없으므로 측정했다(`scripts/digest_drift.py` → `evidence/digest_drift.json`).

| 항목 | 값 | 의미 |
|---|---|---|
| pin | **50** | 증거 문서가 파일에 못 박은 digest 수 |
| 그대로 | **29** | 그 digest 가 지금 파일과 일치한다 |
| 움직임 | **21** | 그 파일이 그 뒤에 바뀌었다 — 증거가 현재 내용에 대해 다시 확인되지 않았다 |
| 깨짐 | **0** | 파일이 없는데 digest 를 못 박은 항목 |

움직인 21건은 13개 문서에 퍼져 있다: T01a `models.py` · T01b `protected_targets.py`·`tests/test_tool_sandbox_coverage.py` ·
T02 `store.py`·`legacy_adapter.py` · T03/T04 `context.py` · T05 `authority.py`·`governance.py`·`tests/cognitive/test_governance.py` ·
T06 `decisions.py`·`readiness.py` · T07 `actions.py` · T08/T09 `runtime.py`·`experience.py` · T10 `learning.py`·`policy_store.py` ·
T11 `cognitive_surface.py` · T13 `growth.py`·`scripts/benchmark_cognitive_growth.py` · T13 live pilot `live_pilot.py`.
그중 `authority.py`·`actions.py`·`cognitive_surface.py` 등은 **이 카드의 회귀가 찾은 수정**(§1.1 ①·③, T11 배선)이
들어간 파일이다 — 즉 움직임은 오류가 아니라 이력이다.

이 스크립트가 **하지 않는 것**: digest 를 자동으로 갱신하는 일. 갱신은 "그 증거를 다시 확인했다" 는 주장이 되는데,
그것은 사람이 그 내용을 다시 봐야 하는 일이다. 그래서 측정만 하고, 움직인 것을 먼저 **이월 항목**으로 남겼다(§5).
저장본도 썩지 않게 했다: 파일을 고치면 다음 `architecture_review` 실행에서 `digest_report` 가 실패하고 다시 재게 한다.

#### 그 21건을 다시 확인했다 — 계약 시험 수준에서

이월만 남기면 다음 사람이 같은 일을 처음부터 한다. 그래서 21건을 실제로 다시 확인하고 **재확인 기록**을 남겼다
(`evidence/digest_reverification.json` · `digest_drift.py --record <문서> --method "..."`). 재확인은 `--method` 없이는
기록되지 않고, 그 문서에서 **지금 움직인 pin** 만 대상으로 한다(낡은 재확인·과장된 재확인을 만들지 않는다).

| 확인 수준 | 이번에 한 것 |
|---|---|
| 계약 시험 재실행 | 증거가 인용한 시험 파일을 현재 트리에서 다시 돌렸다 — `test_models` 58 · `test_store` 17 · `test_legacy_adapter` 8 · `test_context` 13 · `test_governance` 32 · `test_readiness` 28 · `test_actions` 17 · `test_episode` 21 · `test_learning` 29 · `test_surface` 20 (+`test_cognitive_surface_api` 11) · `test_growth` 17 · `test_live_pilot` 12 · `test_protection` 19 — **전부 통과** |
| 선언 수치 대조 | 문서가 적은 시험 수는 대부분 그대로였다(13·28·17·21·29·20·17·12). `test_governance` 만 31 → **32**(중복 enum 회귀 시험 추가). 파일 크기는 스냅샷 이후 조금씩 늘었다(예: `learning.py` 1221→1230 · `cognitive_surface.py` 647→681 — 뒤는 이 카드의 배선 작업) |
| 스크립트 재실행 | `generate_record_schema.py --check` up to date · `measure_cognitive_surface.py` 재실행 · `benchmark_cognitive_growth.py --print-spec` spec digest 출력 |

**이번 재확인이 주장하지 않는 것:** 실모델·실 vault·사람 승인 표면에서 다시 본 것이 아니다. 그 부분은 각 증거 문서의
`limitations` 에 있고, 그대로 미완이다(§5). 즉 여기서 닫힌 것은 "그 파일이 그 뒤 바뀌었는데 계약은 아직 서는가" 라는
질문이고, "실환경에서도 서는가" 는 여전히 열려 있다.

재확인은 영구 면제가 아니다 — 그 파일이 **또** 바뀌면 재확인은 무효(`stale_reverification`)가 되고 게이트가 실패한다.
그래서 `digest_report` 는 "재확인 22건이 지금도 유효한가" 를 매 실행마다 본다.

재확인 과정에서 증거 문장 하나가 낡은 것도 드러났다: `T01b_protection.md` 가 `tools/ssak_bundle_store.py` 때문에
**"기존 red"** 라고 적은 시험은 §1.5 의 등록으로 이미 green 이었다 — 그 문장에 정정을 붙였다(역사는 지우지 않았다).
그러자 같은 부류가 **하나가 아니었다.**

#### 문장 자체를 재판정한다 — 상태 주장 감사

증거 문서에는 두 종류의 문장이 섞여 있다: **시점 기록**(`verified_at` 이 붙은 스냅샷 — 낡아도 역사)과
**지금 트리에 대한 주장**(“이 시험은 실패한다” — 낡으면 틀린 문장). 뒤엣것을 기계로 재판정한다
(`scripts/audit_state_claims.py`).

감사 범위를 의도적으로 좁게 잡았다 — 넓게 잡으면 오탐으로 못 쓰게 된다:

* **test node 를 지목한 문장만** 본다(`tests/cognitive/test_state_claims.py::test_claim_that_matches_the_tree_is_ok`). 파일 단위 서술은 “그렇지 않으면 실패한다” 같은
  조건문과 섞여 기계가 참·거짓을 가를 수 없다.
* **코드 블록 안은 보지 않는다.** 펜스 안은 그때 돌린 명령·출력의 기록이고, 펜스 밖 산문만 주장이다.
* 같은 줄에 상태 어휘(red·실패·failed ↔ green·통과·passed)가 있어야 센다.
* **증거 문서만 본다.** 처음에는 이 리뷰 문서까지 감사했는데, 바로 아래 문단처럼 낡은 문장을 **인용해 해설**하는
  줄이 주장으로 잡혔다(감사가 4건이 아니라 5건을 보고했다). 관찰을 주장하는 자리는 증거 문서이므로
  범위를 그쪽으로 좁혔고, 넓히면 자기 해설로 오탐이 난다는 사실도 harness docstring 에 적었다.

| 항목 | 값 | 의미 |
|---|---|---|
| 상태 주장 | **4** | 산문이 test node 를 지목해 지금 트리에 대해 한 주장 |
| 그대로 | **0** | 실제 상태와 일치했던 주장 |
| 정정 붙임 | **4** | 실제와 달라 **정정 표기**를 붙인 주장 |
| 낡음 | **0** | 정정 없이 남은 주장 |

넷은 전부 같은 시험에 대한 것이었다 — `tests/test_tool_sandbox_coverage.py::test_all_process_execution_paths_are_accounted_for`
는 T01b·T03/T04·T06·T07 네 문서가 “기존 red”·“실패는 그대로” 라고 적었지만, 그 시험은 §1.5 의 등록 뒤 **green** 이다.
네 문서 모두 문장을 지우지 않고 `> **2026-09-23 정정.**` 인용문을 달았다 — 감사는 정정 표기가 붙은 주장을
`FIXED` 로 보고 통과시키고, **정정 없이 실제와 어긋나는 주장이 하나라도 있으면 리뷰가 실패한다**.

이 감사는 **문장을 읽는 기계**이므로, 스스로 눈이 머는 경우를 따로 막았다. 그렇지 않으면 어휘를 지우거나 문서
형식이 바뀔 때 **“주장 0건”** 이 되어 조용히 통과한다 — 가장 위험한 실패다.

| 장치 | 무엇을 막나 | 지금 값 |
|---|---|---|
| **운영 자기시험**(self-probe) | 매 실행마다 어휘·펜스 처리·정정 창·상태 계산을 합성 입력으로 다시 재판정한다. 어휘를 비우거나 단어 하나를 지워도(`green` 삭제) 그 실행이 바로 실패한다 | **17건 재판정 — 통과** |
| **요구 어휘 고정** | 상수를 쓸어보기만 하면 **지워진 단어**는 안 보인다. `_REQUIRED_FAIL_WORDS`/`_REQUIRED_PASS_WORDS` 를 따로 두어 빠지면 실패 | 실패 4 · 통과 3 단어 |
| **탐지력 하한**(coverage floor) | 주장 수뿐 아니라 **node 를 지목한 산문 줄 수(mention)** 를 센다(상태 어휘가 없어도 세므로 주장의 상한 집합). 하한 아래로 가면 게이트 실패 — 정말 주장이 사라졌다면 상수를 근거와 함께 사람이 내린다 | mention **6≥1**(여유 5) · 주장 **4≥1**(여유 3) |
| **하한의 근거 기록** | 하한은 판단이므로 **값만 남기면 나중에 내려도 되는지 아무도 판단할 수 없다**. `Floor` 가 `why`(언제 무엇을 몇 개 봤나)와 `margin`(관측−하한)을 함께 갖고, 각 harness 가 그 기록을 artifact 로 남긴다. 리뷰는 저장본과 새 측정을 대조하고 **근거가 빈 하한도 실패**로 본다 | **여섯 harness 전부** · `2026-09-23 기준 관측` 문장 12개 |

자기시험이 실패하면 **판정 결과와 무관하게 그 실행은 실패**다: 판독 규칙이 깨진 실행은 증거가 아니다.
리뷰도 같은 것을 본다 — `state_claims` 검사가 **자기시험 부재·실패 · 하한 미달 · 하한이 기록되지 않음 · 근거 없는
하한 · 저장본이 낡음**을 모두 실패로 잡는다. 실패 메시지도 감사가 기록한 근거를 그대로 인용한다(값만 옮겨 적지 않는다).

즉 이제 증거는 다섯 층으로 검사된다: **실재 → 추적 → 시점(digest) → 계약(재확인) → 문장(상태 주장)** —
그리고 그 문장을 읽는 감사자 자신이 **여섯 번째 층**에서 매번 자기 눈을 확인한다.

#### 여섯 번째 층을 공통 계약으로 올렸다 — `scripts/harness_contract.py`

상태 주장 감사에 붙인 자기시험·하한은 그 감사만의 것이 아니었다. **측정 harness 는 모두 같은 방식으로 눈이 멀 수 있다**:
문서 형식이 바뀌어 pin 을 하나도 못 찾으면 digest 측정은 “pin 0 · 움직임 0” 으로, junit 을 못 읽으면 원장은
“결정적 0 · drift 0” 으로, 패턴을 바꿔 인용을 못 찾으면 리뷰는 “인용 0건 모두 추적됨” 으로 통과한다.
그래서 두 장치를 공통 module 로 올렸다(`Probe`/`Cases` · `Floor`). 이 회차에 여섯 harness 가 계약을 쓴다 — 마지막 하나
(`measure_cognitive_surface`)는 **게이트 자체가 없어서** 빈 표를 내도 exit 0 이었다(실측 artifact 를 내는데도).

| harness | 자기시험 (매 실행 재판정) | 탐지력 하한 |
|---|---|---|
| `digest_drift` | **9건** — 경로+digest 판독, 경로 없는 `sha256` 배제, 경로 해석, 상태 4종(그대로·움직임·재확인·무효) | pin **50** · pin 을 박은 문서 **13** (하한 1·1) |
| `regression_ledger` | **11건** — junit 판독(수집·skip·실패/오류 둘 다 빨강·중단 표시), `testsuite` 없으면 예외, 회차 0개면 예외, 결정적 판정 | 회차 **21** · scope **9** (하한 1·1) |
| `audit_state_claims` | **17건** — 어휘·요구 어휘·펜스·정정 창·상태 계산 (앞선 회차) | mention **6** · 주장 **4** |
| `audit_enum_identity` | **5건** — identity 비교 2건(종류 구분), 값 비교·리터럴 제외, 제외 목록·스캔 범위 | 스캔한 파일 **≥10** |
| `audit_test_namespace_purge` | **6건** — 미가드 purge 1건, `del` 형태, 트리 override 허용, 함수 본문 제외, 무관한 mapping | 수집 대상 파일 ≥1 (실제 **537**) |
| `measure_cognitive_surface` | **6건** — 실재 모듈 식별, core 도달 판독, 없는 모듈 배제, entrypoint 표 유지, 판독기 예외도 실패로 보고 | entrypoint **9** · 실재 **9** (하한 1·1) |

하한은 **“찾은 것이 없다” 와 “볼 수 없다” 를 가르는 값**이라 낮게 잡았다(하한 1). 올려 잡으면 새 문서가 생길 때마다
숫자 싸움이 되고, 낮게 잡아도 판독 규칙이 죽는 순간은 잡는다. 하한을 **내리는 것은 근거와 함께 사람이 하는 결정**이며,
그 문장을 각 스크립트의 상수 옆에 적어 두었다. 인용 추적의 하한만 **저장소 기본 범위**에 걸린다 — 부분 범위를 넘기는
호출(시험의 합성 문서)은 그 범위를 정한 호출자가 하한을 소유한다.

하한의 **근거는 여섯 harness 가 모두** 값과 함께 기록한다(`why` = 하한을 정한 시점의 관측, `margin` = 관측−하한).
기록된 문장은 “2026-09-23 기준 관측: …” 로 시작하고, 각 harness 의 artifact(`digest_drift.json` ·
`regression_ledger.json` · `state_claims.json` · 표면 실측 JSON 등)에 `floors` 로 실린다. 리뷰가 보는 것은 두 종류다 —
**기록이 아예 없는 하한**(`floors` 에 없다)과 **근거가 빈 하한**(`why` 가 공백), 그리고 저장본이 새 측정과 다른 경우
(`digest_report` 는 `floors` 까지 비교한다). 즉 하한을 올리고 내리는 변경은 **근거 문장을 고치고 artifact 를 다시
만들어야** 반영된다.

#### 마지막 구멍 — 하한이 **장식**일 수 있다

기록이 갖춰져도 남는 경우가 있다: `minimum=0` 이거나 비교가 뒤집혀 있으면 “기록도 있고 자기시험도 통과”
하는데 **아무것도 막지 못한다**. 카나리아(`scripts/harness_canary.py`)가 각 harness 의 하한을 **일부러 눈멀게 한
사본**(`observed=0`)으로 평가해 세 가지를 본다 — ① 정상 측정은 막지 않고, ② 사본은 막으며, ③ 실패 문장이
**기록된 근거를 함께 낸다**. 현재 여덟까지 본다 — 여섯 측정 harness + 증거 게이트 + red 리허설이 전부 통과한다
(`harness_canary` 검사 · marker `canary_harnesses` 8 · `canary_ok` 8).

기준을 어디서 가져오는지도 적어 두었다: `digest_drift`·`regression_ledger`·`audit_state_claims` 는 **기록 artifact**
(리뷰가 읽는 것과 같은 자리), 나머지 다섯은 저장소를 직접 재서 얻는다 — 회차 산출물(junit)이 있어야 관측값이 나오는
원장을 빈 원장으로 기준 삼으면 “정상 측정을 막는다” 는 오탐이 난다(카나리아가 첫 실행에서 실제로 그랬다).

이 카나리아 자신도 시험에 물려 있다(`tests/cognitive/test_harness_canary.py` 11건): 하한 없는 harness 는 통과가 아니라
실패이고, `minimum=0` 하한은 장식으로, 정상 측정을 막는 하한은 고장으로, harness 가 예외로 죽으면 그것도 판정으로
보고된다. 그 시험이 카나리아의 실제 버그를 하나 잡았다 — 근거가 빈 하한을 “문제 있음” 으로 적으면서도 `ok` 는 참으로
남는 모순(빈 목록에 대한 `all()` 이 참이라는 함정)을 없앴다.

**종료 코드도 판정이다 — JSON 을 낸다고 성공을 알리면 안 된다.** 처음에는 `--emit-json` 이 결과와 무관하게 exit 0
이었다. 그래서 그 출력을 읽는 쪽(리뷰·CI)은 “돌았는데 통과했다” 와 “돌았지만 아무것도 못 막았다” 를 종료 코드로
구분할 수 없었다. 이제 장식 하한이 하나라도 있으면 **`--emit-json` 도 exit 1** 이고, JSON 은 stdout 에 그대로 남는다
— 판정(종료 코드)과 진단(JSON)이 함께 나온다. 리뷰 쪽도 같은 자리를 고쳤다: `measure_canary` 는 종료 코드가 0 이
아니어도 **JSON 이 읽히면 그대로 쓰고**, 종료 코드를 보고에 실어 검사가 모순을 잡게 한다 — 보고는 전부 통과라는데
카나리아가 스스로 실패했다고 말하면 실패하고, 종료 코드 없는 보고·합계가 항목과 다른 보고도 실패한다. 이음매에서
진단을 뭉개지 않는지 — 카나리아가 exit 1 로 끝나도 **어느 harness 의 하한이 못 물었는지**가 판정 문장에
남는지 — 는 리뷰 쪽 시험 13건이 고정한다(`tests/cognitive/test_architecture_review.py`).

각 harness 는 `--self-test` 로 자기시험만 돌릴 수 있고(측정·기록 없음), 리뷰는 자기시험 **부재**도 실패로 본다:
판독력을 확인하지 않은 수치를 증거로 옭기지 않는다.

**"JSON 을 낸다" 가 "통과했다" 는 뜻은 아니다 — 같은 이음매가 두 층에 더 있었다.** 카나리아에서 고친 그 자리
(`--emit-json` 이 결과와 무관하게 exit 0)를 전수 확인해 보니 **두 층이 같은 병을 앓고 있었다**: `digest_drift` 는
가리킨 artifact 가 없는 store 에서 `--gate` 는 exit 1 인데 `--emit-json` 은 exit 0 을 냈고(실제로 그랬고, JSON 은
17KB를 그대로 냈다), `audit_state_claims` 도 같았다. 그래서 리뷰의 `returncode != 0` 검사는 그 두 자리에서 죽은
코드였고, 층이 스스로 빨간 것을 아무도 종료 코드로 받지 못했다 — 이제 두 경로가 **같은 판정**을 쓰고(JSON 은
stdout 에 그대로 남는다), 리뷰는 그 셋을 같은 규칙으로 읽는다: 종료 코드가 0 이 아니어도 **JSON 이 읽히면 그대로
쓰고** 종료 코드를 보고에 실어서, ① **종료 코드 없는 보고**는 판정이 아니고 ② 보고서는 문제가 없다는데 실행이
스스로 실패했다고 말하면 **모순**으로 실패한다(같은 결함이 이미 지목됐을 때 모순으로 두 번 세지는 않는다).
이빨은 `test_digest_drift`·`test_state_claims`(“같은 store 에서 `--emit-json` 과 `--gate` 가 같은 결론”)과
리뷰 쪽 6건(종료 코드 부재·모순·정말 결함일 때는 중복해서 세지 않음·exit 1 이어도 JSON 을 살리는지·JSON 이
아니면 None·상태 주장에도 같은 규칙)이다.

**판정과 추이가 리뷰어에게 닿는 자리 — 두 워크플로가 모든 변경을 덮는다.** 게이트가 CI 에서 도는 것만으로는
부족했다: ① `ci.yml` 은 `paths-ignore: docs/**, **.md` 이므로 **문서만 바꾼 PR 은 게이트를 건너뛴다** —
그런데 게이트가 주로 보는 것이 문서·증거라 그 구멍은 실질적이었다. ② 실행 결과가 artifact 로만 남아서,
리뷰어가 “어느 층이 얇아졌나” 를 보려면 내려받아 열어야 했다. 이제 `evidence.yml` 이 그 여집합
(`docs/**`·`**.md`)을 맡고(둘을 합치면 모든 변경이 덮인다 — 코드+문서를 함께 바꾼 PR 은 둘 다 돌지만 각자
30초 안쪽이다), 게이트가 `--summary` 로 **markdown 요약**을 내면 두 워크플로가 그걸 `$GITHUB_STEP_SUMMARY`
에 붙이고 PR 에는 같은 댓글을 갱신하며 artifact 2종(JSON·md)을 올린다. **빨간 실행도 요약을 남긴다**
(`if: always()`) — 요약이 사라지면 리뷰어는 다시 돌려야 하고, 그 사이에 트리가 바뀌면 같은 것을 못 본다.
요약 자체가 판정을 담으므로(`verdict: PASS|FAIL` · 층별 표 · 보지 않은 층 · 기준 대비 움직임 · 문제 목록)
리뷰어가 보는 것과 게이트가 종료 코드로 말하는 것이 같은 한 번의 실행에서 나온다. 배선은 시험이 본다
(txt 수준): 두 워크플로가 같은 명령을 돌리는가 · 한쪽이 문서를 무시하는 전제가 아직 살아 있는가 ·
`--summary` 와 `GITHUB_STEP_SUMMARY` 를 둘 다 쓰는가.

**"어제보다 얇아졌는가" — 층별 수치와 기준.** `exit_code` 만 보면 “지금 빨간가” 밖에 모른다. 그래서 게이트는 층마다
**한 번의 실행으로** 판정과 수치를 함께 받는다(`--emit-json`·`--json`·`--output`; 그 경로가 실패를 종료 코드로 말하지
않으면 여기서 판정이 사라지므로 이음매가 먼저였다). 두 번 돌리면 시간이 두 배가 되고 서로 다른 순간을 가리킨다.
수치는 stage 가 **지목한 키**만 펀다(`counts`·`coverage`·`measured`·`count`·목록은 길이) — 무엇을 비교하는지가
roster 한 줄에 드러나야 하고, 새 층이 엉뚱한 수를 실어도 추이에 섞이지 않아야 한다. 이번 실행이 본 65개 수치를
저장소의 **기준**(`evidence/evidence_gate_baseline.json`, 사람이 마지막으로 승인한 상태)과 비교해 **줄어든 수를 먼저**
보여 주고, 그대로인 수는 접는다(안 움직인 60줄 사이에 답이 묻힌다).

**이동은 판정이 아니다.** 수가 줄었다고 실패시키지 않는다 — 하한을 깨는 감소는 그 층의 자체 게이트가 이미
실패시킨다. 게이트가 실패로 보는 것은 셋이다: **수치를 읽지 못한 층**(수가 안 보이는 층의 추이는 증거가 아니다) ·
**못 돌린 층** · **깨진 기준 파일**(읽지 못한 기준을 “기준 없음” 으로 삼키면 그 뒤의 모든 추이가 거짓말이 된다).
기준은 `--record-baseline --method` 로만 갱신된다(무엇을 보고 승인했는지 없이는 거부하고, `recorded_on`·수치를
함께 남긴다). 게이트는 기준을 **읽기만** 하므로 돌리는 것만으로 승인 기록이 바뀌지 않고, **첫 실행은 “기준 없음”**
이라고 말한다 — 이번 회차에 실제로 잡은 움직임 하나: `review · measured.cognitive_tests 558 → 574 ▲`.

**“위반 0건” 이 관찰인지 미관찰인지 — red 를 심어 본다.** 자기시험은 판독 **규칙**을 합성 문자열로 재판정하고,
하한은 “볼 수 있는가” 를 지키고, 카나리아는 하한이 장식이 아닌지 본다. 셋 다 지나도 한 가지는 남는다: **그 감사가
진짜 위반을 보고 빨간을 낸 적이 있는가.** 이 체크아웃의 두 감사(`audit_enum_identity`·`audit_test_namespace_purge`)는
위반이 0건이라 green 의 뜻이 “다 봤는데 깨끗하다” 인지 “한 번도 빨간을 본 적이 없다” 인지 실행으로는 갈리지 않았다
(코드 경로를 읽어 확인했을 뿐이다). `scripts/red_rehearsal.py` 가 그 물음을 닫는다 — 심는 자리를 **저장소 밖 임시
트리**로 두고, 두 감사에 `--root`(감사 대상 트리, 기본은 지금까지처럼 저장소 루트)를 열어 실제 파일로 위반을 심는다:
① 심은 트리는 exit 1 이고 **심은 파일을 지목**한다(JSON 과 사람이 보는 출력 양쪽) ② **대조군** — 같은 자리에 허용
형태를 넣으면 초록이다(이것이 없으면 “새 파일이 생겨서 빨간” 과 구분할 수 없다) ③ 없는 트리를 가리키면 exit 1 이다
(빈손 스캔은 판정이 아니다 — 이 하한은 `--root` 를 쓸 때도 문다). 리허설 자신도 ① 못 본 층 ② exit 0 ③ 지목 없음
④ 대조군 오탐 ⑤ 빈 트리 통과 ⑥ 사고(traceback)를 각각 실패로 바꾸며(자기시험 19건), 리허설되지 않는 층은 **이유와
함께 선언**한다 — 게이트 자기시험이 그 목록을 stage·카나리아 roster 와 대조해 **red 재현 경로가 없는 층**이 조용히
생기지 않게 한다(이 리허설 자신도 카나리아 여덟 번째로 하한이 무는지 확인된다). 리뷰는 두 감사 각각에 `--root` 로
그 트리만 보게 하는지, 기본값이 저장소 루트 그대로인지를 계약 시험으로 고정한다.

**게이트를 도는 자리 — 층을 한 번에.** harness 마다 게이트가 있어도 그것을 도는 자리는 사람의 기억뿐이었다:
CI 는 하나도 돌리지 않았고, 어디가 얇은지 보려면 여덟 개 명령을 손으로 쳐야 했다. `scripts/evidence_gate.py` 가 그
자리를 하나로 묶는다 — stage 마다 **독립 process** 로 돌리고 종료 코드·소요 시간·**첫 실패 문장**을 모아 어느 층이
빨간지 이름으로 말한다(fast tier 7 stage · 17초). 이 도구도 같은 병을 앓을 수 있어(스크립트 이름이 틀려 아무것도
실행되지 않거나, stage 목록이 줄거나, tier 밖 층이 초록으로 덮이는 것) 같은 규율을 적용했다: **없는 스크립트·없는
산출물·제한 시간 초과는 `unrun`(실패)** 이고 `exit_code` 가 없는 결과는 판정이 아니며, `stage` 수에 하한과 근거가 있고
(`why` 에 “여섯 harness + 리뷰 + 회귀 원장 + red 리허설 = 9”), 자기시험 **43건**이 종류 구분·tier 필터·roster 정합·
red 회계를 매 실행 다시
물어본다. 자기시험이 실제로 즉시 잡은 결함이 둘 있다: ① stage 이름과 카나리아가 아는 harness 이름이 달라 네 층이
“사라진” 것으로 보고됐고(이름을 harness 에 맞춰 통일했다), ② 판정 문장에 `Stage` 를 넘겨 죽었다.

**tier 는 숨김이 아니다.** 회귀 원장의 회차 산출물(`.regression-ledger/`)은 커밋되지 않으므로 깨끗한 체크아웃에서는
그 층을 돌릴 수 없다. `--tier fast`(기본)는 그 층을 **“이 실행이 보지 않은 층”** 으로 적고, `--tier full`(로컬)은 전체
roster 를 요구한다 — 산출물이 없으면 `unrun` 으로 실패하며 왜 못 돌리는지 말한다(초록으로 덮지 않는다).

**게이트 자신도 카나리아가 본다.** 게이트는 stage 수에 하한을 들고 있으므로, 그 하한이 장식인지도 확인해야 한다 —
카나리아 roster 에 `evidence_gate` 를 넣어 눈멀게 한 사본(`observed=0`)이 막히는지 본다(카나리아가 8
harness 를 본다 · marker `canary_harnesses` 8 · `canary_ok` 8). 게이트 자신을 stage 로 넣으면 재귀라, 그 하한을 보는
자리는 카나리아뿐이다. 리뷰는 게이트를 **돌리지 않고 명세만** 읽는다(15번째 검사 `evidence_gate`): stage 의 스크립트
실재 · tier 유효 · fast tier 비어 있지 않음 · 자기시험 존재와 통과 · 하한의 근거 기록. 게이트의 자기시험이 카나리아
roster 와 stage 명단을 대조하므로, 새 harness 를 카나리아에만 넣으면 게이트가 실패한다(예외는 게이트 자신 하나뿐이고,
그 목록이 늘어나도 실패한다). 리뷰가 `--quiet` 로 돌아도 **실패한 검사의 이름과 이유는 stderr 에 남는다** — 한 명령으로
여섯 층을 도는 게이트가 그 출력에서 실패 이유를 읽는다(조용한 실행이 `exit 1` 만 남기면 그 층을 다시 돌려야 한다).

이빨은 게이트 계약 **34건**(`tests/cognitive/test_evidence_gate.py`) + red 리허설 계약 **12건**
(`tests/cognitive/test_red_rehearsal.py`) + 리뷰 계약(증거 게이트 15건 · red 리허설 9건)이다: 없는 스크립트·없는
산출물·제한 시간 초과가 `pass` 가 아닌지, tier 밖 층이 통과로 세어지지 않는지, roster 에서 한 층을 지우면 자기시험이
**그 이름을 짚는지**, **리허설되지도 선언되지도 않은 층이 있으면 걸리는지**, 빨간 층이 보고서와 문제 문장에 이름으로
남는지, CLI 가 실패를 exit code 와 artifact 양쪽으로 남기는지.

### 1.5 회귀 실패 중 둘을 닫았다 — 조용한 스킵과 미등록 실행 경로를 등록으로 없‌앴다

③의 7건 중 둘은 "적혀 있지 않은 상태를 적는" 일이라 이 카드에서 닫았고, 나머지 5건(커밋 이력·패키징·문서 기준선)은
그 소유자의 결정이 필요해 그대로 남겼다.

| 닫은 실패 | 무엇이 문제였나 | 어떻게 닫았나 | 검증 |
|---|---|---|---|
| `test_all_process_execution_paths_are_accounted_for` | `tools/ssak_bundle_store.py` 의 `subprocess.run` 이 ALLOWLIST 미등록 | `FIXED_ARGV` 로 등록 — 신뢰 루트 확인·sha256 일치·platform/arch 일치를 **모두 통과한 뒤에만** `[binary, '--version']` 을 실행하고 argv 가 고정된다(모델 명령 주입 불가). 셸을 쓰지 않는다 | `tests/test_cr14_gate_skip_register.py` + `tests/test_tool_sandbox_coverage.py` 24 passed |
| `test_dashboard_sources_have_no_unregistered_skip_markers` | `dashboard/e2e/ssak-web-integration.spec.ts:191` 의 조건부 `test.skip(!REAL_BUNDLE, …)` 가 등록 없이 남아 있었다(opt-in 설계 자체는 그 카드의 evidence 에 기록되어 있다) | 소스 마커의 회계를 그 마커를 세는 contract 옆에 등록 — 사유·**조건 토큰**·owner·재검토 기한. 등록부 JSON 의 `entries`·`observed_files` 는 **python-tests 게이트의 스킵 집합**을 대조하는 자리라 playwright 소스 마커를 담을 채널이 없기 때문이다(등록부 `scope` 가 그 경계를 말한다) | 13 passed + **이빨 시험**: 등록 안 된 마커·조건 토큰 소실·등록 건수 초과·재검토 기한 경과·낡은 등록을 가짜 입력으로 모두 재현 |

**닫은 뒤 고정 순서 전량 회귀: 5 failed / 7666 passed / 14 skipped / 24 deselected / 20 xfailed (20:13).** 남은 5건은
`test_cr14_fence_movement_detection.py` 2건(후보~HEAD 커밋 이력이 docs 전용이 아님), `test_model_registry.py` 1건
(루트 `config.yaml` 이 번들 기본값과 다름), `test_nx07_doc_consistency.py` 2건(`docs/20_CURRENT_STATUS.md` 기준선)이다.
셋 다 이 카드 밖의 파일·결정이며, 각각 그 소유자의 판단이 필요하다(§6).

세 번째 회귀에서 cognitive 실패는 0이다(두 번째 회귀의 cognitive 3건은 이 작업이 만든 `measured` 마커 미갱신이었고
같은 작업에서 갱신해 닫았다).

순서 의존의 **원인 하나**(import 시점 namespace purge)는 §1.1 ④에서 제거했고, 남은 순서 민감성은 이 카드 범위 밖이다.

| 클러스터 | 건수 | 관찰된 오류 성격 |
|---|---|---|
| `test_browser_tools.py` | 11 | 브라우저 도구가 Playwright 대신 stub으로 fallback("Successfully navigated to …") — 실행 환경 문제 |
| `test_api_server.py` | 10 | 인증 기대 403에 200 응답 — 로컬 인증/서버 설정 |
| `test_ctx01/02/03_*`, `test_cr01/02_*`, `test_cr14_*` | 25 | ctx/cr 게이트·격리·라이선스 메타데이터가 이 환경에서 불충족 |
| `test_cr04_shell_api_boundary.py`, `test_api_forwarder_security.py`, `test_approval_*` | 7 | 자격 증명/경계 설정이 기본값과 다름 |
| `test_diff_engine.py` | 4 | 임시 경로가 `/private/var/...`로 resolve되어 allowlist와 어긋나 DENIED (macOS 경로 별칭) |
| `test_nx07_doc_consistency.py` | 2 | `docs/20_CURRENT_STATUS.md`·CR-14 대장의 **기준선 자체가 이미 위반**(이 작업이 건드린 문서가 아님) |
| 그 밖의 단일 항목 17개 | 17 | `test_tool_sandbox_coverage`(기존 기록된 `test_all_process_execution_paths_are_accounted_for` 포함) 등 개별 환경·기존 이슈 |

단독 재실행으로 성격을 확인했다: `test_browser_tools.py`·`test_diff_engine.py`·`test_nx07_doc_consistency.py`를 함께 단독
실행하면 **63 passed / 2 failed**로 nx07만 남는다 — 즉 browser·diff 실패는 suite 순서·동시 실행에서 오는 artifact이고,
nx07만 기존 문서 기준선 문제다. 나머지 파일은 오류 signature로 분류했으며 개별 재실행 전량 확인은 하지 않았다(한계).

회귀는 "지금 이 source에서 기존 시험이 깨지지 않았다"는 사실까지만 말한다. 실제 모델을 부르는 대화 QA, resume/cancel
실사용 QA, destructive migration, live pilot은 여기에 포함되지 않는다(§5).

## 2. 헌법 24원칙 매핑

원칙 번호와 제목은 `docs/ssak-ai-core/SSAK_AI_CONSTITUTION.md`의 원문을 그대로 사용한다. "증거/시험/module" 열의
문자열은 실제 파일명이며, 검사기가 존재 여부를 확인한다.

| 원칙 | 카드 | 증거 | 시험 | module | 상태 | 한계 |
|---|---|---|---|---|---|---|
| **P1** Brain Replaceability | T01a, T02, T04 | T01a_typed_model.md, T02_canonical_store.md, T03_T04_context_brain.md | test_models.py, test_brain.py, test_store.py | models.py, brain.py, store.py | partial | 교체성 guard(cognitive는 도구·UI import 금지)와 canonical record 유지는 시험으로 고정됐다. 실제 A/B provider 교체는 실 provider가 필요해 미실행. |
| **P2** Brain-Centered Cognition | T04, T05, T06 | T03_T04_context_brain.md, T05_governance.md, T06_commit.md | test_brain.py, test_governance.py, test_readiness.py | brain.py, governance.py, readiness.py | covered | Body는 판단의 정답을 심사하지 않는다(provider LLM 호출 0 spy). 실제 prompt 수준 확인은 실모델 QA로 이월. |
| **P3** Experienced Cognitive Orchestrator | T08, T10, T13 | T08_T09_episode.md, T10_learning.md, T13_growth.md | test_episode.py, test_learning.py, test_growth.py | runtime.py, learning.py, growth.py | partial | 운영 학습 target이 CONTEXT_DEPTH 하나이고, 사용자 대화 경로는 아직 core를 부르지 않는다(P11). |
| **P4** Responsibility Boundary | T04, T05, T06 | T05_governance.md, T06_commit.md, T03_T04_context_brain.md | test_governance.py, test_readiness.py, test_brain.py | governance.py, readiness.py, decisions.py | covered | 의미 통합 주체는 Primary(또는 human-assisted)이며 Body 다수결·semantic merge는 시험으로 금지. |
| **P5** Human Authority | T01b, T05, T11 | T01b_protection.md, T05_governance.md, T11_surface.md | test_protection.py, test_governance.py, test_surface.py, test_enum_identity.py | authority.py, protected_targets.py, ../cognitive_surface.py | partial | ACTIVE 전환은 사람 승인+dispatch port+canonical project id가 모두 필요하고 fail-closed. 승인 발급 주체·보호 hook 실연결은 T01b 이월. |
| **P6** Current-State Primacy | T03, T10 | T03_T04_context_brain.md, T10_learning.md | test_context.py, test_learning.py | context.py, learning.py | covered | 과거 confidence가 높아도 현재 applicability가 MISMATCH면 advisory로만 제시된다. |
| **P7** Historical Preservation | T02, T06, T09, T12 | T02_canonical_store.md, T06_commit.md, T08_T09_episode.md, T12_migration.md | test_readiness.py, test_episode.py, test_migration.py | decisions.py, experience.py, migration.py | covered | 재해석은 새 version, reopen은 append. migration dry-run은 source를 `mode=ro`로만 연다. |
| **P8** Experience Ownership | T09 | T08_T09_episode.md | test_episode.py | experience.py, models.py | covered | Brain Output 자체는 Experience가 아니며, Context·판단·거버넌스·행동·결과가 연결된 episode만 후보가 된다. |
| **P9** Experience Must Change Future Behavior | T10, T13 | T10_learning.md, T13_growth.md, T13_live_pilot.md | test_learning.py, test_growth.py, test_live_pilot.py | learning.py, growth.py, live_pilot.py | covered | 후보→검증→승격→다음 task의 실제 선택→outcome이 trace로 연결된다. 성능 수치는 fixture 한정, live는 NOT_RUN. |
| **P10** Simple to Start, Designed to Mature | T08, T13 | T08_T09_episode.md, T13_growth.md | test_readiness.py, test_growth.py | runtime.py, growth.py | covered | 초기 규칙 경로와 성장 경로가 둘 다 있으며 mature arm은 FINAL split에서 실제 선택을 바꾼다(소표본). |
| **P11** Earned Complexity | T00a, T00b, T10, T13, T14 | T00_baseline.md, T10_learning.md, T13_growth.md, T14_namespace_isolation.md, T14_regression_ledger.md, docs/ssak-ai-core/ARCHITECTURE_REVIEW.md | test_learning.py, test_growth.py, test_architecture_review.py, test_module_namespace_isolation.py, test_regression_ledger.py | learning.py, growth.py | partial | baseline·metric·split을 실행 전에 등록하고 ablation 6종을 전부 MEASURED로 만들었다. 회귀 수도 서술이 아니라 원장(scope 별 두 seed)에서만 인용한다. live 성능 증거가 없어 learned policy는 Core로 승격하지 않았다. |
| **P12** Intentional Cognitive Expansion | T03, T08 | T03_T04_context_brain.md, T08_T09_episode.md | test_context.py, test_readiness.py | context.py, readiness.py | covered | 확장은 goal/evidence linked이고 bounded이며, 무관한 과거 기록은 여유 budget이 있어도 기본 Context로 들어가지 않는다. |
| **P13** Stop Rule | T08 | T08_T09_episode.md | test_readiness.py, test_episode.py | runtime.py, readiness.py | covered | material cognitive delta가 없으면 유한 종료하고 stop을 READY로 승격하지 않는다. |
| **P14** COMMIT Boundary | T06 | T06_commit.md | test_readiness.py | readiness.py, decisions.py | covered | 9 readiness checks만 보고 semantic judge를 호출하지 않는다. 판정 입력에 결론 문구는 없다. |
| **P15** Decision Closure | T06 | T06_commit.md | test_readiness.py, test_store.py | decisions.py, store.py | covered | material trigger로만 최소 범위 reopen, 원래 DecisionTrace 불변, 표현 변경만으로 반복 reopen 없음. |
| **P16** Risk Philosophy | T05, T13 | T05_governance.md, T13_growth.md | test_governance.py, test_growth.py | governance.py, growth.py | covered | RESHAPE는 grant 안에서 scope 축소·checkpoint·verification으로 위험을 줄이고, 고위험이라는 이유만으로 human escalation하지 않는다. |
| **P17** Unknown is Valid | T05, T06 | T05_governance.md, T06_commit.md | test_governance.py, test_readiness.py | governance.py, readiness.py | covered | ACCEPTABLE Unknown 하나로 NOT_READY가 되지 않고 BLOCKING만 관련 action을 막는다. N_A에는 사유가 필요하다. |
| **P18** Knowledge is Evidence, not Authority | T03, T10 | T03_T04_context_brain.md, T10_learning.md | test_context.py, test_learning.py | context.py, learning.py | covered | confidence·applicability·assurance를 분리하고 learned policy는 헌법·보호 권한을 바꾸지 못한다. |
| **P19** Context Philosophy | T03 | T03_T04_context_brain.md | test_context.py | context.py, references.py | partial | 재구성·최소충분·넓게 검색/좁게 주입이 시험으로 고정됐다. 실제 provider context window 확인은 P11 이월. |
| **P20** Brain Steering | T04 | T03_T04_context_brain.md | test_brain.py | brain.py | partial | Body는 질문·범위를 조정하고 결론을 암시하지 않는다. 실제 모델 응답에서의 편향 부재는 실 provider QA 이월. |
| **P21** Targeted Re-reasoning | T04, T08, T13 | T03_T04_context_brain.md, T08_T09_episode.md, T13_growth.md | test_brain.py, test_readiness.py, test_growth.py | brain.py, runtime.py, growth.py | covered | 약한 reasoning만 재사고하고 기존 판단은 append 계보로 남는다. ablation에서 이 mechanism을 끄면 safety violation이 재현된다. |
| **P22** Cognitive Resource Philosophy | T07, T13 | T07_actions.md, T13_growth.md | test_actions.py, test_growth.py | actions.py, growth.py | partial | tool·retry·verification 자원은 측정하지만 latency는 0으로 보고되어(미측정) 실측이 없다. CPU/GPU/network 배분은 v1 core 범위 밖. |
| **P23** Runtime Maturity | T13 | T13_growth.md | test_growth.py | growth.py | partial | FINAL 18 task에서 retry 39→15, success 비열등을 관찰했다. 소표본이고 live pilot은 NOT_RUN. |
| **P24** Ultimate Relationship | T05, T11 | T05_governance.md, T11_surface.md | test_governance.py, test_surface.py | authority.py, ../cognitive_surface.py | partial | human-only boundary는 reshape로 우회 불가이고 ACTIVE는 사람 승인을 요구한다. Human Partner 표면(상태·decision trace)은 P11 잔여. |

집계: covered 15 · partial 9 · gap 0.

## 3. 원문 §63 최종 Architecture Review 질문

각 질문은 `MASTER_PROMPT_V2_SOURCE.md` §63의 원문이며, 답변은 `yes` / `yes_with_limits` / `no` 셋 중 하나다.

### **Q-identity** — Identity
> Primary Brain을 교체해도 SSAK-AI인가?

**답: yes_with_limits.** State/Memory/Experience/Decision/Knowledge/Governance/Authority는 canonical store에 남고,
cognitive 패키지가 도구·UI 계층을 import하지 못하게 architecture guard가 막는다(test_models.py). Brain은 교체 대상이며
Body record가 정체성을 유지한다.
한계: 실제 A/B provider 교체 실측은 실 provider가 필요해 미실행이다.

### **Q-continuity** — Continuity
> Brain이 없어도 SSAK-AI의 경험과 Decision History가 유지되는가?

**답: yes_with_limits.** store가 canonical record로 유지되고 `rebuild_index()`·`verify_digests()`로 재구성된다.
migration dry-run은 source를 읽기 전용으로만 열어 보존을 확인한다(test_migration.py).
한계: 실사용 vault DB·vector index 대상 dry-run은 별도 실행 항목이다.

### **Q-brain_boundary** — Brain Boundary
> Body가 두 번째 Semantic Brain이 되지는 않았는가?

**답: yes.** COMMIT은 readiness만 검사하고 semantic judge를 호출하지 않으며(LLM 호출 0 spy), Governance는 요청의
구조·권한·위험만 판정한다. Body 기계 집계와 의미 해석 주체가 분리되어 있다(test_learning.py).
한계: 의미 해석의 author는 Primary 또는 human-assisted 경로뿐이라는 제약이 계약으로만 존재한다.

### **Q-context** — Context
> Context를 재구성하는가, 단순 누적하는가?

**답: yes.** ContextBuilder가 매 episode 재구성하고, 무관한 과거 기록은 여유 budget이 있어도 기본 Context로
주입되지 않는다. 확장은 handle 단위이며 권한·digest·만료를 재확인한다(test_context.py).
한계: 실제 provider context window에서의 축소·불완전 처리 확인은 P11 이월.

### **Q-experience** — Experience
> Brain Judgment와 SSAK-AI Experience가 분리되어 있는가?

**답: yes.** Brain Output은 Experience가 아니며, OPERATIONAL_ONLY/EXPERIENCE/DEFERRED 선별과 세 평가
(Outcome/Decision/Execution)가 분리된다. 선별 이유·근거·producer·정책 version이 남고 어느 경우도 원본을 지우지 않는다.
한계: PENDING/UNKNOWN을 성공으로 학습하지 않고 후속 관찰은 supplement로 append한다(test_episode.py).

### **Q-learning** — Learning
> Experience가 실제 Future Behavior를 바꿀 수 있는가?

**답: yes_with_limits.** 후보→ValidationReport→PolicyActivation→다음 task의 실제 선택→outcome이 BehaviorChangeTrace로
연결되고, FINAL split에서 retry 39→15·success 비열등을 관찰했다.
한계: deterministic fixture 결과이며 live pilot은 NOT_RUN(exit 2)이다. 18 task 소표본이라 일반 성능 보장이 아니다.

### **Q-governance** — Governance
> COMMIT은 readiness만 확인하는가?

**답: yes.** 9 checks가 PASS/FAIL/UNKNOWN/N_A와 reference를 가지며, provider spy로 semantic LLM 호출 0을 확인했다.
의미적 결론 문구만 바꾼 fixture에서도 판정이 흔들리지 않는다(test_readiness.py).
한계: guard가 실제 executor에서 강제되는지는 action 계층(T07) 증거로 확인한다.

### **Q-risk** — Risk
> 위험을 무조건 회피하지 않고 reshape 가능한가?

**답: yes.** RESHAPE는 기존 grant 안에서 isolated scope·checkpoint·verification으로 위험을 줄이고, 고위험이라는
이유만으로 자동 human escalation하지 않는다(test_governance.py).
한계: human-only action은 reshape로 우회할 수 없다(보호 권한 시험).

### **Q-unknown** — Unknown
> UNKNOWN 상태를 유지할 수 있는가?

**답: yes.** ACCEPTABLE/MATERIAL/BLOCKING Unknown을 구분하고 ACCEPTABLE Unknown 하나로 NOT_READY가 되지 않는다.
BLOCKING은 관련 action만 차단한다.
한계: 원인 UNKNOWN인 실패도 남은 unknown을 명시하고 기록을 닫을 수 있다는 것까지가 계약이다.

### **Q-history** — History
> 과거 Decision과 Experience를 덮어쓰지 않는가?

**답: yes.** reopen은 최소 범위 append이고 원래 DecisionTrace는 불변이다. 재해석·교정은 새 version record이며 기존 core
digest가 동일함을 시험으로 고정했다.
한계: migration은 source를 `mode=ro`로만 열고 destructive in-place 변환은 실행하지 않는다(사람 결정 이월).

### **Q-human** — Human
> Human Partner가 최종 Constitutional Authority인가?

**답: yes_with_limits.** 헌법 변경은 CONSTITUTION_CHANGE_PROPOSAL로만 제안 가능하고, ACTIVE 전환은 사람 승인+dispatch
port+canonical project id가 모두 있어야 한다. OFF가 기본이며 fail-closed다(test_surface.py).
한계: 승인 발급 주체·보호 hook 실연결(T01b)과 Human Partner 표면(P11)은 미완이다.

### **Q-complexity** — Complexity
> Evidence 없이 복잡성이 증가하지 않았는가?

**답: yes_with_limits.** 성장 mechanism 6종을 한 번에 하나씩 ablation했고 전부 MEASURED이며, 쓰이지 않은 mechanism은
NOT_RUN으로 no-op 비교를 증거에서 제외한다.
한계: live 성능 증거가 없어 learned policy를 Core로 승격하지 않았다. 현재 위치는 experimental/conditional 단계다.

## 4. 원문 §52 Constitution Drift 질문

"YES가 있다면 Architecture Review가 필요하다"는 규칙에 따라 답한다. 현재 triggered는 0건이다.

| 질문 | YES? | 근거 | 비고 |
|---|---|---|---|
| **D-body_semantic_brain** Does this make Body a semantic Brain? | NO | COMMIT semantic judge 0(provider 호출 spy), Governance의 advisory_notes 비사용 시험, 기계 집계와 의미 해석 분리 | 의미 해석 author는 Primary/human-assisted만 |
| **D-brain_replaceability** Does this reduce Brain replaceability? | NO | cognitive 패키지의 도구·UI import 금지 guard, fixture 도구·executor는 growth_fixture_tools.py adapter로 분리 | guard가 깨지면 시험 2건이 즉시 실패 |
| **D-history_dependence** Does this make memory dependent on conversation history? | NO | Context는 재구성되고 L1/L2/L3 handle 참조로만 주입된다 | 무관 기록 미유입 시험(test_context.py) |
| **D-experience_dictates** Does this allow experience to dictate conclusions? | NO | Experience는 advisory이고 applicability MISMATCH면 자동 적용되지 않는다 | 승격은 별도 validation report 필요(T10-A) |
| **D-human_authority_bypass** Does this bypass Human Constitutional Authority? | NO | ACTIVE 사람 승인 필수, human-only boundary는 reshape 우회 불가, 헌법 변경은 제안만 가능 | 승인 발급·검증 실표면은 T01b 이월 |
| **D-unbounded_loops** Does this create unbounded cognitive loops? | NO | material delta stop, expansion budget 소진 시 BLOCKED/DEFER, 유한 SSE(limit 후 done), 성장 runner는 고정 task 수 | stop은 READY로 승격되지 않는다(T08-D) |
| **D-commit_semantic** Does this make COMMIT re-evaluate semantic correctness? | NO | readiness 입력만 사용, 결론 문구를 바꾼 fixture에서도 판정 동일 | 판정 입력은 type·args·권한·risk·unknown뿐 |
| **D-complexity_without_value** Does this add complexity without measured value? | NO | 6 ablation 전부 MEASURED, 미사용 mechanism은 NOT_RUN 제외, 개선이 없으면 그대로 기록 | live 성능 증거가 없어 Core 승격 보류 |
| **D-prevents_learning** Does this prevent future learning? | NO | 후보→검증→활성화→실제 선택 변화 사슬이 FINAL split에서 동작, rollback/CAS 계약 존재 | 운영 target 하나라는 범위 제한은 남음(T10-E) |
| **D-erases_history** Does this erase cognitive history? | NO | append-only reopen, 재해석 versioning, migration source read-only, rollback rehearsal은 dry-run 출력 보존 | destructive in-place 변환은 미실행 |

## 5. 결론 — 남은 미완과 이월 조건

**이 문서는 PASS 선언이 아니다.** 헌법 원칙 기준으로 근거가 연결된 범위와, 실 환경·사람 결정이 필요한 범위를 구분해
기록한 것이다. gap은 0이며, partial 9건이 남은 미완의 실체다.

| 미완 인수 | 원칙 | 남은 조건 | owner |
|---|---|---|---|
| T00a 현재 기준선 | P11 | 각 entrypoint→runtime→gate의 파일·symbol 근거를 현재 source에서 재확인 | integration |
| T00b 초기 benchmark | P11 | 등록된 metric/split/manifest를 실제 실행에 사용하고 Fresh baseline을 보존 | integration |
| T01a 모델·계보 | P1 | 현재 schema·선별 기록 계약 대조 | cognitive-core |
| T01b 헌법·보호 권한 | P5 | 신뢰 가능한 승인 발급·검증 주체와 실제 우회 경로 차단, hook 연결 | cognitive-core + human |
| T02 불변 저장·복구 | P1, P7 | 실제 Vault writer와의 동시 write·crash 복구 | storage |
| T03 Context | P19 | 실제 provider context window에서 축소·불완전 처리 확인 | cognitive-core + human |
| T04 Brain 교체 | P1, P20 | A/B provider 교체와 state 연속성 실측 | cognitive-core + human |
| T11 사용자 표면 | P3, P24 | 대화 스트림·background 실행 경로 배선, 실모델 대화 QA, resume/cancel QA, ACTIVE 실도구 검증 | integration + human |
| T14 회귀·최종 리뷰 | P11 | 이 문서의 검사 PASS(회귀 원장 · 인용 추적 · digest 측정 포함) + 실표면 QA. 실표면 QA가 남아 체크박스는 미완으로 유지 | human (Architecture Review) |
| T01a~T13 증거의 실환경 재확인 | P1, P11 | digest 재확인은 **계약 시험 수준에서 끝냈다**(§1.4 — 21건, `digest_reverification.json`). 남은 것은 실모델·실 vault·사람 승인 표면에서 그 증거가 서는지이며, 각 문서의 `limitations` 에 그대로 있다 | 각 카드 레인 + human |
| Live pilot | P9, P23 | 실제 provider 예산 승인 후 `run_kind=LIVE_PILOT` 등록 spec으로 실행 | human |

판단 근거를 명시하지 않은 채 복잡도를 늘린 항목은 없다. 반대로, live 성능 증거가 없다는 이유로 learned policy와
Secondary Brain 계열은 Core로 승격하지 않았다(SELF_IMPROVEMENT_POLICY §56의 CORE/CONDITIONAL/ADVANCED 구분 유지).

## 6. 한계와 재현성

- 이 문서의 회귀는 **이 체크아웃의 고정 `.venv`** 에서 실행한 결과다. CI의 비-editable `uv sync` 환경과 릴리스
  build job은 별도이며, wheel/sdist build는 실행하지 않았다(NOT_RUN).
- 전체 회귀 실패는 오류 signature와 선택 재실행(3개 파일)으로 분류했다. 39개 실패 파일 전량을 단독 재실행해
  "기존 실패"와 "순서 artifact"를 확정하지는 않았다 — 그 비용은 다음 회차로 남긴다.
- **회귀 수치는 원장에서만 인용한다(§1.2).** 과거 네 측정이 94 / 10 / 7 / 5 failed 로 갈렸지만, 그 비교는 트리·수집 오염·실행 선택이 함께 달랐던 상태였다 — 두 seed 를 고정한 원장에서는 **결정적 11 · variant 민감 0** 이다(그중 3 scope 는 수집 순서를 뒤집어도 같았다). 그중
  **원인 하나**(import 시점 namespace purge)는 §1.1 ④에서 제거하고 감사로 고정했지만, 남은 차이는 여전히 순서·
  동시 실행 artifact 이므로 "이전 실패와 동일"을 고정 baseline 으로 주장하지 않고 **가장 보수적인 값(④의 5건)** 을 기록한다.
  원장이 남긴 11건은 5개 파일이다 — cr14 fence 2 · nx07 2 · `config.yaml` 1 · ws01 5 · trn02 1이며 전부 소유자(레인)가 지정돼 있다. 이 카드가 결정할 항목은 없다.
- **원장이 재는 순서는 scope 안의 순서다.** 순서를 뒤집은 variant 는 9 scope 중 3개에만 있다(수집이 섞이는 범위가 곱해져 502개를 한 호출에 넣을 수 없어서다). **scope 사이의 순서**(예: `tests/cognitive`가 다른 구간보다 먼저 import 되는 경우)는 이 원장의 범위 밖이며, §1.1 ④ 의 오염 부류는 구간 안에서 재현되지 않았다.
- **중단된 회차는 판정에서 제외하고, 원인은 아직 특정하지 못했다.** `flat-081-220`·seed 202 에서 같은 조건으로 5회 더 돌려 **1회 재현**했다(누적 6회 중 2회 · 기록 1057/1860). 죽는 자리는 **pytest 자신의 terminal writer flush**(`terminal.py:699 → 532 → terminalwriter.py:187 self._file.flush()`)이고 그 `_file` 의 fd 는 **1** 이다 — 즉 시험이 pytest 의 출력 fd 를 닫으면 *그 시험이 아니라 그 뒤의 보고*가 죽는다. 시험마다 fd 유효성을 확인하는 probe 와 `os.close`/`dup2` 를 가로채는 tracer 로 쫓았으나 Python 이 보이는 경로에서는 잡히지 않았다(중단이 안 난 회차의 `dup2→1` 은 전부 pytest capture 의 suspend/resume 이었다). 남는 후보는 C 수준 close 경로나 fd 번호 재사용이며, macOS 에서는 `dtrace` 가 root 를 요구한다. 그래서 중단은 **완충**으로 처리한다 — 회차가 중단되면 같은 조건으로 한 번 자동 재실행하고(`--retry-aborted`) 횟수·시도 로그를 원장에 남긴다(§1.2 · `evidence/T14_regression_ledger.md` §5·§5a). 최종 원장에는 중단된 회차가 없다(`aborted_scopes: []`).
- 고정 순서(`-p no:randomly`) 전량 회귀는 **한 번 중단(exit 120)** 되었다 — `engine/rag_indexer.py` 가
  `OSError: [Errno 9] Bad file descriptor` 를 받고 내부 오류로 끝났다. 원인을 추적하려고 plugin 으로 열린 fd 를
  시험마다 관찰했다(수집 종료 시점 기준선과 `os.fstat` 대조 · macOS `/dev/fd` 목록은 닫힌 slot 을 포함해 오탐이 난다).
  탐지된 손실은 **1건뿐**이었고 그 정체는 `/dev/null`(ino 336) 의 중복 fd — pytest capture 기계가 쓰는 자원이다.
  **제품 code 가 잃은 fd 는 없었고**, 같은 고정 순서 실행을 두 번 더 돌리자 정상 종료했다(각 7 failed). 즉 그 중단은
  **재현되지 않은 회차성 artifact** 이며, 현재 고정 순서 회귀는 돈다 — 이 bullet 은 그 관찰의 기록이다.
- 이 체크아웃은 **공유 체크아웃**이며 다른 작업자의 변경과 실행 중인 suite가 있었다. 이 머신에는 이틀 전 시작해
  77%에서 멈춘 다른 pytest 프로세스도 남아 있었고(CPU 0% · RSS 약 5GB), 회귀 수치는 그런 조건을 배제하지 못한다.
- §2의 "실제 관찰"은 대부분 deterministic fixture와 module 시험 범위다. 실 모델·실 vault·실 사용자 표면은 partial로 남겼다.
- 매핑은 사람이 작성한 것이고, 검사기는 **존재·일치**만 본다. 인용된 시험이 그 원칙을 실제로 증명하는지는 사람
  리뷰(§3·§4의 근거 서술)의 몫이다.
- 매핑을 바꾸면 이 문서의 `**P..**`·`**Q-..**`·`**D-..**` 마커와 artifact 목록, 그리고 시험 수 marker가 함께 바뀌어야
  하며, 그렇지 않으면 `tests/cognitive/test_architecture_review.py`가 실패한다.
