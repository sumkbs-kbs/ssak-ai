# 그래프 공통 진단 화면 설계

## 1. 목적과 안전 원칙

진단 화면은 구조가 비슷한 세 그래프를 한 지도로 합치지 않는다. **공통 프레임과 탐색 상호작용만 재사용하고, 데이터·점수·관계·시간 의미는 각 영역의 소유 모델 그대로 유지한다.** 사용자가 어느 graph source를 보고 있는지 모든 카드와 상세 패널에서 계속 드러나야 한다.

필수 UI 약속:

1. 세 영역은 고정된 이름/아이콘/색상으로 구분하고 데이터 계약을 표시한다.
   - **코드 구조 인덱스** — 파일·모듈·클래스·함수·심볼 관계; 코드 탐색과 영향 분석.
   - **GBrain 지식 메모리** — persistent memory node 및 directed relation; 선택적 vector search, 저장소별 reward state.
   - **작업 DAG** — 미션의 task/subgoal 및 의존성·수행 상태; DAG/ready/blocked 분석.
2. 선택한 영역이 바뀌면 graph, 검색 결과, 선택 노드, 필터를 통째로 분리한다. 다른 그래프의 ID·edge를 암묵적으로 합치거나 교차 탐색하지 않는다.
3. 각 영역은 자체 **Source / Scope / Freshness / Status** 머리글을 갖는다. 다른 영역에 대한 “같은 것” 연결이 없어야 한다.
4. 모르는 값은 `알 수 없음`, not applicable은 `해당 없음`, 빈 결과는 `0개`, 로딩/오류는 각각 별도 상태로 표현한다. 누락 데이터를 0이나 건강/완료로 대체하지 않는다.
5. 실제 API 응답에 없는 metric(예: 코드 인덱스 freshness, GBrain edge 수, DAG cycle count)은 현행에서 안다고 주장하지 않는다. **진단 미지원**으로 노출하거나 후속 read-only endpoint로 공급한다.
6. 화면은 기본적으로 read-only다. 인덱싱 실행, memory clear/redact, 작업 취소/재개는 이 진단 화면의 그래프 클릭이나 공통 액션으로 실행하지 않는다. 기존 전용 UI/API로 명시적으로 이동시킨다.

## 2. 실제 데이터 모델과 경계

| 영역 | 권위 데이터/현재 형태 | 의미 있는 방향 | 수명주기/주의 |
|---|---|---|---|
| 코드 구조 인덱스 | `engine/code_intel/KnowledgeGraph`의 in-memory `nodes` map + `edges` list. 노드 종류 `File`, `Function`, `Class`, `Variable`, `Module`; pipeline이 Python 파일 AST를 읽어 `CONTAINS` 등을 생성한다. | 파일 → 심볼 등의 코드 구조; 기본 호출 방향은 relation에 따라 설명한다. | 현재 `CodeIndexPipeline`은 instance에 새 그래프를 만들고, API의 search/impact가 `load_existing()` 시 빈 그래프면 다시 scan하는 현행 동작을 한다. 영구 graph snapshot/status 계약으로 간주하지 말 것. index POST는 scan/parse/resolve/cluster phase summary를 반환한다.
| GBrain | `GBrain` directed graph (`knowledge_graph.graphml`), global singleton 또는 project-scoped storage. 쓰기 진입은 `add_node`, `add_edge`; Chroma는 선택 의존성. | 방향성 relation `(source, target)`; node upsert는 별도 의미의 self-pair reward `(id,id)`. | graph의 장기 기억이다. Reward tick/score는 GBrain 내부 정책 데이터이며 code symbol centrality나 task progress가 아니다. 민감한 내용일 수 있으므로 본문 표시·검색/API 노출은 권한과 scope가 확정된 뒤에만 추가한다.
| 작업 DAG | `SubgoalGraph`의 `goal` + `nodes: dict[task_id, SubgoalNode]`, node의 `depends_on`, `TaskState`, result, verification rule. | `depends_on`은 종속 task에서 predecessor dependency를 가리킨다. UI는 이를 `A → B` “A 완료 후 B” 방향으로 그린다. | 현재 `SubgoalGraph`는 `AutonomousFlightController.launch_mission()` 안에서 생성되는 in-memory 객체로, mission report 밖에서 조회할 일반 API/지속 저장소가 확인되지 않았다. 일반 background `/api/tasks` queue/event는 task 실행 레코드이지 이 subgoal DAG 자체가 아니다.

**금지할 유사명 합치기**: CodeIndex node의 `id`와 GBrain `node_id`, DAG `task_id`, `TaskEvent.step_id/agent_id`는 타입과 의미가 다르다. 공통 UI component에 쓸 때도 선택된 domain의 id schema 안에서만 다룬다.

## 3. 정보 구조

신규 dashboard route 제안: `/diagnostics/graphs` — 좌측 sidebar에는 “그래프 진단” 단일 항목. 페이지는 기존 `page-container`, `page-header`, `glass-panel` 스타일과 접근성 패턴을 이용한다.

```text
그래프 진단
[프로젝트 범위: active project 표시]     [자동 새로고침: 꺼짐/30초]
[코드 인덱스] [GBrain 메모리] [작업 DAG]

[선택 domain의 Source · Status · Freshness · Limitations]
[domain별 KPI — 현행 응답으로 계산 가능한 항목만]

┌────────────── domain 그래프 ──────────────┐ ┌ 선택 항목 상세 ─┐
│ graph canvas / 명시적 node & edge 목록     │ │ 실제 source ID   │
│ domain-specific legend                    │ │ type/status/refs │
└───────────────────────────────────────────┘ └────────────────┘
[검색 · 노드 종류/상태 필터 · 페이지네이션 · 오류/empty state]
```

공통 shell properties (고정 visible):

- Domain tab/title + 한 줄 “이 그래프가 모델링하는 것” 설명.
- Scope badge: active project ID/name + canonical root의 최소 안전 표시. global GBrain이면 `전역 저장소`; mission DAG이면 mission ID, 없으면 `미션 범위 확인 불가`.
- Source badge: authoritative module/store/API와 response observed-at. Snapshot, live, in-memory, unavailable을 명확히 표기.
- Freshness: server가 제공한 observation time 또는 retrieval time으로 freshness와 data-age를 나눈다. index의 scan timestamp 부재 시 `스캔 시각 미제공`.
- Loading, stale, disconnected, unauthorized, empty, partial, error 상태를 구분. 숨겨진 프로젝트/다른 owner 자료의 존재 유무를 노출하지 않는다.
- 모든 graph selection과 filter는 domain-local state key를 사용. 세 tab을 이동해도 각자의 선택을 기억해도 되지만 state를 서로 공유하지 않는다.

## 4. 세 domain의 지표·탐색

### A. 코드 구조 인덱스

현행 POST `/api/code-intel/index` summary의 `phases.scan.total_files/languages`, `parse.symbols/calls`, `resolve.resolved_calls`, `cluster.communities/processes`, `elapsed_seconds`만 “마지막 indexing 응답”으로 표시할 수 있다. 이 숫자는 저장된 live index의 검증된 size/freshness와 같지 않음을 캡션으로 쓴다.

- Node list/canvas: file/module/class/function/variable type legend. node detail은 ID, type, `file`, `name`만 allowlist.
- Edge list는 `source`, `target`, `relationship` 원문. relationship을 call이라고 재명명하지 않는다.
- 검색은 `/api/code-intel/search`의 현재 `repo_path` 사용 계약을 확인한 뒤 호출하고 결과는 result source/type 포함. 영향도는 전용 `/impact` 결과 그대로, analysis boundary를 명시.
- Indexing은 이 페이지에서 직접 자동 시작하지 않음. 유저가 수동 인덱스 실행을 원하면 명시적 확인 후 기존 index operation으로 이동. 로딩 동안 duplicate submit 방지.
- 현재 in-memory 그래프의 read-only node/edge API는 확인되지 않았다. 초기 배포는 진단 endpoint가 제공될 때까지 요약/검색/impact 중심으로 시작하거나, schema에 맞는 안전한 bounded node-edge snapshot을 별도 backend 작업으로 추가한다. `CodeIndexPipeline` 내부 graph를 대시보드에서 직접 채우거나 테스트 전용 mock node를 실제 데이터로 보여주는 것을 금지.

### B. GBrain 지식 메모리

- Display는 project-scoped graph를 기본으로 하고 scope를 서버가 정한 canonical project binding에서 가져온다. 전역 memory는 별도 scope selector와 권한 조건이 확정된 경우에만 노출.
- KPI 후보: graph nodes/edges는 정확한 count API 제공 전까지 미지원. reward tick은 GBrain API가 숫자를 반환하도록 명시될 경우에만 표시. pair reward 10 상한은 reward-policy diagnostics이지 node quality score가 아니다.
- Privacy: 기본 검색/상세는 `id`, `label`, 비민감 scalar provenance allowlist. `content`, Chroma documents, metadata secret, full local path는 기본 미노출. server redaction을 거치지 않은 원문을 UI에서 regex로 마스킹해 안전하다고 취급하지 않는다.
- 그래프가 크거나 private data인 경우 server-side cursor pagination 및 response byte cap 사용. 관계량/edge 목록 endpoint에 limit이 없으면 canvas 전량 로드는 막는다.
- clear/redact는 다른 화면의 memory compliance 동작으로만 수행; 진단 canvas에서 파괴 작업 버튼을 제공하지 않는다.

### C. 작업 DAG

- 처음엔 domain을 “Subgoal DAG”로 표기한다. 일반 `/api/tasks` queue는 실행 task의 status 목록, `/api/tasks/{id}/events`는 owner-scoped task event stream이고 DAG dependency source가 아님.
- DAG node card: task_id, 짧은 description, `pending/ready/in_progress/completed/failed/blocked`, dependency count, 검증 규칙의 존재 여부. result/output/error는 별도 “민감할 수 있음” 접힘 상태이며 기본 감춤.
- edge label은 `depends_on`; direction legend: **선행 → 후행**. 현재 storage가 `node.depends_on`인 사실을 함께 표시한다.
- Ready/blocked/failure summary는 DAG snapshot에서 계산하되 server가 유효성/노드 수를 검증해야 한다. cycle/unknown dependency가 source 계약상 불가능한 것으로 assert하기보다 API serializer에서 진단 status/error로 기록.
- 현재 API/영구 store 부재: DAG 탭을 `아직 조회 가능한 실행 DAG 없음` 상태로 렌더링하고, task queue를 DAG인 것처럼 대체하지 않는다. 후속 API가 설계되면 mission ID를 받아 owner/project binding, task DAG snapshot과 state/version, read-only semantics를 제공한다.

## 5. 공통 API/UI 데이터 계약 (제안)

각 domain endpoint는 같은 envelope를 가지지만 domain payload는 discriminated union으로 분리한다. envelope의 일치는 graph merging을 뜻하지 않는다.

```ts
type GraphSource = 'code_index' | 'gbrain_memory' | 'subgoal_dag';
type Availability = 'available' | 'empty' | 'not_supported' | 'unavailable' | 'error';

type DiagnosticsEnvelope<T> = {
  schema_version: 1;
  source: GraphSource;
  availability: Availability;
  scope: { kind: 'project' | 'global' | 'mission'; id: string | null; label: string | null };
  observed_at: string | null;
  freshness: 'live' | 'snapshot' | 'unknown';
  limitations: string[];
  payload: T | null;
};
```

- Domain payload `CodeIndexSnapshot`, `GBrainSnapshot`, `SubgoalDagSnapshot` separate validators/types. Node/edge IDs are source-scoped branded IDs. No generic cross-graph edge.
- Required security: existing access PIN/session headers + project identity headers, server authorization before lookup, canonical root resolution, path validation for repo path, bounded `limit<=200`, cursor pagination, no untrusted file path traversal, output redaction. DAG/task owner check mirrors existing task API ownership. Never infer global/project identity from a dashboard query param alone.
- Failure responses preserve availability: no API -> `not_supported`; no indexed nodes -> `empty`; timeout/network/auth -> `unavailable`/`error` with safe error code, not empty graph.
- Caching keys include `(source, scope id, query, filters, cursor)` to prevent project bleed. Abort stale requests on project/source change; do not render prior project's graph as the new project's graph while loading.
- Read-only endpoints do not write, reindex, clear or mutate graph state; tests assert a GET makes no backend mutation.

## 6. 상호작용과 시각화

- Canvas library: project dependency list currently includes `mermaid` but no dedicated graph canvas library. Do not add an unverified package for first iteration. Start with accessible bounded SVG renderer plus synchronized accessible node/edge table; Mermaid may render DAG dependency flow from trusted, validated data but must not be treated as the data model. Avoid inserting untrusted IDs/labels as raw HTML.
- Layout algorithms are domain local: code structure hierarchical file→symbol; GBrain force-directed or simple adjacency only for a bounded sample; DAG layered topological order. Same coordinates/layout across graphs are meaningless.
- Canvas cap 300 nodes/500 edges per response; deterministic truncation + visible “일부만 표시” notice and server pagination/filter. If graph exceeds cap, require search/type scope before loading. Never silently collapse edges or claim complete visualization.
- Node selection highlights only same-domain adjacent edges, updates details via textContent/React-safe rendering, supports keyboard focus, Enter/Space, Escape, and synchronized list selection. Avoid click-to-open as only navigation mechanism.
- Color encodes only one documented domain-specific attribute (Code: node kind; GBrain: label; DAG: task state). Use text/shape/icon too, not color alone. Relationship labels remain visible in edge list and on high zoom.
- Layout includes zoom/pan controls with reset and fit; small screen falls back to list + detail instead of compressing three canvas columns.

## 7. 상태 문구/판정

- **Live** means endpoint returned current snapshot at `observed_at`; it does not mean durable, valid, complete, or healthy.
- **Snapshot** means retained historical output with source timestamp/commit. Never badge as live.
- **Indexing successful** means only that code-index endpoint returned success; it is not a release gate.
- **GBrain count/reward** is not graph quality/learning success.
- **Task status** and **DAG readiness** are distinct: task can be running while no subgoal graph is available, and a ready DAG node does not prove a background task was dispatched.
- Cross-graph causal conclusions are excluded unless a future explicit, provenance-bearing reference model is introduced and reviewed.

## 8. Rollout stages

1. **UI frame**: route + three isolated tabs; static explanations, source/scope/status slots, explicit unsupported states. No backend changes required; no false graph fixtures.
2. **Read-only backend adapters**: scoped endpoint for bounded code index, GBrain metadata-only stats/snapshot, and mission DAG snapshot. Separate response schemas and contracts; project/owner tests first.
3. **Accessible domain renderers**: source-local graph SVG + table, search/filter, limits, selected node detail. Contract fixtures can exercise graph rendering without pretending to be production observation.
4. **Live freshness and observability**: update source timestamps/counts from server truth; polling/backoff and disconnected/stale UX; prove project switch isolation and bounded response.
5. **Optional navigation**: links to existing code impact, memory compliance, task events/execution panel. Keep mutation actions in original surfaces.

Definition of done for all stages: never show records from an unselected source/scope; distinguish live/snapshot/unknown/unavailable; no false empty/zero; no mutation from read-only query; show direction/edge type; keep node/edge limits visible; keyboard/SR path matches canvas; domain API failures isolated so one tab's error cannot blank others.

## 9. Required test matrix

- Component: source badges distinguish exactly three domains; unique local state; empty/not-supported/stale/disconnected/error; malformed DTO rejected; no `content`/output leakage by default.
- Direction: code relationship labels preserved; GBrain `a→b` separate from `b→a`; DAG dependency A→B rendering agrees with `B.depends_on=[A]`.
- Scope/security: same-named IDs in different graph/scope don't collide; project change during request cancels old response; authorization failures cannot appear empty; no query-param path escape; DAG owner isolation.
- Bounded rendering: max nodes/edges/cursor; truncated notice; malicious labels/IDs rendered as text; large graph fallback; keyboard navigation parity.
- API contracts: source discriminant, observed_at/freshness/availability, filters, caps, safe error response. GET has no writes/reindex/clear side effects.
- Current capability guard: existing tests exercise CodeIntel index/search/impact, GBrain GraphML and reward policy, Task API/event ownership independently; do not merge their assertions into a fake common graph implementation.

## 10. Current-state note

This document specifies the shared diagnostics surface; it does not claim that the backend snapshots are implemented. Existing code proves code-index operation summaries/search/impact, GBrain persistence, and an in-memory SubgoalGraph used by flight control. Before stages 2–4, graph snapshot APIs and durable/owner-bound mission DAG observability remain implementation work. Until then, the safe initial UX is three clearly distinguished status cards, with unavailable subgraph views labeled honestly.
