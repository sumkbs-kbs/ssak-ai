#!/usr/bin/env bash
# NX-10 soak 예약 **통제** — arm / status / cancel / orphans / selftest
#
# 왜 이 파일이 생겼는가 (2026-09-16, 실측):
#   ① 예약을 취소했다고 기록했는데 **프로세스가 살아 있었다.** 취소는 `screen -S nx10soak -X quit`
#      였고 기록도 "시작 전 대기 중이었고 시작하지 않았다" 였지만, pgrep 로 확인하니 옛 예약 3건이
#      그대로 대기 중이었다(18:47Z·19:26Z·19:47Z 시작분 + 최초 08:20Z 분 = 총 4개). `login -pflq`
#      래퍼는 SIGHUP 을 무시하므로 화면을 닫아도 프로세스는 살아남는다.
#      → 22:00 에 4개가 동시에 깨어날 뻔했다(그중 3개는 지문 불일치로 abort 했겠지만, 같은 기록
#      파일을 동시에 append 하고 그 사실이 로그에 묻힌다).
#   ② 그래서 "취소 = 프로세스가 실제로 죽었음을 확인하는 일" 로 정의하고, 예약은 **단일**만
#      허용한다(잠금은 `mkdir` 원자성으로 잡는다). 이 도구가 그 두 가지를 강제한다.
#
# 사용(승격 뒤에는 `bash scripts/soak_control.sh …` — 증거는 계속 `$OUT` 에 쓴다):
#   bash docs/qa/2026-09-16-followup/nx10/soak_control.sh status
#   bash docs/qa/2026-09-16-followup/nx10/soak_control.sh arm            # 기본 22:00, 지문은 **지금 트리**에서 계산
#   bash docs/qa/2026-09-16-followup/nx10/soak_control.sh arm --at 23:30 --fp <지문>
#   bash docs/qa/2026-09-16-followup/nx10/soak_control.sh cancel         # 살아 있는 예약을 죽이고 **죽었는지 검증**
#   bash docs/qa/2026-09-16-followup/nx10/soak_control.sh orphans        # 잠금 주인이 아닌 살아 있는 예약 탐지
#   bash docs/qa/2026-09-16-followup/nx10/soak_control.sh preflight      # 발화 전: 8시간을 태울 준비가 됐는가(의존성·여유 공간·후보 귀속·**처리량 하한**)
#     처리량 하한은 `NX10_PREFLIGHT_PROBE_SECONDS`(기본 60초)·`NX10_PREFLIGHT_MIN_OPS_PER_SEC`(기본 133)로 조정하고,
#     `NX10_PREFLIGHT_SKIP_THROUGHPUT=1` 로 생략한다(자기시험은 그 문을 쓴다 — 60초 프루브는 시험을 느리게 만든다).
#     “다른 soak 실행 없음” 은 **기계 전체**를 보고 하네스 이름은 `NX10_SOAK_PROC_PATTERN`(기본
#     `val02_staging.py`)으로 정한다 — 진짜 soak 이 도는 동안에도 시험이 의미를 가지려면 이름을 시험이 통제해야 한다.
#   bash docs/qa/2026-09-16-followup/nx10/soak_control.sh run           # 예약을 기다리지 않고 **지금** 시작(같은 preflight 를 통과해야 한다)
#   bash docs/qa/2026-09-16-followup/nx10/soak_control.sh harvest       # 8시간 뒤 회수: 끝날 때까지 기다렸다가 회수 판정기까지 돌린다
#     `--detach` 면 화면 세션(`nx10harvest`)에 띄워 창이 재시작돼도 살아남는다(대기 중 잠자기 차단 포함).
#     `--no-wait` 는 "지금 끝난 실행만 판정" 이다(아직 돌면 exit 4로 거부한다 — 옛 블록을 읽지 않기 위해).
#     대기 상한 `NX10_HARVEST_TIMEOUT`(기본 43200초) · 폴링 `NX10_HARVEST_POLL`(기본 60초) ·
#     판정기 교체 `NX10_JUDGE`(기본 `scripts/collect_soak_result.py` — 자기시험은 스텁을 쓴다).
#     **플러시 대기** `NX10_HARVEST_SETTLE`(기본 120초) · **무응답 상한** `NX10_HARVEST_MAX_STALL`(기본 1800초): 프로세스는 살아 있는데 그 시간 동안
#     아무것도 쓰지 않으면 "도는 중" 이 아니라 **멈춘 것**으로 보고 exit 6 으로 내려온다
#     (실측 2026-09-17: 죽은 worker 를 부모가 영원히 기다렸고, 프로세스 생존만 보는 판정은 그 상태를 몰랐다).
#   bash docs/qa/2026-09-16-followup/nx10/soak_control.sh selftest       # 임시 디렉터리에서 전 수명주기 검증
#
# 종료 코드: arm/cancel 은 성공 0, 거부 2(이미 예약 있음), 검증 실패 3(죽이지 못했다). harvest 는
#            판정기의 exit 그대로(0=PASS) · 2 인자 · 3 회수할 실행 없음 · 4 아직 돌고 있다 · 5 대기 초과
#            · 6 무응답(살아 있지만 오래 아무것도 안 쓴다 — 멈춘 것으로 본다).
#            status 는 0 = "단일 예약 + 지문 일치" **또는** "실행 중(run) + 시작 지문 일치", 아니면 1.
#
# 테스트를 위해 경로를 덮어쓸 수 있다(기본값은 이 저장소): NX10_REPO · NX10_OUT ·
# NX10_SCHEDULER · NX10_RUNNER · NX10_SCHED_PATTERN · NX10_CANCEL_GRACE.

set -u

# 저장소 루트를 **스크립트 위치에서** 찾는다 — 승격(`docs/` → `scripts/`)으로 깊이가 바뀌어도 산다.
# (하드코딩된 절대 경로를 기본값으로 두면 남의 클론에서 조용히 엉뚱한 저장소를 조작한다.)
_nx10_repo_root() {
  local dir
  dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  while [[ "$dir" != "/" ]]; do
    if [[ -f "$dir/pyproject.toml" && -d "$dir/src/antigravity_k" ]]; then
      printf '%s\n' "$dir"
      return 0
    fi
    dir="$(dirname "$dir")"
  done
  return 1
}
REPO="${NX10_REPO:-$(_nx10_repo_root)}"
[ -n "$REPO" ] || { printf 'Candidate repository unavailable\n' >&2; exit 2; }
OUT="${NX10_SOAK_OUT_DIR:-${NX10_OUT:-$REPO/docs/qa/2026-09-16-followup/nx10}}"
SCHEDULER="${NX10_SCHEDULER:-$REPO/docs/qa/2026-09-16-followup/nx10/schedule_nx10_soak.sh}"
RUNNER="${NX10_RUNNER:-$REPO/docs/qa/2026-09-16-followup/nx10/run_nx10_soak.sh}"
export NX10_REPO="$REPO" NX10_OUT="$OUT" NX10_SOAK_OUT_DIR="$OUT" NX10_RUNNER="$RUNNER"
PATTERN="${NX10_SCHED_PATTERN:-schedule_nx10_soak.sh}"
GRACE="${NX10_CANCEL_GRACE:-15}"
SCREEN_NAME="${NX10_SCREEN_NAME:-nx10soak}"
# “이미 돌고 있는 soak” 을 알아보는 이름(하네스). 기본값은 실제 하네스이고, **자기시험은 이 값을
# 통제해야 한다** — 그렇지 않으면 진짜 soak 이 돌 때 시험 픽스처가 전부 빨개진다(실측 2026-09-16T23:34Z).
SOAK_PROC_PATTERN="${NX10_SOAK_PROC_PATTERN:-val02_staging.py}"
LOCK="$OUT/.soak-arm.lock"          # 예약(대기 중) 단일 잠금 — scheduler 가 만든다
RUNLOCK="$OUT/.soak-run.lock"       # 8시간 실행 단일 잠금 — runner 가 만든다
EXIT_TXT="$OUT/soak-exit.txt"
SCHED_LOG="$OUT/soak-schedule.log"
SCHEDULE="$OUT/soak-schedule.txt"
VENV_PY="${NX10_PYTHON:-$REPO/.venv/bin/python}"
export NX10_PYTHON="$VENV_PY"

_utc() { date -u +%FT%TZ; }

_py() {
  # 지문 계산은 venv 파이썬으로만 한다 — 시스템 `python` 이 3.9 일 수 있고(실측: /usr/bin/python3),
  # 그러면 `ga_gate.py` 의 3.12 문법에서 SyntaxError 가 나 지문이 UNVERIFIED 로 떨어진다.
  if [ -x "$VENV_PY" ]; then printf '%s' "$VENV_PY"; else printf '%s' python3; fi
}

_tree_fingerprint() {
  (cd "$REPO" && "$(_py)" -c "import sys,pathlib; sys.path.insert(0,'scripts'); import ga_gate; print(ga_gate.worktree_fingerprint(pathlib.Path('.')))" 2>/dev/null) || echo UNVERIFIED
}

_iso_after() { # 남은 초 → 종료 예정 시각(UTC ISO). macOS 에서 epoch→ISO 는 date -r 의 의미가
  # GNU 와 달라서(--reference) 이식성이 없다 — 파이썬으로 계산한다.
  [ -n "${1:-}" ] || return 0
  "$(_py)" -c 'import datetime,sys; print((datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(seconds=int(sys.argv[1]))).strftime("%Y-%m-%dT%H:%M:%SZ"))' "$1" 2>/dev/null || true
}

_secs_since() { # ISO8601(UTC) → 경과 초. 계산 못 하면 빈 문자열(호출자가 줄을 생략한다).
  [ -n "${1:-}" ] || return 0
  "$(_py)" -c 'import datetime,sys; t=datetime.datetime.strptime(sys.argv[1],"%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc); print(int((datetime.datetime.now(datetime.timezone.utc)-t).total_seconds()))' "$1" 2>/dev/null || true
}

_run_field() { # soak-exit.txt 의 **마지막 러너 블록**에서 키 값. 운영자 기록은 `#` 로 시작하므로
  # `^키:` 에 걸리지 않는다(그 구분이 판정기 파서와 같아야 한다).
  sed -n "s/^$1: //p" "$EXIT_TXT" 2>/dev/null | tail -1
}

_run_soak_seconds() { # 러너 블록의 command 줄에서 요청 길이를 읽는다(실행 중 남은 초 계산용)
  grep -o -e '--soak-seconds [0-9][0-9]*' "$EXIT_TXT" 2>/dev/null | tail -1 | awk '{print $2}'
}

# 러너는 **시작할 때** 블록의 앞부분을 쓰고 `end_time`·`exit` 은 끝날 때 덧붙인다. 그래서
# `sed -n s/^key: //p | tail -1` 로 값을 읽으면 **직전 실행의** 값을 읽을 수 있다(회수 판정이
# 겪었던 함정과 같은 종류다). 여기서는 마지막 `generated_at:` 부터만 잘라 쓴다.
_runner_block() {
  awk '/^generated_at: /{buf=""} {buf = buf $0 "\n"} END{printf "%s", buf}' "$EXIT_TXT" 2>/dev/null
}

_block_field() { # $1=key — **마지막 러너 블록** 안에서
  _runner_block | sed -n "s/^$1: //p" | head -1
}

_block_complete() { # 러너가 종료 시에만 쓰는 필드가 다 있는가
  local b
  b="$(_runner_block)"
  printf '%s' "$b" | grep -q '^exit: ' &&
    printf '%s' "$b" | grep -q '^end_time: ' &&
    printf '%s' "$b" | grep -q '^end_fingerprint: '
}

# 패턴에 걸린 프로세스가 **하네스인가** — `comm` 이 파이썬이어야 한다.
#
# 왜 필요한가(실측 2026-09-17): `pgrep -f val02_staging.py` 는 **패턴 문자열을 argv 에 담은 다른 프로세스**도
# 잡는다. 운영자의 진단 명령(`bash -c "… pgrep -f val02_staging.py …"`)이 그렇게 잡혔고, ① 감시 계열에
# 표본 5개가 섞여 “터졌다/내려갔다” 는 없는 그림을 만들었고 ② 도구 쪽에서는 “도는 soak” 오탐 위험이 생겼다.
# 하네스는 `.venv/bin/python scripts/val02_staging.py …` 로 돌므로 인터프리터 여부로 가른다.
_is_harness_pid() {
  local comm
  comm="$(ps -o comm= -p "$1" 2>/dev/null | tr -d ' ')"
  [ -n "$comm" ] || return 1
  comm="$(basename "$comm" | tr 'A-Z' 'a-z')"
  case "$comm" in
    *python*) return 0 ;;
    *) return 1 ;;
  esac
}

# 패턴에 걸린 것 중 **하네스만** — 예약( 스케줄러·래퍼 스크립트)은 여기가 아니라 잠금 주인 경로로 찾는다.
_soak_candidates() {
  local pid pattern="${1:-$SOAK_PROC_PATTERN}"
  for pid in $(pgrep -f -- "$pattern" 2>/dev/null | grep -v -x -e "$$" -e "${PPID:-0}" || true); do
    _is_harness_pid "$pid" && printf '%s\n' "$pid"
  done
}

_soak_pids() { # 지금 실제로 soak 이 돌고 있는가 — 하네스 프로세스 · 실행 잠금 주인 · 아직 기다리는 예약
  local p
  _soak_candidates "$SOAK_PROC_PATTERN"
  p="$(sed -n 's/^pid: //p' "$RUNLOCK/owner" 2>/dev/null | head -1)"
  if [ -n "$p" ] && _alive "$p"; then printf '%s\n' "$p"; fi
  p="$(_lock_owner_pid 2>/dev/null || true)"
  if [ -n "${p:-}" ] && _alive "$p"; then printf '%s\n' "$p"; fi
  return 0
}

_alive() { kill -0 "$1" 2>/dev/null; }

_newest_write_epoch() { # $1=파일 또는 디렉터리 → 그 안(또는 자신)의 마지막 쓰기 epoch(없으면 0)
  "$(_py)" - "$1" <<'PY' 2>/dev/null || echo 0
import os, sys
root = sys.argv[1]
newest = 0.0
if os.path.isdir(root):
    # 디렉터리 **자신**의 mtime 도 본다: 파일을 하나도 안 쓰는 동안에도 디렉터리는 지워지지 않고,
    # 작업디렉터리가 빈 순간에도 답이 필요하다(실측: 빈 디렉터리에서 unknown 이 나와 문이 안 걸렸다).
    try:
        newest = os.path.getmtime(root)
    except OSError:
        pass
    for dirpath, _dirs, files in os.walk(root):
        try:
            newest = max(newest, os.path.getmtime(dirpath))
        except OSError:
            pass
        for name in files:
            try:
                newest = max(newest, os.path.getmtime(os.path.join(dirpath, name)))
            except OSError:
                pass
else:
    try:
        newest = os.path.getmtime(root)
    except OSError:
        pass
print(int(newest))
PY
}

_soak_stall_seconds() { # 지금 도는 실행이 **마지막으로 무엇인가를 쓴 지** 얼마나 됐는가
  # 왜 필요한가(실측 2026-09-17): SC-3 worker 가 죽자 하네스가 영원히 대기했는데, 프로세스는
  # 살아 있었으므로 `_soak_pids` 로는 "도는 중"과 구분되지 않았다. 그 상태를 그대로 두면
  # 끝나지 않는 실행을 하루치 기다리게 된다 — 마지막 쓰기 이후 경과로 그것을 본다.
  local workdir log last=0 w
  workdir="$(_block_field workdir)"
  log="$OUT/soak-run.log"
  for w in "$workdir" "$log"; do
    [ -n "$w" ] || continue
    [ -e "$w" ] || continue
    last="$(_newest_write_epoch "$w")"
    [ "${last:-0}" -gt 0 ] && break
  done
  [ "${last:-0}" -gt 0 ] || { printf 'unknown'; return 0; }
  printf '%s' "$(( $(date +%s) - last ))"
}

_descendants() {
  # 부모 → 자식 BFS(손자 포함). heartbeat 파이썬처럼 **패턴에 안 걸리는** 자식을 놓치지 않으려면
  # 프로세스 목록이 아니라 프로세스 트리로 모아야 한다.
  local pid="$1" queue=("$1") child
  while [ "${#queue[@]}" -gt 0 ]; do
    pid="${queue[0]}"
    queue=("${queue[@]:1}")
    for child in $(pgrep -P "$pid" 2>/dev/null); do
      printf '%s\n' "$child"
      queue+=("$child")
    done
  done
}

_tree_pids() { printf '%s\n' "$1"; _descendants "$1"; }

_in_tree() { # $1=root $2=pid
  local p
  for p in $(_tree_pids "$1"); do
    [ "$p" = "$2" ] && return 0
  done
  return 1
}

# 줄 역순 — macOS 에는 GNU `tac` 이 없다(실측: 첫 자기시험이 `tac: command not found` 로
# 아무것도 죽이지 못하고 "취소 성공"인지 아닌지만 실패로 보고했다. 자식부터 죽이려면 역순이 필요하다).
_reverse_lines() { awk '{a[NR]=$0} END {for (i = NR; i >= 1; i--) print a[i]}'; }

_matches() {
  pgrep -f -- "$PATTERN" 2>/dev/null | grep -v -x -e "$$" -e "${PPID:-0}" || true
}

_roots() {
  # 예약 1건은 프로세스 **2개**로 보인다: `login -pflq … schedule_nx10_soak.sh` 래퍼와 그 아래
  # `bash … schedule_nx10_soak.sh`. 그래서 "살아 있는 예약 수" 는 일치 프로세스 수가 아니라
  # **부모가 일치하지 않는 최상위(루트)** 를 세야 한다 — 실측: 오늘 아침 저장소에서 예약 4건이
  # 12개 프로세스(래퍼 4 · bash 4 · heartbeat 4)로 보였다. 루트를 세면 4건이다.
  local all pid ppid
  all="$(_matches)"
  while read -r pid; do
    [ -n "$pid" ] || continue
    ppid="$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')"
    printf '%s\n' "$all" | grep -q -x "${ppid:-none}" && continue
    printf '%s\n' "$pid"
  done <<< "$all"
}

# ── 잠금 주인 정보 ──────────────────────────────────────────────────────────
_lock_field() { # $1=key
  [ -f "$LOCK/owner" ] || return 1
  sed -n "s/^$1: //p" "$LOCK/owner" | head -1
}

_lock_owner_pid() { _lock_field pid; }

_lock_state() {
  # armed | stale | none
  if [ ! -d "$LOCK" ]; then printf 'none'; return 0; fi
  local pid
  pid="$(_lock_owner_pid)" || { printf 'stale'; return 0; }
  if [ -n "$pid" ] && _alive "$pid"; then printf 'armed'; else printf 'stale'; fi
}

_print_lock() {
  local state pid
  state="$(_lock_state)"
  printf '  잠금: %s (%s)\n' "$state" "$LOCK"
  [ "$state" = "none" ] && return 0
  pid="$(_lock_owner_pid)"
  printf '    pid=%s alive=%s\n' "${pid:-?}" "$(_alive "${pid:-0}" && echo yes || echo no)"
  printf '    expected_fingerprint=%s\n' "$(_lock_field expected_fingerprint || echo '?')"
  printf '    at_local=%s target_utc=%s\n' "$(_lock_field at_local || echo '?')" "$(_lock_field target_utc || echo '?')"
  printf '    armed_at=%s\n' "$(_lock_field armed_at || echo '?')"
}

_remaining() {
  local t
  t="$(_lock_field target_utc)" || return 1
  [ -n "$t" ] || return 1
  "$(_py)" - "$t" <<'PY' || true
import datetime, sys
target = datetime.datetime.fromisoformat(sys.argv[1].replace("Z", "+00:00"))
now = datetime.datetime.now(datetime.timezone.utc)
print(max(0, int((target - now).total_seconds())))
PY
}

# ── status ──────────────────────────────────────────────────────────────────
cmd_status() {
  local state fp_current fp_expected live roots orphans=() pid owner healthy=1 count run_owner
  printf 'NX-10 soak 예약 상태 (%s)\n' "$(_utc)"
  printf '  repo=%s\n  pattern=%s\n' "$REPO" "$PATTERN"

  state="$(_lock_state)"
  _print_lock

  live="$(_matches)"
  roots="$(_roots)"
  count="$(printf '%s\n' "$roots" | grep -c . || true)"
  printf '  살아 있는 예약: %s건 (일치 프로세스 %s개 — 래퍼·heartbeat 포함)\n' \
    "$count" "$(printf '%s\n' "$live" | grep -c . || true)"
  while read -r pid; do
    [ -n "$pid" ] || continue
    printf '    root pid=%s ppid=%s elapsed=%s tree=%s개\n' "$pid" \
      "$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')" \
      "$(ps -o etime= -p "$pid" 2>/dev/null | tr -d ' ')" \
      "$(printf '%s\n' "$(_tree_pids "$pid")" | grep -c .)"
  done <<< "$(printf '%s' "$roots")"

  owner="$(_lock_owner_pid 2>/dev/null || true)"
  while read -r pid; do
    [ -n "$pid" ] || continue
    # 잠금 주인이 자기 트리 안에 있으면 그건 정상 예약이다. 트리 밖에서 도는 것이 고아다
    # (오늘 사고가 난 그 상태 — 취소했다고 기록된 예약이 살아서 대기).
    if [ -n "$owner" ] && _in_tree "$pid" "$owner"; then continue; fi
    orphans+=("$pid")
  done <<< "$(printf '%s' "$roots")"
  printf '  잠금 밖(고아) 예약: %s\n' "${#orphans[@]}"
  [ "${#orphans[@]}" -gt 0 ] && printf '    pids=%s\n' "${orphans[*]}"

  fp_expected="$(_lock_field expected_fingerprint 2>/dev/null || true)"
  fp_current="$(_tree_fingerprint)"

  # 실행 중인 soak 은 **예약 잠금이 없다**(즉시 실행 모드 — `run`). 그러니 "예약 == armed" 를 그대로
  # 요구하면 도는 soak 을 보면서도 영원히 ATTENTION 을 뱉는다(실측 2026-09-16T23:28Z: 8시간 재실행 중
  # `판정: ATTENTION`). 상시 거짓 경보는 다음 사람이 이 줄을 안 읽게 만든다 — 그래서 모드를 먼저 가른다.
  run_owner=""
  if [ -d "$RUNLOCK" ]; then
    run_owner="$(sed -n 's/^pid: //p' "$RUNLOCK/owner" 2>/dev/null | head -1)"
  fi

  if [ -n "$run_owner" ] && _alive "$run_owner"; then
    local started elapsed remaining soak_secs run_fp
    started="$(sed -n 's/^started_at: //p' "$RUNLOCK/owner" 2>/dev/null | head -1)"
    run_fp="$(_run_field start_fingerprint)"
    soak_secs="$(_run_soak_seconds)"
    elapsed="$(_secs_since "${started:-}")"
    printf '  모드: RUNNING (즉시 실행 — 예약 아님) pid=%s alive=yes\n' "$run_owner"
    printf '  지문: 실행 시작=%s\n        현재 트리=%s\n' "${run_fp:-?}" "$fp_current"
    if [ -n "$elapsed" ]; then
      printf '  경과: %s초' "$elapsed"
      if [ -n "$soak_secs" ]; then
        remaining=$((soak_secs - elapsed))
        printf ' · 남은 초: %s · 종료 예정: %s' "$remaining" "$(_iso_after "$remaining")"
      fi
      printf '\n'
    fi
    [ "${#orphans[@]}" -gt 0 ] && healthy=0
    if [ -z "$run_fp" ]; then
      printf '  판정: ATTENTION — 실행 중인데 기록에서 시작 지문을 찾지 못했다(이 실행은 후보에 붙일 수 없다)\n'
      return 1
    fi
    if [ "$run_fp" != "$fp_current" ]; then
      printf '  판정: ATTENTION — 실행 중인데 트리 지문이 시작값과 다르다(이 실행은 후보에 붙일 수 없다)\n'
      return 1
    fi
    printf '  판정: RUNNING — 시작 지문 == 현재 트리. 이 창은 `docs/` 만 수정한다(코드 스코프 편집 금지)\n'
    return 0
  fi

  # 여기부터는 대기 중(예약) 상태의 판정이다.
  if [ -n "$run_owner" ]; then
    printf '  모드: 실행 잠금의 주인(pid=%s)이 죽었다 — 죽은 잠금은 증거로 남긴다\n' "$run_owner"
  fi
  printf '  지문: 기대=%s\n        현재=%s\n' "${fp_expected:-?}" "$fp_current"
  [ "${#orphans[@]}" -gt 0 ] && healthy=0
  [ "$state" = "armed" ] || healthy=0
  [ "$count" = "1" ] || healthy=0
  if [ -n "$fp_expected" ] && [ "$fp_expected" != "$fp_current" ]; then healthy=0; fi
  if [ "$state" = "armed" ]; then
    printf '  발화까지 남은 초: %s\n' "$(_remaining)"
  fi
  if [ "$healthy" = "1" ]; then
    printf '  판정: OK — 단일 예약 · 지문 일치\n'
    return 0
  fi
  printf '  판정: ATTENTION — 단일 예약이 아니거나 지문이 다르다(위 참조)\n'
  return 1
}

cmd_orphans() {
  local owner pid found=0
  owner="$(_lock_owner_pid 2>/dev/null || true)"
  while read -r pid; do
    [ -n "$pid" ] || continue
    if [ -n "$owner" ] && _in_tree "$pid" "$owner"; then continue; fi
    printf '%s\n' "$pid"
    found=1
  done <<< "$(_roots)"
  [ "$found" = "1" ] && return 0 || return 1
}

# ── arm ─────────────────────────────────────────────────────────────────────
cmd_arm() {
  local at="22:00" fp="" state owner live roots
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --at) at="$2"; shift 2 ;;
      --fp) fp="$2"; shift 2 ;;
      *) printf '알 수 없는 인자: %s\n' "$1" >&2; return 2 ;;
    esac
  done
  [ -n "$fp" ] || fp="$(_tree_fingerprint)"
  if [ "$fp" = "UNVERIFIED" ]; then
    printf '거부: 지문을 계산하지 못했다(UNVERIFIED). 예약하면 22:00 에 스스로 중단된다.\n' >&2
    return 2
  fi

  roots="$(_roots)"
  if [ -n "$roots" ]; then
    printf '거부: 이미 살아 있는 예약이 있다(중복 예약 금지 — 오늘 사고의 원인).\n' >&2
    printf '%s\n' "$roots" | sed 's/^/  root pid=/' >&2
    printf '먼저 cancel 로 **죽었는지 확인**하고 다시 걸어라.\n' >&2
    return 2
  fi
  state="$(_lock_state)"
  case "$state" in
    armed)
      owner="$(_lock_owner_pid)"
      printf '거부: 잠금 주인(pid=%s)이 살아 있다.\n' "$owner" >&2
      return 2
      ;;
    stale)
      # 죽은 주인의 잠금은 증거로 남기고 물려받는다(지우지 않는다).
      mv "$LOCK" "$LOCK.stale-$(date -u +%Y%m%dT%H%M%SZ)"
      printf '참고: 죽은 주인의 잠금을 %s 로 밀어 두고 새로 건다.\n' "$(basename "$LOCK")".stale-* >&2
      ;;
  esac

  if [ ! -f "$SCHEDULER" ]; then
    printf '거부: 예약 스크립트가 없다: %s\n' "$SCHEDULER" >&2
    return 2
  fi

  printf '예약 발사: at=%s(로컬) fp=%s\n' "$at" "$fp"
  NX10_SOAK_AT="$at" NX10_EXPECT_FINGERPRINT="$fp" NX10_REPO="$REPO" NX10_OUT="$OUT" \
    NX10_RUNNER="$RUNNER" \
    screen -dmS "$SCREEN_NAME" bash "$SCHEDULER"
  local rc=$?
  if [ "$rc" != "0" ]; then
    printf '실패: screen 실행 rc=%s\n' "$rc" >&2
    return "$rc"
  fi
  # 예약 스크립트가 잠금을 잡았는지 확인 — 잡았다는 것은 실제로 대기 중이라는 뜻이다.
  local waited=0
  while [ "$waited" -lt 20 ]; do
    if [ "$(_lock_state)" = "armed" ]; then break; fi
    sleep 1
    waited=$((waited + 1))
  done
  if [ "$(_lock_state)" != "armed" ]; then
    printf '경고: 예약 프로세스가 20초 안에 잠금을 잡지 않았다. status 로 확인하라.\n' >&2
    cmd_status
    return 3
  fi
  printf '예약 완료.\n'
  cmd_status
}

# ── cancel ──────────────────────────────────────────────────────────────────
_die_verified() { # $1=root pid  → 0 = 죽었다(검증됨), 1 = 살아 있다/검증 불가
  local pid="$1" waited=0 p
  local pids
  pids="$(_tree_pids "$pid" | _reverse_lines)"
  if [ -z "$pids" ]; then
    # 열거조차 못 했으면 "죽었다"고 주장하지 않는다(검증 못 한 성공을 만들지 않는다).
    printf '    프로세스 트리 열거 실패 — 죽음을 검증할 수 없다\n'
    return 1
  fi
  for p in $pids; do kill -TERM "$p" 2>/dev/null; done
  while [ "$waited" -lt "$GRACE" ]; do
    local any=0
    for p in $pids; do _alive "$p" && any=1; done
    [ "$any" = "0" ] && return 0
    sleep 1
    waited=$((waited + 1))
  done
  # SIGTERM 을 무시하는 프로세스(트랩 등)는 KILL 로 승격한다 — 조용히 남겨 두지 않는다.
  printf '    TERM 무시 %s초 경과 → KILL 승격\n' "$GRACE"
  for p in $pids; do kill -KILL "$p" 2>/dev/null; done
  sleep 2
  for p in $pids; do _alive "$p" && return 1; done
  return 0
}

cmd_cancel() {
  local live pid state failed=0
  live="$(_roots)"
  if [ -z "$live" ]; then
    state="$(_lock_state)"
    printf '살아 있는 예약 프로세스가 없다(잠금 상태: %s).\n' "$state"
    if [ "$state" = "stale" ]; then
      printf '  죽은 주인의 잠금만 남아 있다 → 해제한다.\n'
      rm -rf "$LOCK"
    elif [ "$state" = "none" ]; then
      printf '  해제할 잠금도 없다.\n'
    fi
    _record_cancel "살아 있는 예약 없음(잠금 상태 $state)" "확인: pgrep 0건"
    return 0
  fi

  printf '취소 대상 %s개:\n' "$(printf '%s\n' "$live" | grep -c .)"
  while read -r pid; do
    [ -n "$pid" ] || continue
    printf '  pid=%s → 트리 종료 시도(자식 포함)\n' "$pid"
    if _die_verified "$pid"; then
      printf '    [OK] 죽음 확인\n'
    else
      printf '    [FAIL] 아직 살아 있다 — 취소가 끝나지 않았다\n'
      failed=1
    fi
  done <<< "$live"

  if [ "$failed" = "0" ]; then
    rm -rf "$LOCK"
    printf '  잠금 해제.\n'
  fi
  # 검증: 다시 훑어서 0건인지 본다(오늘 사고는 바로 이 확인이 없어서 생겼다).
  live="$(_roots)"
  if [ -n "$live" ]; then
    printf '검증 실패: 아직 %s개가 살아 있다:\n' "$(printf '%s\n' "$live" | grep -c .)"
    printf '%s\n' "$live" | sed 's/^/  pid=/'
    failed=1
  else
    printf '검증: 살아 있는 예약 0건.\n'
  fi
  _record_cancel "취소 요청(pgrep -f $PATTERN)" "$(if [ "$failed" = 0 ]; then echo '검증: 0건 — 죽음 확인'; else echo '검증 FAIL: 잔존 프로세스 있음'; fi)"
  [ "$failed" = "0" ] && return 0 || return 3
}

_record_run_expectation() { # $1=pid  $2=지문(빈 값이면 계산)  $3=기록 대상(기본 $SCHEDULE · 시험용)
  # 이 실행이 **무엇을 재려 하는지**를 예약 이력에 남긴다 — 판정기의 기대 지문이 여기서 온다.
  #
  # 왜 필요한가(2026-09-17 실측): 예약(`arm`)은 블록을 남기지만 **즉시 실행(`run`)은 아무것도 남기지
  # 않았다**. 그래서 판정기는 “마지막 예약”을 기대값으로 집었고, 그 마지막은 ① 중단된 예약(한 틱도 안 돎)
  # 이거나 ② **철 지난 다른 트리의 예약**이었다. 4차 실행(지표 all_pass · exit 0 · 8h00m04s ·
  # 시작==종료==현재 트리)이 그 지문과 달라 FAIL 로 판정됐다 — 없던 근거를 만들어 낸 것이 아니라
  # **있던 낡은 근거를 집은** 것이다. 이 실행의 기대값은 이 실행이 적는다.
  local pid="$1" fp="${2:-}" target="${3:-$SCHEDULE}"
  [ -n "$fp" ] || fp="$(_tree_fingerprint)"
  {
    echo ""
    echo "# NX-10 soak 예약 기록 (즉시 실행 — 예약 없이 시작)"
    echo "recorded_at: $(_utc)"
    echo "mode: run (immediate)"
    echo "runner: $RUNNER"
    echo "pid: $pid"
    if [ "$fp" != "UNVERIFIED" ]; then
      echo "expected_fingerprint: $fp"
      echo "expected_fingerprint_source: 시작 시점 트리(즉시 실행 — 예약 블록이 없다)"
    else
      # 계산 실패를 “그냥 진행” 으로 넘기지 않는다: 기대값을 **주장하지 않고** 판정기가 러너 기록으로
      # 내려가게 둔다(그때는 출처가 문장으로 남는다).
      echo "expected_fingerprint: UNVERIFIED"
      echo "expected_fingerprint_source: 계산 실패 — 기대값을 주장하지 않는다(판정기는 러너 기록으로 내려간다)"
    fi
  } >> "$target"
}


_record_cancel() {
  {
    echo ""
    echo "# ── 운영자 기록: 예약 취소 (soak_control.sh cancel) ──"
    echo "cancel_recorded_at: $(_utc)"
    echo "cancel_method: soak_control.sh cancel (SIGTERM → $GRACE 초 대기 → SIGKILL, 트리 단위)"
    echo "cancel_target: $1"
    echo "cancel_verification: $2"
  } >> "$EXIT_TXT"
  printf '%s cancel: %s / %s\n' "$(_utc)" "$1" "$2" >> "$SCHED_LOG"
}

# ── preflight ────────────────────────────────────────────────────────────────
# 22:00 발화 **전에** 답해야 하는 질문: “이 예약은 돌 것이고, 돌면 쓸 수 있는 값이 나오는가?”
# 지금 결함을 알면 고칠 수 있고, 06:00 에 알면 밤을 버린다. 그래서 8시간이 의존하는 것들을 먼저 본다:
# 예약이 단일·유효한가 · 지문이 **커밋된 후보**의 것인가 · 인터프리터·러너 자산이 있는가 ·
# 작업디렉터리(기본 `/tmp`)에 여유가 있는가 · **이미 다른 soak 이 돌고 있지 않은가** · 그리고
# **이 작업량이 8시간에 의미 있는 양을 하는가**(처리량 하한 — 2026-09-16 실패의 사각지대).
# 종료 코드: 전부 OK 0, 하나라도 FAIL 1.
_pf_total=0
_pf_failed=0

_pf_check() { # 이름 결과 상세
  _pf_total=$((_pf_total + 1))
  if [ "$2" = "1" ]; then
    printf '  [OK  ] %s%s\n' "$1" "${3:+ — $3}"
  else
    _pf_failed=$((_pf_failed + 1))
    printf '  [FAIL] %s%s\n' "$1" "${3:+ — $3}"
  fi
}

_commit_fingerprint() {
  (cd "$REPO" && "$(_py)" -c "import sys,pathlib; sys.path.insert(0,'scripts'); import ga_gate; print(ga_gate.tree_fingerprint_of_commit(pathlib.Path('.'),'HEAD'))" 2>/dev/null) || echo UNVERIFIED
}

_end_of_run() { # 예약 발화 + 8시간(28800s) → UTC 문자열. 못 구하면 빈 값.
  local t
  t="$(_lock_field target_utc)" || return 1
  [ -n "$t" ] || return 1
  "$(_py)" - "$t" <<'PY'
import datetime, sys
t = datetime.datetime.fromisoformat(sys.argv[1].replace("Z", "+00:00")) + datetime.timedelta(seconds=28800)
print(t.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
PY
}

_free_mb() { # $1=디렉터리 → MiB
  df -m "$1" 2>/dev/null | awk 'NR==2 {print $4}' || echo 0
}

_hard_cap_mb() { # 유효 hard cap(MiB). 우선순위: 환경변수 > 러너가 선언한 기본값 > 제품 기본값
  # 러너가 선언한 기본값을 읽는 이유: 그 값이 이 soak 의 실제 hard cap 이고(러너가 export 한다),
  # preflight 는 **다른 프로세스**라 그 env 를 물려받지 못한다. 커플링이지만 위험한 방향이 아니다 —
  # 러너가 선언을 멈추면 제품 기본값(512)으로 내려가고, 그때는 이 점검이 **더 엄격해진다**.
  local v="${AGK_CONVERSATION_JOURNAL_HARD_CAP_MB:-}"
  if [ -z "$v" ]; then
    v="$(sed -n 's/.*AGK_CONVERSATION_JOURNAL_HARD_CAP_MB:-\([0-9][0-9]*\).*/\1/p' "$RUNNER" 2>/dev/null | head -1)"
  fi
  if [ -z "$v" ]; then
    v="$(sed -n 's/.*DEFAULT_HARD_CAP_MB: Final = \([0-9][0-9]*\).*/\1/p' \
      "$REPO/src/antigravity_k/engine/conversation_retention.py" 2>/dev/null | head -1)"
  fi
  printf '%s' "${v:-512}"
}

_pf_journal_check() { # $1=프루브 작업디렉터리 $2=프루브 초 — 쓰기량 투영 vs hard cap
  # 왜 이 항목이 있는가(실측 2026-09-17): 꼬리 창 수정으로 append 가 20배 빨라지자 8시간 soak 이
  # journal 을 ≈160 KB/s 로 쓰게 됐고, **기본 hard cap 512 MiB 를 50분 만에 넘겼다**(중단 시점 439 MiB).
  # ADR-DAT-02 는 자동 prune 을 금지하므로 넘긴 뒤에는 **모든 append 가 507 로 거절**되고, 하네스는
  # 그것을 `errors` 로 세므로(`SC-6 pass` 조건에 `errors == 0`) 새 실행이 **설정 때문의 거짓 FAIL**
  # 이 된다. 처리량 하한과 같은 가족의 사각지대이다 — 시작 전에 보이는 것을 시작 전에 본다.
  local jbytes cap_mb projected_mb jdisp
  jbytes="$("$(_py)" -c 'import glob,os,sys; print(sum(os.path.getsize(p) for p in glob.glob(os.path.join(sys.argv[1],"soak-conversations","**","*.jsonl"),recursive=True)))' "$1" 2>/dev/null | tr -dc '0-9')"
  case "${jbytes:-}" in ''|*[!0-9]*) jbytes=0 ;; esac
  [ "${2:-0}" -gt 0 ] || return 0
  cap_mb="$(_hard_cap_mb)"
  projected_mb=$(( jbytes * 28800 / $2 / 1048576 ))
  if [ "$jbytes" = "0" ]; then
    _pf_check "예상 journal 쓰기량 < hard cap" 0 \
      "프루브가 journal 을 만들지 않았다 — 측정할 수 없다(경로·권한 확인)"
    return 1
  fi
  # 여유 10% 를 요구한다 — 투영은 선형이지만 실제 곡선은 초반이 더 느리므로, 90% 를 넘으면 넘길 여지가 없다.
  # 프루브는 5초라 MiB 가 0 으로 보일 수 있다 — KiB 로 내려 읽을 수 있게 한다(0 MiB 로 보이면 못 읽는다).
  if [ "$jbytes" -ge 1048576 ]; then
    jdisp="$(( jbytes / 1048576 )) MiB"
  else
    jdisp="$(( jbytes / 1024 )) KiB"
  fi
  if [ "$(( projected_mb * 10 ))" -lt "$(( cap_mb * 9 ))" ]; then
    _pf_check "예상 journal 쓰기량 < hard cap" 1 \
      "${2}초 ${jdisp} → 8시간 외삽 ${projected_mb} MiB < cap ${cap_mb} MiB"
    return 0
  fi
  _pf_check "예상 journal 쓰기량 < hard cap" 0 \
    "8시간 외삽 ${projected_mb} MiB ≥ cap ${cap_mb} MiB 의 90% — 그러면 50분쯤 뒤부터 append 가 507 로 거절되고 하네스가 그것을 errors 로 세서 **설정 때문의 거짓 FAIL** 이 된다(러너의 AGK_CONVERSATION_JOURNAL_HARD_CAP_MB 를 올려라)"
  return 1
}

_pf_throughput() {
  # 왜 이 항목이 있는가: 2026-09-16 의 8시간 soak 은 **60초에 2,978 ops(49.6 ops/s)** 를 내고도
  # preflight 를 통과했고, 8시간 뒤 **70,430 ops(2.45 ops/s)** 로 끝났다. 원인은 `journal.tail()` 이
  # append 마다 journal 전체를 파싱한 것이고, 그래서 시간이 갈수록 느려졌다(파일이 커지므로).
  # 즉 "시작할 때 잠깐 재본 값"만으로는 부족하지만, **많이 느린 것**은 시작 전에 보인다 —
  # 그 실행의 60초 값은 정상의 1%였다. 이 프루브가 8시간을 태우기 전에 그 사실을 말한다.
  local secs rate dir out ops log rc measured projected
  secs="${NX10_PREFLIGHT_PROBE_SECONDS:-60}"
  # **비율**로 잡는다(절대 개수가 아니다): 프루브 길이를 바꿔도 기준이 같은 뜻을 가지게 하려는 것이다.
  # 기준 근거(실측): 고친 코드 486 ops/s(60초 29,180) · 고장난 코드 49.6 ops/s(60초 2,978, 평균 2.45 ops/s).
  # 기본 133/s = 고친 코드의 27% · 고장난 60초 값의 2.7배 — 기계 속도 차이를 견디는 폭이다.
  rate="${NX10_PREFLIGHT_MIN_OPS_PER_SEC:-133}"
  if ! dir="$(mktemp -d "${TMPDIR:-/tmp}/nx10-preflight-XXXXXX")"; then
    _pf_check "처리량 프루브(임시 디렉터리)" 0 "mktemp 실패"
    return 1
  fi
  out="$dir/probe.json"
  log="$dir/probe.log"
  # SC-6 만 돌리면 리포트는 `missing_required: SC-1..SC-5` 를 담고 main() 이 **exit 1** 을 낸다 —
  # 그래서 성공 판정은 exit code 가 아니라 **리포트가 나왔는가** 로 한다(이걸 exit code 로 보면
  # 프루브가 매번 실패로 보인다 — 실측으로 겪었다).
  (cd "$REPO" && PYTHONPATH=src "$(_py)" scripts/val02_staging.py --scenarios SC-6 \
    --soak-seconds "$secs" --workdir "$dir/work" --output "$out") >"$log" 2>&1
  rc=$?
  ops="$("$(_py)" -c 'import json,sys; d=json.load(open(sys.argv[1])); print(next(s["completed_ops"] for s in d["scenarios"] if s["scenario"]=="SC-6-soak"))' "$out" 2>/dev/null | tr -dc '0-9')"
  case "${ops:-}" in ''|*[!0-9]*) ops=0 ;; esac
  [ "$secs" -gt 0 ] || secs=60
  measured=$((ops / secs))
  projected=$((ops * 28800 / secs))
  if [ "$ops" = "0" ]; then
    _pf_check "처리량 하한 ≥ ${rate} ops/s" 0 \
      "SC-6 프루브가 리포트를 내지 않았다(exit=$rc, 0 ops) — 로그를 남겨 둔다: $log"
    return 1
  fi
  if [ "$measured" -ge "$rate" ]; then
    _pf_check "처리량 하한 ≥ ${rate} ops/s" 1 \
      "실측 ${measured} ops/s(${secs}초 ${ops} ops · 8시간 외삽 ≈${projected} ops)"
    _pf_journal_check "$dir/work" "$secs" || true   # 실패는 _pf_check 가 이미 셌다
    rm -rf "$dir"
    return 0
  fi
  _pf_check "처리량 하한 ≥ ${rate} ops/s" 0 \
    "실측 ${measured} ops/s(${secs}초 ${ops} ops · 8시간 외삽 ≈${projected} ops) — 프루브 로그: $log"
  return 1
}

cmd_preflight() {
  # `NX10_PF_SKIP_RESERVATION=1` 이면 **예약과 무관한** 점검만 한다 — 즉시 시작(`run`)이 그 경로를 쓴다
  # (예약이 없으면 “발화까지 남은 초”도 “기대 지문”도 정의되지 않는다. 두 경로가 같은 함수를 쓰는 이유는
  # 한쪽만 재는 사각지대를 만들지 않기 위해서다).
  local skip_res="${NX10_PF_SKIP_RESERVATION:-0}"
  local roots owner state fp_now fp_commit fp_expected cmd remaining minfree free target_utc
  _pf_total=0
  _pf_failed=0
  printf 'NX-10 soak 발화 전 점검 (%s)%s\n  repo=%s\n' "$(_utc)" \
    "$([ "$skip_res" = "1" ] && echo ' — 즉시 시작 모드(예약 점검 제외)' || echo '')" "$REPO"

  # ① 예약은 하나이고, 살아 있고, **그 프로세스가 맞는가**(pid 재사용·유령 잠금 방지)
  if [ "$skip_res" != "1" ]; then
  roots="$(_roots)"
  owner="$(_lock_owner_pid 2>/dev/null || true)"
  local nroots
  nroots="$(printf '%s\n' "$roots" | grep -c . || true)"
  cmd="$(ps -o command= -p "${owner:-0}" 2>/dev/null || true)"
  _pf_check "예약 프로세스 단일(루트 1개)" "$([ "$nroots" = "1" ] && echo 1 || echo 0)" "roots=$nroots"
  if [ -n "$owner" ] && _alive "$owner" && printf '%s' "$cmd" | grep -q -- "$PATTERN"; then
    _pf_check "잠금 주인이 살아 있는 예약 프로세스" 1 "pid=$owner"
  else
    _pf_check "잠금 주인이 살아 있는 예약 프로세스" 0 "pid=${owner:-없음} cmd=${cmd:-없음} — 유령/재사용 의심"
  fi
  state="$(_lock_state)"
  _pf_check "잠금 상태=armed" "$([ "$state" = "armed" ] && echo 1 || echo 0)" "state=$state"
  fi # ← skip_res 끝

  # ② 지문: (예약 시) 기대 == 지금 트리 **그리고** 지금 트리 == HEAD 트리(= 커밋된 후보)
  fp_expected="$(_lock_field expected_fingerprint 2>/dev/null || true)"
  fp_now="$(_tree_fingerprint)"
  fp_commit="$(_commit_fingerprint)"
  if [ "$skip_res" != "1" ]; then
  _pf_check "기대 지문 == 현재 트리" "$([ -n "$fp_expected" ] && [ "$fp_expected" = "$fp_now" ] && echo 1 || echo 0)" \
    "기대=${fp_expected:0:12}… 현재=${fp_now:0:12}…"
  fi
  # 이 항등식이 “soak 이 재는 것이 커밋된 후보”라는 뜻이다(아니면 결과를 후보에 귀속할 수 없다).
  # `NX10_PF_SKIP_ATTRIBUTION=1` 은 ** 이 항목만** 생략한다 — 승격 리허설처럼 “작업 트리가 일부러
  # 더러운” 환경에서 자기시험을 돌리기 위한 문이다(2026-09-17 3차 승격 리허설이 실제로 이것을 막혔다:
  # 미러는 이동을 재현하므로 커밋된 후보와 다를 수밖에 없고, 자기시험의 두 단언이 그 때문에 빨개졌다).
  # 생략된 사실을 점검 목록에 **드러낸다** — 조용한 구멍으로 만들지 않는다.
  if [ "${NX10_PF_SKIP_ATTRIBUTION:-0}" = "1" ]; then
    _pf_check "후보 귀속(생략됨)" 1 "NX10_PF_SKIP_ATTRIBUTION=1 — 작업 트리가 일부러 더러울 때만 쓴다"
  else
    _pf_check "현재 트리 == HEAD 트리(커밋된 후보)" "$([ "$fp_commit" != "UNVERIFIED" ] && [ "$fp_now" = "$fp_commit" ] && echo 1 || echo 0)" \
      "HEAD=${fp_commit:0:12}…"
  fi

  # ③ 발화가 미래인가(지나간 예약을 붙잡고 앉아 있지 않은가)
  remaining="$(_remaining 2>/dev/null || echo 0)"
  target_utc="$(_lock_field target_utc 2>/dev/null || true)"
  if [ "$skip_res" != "1" ]; then
  _pf_check "발화 시각이 아직 오지 않았다" "$([ "${remaining:-0}" -gt 0 ] && echo 1 || echo 0)" "남은=${remaining}s"
  fi

  # ④ 인터프리터가 지문을 계산할 수 있는가(3.9 로 해석되면 UNVERIFIED 로 스스로 중단된다)
  if "$(_py)" -c "import sys; sys.path.insert(0,'$REPO/scripts'); import ga_gate" >/dev/null 2>&1; then
    _pf_check "인터프리터가 ga_gate 를 임포트한다" 1 "$(_py) $("$(_py)" -V 2>&1)"
  else
    _pf_check "인터프리터가 ga_gate 를 임포트한다" 0 "$(_py) 로 실패(3.12 문법 필요)"
  fi

  # ⑤ 8시간이 필요로 하는 자산이 그 자리에 있는가
  local missing=() f
  for f in "$SCHEDULER" "$RUNNER" "$REPO/scripts/val02_staging.py" "$REPO/scripts/ga_gate.py" "$REPO/src/antigravity_k"; do
    [ -e "$f" ] || missing+=("$f")
  done
  _pf_check "러너·측정 자산 존재" "$([ "${#missing[@]}" -eq 0 ] && echo 1 || echo 0)" "${missing[*]:-전부 있음}"

  # ⑥ 작업디렉터리 여유(8시간 soak 은 `/tmp` 에 수백 MB~GB 를 쓴다)
  minfree="${NX10_PREFLIGHT_MIN_FREE_MB:-2048}"
  free="$(_free_mb /tmp)"
  _pf_check "작업디렉터리 여유 ≥ ${minfree} MiB" "$([ "${free:-0}" -ge "$minfree" ] && echo 1 || echo 0)" "/tmp 여유=${free} MiB"

  # ⑦ 이미 돌고 있는 soak 이 없는가 — **기계 전체**를 본다(다른 디렉터리에서 시작됐어도 두 개가 동시에
  #    돌면 서로의 처리량·RSS 측정을 오염시킨다). 이름은 $SOAK_PROC_PATTERN 으로 통제한다.
  local running
  running="$(_soak_candidates "$SOAK_PROC_PATTERN" | tr '\n' ' ')"
  if [ -n "$running" ]; then
    _pf_check "다른 soak 실행 없음" 0 "$SOAK_PROC_PATTERN pid=$running"
  else
    local rpid
    rpid="$(sed -n 's/^pid: //p' "$RUNLOCK/owner" 2>/dev/null | head -1)"
    if [ -n "$rpid" ] && _alive "$rpid"; then
      _pf_check "다른 soak 실행 없음" 0 "실행 잠금 주인 pid=$rpid 가 살아 있다"
    else
      _pf_check "다른 soak 실행 없음" 1 "실행 잠금 없음 · $SOAK_PROC_PATTERN 0건"
    fi
  fi

  # ⑧ 처리량 하한 — 8시간을 태우기 전에 "이 작업량이 8시간에 의미 있는 양을 하는가"를 잰다.
  # 60초 프루브라 `run` 경로에서는 시작이 1분 늦어지고, 그 대가로 밤을 지킨다.
  if [ "${NX10_PREFLIGHT_SKIP_THROUGHPUT:-0}" = "1" ]; then
    _pf_check "처리량 하한(생략됨)" 1 "NX10_PREFLIGHT_SKIP_THROUGHPUT=1"
  else
    _pf_throughput || true   # 실패는 _pf_check 가 이미 셌다(여기서 종료 코드를 죽이지 않는다)
  fi

  # 참고(실패 아님): 화면 세션·잠자기. 예약은 대기 구간에 caffeinate 를 걸지 않는다.
  printf '  [note] screen 세션: %s개\n' "$(screen -ls 2>/dev/null | grep -c "\.${SCREEN_NAME}[[:space:]]" | tr -d ' ')"
  if [ "$skip_res" != "1" ]; then
    printf '  [note] 발화까지: %ss · 발화 예정: %s · 종료 예정(발화+8h): %s\n' "$remaining" \
      "${target_utc:-?}" "$(_end_of_run 2>/dev/null || echo '?')"
  fi
  printf '  [note] 뚜껑을 닫으면 잠들어 발화를 놓칠 수 있다(대기 구간에 caffeinate 를 걸지 않았다).\n'

  printf '\n  PREFLIGHT: %s/%s OK\n' "$((_pf_total - _pf_failed))" "$_pf_total"
  [ "$_pf_failed" = "0" ] && return 0 || return 1
}

# ── run — 예약을 기다리지 않고 **지금** 시작한다 ────────────────────────────
# 수동 타이핑은 오늘 사고가 난 바로 그 자리다(caffeinate 를 빼먹으면 기기가 자고, screen 을 빼먹으면
# 터미널을 닫을 때 죽는다). 그래서 포장은 도구가 한다: **예약과 같은 preflight** 를 통과해야 시작하고,
# 이미 예약이 걸려 있으면 거부하며(두 개가 뜨지 않게), 시작 뒤 실행 잠금·프로세스를 확인한다.
cmd_run() {
  local roots rpid waited=0
  if ! NX10_PF_SKIP_RESERVATION=1 cmd_preflight; then
    printf '\n거부: 위 점검이 실패했다 — 이 상태로 8시간을 시작하지 않는다.\n' >&2
    return 2
  fi
  roots="$(_roots)"
  if [ -n "$roots" ]; then
    printf '거부: 예약이 이미 걸려 있다. 두 개가 뜨지 않도록 먼저 `cancel` 로 내려라.\n' >&2
    printf '%s\n' "$roots" | sed 's/^/  root pid=/' >&2
    return 2
  fi
  if [ ! -f "$RUNNER" ]; then
    printf '거부: 러너가 없다: %s\n' "$RUNNER" >&2
    return 2
  fi
  printf '\n즉시 시작: %s\n' "$RUNNER"
  # 예약 경로와 **같은 포장**(화면 + caffeinate -i)으로 띄운다.
  if [ "${NX10_NO_CAFFEINATE:-0}" = "1" ] || ! command -v caffeinate >/dev/null 2>&1; then
    printf '  (caffeinate 없이 시작 — 대기 중 잠들 수 있다)\n'
    screen -dmS "$SCREEN_NAME" bash "$RUNNER"
  else
    screen -dmS "$SCREEN_NAME" caffeinate -i bash "$RUNNER"
  fi
  while [ "$waited" -lt 30 ]; do
    rpid="$(sed -n 's/^pid: //p' "$RUNLOCK/owner" 2>/dev/null | head -1)"
    if [ -n "$rpid" ] && _alive "$rpid"; then break; fi
    sleep 1
    waited=$((waited + 1))
  done
  if [ -z "${rpid:-}" ] || ! _alive "$rpid"; then
    printf '경고: 러너가 30초 안에 실행 잠금을 잡지 않았다 — %s 를 보라.\n' "$OUT/soak-run.log" >&2
    return 3
  fi
  printf '시작됨: 실행 잠금 pid=%s · 화면 세션 %s\n' "$rpid" "$SCREEN_NAME"
  printf '  확인: tail -3 %s · tail -f %s\n' "$EXIT_TXT" "$OUT/soak-run.log"
  printf '%s run: 즉시 시작(pid %s, caffeinate=%s)\n' "$(_utc)" "$rpid" \
    "$([ "${NX10_NO_CAFFEINATE:-0}" = "1" ] && echo no || echo yes)" >> "$SCHED_LOG"
  # 이 실행의 기대 지문을 기록한다 — 판정기가 낡은 예약 대신 **이 블록**을 근거로 쓴다.
  _record_run_expectation "$rpid" ""
  return 0
}

# ── harvest — 8시간 뒤 회수를 **기다렸다가 한 번에** 한다 ───────────────────
# 왜 도구가 하는가: 회수는 (a) 러너가 종료 시에만 `end_*`·`exit` 를 쓰므로 **끝난 뒤**에만 성립하고,
# (b) 그 시각이 깨어 있는 시각과 겹친다는 보장이 없다. 손으로 두 번(기다렸다가, 다시 판정) 하는 대신
# 한 번 띄워 두며, `--detach` 를 쓰면 화면 세션에서 돌아 창이 재시작돼도 살아남는다.
# 종료 코드: 판정기의 exit 그대로(0=PASS) · 2 인자 · 3 회수할 실행 없음(마지막 블록 미완성) ·
#            4 `--no-wait` 인데 아직 돌고 있다 · 5 대기 시간 초과.
_harvest_cmdline() { # $1=timeout $2=poll $3=judge $4=log — 화면 세션에 넘길 한 줄(경로 인용)
  printf 'bash %q harvest --timeout %s --poll %s --judge %q >> %q 2>&1' "$0" "$1" "$2" "$3" "$4"
}

cmd_harvest() {
  local detach=0 no_wait=0 timeout="${NX10_HARVEST_TIMEOUT:-43200}" poll="${NX10_HARVEST_POLL:-60}"
  local judge="${NX10_JUDGE:-$REPO/scripts/collect_soak_result.py}"
  local hscreen="${NX10_HARVEST_SCREEN:-nx10harvest}"
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --detach) detach=1; shift ;;
      --no-wait) no_wait=1; shift ;;
      --timeout) timeout="$2"; shift 2 ;;
      --poll) poll="$2"; shift 2 ;;
      --judge) judge="$2"; shift 2 ;;
      *) printf '알 수 없는 인자: %s\n' "$1" >&2; return 2 ;;
    esac
  done
  local hlog="$OUT/soak-harvest.log"
  if [ "$detach" = 1 ]; then
    local cmd
    cmd="$(_harvest_cmdline "$timeout" "$poll" "$judge" "$hlog")"
    if [ "${NX10_NO_CAFFEINATE:-0}" = "1" ] || ! command -v caffeinate >/dev/null 2>&1; then
      screen -dmS "$hscreen" bash -c "$cmd"
    else
      # 대기 구간에 기기가 잠들면 판정이 밀린다 — `run` 과 같은 포장을 쓴다.
      screen -dmS "$hscreen" caffeinate -i bash -c "$cmd"
    fi
    printf '회수 감시를 화면 세션에 띄움: %s\n  기록: %s\n  확인: screen -ls · tail -f %s\n' \
      "$hscreen" "$hlog" "$hlog"
    return 0
  fi

  local pids waited=0
  pids="$(_soak_pids)"
  if [ -n "$pids" ]; then
    if [ "$no_wait" = 1 ]; then
      printf '거부: 아직 soak 이 돌고 있다(pid %s). 회수 판정은 **끝난 뒤**에만 성립한다 —\n' \
        "$(printf '%s' "$pids" | tr '\n' ' ')" >&2
      printf '      러너는 종료 시에만 end_time·exit 를 쓰므로 지금 판정하면 옛 값을 읽는다.\n' >&2
      return 4
    fi
    local stall max_stall="${NX10_HARVEST_MAX_STALL:-1800}"
    printf '회수 대기: 도는 soak 이 끝나기를 기다린다(최대 %ss · %s초 간격 · 무응답 상한 %ss)\n' \
      "$timeout" "$poll" "$max_stall"
    while :; do
      pids="$(_soak_pids)"
      [ -z "$pids" ] && break
      if [ "$waited" -ge "$timeout" ]; then
        printf '중단: %ss 를 기다렸는데 아직 돌고 있다(pid %s). 수확하지 않았다.\n' "$timeout" \
          "$(printf '%s' "$pids" | tr '\n' ' ')" >&2
        return 5
      fi
      stall="$(_soak_stall_seconds)"
      printf '  [%s] 대기 %ss — 아직 실행 중(pid %s) · 마지막 쓰기 %s초 전\n' "$(_utc)" "$waited" \
        "$(printf '%s' "$pids" | tr '\n' ' ')" "$stall"
      # 살아 있는데 아무것도 안 쓰는 상태는 "도는 중" 이 아니라 **사로잡힌 중**이다(실측).
      if [ "$stall" != "unknown" ] && [ "$stall" -ge "$max_stall" ]; then
        printf '중단: %ss 동안 아무것도 쓰지 않았다(pid %s) — 도는 중이 아니라 멈춘 것으로 본다.\n' \
          "$stall" "$(printf '%s' "$pids" | tr '\n' ' ')" >&2
        printf '      확인: tail -20 %s · 그리고 정지가 맞다면 `soak_control.sh` 로 정리하고 \n' "$OUT/soak-run.log" >&2
        printf '      다시 시작하라(러너는 종료 시에만 리포트를 쓴다 — 이대로 두면 8시간이 결과 0 이다).\n' >&2
        printf '      상한 조정: NX10_HARVEST_MAX_STALL(기본 1800초).\n' >&2
        return 6
      fi
      sleep "$poll"
      waited=$((waited + poll))
    done
    printf '  실행 종료를 확인했다(%ss 대기).\n' "$waited"
  fi

  # 잠금·프로세스가 사라졌다고 해서 블록이 완성된 것은 아니다(러너가 마지막 필드를 쓰는 중일 수 있다).
  # `NX10_HARVEST_SETTLE`(기본 120초)은 그 플러시를 기다리는 시간 — 자기시험은 짧게 준다.
  local settle=0 settle_max="${NX10_HARVEST_SETTLE:-120}"
  while [ "$settle" -lt "$settle_max" ] && ! _block_complete; do
    sleep 5
    settle=$((settle + 5))
  done
  if ! _block_complete; then
    printf '거부: 마지막 러너 블록이 완성되지 않았다(end_time/exit 없음) — 회수할 실행이 없다.\n' >&2
    printf '      중단된 실행이라면 그 사실이 soak-exit.txt 에 러너 기록과 구분돼 있어야 한다.\n' >&2
    return 3
  fi
  if [ "$waited" = 0 ]; then
    printf '  (도는 soak 이 없다 — 이미 끝난 마지막 실행을 판정한다: %s → %s)\n' \
      "$(_block_field start_time)" "$(_block_field end_time)"
  fi

  local stamp log rc verdict start_fp end_fp
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  log="$OUT/soak-harvest-$stamp.txt"
  printf '  판정기: %s\n  판정 기록: %s\n\n' "$judge" "$log"
  "$(_py)" "$judge" 2>&1 | tee "$log"
  rc="${PIPESTATUS[0]}"

  verdict="$(sed -n 's/^  판정: \([A-Z][A-Z]*\).*/\1/p' "$log" | tail -1)"
  start_fp="$(_block_field start_fingerprint)"
  end_fp="$(_block_field end_fingerprint)"
  printf '\n  ── 수확 요약 ──\n'
  printf '  실행: %s → %s · exit %s · 판정: %s\n' "$(_block_field start_time)" \
    "$(_block_field end_time)" "$(_block_field exit)" "${verdict:-?}"
  printf '  시작 지문=%s\n  종료 지문=%s\n' "${start_fp:-?}" "${end_fp:-?}"
  if [ -n "$start_fp" ] && [ "$start_fp" = "$end_fp" ]; then
    printf '  귀속: 성립(시작 == 종료) — 이 실행은 후보의 것으로 적을 수 있다\n'
  else
    printf '  귀속: 불성립(시작 != 종료) — 이 실행은 후보에 붙일 수 없다\n'
  fi
  printf '  다음: 대장 기록 → 커밋 → clean-machine → ga_gate_verify (판정기의 순서를 그대로 따른다)\n'
  printf '  타 레인/오너 대기: required red · CR-14 재선언 · owner 허용 — OWNER_REQUEST_TAILFIX.md\n'
  return "$rc"
}

# ── selftest ────────────────────────────────────────────────────────────────
# 오늘 사고를 그대로 재현해 **막히는지**를 본다. 본 저장소의 예약은 건드리지 않고,
# 임시 디렉터리에서 가짜 예약 프로세스와 진짜 예약 스크립트‌ (임시 OUT·스텁 러너)를 돌린다.
# 종료 코드: 전부 통과 0, 하나라도 실패 1.
_st_total=0
_st_passed=0

_st_ck() { # 이름 기대 실제
  _st_total=$((_st_total + 1))
  if [ "$2" = "$3" ]; then
    _st_passed=$((_st_passed + 1))
    printf '  [OK]   %s\n' "$1"
  else
    printf '  [FAIL] %s (기대=%s 실제=%s)\n' "$1" "$2" "$3"
  fi
}

_st_ck_has() { # 이름 파일 패턴
  _st_total=$((_st_total + 1))
  if grep -q -- "$3" "$2" 2>/dev/null; then
    _st_passed=$((_st_passed + 1))
    printf '  [OK]   %s\n' "$1"
  else
    printf '  [FAIL] %s — %s 에서 %s 를 찾지 못했다\n' "$1" "$2" "$3"
  fi
}

_st_ck_dead() { # 이름 패턴
  local live
  live="$(pgrep -f -- "$2" 2>/dev/null | grep -v -x -e "$$" -e "${PPID:-0}" || true)"
  _st_total=$((_st_total + 1))
  if [ -z "$live" ]; then
    _st_passed=$((_st_passed + 1))
    printf '  [OK]   %s\n' "$1"
  else
    printf '  [FAIL] %s — 잔존 pid=%s\n' "$1" "$live"
  fi
}

_fake_sched() { # $1=경로 $2=본문
  printf '#!/usr/bin/env bash\n%s\n' "$2" > "$1"
  chmod +x "$1"
}

cmd_selftest() {
  local tmp d rc at fp
  tmp="$(mktemp -d "${TMPDIR:-/tmp}/nx10-ctl-selftest-XXXXXX")"
  printf 'NX-10 soak 통제 자기시험 — 임시 루트 %s\n' "$tmp"

  # ① 살아 있는 예약이 있으면 예약(arm)이 거부된다 (오늘 사고의 핵심: 중복 예약)
  d="$tmp/t1"
  mkdir -p "$d/out"
  _fake_sched "$d/schedule_nx10_soak.sh" 'sleep 120'
  # 가짜 프로세스의 출력은 파일로 보낸다 — 파이프를 물려받으면 그 프로세스가 살아 있는 동안
  # 호출자가 EOF 를 못 받는다(첫 실행이 정확히 그렇게 타임아웃까지 매달렸다).
  bash "$d/schedule_nx10_soak.sh" > "$d/fake.log" 2>&1 & local fake1=$!
  sleep 1
  NX10_OUT="$d/out" NX10_REPO="$REPO" NX10_SCHEDULER="$d/schedule_nx10_soak.sh" \
    NX10_SCHED_PATTERN="$d/schedule_nx10_soak.sh" \
    bash "$0" arm --at 22:00 > "$d/arm.txt" 2>&1
  _st_ck "① 살아 있는 예약이 있으면 arm 거부(exit 2)" 2 "$?"
  _st_ck_has "① 거부 사유가 '중복 예약 금지'" "$d/arm.txt" "이미 살아 있는 예약"

  # ② 지문을 계산할 수 없으면 예약하지 않는다(22:00 에 스스로 멈출 예약을 걸지 않는다)
  mkdir -p "$d/empty"
  NX10_OUT="$d/out" NX10_REPO="$d/empty" NX10_SCHEDULER="$d/schedule_nx10_soak.sh" \
    NX10_SCHED_PATTERN="$d/no-such-scheduler.sh" \
    bash "$0" arm --at 22:00 > "$d/arm2.txt" 2>&1
  _st_ck "② 지문 UNVERIFIED 면 arm 거부(exit 2)" 2 "$?"
  _st_ck_has "② 거부 사유가 UNVERIFIED" "$d/arm2.txt" "UNVERIFIED"

  # ③ cancel 이 실제로 죽였는지 **검증**한다(TERM 을 따르는 프로세스)
  d="$tmp/t3"
  mkdir -p "$d/out"
  _fake_sched "$d/schedule_nx10_soak.sh" 'sleep 300'
  bash "$d/schedule_nx10_soak.sh" > "$d/fake.log" 2>&1 & sleep 1
  NX10_OUT="$d/out" NX10_SCHED_PATTERN="$d/schedule_nx10_soak.sh" NX10_CANCEL_GRACE=5 \
    bash "$0" cancel > "$d/cancel.txt" 2>&1
  _st_ck "③ cancel 성공(exit 0)" 0 "$?"
  _st_ck_dead "③ cancel 뒤 잔존 프로세스 0건" "$d/schedule_nx10_soak.sh"
  _st_ck_has "③ '죽음 확인'을 문장으로 남긴다" "$d/cancel.txt" "검증: 살아 있는 예약 0건"

  # ④ TERM 을 무시하는 프로세스는 KILL 로 승격해 끝낸다(조용히 남기지 않는다).
  #    승격 경로는 첫 자기시험이 '취소가 아무것도 죽이지 못했음' 을 드러낸 자리다(`tac` 부재).
  d="$tmp/t4"
  mkdir -p "$d/out"
  _fake_sched "$d/schedule_nx10_soak.sh" "trap '' TERM
sleep 300"
  bash "$d/schedule_nx10_soak.sh" > "$d/fake.log" 2>&1 & sleep 1
  NX10_OUT="$d/out" NX10_SCHED_PATTERN="$d/schedule_nx10_soak.sh" NX10_CANCEL_GRACE=3 \
    bash "$0" cancel > "$d/cancel.txt" 2>&1
  _st_ck "④ TERM 무시 프로세스도 cancel 성공(exit 0)" 0 "$?"
  _st_ck_has "④ KILL 승격을 기록했다" "$d/cancel.txt" "KILL 승격"
  _st_ck_dead "④ 승격 뒤 잔존 0건" "$d/schedule_nx10_soak.sh"

  # ⑤b 잠금 주인이 자기 트리 안에 있으면 고아가 아니다(예약 1건이 프로세스 2개로 보이는 것을
  #     오탐으로 올리지 않는다 — 실측: 래퍼 + bash).
  d="$tmp/t5b"
  mkdir -p "$d/out/.soak-arm.lock"
  _fake_sched "$d/schedule_nx10_soak.sh" 'sleep 60'
  bash "$d/schedule_nx10_soak.sh" > "$d/fake.log" 2>&1 & local fake5=$!
  sleep 1
  printf 'pid: %s\nexpected_fingerprint: %s\n' "$fake5" "$(_tree_fingerprint)" > "$d/out/.soak-arm.lock/owner"
  NX10_OUT="$d/out" NX10_REPO="$REPO" NX10_SCHED_PATTERN="$d/schedule_nx10_soak.sh" \
    bash "$0" status > "$d/status.txt" 2>&1
  _st_ck "⑤b 잠금 주인을 품은 예약은 건강(exit 0)" 0 "$?"
  _st_ck_has "⑤b 고아 0건" "$d/status.txt" "잠금 밖(고아) 예약: 0"
  kill -TERM "$fake5" 2>/dev/null || true
  sleep 1

  # ⑦ 러너도 동시 실행을 거부한다 — 예약이 둘로 늘어나도 soak 이 둘로 늘어나지 않게 하는 두 번째 문.
  d="$tmp/t7"
  mkdir -p "$d/out/.soak-run.lock" "$d/work"
  sleep 60 > "$d/keep.log" 2>&1 & local keep=$!
  printf 'pid: %s\nstarted_at: now\n' "$keep" > "$d/out/.soak-run.lock/owner"
  NX10_SOAK_OUT_DIR="$d/out" NX10_SOAK_WORKDIR="$d/work" \
    bash "$RUNNER" > "$d/run.log" 2>&1
  _st_ck "⑦ 이미 soak 이 돌면 러너가 거부(exit 5)" 5 "$?"
  _st_ck_has "⑦ 거부 사유를 증거에 남긴다" "$d/out/soak-exit.txt" "concurrent soak"
  _st_ck "⑦ 거부된 실행은 리포트를 만들지 않는다" "no" "$(test -f "$d/out/soak-28800.json" && echo yes || echo no)"
  kill -TERM "$keep" 2>/dev/null || true

  # ⑧ preflight: 발화 전에 “밤을 태울 준비가 됐는가”를 묻는가(의존성·여유 공간·후보 귀속).
  #
  #    **더러운 트리 규칙**: 승격 리허설은 커밋되지 않은 파일을 작업 트리에 두는 것이 정의다. 그 상태에서는
  #    “현재 트리 == HEAD 트리” 가 **설계상** 거짓이라, “건강하면 preflight 0” 을 묻는 픽스처가 전부 1 을 받는다
  #    (실측 2026-09-17: 미러 리허설에서 ⑧ 2건 + ⑩ 1건이 빨개졌다). 도구가 틀린 게 아니라 **시험이 자기
  #    환경을 가정**한 것이므로, 트리가 HEAD 와 다르면 그 항목만 생략하고 **생략했다고 문장으로 밝힌다**.
  #    깨끗한 트리(실제 운영·실제 soak)에서는 종전대로 그 검사를 수행한다 — 이빨은 그때 문다.
  local attr_skip=0
  if [ "$(_tree_fingerprint)" != "$(_commit_fingerprint)" ]; then
    attr_skip=1
    printf '자기시험 환경: 작업 트리 ≠ HEAD — 후보 귀속 검사를 생략한다(리허설은 일부러 더럽다)\n'
  fi
  d="$tmp/t8"
  mkdir -p "$d/out/.soak-arm.lock"
  _fake_sched "$d/schedule_nx10_soak.sh" 'sleep 120'
  bash "$d/schedule_nx10_soak.sh" > "$d/fake.log" 2>&1 & local fake8=$!
  sleep 1
  local fp8 future
  fp8="$(_tree_fingerprint)"
  future="$("$(_py)" -c 'import datetime; print((datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ"))')"
  _owner8() { printf 'pid: %s\nexpected_fingerprint: %s\ntarget_utc: %s\nat_local: 22:00\n' "$fake8" "$1" "$future" > "$d/out/.soak-arm.lock/owner"; }
  _owner8 "$fp8"
  preflight() {
    # `NX10_SOAK_PROC_PATTERN` 은 **시험이 통제한다** — 기본값(실제 하네스)을 그대로 두면 진짜 soak 이
    # 도는 동안 “다른 soak 실행 없음” 이 정당하게 빨개져서, 이 픽스처가 전부 무의미해진다.
    NX10_OUT="$d/out" NX10_REPO="$REPO" NX10_SCHEDULER="$d/schedule_nx10_soak.sh" \
      NX10_RUNNER="$RUNNER" NX10_SCHED_PATTERN="$d/schedule_nx10_soak.sh" \
      NX10_SOAK_PROC_PATTERN="${NX10_SOAK_PROC_PATTERN:-$d/no-such-soak-harness-$$}" \
      NX10_PREFLIGHT_MIN_FREE_MB="${NX10_PREFLIGHT_MIN_FREE_MB:-2048}" \
      NX10_PF_SKIP_ATTRIBUTION="$attr_skip" \
      NX10_PREFLIGHT_SKIP_THROUGHPUT="${NX10_PREFLIGHT_SKIP_THROUGHPUT:-1}" bash "$0" preflight "$@"
  }
  preflight > "$d/pf-ok.txt" 2>&1
  _st_ck "⑧ 건강한 예약이면 preflight 0" 0 "$?"
  #    귀속 검사 자체는 **깨끗한 트리에서만** 물을 수 있다: 더러운 트리에서는 항목이 빠지고 대신 “생략했다”는
  #    문장이 남으므로, 두 경우 모두 **무엇을 했는지가 출력에 드러나는지**를 본다(조용한 생략 금지).
  if [ "$attr_skip" = "1" ]; then
    _st_ck_has "⑧ (전제) 후보 귀속 생략을 문장으로 밝힌다" "$d/pf-ok.txt" "후보 귀속(생략됨)"
  else
    _st_ck_has "⑧ 후보 귀속(현재 트리 == HEAD)까지 본다" "$d/pf-ok.txt" "현재 트리 == HEAD 트리"
  fi

  # 여유 공간 기준을 크게 주면 실패해야 한다(임계값이 실제로 작동하는지)
  NX10_PREFLIGHT_MIN_FREE_MB=99999999 preflight > "$d/pf-disk.txt" 2>&1
  _st_ck "⑧ 여유 공간 미달이면 preflight 1" 1 "$?"
  _st_ck_has "⑧ 미달 항목을 지목" "$d/pf-disk.txt" "작업디렉터리 여유"

  # 다른 soak 이 돌고 있으면 시작하지 않는다
  mkdir -p "$d/out/.soak-run.lock"
  sleep 60 > "$d/keep8.log" 2>&1 & local keep8=$!
  printf 'pid: %s\n' "$keep8" > "$d/out/.soak-run.lock/owner"
  preflight > "$d/pf-run.txt" 2>&1
  _st_ck "⑧ 이미 soak 이 돌면 preflight 1" 1 "$?"
  _st_ck_has "⑧ 다른 실행을 지목" "$d/pf-run.txt" "다른 soak 실행 없음"
  kill -TERM "$keep8" 2>/dev/null || true
  rm -rf "$d/out/.soak-run.lock"

  # 기대 지문이 틀리면 밤을 버리기 전에 잡는다
  _owner8 deadbeefdeadbeef
  preflight > "$d/pf-fp.txt" 2>&1
  _st_ck "⑧ 지문 불일치면 preflight 1" 1 "$?"
  _st_ck_has "⑧ 지문 불일치를 지목" "$d/pf-fp.txt" "기대 지문 == 현재 트리"

  # 유령 잠금(주인 프로세스가 죽었는데 잠금만 남음)
  kill -TERM "$fake8" 2>/dev/null || true
  sleep 1
  preflight > "$d/pf-ghost.txt" 2>&1
  _st_ck "⑧ 유령 잠금이면 preflight 1" 1 "$?"
  _st_ck_has "⑧ 유령 잠금을 지목" "$d/pf-ghost.txt" "잠금 상태=armed"

  # ⑧ 이미 도는 soak(다른 디렉터리에서 시작된 것)은 **기계 전체**에서 잡는다 — 두 개가 동시에 돌면
  #    서로의 처리량·RSS 측정을 오염시키기 때문이다. 판정은 하네스 이름으로 하는데, 그 이름을 시험이
  #    통제하지 않으면 **진짜 soak 이 도는 동안 이 픽스처가 전부 빨개진다**(실측 2026-09-16T23:34Z:
  #    재실행 중인 soak 을 “다른 soak 실행 없음” 이 잡아 ⑧·⑨ 3건이 실패 — 원인은 도구가 아니라 시험 쪽).
  #    ※ 뒤 픽스처가 `$d`(t8)의 자산을 그대로 쓰므로 여기서 `$d` 를 바꾸지 않는다 — 바꿦다가 처리량
  #      픽스처가 “스케줄러 자산 없음” 으로 빨개졌다(실측: 51/52 의 유일한 실패가 그것이었다).
  local df="$tmp/t8f"
  mkdir -p "$df/out"
  # 픽스처는 **파이썬**이어야 한다: 도구는 `comm` 이 파이썬인 것만 하네스로 센다(셸 래퍼 오탐 차단).
  # 토큰을 argv 에 실어 이 시험만 가리키게 한다.
  local foreign_token="nx10-foreign-soak-$$"
  "$(_py)" -c "import time; time.sleep(120)" "$foreign_token" > "$df/pretend.log" 2>&1 & local pre8=$!
  sleep 1
  NX10_OUT="$df/out" NX10_REPO="$REPO" NX10_SCHED_PATTERN="$df/no.sh" \
    NX10_SOAK_PROC_PATTERN="$foreign_token" NX10_PF_SKIP_RESERVATION=1 \
    NX10_PF_SKIP_ATTRIBUTION="$attr_skip" \
    NX10_PREFLIGHT_SKIP_THROUGHPUT=1 \
    bash "$0" preflight > "$df/pf-foreign.txt" 2>&1
  _st_ck "⑧ 다른 soak 이 돌면 preflight 1" 1 "$?"
  _st_ck_has "⑧ 도는 프로세스를 pid 로 지목한다" "$df/pf-foreign.txt" "$foreign_token pid="
  kill -TERM "$pre8" 2>/dev/null || true
  wait "$pre8" 2>/dev/null || true

  # ⑧b 이빨 — 패턴에 걸린 **셸**은 soak 이 아니다(실측 2026-09-17: 진단 명령이 soak 으로 잡혔다).
  #     이 픽스처가 없으면 인터프리터 필터가 조용히 사라져도 시험이 초록으로 남는다.
  #     ※ 귀속 문을 여기에도 반드시 붙인다: 이 자리는 preflight 가 **exit 0 을 내야** 하는 유일한 직접 호출이라,
  #       문을 빼면 **더러운 트리(승격 미러가 정확히 그렇다)에서만** 빨개진다 — 2026-09-17 리허설 `attempt6`
  #       이 그렇게 멈췄다(청정한 본 트리에서는 초록이었다). 시험은 “본 트리에서만 통과하는” 단언을 갖지 않는다.
  local shell_token="nx10-shell-decoy-$$"
  _fake_sched "$df/schedule_nx10_soak.sh" 'sleep 5'
  bash -c "sleep 120 # $shell_token" > "$df/shell.log" 2>&1 & local sh8=$!
  sleep 1
  NX10_OUT="$df/out" NX10_REPO="$REPO" NX10_SCHED_PATTERN="$df/no.sh" \
    NX10_SCHEDULER="$df/schedule_nx10_soak.sh" NX10_RUNNER="$RUNNER" \
    NX10_SOAK_PROC_PATTERN="$shell_token" NX10_PF_SKIP_RESERVATION=1 \
    NX10_PF_SKIP_ATTRIBUTION="$attr_skip" \
    NX10_PREFLIGHT_SKIP_THROUGHPUT=1 \
    AGK_CONVERSATION_JOURNAL_HARD_CAP_MB=8192 \
    bash "$0" preflight > "$df/pf-shell.txt" 2>&1
  _st_ck "⑧ (이빨) 셸이 패턴에 걸러도 preflight 0" 0 "$?"
  _st_ck_has "⑧ (이빨) 그 사실을 숫자로 밝힌다" "$df/pf-shell.txt" "$shell_token 0건"
  if [ "$attr_skip" = "1" ]; then
    _st_ck_has "⑧b (전제) 후보 귀속 생략을 문장으로 밝힌다" "$df/pf-shell.txt" "후보 귀속(생략됨)"
  fi
  kill -TERM "$sh8" 2>/dev/null || true
  wait "$sh8" 2>/dev/null || true

  # ⑧ 처리량 하한 — 5초 프루브로 문 하나만 본다(예약 점검은 빼고, 60초는 시험을 느리게 만든다).
  #     넉넉한 하한은 통과하고, 터무니없이 높은 하한은 **실패해야** 한다(문이 실제로 작동하는가).
  NX10_OUT="$d/out" NX10_REPO="$REPO" NX10_SCHEDULER="$d/schedule_nx10_soak.sh" \
    NX10_RUNNER="$RUNNER" NX10_SCHED_PATTERN="$d/no.sh" NX10_PF_SKIP_RESERVATION=1 \
    NX10_SOAK_PROC_PATTERN="$d/no-such-soak-harness-$$" \
    NX10_PF_SKIP_ATTRIBUTION="$attr_skip" \
    NX10_PREFLIGHT_SKIP_THROUGHPUT=0 NX10_PREFLIGHT_PROBE_SECONDS=5 NX10_PREFLIGHT_MIN_OPS_PER_SEC=1 \
    bash "$0" preflight > "$d/pf-thr-ok.txt" 2>&1
  _st_ck "⑧ 처리량 하한을 넘으면 preflight 0" 0 "$?"
  _st_ck_has "⑧ 처리량을 ops/s 로 보고한다" "$d/pf-thr-ok.txt" "처리량 하한 ≥ 1 ops/s"
  _st_ck_has "⑧ 프루브가 리포트를 냈는지 확인한다" "$d/pf-thr-ok.txt" "8시간 외삽"

  NX10_OUT="$d/out" NX10_REPO="$REPO" NX10_SCHEDULER="$d/schedule_nx10_soak.sh" \
    NX10_RUNNER="$RUNNER" NX10_SCHED_PATTERN="$d/no.sh" NX10_PF_SKIP_RESERVATION=1 \
    NX10_SOAK_PROC_PATTERN="$d/no-such-soak-harness-$$" \
    NX10_PREFLIGHT_SKIP_THROUGHPUT=0 NX10_PREFLIGHT_PROBE_SECONDS=5 NX10_PREFLIGHT_MIN_OPS_PER_SEC=99999999 \
    bash "$0" preflight > "$d/pf-thr-fail.txt" 2>&1
  _st_ck "⑧ 처리량 미달이면 preflight 1" 1 "$?"
  _st_ck_has "⑧ 미달 항목을 지목한다" "$d/pf-thr-fail.txt" "처리량 하한"

  # 프루브가 리포트를 내지 못하면(예: 소크 하네스 자체가 깨짐) 0 ops 로 **실패**해야 한다
  NX10_OUT="$d/out" NX10_REPO="$d/no-such-repo" NX10_SCHEDULER="$d/schedule_nx10_soak.sh" \
    NX10_RUNNER="$RUNNER" NX10_SCHED_PATTERN="$d/no.sh" NX10_PF_SKIP_RESERVATION=1 \
    NX10_SOAK_PROC_PATTERN="$d/no-such-soak-harness-$$" \
    NX10_PREFLIGHT_SKIP_THROUGHPUT=0 NX10_PREFLIGHT_PROBE_SECONDS=5 NX10_PREFLIGHT_MIN_OPS_PER_SEC=1 \
    bash "$0" preflight > "$d/pf-thr-noreport.txt" 2>&1
  _st_ck "⑧ 프루브가 리포트를 못 내면 preflight 1" 1 "$?"
  _st_ck_has "⑧ 그 사유를 문장으로 남긴다" "$d/pf-thr-noreport.txt" "SC-6 프루브가 리포트를 내지 않았다"

  # ⑧ 쓰기량 투영 vs hard cap — 처리량 하한의 쌍둥이 사각지대다. 실측(2026-09-17): 꼬리 창 수정으로
  #    append 가 빨라지자 기본 512 MiB 캡을 **47분에 452 MiB**로 밀어붙였고, 넘긴 뒤에는 모든 append 가
  #    507 로 거절되어 하네스가 그것을 `errors` 로 세고 SC-6 이 **설정 때문의 거짓 FAIL** 이 된다.
  #    문이 두 방향으로 작동하는지 본다: 넘치는 캡은 빨개지고, 넉넉한 캡은 초록이다.
  NX10_OUT="$d/out" NX10_REPO="$REPO" NX10_SCHEDULER="$d/schedule_nx10_soak.sh" \
    NX10_RUNNER="$RUNNER" NX10_SCHED_PATTERN="$d/no.sh" NX10_PF_SKIP_RESERVATION=1 \
    NX10_SOAK_PROC_PATTERN="$d/no-such-soak-harness-$$" \
    NX10_PREFLIGHT_SKIP_THROUGHPUT=0 NX10_PREFLIGHT_PROBE_SECONDS=5 NX10_PREFLIGHT_MIN_OPS_PER_SEC=1 \
    AGK_CONVERSATION_JOURNAL_HARD_CAP_MB=1 \
    bash "$0" preflight > "$d/pf-cap-fail.txt" 2>&1
  _st_ck "⑧ 예상 쓰기량이 hard cap 을 넘으면 preflight 1" 1 "$?"
  _st_ck_has "⑧ 그 항목을 지목한다" "$d/pf-cap-fail.txt" "예상 journal 쓰기량 < hard cap"
  _st_ck_has "⑧ 왜 빨간지(507 거절 → 거짓 FAIL)를 말한다" "$d/pf-cap-fail.txt" "거짓 FAIL"

  NX10_OUT="$d/out" NX10_REPO="$REPO" NX10_SCHEDULER="$d/schedule_nx10_soak.sh" \
    NX10_RUNNER="$RUNNER" NX10_SCHED_PATTERN="$d/no.sh" NX10_PF_SKIP_RESERVATION=1 \
    NX10_SOAK_PROC_PATTERN="$d/no-such-soak-harness-$$" \
    NX10_PREFLIGHT_SKIP_THROUGHPUT=0 NX10_PREFLIGHT_PROBE_SECONDS=5 NX10_PREFLIGHT_MIN_OPS_PER_SEC=1 \
    NX10_PF_SKIP_ATTRIBUTION="$attr_skip" \
    AGK_CONVERSATION_JOURNAL_HARD_CAP_MB=8192 \
    bash "$0" preflight > "$d/pf-cap-ok.txt" 2>&1
  _st_ck "⑧ 넉넉한 캡이면 preflight 0" 0 "$?"
  _st_ck_has "⑧ 투영·캡·프루브 길이를 숫자로 보여준다" "$d/pf-cap-ok.txt" "8시간 외삽"
  _st_ck_has "⑧ 캡 값을 문장으로 남긴다" "$d/pf-cap-ok.txt" "cap 8192 MiB"
  #    생략은 **밝히고** 생략한다(⑨ 와 같은 이유): 승격 리허설처럼 작업 트리가 일부러 더러운 곳에서도
  #    "캡 때문에 초록인가"를 물을 수 있어야 한다 — 조용히 건너뛰면 이 카드가 이빨로 쓰는 문장이 가짜다.
  if [ "$attr_skip" = "1" ]; then
    _st_ck_has "⑧ (전제) 캡 픽스처도 귀속 생략을 밝힌다" "$d/pf-cap-ok.txt" "후보 귀속(생략됨)"
  fi

  # ⑨ `run`(예약을 기다리지 않고 지금 시작) — **거부** 쪽을 고정한다. 해피 패스는 8시간 soak 을 실제로
  #     띄우므로 시험에서 돌리지 않는다(그 자체가 운영 기록이다 — 오늘 밤 실제 시작이 그 증거다).
  d="$tmp/t9"
  mkdir -p "$d/out" "$d/empty"
  NX10_OUT="$d/out" NX10_REPO="$d/empty" NX10_SCHEDULER="$d/does-not-exist.sh" \
    NX10_RUNNER="$RUNNER" NX10_SCHED_PATTERN="$d/no.sh" NX10_PREFLIGHT_MIN_FREE_MB=99999999 \
    NX10_SOAK_PROC_PATTERN="$d/no-such-soak-harness-$$" \
    NX10_PREFLIGHT_SKIP_THROUGHPUT=1 \
    bash "$0" run > "$d/run-fail.txt" 2>&1
  _st_ck "⑨ preflight 실패면 run 거부(exit 2)" 2 "$?"
  _st_ck_has "⑨ 거부 사유를 문장으로 남긴다" "$d/run-fail.txt" "이 상태로 8시간을 시작하지 않는다"

  #     예약이 이미 걸려 있으면 두 개가 뜨지 않게 거부한다. 이 시험이 보는 것은 **거부 사유가 예약인지**
  #     이므로, 앞선 preflight 가 다른 이유로 먼저 거부해 버리면 시험이 무의미해진다 — 그래서 후보 귀속을
  #     명시적으로 생략해 **예약 문이 실제로 닫히는지**만 남긴다(승격 리허설의 더러운 트리에서도 같은 의미).
  d="$tmp/t9b"
  mkdir -p "$d/out"
  _fake_sched "$d/schedule_nx10_soak.sh" 'sleep 60'
  bash "$d/schedule_nx10_soak.sh" > "$d/fake.log" 2>&1 & local fake9=$!
  sleep 1
  NX10_OUT="$d/out" NX10_REPO="$REPO" NX10_SCHEDULER="$d/schedule_nx10_soak.sh" \
    NX10_RUNNER="$RUNNER" NX10_SCHED_PATTERN="$d/schedule_nx10_soak.sh" \
    NX10_SOAK_PROC_PATTERN="$d/no-such-soak-harness-$$" \
    NX10_PREFLIGHT_SKIP_THROUGHPUT=1 \
    NX10_PF_SKIP_ATTRIBUTION="$attr_skip" \
    bash "$0" run > "$d/run-armed.txt" 2>&1
  _st_ck "⑨ 예약이 걸려 있으면 run 거부(exit 2)" 2 "$?"
  _st_ck_has "⑨ 예약을 지목" "$d/run-armed.txt" "예약이 이미 걸려 있다"
  kill -TERM "$fake9" 2>/dev/null || true

  # ⑩ 실행 중(`run`)에는 예약 잠금이 **없다** — 그때 status 가 ATTENTION 을 내면 상시 거짓 경보가 되고,
  #    상시 거짓 경보는 진짜 경보를 무디게 만든다(실측 2026-09-16T23:28Z: 8시간 재실행 중 `판정: ATTENTION`).
  d="$tmp/t10"
  mkdir -p "$d/out/.soak-run.lock"
  sleep 60 & local runp=$!
  fp="$(_tree_fingerprint)"
  _st_ck "⑩ (전제) 시험용 지문을 계산했다" "yes" "$([ "${#fp}" = 64 ] && echo yes || echo no)"
  printf 'pid: %s\nstarted_at: %s\n' "$runp" "$(_utc)" > "$d/out/.soak-run.lock/owner"
  {
    printf 'command: x --soak-seconds 28800 --workdir /tmp/x\n'
    printf 'start_fingerprint: %s\n' "$fp"
  } > "$d/out/soak-exit.txt"
  NX10_OUT="$d/out" NX10_REPO="$REPO" NX10_SCHED_PATTERN="$d/no-such-scheduler.sh" \
    bash "$0" status > "$d/run-status.txt" 2>&1
  _st_ck "⑩ 실행 중이면 status 가 RUNNING(exit 0)" 0 "$?"
  _st_ck_has "⑩ 모드를 문장으로 말한다" "$d/run-status.txt" "모드: RUNNING"
  _st_ck_has "⑩ 남은 초와 종료 예정을 보여준다" "$d/run-status.txt" "남은 초:"
  _st_ck_has "⑩ 실행 시작 지문을 현재 트리와 나란히 보여준다" "$d/run-status.txt" "실행 시작="

  #     실행 중인데 트리 지문이 갈리면(코드 스코프 편집) 그 실행은 후보에 못 붙는다 — 그때는 빨개야 한다.
  #     마지막 러너 블록을 쓰는지도 같이 본다(값을 뒤에 덧붙여 확인한다).
  printf 'start_fingerprint: %s\n' "0000000000000000000000000000000000000000000000000000000000000000" \
    >> "$d/out/soak-exit.txt"
  NX10_OUT="$d/out" NX10_REPO="$REPO" NX10_SCHED_PATTERN="$d/no-such-scheduler.sh" \
    bash "$0" status > "$d/run-status2.txt" 2>&1
  _st_ck "⑩ 지문이 갈리면 status 가 ATTENTION(exit 1)" 1 "$?"
  _st_ck_has "⑩ 후보 귀속이 끊겼다고 말한다" "$d/run-status2.txt" "후보에 붙일 수 없다"
  kill -TERM "$runp" 2>/dev/null || true
  wait "$runp" 2>/dev/null || true

  # ⑤ 죽은 주인의 잠금은 '예약됨'이 아니라 'stale' 로 보인다(상태를 속이지 않는다)
  d="$tmp/t5"
  mkdir -p "$d/out/.soak-arm.lock"
  printf 'pid: 4194303\nexpected_fingerprint: deadbeef\n' > "$d/out/.soak-arm.lock/owner"
  NX10_OUT="$d/out" NX10_SCHED_PATTERN="$d/no-such.sh" bash "$0" status > "$d/status.txt" 2>&1
  _st_ck "⑤ stale 잠금이면 status 가 1" 1 "$?"
  _st_ck_has "⑤ stale 로 표기" "$d/status.txt" "잠금: stale"
  _st_ck_has "⑤ ATTENTION 판정" "$d/status.txt" "ATTENTION"

  # ⑥ 전체 수명주기: 진짜 예약 스크립트(임시 OUT·스텁 러너) → 잠금 → 발화 → 잠금 해제 · 러너 1회 실행
  d="$tmp/t6"
  mkdir -p "$d/out"
  cp "$SCHEDULER" "$d/out/schedule_nx10_soak.sh"
  _fake_sched "$d/stub.sh" 'echo "stub ran $(date -u +%FT%TZ)" >> "$STUB_OUT"'
  read -r at _wait < <("$(_py)" - <<'PY'
import datetime
now = datetime.datetime.now()
target = now + datetime.timedelta(seconds=40)
target = target.replace(second=0, microsecond=0)
if (target - now).total_seconds() < 15:
    target += datetime.timedelta(minutes=1)
print(target.strftime("%H:%M"), int((target - now).total_seconds()))
PY
)
  fp="$(_tree_fingerprint)"
  if [ "$fp" = "UNVERIFIED" ] || ! command -v screen >/dev/null 2>&1; then
    printf '  [SKIP] ⑥ 수명주기 시험(fp=%s, screen=%s)\n' "$fp" "$(command -v screen || echo none)"
  else
    NX10_OUT="$d/out" NX10_REPO="$REPO" NX10_SCHEDULER="$d/out/schedule_nx10_soak.sh" \
      NX10_RUNNER="$d/stub.sh" NX10_SCHED_PATTERN="$d/out/schedule_nx10_soak.sh" \
      NX10_SCREEN_NAME=nx10selftest NX10_NO_CAFFEINATE=1 STUB_OUT="$d/runner-ran.txt" \
      bash "$0" arm --at "$at" --fp "$fp" > "$d/arm.txt" 2>&1
    _st_ck "⑥ arm 이 잠금을 잡고 성공(exit 0)" 0 "$?"
    local waited=0
    while [ "$waited" -lt 120 ] && [ ! -f "$d/runner-ran.txt" ]; do sleep 2; waited=$((waited + 2)); done
    _st_ck "⑥ 발화 시각에 스텁 러너가 실행됐다" "yes" "$(test -f "$d/runner-ran.txt" && echo yes || echo no)"
    local lockstate
    lockstate="$(NX10_OUT="$d/out" NX10_REPO="$REPO" NX10_SCHED_PATTERN="$d/no.sh" \
      bash "$0" status 2>/dev/null | sed -n 's/^  잠금: \([a-z]*\).*/\1/p' | head -1)"
    _st_ck "⑥ 시작 뒤 예약 잠금이 해제됐다" "none" "$lockstate"
    _st_ck_has "⑥ 예약 기록에 시작 지문이 남았다" "$d/out/soak-schedule.txt" "start_check_fingerprint: $fp"
    screen -S nx10selftest -X quit >/dev/null 2>&1 || true
  fi

  # ⑪ harvest — 회수를 **기다렸다가** 한 번에 한다. 문은 네 가지: 끝나기 전엔 판정하지 않는다,
  #    기다린 뒤에는 판정기의 exit 를 **그대로** 전한다, 완료 블록이 없으면 판정하지 않는다,
  #    그리고 기다릴 때는 정말로 기다린다. 판정기는 시험용 파이썬 스텁으로 갈아 끼운다.
  d="$tmp/t11"
  mkdir -p "$d/out"
  printf 'import os, pathlib, sys\npathlib.Path(os.environ["JUDGE_RAN"]).write_text("ran\\n")\nprint("  판정: FAIL (미충족: SC-6)")\nsys.exit(7)\n' > "$d/judge.py"
  hpat="$d/fake-soak.sh"
  hrun() { # 인자를 그대로 전달하며 판정기·하네스 이름을 시험용으로 갈아 끼운다
    JUDGE_RAN="$d/judge-ran.txt" NX10_OUT="$d/out" NX10_REPO="$REPO" NX10_JUDGE="$d/judge.py" \
      NX10_SOAK_PROC_PATTERN="$hpat" NX10_SCHED_PATTERN="$d/no.sh" NX10_REPO="$REPO" \
      bash "$0" harvest "$@"
  }
  _completed_block() { # 러너가 종료 시에 쓰는 필드까지 갖춘 블록
    {
      printf 'generated_at: 2026-01-01T00:00:00Z\nreport: %s/soak-28800.json\n' "$d/out"
      printf 'start_time: 2026-01-01T00:00:00Z\nstart_fingerprint: aaaaaaaaaaaa\n'
      printf 'exit: 1\nend_time: 2026-01-01T08:00:00Z\nend_fingerprint: aaaaaaaaaaaa\n'
    } > "$d/out/soak-exit.txt"
  }

  # 가짜 soak 은 **파이썬**이어야 한다 — 도구는 `comm` 이 파이썬인 것만 하네스로 센다(셸 래퍼 오탐 차단).
  hpat="nx10-harvest-decoy-$$"
  "$(_py)" -c "import time; time.sleep(8)" "$hpat" > "$d/fake.log" 2>&1 & local fake11=$!
  sleep 1
  hrun --no-wait > "$d/h-nowait.txt" 2>&1
  _st_ck "⑪ 도는 soak 이 있으면 --no-wait 는 거부(exit 4)" 4 "$?"
  _st_ck_has "⑪ 그 사유가 '끝난 뒤' 임을 말한다" "$d/h-nowait.txt" "끝난 뒤"
  _st_ck "⑪ 거부된 회수는 판정기를 실행하지 않는다" "no" \
    "$(test -f "$d/judge-ran.txt" && echo yes || echo no)"

  # 완성 블록 + 도는 soak 없음 → 판정기의 exit 를 **그대로** 전하고, 그 출력을 파일로 남긴다.
  kill -TERM "$fake11" 2>/dev/null || true
  wait "$fake11" 2>/dev/null || true
  _completed_block
  hrun --no-wait > "$d/h-run.txt" 2>&1
  _st_ck "⑪ 판정기의 exit 를 그대로 전한다(7)" 7 "$?"
  _st_ck "⑪ 판정기를 실제로 실행했다" "yes" "$(test -f "$d/judge-ran.txt" && echo yes || echo no)"
  _st_ck "⑪ 판정 출력을 파일로 남긴다" "yes" \
    "$(ls "$d/out"/soak-harvest-*.txt >/dev/null 2>&1 && echo yes || echo no)"
  _st_ck_has "⑪ 요약에 실행·판정·지문을 모아 보여준다" "$d/h-run.txt" "수확 요약"
  _st_ck_has "⑪ 시작 == 종료 지문이면 귀속 성립을 말한다" "$d/h-run.txt" "귀속: 성립"

  # 완성되지 않은 블록(러너는 시작했는데 끝나지 않은 모양) → 판정하지 않는다.
  # (러너의 마지막 플러시를 기다리는 `settle` 을 짧게 줘서 시험이 120초를 쓰지 않게 한다.)
  printf 'generated_at: 2026-01-01T00:00:00Z\nstart_fingerprint: bbbbbbbbbbbb\n' \
    > "$d/out/soak-exit.txt"
  NX10_HARVEST_SETTLE=2 hrun --no-wait > "$d/h-incomplete.txt" 2>&1
  _st_ck "⑪ 완성 블록이 없으면 판정하지 않는다(exit 3)" 3 "$?"
  _st_ck_has "⑪ 그 사유를 문장으로 남긴다" "$d/h-incomplete.txt" "완성되지 않았다"

  # 기다리는 경로: 아직 도는 soak 이 끝나야 판정한다(초 단위 폴링으로 빠르게 확인).
  hpat="nx10-short-decoy-$$"
  "$(_py)" -c "import time; time.sleep(6)" "$hpat" > "$d/short.log" 2>&1 & local short11=$!
  sleep 1
  _completed_block
  hrun --poll 1 --timeout 30 > "$d/h-wait.txt" 2>&1
  _st_ck "⑪ 기다렸다가 판정한다(exit 7 = 판정기 exit)" 7 "$?"
  _st_ck_has "⑪ 기다린 사실을 기록한다" "$d/h-wait.txt" "실행 종료를 확인했다"
  kill -TERM "$short11" 2>/dev/null || true
  wait "$short11" 2>/dev/null || true

  # ⑫ 죽은-것-같은 실행을 **하루치 기다리지 않는다**. 프로세스가 살아 있으면 `harvest` 는 그냥
  #    "도는 중" 으로 보는데, 실측 사고는 정확히 그 모양이었다(worker 가 죽고 부모가 영원히 대기,
  #    로그·작업디렉터리 쓰기 0건). 마지막 쓰기 이후 경과로 그것을 잡는가.
  d="$tmp/t12"
  mkdir -p "$d/out/work"
  # 작업디렉터리를 **과거로** 만들어 둔다(멈춘 실행은 마지막 쓰기가 오래 전이다).
  touch -t 202001010000 "$d/out/work" 2>/dev/null || true
  # 가짜 soak 은 **파이썬**이어야 한다(도구가 comm 으로 하네스를 가린다 — 위 _is_harness_pid 참조).
  local hung_token="nx10-hung-soak-$$"
  "$(_py)" -c "import time; time.sleep(60)" "$hung_token" > "$d/fake.log" 2>&1 & local hung12=$!
  sleep 1
  {
    printf 'generated_at: 2026-01-01T00:00:00Z\nworkdir: %s\n' "$d/out/work"
    printf 'start_time: 2026-01-01T00:00:00Z\nstart_fingerprint: aaaa\n'
  } > "$d/out/soak-exit.txt"
  JUDGE_RAN="$d/judge-ran.txt" NX10_OUT="$d/out" NX10_JUDGE="$d/judge.py" \
    NX10_SOAK_PROC_PATTERN="$hung_token" NX10_HARVEST_MAX_STALL=2 NX10_HARVEST_POLL=1 \
    NX10_HARVEST_TIMEOUT=60 \
    bash "$0" harvest > "$d/h-stall.txt" 2>&1
  _st_ck "⑫ 무응답(살아 있지만 안 쓴다)이면 harvest 가 중단(exit 6)" 6 "$?"
  _st_ck_has "⑫ 마지막 쓰기 경과를 숫자로 보여준다" "$d/h-stall.txt" "마지막 쓰기"
  _st_ck_has "⑫ 그대로 두면 8시간이 결과 0 이라고 말한다" "$d/h-stall.txt" "결과 0"
  _st_ck "⑫ 멈춘 실행을 판정하지 않는다" "no" \
    "$(test -f "$d/out/soak-harvest-*.txt" 2>/dev/null && echo yes || echo no)"

  #    그리고 쓰기가 살아 있으면(정상 실행) 그 문에 걸리지 않고 계속 기다린다.
  local alive_token="nx10-alive-soak-$$"
  "$(_py)" -c 'import pathlib, time, sys
p = pathlib.Path(sys.argv[2])
p.mkdir(parents=True, exist_ok=True)
for i in range(20):
    (p / "tick").write_text(str(i))
    time.sleep(1)' "$alive_token" "$d/out/work/alive" > "$d/alive.log" 2>&1 & local alive12=$!
  sleep 1
  JUDGE_RAN="$d/judge-ran.txt" NX10_OUT="$d/out" NX10_JUDGE="$d/judge.py" \
    NX10_SOAK_PROC_PATTERN="$alive_token" NX10_HARVEST_MAX_STALL=3 NX10_HARVEST_POLL=1 \
    NX10_HARVEST_TIMEOUT=6 \
    bash "$0" harvest > "$d/h-alive.txt" 2>&1
  _st_ck "⑫ 쓰기가 살아 있으면 무응답으로 몰지 않는다(exit 5 = 대기 초과)" 5 "$?"
  kill -TERM "$alive12" "$hung12" 2>/dev/null || true
  wait "$alive12" "$hung12" 2>/dev/null || true

  # ⑬ 즉시 실행이 **무엇을 재려 하는지**를 스스로 적는가 — 판정기의 기대 지문이 여기서 온다.
  #    2026-09-17: 이 기록이 없어서 4차 실행(지표 all_pass · exit 0 · 8h00m04s · 시작==종료==현재 트리)이
  #    예약 이력의 **마지막 낡은 지문**과 비교됐다. 판정기가 “마지막 살아 있는 블록”을 쓰므로,
  #    이 실행의 블록이 마지막에 적히는 것이 이 처방의 핵심이다.
  local t13 st13 st13b stale13 run13 last13
  d="$tmp/t13"
  mkdir -p "$d/out"
  st13="$d/out/soak-schedule.txt"
  st13b="$d/out/schedule-unverified.txt"
  stale13="$(printf '9%.0s' $(seq 1 64))"
  run13="$(_tree_fingerprint)"
  printf '# NX-10 soak 예약 기록\nscheduled_at: 2026-01-01T00:00:00Z\nexpected_fingerprint: %s\n' \
    "$stale13" > "$st13"
  _record_run_expectation 12345 "$run13" "$st13"
  _st_ck "⑬ 즉시 실행의 기대 지문 기록이 성공(exit 0)" 0 "$?"
  _st_ck_has "⑬ 기록이 즉시 실행임을 밝힌다" "$st13" "mode: run (immediate)"
  _st_ck "⑬ 중단 표시를 달지 않는다(살아 있는 기록)" "0" "$(grep -c '^aborted: true' "$st13")"
  last13="$(grep '^expected_fingerprint: ' "$st13" | tail -1 | sed 's/^expected_fingerprint: //')"
  _st_ck "⑬ 마지막 기대값이 이 실행의 것(낡은 예약을 덮는다)" "$run13" "$last13"
  # 계산 실패는 “주장하지 않는다” 로 남는다 — 없던 근거를 만들지 않는다.
  _record_run_expectation 999 "UNVERIFIED" "$st13b"
  _st_ck_has "⑬ 지문 계산 실패는 주장하지 않고 남긴다" "$st13b" "기대값을 주장하지 않는다"

  # 청소: 임시 디렉터리의 가짜 프로세스가 남지 않게 한다.
  pkill -f -- "$tmp" 2>/dev/null || true
  rm -rf "$tmp"
  printf '\n  SOAK_CONTROL_SELFTEST: %s/%s passed\n' "$_st_passed" "$_st_total"
  [ "$_st_passed" = "$_st_total" ]
}

# ── 진입점 ──────────────────────────────────────────────────────────────────
case "${1:-status}" in
  status) shift; cmd_status "$@" ;;
  arm) shift; cmd_arm "$@" ;;
  cancel) shift; cmd_cancel "$@" ;;
  orphans) shift; cmd_orphans "$@" ;;
  preflight) shift; cmd_preflight "$@" ;;
  run) shift; cmd_run "$@" ;;
  harvest) shift; cmd_harvest "$@" ;;
  selftest) shift; cmd_selftest "$@" ;;
  -h | --help | help) sed -n '2,40p' "$0" ;;
  *)
    printf '사용: %s {status|arm|cancel|orphans|preflight|run|harvest|selftest} [--at HH:MM] [--fp <지문>]\n' "$0" >&2
    exit 2
    ;;
esac
