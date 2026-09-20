#!/usr/bin/env python3
"""작업 재개 시험용 **자식 프로세스** (task 20).

시험이 재고 싶은 것은 "진짜 프로세스가 행동을 보낸 직후에 죽으면 어떻게 되는가" 다. 그래서 이
파일은 실제 브라우저·실제 HTTP 서버를 상대로 **진짜 작업**을 돌리고, 정해진 지점에서 스스로
SIGKILL 을 맞는다(정리도 flush 도 없다 — 그것이 크래시의 정의다).

모드:
  - `crash_before_submit` — **실제 브라우저 경로**. 제출 버튼의 발송 기록이 남은 직후(페이지를
    건드리기 전) 죽는다. 저널에는 intent + dispatched 만 남고 결과는 없다. 이때 효과는 **실제 분류기**가
    정한다(제출 버튼 → `transmit`) — 시험이 그 값을 확인한다.
  - `crash_after_submit`  — 서버에 **실제로** POST 한 뒤(변경 1회 발생) 결과 기록 전에 죽는다.
    task 18 의 결정 때문에 되돌릴 수 없는 클릭은 승인 없이 루프가 누를 수 없으므로, 이 모드는 그
    창(window)을 **합성 호스트**로 재현한다: 루프와 저널은 실제 코드이고, 행동은 진짜 HTTP 요청이다.
  - `pause_read`          — 실제 브라우저로 **읽기 행동**(링크 이동)을 하나 마친 뒤 죽는다(변경 0회).
  - `resume_read`         — 이어받아 성공까지 간다(새 관찰로 시작).
  - `duplicate_read`      — 읽기 작업을 `run_task` 로 정상 완료시킨다(중복 요청 시험의 기준).
  - `duplicate_submit`    — **미확정** 제출 작업을 같은 키로 다시 요청한다: 실행 대신 그 사실이 돌아와야 한다.
  - `resume_only`         — 재개 판정만 받아 JSON 한 줄로 찍는다(브라우저를 열지 않는다).

결과는 마지막 줄에 JSON 한 줄로 찍는다. 실패는 stderr 와 비0 종료로 드러난다.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from antigravity_k.agents.browser_surfing_agent import BrowserSurfingAgent  # noqa: E402
from antigravity_k.agents.browser_task_loop import (  # noqa: E402
    BrowserTaskError,
    BrowserTaskLoop,
    PlannedAction,
    Postcondition,
    TaskBudget,
    TaskGoal,
    TaskMeasurement,
    TaskOutcome,
    TaskStep,
)
from antigravity_k.tools.browser_observation import ActionResult, ElementRef, Observation  # noqa: E402
from antigravity_k.tools.browser_session_owner import get_browser_session_owner  # noqa: E402
from antigravity_k.tools.browser_task_journal import BrowserTaskJournal  # noqa: E402

MODE_CHOICES = frozenset(
    {
        "crash_before_submit",
        "crash_after_submit",
        "pause_read",
        "resume_read",
        "resume_only",
        "duplicate_read",
        "duplicate_submit",
    }
)

SENT_GOAL = TaskGoal(
    goal="송금이 완료됐는지 확인한다",
    postconditions=(Postcondition("flag_equals", "1", key="sent"),),
)
LINK_GOAL = TaskGoal(
    goal="다음 페이지에 이체 내역이 있는지 확인한다",
    postconditions=(Postcondition("url_contains", "/page2"), Postcondition("text_contains", "이체 내역")),
)


def _die() -> None:
    """진짜 죽음(SIGKILL) — 정리도, flush 도 없다."""
    os.kill(os.getpid(), signal.SIGKILL)


def _allow_local_egress() -> None:
    """루프백 fixture 서버를 열기 위해 **이 자식만** egress 를 연다.

    제품 경로가 스스로 로컬을 열지 않는다는 사실은 task 16 계약 시험이 재고, 저장소의 다른
    브라우저 시험들도 같은 방식으로 이 시험 하나에서만 연다.
    """
    owner = get_browser_session_owner()
    original = owner.validate_navigation

    def _validate(url: str, *, allow_local: bool = False) -> str:
        return original(url, allow_local=True)

    owner.validate_navigation = _validate  # type: ignore[method-assign]


def _ref_for(observation: object, name: str) -> str | None:
    """관찰이 발급한 ref 중 이름이 맞는 것 하나(없으면 누를 수 있는 첫 요소)."""
    refs = list(getattr(observation, "refs", ()))
    for item in refs:
        if getattr(item, "name", "") == name:
            return str(getattr(item, "ref", "")) or None
    for item in refs:
        if getattr(item, "role", "") in {"button", "link"}:
            return str(getattr(item, "ref", "")) or None
    return None


class _ScriptedPlanner:
    """모델 없이 결정적으로 계획한다: 첫 계획은 `first`, 그 다음부터는 `second`."""

    def __init__(self, *, target: str, first: str, second: str) -> None:
        self.target = target
        self.first = first
        self.second = second
        self.calls = 0

    async def plan(
        self, *, goal: TaskGoal, observation: object, history: object, remaining_actions: int
    ) -> PlannedAction:  # noqa: ARG002 - 계약상 쓰지 않는 인자
        self.calls += 1
        action = self.first if self.calls == 1 else self.second
        return PlannedAction(
            action=action,
            ref=_ref_for(observation, self.target) if action != "done" else None,
            target_name=self.target,
            reason=f"{self.target or action} 를 {action}",
        )


class _KillAfterAct:
    """실제 호스트를 감싸 **행동이 끝난 직후, 결과가 기록되기 전에** 죽는다."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    async def observe(self) -> Any:
        return await self._inner.observe()

    async def act(self, action: PlannedAction) -> Any:
        result = await self._inner.act(action)
        _die()
        return result

    async def measure(self) -> Any:
        return await self._inner.measure()

    def effect_of(self, action: PlannedAction) -> str:
        return str(self._inner.effect_of(action))


class _SubmitHost:
    """되돌릴 수 없는 효과를 **실제로** 보내는 합성 호스트: POST /submit 이 곧 변경이다.

    task 18 이후 이런 행동은 승인 없이 루프가 누를 수 없다. 그래서 그 창(window)만 여기서 만들고,
    루프·저널·서버는 전부 실제 것을 쓴다 — 재는 것은 저널의 크래시 계약이다.
    """

    def __init__(self, base_url: str) -> None:
        self._base = base_url
        self._sent = False
        self.acts = 0

    def effect_of(self, action: PlannedAction) -> str:
        return "transmit"

    async def observe(self) -> Observation:
        return Observation(
            session_tag="tag001",
            snapshot_id="snap1",
            generation=1,
            page_key="main",
            url=f"{self._base}/form",
            title="송금",
            captured_at="2026-09-20T00:00:00Z",
            refs=(ElementRef(ref="tag001-snap1-main-e0", role="button", name="송금", tag="button", frame="main"),),
            accessibility='button "송금"',
        )

    async def act(self, action: PlannedAction) -> ActionResult:
        if action.action == "done":
            return ActionResult(action=action.action, performed=False, goal_verified=False, detail="")
        self.acts += 1
        payload = urllib.parse.urlencode({"amount": "100"}).encode()
        request = urllib.request.Request(f"{self._base}/submit", data=payload, method="POST")  # noqa: S310 - 로컬 시험 서버
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310 - 로컬 시험 서버
            _ = response.read()
        self._sent = True
        _die()  # 서버는 이미 변경을 기록했고, 저널에는 그 결과가 없다
        return ActionResult(
            action=action.action,
            performed=True,
            goal_verified=True,
            detail="",
            ref=action.ref,
            snapshot_id="snap1",
            generation=1,
            url_before=f"{self._base}/form",
            url_after=f"{self._base}/submit",
        )

    async def measure(self) -> TaskMeasurement:
        return TaskMeasurement(
            url=f"{self._base}/submit" if self._sent else f"{self._base}/form",
            title="송금",
            text="송금 완료" if self._sent else "송금",
            flags={"sent": "1"} if self._sent else {},
            ref_names=frozenset({"송금"}),
            generation=1,
        )


def _payload(outcome: TaskOutcome) -> dict[str, object]:
    return {
        "status": outcome.status.value,
        "code": outcome.code,
        "actions": outcome.actions_performed,
        "verified": outcome.verified_count,
        "cancel_mode": outcome.cancel_mode,
    }


async def _run(mode: str, base_url: str, task_id: str, key: str) -> dict[str, object]:
    journal = BrowserTaskJournal()

    if mode == "resume_only":
        return journal.resume_plan(task_id).to_dict()

    agent = BrowserSurfingAgent(model_manager=None)

    if mode == "crash_after_submit":
        journal.open_task(task_id, goal=SENT_GOAL.goal, idempotency_key=key)
        loop = BrowserTaskLoop(
            _ScriptedPlanner(target="송금", first="click", second="done"),
            budget=TaskBudget(action_budget=3),
            journal=journal,
            task_id=task_id,
        )
        outcome = await loop.run(SENT_GOAL, _SubmitHost(base_url))
        return _payload(outcome)

    if mode == "duplicate_submit":
        # 발송된 뒤 결과를 모르는 작업을 같은 키로 다시 요청한다 — 이 경로는 **실행되면 안 된다**.
        outcome = await agent.run_task(
            base_url,
            SENT_GOAL,
            budget=TaskBudget(action_budget=3),
            planner=_ScriptedPlanner(target="송금", first="click", second="done"),
            journal=journal,
            task_id=task_id,
            idempotency_key=key,
        )
        return _payload(outcome)

    if mode == "duplicate_read":
        # 실제 제품 경로(`run_task`)로 중복 판정을 지난다 — 두 번째 요청은 브라우저를 열지 않아야 한다.
        outcome = await agent.run_task(
            base_url,
            LINK_GOAL,
            budget=TaskBudget(action_budget=3),
            planner=_ScriptedPlanner(target="다음", first="click", second="done"),
            journal=journal,
            task_id=task_id,
            idempotency_key=key,
        )
        return _payload(outcome)

    if mode == "crash_before_submit":

        def _kill_after_dispatch(intent: object) -> None:
            # 발송 기록은 이미 파일에 있다 — 여기서 죽으면 "보냈는데 결과를 모른다" 가 남는다.
            _ = intent
            _die()

        journal.open_task(task_id, goal=SENT_GOAL.goal, idempotency_key=key)
        loop = BrowserTaskLoop(
            _ScriptedPlanner(target="송금", first="click", second="done"),
            budget=TaskBudget(action_budget=3),
            journal=journal,
            task_id=task_id,
            on_dispatch=_kill_after_dispatch,
        )
        async with agent.browser_task_host(base_url) as host:
            await loop.run(SENT_GOAL, host)
        return {"status": "unreachable"}

    if mode == "pause_read":
        journal.open_task(task_id, goal=LINK_GOAL.goal, idempotency_key=key)

        def _kill_after_one_step(step: TaskStep) -> None:
            if step.performed:
                _die()

        loop = BrowserTaskLoop(
            _ScriptedPlanner(target="다음", first="click", second="click"),
            budget=TaskBudget(action_budget=4),
            journal=journal,
            task_id=task_id,
            on_step=_kill_after_one_step,
        )
        async with agent.browser_task_host(base_url) as host:
            await loop.run(LINK_GOAL, host)
        return {"status": "unreachable"}

    if mode == "resume_read":
        resumed = journal.resume_plan(task_id)
        if not resumed.replay_allowed:
            return resumed.to_dict()
        journal.record_resumed(task_id, must_reobserve=resumed.must_reobserve)
        try:
            outcome = await agent.run_task(
                base_url,
                LINK_GOAL,
                budget=TaskBudget(action_budget=3),
                planner=_ScriptedPlanner(target="다음", first="click", second="done"),
                journal=journal,
                task_id=task_id,
                idempotency_key=key,
            )
        except BrowserTaskError as exc:  # 계획 주체 문제는 그대로 알린다
            return {"status": "error", "code": exc.code}
        return _payload(outcome)

    raise SystemExit(f"unknown mode: {mode!r} (choose from {sorted(MODE_CHOICES)})")


def main() -> int:
    _allow_local_egress()
    if len(sys.argv) != 5:
        raise SystemExit("usage: browser_task_child.py <base_url> <mode> <task_id> <idempotency_key>")
    base_url, mode, task_id, key = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    if mode not in MODE_CHOICES:
        raise SystemExit(f"unknown mode: {mode!r} (choose from {sorted(MODE_CHOICES)})")
    payload = asyncio.run(_run(mode, base_url, task_id, key))
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
