# GBrain 보상 감쇠·쌍별 상한 정책

## 상태와 범위

- 범위: `antigravity_k.engine.gbrain.GBrain`의 모든 영속 쓰기 경로. 전역 singleton과 `_gbrain_for_project()`가 만든 project-scoped instance에 같은 규칙을 적용한다. `engine/code_intel`의 별도 메모리 그래프는 이 GBrain 저장소가 아니므로 범위 밖이다.
- 정책 승인: 모든 `add_node`/`add_edge` 호출이 성공해 그래프와 GraphML을 저장하면 해당 GBrain 저장소 tick을 1 올린다. 실패한 쓰기와 존재하지 않는 endpoint 때문에 거부된 `add_edge`는 tick이 아니다.
- 점수 초기값은 0. 변경된 pair에는 `+1`을 더한다. 각 성공 tick에서 **모든 pair** 점수를 먼저 `score × 0.95`로 감쇠한 다음 변경 pair에 `+1`하고 `10`으로 제한한다. 점수는 유한한 `0 < score ≤ 10`으로 보관하고 0은 항목 없음으로 표현한다.
- 노드 upsert의 pair는 `(node_id, node_id)`. 간선 pair는 방향성을 보존한 `(source_id, target_id)`. 반대 방향은 별도 pair이며 같은 방향의 기존 edge relation을 대체하는 쓰기도 새 tick/보상이다.
- 구현은 모든 pair를 먼저 `R_d = 0.95R`로 감쇠한 다음 이벤트 pair에 대해 `R' = min(10, R_d + 1)`을 적용한다. 비대상 pair는 `R' = R_d` 이다. 이벤트 순서가 보상을 바꾸며, decay는 이벤트 기반 tick이지 벽시계 시간이 아니다.

## 영속화 및 마이그레이션

- Tick과 pair 점수는 `knowledge_graph.graphml`의 버전 관리 scalar graph 속성에 저장된다. pair 목록은 JSON 문자열로 직렬화되어 별도 sidecar와 원자적 다중 파일 업데이트 없이 GraphML snapshot과 함께 복구된다.
- 기존 GraphML에 보상 메타데이터가 전혀 없으면 tick 0 / 보상 없음으로 읽는다. 기존 그래프의 노드/간선은 점수를 추론해 backfill하지 않는다. 다음 쓰기부터 새 정책을 누적한다.
- state 버전 누락/미지원, 부분 상태, 중복 pair, 비수치·비유한·음수·상한 초과 score는 조용히 초기화하지 않고 `GBrainCorruptSnapshotError`로 거부한다. **그래프 파일 자체가 손상되어 읽지 못하면 빈 그래프로 조용히 성공하지 않는다** — 동일 예외로 fail-closed한다. 복구는 운영자가 backup 복원·손상 파일 제거·명시적 `clear_all` 경로를 택할 때만 한다.
- GraphML 쓰기는 임시 파일에 완료한 뒤 `os.replace`로 교체한다. `add_node`, `add_edge`는 저장 완료를 확인한 뒤 성공을 반환하며 저장 실패 시 그래프·tick·점수와 가능한 Chroma 투영을 이전 값으로 복구한다. 메모리만 바뀌고 보상 성공으로 처리되는 비동기 fire-and-forget은 허용하지 않는다.
- `clear_all()`은 그래프, 노드 벡터, tick과 점수를 함께 비우고 새 빈 그래프를 저장한다. 이 purge 자체는 보상 이벤트가 아니다. `redact_all()`은 민감 문자열만 비식별화하고 tick/점수를 보존하며 tick을 올리지 않는다. export/search는 읽기 전용이다. retention은 현재 no-op이며 이후 삭제 동작을 구현할 경우 보상 이벤트 여부를 별도로 정해야 한다.
- 그래프·점수 snapshot은 `GBrain` 인스턴스 lock과 저장소의 `.gbrain.lock` file lock으로 직렬화하고, commit 전에 최신 GraphML을 다시 읽는다. 같은 저장소를 공유한 여러 프로세스도 tick을 잃지 않는다. GraphML 저장은 임시 파일 + 원자 교체 + 가능한 플랫폼의 디렉터리 fsync이며, 원자적 교체 이후 디렉터리 fsync 미지원은 저장 실패로 오판하지 않는다. Chroma는 보조 투영이며, 쓰기 전 대상 record를 snapshot해 호출이 실패하면 이전 record를 복구한다.

## 검증 기준

1. **수식**: 새 노드/간선의 첫 점수 `1`; 다음 쓰기 tick 후 이전 점수 `0.95`; 기존 점수의 decay와 target `+1` 순서를 고정한다.
2. **모든 기록 경로**: add_node 신규/중복 upsert와 add_edge 신규/동일 방향 관계 대체 각각 tick 1; 같은 pair로 40회 쓰기에서도 상한 10.
3. **pair 격리**: 노드 self-pair, source→target, target→source 점수 독립성 및 매 tick 모든 pair decay 확인.
4. **실패/무효 쓰기**: Chroma upsert 실패와 GraphML 저장 실패 시 그래프, vector projection(가능한 경우), tick 및 모든 점수가 전 상태로 유지. 없는 edge endpoint는 완전 no-op.
5. **수명주기**: GraphML flush 완료 뒤 재인스턴스화해 tick·score·그래프 일치; 구버전 GraphML은 0 상태; 부분/손상/알 수 없는 reward metadata는 거부. clear_all 초기화와 redact_all 보존 확인.
6. **저장소 격리/선택 의존성**: 각각 별도 storage_dir의 두 GBrain 인스턴스는 state를 공유하지 않으며, 같은 storage_dir를 공유한 인스턴스는 서로의 최신 그래프/tick을 반영한다. ChromaDB 없는 graph-only 환경에서도 동일 정책과 회귀가 통과한다.
7. **품질 게이트**: `uv run pytest tests/test_gbrain.py`, 변경 Python 파일 Ruff 및 basedpyright 오류 게이트를 실행한다. 공식 `KGBinaryValidator.validate()`가 `OK=True`여야 하는 KG release gate는 코드 단위시험과 구별한다. validator 구현/호출법을 찾거나 실제 성공을 증명하지 못했다면 `NOT_RUN`로 남기고 전체 KG release PASS를 주장하지 않는다.

## R20 의미·소비자·승격 경계 (2026-09-26)

- **의미 고정:** `reward_score` / `reward_tick`은 성공한 영속 쓰기의 **recency/frequency 저장 메타데이터**다. task utility, semantic truth, confidence, applicability, authority, cognitive maturity가 **아니다**.
- **승격 상태:** `experimental_storage_metadata`. 의사결정 authority/confidence에 자동 승격하지 않는다. `GBrain.reward_implies_authority()`는 항상 False.
- **실제 소비자(graph-first 조사):** production 경로에서 `reward_score`로 검색·순위·권한을 바꾸는 caller는 **없다** (`REWARD_SELECTION_CONSUMERS = ()`). `failure_memory` / `user_model` / API export·redact는 노드 쓰기·semantic search(Chroma distance)·purge만 사용한다. 새 소비자를 만들어 복잡성을 정당화하지 않는다.
- **enabled vs disabled:** reward는 쓰기 경로에 내장되어 끌 수 있는 별도 feature flag가 없다. 대신 selection consumer가 reward를 읽지 않음을 관측으로 고정한다(검색/이웃 결과에 reward·authority 필드 없음).
- **비용:** 매 성공 write는 전 pair decay + GraphML 원자 rewrite다. 고정 규모 latency는 `tests/test_gbrain.py::TestR20RewardMeaningAndConsumers::test_r20_a4_write_amplification_at_fixed_scale`로 재현한다.
- **공식 KG validator:** `KGBinaryValidator`는 wiki SQLite(`knowledge/wiki_graph.py`) 소유이며 GBrain GraphML release gate가 아니다. GBrain에 대한 `KGBinaryValidator.validate() OK=True` 주장은 **NOT_RUN** (잘못된 대체물 금지).
