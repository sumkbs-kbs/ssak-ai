---
title: "T01b — 헌법·protected authority enforcement 증거"
date: 2026-09-22
status: verified-module-and-gate
owner: 주 에이전트(P03)
---

# T01b 헌법 보호 (P03)

```yaml
check_id: T01b
status: PASS (module + tool gate + store)
owner: principal
source_head: 79582ccd556c103b8ff7c4237e348c38e2eeb025
command: .venv/bin/python -m pytest tests/cognitive -q  /  ruff  /  mypy  /  tool gate 회귀
exit_code: 0
observed_behavior: learned policy·runtime actor의 직접/간접 헌법 변경 거부, 승인 없는 protected ceiling 변경 0,
  symlink·shell·patch·store 우회 차단, 기존 tool/permission 회귀 156 passed
artifact:
  - src/antigravity_k/engine/cognitive/protected_targets.py (sha256 090bc97f…)
  - src/antigravity_k/engine/cognitive/store.py (sha256 26a65e6f…, write_guard 연결)
  - src/antigravity_k/tools/permission_gate.py (sha256 ca51e2b9…, 수정: cognitive protection 단계 추가)
  - tests/cognitive/test_protection.py (sha256 b5774397…, 19 시험)
  - tests/test_tool_sandbox_coverage.py (sha256 8244251f…, 수정: store.py process path 등록)
limitations: migration 전용 runner와 self-evolution의 실제 실행 경로에는 아직 hook을 넣지 않았다(호출 시 같은 guard를 직접 호출해야 한다). 승인 record 발급 자체는 P05/P06 governance 범위다. 문서 hash 검사는 보호 근거로 사용하지 않는다.
verified_at: 2026-09-22T03:28:22Z
```

## 보호 대상과 판정

| class | 기본 protected root | 보호 이유 |
|---|---|---|
| CONSTITUTION | `docs/ssak-ai-core/SSAK_AI_CONSTITUTION.md`, `SOURCE_MANIFEST.json`, `MASTER_PROMPT_V2_SOURCE.md`, store `records/constitution_rule/**` | 헌법 원칙 원문·원문 digest·헌법 rule record |
| HUMAN_AUTHORITY | store `records/authority_profile/**`, `.cognitive/legacy/agency_map.json` | authority ceiling과 legacy 계보 mapping |
| PROJECT_PREMISE | store `records/project/**` | Human이 소유한 premise |
| HISTORICAL_DELETION | store `.cognitive/committed/**` | 공개된 이력 manifest |

판정 순서: path realpath 해석 → project 밖이면 `PATH_ESCAPE` → protected class 일치 → actor 규칙 → 사람 승인 결박 검사.
actor 규칙은 **brain·learned_policy·plugin·evolution·migration은 승인이 있어도 `ACTOR_FORBIDDEN`** 이고, body/tool은 사람 승인(`human:` 발급자)이 있어야 `ALLOWED`다. 사람 actor는 최종 권한자이므로 승인 없이 허용하되 판정을 기록한다.

승인은 `action_digest`(store에서는 record wire digest)·`resource_scope`·`protected_class`·`expires_at`·`revision`에 결박되며, 각 불일치는 `APPROVAL_DIGEST_MISMATCH`·`APPROVAL_SCOPE_MISMATCH`·`APPROVAL_CLASS_MISMATCH`·`APPROVAL_EXPIRED`로 구분된다.

## 우회 경로 차단 (T01b가 요구한 4개 경로)

- **canonical path/traversal**: realpath로 해석하므로 `..`·중간 symlink를 거친 쓰기도 실제 대상으로 판정된다. project 밖 대상은 `PATH_ESCAPE`다.
- **symlink**: `src/innocent.md → docs/ssak-ai-core/SSAK_AI_CONSTITUTION.md` 같은 링크는 protected로 분류된다(시험 `test_symlink_into_protected_root_is_detected`).
- **shell**: `evaluate_shell_command`가 redirect/`tee`/`sed -i`/`cp`/`mv`/`rm`/`dd of=` 같은 쓰기 표시를 찾아 대상을 추출하고, protected 이름이 있는데 대상을 확정할 수 없으면 `SHELL_WRITE_INDETERMINATE`로 **fail-closed** 거부한다. 읽기 명령은 허용한다.
- **policy(간접)**: `evaluate_policy_target`은 allowlist(`PolicyTarget` 14종) 밖 target과, rule/parameter 문자열에 protected 이름·경로가 섞인 간접 시도를 `POLICY_TARGET_NOT_ALLOWED`로 거부한다.
- **plugin/migration/evolution**: `ActorKind`로 명시되며 protected class에서는 항상 거부된다. 각 실행 경로는 이 guard를 호출해야 한다(미연결 항목은 limitation에 기록).

## runtime 연결점 (실제 코드 변경)

1. **tool gate** — `PermissionGate.decide()`에 protected target 단계를 추가했다. 파일 쓰기 도구(`file_path`/`path`/`target`/`dir_path`, `apply_patch`의 patch 경로)와 shell 도구(`run_bash_command`/`bash`/`run_persistent_command`)가 같은 판정을 지나며, 거부 시 `Permission.DENY`(source=`cognitive_protection`)를 반환한다. request-scoped workspace(`effective_root`)를 반영해 root를 다시 계산한다. 승인은 `set_protection_approvals()`로 등록한 사람 승인 record만 인정한다.
2. **canonical store** — `CanonicalStore(write_guard=...)` + `commit_records(..., approvals=...)`. record producer kind가 actor가 되므로 **brain이 만든 헌법 record는 승인과 무관하게 거부**되고, body record는 승인 digest가 wire digest와 일치해야 공개된다. 검증 실패 시 어떤 파일도 공개되지 않는다.

## 검증 명령과 결과

```
.venv/bin/python -m pytest tests/cognitive -q                       → 102 passed (protection 19 포함)
.venv/bin/python -m pytest tests/test_tool_executor.py tests/test_ws02_tool_root.py \
    tests/test_claw_integration.py tests/test_plan_guard.py tests/test_fr02_shell_execution_boundary.py \
    tests/test_command_execution_boundary.py -q                     → 156 passed
.venv/bin/python -m pytest tests/test_vault.py tests/test_persistent_agency.py … → 284 passed (영향 영역)
ruff check / ruff format --check / mypy                              → clean
```

## 기존 red (분리 기록, 내 변경과 무관)

- `tests/test_tool_sandbox_coverage.py::test_all_process_execution_paths_are_accounted_for`는 `tools/ssak_bundle_store.py`(`subprocess.run`, S603 noqa 포함, HEAD 커밋 상태) 때문에 실패한다. HEAD의 ALLOWLIST에도 미등록이므로 **기존 red**다. 다른 작업 소유 파일이라 수정하지 않았고, 내 `engine/cognitive/store.py` 경로는 등록해 신규 red를 만들지 않았다.

  > **2026-09-23 정정.** 이 시험은 이후 샌드박스 ALLOWLIST에 `FIXED_ARGV` 로 등록되면서 **green 이 됐다**(신뢰 루트·sha256·arch 통과 뒤 고정 argv selftest — `ARCHITECTURE_REVIEW.md` §1.5). 위 문장은 그 시점의 관찰로 남기되, "기존 red" 는 지금 기준으로 낡았다.

## 남은 것 (다음 카드)

- P05/P06: 사람 승인 record 발급·검증을 governance/readiness와 연결한다(현재는 승인 객체를 호출부가 주입).
- P07: action receipt와 protected target 승인을 같은 digest 체계로 묶는다.
- P11: migration/self-evolution 실행 경로에 guard hook을 강제한다.

## 2026-09-24 회차 — migration/evolution 실제 경로 hook + 승인 발급·취소

위 limitations가 스스로 지적한 두 빈자리("migration 전용 runner와 self-evolution의 실제 실행 경로에는
아직 hook을 넣지 않았다")를 닫은 회차다. guard 함수 시험과 **실제 진입 경로** 시험을 분리했다(v1.1).

```yaml
check_id: T01b-entry-paths
status: PASS (module + 실제 진입 경로)
owner: principal
source_head: 7ea468e9 (dirty — 본 회차: protected_targets.py · migration.py · evolution.py · test_protection.py · tests/test_evolution.py)
command: .venv/bin/python -m pytest tests/cognitive/test_protection.py tests/cognitive/test_migration.py tests/test_evolution*.py tests/test_self_evolution*.py tests/test_meta_evolution*.py tests/test_prompt_meta_evolution.py -q
exit_code: 0 (43 passed — protection 19→23)
observed_behavior: 아래 매핑
artifact:
  - src/antigravity_k/engine/cognitive/protected_targets.py — issue_human_approval · guard.revoke(APPROVAL_REVOKED) · migration_guard factory
  - src/antigravity_k/engine/cognitive/migration.py — LegacyMigrationRunner._target_store(write_guard=migration_guard)
  - src/antigravity_k/engine/evolution.py — EvolutionManager 기본 guard 결선 + _save_draft(EVOLUTION channel)
  - tests/cognitive/test_protection.py (23 시험)
limitations: 발급 주체의 진위(그 사람이 실제로 입력했는가)·사용자 표면에서의 실제 우회 경로 관찰은 P11 이월. evolution API/coordinator 호출처는 기본 결선으로 보호된다(별도 전달 없이 vault root guard).
verified_at: 2026-09-24T14:40:42Z
```

### 실제 진입 경로 매핑

- **migration** — `LegacyMigrationRunner`의 대상 store가 항상 `migration_guard`를 단다(run·rollback
  rehearsal 모두 `_target_store()`로). guard의 범위와 이유: migration의 **선언된 임무**는 사람이
  dry-run report로 검토하는 새 root에 legacy identity를 최초 구축하는 일이므로 PROJECT_PREMISE의
  최초 CREATE는 열고, constitution·authority·공개 이력 manifest·계보 mapping은 닫는다(ActorKind.MIGRATION은
  승인이 있어도 금지). 시험: 실제 legacy DB dry-run이 그대로 성공(premise 구축 허용 관찰) +
  같은 결선의 store에 constitution rule record를 넣으면 `PROTECTED_WITHOUT_APPROVAL`로 거부.
- **evolution** — `EvolutionManager`가 **기본으로** vault root guard를 달고(`write_guard=None`이면
  자동 결선 — 별도 전달이 없는 기존 호출처도 보호된다), draft 저장이 `open()` 직접 쓰기에서
  `_save_draft`(guard `assert_allowed`, channel=EVOLUTION, actor=EVOLUTION)로 바뀐다. skills/system-prompt
  draft는 보호 대상이 아니라 그대로 허용, 헌법 문서 경로로의 draft는 `ACTOR_FORBIDDEN`(사람 승인으로도
  열리지 않는다). vault root 밖 경로는 `PATH_ESCAPE`.
- **승인 발급** — `issue_human_approval`: 발급자는 사람 식별자만, **digest 결박 없는 승인은 발급
  단계에서 거부**(빈 digest 승인은 모든 쓰기에 재사용되는 면주). 발급 주체의 진위는 사용자 표면(P11)의
  몫으로 경계를 문서에 박았다.
- **승인 취소** — `guard.revoke(approval)`: 취소는 즉시 반영된다(만료 전 승인도 revoke 뒤 아무 쓰기를
  열지 않는다, `APPROVAL_REVOKED`). 취소 대상은 발급자·digest·개정 key로 특정한다.

### 이 회차가 잡은 결함 둘

- **enum identity 감사가 이 회차 자신의 위반을 잡았다**: `migration_guard`의 첫 구현이
  `protected_class is not ProtectedClass.PROJECT_PREMISE`(raw identity)로 써서
  `audit_enum_identity`가 즉시 위반 1건으로 게이트를 멈췄다 — `same_enum`으로 고쳤다(재발 감사 0건).
- **시험 결함

`tests/test_evolution.py::test_evolve_skill_not_found`는 `vault_path=MagicMock`이라 `skill_path.exists()`가
항상 참인데, 예전 구현의 `open(MagicMock)`이 우연히 TypeError를 내며 None을 반환해 **우연히** 통과했다.
draft 저장이 `write_text`로 바뀌며 우연이 사라져 드러났다 — 시험을 실경로(tmp_path)로 고쳐 의도(없는
스킬→None)를 보존했다.
