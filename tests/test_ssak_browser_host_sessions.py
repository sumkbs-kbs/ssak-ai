"""task 16 후속 계약 시험 — 브라우저 세션 상한·회수가 **프로세스 경계 너머**에서도 지켜진다.

여기서 고정하는 문장:

- **호스트 전체가 하나의 상한을 센다**: 앱이 자리 2개를 쥐고 있으면 CLI 의 세 번째 시도는
  거절된다(반대도 같다). 이 프로세스가 아무것도 열지 않았어도 그렇다.
- **예약도 자리를 차지한다**: launch 전에 잡은 자리도 다른 프로세스에게는 점유다.
- **죽은 프로세스는 호스트를 인질로 잡지 못한다**: 정리 없이 죽은 프로세스의 자리는 다음
  프로세스가 즉시 걷어낸다.
- **회수는 협조적이다**: 다른 프로세스의 브라우저는 우리가 닫을 수 없다. 그래서 자리를 걷어내고,
  소유 프로세스는 **다음 호출에서** 그 사실을 알고 자기 세션을 닫는다.
- **원장을 못 써도 기동은 막히지 않는다**: 상태 디렉터리·잠금이 안 되면 경고하고 프로세스 안
  규칙으로 퇴화하며, 그 사실이 `status()` 에 드러난다.
- **손상된 원장은 영구 거절이 아니다**: JSON 이 깨져 있으면 옆으로 치우고 새로 시작한다.

시험은 **진짜 자식 프로세스**(`tests/fixtures/browser_host_child.py`)를 띄운다 — 같은 프로세스
안에서 두 소유자를 만들어 세면 pid 가 같아서 "프로세스 경계"를 재지 못한다.
"""

from __future__ import annotations

import json
import os
import subprocess  # noqa: S404 - 우리가 만든 시험용 자식 프로세스만 띄운다
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from antigravity_k.tools import browser_session_owner as owner_module
from antigravity_k.tools.browser_session_ledger import (
    STATE_ENV,
    HostSessionLedger,
    _process_alive,
    state_path,
)
from antigravity_k.tools.browser_session_owner import (
    BrowserOwner,
    BrowserSessionLimitError,
    BrowserSessionOwner,
    describe_policy,
    get_browser_session_owner,
)

REPO = Path(__file__).resolve().parent.parent
CHILD = REPO / "tests" / "fixtures" / "browser_host_child.py"


class _Page:
    """페이지의 최소 계약 — 여기서는 닫혔는지만 본다."""

    def __init__(self) -> None:
        self.url = "about:blank"
        self.closed = 0

    def close(self) -> None:
        self.closed += 1


def _owner(subject: str = "parent@example.com", scope: str = "web-1", task_id: str = "t-1") -> BrowserOwner:
    return BrowserOwner(subject=subject, scope=scope, task_id=task_id)


# ── 자식 프로세스 도구 ──────────────────────────────────────────────────────


def _spawn(mode: str, *, count: int = 1, env: dict[str, str] | None = None) -> subprocess.Popen[str]:
    merged = {**os.environ, "CHILD_COUNT": str(count), **(env or {})}
    return subprocess.Popen(  # noqa: S603 - 고정된 스크립트만 실행한다
        [sys.executable, str(CHILD), mode],
        cwd=str(REPO),
        env=merged,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _read_event(process: subprocess.Popen[str], *, timeout: float = 60.0) -> dict[str, Any]:
    """자식이 찍은 JSON 한 줄. 시간 안에 안 오면 죽이고 실패시킨다(무한 대기 금지)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        line = process.stdout.readline() if process.stdout else ""
        if line.strip():
            payload = json.loads(line)
            assert isinstance(payload, dict)
            return payload
        if process.poll() is not None:
            stderr = process.stderr.read() if process.stderr else ""
            raise AssertionError(f"자식이 결과를 찍지 않고 끝났다: {stderr[-2000:]}")
        time.sleep(0.01)
    process.kill()
    raise AssertionError("자식이 시간 안에 결과를 찍지 않았다")


def _signal(process: subprocess.Popen[str], text: str = "go\n") -> None:
    assert process.stdin is not None
    process.stdin.write(text)
    process.stdin.flush()


def _quit(process: subprocess.Popen[str]) -> dict[str, Any] | None:
    """자식을 정리한다. 죽었으면 None, 살아 있었으면 마지막 이벤트를 돌려준다."""
    if process.poll() is not None:
        return None
    _signal(process, "quit\n")
    event = _read_event(process)
    process.wait(timeout=30)
    return event


@pytest.fixture
def children() -> Iterator[list[subprocess.Popen[str]]]:
    """이 시험이 띄운 자식들. 무엇이 실패하든 남기지 않는다."""
    spawned: list[subprocess.Popen[str]] = []
    yield spawned
    for process in spawned:
        try:
            if process.poll() is None:
                _quit(process)
        except Exception:  # noqa: BLE001 - 정리 실패가 원래 실패를 가리면 안 된다
            process.kill()
        finally:
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()


# ── 상한이 프로세스 경계를 넘는다 ───────────────────────────────────────────


def test_the_cap_counts_sessions_of_another_process(
    children: list[subprocess.Popen[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """앱이 2개를 쥐고 있으면 CLI 의 세 번째는 거절된다 — **이 프로세스는 아무것도 열지 않았는데도**."""
    monkeypatch.setenv("AGK_BROWSER_MAX_SESSIONS", "2")
    child = _spawn("hold", count=2)
    children.append(child)
    event = _read_event(child)
    assert event["error"] == "", event
    assert len(event["slots"]) == 2

    owner = get_browser_session_owner()
    assert owner.active_count == 0, "이 프로세스는 실제로 아무것도 열지 않았다"
    assert owner.host_active_count == 2, "호스트 전체로는 2개다"

    with pytest.raises(BrowserSessionLimitError) as failure:
        _ = owner.begin(_owner("parent"))
    assert "(2/2)" in str(failure.value)
    assert "host" in str(failure.value), "호스트 전역 판정임을 문장이 말해야 한다"
    assert owner.status()["host"]["active"] == 2  # type: ignore[index]

    assert _quit(child) is not None
    assert owner.host_active_count == 0, "자식을 정리하면 자리가 즉시 풀린다"
    reservation = owner.begin(_owner("parent"))
    assert reservation.slot
    owner.abort(reservation)


def test_a_crashed_process_does_not_hold_the_host_cap(
    children: list[subprocess.Popen[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """정리 없이 죽은 프로세스가 상한을 붙잡고 있으면 호스트가 영구히 막힌다."""
    monkeypatch.setenv("AGK_BROWSER_MAX_SESSIONS", "2")
    child = _spawn("hold", count=2, env={"CHILD_EXIT": "crash"})
    children.append(child)
    event = _read_event(child)
    assert len(event["slots"]) == 2

    assert child.stdin is not None
    child.stdin.close()  # EOF → 자식은 close_all() 없이 os._exit 한다
    child.wait(timeout=30)
    assert child.returncode == 0

    owner = get_browser_session_owner()
    reservation = owner.begin(_owner("parent"))  # 죽은 pid 의 자리는 여기서 걷어낸다
    assert reservation.slot, "죽은 프로세스의 자리를 회수하지 못했다"
    reclaimed = owner.status()["host"]["reclaimed"]  # type: ignore[index]
    assert any(item["reason"] == "dead_process" for item in reclaimed), reclaimed
    owner.abort(reservation)


def test_an_idle_session_of_another_process_is_reclaimed_and_its_owner_closes_it(
    children: list[subprocess.Popen[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """회수는 협조적이다 — 자리는 다른 프로세스가 걷어내고, 브라우저는 소유자가 닫는다.

    자식은 **자기 시계로는 놀고 있지 않다**(TTL 900초). 부모만 "1초 놀면 회수" 라고 판정하므로,
    여기서 걷어가는 쪽은 **다른 프로세스**다 — 시험을 통과하는 이유가 자식의 자체 회수면
    계약을 재지 못한다(그래서 회수 이유까지 확인한다).
    """
    monkeypatch.setenv("AGK_BROWSER_MAX_SESSIONS", "2")
    monkeypatch.setenv("AGK_BROWSER_IDLE_TTL_SECONDS", "1")
    child = _spawn("recheck", count=1, env={"AGK_BROWSER_IDLE_TTL_SECONDS": "900"})
    children.append(child)
    event = _read_event(child)
    assert len(event["slots"]) == 1, event
    child_slot = event["slots"][0]

    time.sleep(1.3)  # 부모의 기준으로 자식의 세션이 유휴 TTL 을 넘겼다

    owner = get_browser_session_owner()
    reservation = owner.begin(_owner("parent"))
    assert reservation.slot != child_slot
    reclaimed = owner.status()["host"]["reclaimed"]  # type: ignore[index]
    assert any(item["reason"] == "idle_ttl" and item["slot"] == child_slot for item in reclaimed), (
        f"다른 프로세스가 유휴 자리를 걷어내지 않았다: {reclaimed}"
    )
    owner.abort(reservation)

    _signal(child)
    rechecked = _read_event(child)
    assert rechecked["reuse"] is False, "걷어간 자리를 그대로 재사용하면 상한이 세지 않는 브라우저가 생긴다"
    assert rechecked["slot"] != child_slot
    assert rechecked["closed"] == 1, "소유자가 자기 세션을 실제로 닫아야 한다"


def test_a_session_past_its_task_deadline_is_reclaimed_by_another_process(
    children: list[subprocess.Popen[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """작업 시간을 넘긴 세션도 다른 프로세스가 걷어낸다(그 프로세스가 안 죽었어도)."""
    monkeypatch.setenv("AGK_BROWSER_MAX_SESSIONS", "1")
    monkeypatch.setenv("AGK_BROWSER_TASK_DEADLINE_SECONDS", "1")
    child = _spawn(
        "hold", count=1, env={"AGK_BROWSER_TASK_DEADLINE_SECONDS": "900", "AGK_BROWSER_IDLE_TTL_SECONDS": "900"}
    )
    children.append(child)
    event = _read_event(child)
    assert len(event["slots"]) == 1, event
    child_slot = event["slots"][0]

    time.sleep(1.3)

    owner = get_browser_session_owner()
    reservation = owner.begin(_owner("parent"))
    assert reservation.slot and reservation.slot != child_slot
    reclaimed = owner.status()["host"]["reclaimed"]  # type: ignore[index]
    assert any(item["reason"] == "task_deadline" and item["slot"] == child_slot for item in reclaimed), (
        f"작업 deadline 을 넘긴 자리를 걷어내지 않았다: {reclaimed}"
    )
    owner.abort(reservation)


def test_reservations_also_take_host_wide_slots(
    children: list[subprocess.Popen[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """launch 전 예약도 다른 프로세스에게는 점유다(동시 첫 호출이 브라우저를 여러 개 띄우지 않게)."""
    monkeypatch.setenv("AGK_BROWSER_MAX_SESSIONS", "2")
    owner = get_browser_session_owner()
    first = owner.begin(_owner("parent", scope="a"))
    second = owner.begin(_owner("parent", scope="b"))

    child = _spawn("once", count=1)
    children.append(child)
    event = _read_event(child)
    assert event["slots"] == [], "예약 2개가 자리를 차지했는데 자식이 열었다"
    assert "(2/2)" in event["error"]

    owner.abort(first)
    owner.abort(second)
    assert owner.host_active_count == 0
    after = _spawn("once", count=1)
    children.append(after)
    assert len(_read_event(after)["slots"]) == 1, "예약을 반납하면 자리가 즉시 풀려야 한다"


def test_release_frees_the_slot_for_another_process(
    children: list[subprocess.Popen[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGK_BROWSER_MAX_SESSIONS", "1")
    owner = get_browser_session_owner()
    reservation = owner.begin(_owner("parent"))
    page = _Page()
    _ = owner.commit(reservation, page=page, close=page.close)

    blocked = _spawn("once", count=1)
    children.append(blocked)
    assert _read_event(blocked)["error"] != "", "호스트가 가득 찼는데 자식이 열었다"

    assert owner.release(_owner("parent")) is True
    assert owner.host_active_count == 0

    freed = _spawn("once", count=1)
    children.append(freed)
    assert len(_read_event(freed)["slots"]) == 1


def test_the_host_cap_holds_when_six_processes_race(
    children: list[subprocess.Popen[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """동시 첫 호출이 상한을 넘기지 않는다 — 파일 잠금과 자리 수 셈을 함께 잰다.

    잠금이 없거나(둘이 같은 시점에 읽고 쓰면 서로를 덮어쓴다) 이 프로세스 것만 세면 통과한
    자식이 3개 이상 나온다.
    """
    monkeypatch.setenv("AGK_BROWSER_MAX_SESSIONS", "2")
    racers = [_spawn("hold", count=1) for _ in range(6)]
    children.extend(racers)
    events = [_read_event(process) for process in racers]

    granted = [event for event in events if event["slots"]]
    refused = [event for event in events if event["error"]]
    assert len(granted) == 2, f"상한 2 를 넘겨 열렸다: {events}"
    assert len(refused) == 4
    assert all("(2/2)" in event["error"] for event in refused)
    assert get_browser_session_owner().host_active_count == 2


def test_admission_waits_for_the_file_lock() -> None:
    """원장은 임계구역 안에서만 바뀐다 — 잠금을 무시하면 둘이 같은 것을 읽고 서로를 덮어쓴다.

    파일 잠금은 같은 프로세스의 **다른 파일 서술자**끼리도 충돌한다(`flock` 은 서술자에 붙는다).
    그래서 원장 두 개를 만들어 한쪽이 임계구역을 잡고 있는 동안 다른 쪽의 자리 요청이 **기다리는지**를
    잴 수 있다.
    """
    holder = HostSessionLedger(wall_clock=_Wall(), pid=os.getpid())
    waiter = HostSessionLedger(wall_clock=_Wall(), pid=os.getpid())
    finished = threading.Event()

    def _admit() -> None:
        _ = waiter.admit(owner_key="waiter", max_active=2, idle_ttl=900.0, task_deadline=600.0)
        finished.set()

    with holder._locked():  # noqa: SLF001 - 계약 자체(임계구역)를 재는 시험이다
        thread = threading.Thread(target=_admit, daemon=True)
        thread.start()
        assert not finished.wait(0.4), "임계구역을 잡고 있는데 다른 쪽이 그냥 들어왔다"
    thread.join(timeout=10)
    assert finished.is_set(), "잠금이 풀렸는데도 자리 요청이 끝나지 않았다"
    assert waiter.host_active() == 1


# ── 원장이 없을 때·깨졌을 때 ────────────────────────────────────────────────


def test_an_unwritable_ledger_degrades_to_per_process_rules(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """상태 디렉터리를 못 만들어도 기동이 막히면 안 된다 — 대신 그 사실이 드러나야 한다."""
    blocker = tmp_path / "blocker"
    _ = blocker.write_text("디렉터리가 아니라 파일이다", encoding="utf-8")
    monkeypatch.setenv(STATE_ENV, str(blocker / "sessions.json"))
    monkeypatch.setenv("AGK_BROWSER_MAX_SESSIONS", "2")

    owner = get_browser_session_owner()
    first = owner.begin(_owner("a", scope="a"))
    assert first.slot == "", "원장을 못 쓰면 자리 표식이 없다"
    _ = owner.commit(first, page=_Page(), close=lambda: None)
    second = owner.begin(_owner("a", scope="b"))
    _ = owner.commit(second, page=_Page(), close=lambda: None)

    ledger = owner.status()["host"]["ledger"]  # type: ignore[index]
    assert ledger["degraded"] is True
    assert ledger["degrade_reason"], "왜 퇴화했는지 말해야 한다"
    assert ledger["file"] == "sessions.json"

    # 퇴화 모드에서도 프로세스 안 상한은 살아 있다(상한 자체가 사라지면 그것도 결함이다).
    owner.close_all()
    for scope in ("a", "b"):
        reservation = owner.begin(_owner("a", scope=scope))
        _ = owner.commit(reservation, page=_Page(), close=lambda: None)
    with pytest.raises(BrowserSessionLimitError):
        _ = owner.begin(_owner("a", scope="c"))


def test_a_corrupt_ledger_is_quarantined_instead_of_denying_forever(monkeypatch: pytest.MonkeyPatch) -> None:
    """손상된 원장이 영구 거절이 되면 호스트에서 브라우저를 영원히 못 연다."""
    target = state_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = target.write_text("{ 이건 JSON 이 아니다", encoding="utf-8")

    owner = get_browser_session_owner()
    reservation = owner.begin(_owner("a"))
    assert reservation.slot, "손상된 원장을 버리고 새로 시작해야 한다"
    assert list(target.parent.glob(f"{target.name}.corrupt-*")), "손상된 원장은 옆으로 치워 둔다"
    owner.abort(reservation)


def test_status_reports_the_host_wide_count_without_leaking_the_state_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGK_BROWSER_MAX_SESSIONS", "2")
    owner = get_browser_session_owner()
    reservation = owner.begin(_owner("a"))
    _ = owner.commit(reservation, page=_Page(), close=lambda: None)

    status = owner.status()
    text = json.dumps(status, ensure_ascii=False, default=str)
    target = state_path()
    assert status["host"]["active"] == 1  # type: ignore[index]
    assert status["host"]["ledger"]["file"] == target.name  # type: ignore[index]
    assert str(target.parent) not in text, "상태 응답이 사용자 홈 경로를 나르면 안 된다"
    assert status["max_active_sessions"] == 2


# ── 소유자 밖에 두 번째 셈이 없다(소스 게이트) ──────────────────────────────

_ENTRYPOINTS = (
    "api/routes/agent_tools.py",
    "tools/browser_tools.py",
    "tools/browser_tool.py",
    "agents/browser_surfing_agent.py",
    "engine/harness.py",
    "engine/autonomous_qa.py",
)


def test_no_entrypoint_counts_sessions_on_its_own() -> None:
    """상한을 세는 곳은 원장 하나뿐이어야 한다 — 진입점이 자기 수를 세면 경계 너머는 다시 깨진다."""
    for name in _ENTRYPOINTS:
        source = (REPO / "src" / "antigravity_k" / name).read_text(encoding="utf-8")
        assert "browser_sessions.json" not in source, name
        assert "flock" not in source, f"{name} 가 원장 파일을 직접 다룬다"
        assert "STATE_ENV" not in source, f"{name} 가 원장 경로를 스스로 해석한다"
        assert "max_active_sessions" not in source or "get_browser_session_owner()" in source, name

    ledger_source = (REPO / "src" / "antigravity_k" / "tools" / "browser_session_ledger.py").read_text(encoding="utf-8")
    assert "flock" in ledger_source, "원장이 파일 잠금을 쓰지 않으면 동시 첫 호출이 서로를 덮어쓴다"

    owner_source = (REPO / "src" / "antigravity_k" / "tools" / "browser_session_owner.py").read_text(encoding="utf-8")
    assert "self._ledger.admit(" in owner_source, "소유자가 공유 원장에 자리를 요청하지 않는다"
    # 프로세스 안 수를 기준으로 거절하는 문장은 **퇴화 모드 전용으로 하나만** 남아야 한다.
    assert owner_source.count("if self.active_count >= self.max_active_sessions:") == 1


def test_configured_policy_says_the_cap_is_host_wide() -> None:
    policy = describe_policy()
    assert policy["host_sessions"]["cap_is_host_wide"] is True  # type: ignore[index]
    assert policy["env"]["session_state"] == STATE_ENV  # type: ignore[index]
    assert policy["host_sessions"]["shared_ledger_file"] == state_path().name  # type: ignore[index]


class _Wall:
    """시험이 움직이는 벽시계(파일에 실리는 시각은 이걸로 만든다)."""

    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_the_ledger_uses_wall_clock_so_other_processes_can_compare() -> None:
    """단조 시계는 프로세스마다 기준점이 달라 파일에 실리면 비교할 수 없다."""
    wall = _Wall()
    ledger = HostSessionLedger(wall_clock=wall, pid=os.getpid())
    decision = ledger.admit(owner_key="k", max_active=1, idle_ttl=900.0, task_deadline=600.0)
    assert decision.slot
    assert ledger.entries()[0].opened_at == 1000.0, "파일에 실리는 시각은 벽시계여야 한다"

    wall.advance(5)
    assert ledger.heartbeat(decision.slot) is True
    assert ledger.entries()[0].last_used_at == 1005.0


def test_decisions_report_what_was_reclaimed() -> None:
    """회수 판정은 그냥 사라지면 안 된다 — 누구의 무엇을 왜 걷어냈는지 남아야 한다."""
    ghost_pid = 999_999_999
    assert _process_alive(ghost_pid) is False, "이 시험은 확실히 죽은 pid 를 전제한다"

    ledger = HostSessionLedger()
    ghost = HostSessionLedger(path=ledger.path(), pid=ghost_pid)
    assert ghost.admit(owner_key="ghost", max_active=2, idle_ttl=900.0, task_deadline=600.0).slot

    decision = ledger.admit(owner_key="live", max_active=2, idle_ttl=900.0, task_deadline=600.0)
    reclaimed = [item for item in decision.reclaimed if item["reason"] == "dead_process"]
    assert reclaimed, decision.reclaimed
    assert reclaimed[0]["slot"] and reclaimed[0]["pid"] == ghost_pid


def test_owner_module_exposes_the_ledger_for_diagnostics() -> None:
    owner = BrowserSessionOwner()
    assert isinstance(owner_module.STATE_ENV, str)
    assert owner.ledger.path().name.endswith(".json")
