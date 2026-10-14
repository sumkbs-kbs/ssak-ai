#!/usr/bin/env bash
# NX-10 soak 예약 실행 — 오너가 지정한 시각(기본 22:00 로컬)에 **동결 트리**에서 soak 을 시작한다.
#
# 왜 예약인가: 8시간 soak 은 오너가 정한 창(오늘 22:00 ≈ 종료 06:00)에 돌려야 하고, 그 전에 코드가
# 바뀌면 안 된다. 예약 실행기는 시작 직전에 **지문을 확인**해서, 동결 이후 트리가 움직였으면 8시간을
# 태우지 않고 즉시 기록하고 멈춘다.
#
# 실행:
#   screen -dmS nx10soak bash docs/qa/2026-09-16-followup/nx10/schedule_nx10_soak.sh
# 확인:
#   cat  docs/qa/2026-09-16-followup/nx10/soak-schedule.txt   # 예약 시각·지문·pid
#   tail docs/qa/2026-09-16-followup/nx10/soak-schedule.log    # 대기 heartbeat
#   screen -ls ; tail -3 docs/qa/2026-09-16-followup/nx10/soak-exit.txt
#
# 시각/지문 바꾸기(기본값은 오너 판정 2026-09-16):
#   NX10_SOAK_AT=23:30 NX10_EXPECT_FINGERPRINT=<fp> screen -dmS nx10soak bash .../schedule_nx10_soak.sh
# 계산만 확인(실행 안 함):
#   NX10_SCHEDULE_DRY_RUN=1 bash .../schedule_nx10_soak.sh
# 노트북 잠자기를 막지 않으려면: NX10_NO_CAFFEINATE=1

set -u

REPO="${NX10_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)}"
OUT="${NX10_SOAK_OUT_DIR:-${NX10_OUT:-$REPO/docs/qa/2026-09-16-followup/nx10}}"
RUNNER="${NX10_RUNNER:-$REPO/docs/qa/2026-09-16-followup/nx10/run_nx10_soak.sh}"
export NX10_REPO="$REPO" NX10_OUT="$OUT" NX10_SOAK_OUT_DIR="$OUT" NX10_RUNNER="$RUNNER"
SCHEDULE="$OUT/soak-schedule.txt"
LOG="$OUT/soak-schedule.log"
LOCK="$OUT/.soak-arm.lock"   # 예약 단일 잠금 — 상세는 soak_control.sh 참조
# 지문 계산은 **venv 파이썬**으로 한다. 시스템 `python`/`python3` 는 3.9 일 수 있고(실측:
# /usr/bin/python3 = 3.9.6), 그러면 `ga_gate.py` 의 3.12 문법에서 SyntaxError 가 나
# 지문이 UNVERIFIED 로 떨어져 **22:00 에 아무것도 하지 않고 중단**된다.
PY_FP="${NX10_PYTHON:-$REPO/.venv/bin/python}"
[ -x "$PY_FP" ] || { printf 'Candidate interpreter unavailable: %s\n' "$PY_FP" >&2; exit 2; }
export NX10_PYTHON="$PY_FP"
AT_LOCAL="${NX10_SOAK_AT:-22:00}"
# 기본값은 **예약하는 시점의 트리 지문**이다(고정 해시를 하드코딩하지 않는다 — 낡은 해시가 남아
# 있으면 정상 예약도 드리프트로 오판한다). 값을 넘기면 그 값이 우선이고 출처를 기록한다.
if [ -n "${NX10_EXPECT_FINGERPRINT:-}" ]; then
  EXPECTED_FP="$NX10_EXPECT_FINGERPRINT"
  FP_SOURCE="env"
else
  EXPECTED_FP=""
  FP_SOURCE="computed-at-launch"
fi
DRY_RUN="${NX10_SCHEDULE_DRY_RUN:-0}"

cd "$REPO" || exit 1

_fingerprint() {
  "$PY_FP" -c "import sys,pathlib; sys.path.insert(0,'scripts'); import ga_gate; print(ga_gate.worktree_fingerprint(pathlib.Path('.')))" 2>/dev/null || echo UNVERIFIED
}

# ── 단일 예약 잠금 ───────────────────────────────────────────────────────────
# 왜 필요한가(2026-09-16 실측): “취소했다"고 기록한 예약 3건이 실제로는 살아서 대기하고 있었다.
# 취소는 `screen -X quit`(화면만 닫힘)이었고 `login -pflq` 래퍼가 SIGHUP 을 무시했다. 그대로두면
# 4개가 22:00 에 동시에 깨어난다 — 같은 기록 파일을 동시에 append 하고, 둘 이상이 같은 지문을
# 들고 있었다면 soak 두 개가 동시에 돌아 포트·산출물을 다툰다. 그래서 잠금은 **원자적 mkdir** 로
# 잡고, 주인이 살아 있으면 예약을 거부한다.
_acquire_lock() {
  local tries=0 owner_pid
  while [ "$tries" -lt 2 ]; do
    if mkdir "$LOCK" 2>/dev/null; then
      {
        echo "pid: $$"
        echo "armed_at: $(date -u +%FT%TZ)"
        echo "at_local: $AT_LOCAL"
        echo "target_utc: $TARGET_UTC"
        echo "expected_fingerprint: $EXPECTED_FP"
        echo "expected_fingerprint_source: $FP_SOURCE"
        echo "runner: $RUNNER"
      } > "$LOCK/owner"
      return 0
    fi
    owner_pid="$(sed -n 's/^pid: //p' "$LOCK/owner" 2>/dev/null | head -1)"
    if [ -n "$owner_pid" ] && kill -0 "$owner_pid" 2>/dev/null; then
      {
        echo "aborted: true"
        echo "aborted_reason: duplicate reservation — 잠금 주인 pid $owner_pid 이 살아 있다"
        echo "aborted_at: $(date -u +%FT%TZ)"
      } >> "$SCHEDULE"
      echo "=== schedule ABORTED (duplicate reservation, owner pid $owner_pid) $(date -u +%FT%TZ) ===" >> "$LOG"
      exit 4
    fi
    # 죽은 주인의 잠금은 지우지 않고 증거로 밀어 둔다.
    mv "$LOCK" "$LOCK.stale-$(date -u +%Y%m%dT%H%M%SZ)" 2>/dev/null || true
    tries=$((tries + 1))
  done
  echo "=== schedule ABORTED (cannot acquire lock) $(date -u +%FT%TZ) ===" >> "$LOG"
  exit 4
}

_release_lock() {
  # 내 잠금만 푼다(pid 비교). 남의 잠금을 지워 다른 예약을 망가뜨리지 않는다.
  local owner_pid
  owner_pid="$(sed -n 's/^pid: //p' "$LOCK/owner" 2>/dev/null | head -1)"
  if [ -n "$owner_pid" ] && [ "$owner_pid" != "$$" ]; then return 0; fi
  rm -rf "$LOCK"
}

read -r TARGET_EPOCH TARGET_LOCAL TARGET_UTC WAIT_SECONDS < <(
  "$PY_FP" - "$AT_LOCAL" <<'PY'
import datetime, sys

spec = sys.argv[1]
hour_text, _, minute_text = spec.partition(":")
tz = datetime.datetime.now().astimezone().tzinfo
now = datetime.datetime.now(tz)
target = now.replace(hour=int(hour_text), minute=int(minute_text or 0), second=0, microsecond=0)
if target <= now:
    target += datetime.timedelta(days=1)
print(
    int(target.timestamp()),
    target.isoformat(timespec="seconds"),
    target.astimezone(datetime.timezone.utc).isoformat(timespec="seconds"),
    int((target - now).total_seconds()),
)
PY
)

if [ "$DRY_RUN" = "1" ]; then
  echo "dry_run=1 at_local=$AT_LOCAL target_local=$TARGET_LOCAL target_utc=$TARGET_UTC wait_seconds=$WAIT_SECONDS epoch=$TARGET_EPOCH"
  echo "expected_fingerprint=${EXPECTED_FP:-<예약 시점 트리에서 계산>} source=$FP_SOURCE"
  exit 0
fi

# 여기서 잠금을 잡는다: 대기 중인 예약은 하나만 존재해야 한다.
mkdir -p "$OUT" || exit 2
_acquire_lock
# 대기 중 중단(TERM/HUP/INT)되더라도 내 잠금은 풀고 죽는다 — 남겨 두면 다음 예약이 stale 판정을 본다.
trap '_release_lock' EXIT INT TERM HUP

if [ -z "$EXPECTED_FP" ]; then
  EXPECTED_FP="$(_fingerprint)"
  # 잠금 파일에 실제 기대값을 적어 둔다(status 가 지문을 대조할 수 있게).
  printf 'expected_fingerprint: %s\n' "$EXPECTED_FP" >> "$LOCK/owner"
fi

# 대기 구간까지 깨어 있게 하려면 NX10_CAFFEINATE_WAIT=1 (기본은 soak 실행 구간만 깨어 있게 한다).
# 뚜껑을 닫으면 caffeinate 로도 잠들기 때문에, 22:00 시작을 지키려면 기계를 열어 두어야 한다.
if [ "${NX10_CAFFEINATE_WAIT:-0}" = "1" ] && [ "${_NX10_CAFFEINATED:-0}" != "1" ] && command -v caffeinate >/dev/null 2>&1; then
  export _NX10_CAFFEINATED=1
  exec caffeinate -i bash "$0" "$@"
fi

{
  echo "# NX-10 soak 예약 기록 (오너 지정 시각 실행)"
  echo "scheduled_at: $(date -u +%FT%TZ)"
  echo "scheduled_local: $(date +%FT%T%z)"
  echo "at_local: $AT_LOCAL"
  echo "target_local: $TARGET_LOCAL"
  echo "target_utc: $TARGET_UTC"
  echo "wait_seconds: $WAIT_SECONDS"
  echo "expected_fingerprint: $EXPECTED_FP"
  echo "runner: $RUNNER"
  echo "pid: $$"
} >> "$SCHEDULE"

echo "=== schedule WAIT until $TARGET_LOCAL ($TARGET_UTC), ${WAIT_SECONDS}s $(date -u +%FT%TZ) ===" >> "$LOG"

# 대기 heartbeat — 자고 있는지/깨어 있는지 사후에 알 수 있게 남긴다.
python3 - "$TARGET_EPOCH" <<'PY' >> "$LOG"
import sys, time

target = int(sys.argv[1])
last_bucket = None
while True:
    remaining = target - int(time.time())
    if remaining <= 0:
        break
    bucket = remaining // 900
    # 이전 구현은 `remaining % 900 < 60` 이었고 60초 창 동안 30초마다 찍혀 15분마다 **4줄**이
    # 쌓였다(“중복 방지” 주석과 달리 중복이었다). 버킷이 바뀔 때만 한 줄 찍는다 — 로그가 중복
    # 프로세스를 숨기지 않게 하는 것이 목적이다(오늘 4개 예약이 동시에 heartbeat 를 쓰고 있었다).
    if bucket != last_bucket:
        print(f"waiting remaining={remaining}s at {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}", flush=True)
        last_bucket = bucket
    time.sleep(30)
print(f"target reached at {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}", flush=True)
PY

# 시작 직전 지문 확인: 동결 이후 코드가 움직였으면 8시간을 태우지 않는다.
CURRENT_FP="$(_fingerprint)"
{
  echo "start_check_at: $(date -u +%FT%TZ)"
  echo "start_check_fingerprint: $CURRENT_FP"
  echo "start_check_head: $(git rev-parse HEAD)"
  echo "start_check_dirty: $(test -n "$(git status --porcelain)" && echo true || echo false)"
} >> "$SCHEDULE"

# UNVERIFIED 는 **불일치보다 먼저** 막는다: 계산 실패를 "그냥 진행" 으로 넘기지 않는다.
if [ "$CURRENT_FP" = "UNVERIFIED" ]; then
  {
    echo "aborted: true"
    echo "aborted_reason: fingerprint unverifiable ($PY_FP 로 계산 실패) — 확인되지 않은 트리에서 8시간을 쓰지 않는다"
    echo "aborted_at: $(date -u +%FT%TZ)"
  } >> "$SCHEDULE"
  echo "=== schedule ABORTED (fingerprint unverifiable, PY_FP=$PY_FP) $(date -u +%FT%TZ) ===" >> "$LOG"
  _release_lock
  exit 3
fi

if [ "$CURRENT_FP" != "$EXPECTED_FP" ]; then
  {
    echo "aborted: true"
    echo "aborted_reason: fingerprint drift (expected $EXPECTED_FP, got $CURRENT_FP) — 동결 트리가 아니므로"
    echo "aborted_at: $(date -u +%FT%TZ)"
  } >> "$SCHEDULE"
  echo "=== schedule ABORTED (fingerprint drift) $(date -u +%FT%TZ) ===" >> "$LOG"
  _release_lock
  exit 2
fi

# 여기서 예약 잠금을 놓는다 — 대기는 끝났고, 이후의 단일 실행은 러너의 실행 잠금이 지킨다.
_release_lock
echo "=== schedule START soak $(date -u +%FT%TZ) ===" >> "$LOG"
if [ "${NX10_NO_CAFFEINATE:-0}" = "1" ] || ! command -v caffeinate >/dev/null 2>&1; then
  exec bash "$RUNNER"
fi
# 기본: 오너가 정한 밤 창에 8시간이 실제로 흐르도록 idle sleep 을 막는다(사용자 활동 아님).
exec caffeinate -i bash "$RUNNER"
