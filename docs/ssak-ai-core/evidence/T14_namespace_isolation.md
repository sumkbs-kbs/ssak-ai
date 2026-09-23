# T14 증거 · import 시점 namespace 오염의 제거 (수집 순서 의존성)

T14 회귀가 **오염원으로 기록만 남겼던** 항목(`ARCHITECTURE_REVIEW.md` §1.1 ③ 뒤의 "오염원")을 이번에 재현·수정·고정했다.
이 문서는 "왜 그것이 결함이며, 고친 뒤에도 미러 리허설의 이빨이 살아 있는가"를 관찰로 남긴다.

- source head: `79582ccd` (branch `codex/m1-task-events`)
- 검증 환경: 이 체크아웃의 `.venv` (`pytest 8.x` · `ruff` · `mypy`)

## 0. 무엇이 문제였나

`tests/test_flush_budget_contract.py` 는 **import 시점에** `sys.modules` 에서 `antigravity_k.*` 를 전부 지운다.

```python
for name in [key for key in list(sys.modules) if key.startswith("antigravity_k")]:
    del sys.modules[name]
```

의도는 정당하다 — nx10 미러 리허설이 **미러 트리의 바이트**를 검사하게 만들려면 트렁크에서 이미 import 된 module 을
버려야 한다(그러지 않으면 조용히 옛 바이트를 검사한다). 문제는 이 파일이 **승격되어 `tests/` 에 있고**, pytest 가
실행 전에 모든 시험 module 을 **수집(import) 단계**에서 읽는다는 점이다. 그 순간:

1. 먼저 import 된 시험 파일은 **옛 class 객체**를 잡고,
2. 뒤에 import 되는 module 은 같은 이름으로 **새로 만들어져** 다른 객체가 되고,
3. 서로 다른 객체가 만나면 `is` 비교가 거짓이 된다 — `ARCHITECTURE_REVIEW.md` §1.1 ①에서 유효한 grant 가
   `NOT_GRANTED → DEFER` 로 떨어진 그 부류다.

즉 **판정이 실행 순서에 따라 달라진다**. 이것이 "기록만" 하고 넘어갈 수 없는 이유다.

## 1. 재현 (고치기 전 · RED)

`tests/test_aa_purge_probe.py`(임시 진단, 수집 순서 `test_aa*` → `test_flush*`)를 두고 두 파일만 순서대로 돌렸다.
앞 파일의 module 본문이 먼저 돌아 `authority.AuthorityProfile` 을 잡고, 뒤 파일이 namespace 를 지운 뒤,
시험 실행 시점의 fresh import 가 새 객체를 만든다.

```
$ .venv/bin/python -m pytest tests/test_aa_purge_probe.py tests/test_flush_budget_contract.py -q -p no:randomly
F.........
>       assert authority_after is BEFORE_MODULE, "module 객체가 갈라졌다(같은 이름 · 다른 객체)"
E       AssertionError: module 객체가 갈라졌다(같은 이름 · 다른 객체)
1 failed, 9 passed in 2.29s
```

## 2. 수정 — purge 를 **미러 리허설에서만** 하도록 조건화

세 파일을 같은 형태로 고쳤다. 리허설의 이빨(옛 바이트 버리기)은 그대로 두고, **조건 없이 비우는 성질만** 없앴다.

```python
TREE_ENV = "NX10_FLUSH_TREE"
...
# 다른 트리를 검사할 때 이전 임포트가 남아 있으면 조용히 옛 바이트를 검사한다(승격 때 실제로 겪은 부류).
# 그래서 비우는 것은 **미러 리허설에서만** 한다 — 이 파일은 승격 뒤 `tests/` 에서 일반 suite 와 함께 수집되므로,
# 조건 없이 비우면 아직 import 되지 않은 module 이 나중에 같은 이름으로 다시 만들어져 class identity 가 갈라진다.
if os.environ.get(TREE_ENV):
    for name in [key for key in list(sys.modules) if key.startswith("antigravity_k")]:
        del sys.modules[name]
```

| 파일 | 위치 | sha256 | 비고 |
|---|---|---|---|
| `tests/test_flush_budget_contract.py` | 승격본(tracked) | `742e02d3f0…` | 일반 suite 가 수집하던 파일 — 오염의 실체 |
| `docs/qa/2026-09-16-followup/nx10/fsync/test_flush_budget_contract.py` | staged 쌍둥이(untracked) | `742e02d3f0…` | 승격 계약(`apply_flush_batch.sh` 가 `cp`)에 맞춰 **바이트 동일** 유지 |
| `docs/qa/2026-09-16-followup/nx10/fsync2/test_view_freshness_contract.py` | staged(untracked) | `9b629dc06b…` | 같은 부류(F2 · `NX10_VIEW_TREE`) — 승격 전에 같이 고쳤다 |

수정 뒤 재현은 GREEN 이다(임시 진단은 확인 뒤 삭제했다).

```
$ .venv/bin/python -m pytest tests/test_aa_purge_probe.py tests/test_flush_budget_contract.py -q -p no:randomly
..........                                                               [100%]
10 passed in 0.52s
```

이번에 추가한 검사기·시험:

| 파일 | sha256 |
|---|---|
| `scripts/audit_test_namespace_purge.py` | `730fca68f6828ddf…` |
| `tests/cognitive/test_module_namespace_isolation.py` | `57e9565df0e44230…` |

세 계약 시험 파일은 **미러 리허설로 검사하는 파일**이므로 승격본과 staged 쌍둥이의 바이트가 같아야 한다는 계약을 그대로
유지한다(위 표의 두 `742e02d3f0…`). 수정한 tracked 파일은 `tests/test_flush_budget_contract.py` 하나이고,
`docs/qa/...` 의 두 파일과 새 감사·시험은 untracked(신규)이다.

## 3. 재발 방지 — 감사(게이트)와 계약 시험

문서 규율이 아니라 **실패하는 검사**로 고정했다(`scripts/audit_test_namespace_purge.py`,
`tests/cognitive/test_module_namespace_isolation.py` 5건).

감사는 수집 대상 시험 파일(`tests/**` · `docs/qa/**` 의 `conftest.py` · `test_*.py`)을 AST 로 읽어,
**module 수준**에서 `sys.modules` 를 지우는 문장이 **환경변수 조건으로 감싸이지 않았으면** 위반으로 본다.

| 입력 | 판정 | 왜 |
|---|---|---|
| `for …: del sys.modules[name]` (module 수준) | **위반** (삭제 줄 번호) | 수집 단계에서 남의 import 결과를 바꾼다 |
| `if os.environ.get("NX10_…_TREE"): for …: del …` | 통과 | 미러 리허설의 정당한 형태 |
| 함수 본문 안의 `sys.modules.pop(…)` | 통과(범위 밖) | 실행 시점 — 수집 단계가 아니다 |
| `del sys.modules["x"]` · `sys.modules.pop(…)` · `sys.modules.clear()` | 위반 | 문장 자체가 purge 인 형태도 문다 |
| comprehension 조건이 다른 namespace | **위반**(보수적) | 조건을 평가하지 않는다 — 어느 namespace 든 지우면 남의 import 가 달라진다 |

행위도 함께 고정했다(순서에 기대지 않는다). 별도 인터프리터에서 승격된 계약 시험을 import 하며 관찰한 값:

| 상황 | `antigravity_k.engine.cognitive.authority` | 심어 둔 다른 module | 계약 |
|---|---|---|---|
| override 없음(승격 위치 · 일반 suite) | **유지** | **유지** | 판정이 순서에 흔들리지 않는다 |
| `NX10_FLUSH_TREE=<다른 트리>` | 버려짐 | 버려짐 | 미러 리허설의 이빨이 살아 있다 |

```
$ .venv/bin/python scripts/audit_test_namespace_purge.py
import 시점 namespace purge 없음 (수집 대상 시험 파일 전체)   # exit 0
$ .venv/bin/python -m pytest tests/cognitive/test_module_namespace_isolation.py -q -p no:randomly
5 passed
$ .venv/bin/python -m pytest tests/test_flush_budget_contract.py -q -p no:randomly
9 passed
$ .venv/bin/python -m pytest tests/test_flush_budget_contract.py tests/cognitive -q -p no:randomly
367 passed      # 계약 시험이 먼저 import 되는 순서에서도 cognitive 전건 통과
$ .venv/bin/python -m ruff check src/ tests/ scripts/   # All checks passed
$ .venv/bin/python -m ruff format --check src/ tests/ scripts/   # 1166 files already formatted
$ .venv/bin/python -m mypy scripts/audit_test_namespace_purge.py tests/cognitive/test_module_namespace_isolation.py \
    scripts/architecture_review.py   # Success: no issues found in 3 source files
```

## 4. 리허설 무회귀 — 이빨이 여전히 무는가

수정이 리허설을 무디게 만들었는지가 이 작업의 핵심 위험이다. nx10 flush 미러 리허설을 **그대로** 돌렸다.

```
$ bash docs/qa/2026-09-16-followup/nx10/fsync/rehearse_flush.sh
  [INFO] 창 재구성 — 트렁크가 F1 이후라 두 파일을 이력(29baaa8f^)에서 되돌렸다
  [INFO] 사전 이미지 확인 — 두 파일 해시가 패처의 기대와 일치한다
  [PASS] 적용 전 계약 시험 실패(3 failed) — 이빨이 문다
  [PASS] 적용 뒤 계약 시험 통과(9 passed)
  [PASS] 검사 대상이 미러의 src 다(…/nx10-flush-rehearsal-…/src/antigravity_k/engine/conversation_journal.py)
  [PASS] 기존 시험 무회귀(70 passed)
  [PASS] 돌고 있는 soak 을 만나면 exit 9(실제 exit=9)  ·  PERF 미승격 트리 exit 6
  [PASS] 사전 이미지가 다르면 검사가 실패한다  ·  본 트리 무변경(sha256 전후 동일)

=== 결과: PASS 17 · FAIL 0 ===
ALL PASS — 미러 정리 완료(본 트리 쓰기 0건)
```

`P1` 의 **3 failed(빨강)** 는 이 시험이 사전 이미지에서 실제로 무는 증거이고, `P2` 의 **9 passed(초록)** 는 패치 뒤
계약 충족의 증거다. 즉 조건화는 "리허설에서만 purge" 라는 의도를 보존했고 트렁크에서는 namespace 를 건드리지 않는다.

## 5. 전체 회귀 (전/후 대조)

명령은 이전 회차와 같게 두고(`-m 'not slow and not benchmark'`), 결과를 세 번 관찰했다.

| 회귀 | 명령 | 관찰 |
|---|---|---|
| ① 수정 전 | `.venv/bin/python -m pytest tests/ -m 'not slow and not benchmark' -q` | 7723 수집 · **94 failed / 7571 passed / 14 skipped / 20 xfailed** (26:31) |
| ② 수정 후 | 같은 명령 | 7726 수집 · **10 failed / 7660 passed / 14 skipped / 24 deselected / 20 xfailed** (21:38) |
| ③ **고정 순서** | 같은 명령 + `-p no:randomly` | 7726 수집 · **7 failed / 7663 passed / 14 skipped / 24 deselected / 20 xfailed** (21:21) |
| ④ **고정 순서 · 정리 뒤** | 같은 명령 + `-p no:randomly` | 7726 수집 · **5 failed / 7666 passed / 14 skipped / 24 deselected / 20 xfailed** (20:13) — ③의 7건 중 둘(미등록 실행 경로·조용한 스킵)을 등록으로 닫은 뒤 |
| ③-1 중단 회차 | 같은 명령 + `-p no:randomly`(첫 시도) | **31%에서 중단(exit 120)** — `engine/rag_indexer.py` 가 `OSError: [Errno 9] Bad file descriptor` |

**②가 좋아진 것은 이 수정의 효과가 아니다** — pytest-randomly 의 순서가 달라졌기 때문이다(브라우저·diff·API 인증·ctx/cr
게이트 실패는 suite 순서에서 오는 artifact라는 사실이 이전 회차에 이미 관찰되어 있다). 이 비교로 말할 수 있는 것은 두 가지다.

1. ②의 실패 10건은 전부 이전 회차 클러스터의 기존 항목이다 — `tests/cognitive/test_architecture_review.py` 3건(이 작업이
   만든 문서 `measured` 마커 미갱신 → 갱신 뒤 0), `test_cr14_fence_movement_detection.py` 2건,
   `test_cr14_gate_skip_register.py` 1건, `test_model_registry.py` 1건, `test_nx07_doc_consistency.py` 2건,
   `test_tool_sandbox_coverage.py` 1건.
2. 이 수정이 만든 **새 실패는 0건**이다(cognitive 마커 3건은 문서를 갱신해 닫았다).

이 카드에서 추가한 5건을 포함해 `tests/cognitive -q` 는 **358 passed** 이고, `scripts/architecture_review.py` 는
8 checks PASS(`artifact 161 · 상대 link 161 · evidence 15문서 고아 0 · measured 마커 9종 일치 · 수집 358`)이다.

③(고정 순서)의 실패 7건은 **전부 이 작업 밖**이고, 그 5개 파일을 단독 실행해도 같은 7건이 재현된다
(`86 passed / 7 failed` · `-p no:randomly` · 46초). 그중 둘은 T14 정리에서 등록으로 닫아 **④는 5건**이며,
닫은 근거와 방식은 `ARCHITECTURE_REVIEW.md` §1.3 에 있다(`tools/ssak_bundle_store.py` 를 `FIXED_ARGV` 로 등록,
`dashboard/e2e/ssak-web-integration.spec.ts` 의 조건부 skip 을 조건 토큰·owner·재검토 기한과 함께 등록).

| 실패 | 건수 | 관찰된 원인 | 왜 이 작업과 무관한가 |
|---|---|---|---|
| `test_cr14_fence_movement_detection.py` | 2 | 선언 후보 커밋 뒤에 코드 스코프 커밋이 움직였고, HEAD 트리 지문이 선언값과 다르다 | 두 시험은 **git 커밋 객체**(후보 vs HEAD)를 비교한다 — 나는 커밋을 만들지 않았다 |
| `test_cr14_gate_skip_register.py` | 1 | `dashboard/e2e/ssak-web-integration.spec.ts:191` 의 skip 마커가 등록부에 없다 | dashboard 소스는 건드리지 않았다 |
| `test_model_registry.py` | 1 | 번들 `config.yaml` 에 저장소 설정의 `search:` 절이 없다 | config 는 다른 작업자가 편집 중인 파일이다 |
| `test_nx07_doc_consistency.py` | 2 | `docs/20_CURRENT_STATUS.md`·CR-14 대장의 **기준선 자체가 이미 위반**(EX-05 상태 셀) | 기존 문서 기준선 (이전 회차에 이미 분리) |
| `test_tool_sandbox_coverage.py` | 1 | `tools/ssak_bundle_store.py` 의 `subprocess.run` 이 ALLOWLIST 미등록 | 기존 항목 |

> 순서 민감성 자체는 남아 있다 — ①②③이 94 / 10 / 7 failed 로 갈렸다. "이전 실패와 동일"을 고정 baseline 으로
> 주장하지 않고 가장 보수적인 값(③의 7건)을 기록한다. 이 수정이 닫은 것은 **원인 하나**다.

### 5b. 중단 회차(③-1)의 추적 — fd 를 누가 닫았나

③-1 의 중단을 그냥 "환경 문제"로 두지 않고 추적했다. plugin 으로 **수집 종료 시점에 열려 있던 fd** 를 기준선으로
잡고 시험마다 `os.fstat` 으로 남은 fd 를 대조했다(macOS 의 `/dev/fd` 목록은 닫힌 slot 도 포함해 오탐이 난다 — 실측).

| 관찰 | 값 |
|---|---|
| 고정 순서 전량 회귀 재실행 | **2회 모두 정상 종료**(각 7 failed) — ③-1 은 재현되지 않았다 |
| 탐지된 fd 손실 | **1건** — `test_worktree_manager.py::TestInit::test_uses_existing_worktrees_dir` 에서 `fd=10` |
| 그 fd 의 정체 | `/dev/null` (ino 336 · `crw-rw-rw-`) 의 중복 — pytest capture 기계가 쓰는 자원 |
| 제품 code 가 잃은 fd | **0건** |

즉 중단은 제품 결함이 아니라 **회차성 artifact** 이며, 그 뒤 고정 순서 회귀는 돈다. 그래서 리뷰 §6 의 "고정 순서 불가"
문장을 이 관찰로 대체했다(그 한 회차의 중단 사실 자체는 지웠지 않고 기록으로 남긴다).

## 6. 한계

- 감사는 **파일 이름**(`conftest.py` · `test_*.py`)과 `tests/` · `docs/qa/` 만 본다. 다른 경로의 module 이 pytest 로
  수집되는 구조가 생기면 감사 범위를 함께 넓혀야 한다.
- **함수 본문 purge** 는 범위 밖이다(실행 시점이라 수집 단계가 아니다). 시험 안에서 `sys.modules` 를 비우고
  복원하는 형태가 실패하면 그것은 별개의 문제다 — 이 감사가 잡지 않는다.
- 순서 의존은 **사라지지 않았다**. `tests/test_cr14_*.py` 류처럼 `module_from_spec` 으로 **경로에서 module 을 다시
  load 하는** 시험(같은 이름의 객체가 둘 생긴다)이나
  plugin 이 만든 중복 객체는 `same_enum`(§1.1 ③) 과 이 조건화로 **막은 것**이지, "같은 module 이 두 번 로드될 수
  있다"는 사실 자체를 없앤 것은 아니다.
- 이 문서의 전체 회귀 값은 이 체크아웃에서의 관찰이며, 같은 시각 다른 thread 가 suite 를 함께 돌린 상태였다
  (§5 의 조건 참조). CI 값과 같다고 주장하지 않는다. 이 머신에는 이틀 전 시작해 77%에서 멈춘 다른 pytest 프로세스도
  남아 있었다(CPU 0% · RSS 약 5GB) — 그런 조건까지 배제하지는 못한다.
- §5b 의 fd 추적은 **열린 fd 수준**의 관찰이다. "누가 닫았는지" 를 코드 위치까지 확정한 것이 아니라, **제품 code 가
  fd 를 잃지 않았다**는 것과 중단이 재현되지 않는다는 것까지 확정했다. 같은 signature 가 다시 보이면 이 plugin 방식으로
  다시 추적한다.

## 7. 남은 것

- `docs/qa/.../fsync2/probe_view_throttle_benefit.py` 는 트리를 바꿔가며 재는 단독 probe 이고 **함수 안에서** purge 한다
  (수집 대상 아님). 그대로 두었고, 이 선택을 감사의 경계로 문서화했다.
- fsync2(view 신선도) 계약 시험은 아직 승격되지 않았다(`patch_view_freshness.py --check` exit 0 = 트렁크가 사전 이미지).
  승격 시 이 파일은 이미 조건화된 형태로 올라간다.
- 사람 결정·실환경 항목(P11 대화 QA · destructive migration · live pilot · 리뷰 승인)은 이 문서의 범위 밖이다.
