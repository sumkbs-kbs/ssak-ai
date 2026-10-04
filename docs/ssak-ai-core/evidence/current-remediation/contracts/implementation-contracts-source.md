# 카드 사이의 공통 구현 계약

이 문서는 Luna가 카드마다 서로 다른 인터페이스를 발명하지 않도록 경계의 의미를 고정한다. 아래 함수 이름은 기존 소스에서 확인된 이름만 코드 형식으로 적었다. 새로운 API의 철자·배치는 담당자가 기존 패턴에 맞추되 **입출력 의미·권위·실패 동작은 이 계약을 따른다**. 공개 API나 record schema를 변경하면 additive/versioned migration을 기록하고 기존 records의 읽기를 검증한다.

## 계약 소유권과 완료 게이트

아래 경로는 향후 repository에 구현자가 남길 산출물 경로다. 이번 출력 폴더에서 해당 계약의 의미는 이 문서 C01–C09에 고정한다. 신규 method/schema의 정확한 타입과 placement는 producer 카드의 **첫 소작업**으로 문서화한다. strong reviewer가 기존 types·caller·failure model과 대조해 승인한 뒤 해당 seam을 구현한다. 이것은 개발 검토 절차이며 일반 구현을 위한 Human 승인 요구가 아니다.

| 계약 | producer / consumer | repository 산출물 | producer 인수 | consumer 통합 인수 |
|---|---|---|---|---|
| C01 Context/예산 | R05/R06 → R07/R14/R15 | `docs/ssak-ai-core/evidence/current-remediation/contracts/context-v1.md` | required inclusion, revision, serialized budget의 typed examples와 failing/success contract tests. R05-E/V, R06-E/V | R14-A5 adapter call0, R15-A5 실제 boot call0/action0 |
| C02 feedback | R07 → R14/R15 | `…/contracts/feedback-v1.md` | request/signature/feedback/round 전이, 성공·DENY·stop tests. R07-A* | R14 envelope roundtrip, R15-A1 실제 판단→action |
| C03 freshness | R08 → R09/R13/R15 | `…/contracts/freshness-v1.md` | lookup 입력/오류/current binding·pin invalidation·race ordering. R08-A* | R09-A1 실제 durable heads, R13 pin/rollback, R15-A1/A2 새 revision/revoke와 effect0 |
| C04 transaction | R03 → R09/R11/R21 | `…/contracts/transaction-v1.md` | exact/different digest replay, conflict/crash tests. R03-A* | R09 writes/R11 completion/R21 replay의 동일 ID 계약 |
| C05 lifecycle | R09 → R10/R11/R16 | `…/contracts/lifecycle-v1.md` | canonical ID/reference, pending 조회, receipt revision schema와 serialized fixtures. R09-A* | R10-A1/A2 restart/idempotent observation, R11-A6 selected core dedupe, R16-A1/A2 durable status |
| C06 평가/경험 | R11/R12 → R13/R18 | `…/contracts/experience-v1.md` | operational/selection/core/assessment의 출처·UNKNOWN tests. R11/R12-A* | R13 actual policy input, R18 TRAIN experience ledger |
| C07 policy/trace | R13 → R18/R19 | `…/contracts/policy-v1.md` | actual selector IDs, scope, rollback/pin tests. R13-A* | R18-A2/A3 학습 분리, R19 독립 재계산 |
| C08 trial ledger | R17 → R18/R19 | `…/contracts/trial-ledger-v1.md` | manifest/result schema, invalid 입력 provider0, partial ledger fixtures. R17-A* | R18 real adapter, R19 complete raw trial ledger |
| C09 composition/status | R15/R16 → R22 | `…/contracts/composition-v1.md` | route별 executor owner와 actual/config/static fields. R15/R16-A* | R22 actual supported route 통합과 rollback 검증 |

표의 `…/contracts/`는 첫 행과 같은 `docs/ssak-ai-core/evidence/current-remediation/contracts/`이다. 각 산출물에는 contract version·source/spec hash·정확한 함수/필드 타입·권위 있는 조회 원천·오류 코드·직렬화 예제·producer/consumer test node·reviewer를 남긴다. 소비자는 계약 version/hash를 pin하고 breaking change가 있으면 조용히 적응하지 말고 producer/consumer 계약을 함께 갱신한다.

producer가 완료되어도 consumer 통합이 미실행이면 producer의 구현 계약만 PASS다. E/V에 `producer_contract=PASS, consumer_integration=NOT_RUN(owner=Rxx)`를 명시한다. R22는 표의 consumer 열까지 확인해야 전체 인수를 닫을 수 있다. 이 방식으로 선행 카드가 아직 없는 후행 기능을 구현했다고 주장하지 않는다.

**R08/R09의 구체적 경계:** R08은 기존 CanonicalStore에 저장한 실제 fixture decision/state/policy heads를 읽는 resolver adapter와 atomic admission 경계를 만든다. 아직 없는 head는 unavailable/NOT_READY이며 client intent로 대체하지 않는다. R09는 실제 episode writer가 동일 head/reference contract를 지속하도록 연결한다. R09-E/V에서 R08 resolver가 그 실제 기록을 읽는 통합 test를 추가하고, R15에서 boot 구성과 동시 revision 변경을 재검증한다. R08이 R09의 episode persistence를 미리 설계·구현할 필요는 없다.

**R14의 구체적 경계:** R14는 pre-existing committed fixture records로 provider-independent adapter 계약을 닫을 수 있다. R11이 생성한 실제 경험과 재시작·Brain 교체 연속성은 R11/R14를 모두 선행으로 갖는 R15-A6에서 실행한다. R14 contract PASS를 live continuity PASS로 옮기지 않는다.

## C01 — 최소 Context

소유: R05/R06. 소비: R07/R14/R15.

기존 `ContextPackagePayload`는 goal_id, state_revision, policy_version, L0–L3, handles, budget, exclusions, integrity, missing_ids를 가진다. 같은 내용을 별도 Context 클래스에 중복 원본으로 만들지 않는다.

요청은 project/goal/current snapshot revision, 허용 policy version, 필수 evidence reference, provider/request 예산을 포함한다. “필수”는 caller의 명시적 현재 task 계약·hard constraints·material unknown에 근거한다. Body가 원하는 conclusion을 필수 사실로 선택할 수 없다.

COMPLETE는 필수 record가 존재한다는 뜻을 넘어 **Brain에게 전달할 package에 실제 필요한 내용이 있다**는 뜻이다. truncation/limit/budget으로 필수 ID를 제외했으면 missing_ids와 exclusion reason에 넣고 INCOMPLETE로 만든다. handles만 있다고 COMPLETE로 올리지 않는다. 기존 payload validator가 INCOMPLETE에 missing_ids를 요구하므로 budget 부족도 해당 누락 ID와 함께 표현한다.

현재 revision이 바뀌었으면 재구성하거나 명시적 snapshot 모드로 고정한다. COMPLETE의 revision을 소비자가 바꾸지 않는다. 전송 예산은 최소 capability/request limit에서 system/schema/repair 여유를 뺀 값이며 metadata와 handles를 포함한 실제 serialization을 측정한다. exact tokenizer가 없으면 보수적 추정의 방법·오차 한계를 기록한다.

## C02 — 요청·feedback·targeted rethink

소유: R07. 소비: R14/R15.

한 episode에는 현재 judgment/plan, 처리할 request batch, typed feedback, 사용한 budget이 있다. 모든 request는 governance disposition과 실행 여부/결과 reference를 받는다. 요청이 성공해 새 evidence가 생겼으면 그것을 Primary에게 전달한다. 실패만 rethink하는 구조는 금지한다.

Primary의 후속 출력은 다음 중 하나다: 업데이트된 judgment/plan, bounded 추가 request, no material delta/stop, unresolved/defer. Body는 새 출력의 의미를 대신 만들지 않는다. 다음 request는 초기 request와 동일 gate/예산을 거친다. 최종 COMMIT 대상은 가장 최근 통합 판단이다.

반복 identity는 request type, canonical target, normalized args, purpose, 관련 evidence revision이다. JSON key 순서 같은 비의미적 차이로 signature를 우회하지 못하게 한다. round 수와 총 요청 수는 별도 제한하고 tool/model 비용도 누적한다. 같은 evidence에서 반복되는 동일 요청은 더 실행하지 않고 이유를 feedback한다. 새 evidence가 있어도 총 예산을 넘지 못한다.

## C03 — 현재 revision과 policy pin

소유: R08. 소비: R09/R13/R15.

기존 `FreshnessBinding`의 `(decision_revision, action_digest, state_revision, authority_revision, policy_version)`을 그대로 기준으로 쓴다. authoritative lookup 입력은 authenticated project, canonical decision/action identity다. 출력은 durable 현재 head에서 읽은 binding 또는 missing/stale/unavailable 오류다. client가 준 “current revision”은 조회 결과가 아니다.

reasoning 시작에 pin한 policy와 Context snapshot은 그 판단의 역사적 근거로 보존한다. action 직전 현재 binding이 달라지면 **기존 판단 기록을 수정하지 않고 NOT_READY/reprepare**한다. policy가 새로 승격됐다는 이유로 진행 중 판단의 pin만 몰래 바꿀 수 없다. 반대로 오래된 pin이라는 이유로 현재 binding 검사를 생략할 수도 없다. 새로 준비한 decision/action은 새 ID 또는 명시적 revision과 readiness를 갖는다.

실행 직전 check와 effect admission은 동시 reopen/revoke에 대한 정해진 ordering을 가져야 한다. permit의 의미는 “그 ordering 시점에 해당 digest와 revision에 한정된 실행 권한”이다. 외부 effect 중간에 이미 발생한 행동을 revoke로 되돌렸다고 주장하지 않는다. 취소·rollback·결과 관찰로 처리한다.

## C04 — transaction identity

소유: R03. 소비: R09/R11/R21.

transaction ID는 정규화 record content 목록과 episode scope에 귀속된다. 동일 ID/동일 digest는 idempotent replay, 동일 ID/다른 digest는 명시적 conflict다. stage의 비교·생성과 commit의 expected digest 확인이 lock/atomicity 경계 안에 있어야 한다. ID만 안다고 다른 호출자의 pending content를 commit하지 못한다.

pending·partially written record는 committed visibility가 없으면 Context/learning/index에 노출하지 않는다. file 작성과 Git commit 실패를 별도 상태로 보존하여 재시작 때 같은 transaction을 복구한다. 파일이나 기록을 지워 “복구 성공”으로 만들지 않는다.

## C05 — durable action과 recovery

소유: R09/R10. 소비: R11/R15/R16.

기존 `ActionRun`은 intent/status/receipt/refusal/reconciliation_required/cancellation_requested/records를 가진다. 이 메모리 객체 자체를 durable truth로 취급하지 않는다. canonical record IDs로 다시 구성할 수 있게 연결을 남긴다.

| 논리 지점 | durable 사실 | crash 뒤 허용 동작 |
|---|---|---|
| 준비 완료 | decision/context/judgment/governance/readiness binding | freshness 재검사 후 새 admission |
| effect admission | 고유 action identity/claim + committed intent | 아직 effect가 없다는 증거 없이 자동 재실행 금지 |
| effect 후 receipt 전 | 외부 효과가 있을 수 있음 | UNKNOWN/pending을 조회·관찰·reconcile |
| receipt 저장 후 | receipt의 안정된 canonical ID와 action link | observe를 이어가되 redispatch하지 않음 |
| outcome 관측 | observation provenance/time + 평가/선택 | 선택된 Experience를 idempotent append |

이 표는 기존 enum을 무조건 교체하라는 지시가 아니다. 기존 status로 표현하고 부족할 때만 versioned 필드를 추가한다. claimed와 external effect observed를 혼동하지 않는다.

reconciliation 입력은 authenticated principal/project, 기존 action ID, observation ID 또는 새 관측 payload+출처, expected current revision이다. 성공은 append된 record IDs와 새 projection revision을 돌려준다. unknown action/project mismatch/revoked authority/stale revision/malformed observation은 effect 없이 명시적으로 거절한다. 이미 같은 observation digest가 들어왔으면 같은 결과를 idempotent 반환한다. 늦게 온 이전 관측은 history에 남길 수 있으나 최신 상태를 자동 downgrade하지 않는다.

새로운 retry는 원래 action을 지우는 것이 아니다. 외부 idempotency 또는 effect 부재를 확인한 근거와 현재 권한 아래 별도 attempt를 원래 action에 연결한다. timeout만으로 claim을 해제하지 않는다.

## C06 — Experience와 평가

소유: R11/R12. 소비: R13/R18.

모든 terminal/pending episode는 operational trail을 남긴다. OPERATIONAL_ONLY는 실패한 학습이 아니라 정상적인 선택 결과다. DEFERRED는 필요한 관찰 부족이며 success가 아니다. EXPERIENCE는 선택 이유와 episode lineage가 있는 경우에만 HistoricalCore를 만든다.

중복 completion/observation은 같은 selection/core를 중복 생성하지 않는다. 새 해석은 새로운 Interpretation/Reassessment ID로 원본에 연결한다. core에는 당시 Context/Judgment/Governance/Action/Outcome/Reality Feedback을 추적할 reference가 필요하다. 실행 전 중단/거절 episode는 해당 상태와 비실행 사실을 명시하여 action 성공으로 오해하지 않게 한다.

execution quality, observed outcome, decision-time semantic assessment는 다른 축이다. Body는 구조적 facts를 측정하고 Primary/Human assessment의 출처를 연결한다. 명시적 의미 평가가 없으면 decision quality는 UNKNOWN/UNEVALUATED이며 자동 MATCH가 아니다.

## C07 — policy 소비와 실제 trace

소유: R13. 소비: R18/R19.

기존 `BehaviorChangeTrace`의 shadow_selection/actual_selection은 **실제 같은 frozen task 입력에 selector를 실행해서 얻은 ID tuple**이다. expected refs를 합쳐 만들지 않는다. shadow는 side-effect 없는 비교이며 tool을 두 번 실행할 근거가 아니다. 정책 ID/version, input snapshot, consumer, outcome reference를 연결한다. deferred outcome은 뒤에 append로 연결한다.

policy는 allowlisted 운영 knob만 소비한다. 적용 전에 scope/current applicability/validation/retirement를 확인한다. grant·헌법·Human-only ceiling·과거 관측은 바꾸지 않는다. activation과 rollback은 versioned/CAS이고 reasoning pin과 실행 freshness는 C03을 따른다.

## C08 — live experiment ledger

소유: R17/R18/R19.

등록 manifest는 task ID와 family/split/content digest, seed, arm order, primary metric, safety metric, mechanism flags, model digest, code fingerprint, hardware/runtime, 시간·호출·비용 budget을 가진다. trial ledger는 run/trial/task/arm/repetition IDs, 시작·끝·status, context/policy/model versions, 실제 calls/tools/selection IDs, receipt/outcome, budget 사용량과 error category를 가진다. 비밀 prompt/customer data를 그대로 증거에 노출하지 않는다.

schema 입력 검증 실패는 provider0이다. trial 중 예외/timeout/budget exhaustion은 partial results를 원시 ledger에 남기고 run completion과 efficacy verdict를 분리한다. 학습 누수와 both-arm safety 실패를 성공 trial 평균으로 숨기지 않는다. 108번 반복 실행은 108개의 독립 task를 뜻하지 않는다.

## C09 — composition과 상태 조회

소유: R15/R16.

한 task의 executor owner는 시작에 명시적으로 legacy 또는 canonical로 정한다. 같은 effect를 둘 다 실행하지 않는다. OFF/SHADOW/ACTIVE 설정, 실제 activation, 실제 effect/episode 상태는 다른 값이다. 지원하지 않는 entry를 status import reach로 지원한다고 표시하지 않는다.

status는 authenticated project의 durable records/projection에서 읽고 observed_at/source revision을 표시한다. unavailable/lagging도 정상 응답 상태로 표현한다. status 읽기가 Brain·learning·action을 새로 실행하면 안 된다. 실제 boot에서 required service가 없으면503을 유지한다.
