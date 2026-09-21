# FlyWire FAFB v783 (Princeton thresholded) — 연구 dataset card

이 문서는 **원자료 D**(`/Users/mr.k/program/fly`, 읽기 전용, 약 16.6 GB)를 Ssak-Ai 연구에서
어떻게 읽는지를 고정한다. 원자료와 파생물은 **제품 패키지·Git 에 들어가지 않는다**
(`.gitignore`). 여기 남는 것은 코드·기대치·증거다.

- 소유: S(`research/flywire/`) · D 는 읽기 전용
- release: `fafb_v783` (FlyWire public release 783, 2023-10 스냅숏)
- 라이선스: **CC BY-NC 4.0** — 비상업 연구 전용, 출처 표시 필요
  ([FlyWire guidelines](https://home.flywire.ai/guidelines), 2026-09-21 조회)
- 출처 표시: FlyWire Consortium / Princeton Neuroscience Institute,
  [Nature 2024 연결망 논문](https://www.nature.com/articles/s41586-024-07558-y) 인용 지침을 따른다.

## 1. 어떤 표를, 어떤 규칙으로 쓰는가

| 역할 | 파일 | 비고 |
|---|---|---|
| 노드 | `neurons.csv.gz` | 139,255 고유 root_id(64bit 정수) |
| 주석 | `classification.csv.gz` | class/super_class/sub_class |
| 교차 주석 | `consolidated_cell_types.csv.gz` | `primary_type` — 세포군 주장의 **두 번째 출처** |
| 연결 | `connections_princeton.csv.gz` | **thresholded** Princeton 만 |
| skeleton | `sk_lod1_783_healed.zip` | 139,273 항목(neuron 대비 +18, 누락 0) |

규칙(계약):

1. **표 혼합 금지.** `connections_princeton_no_threshold.csv.gz`(22,285,323행)와
   `connections_buhmann_no_threshold.csv.gz`(16,847,997행)는 별도 데이터셋이다. 한 그래프로
   합치지 않는다. thresholded 표의 서명은 "pair 합 최소 5" — pair 합이 5 미만인 pair 가
   존재하면 그 표는 다른 표다(exit 7).
2. **neuropil 행 → pair 합산.** 5,342,446행이 3,732,460 pair 로 합쳐지고 synapse 총합은
   50,666,648 이다. **행 최소 syn(=1)과 pair 최소 합(=5)을 혼동하지 않는다.**
3. **미상 NT 는 보존한다.** `nt_type` NULL 19,658 · `nt_type_score` < 0.5 28,991 을
   평균·대체값으로 채우지 않는다. 연결의 흥분/억제 **부호를 추정하지 않는다** —
   `syn_count` 는 관측 강도 지표이지 학습된 가중치가 아니다.
4. **행 순서 독립.** 정렬된 root_id→index 매핑의 sha256 을 manifest 에 남긴다. 같은 데이터의
   두 덤프(행 순서만 다름)는 같은 해시를 낸다.
5. **원본이 바뀌면 새 dataset version.** 입력 해시는 **승인 실행**이 찍고, 한 바이트라도
   다르면 exit 6 이다. 승인에는 사유가 필요하고, 참조 수치가 통과하지 않은 실행은
   승인할 수 없다.

## 2. 세포군 — 주장할 수 있는 것과 없는 것

세포군은 **class 컬럼으로만** 정의한다(label 이름이나 root_id 크기로 추정하지 않는다).
그리고 두 번째 출처(`consolidated_cell_types.primary_type`)로 검증한다.

| 집단 | class | 수 | 교차 출처 | 상태 |
|---|---|---:|---|---|
| ALPN | `ALPN` | 685 | 해소 594/685(86.7%) · 일치 100% | **CONFIRMED** |
| Kenyon_Cell | `Kenyon_Cell` | 5,177 | 해소 5,177/5,177 · `^KC` | **CONFIRMED** |
| MBON | `MBON` | 96 | 해소 96/96 · `^MBON` | **CONFIRMED** |
| MBIN | `MBIN` | 4 | primary_type = `APL`/`DPM` | **INCONCLUSIVE** |

- ALPN 의 91명(13.3%)은 교차 출처에 이름이 없다(`CB####` 자리표시자). 그래서 mask 에서
  빼지 않고, **그 endpoint 를 지나는 edge 수를 보고**한다(PN→KC 에서 13건). 근거 없는
  제거는 그래프를 조용히 줄이는 일이다.
- MBIN 은 두 주석이 **다른 어휘**(class=MBIN vs primary_type=APL/DPM)를 쓴다. 어휘 대응은
  주석 문서/사람 확인이 필요하므로 회로 mask 의 근거로 삼지 않는다 — `KC_to_MBIN` mask 는
  만들되 `INCONCLUSIVE` 로 표시한다. **미실행 실험을 성공으로 위장하지 않는다.**

## 3. 회로 mask (2026-09-21 실행)

| 회로 | pairs | rows | synapses | pre/post node | 미해소 endpoint edge | 상태 | sha256(앞 16) |
|---|---:|---:|---:|---|---:|---|---|
| `PN_to_KC` | 22,298 | 22,569 | 366,946 | 285 / 4,750 | 13 | CONFIRMED | `b346975237504917` |
| `KC_to_MBON` | 26,937 | 49,236 | 226,932 | 5,146 / 84 | 0 | CONFIRMED | `13987e1600c3a3c4` |
| `KC_to_MBIN` | 10,246 | 48,022 | 254,835 | 5,177 / 4 | 10,246 | INCONCLUSIVE | `cdc9d47dc5fd1394` |

mask 는 `(pre_root_id,post_root_id,syn_count)` 를 **정렬해서** 쓴다(재현 가능). `pairs` 와
`rows` 를 함께 재는 이유는 위 규칙 2 다. 같은 입력·같은 명령을 두 번 돌리면 세 CSV 의 sha256 이
바이트 단위로 같다(2026-09-22 확인).

"미해소 endpoint edge"의 정의를 정확히 적어 둔다 — 이 수치는 **"원자료에 없는 ID"가 아니라**
"교차 출처 근거가 **선언되지 않은** 집단을 지나는 edge"의 수다. ALPN 은 해소 86.7% 라
PN→KC 13건이 남고(§2), MBIN 은 선언 패턴이 `[]` 이므로 `unresolved_members` 가 구성원 전부를
돌려주어 KC_to_MBIN 의 이 값이 `pairs` 와 같아진다(10,246). 즉 이 수치가 큰 것은 "데이터가
깨졌다"가 아니라 "그 집단에 대한 주장을 이 릴리스의 주석으로는 세울 수 없다"는 뜻이며,
그래서 같은 회로가 `INCONCLUSIVE` 다. mask 자체는 줄이지 않는다.

## 4. 실행 방법

원자료 D 는 저장소 밖이다. 연구 의존성은 스크립트별 PEP723 lock 으로 고정한다
(`validate_dataset.py.lock`, `extract_circuits.py.lock` — duckdb 1.5.5).

```bash
# 1) 검증(읽기 전용) — 기대치·해시·수치·skeleton·세포군을 모두 잰다
uv run research/flywire/validate_dataset.py \
  --data-root "$D" --output <E>/task-25/manifest.json

# 2) 입력 해시 승인 — **참조 수치가 통과한 실행에서만**, 사유 필수
uv run research/flywire/validate_dataset.py \
  --data-root "$D" --output <E>/task-25/manifest.json \
  --approve-hashes --reason "<왜 이 입력을 고정하는가>"

# 3) 회로 mask 추출 (기본 reader=duckdb, 원자료에서 4.6초)
uv run research/flywire/extract_circuits.py \
  --data-root "$D" --out-dir <E>/task-25/artifacts/circuits \
  --output <E>/task-25/circuits.json

# 4) 계약 시험(원자료 불필요 — fixture 는 생성물이다)
uv run --frozen python -m pytest tests/test_ssak_flywire_dataset.py
```

exit code 는 계약 숫자다: `0` PASS · `2` 입력 부재 · `3` 스키마(정수 아님 ID) · `4` 중복 edge ·
`5` FK 누락 · `6` release/입력 변경 · `7` 표 혼합 · `8` 수치 불일치 · `10` 회로 INCONCLUSIVE.

## 5. 정직한 한계

- 이 카드의 수치는 **관측치**다. "생물학적 전체 세포 수"나 "연결이 곧 지능"이라는 주장이 아니다.
- `syn_count` 는 관측된 시냅스 수 합이다. 부호·시간·수용체·가소성은 이 자료로 결정되지 않는다.
- skeleton(+18)은 런타임에 쓰지 않는다. 형태 분석이 필요할 때만 쓰는 별도 입력이다.
- 회로 mask 는 그래프 수준 대조 실험의 **입력**이다. 이 mask 자체가 성능 개선의 증거는 아니다
  (그 판정은 task 28, 제품 반영은 task 29 — 기본 off feature flag).
- 원자료 재배포는 허용되지 않는다(CC BY-NC 4.0). 파생 mask 도 비상업 연구 범위를 넘지 않는다.
