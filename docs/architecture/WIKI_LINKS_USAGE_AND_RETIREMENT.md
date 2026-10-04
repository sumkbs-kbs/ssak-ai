---
title: 위키 관계 테이블 사용 현황 및 폐기 기준
date: 2026-09-26
tags: [architecture, wiki, sqlite, migration, data-retention]
---

# 위키 관계 테이블 사용 현황 및 폐기 기준

## 결론

`wiki_links`의 기본 DB 읽기 전용 조사에서는 0행이었지만, 이는 전체 설치 범위의 데이터 부재나 런타임 미사용을 증명하지 않는다. 현재 Obsidian 링크 파싱·대상 해석·볼트 임포트·방향 관계 저장·1-hop 검색 확장을 유지하기로 했고 이 기능 경로를 구현했다. 폐기 판정과 프로덕션 변경은 보류이며, 기존 집계는 구현 이전의 조사 스냅샷이다.

## 1. 구조와 코드 참조

`src/antigravity_k/knowledge/wiki.py`의 `LLMWiki._init_db()`가 위키 엔트리, FTS, `wiki_links`, KG tick/reward 테이블을 만든다. `wiki_links`는 `(from_id, to_id)` 복합 기본 키, `relation`, `created_at`, 두 endpoint의 `ON DELETE CASCADE` 외래 키를 갖는다. 역방향/백링크 조회를 위해 `(to_id, from_id)` 인덱스도 있다.

KG 점수/tick 정책은 `src/antigravity_k/knowledge/wiki_graph.py`가 같은 SQLite 트랜잭션 안에서 적용한다. 성공한 각 노드/관계 변경 tick은 기존 node/link 점수 전체에 `0.95` 감쇠를 적용하고 변경된 노드 또는 directed pair 점수를 증가시키며 상한은 pair당 `10`이다. Batch는 여러 tick의 순서를 보존해 감쇠한다. 삭제는 제거 노드/incident edge에 보상하지 않고 감쇠 tick만 기록한 뒤 FK cascade와 명시적 graph 정리를 수행한다. DB mutation 실패 시 관계·위키 행·reward/tick을 함께 rollback한다.

## 2. 읽기 전용 기준 집계 (구현 전 스냅샷)

초기 조사에서는 `LLMWiki()` 및 `_connect()`를 사용하지 않았다. 각각 DDL과 `PRAGMA journal_mode=WAL`을 수행하기 때문이다. SQLite URI `mode=ro`, `PRAGMA query_only=ON`, 명시적 읽기 트랜잭션으로 조회 후 rollback/close했다. 당시 DB·WAL·SHM 해시가 전후 동일했다.

| 항목 | 구현 전 조사 결과 |
|---|---:|
| 기본 DB (`data/wiki.db`) 크기 | 15,446,016 bytes |
| `wiki_entries` / `wiki_links` | 18,243 / **0행** |
| self/reverse/duplicate/orphan 관계 | 모두 0 |
| 빈 `created_at` / FK 위반 | 0 / 0 |
| DB `user_version` / journal mode | 0 / WAL |
| DB SHA-256 | `5aa426bbefe98f58e1dd8577759f48976c447597ebaca1a9ac326abce7d0529d` |

범위는 기본 DB, fallback 후보, `data/projects.json`에 등록된 2개 프로젝트의 규약상 DB 후보 등 4개 경로였다. DB는 기본 DB 1개만 존재하고 나머지 3개는 없었다. 다른 설치본, 임의 경로 프로젝트 DB, 복제본/백업은 확인하지 않았다. `PRAGMA integrity_check`도 당시 수행하지 않았다. `data/wiki_entries`의 Markdown 359개 lexical 검사에서 `[[...]]` 형태는 85개 파일/625회였지만 관계 테이블 사용 증거는 아니다. 위 수치/hash는 구현 전 조사 시점만 설명하며 현재 DB 상태로 일반화하지 않는다.

## 3. 구현 및 실행 계약

### 파싱·임포트

`src/antigravity_k/knowledge/obsidian_links.py`는 wiki-link 경로, heading, alias, embed 구문, frontmatter 별칭 및 안전한 대상 해석을 제공한다. fenced/inline code 및 escaped 링크는 무시한다. `plan_obsidian_vault()`는 일반 Markdown만 읽고 숨김 경로와 symlink는 건너뛴다. 접근/UTF-8 오류가 하나라도 있으면 `import_obsidian_vault()`는 DB 쓰기 전에 실패한다.

임포트는 전체 vault를 먼저 계획한 다음 SQLite write lock 안에서 기존 `source IN ('vault', 'obsidian')` 엔트리를 path 기준으로 갱신하고 링크 대상을 entry ID로 해석한다. 노트 추가/변경, 관계 생성/삭제, 점수·tick 갱신, 제거된 문서 endpoint 정리는 단일 DB 트랜잭션이다. 반복 임포트는 변경이 없으면 tick을 증가시키지 않는다. rename/move/delete에 따라 오래된 링크를 제거하고 대상을 다시 계산한다. 숨김 또는 symlink 때문에 스캔에서 제외된 기존 노트/링크는 불완전한 인벤토리로 간주해 보존한다. 비-Obsidian relation 행은 임포트에서 수정하지 않는다.

공유 Vault 쓰기 및 privacy 복원/재동기화는 `source_url` 완전 일치로 같은 항목을 갱신한다. 제목이 같아도 다른 파일은 덮어쓰지 않으며, 내용이 바뀌지 않은 재동기화는 reward tick을 추가하지 않는다. `vault`와 `obsidian` source는 같은 exact path에서 중복 생성되지 않도록 서로 재사용한다. 현재 같은 위키 DB가 여러 Vault를 함께 소유하는 별도 registry/policy는 없다.

### 검색

`LLMWiki.search()`는 FTS seed 결과를 순위대로 보존하고 명시적 방향(`outbound`, `backlinks`, `both`)으로 한 hop만 확장한다. 현재는 `relation='obsidian'` 행만 확장한다. category 조건은 seed와 연결 항목 양쪽에 적용되고 전체 `limit` 및 중복 제거를 지킨다. 직접 결과는 이웃보다 우선한다. 확장 결과는 `matched_field='wiki_link'`로 표기하고 접근 로그에 기록한다. 백링크용 `(to_id, from_id)` 인덱스가 있으며 검색은 seed와 인접 관계만 조회한다. `search_for_llm()`은 완전한 문서 block만 포함하고 전체 문자열 길이를 `max_chars` 이하로 제한한다.

### 삭제·개인정보

항목 삭제, retention, 전체 purge, vault source purge는 제거할 노드/incident edge에 reward decay tick을 반영한 뒤 같은 트랜잭션에서 위키 행을 제거한다. FK 설정이 꺼진 legacy 연결에서도 graph/reward 행을 명시적으로 제거한다. `delete_vault_sources()`는 `'vault'`와 `'obsidian'` source를 모두 purge한다. Privacy redaction/restore는 동일 source path의 행을 삭제 후 새 항목으로 복제하지 않고 갱신하여 기존 graph 연결/reward identity를 보존한다. 전체 삭제는 관계/reward 행을 비우고 반복 호출에 안전하다.

## 4. 회귀 테스트 및 검증

| 계약 | 테스트 증거 |
|---|---|
| 파싱/해석 | `tests/test_obsidian_links.py`: 구문, code mask, alias, ambiguity, path traversal, symlink |
| 임포트/멱등성 | `tests/test_wiki_obsidian_links.py`: 임시 볼트·SQLite, alias/forward link, move, 불완전 스캔, skip 보존 |
| 관계 동기화 | 변경·삭제·이동 재임포트 후 stale edge/orphan 없음, 동일 재임포트 tick 변화 없음 |
| 검색 | outbound/backlink, 관계 종류 필터, category, limit, opt-out, 접근 기록, LLM 길이 제한 |
| 삭제/privacy | entry delete, vault purge, retention, clear-all, legacy FK OFF, reward/tick 정책 |
| validator | 임시 DB에서 `KGBinaryValidator.validate()`가 `OK=True`, legacy orphan는 거부 |
| Vault 연동 | 같은 제목의 서로 다른 Vault path, 재기록 멱등성, privacy redaction/restore 경로 identity |

검증 실행:
- `uv run pytest tests/test_wiki_obsidian_links.py tests/test_obsidian_links.py tests/test_wiki_vault_privacy.py tests/test_vault_privacy_api.py tests/test_vault_privacy_service.py tests/test_memory_compliance.py -q` — **84 passed**.
- 집중 `uv run ruff check` — 통과. 집중 `uv run basedpyright --level error` — 0 errors, 0 warnings, 0 notes. 해당 변경 파일들에 `git diff --check`도 통과했다.
- 앞선 추가 회귀에서 `tests/test_durable_memory_purge.py::test_gbrain_clear_all_removes_graph_and_vectors`는 실패 관측이 있었다. `GBrain.clear_all()`이 `_mutation_lock` 초기화를 기대하나 `object.__new__` 기반 기존 fixture에 lock이 없는 경로다. 이번 집중 최종 실행에는 해당 파일을 포함하지 않았고, 공유 checkout의 별도 GBrain 작업과 겹쳐 수정하지 않았다.
- 모든 새 데이터 검증은 테스트 임시 디렉터리/DB에서 수행했다. 실제 `data/wiki.db`, 사용자 Vault의 운영 데이터에 마이그레이션/drop은 적용하지 않았다.

## 5. 폐기 안전 게이트와 판정

폐기는 현재 목표가 아니며 DROP 또는 프로덕션 마이그레이션은 수행하지 않았다. 나중에 폐기를 검토한다면 개발/운영/프로젝트/복제/백업 DB 전체 인벤토리, 대표 업무 주기의 runtime read/write 접근 계측, WAL-safe 백업/복구 리허설을 먼저 마쳐야 한다. 테이블 없는 DB의 핵심 위키 동작, DDL 자동 재생성 방지, FK ON/OFF, privacy/retention/clear-all, idempotent rollback을 별도로 검증한다. 데이터가 있거나 판독 불가하면 소유자 승인·보존·복구 계획 전까지 fail closed한다. quiet window, 범위, 복구, 승인 게이트가 모두 통과하기 전 물리 삭제를 금한다.

**현재 판정: 관계 기능은 구현 및 격리 DB 회귀 검증 완료, 프로덕션 배포/운영 검증은 별도.** 구현 전 기본 DB의 0행을 지금 상태로 외삽하지 않으며 운영 관측이나 전체 설치 데이터 인벤토리가 완료됐다고 주장하지 않는다.
