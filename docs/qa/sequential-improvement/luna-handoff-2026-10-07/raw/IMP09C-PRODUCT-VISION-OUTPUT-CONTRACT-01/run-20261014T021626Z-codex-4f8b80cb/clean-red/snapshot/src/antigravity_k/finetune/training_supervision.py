"""TRN-02 — 학습 subprocess 감독: timeout · 무출력 hang · cancel · 프로세스 그룹 종료.

lora_pipeline.run_training과 finetune.training_adapter.run_resolved_training이
공유하는 감독 로직. POSIX에서는 ``start_new_session=True``로 새 프로세스 그룹을
만들어 parent+descendant를 ``killpg``로 함께 종료한다.

계약 (docs/11_COMMERCIAL_GA_100_PLAN.md §TRN-02):
- ``timeout_sec``는 실제 process에 적용된다 (벽시계 상한).
- ``no_output_timeout_sec``는 stdout 정체(hung)를 감지해 종료한다.
- cancel_event가 set되면 프로세스 그룹 전체가 종료된다.
- 종료는 SIGTERM → grace → SIGKILL 단계로 idempotent하다.
- 이 모듈은 stdlib만 사용한다 (engine/finetune 간 순환 import 방지).
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Literal

TERMINATION_GRACE_SEC = 5.0
WATCHDOG_POLL_SEC = 0.2

TerminationReason = Literal["completed", "timeout", "no_output_hang", "cancelled"]

_REASON_DETAIL: dict[str, str] = {
    "timeout": "timeout_sec 초과로 학습 프로세스를 종료했습니다",
    "no_output_hang": "무출력 hang 감지 — 제한 시간 내 출력이 없어 학습 프로세스를 종료했습니다",
    "cancelled": "cancelled by user",
}


@dataclass(slots=True)
class SupervisionOutcome:
    """감독된 프로세스 실행 결과."""

    reason: TerminationReason = "completed"
    return_code: int | None = None
    output: list[str] = field(default_factory=list)
    detail: str = ""

    @property
    def success(self) -> bool:
        return self.reason == "completed" and self.return_code == 0


@dataclass(slots=True)
class _WatchdogState:
    lock: threading.Lock = field(default_factory=threading.Lock)
    last_output_monotonic: float = field(default_factory=time.monotonic)
    fired_reason: TerminationReason | None = None


def _signal_group(proc: subprocess.Popen[str], sig: int) -> None:
    """프로세스 그룹에 시그널 전송. POSIX가 아니면 단일 프로세스 fallback."""
    pid = getattr(proc, "pid", None)
    if pid is None or proc.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(os.getpgid(pid), sig)
        else:
            proc.send_signal(sig)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def terminate_process_group(proc: subprocess.Popen[str], grace_sec: float = TERMINATION_GRACE_SEC) -> None:
    """SIGTERM → grace → SIGKILL. 여러 번 호출해도 안전(idempotent)."""
    if proc.poll() is not None:
        return
    _signal_group(proc, signal.SIGTERM)
    try:
        proc.wait(timeout=grace_sec)
        return
    except subprocess.TimeoutExpired:
        pass
    if proc.poll() is None:
        _signal_group(proc, signal.SIGKILL)
    try:
        proc.wait(timeout=grace_sec)
    except subprocess.TimeoutExpired:
        pass


def start_watchdog(
    proc: subprocess.Popen[str],
    state: _WatchdogState,
    *,
    timeout_sec: float | None,
    no_output_timeout_sec: float | None,
    cancel_event: threading.Event | None,
    on_fire: Callable[[TerminationReason], None] | None = None,
) -> threading.Thread:
    """감독 watchdog 스레드. timeout / no-output / cancel 시 그룹을 종료한다."""

    def _run() -> None:
        started = time.monotonic()
        while proc.poll() is None:
            now = time.monotonic()
            reason: TerminationReason | None = None
            if cancel_event is not None and cancel_event.is_set():
                reason = "cancelled"
            elif timeout_sec is not None and now - started >= timeout_sec:
                reason = "timeout"
            elif no_output_timeout_sec is not None:
                with state.lock:
                    last = state.last_output_monotonic
                if now - last >= no_output_timeout_sec:
                    reason = "no_output_hang"
            if reason is not None:
                with state.lock:
                    if state.fired_reason is None:
                        state.fired_reason = reason
                    else:
                        reason = None
                if reason is not None:
                    if on_fire is not None:
                        on_fire(reason)
                    terminate_process_group(proc)
                    return
            time.sleep(WATCHDOG_POLL_SEC)

    thread = threading.Thread(target=_run, name="training-watchdog", daemon=True)
    thread.start()
    return thread


def read_output_loop(
    proc: subprocess.Popen[str],
    state: _WatchdogState,
    on_output: Callable[[str], None] | None = None,
) -> list[str]:
    """stdout(stderr 병합)을 라인 단위로 읽으며 last_output 타임스탬프를 갱신한다."""
    lines: list[str] = []
    assert proc.stdout is not None
    for raw in proc.stdout:
        line = raw.rstrip()
        lines.append(line)
        with state.lock:
            state.last_output_monotonic = time.monotonic()
        if on_output is not None:
            on_output(line)
    return lines


def supervise_command(
    argv: Sequence[str],
    *,
    cwd: str | os.PathLike[str] | None = None,
    timeout_sec: float | None = None,
    no_output_timeout_sec: float | None = None,
    cancel_event: threading.Event | None = None,
    on_output: Callable[[str], None] | None = None,
    on_proc_start: Callable[[subprocess.Popen[str]], None] | None = None,
    env: dict[str, str] | None = None,
) -> SupervisionOutcome:
    """명령을 새 프로세스 그룹으로 실행하고 감독한다. (TRN-02 단일 진입점)

    - 프로세스는 ``start_new_session=True``로 실행되어 parent+descendant가
      한 그룹이 된다. 종료 시 ``killpg``로 그룹 전체가 함께 종료된다.
    - timeout/no-output/cancel이 발생하면 SIGTERM → grace → SIGKILL.
    - 정상 종료는 완료된 출력을 그대로 반환한다.
    """
    popen_kwargs: dict[str, object] = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "bufsize": 1,
    }
    if os.name == "posix":
        popen_kwargs["start_new_session"] = True
    if cwd is not None:
        popen_kwargs["cwd"] = cwd
    if env is not None:
        popen_kwargs["env"] = env

    proc = subprocess.Popen(
        list(argv),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=cwd,
        env=env,
        start_new_session=(os.name == "posix"),
    )
    if on_proc_start is not None:
        on_proc_start(proc)

    state = _WatchdogState()
    watchdog = start_watchdog(
        proc,
        state,
        timeout_sec=timeout_sec,
        no_output_timeout_sec=no_output_timeout_sec,
        cancel_event=cancel_event,
    )
    lines = read_output_loop(proc, state, on_output=on_output)
    exit_code = proc.wait() if proc.poll() is None else proc.returncode
    watchdog.join(timeout=WATCHDOG_POLL_SEC + 0.5)

    with state.lock:
        fired = state.fired_reason
    if fired is None and cancel_event is not None and cancel_event.is_set() and exit_code != 0:
        # TRN-02/F-15 — 사유를 **관측이 아니라 사실**로 결정한다.
        #
        # `task_process_supervisor.cancel_task` 는 event 를 set 하는 것과 **동시에**
        # terminate 한다. 그래서 프로세스가 watchdog 의 다음 폴링(최대 0.2초)보다 빨리
        # 죽으면 watchdog 은 `fired_reason` 을 세우지 못하고 루프를 빠져나간다 — 그러면
        # 취소로 죽었는데도(exit_code != 0) 사유가 `completed` 로 남고, 취소 핸들러가
        # 기록한 `cancelled` 를 잡 스레드가 덮어써 "취소했다"는 사실이 사라진다.
        # 정상 종료는 exit_code == 0 이므로 이 보정은 정상 완료를 취소로 바꾸지 않는다.
        fired = "cancelled"
    reason: TerminationReason = "completed" if fired is None else fired
    return SupervisionOutcome(
        reason=reason,
        return_code=exit_code,
        output=lines,
        detail=_REASON_DETAIL.get(reason, ""),
    )
