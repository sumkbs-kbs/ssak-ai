---
title: "T02 — canonical store·legacy adapter 불변 저장·복구 증거"
date: 2026-09-22
status: verified-module
owner: 저장 담당(P02)
---

# T02 불변 저장·복구 (P02)

```yaml
check_id: T02
status: PASS (module-level)
owner: storage
source_head: 79582ccd556c103b8ff7c4237e348c38e2eeb025
command: .venv/bin/python -m pytest tests/cognitive -q  /  ruff  /  mypy
exit_code: 0
observed_behavior: duplicate ID 거부, write/commit/publish 각 crash 복구, 원본 digest 불변, 미완료 transaction 비노출
artifact:
  - src/antigravity_k/engine/cognitive/store.py (sha256 2172a9b6…)
  - src/antigravity_k/engine/cognitive/legacy_adapter.py (sha256 cc972338…)
  - tests/cognitive/test_store.py (sha256 de5d411c…)
  - tests/cognitive/test_legacy_adapter.py (sha256 77a22b03…)
limitations: 실제 사용자 경로(AgentRuntime·API·CLI) 연결은 P08/P11 범위다. VaultEngine 인스턴스와 동일 lock 파일을 쓰지만 VaultEngine 내부 write 경로와의 동시성은 실사용 통합 시점에 다시 시험한다.
verified_at: 2026-09-22T03:16:57Z
```

## 저장 계약 구현

- **원본 형식**: `records/<namespace>/<uuid>.md` — YAML frontmatter + JSON wire block. frontmatter에 `record_digest`를 기록한다.
- **create-only**: ID uniqueness를 내용과 무관하게 강제한다. 이미 공개된 ID는 같은 transaction 재사용 외에는 `DuplicateRecordError`다.
- **transaction manifest**: `stage()`가 `.cognitive/staging/<txn>/manifest.json`에 record 전체(wire + digest)를 기록하고, `commit()`이 staging 파일 flush → `os.replace` → Git commit → `.cognitive/committed/<txn>.json` 공개 순서를 수행한다.
- **공개 경계**: reader(`read`/`list_committed`/`resolve`)는 committed manifest에 열거된 record만 본다. rename 후 publish 전 상태는 조회되지 않는다(`test_stage_does_not_publish`, `test_failed_git_commit_is_invisible_then_recovered`).
- **복구**: Git commit 실패 시 `GitCommitError`로 publish를 막고, `recover()`가 같은 transaction ID를 재대조해 publish한다. 이미 공개된 transaction은 건너뛰므로 반복 호출이 중복 publish를 만들지 않는다.
- **digest 불변**: `verify_digests()`가 재계산으로 변조를 검출하고(`CanonicalDigestError`), 새 Interpretation을 append해도 기존 record 파일 byte는 변하지 않는다.
- **lock/Git 재사용**: Git 저장소 root에서 `VaultEngine`과 같은 `.git/.agk_vault.lock`을 사용한다(`store.lock_path`). 별도 lock 순서를 만들지 않는다. **버그 발견·수정**: `SoftFileLock`이 `.git` 디렉터리를 먼저 생성해 `git init`이 건너뛰어지고 `git add`가 "not a git repository"로 실패했다. `ensure_git_repo`가 `git rev-parse --git-dir`로 repo 유효성을 확인하도록 고쳤고, git 비활성 store는 `.cognitive/agk_vault.lock`을 쓴다.
- **참조 검증**: commit 전에 `validate_references`(존재·타입·project 범위)와 `supersedes` 순환 검사를 수행한다. 한 transaction 안에서 서로 참조하는 record는 함께 commit할 수 있다. 검증 실패 시 어떤 파일도 공개되지 않는다.
- **index**: `.cognitive/index/records.json`은 committed manifest에서 재생성 가능한 projection이다(`rebuild_index`).

## legacy adapter (PersistentAgency)

- legacy SQLite는 **읽기 전용**이다. `test_legacy_database_is_not_modified`가 import 전후 DB 파일 SHA256과 event 수를 비교한다.
- 매핑: legacy project 문자열 → `project:` ID(고정), trajectory event → canonical `Event`, objective → `Goal`, task 제출 → `Action`(`idempotency_key="legacy-task:<id>"`). mapping manifest는 `.cognitive/legacy/agency_map.json`에 append-only로 보존한다.
- 같은 legacy 원자료는 같은 canonical ID를 반환하고, 내용이 바뀌면 `LegacyMappingConflict`, 알 수 없는 legacy enum은 `UnmappedLegacyValue`로 거부한다.
- origin 계보는 `REL_ORIGIN` reference로 표현하며, mapping이 없으면 reference를 만들지 않는다(추정 금지). Project record가 공개된 경우에만 `REL_PROJECT` reference를 추가한다.

## 검증 명령과 결과

```
.venv/bin/python -m pytest tests/cognitive -q   → 83 passed (models 57 + store 17 + adapter 9)
.venv/bin/python -m pytest tests/cognitive tests/test_agent_runtime.py tests/test_context_shaper.py \
    tests/test_tool_executor.py tests/test_cognitive_loop_events.py tests/test_task_state_store.py \
    tests/test_persistent_agency.py -q            → 219 passed (기존 회귀 신규 red 0)
ruff check / ruff format --check / mypy src/antigravity_k/engine/cognitive → clean
```

## 남은 것 (다음 카드)

- P03: protected target enforcement — store의 writer allowlist와 연결해야 한다(현재 store는 경로 보호를 강제하지 않는다).
- P07: action receipt와 제출 idempotency를 legacy task 매핑과 연결한다.
- P12: 기존 DB → canonical backfill dry-run과 ID mapping 보고서.

## 2026-09-24 회차 — 실제 VaultEngine write 경로와의 동시성 (T02 남은 limitations를 닫음)

위 limitations("VaultEngine 내부 write 경로와의 동시성은 실사용 통합 시점에 다시 시험한다")를
현재 트리에서 닫은 회차다. **실제 VaultEngine**(git 자동 commit 포함, `sync_rag=False`)과 함께 돌렸다.

```yaml
check_id: T02-vault-concurrency
status: PASS (실제 VaultEngine 통합)
owner: storage
source_head: 456731b0 (dirty — 본 회차: tests/cognitive/test_store.py)
command: .venv/bin/python -m pytest tests/cognitive/test_store.py -q (5회 반복)
exit_code: 0 (19 passed × 5 — 요동 0)
observed_behavior: 아래 두 배치
artifact: tests/cognitive/test_store.py (17→19 시험)
limitations: 실제 사용자 경로(API·CLI에서 이 store를 호출하는 배선)는 P11 이월.
verified_at: 2026-09-24T20:10:17Z
```

### 두 배치의 관찰

- **같은 repo root 배치(공유 lock)** — vault와 store가 같은 root에서 같은 `.git`을 쓸 때,
  양쪽 lock 파일이 **문자 그대로 같은 파일**(`root/.git/.agk_vault.lock`)임을 확인하고, 실제
  VaultEngine `write_note`(노트 파일 + git add/commit) 2스레드 × 3회와 CanonicalStore
  `commit_records`(records/.cognitive + git add/commit) 2인스턴스 × 3회를 **동시에** 돌렸다.
  결과: 실패 0(git index 경합으로 깨지는 commit 없음) · 공개 record 6 · `verify_digests()` 6 ·
  노트 6 전부 실재. store 스레드는 인스턴스를 분리해 썼다 — 같은 `SoftFileLock` 인스턴스는
  프로세스 안 재진입으로 세므로 스레드를 직렬화하지 않는다(기존 동시성 시험과 같은 형태).
- **기본 배치(공유 없음이 설계)** — `default_store()`은 `.cognitive/canonical`에 git 비활성으로
  놓인다. store가 `.git`과 git index를 전혀 건드리지 않으므로 vault와 **공유할 경합 자체가 없다**
  (lock 파일이 다른 것이 결함이 아니라 설계다 — 이유를 시험으로 고정). vault 3노트 + store 3commit
  병렬·교차 실행 모두 성공, 원본·digest 불변.
