#!/usr/bin/env bash
# NX-10 — SC-1~6 8시간(28,800s) soak 러너. **아직 실행하지 않았다** (8시간 + 기기 점유 결정 필요).
#
# NX-00 이 남긴 세 가지 실패 모드를 코드로 막는다:
#   ① 실행 명령이 사라진다 → 이 파일이 원문 명령을 소유하고, 러너가 자기 명령을 로그에 남긴다.
#   ② 시작/종료 코드 후보가 귀속되지 않는다(`run_sha_binding: UNVERIFIED`) → 시작·종료 시점의
#      HEAD SHA 와 코드 지문을 **따로** 기록해 리포트가 어느 트리의 것인지 사후에 확정할 수 있게 한다.
#   ③ 래퍼 exit 를 잃는다(`finished exit:141` + stdout 절단) → 출력은 파일로만 흘리고(파이프 금지),
#      종료 코드를 별도 파일에 남긴다.
#
# 실행:
#   screen -dmS nx10soak bash docs/qa/2026-09-16-followup/nx10/run_nx10_soak.sh
# 진행 확인:
#   screen -ls ; tail -f docs/qa/2026-09-16-followup/nx10/soak-run.log
#   tail -3 docs/qa/2026-09-16-followup/nx10/soak-exit.txt
#
# 끝난 뒤:
#   uv run scripts/ga_gate_verify.py --report docs/qa/2026-09-16-followup/nx10/gate-report-full001.json \
#     --manifest scripts/commercial_ga_gates.json --expected-sha <FULL_CANDIDATE_SHA> \
#     --soak-artifact docs/qa/2026-09-16-followup/nx10/soak-28800.json --min-soak-seconds 28800

set -u

# 저장소 루트는 NX10_REPO 로 덮어쓸 수 있다 — 절대경로 고정은 남의 클론/격리 체크아웃에서 조용히
# 엉뚱한 저장소를 조작한다(soak_control.sh 와 같은 규칙, schedule_nx10_soak.sh 와 동일 형식).
REPO="${NX10_REPO:-/Users/mr.k/program/coding/ssak_comp/Ssak-Ai}"
OUT_REL="${NX10_SOAK_OUT_REL:-docs/qa/2026-09-16-followup/nx10}"
# 증거 경로를 **절대경로로 덮어쓸 수 있게** 둔다: 그래야 "동시 실행을 거부하는가"를 임시 디렉터리에서
# 검증할 수 있다(거부 경로가 본 증거에 시험 흔적을 남기지 않는다).
cd "$REPO" || exit 1
OUT="${NX10_SOAK_OUT_DIR:-$REPO/$OUT_REL}"
PY="$REPO/.venv/bin/python"
SOAK_SECONDS="${SOAK_SECONDS:-28800}"
REPORT="$OUT/soak-${SOAK_SECONDS}.json"
# ── 보존 캡(측정 설정 — 기록에 남긴다) ─────────────────────────────────────────
# 왜 러너가 정하는가(실측 2026-09-17): ADR-DAT-02 의 기본 **hard cap 은 512 MiB 이고 자동 prune 은
# 없다**(설계 — 지우지 않고 거절한다). 꼬리 창 수정으로 append 가 20배 빨라진 뒤 이 soak 은 journal 을
# ≈160 KB/s 로 쓴다 → **50분이면 기본 캡을 넘긴다**(실측: 47분에 452 MiB, 중단 시점 439 MiB).
# 넘긴 뒤에는 모든 append 가 `ConversationHistoryQuotaExceededError`(507) 로 거절되고, 하네스가
# 그것을 `errors` 로 세므로(`SC-6 pass` 조건에 `errors == 0`) **제품 결함이 아닌 설정 때문의 거짓 FAIL**
# 이 된다 — 이 카드가 반복해 겪은 종류(`돌리다 만 것`과 `다른 이유로 빨개진 것`)다.
# 8시간 예상 쓰기량(≈4.5 GB)이 여유 있게 들어가는 값으로 올리고, 그 사실을 기록·문서에 남긴다.
# soft cap 은 기본값을 그대로 둔다(경고·`journals_over_soft_cap` 관측이 그대로 살아 있다).
export AGK_CONVERSATION_JOURNAL_HARD_CAP_MB="${AGK_CONVERSATION_JOURNAL_HARD_CAP_MB:-8192}"
RETENTION_CAPS="$("$REPO/.venv/bin/python" -c "import sys; sys.path.insert(0,'src'); from antigravity_k.engine.conversation_retention import resolve_policy as r; p=r(); print('soft=%dMiB hard=%dMiB' % (p.soft_cap_bytes//1048576, p.hard_cap_bytes//1048576))" 2>/dev/null || echo unknown)"
# 작업 디렉토리는 **저장소 밖**에 둔다 — 8시간 soak 은 수백 MB~수 GB 를 쓰므로 공유 체크아웃을
# 더럽히면 다른 레인의 `git status`/프라이어블 worktree 판정에 끼어든다. (60초 리허설은
# 저장소 안에 만들었던 적이 있다 — 그 디렉토리들은 증거로 남기고, 정식 실행부터는 /tmp 를 쓴다.)
WORKDIR="${NX10_SOAK_WORKDIR:-/tmp/nx10-soak-work-$(date -u +%Y%m%dT%H%M%SZ)}"
# 지문은 **venv 파이썬**으로만 계산한다(실측: /usr/bin/python3 = 3.9.6 은 ga_gate.py 의 3.12 문법을
# 파싱하지 못해 지문이 UNVERIFIED 로 떨어진다).
FINGERPRINT_CMD=("$PY" -c "import sys,pathlib; sys.path.insert(0,'scripts'); import ga_gate; print(ga_gate.worktree_fingerprint(pathlib.Path('.')))")
RUNLOCK="$OUT/.soak-run.lock"   # 8시간 실행 단일 잠금 — 별개 예약/수동 실행이 겹치는 것을 막는다

# ── 동시 실행 방지 ───────────────────────────────────────────────────────────
# soak 은 포트·작업 디렉토리(`/tmp/nx10-soak-work-*`)·리포트를 혼자 쓴다. 두 개가 동시에 돌면
# 서로의 지표를 오염시키고 어느 쪽 결과도 후보에 쓸 수 없다. 그래서 실행은 단일만 허용한다.
_soak_lock() {
  local owner_pid
  if mkdir "$RUNLOCK" 2>/dev/null; then
    {
      echo "pid: $$"
      echo "started_at: $(date -u +%FT%TZ)"
    } > "$RUNLOCK/owner"
    return 0
  fi
  owner_pid="$(sed -n 's/^pid: //p' "$RUNLOCK/owner" 2>/dev/null | head -1)"
  if [ -n "$owner_pid" ] && kill -0 "$owner_pid" 2>/dev/null; then
    {
      echo ""
      echo "# soak 실행 거부 — 이미 돌고 있다"
      echo "generated_at: $(date -u +%FT%TZ)"
      echo "refused_reason: concurrent soak (run lock held by live pid $owner_pid)"
    } >> "$OUT/soak-exit.txt"
    echo "=== soak REFUSED (concurrent run, owner pid $owner_pid) $(date -u +%FT%TZ) ===" | tee -a "$OUT/soak-run.log"
    exit 5
  fi
  # 중단된 옛 실행이 남긴 잠금은 지우지 않고 증거로 밀어 둔다.
  mv "$RUNLOCK" "$RUNLOCK.stale-$(date -u +%Y%m%dT%H%M%SZ)" 2>/dev/null || true
  mkdir "$RUNLOCK" 2>/dev/null && {
    echo "pid: $$"
    echo "started_at: $(date -u +%FT%TZ)"
  } > "$RUNLOCK/owner"
  return 0
}

_soak_unlock() {
  local owner_pid
  owner_pid="$(sed -n 's/^pid: //p' "$RUNLOCK/owner" 2>/dev/null | head -1)"
  if [ -n "$owner_pid" ] && [ "$owner_pid" != "$$" ]; then return 0; fi
  rm -rf "$RUNLOCK"
}

_soak_lock
trap '_soak_unlock' EXIT INT TERM HUP

{
  echo "# NX-10 SC-1~6 soak 러너 기록"
  echo "generated_at: $(date -u +%FT%TZ)"
  echo "soak_seconds: $SOAK_SECONDS"
  echo "report: $REPORT"
  echo "workdir: $WORKDIR"
  echo "command: AGK_CONVERSATION_JOURNAL_HARD_CAP_MB=$AGK_CONVERSATION_JOURNAL_HARD_CAP_MB PYTHONPATH=src $PY scripts/val02_staging.py --output $REPORT --scenarios SC-1,SC-2,SC-3,SC-4,SC-5,SC-6 --soak-seconds $SOAK_SECONDS --workdir $WORKDIR"
  echo "retention_caps: $RETENTION_CAPS (soft 는 기본 유지 — 경고 관측을 남긴다)"
} >> "$OUT/soak-exit.txt"

# ② 시작 시점의 후보 귀속 (종료 시점에도 다시 찍는다)
{
  echo "start_time: $(date -u +%FT%TZ)"
  echo "start_head: $(git rev-parse HEAD)"
  echo "start_dirty: $(test -n "$(git status --porcelain)" && echo true || echo false)"
  echo "start_fingerprint: $("${FINGERPRINT_CMD[@]}" 2>/dev/null || echo UNVERIFIED)"
} >> "$OUT/soak-exit.txt"

echo "=== soak START $(date -u +%FT%TZ) (${SOAK_SECONDS}s) ===" | tee -a "$OUT/soak-run.log"

# ③ 파이프 없이 파일로만 — stdout 절단/SIGPIPE 를 만들지 않는다.
PYTHONPATH="$REPO/src" "$PY" scripts/val02_staging.py \
  --output "$REPORT" \
  --scenarios SC-1,SC-2,SC-3,SC-4,SC-5,SC-6 \
  --soak-seconds "$SOAK_SECONDS" \
  --workdir "$WORKDIR" >> "$OUT/soak-run.log" 2>&1
code=$?

{
  echo "exit: $code"
  echo "end_time: $(date -u +%FT%TZ)"
  echo "end_head: $(git rev-parse HEAD)"
  echo "end_dirty: $(test -n "$(git status --porcelain)" && echo true || echo false)"
  echo "end_fingerprint: $("${FINGERPRINT_CMD[@]}" 2>/dev/null || echo UNVERIFIED)"
} >> "$OUT/soak-exit.txt"

echo "=== soak EXIT:$code $(date -u +%FT%TZ) ===" | tee -a "$OUT/soak-run.log"
exit "$code"
