from __future__ import annotations

import os
from typing import Literal, assert_never

from pydantic import TypeAdapter, ValidationError

from antigravity_k.engine.task_state_types import TaskStatusName

_status_adapter: TypeAdapter[TaskStatusName] = TypeAdapter(TaskStatusName)

# 보고용 파생 값 — **저장하지 않는다**. `running` 행의 실행 주인이 지금 살아 있는가.
#   live  : 소유 pid 가 살아 있다(그 프로세스가 이 태스크를 실행 중이다)
#   dead  : 소유 pid 가 있지만 죽었다(크래시·재시작 — 아무도 실행하지 않는다)
#   none  : 실행 중이 아니거나(terminal·pending·paused) 소유 pid 가 없다
ExecutionOwner = Literal["live", "dead", "none"]


def execution_owner_of(raw_status: str, owner_pid: int | None) -> ExecutionOwner:
    """이 행의 실행 주인이 **지금 살아 있는가** — F-36 의 보고 필드가 나오는 유일한 자리다.

    F-36: 서버가 크래시해 다시 뜨면, 죽은 소유자의 `running` 행이 표면에서 **살아 있는 실행과
    구별되지 않았다**. 저장소는 그 판정(`_process_is_alive`)을 이미 소유하고 있었지만
    **행동**(`can_prepare_resume`·`can_cancel` 의 허용)에만 썼고 **보고**에는 쓰지 않았다 —
    그래서 화면(`TaskQueuePanel`)은 복구 가능한 태스크를 "실행 중"으로 읽고 **재개 대신 취소만**
    제안했다. 이 함수가 그 값을 만드는 한 곳이고, `can_*` 와 **같은 liveness 함수**를 쓴다.

    판정 규칙은 `can_prepare_resume`/`can_cancel` 과 같은 모양이다: 터미널·`pending`·`paused` 는
    실행 중이 아니므로 `"none"`(주인이 없다), `running`/`resuming` 은 소유 pid 의 생존 여부다.
    소유 pid 가 없는 `running`(레거시 행)도 `"none"` 이다 — "살아 있다"고 말할 근거가 없기 때문이다.
    """
    try:
        status = _status_adapter.validate_python(raw_status)
    except ValidationError:
        return "none"
    match status:
        case "running" | "resuming":
            if owner_pid is None:
                return "none"
            return "live" if _process_is_alive(owner_pid) else "dead"
        case "pending" | "paused" | "done" | "failed" | "cancelled":
            return "none"
    assert_never(status)


def resumable_task(raw_status: str, owner_pid: int | None, has_checkpoint: bool) -> bool:
    """`POST /resume` 이 이 행에 대해 **성공할 것인가** — 표면과 행동이 같은 함수를 쓴다.

    행동(`BackgroundTaskRunner.resume_task`)은 ① 체크포인트가 있어야 하고
    ② `TaskStateStore.prepare_resume` 이 `can_prepare_resume` 을 만족해야 한다. 그 둘을 그대로
    옮긴 것이 이 함수다 — 화면이 버튼을 그릴 근거와 서버가 받아줄 근거가 갈라지면, 버튼은
    눌러도 404 가 나거나(과잉) 복구 가능한 태스크에 버튼이 없다(과소).
    """
    return has_checkpoint and can_prepare_resume(raw_status, owner_pid)


def owner_pid_for_raw_status(raw_status: str) -> int | None:
    """문자열 상태를 검증해 `owner_pid_for_status` 로 넘긴다 — 보고 표면이 쓰는 경로다.

    `TaskStatusName`(Literal)은 **검증된** 상태에만 붙는다. 저장소를 거치는 값은 문자열이므로,
    검증을 이 한 곳에서 해서 규칙을 복제하지 않는다(모르는 상태는 소유자 없음으로 본다).
    """
    try:
        status = _status_adapter.validate_python(raw_status)
    except ValidationError:
        return None
    return owner_pid_for_status(status)


def owner_pid_for_status(status: TaskStatusName) -> int | None:
    match status:
        case "running" | "resuming":
            return os.getpid()
        case "pending" | "paused" | "done" | "failed" | "cancelled":
            return None
    assert_never(status)


def can_prepare_resume(raw_status: str, owner_pid: int | None) -> bool:
    try:
        status = _status_adapter.validate_python(raw_status)
    except ValidationError:
        return False
    match status:
        case "paused" | "failed":
            return True
        case "running" | "resuming":
            return owner_pid is not None and owner_pid != os.getpid() and not _process_is_alive(owner_pid)
        case "pending" | "done" | "cancelled":
            return False
    assert_never(status)


def can_cancel(raw_status: str, owner_pid: int | None) -> bool:
    """이 프로세스가 그 행을 `cancelled` 로 적어도 되는가 — 소유 규칙은 `can_prepare_resume` 과 같다.

    `resume` 은 소유자를 보는데 `cancel` 은 보지 않았고, 그래서 **살아 있는 다른 프로세스의**
    `running` 태스크를 `cancelled` 로 적을 수 있었다(F-35). 그 행은 "끝났다"고 말하지만
    취소 신호(`cancel_event`)는 그 프로세스 **안에** 있으므로 실행은 계속된다 — 이력이 거짓이 된다.

    - `pending`/`paused`: **허용한다.** `pending` 은 아직 실행 시작 전이라 소유자가 없고, 취소가
      먼저 적히면 소유자의 시작 CAS(`pending → running`)가 실패해 **실행되지 않는다**(거짓이 아니라
      실제로 취소된다). `paused` 는 실행 중이 아니다.
    - `running`/`resuming`: **소유자가 살아 있으면 거부한다** — 이 프로세스이거나,
      소유자가 없거나(레거시 행), 소유자 PID 가 이미 죽었을 때만 허용한다. 그 판정 함수
      (`_process_is_alive`)를 `resume` 과 **공유**하는 것이 요점이다: 두 경로가 다른 규칙을
      쓰면 그 사이가 조용한 자리가 된다.
    - 터미널 상태: 취소할 대상이 아니다.
    """
    try:
        status = _status_adapter.validate_python(raw_status)
    except ValidationError:
        return False
    match status:
        case "pending" | "paused":
            return True
        case "running" | "resuming":
            return owner_pid is None or owner_pid == os.getpid() or not _process_is_alive(owner_pid)
        case "done" | "failed" | "cancelled":
            return False
    assert_never(status)


def _process_is_alive(pid: int) -> bool:
    if pid <= 0:
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
