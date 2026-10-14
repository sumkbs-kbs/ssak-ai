# CR-14 외부 조건(EX-01~06) 실행 대장

- 시작: 2026-09-15 06:44 UTC+09:00
- 담당: 강병석 (겸직)
- 코드 후보: `b6003205365606407cadfd6cbb1c813110beef0f`
- 지문: `02349a8d06945e438bdc60799ed770a87d6bb67d33d27f09b52008d242536ed6`
- 증거 루트: `.omo/evidence/commercial-reliability/CR-14/ex-2026-09-15/` (gitignore)
- **비밀값·토큰·PIN 원문은 이 문서와 증거에 넣지 않는다.**

## EX-05 측정 전 임계값 (측정 시작 전 고정 — 종료 후 조정 금지)

VAL-02 계승 (`scripts/val02_staging.py`):

| 항목 | 임계값 |
|---|---|
| soak 요청 시간 | **28800초 (8시간)** |
| P95 latency | ≤ 500 ms |
| P99 latency | ≤ 1000 ms |
| error rate | ≤ 0 (CAS loser는 정상) |
| FD leak | ≤ 5 |
| RSS growth | ≤ 64 MB |
| 조기 종료 | 실측 < 요청×0.9 이면 FAIL |

결정 ID: `EX-05-THRESHOLDS-2026-09-15` · 출시 책임자 강병석.

## EX-06 범위 결정

- 결정: **최초 GA 범위를 local-only로 축소하지 않는다** (변경 요청 없음 유지).
- cloud provider 주장은 EX-01·EX-02 근거가 있을 때만 허용. 없으면 지원표 Experimental 유지.
- 결정 ID: `EX-06-NO-SHRINK-2026-09-15`.

## 실행 상태 (갱신)

| ID | 목표 | 상태 | 근거 |
|---|---|---|---|
| EX-01 | 마케팅 대상 provider 실호출 | **PARTIAL** | 로컬 Ollama VAL-01 12/12 PASS · **NVIDIA(NIM) PASS** HTTP 200 · Gemini FAIL(empty/503/404) · ZAI FAIL HTTP 429 · OpenRouter FAIL HTTP 401 · `ex-2026-09-15/ex01_summary.md` (비밀 미기록) |
| EX-02 | 모델/라이선스/개인정보·지원 승인 | **PARTIAL** | [CR14_EX02_APPROVAL_RECORD.md](./CR14_EX02_APPROVAL_RECORD.md) — PRODUCT_SELF_APPROVAL(범위 문구) 완료; `BLOCKED_EXTERNAL` legal 미해제 · Experimental→Supported 없음 · GA GO 아님 |
| EX-03 | 이전 출시 artifact | **DONE** | **NOT_AVAILABLE** — 태그 0 · gh release 401 · dist는 현재 후보만 · `ex03_summary.md` |
| EX-04 | 지원 OS sandbox 실측 | **DONE** | macOS 26.6.2 arm64 · seatbelt/`sandbox-exec` · pytest 46 passed · `ex04_summary.md` (행렬 미승격) |
| EX-05 | 8h soak | **INCONCLUSIVE — DONE 아님** (JSON 지표 PASS, 종료·귀속 미확정) | prior FAIL retained · resoake `run28800e` · `all_pass: true` · SC-1..6 PASS · SC-6 rss_growth_mb=**48.7** (<64) · messages_bounded · duration≈28801s · JSON `…/val02_soak_28800_resoake.json` (~2026-09-15 23:08 KST) · wrapper `finished exit:141` (original command unavailable) · `run_sha_binding: UNVERIFIED` · watch routine deleted |
| EX-06 | 범위 축소 여부 | **DONE** | 축소 없음 (`EX-06-NO-SHRINK-2026-09-15`) |

## 진행 노트

- 이 실행은 C14-08 NO-GO를 GO로 바꾸지 않는다. 근거가 쌓이면 재판정한다.
- OPENAI_API_KEY 는 자리표시자 수준(길이 3)으로 보고 **미설정** 취급한다.

- 2026-09-15: EX-01/03/04 증거 수집. Ollama PASS · OpenRouter 401 blocker · EX-03 NOT_AVAILABLE · EX-04 46 passed. CR-14 GO/DONE 미선언 · 커밋/푸시 안 함 · soak 재시작 안 함.

- 2026-09-15: EX-02 승인 기록 작성 (`CR14_EX02_APPROVAL_RECORD.md`). 겸직·제3자 법무 아님·GA GO 아님. 상태 PARTIAL.

## EX-05 실행 기록

- 재시작: 2026-09-15 06:46 UTC+09:00
- pid: `29961`/`29969` (tool-backed background; 29455 died empty-log) (파일: `.omo/evidence/commercial-reliability/CR-14/ex-2026-09-15/soak/pid.txt`)
- 명령: `val02_staging.py --scenarios SC-1..SC-6 --soak-seconds 28800 --workdir …/soak/workdir/run28800`
- 출력: `.omo/evidence/commercial-reliability/CR-14/ex-2026-09-15/soak/val02_soak_28800.json`
- 첫 시도는 tempfile+RegistrySaveError 로 실패 → 고정 workdir 로 재시작. prunable worktree 1건 prune 후 재측정.
- 감시 루틴: `ex-05-8h-soak` (평일 14–17시)
- 2026-09-15 pause note: desktop packaging stopped; soak watch-only. PIDs still `29961`/`29969` (workdir `run28800c`). Do not kill.

## EX-01/03/04 실측 마감 (2026-09-15 06:50 UTC+09:00)

- EX-01: 로컬 PASS · OpenRouter 401 → cloud BLOCKED (NVIDIA/Gemini/ZAI 추가 프로브 진행 중일 수 있음)
- EX-03: NOT_AVAILABLE
- EX-04: 이 macOS 호스트 DONE (행렬 미승격)
- EX-02: PARTIAL · EX-05: **FAIL** · EX-06: DONE
- CR-14 GO/DONE 아님

- 2026-09-15: EX-01 cloud 추가 프로브(NVIDIA/Gemini/ZAI). NVIDIA PASS · Gemini/ZAI/OpenRouter FAIL → EX-01 **PARTIAL**. 비밀 미기록 · GO 미선언 · 커밋/soak 재시작 없음.
- 2026-09-15: OpenRouter 재실측 — 키 유효 · gpt-4o-mini 402 credits · **openrouter/free PASS** (stream). EX-01 여전히 PARTIAL(유료 모델/타 provider 잔여). 비밀 미기록 · GO 미선언.

- 2026-09-15 (~09:07 KST): **데스크톱 패키징 레인 일시 중단** (사용자). tip `1754db83` unpushed. EX-05 soak **여전히 IN_PROGRESS** — pids `29961`/`29969` ALIVE (~2h20+/28800s at pause note); 종료 JSON 대기. CR-14 GO 미선언. 별도 레인: `docs/packaging/notes/SESSION_CHECKPOINT_2026-09-15.md`.

## EX-05 결과 (2026-09-15 ~14:47 KST) — **FAIL**

- Soak finished ~2026-09-15 14:47 KST; pids `29961`/`29969` gone.
- SC-1..SC-5 **PASS**; SC-6 **FAIL**; `all_pass: false`.
- SC-6: `duration_s=28800.051`, `errors=0`, `fd_growth=0`, `orphan_worktrees=0`.
- RSS: ~66.8 → 1721.8 MB; **`rss_growth_mb=1654.9`** vs frozen **`rss_leak_mb=64`** (do not raise without Decision Log + owner).
- Workload: ~150554 conversation appends on single `soak-conv`.
- Evidence path only: `.omo/evidence/commercial-reliability/CR-14/ex-2026-09-15/soak/val02_soak_28800.json`
- **CR-14 remains NO-GO.** Candidate `b6003205` / fingerprint `02349a8d…`.
- Investigation: `docs/ga/notes/EX05_SC6_RSS_INVESTIGATION_2026-09-15.md`. Desktop packaging paused (D-09). Soak watch routine paused.
- 2026-09-15: Decision **A** — ConversationStore soft-max auto-compact (default 64). SC-6 equality updated to bounded messages. Threshold 64MB unchanged. Short probe pending/recorded separately. CR-14 GO 아님.

## EX-05 재soak 결과 (2026-09-15 15:07 → ~23:08 KST) — **JSON PASS / 귀속 UNVERIFIED**

- 3단계를 **섞지 않는다**: ① 1차 run 은 **FAIL**(RSS 1654.9 ≫ 64), ② Decision A, ③ 재soak 은 **JSON 지표 PASS**, ④ 종료·귀속은 **미확정**.
- 재soak JSON: `duration_s=28801.318` · `completed_ops=12102886` · `conversation_ops=12102886` · `conversation_revision=12102886` · `conversation_message_count=26`(soft max 64) · `errors=0` · `fd_growth=0` · `orphan_worktrees=0` · `rss_growth_mb=48.7` · SC-1~6 `pass:true` · `all_pass:true`.
- 경로: `.omo/evidence/commercial-reliability/CR-14/ex-2026-09-15/soak/val02_soak_28800_resoake.json`(원본 수정 없음). SHA256과 sample 배열 요약은 `docs/qa/2026-09-16-followup/soak-summary.json`.
- **이 결과로 EX-05 를 DONE 으로 올리지 않는다.** ④ 가 남아 있다:
  - 래퍼 로그 마지막 줄이 `finished exit:141` 이고 **원문 명령이 보존되지 않아** INCONCLUSIVE 다(SIGPIPE 로 **설명**할 수는 있지만 입증된 원인으로 기록하지 않는다). JSON PASS 를 FAIL 로 바꾸지도, 정상 exit0 을 추정하지도 않는다.
  - **재soak 이 어느 커밋 후보의 트리에서 돌았는지** 시작/종료 지문으로 귀속되지 않았다(`run_sha_binding: UNVERIFIED`). 지문 없는 초록은 판정 근거가 아니다.
  - 종료 원문 복구는 불가로 종결하고 **NX-10 의 새 후보 시험**으로 대체한다(`nx00/handoff.md` §2 · NX-00-F01).
- CR-14 는 여전히 **NO-GO** 이고, 현재 작업 트리 상태는 이 JSON 의 지표를 주장할 수 없다.

## EX-05 resoake start (2026-09-15 15:07 KST)

- After Decision A (`78012f4a` soft-max auto-compact). Prior 8h result remains FAIL (RSS 1654.9).
- Command: `val02_staging.py --scenarios SC-1..SC-6 --soak-seconds 28800`
- workdir: `…/soak/workdir/run28800e`
- output: `…/soak/val02_soak_28800_resoake.json`
- pids: shell `72699` + `val02_staging` (see pid_resoake.txt); first nohup attempt died — relaunched durable
- Watch routine **resumed** (`ex-05-8h-soak`).
- CR-14 still **NO-GO** until resoake PASS + other EX gates.
- 2026-09-16: resoake 종료 — **JSON PASS**, 단 종료141·후보 귀속은 미확정(위 "EX-05 재soak 결과" 참조). EX-05 는 DONE 아님. 현재 상태 요약: `docs/20_CURRENT_STATUS.md` §3.

## EX-05 resoake result (2026-09-15 ~23:08 KST) — **PASS**

- Decision A soft-max tip `78012f4a`. workdir `…/soak/workdir/run28800e`.
- `all_pass: true`. SC-1..SC-6 all `pass: true`.
- SC-6: `rss_growth_mb=48.7` (threshold 64), RSS ~65.7→114.4 MB, `conversation_messages_bounded=true`, `actual_duration_s≈28801`, errors=0, fd_growth=0.
- Evidence: `.omo/evidence/commercial-reliability/CR-14/ex-2026-09-15/soak/val02_soak_28800_resoake.json`
- Prior 8h FAIL (RSS 1654.9 on unbounded history) remains in history; this PASS is the Decision A re-measure.
- Soak watch routine deleted after completion.
- **CR-14 still NO-GO** — other EX gates (EX-01/02 PARTIAL, etc.) and human C14-08 still apply. Do not claim GO from EX-05 alone.
