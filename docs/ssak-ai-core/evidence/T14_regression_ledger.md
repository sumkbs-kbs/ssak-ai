# T14 증거 — 전량 회귀 원장 (결정적 실패 vs seed 민감 실패)

`scripts/regression_ledger.py` · `tests/cognitive/test_regression_ledger.py` (23 시험) ·
`evidence/regression_ledger.json`(원장) · `scripts/architecture_review.py` 의 `regression_ledger` 검사.

작성 2026-09-23 · source head `codex/m1-task-events` (커밋하지 않은 트리, `docs/`+`scripts/`+`tests/` 편집분 포함).

## 1. 왜 이 카드가 필요했나

T14 회귀는 `N failed` 만 적어 왔고, 그 수가 회차마다 달랐다(94 → 10 → 7 → 5). 원인을 **측정 없이**
서술했다 — "순서 artifact", "random 순서 차이". 그러나 그 차이는

* 트리 자체가 회차 사이에 바뀌었고(다른 레인의 편집·문서 커밋),
* 수집 단계 오염(§1.1 ④ 의 import 시점 namespace purge)이 켜져 있었으며,
* 회차마다 **다른 선택**(`-p no:randomly` 유무)을 썼다

는 세 가지가 겹친 결과였다. 즉 이전 회차들의 숫자를 나란히 놓고 "차이는 순서 때문"이라고 말할 근거가
없었다. 그래서 회귀 수치를 **재현 가능한 방식으로 생산**하는 도구를 만들고, 그 산출물만 인용하기로 했다.

## 2. 방법 — 같은 scope 를 두 hash seed 로 돌려 집합을 비교한다

`scripts/regression_ledger.py`:

1. **scope** 를 정해 pytest 를 실행한다(`--extra` 로 선택을 넘긴다). 회차는 `PYTHONHASHSEED` 를
   **명시적으로** 박고(상속된 값에 기대지 않는다), junit XML(`--junitxml`)을 남긴다.
2. XML 만 읽는다 — **로그 문자열을 긁지 않는다**. `failure` 와 `error` 를 모두 빨강으로 세고,
   `skipped`/`xfail` 은 빨강이 아니다.
3. scope 안에서 회차들의 **교집합 = 결정적 실패**, **대칭차 = seed 민감 실패** 로 나눈다.
   scope 가 섞이면 없던 "결정적"이 생기므로 판정은 **scope 단위**다.
4. 결정적 실패에 **소유자**(레인·사유)를 붙인다. 분류표에 없으면 `unowned` 로 남고 `--gate` 가 실패한다.
5. **중단된 회차는 판정에서 뺀다**(§5) — 끝까지 돌지 않은 회차의 "안 나온 실패"는 통과가 아니다.

긴 suite 를 한 호출에 돌릴 수 없는 환경이므로 scope 를 나눠 여러 번 호출하고, 마지막에
`--from-junit` 으로 **재실행 없이** 원장을 합친다. 원장 JSON 에는 scope·seed·junit 경로·빨강 목록·
소유자·명령이 남는다.

## 3. 관찰 — 두 seed 의 실패 집합이 **완전히 같다** (drift 0)

```
$ for scope in flat-001-080 flat-081-220 flat-221-314 flat-315-338 flat-339-380 \
               flat-381-408 flat-409-456 flat-457-502 ; do
    .venv/bin/python scripts/regression_ledger.py --run 2 --scope $scope ... ; done
$ .venv/bin/python scripts/regression_ledger.py --from-junit .regression-ledger --gate
```

| scope | 파일 선택 | 회차 | 수집(합) | 빨강(합) | 결정적 | seed 민감 |
|---|---|---|---|---|---|---|
| flat-001-080 | 1~80 | 2 (101·202) | 2048 | 0 | 0 | 0 |
| flat-081-220 | 81~220 | 2 | 3720 | 4 | 2 | 0 |
| flat-221-314 | 221~314 | 2 | 2572 | 6 | 3 | 0 |
| flat-315-338 | 315~338 | 2 | 692 | 0 | 0 | 0 |
| flat-339-380 | 339~380 | 2 | 1352 | 0 | 0 | 0 |
| flat-381-408 | 381~408 | 2 | 1454 | 0 | 0 | 0 |
| flat-409-456 | 409~456 | 2 | 1572 | 2 | 1 | 0 |
| flat-457-502 | 457~502 | 2 | 1262 | 10 | 6 | 0 |
| subdirs | `tests/cognitive`·`curriculum`·`evals` | 2 | 798 | 0 | 0 | 0 |
| **합계** | **502 + 3 구간** | **18** | **—** | **—** | **11** | **0** |

**회차별 `failed` 수도 동일하다**(예: flat-221-314 는 두 회차 모두 `3 failed, 1283 passed`). 즉 이
체크아웃에서 **hash seed 를 바꿔도 빨간 집합이 움직이지 않는다** — 회차 사이의 차이는 seed 탓이 아니었고,
그 서술은 이 원장으로 **대체**한다.

결정적 실패 11건(전부 소유자 있음 · `unowned` 0):

| 실패 | 건수 | 소유자 | 관찰 |
|---|---|---|---|
| `test_cr14_fence_movement_detection.py` | 2 | cr14-lane | git 이력: 선언 후보 뒤 코드 스코프 커밋 이동 · HEAD 트리 지문 ≠ 선언값 |
| `test_nx07_doc_consistency.py` | 2 | release-owner | EX-05 대장 행의 지표/귀속 두 단계 분리(오너 판정 브리프 §5 B) |
| `test_model_registry.py` | 1 | config-owner | 번들 기본값 ≠ 저장소 `config.yaml` |
| `test_ws01_project_binding.py` | 5 | ws01/cr01-lane | `ConversationStorageMigrationRequiredError` — 이 체크아웃의 대화 저장소가 v2 마이그레이션 전(단독 실행으로 재현) |
| `test_trn02_timeout_resource.py` | 1 | trn02-lane | 학습 job cancel API `ok=False`(단독 실행으로 재현) |

ws01·trn02 6건은 **이전 회차의 5건 기준선에 없던 항목**이다. 같은 트리에서 단독 실행해도 재현되므로
(6 failed / 32 passed) 회차 조건 탓이 아니고, 원인 signature(`vault_data`·대화 저장소 상태, training job
API)는 이 카드가 건드리는 파일이 아니다. 그래도 "무관하다"고 단정하지 않고 **레인 이름을 붙여 원장에
남겼다** — 원장은 누가 처리할지를 말하는 문서이지, 통과 선언이 아니다.

## 4. 이빨 — 원장 자체를 시험한다

`tests/cognitive/test_regression_ledger.py` (23 시험) 는 판독·분리·귀속·게이트가 **실제로 무는지**를 본다.

| 시험 | 무엇을 고정하나 |
|---|---|
| 실제 junit 형태 판독 | 루트 `<testsuites>`·`classname`/`name` 에서 파일·class·시험 이름을 복원(파일을 못 찾으면 dotted 이름 유지) |
| `failure` + `error` | 둘 다 빨강, `skipped` 는 아님 |
| 한 회차만 실패 | 교집합이 아니라 **대칭차**로 간다 |
| scope 분리 | scope 가 다르면 교집합하지 않는다(없던 결정적 실패 방지) |
| 한 회차 scope | `incomplete` 로 남고 게이트가 실패한다(seed 가 겹친 두 회차도 같다) |
| 분류표 | 없는 파일을 가리키면 실패 · 사유가 문장이어야 한다(레인 이름만으로는 근거가 안 된다) |
| 게이트 | 무소유 결정적 실패 · 중단 회차 · 허용치 초과 drift 를 각각 실패로 만든다 |
| 산출물 | `--from-junit` 이 이름 규약 밖 XML 을 섞지 않는다 · 없으면 멈춘다 |
| seed 고정 | `run_once` 가 `PYTHONHASHSEED` 를 명시하고 scope 선택을 pytest 인자에 싣는다 |

리뷰 쪽(`tests/cognitive/test_architecture_review.py`)은 원장 JSON 계약을 시험한다 — artifact 부재 ·
scope 없는 원장 · 한 회차 scope · 무소유 결정적 실패를 각각 거부하고, 마커 5종(scope·회차·결정적·
drift·무소유)이 원장의 실제 값과 일치하는지 확인한다.

## 5. 중단된 회차 — 실측과 처리

`flat-081-220` 의 seed 202 회차가 **중간에 끝났다**. junit 에 `tests="1078"`(다른 회차는 1860)로 남고,
로그 마지막은

```
File ".../_pytest/config/__init__.py", line 254, in _console_main
    sys.stdout.flush()
OSError: [Errno 9] Bad file descriptor
```

였다. 즉 어떤 시험이 **stdout fd 를 닫아** pytest 가 종료 시 flush 에서 죽었다. 중단 직전까지 기록된
마지막 파일은 `tests/test_evolution.py` 였고(그 시험들은 통과로 기록됨), 같은 slice 를 두 번 더 돌렸을
때는 정상 종료했다(두 회차 모두 `2 failed, 1837 passed`).

**처리**: 원장은 `<testcase classname="pytest" name="internal">` 를 **중단 표시**로 읽고, 그 회차가 있는
scope 는 `aborted` 로 남겨 **판정에서 제외**한다(`--gate` 도 실패한다). 부분 회차의 빨강 집합을
"결정적 실패"로 세면 안 나온 실패가 통과처럼 보이기 때문이다. 중단된 회차는 같은 명령으로 다시 돌려
덮어쓴다(`--seeds 202` 로 한 회차만 재실행). 최종 원장에는 중단된 회차가 없다(`aborted_scopes: []`).

fd 원인 조사도 했다: `os.close`/`os.dup2`/`os.closerange` 를 감시하고 시험마다 fd 0/1/2 유효성을
`os.fstat` 로 확인하는 임시 plugin(`/tmp/fdprobe.py`)을 붙여 60파일 구간(670 시험)을 돌렸으나
**깨진 fd 를 잡지 못했다**(그 구간에서 재현되지 않음). 원인 시험은 특정하지 못했고, 그 사실을 한계로
남긴다(제품 코드 결함이라는 증거는 없다 — 회차 중단은 pytest 종료 경로에서 발생한다).

## 6. 한계

* **scope 안의 순서만** 비교한다. `tests/test_*.py` 502개를 8구간으로 나눠 돌렸으므로
  **구간 사이의 수집 순서 효과**는 이 원장이 재지 않는다(구간 경계에서 module 이 먼저·나중에 import 되는
  차이는 남는다). §1.1 ④ 의 오염 부류는 구간 안에서 재현되지 않았다.
* 502개를 한 호출에 돌릴 수 없어 **두 seed 를 한 프로세스 쌍으로** 재지 못했다(§2 의 분할 실행).
* `test_ws01_project_binding.py`·`test_trn02_timeout_resource.py` 6건은 원인을 **다른 레인 이름으로만**
  귀속했다 — 그 레인의 수리 여부는 여기서 확인하지 않는다.
* 원장은 특정 source head·체크아웃 상태의 관찰이다. 다음 회차에 트리가 바뀌면 수치도 바뀌고, 마커가
  어긋나면 `architecture_review` 가 실패한다(그게 의도다).
