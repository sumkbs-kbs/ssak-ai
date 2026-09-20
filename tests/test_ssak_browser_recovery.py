"""task 20 — 작업 checkpoint·취소·안전 재개·중복 방지 계약 시험.

이 파일이 재는 것
----------------
**"보냈는데 결과를 모르는 행동" 을 다시 누르지 않는다.**

작업 저널(`tools/browser_task_journal.py`)은 의도 → 발송 → 관측 결과를 디스크에 남긴다. 앱이
재시작하거나 프로세스가 SIGKILL 을 맞으면 그 창(window)이 그대로 파일에 남고, 재개는 그 사실을
읽고 **멈춘다**(되돌릴 수 없는 효과) 또는 이어받는다(읽기).

무엇으로 재는가
--------------
- ① **저널만**: 순서 계약 · 비밀 금지 · 중복 방지 · 재개 판정 · 취소 가시성 · 잠금 정직 실패
- ② **루프 배선**: 취소(협력/시간초과) · 결과를 모르는 발송 · 저널이 없으면 task 19 와 동일
- ③ **실 Chromium + 실제 mutation counter**: 자식 프로세스를 진짜로 죽여(제출 직전/직후) 서버의
  변경 횟수로 중복 실행이 없음을 확인하고, 같은 idempotency key 의 두 번째 요청이 실행되지 않음을
  확인한다. 자식은 `tests/fixtures/browser_task_child.py` 다.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import threading
from collections.abc import Callable, Iterator, Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Final

import pytest

from antigravity_k.agents.browser_task_loop import (
    ACTION_FAILED,
    BUDGET_EXHAUSTED,
    CANCELLED,
    FALSE_DONE,
    GOAL_VERIFIED,
    UNKNOWN_OUTCOME,
    BrowserTaskLoop,
    PlannedAction,
    Postcondition,
    TaskBlocked,
    TaskBudget,
    TaskGoal,
    TaskMeasurement,
    TaskStatus,
)
from antigravity_k.tools.browser_approval import REQUIRES_APPROVAL, Effect
from antigravity_k.tools.browser_observation import ActionResult, ElementRef, Observation
from antigravity_k.tools.browser_task_journal import (
    ALREADY_FINISHED,
    CANCEL_REQUESTED,
    CONSEQUENTIAL_EFFECTS,
    DUPLICATE_REQUEST,
    JOURNAL_UNAVAILABLE,
    ORDER_VIOLATION,
    SAFE_RETRY,
    SECRET_IN_RECORD,
    STALE_APPROVAL,
    UNKNOWN_TASK,
    BrowserTaskJournal,
    JournalError,
)

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
CHILD: Final = REPO_ROOT / "tests" / "fixtures" / "browser_task_child.py"


# ── ① 저널만 ────────────────────────────────────────────────────────────────
def test_records_are_append_only_jsonl_with_monotonic_sequences(tmp_path: Path) -> None:
    """한 줄에 하나씩, seq 는 이어지고, 파일의 줄 수가 곧 기록 수다."""
    journal = BrowserTaskJournal(tmp_path / "tasks.jsonl")
    journal.open_task("t1", goal="무엇을 확인한다")
    intent = journal.record_intent("t1", action="click", target="조회", effect="read")
    journal.record_dispatch("t1", intent.seq)
    journal.record_outcome("t1", intent.seq, performed=True)

    lines = journal.path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 4
    seqs = [json.loads(line)["seq"] for line in lines]
    assert seqs == [1, 2, 3, 4]
    assert [json.loads(line)["kind"] for line in lines] == [
        "task_opened",
        "intent",
        "dispatched",
        "observed_outcome",
    ]
    assert all(json.loads(line)["schema"] == "ssak.browser.tasks/1.0" for line in lines)


def test_a_corrupt_or_partial_line_does_not_hide_the_rest(tmp_path: Path) -> None:
    """크래시 중에 잘린 줄(부분 JSON)은 **건너뛰고** 나머지를 읽는다 — 재개가 눈이 멀면 안 된다."""
    journal = BrowserTaskJournal(tmp_path / "tasks.jsonl")
    journal.open_task("t1", goal="g")
    good = journal.path.read_text(encoding="utf-8")
    with journal.path.open("ab") as handle:
        handle.write(b'{"schema": "ssak.browser.tasks/1.0", "seq": 2, "at": 1.0, "ki')  # 잘린 줄
    journal.path.write_text(good + '{"schema": "ssak.browser.tasks/1.0", "seq": 9, "at": 1.0, "kind": "intent"\n')
    records = journal.records()
    assert [record.kind for record in records] == ["task_opened"]
    assert journal.records(task_id="t1")


def test_a_missing_journal_is_not_an_error_but_an_empty_past(tmp_path: Path) -> None:
    """파일이 없으면 "아는 것이 없다" — 예외가 아니라 빈 목록이다."""
    journal = BrowserTaskJournal(tmp_path / "nope.jsonl")
    assert journal.records() == ()
    assert not journal.exists()


def test_a_dispatch_needs_an_intent_and_an_outcome_needs_a_dispatch(tmp_path: Path) -> None:
    """순서 계약: 의도 없는 발송은 없고, 발송 없는 결과는 알 수 없다."""
    journal = BrowserTaskJournal(tmp_path / "tasks.jsonl")
    journal.open_task("t1", goal="g")
    with pytest.raises(JournalError) as dispatch_error:
        journal.record_dispatch("t1", 99)
    assert dispatch_error.value.code == ORDER_VIOLATION

    intent = journal.record_intent("t1", action="scroll", effect="read")
    with pytest.raises(JournalError) as outcome_error:
        journal.record_outcome("t1", intent.seq, performed=True)
    assert outcome_error.value.code == ORDER_VIOLATION
    # 거절된 기록은 **한 줄도** 남지 않는다(부분 상태를 만들지 않는다).
    assert [record.kind for record in journal.records()] == ["task_opened", "intent"]


@pytest.mark.parametrize("field", ["password", "token", "cookie", "authorization", "value", "otp"])
def test_secrets_cannot_be_written_to_the_journal(tmp_path: Path, field: str) -> None:
    """비밀은 값이 아니라 키로 막는다 — 실수로 넘겨도 파일에 들어가지 않는다."""
    journal = BrowserTaskJournal(tmp_path / "tasks.jsonl")
    with pytest.raises(JournalError) as excinfo:
        journal.open_task("t1", goal="로그인한다", metadata={field: "s3cr3t-value"})
    assert excinfo.value.code == SECRET_IN_RECORD
    with pytest.raises(JournalError) as nested:
        journal.record_intent("t2", action="fill", metadata={"nested": {"password": "s3cr3t-value"}})
    assert nested.value.code == SECRET_IN_RECORD
    text = journal.path.read_text(encoding="utf-8") if journal.path.exists() else ""
    assert "s3cr3t-value" not in text, "비밀이 파일에 남았다"
    assert not journal.path.exists() or "password" not in text


def test_a_secret_handle_is_the_one_thing_that_may_be_recorded(tmp_path: Path) -> None:
    """값 대신 handle 은 남을 수 있다(재개가 **무엇을** 다시 물어야 하는지 알기 위해)."""
    journal = BrowserTaskJournal(tmp_path / "tasks.jsonl")
    journal.open_task("t1", goal="로그인한다")
    intent = journal.record_intent("t1", action="fill", effect="auth", approval="ssak1.handle.abc")
    records = journal.records(task_id="t1")
    assert records[-1].data["approval"] == "ssak1.handle.abc"
    assert intent.consequential is True


def test_consequential_effects_match_the_approval_contract() -> None:
    """저널의 '되돌릴 수 없는 효과' 는 task 18 의 승인 대상과 **같은 집합**이어야 한다.

    두 곳이 갈라지면 \"승인은 필요 없는데 재개는 위험하다고 보는\"(또는 그 반대) 어긋남이 생긴다.
    """
    assert set(CONSEQUENTIAL_EFFECTS) == {item.value for item in REQUIRES_APPROVAL}
    assert Effect.TRANSMIT.value in CONSEQUENTIAL_EFFECTS
    assert Effect.READ.value not in CONSEQUENTIAL_EFFECTS


def test_the_same_idempotency_key_is_not_run_twice(tmp_path: Path) -> None:
    """중복 방지: 같은 키의 두 번째 요청은 **실행되지 않고** 기록된 결말을 돌려준다."""
    journal = BrowserTaskJournal(tmp_path / "tasks.jsonl")
    first = journal.open_task("t1", goal="송금한다", idempotency_key="req-1")
    assert first.duplicate is False
    journal.finish_task("t1", status="succeeded", code=GOAL_VERIFIED, actions=1)

    second = journal.open_task("t2", goal="송금한다", idempotency_key="req-1")
    assert second.duplicate is True
    assert second.task_id == "t1", "같은 키는 같은 작업으로 돌아간다"
    assert second.finished is not None and second.finished["code"] == GOAL_VERIFIED
    assert second.phase == "finished"
    assert journal.task_ids() == ("t1",)

    other = journal.open_task("t3", goal="송금한다", idempotency_key="req-2")
    assert other.duplicate is False


def test_resume_of_a_finished_task_returns_the_recorded_end(tmp_path: Path) -> None:
    journal = BrowserTaskJournal(tmp_path / "tasks.jsonl")
    journal.open_task("t1", goal="g")
    journal.finish_task("t1", status="partial", code=BUDGET_EXHAUSTED, reason="예산", actions=3)
    plan = journal.resume_plan("t1")
    assert plan.phase == "finished"
    assert plan.code == ALREADY_FINISHED
    assert plan.replay_allowed is False
    assert plan.finished is not None and plan.finished["status"] == "partial"


def test_an_unknown_task_is_named_not_guessed(tmp_path: Path) -> None:
    journal = BrowserTaskJournal(tmp_path / "tasks.jsonl")
    with pytest.raises(JournalError) as excinfo:
        journal.resume_plan("ghost")
    assert excinfo.value.code == UNKNOWN_TASK


def test_a_read_only_open_action_may_be_retried_after_a_restart(tmp_path: Path) -> None:
    """읽기 행동은 사이트 상태를 바꾸지 않는다 — 새 관찰 뒤 이어받아도 안전하다."""
    journal = BrowserTaskJournal(tmp_path / "tasks.jsonl")
    journal.open_task("t1", goal="g")
    intent = journal.record_intent("t1", action="scroll", effect="read")
    journal.record_dispatch("t1", intent.seq)
    plan = journal.resume_plan("t1")
    assert plan.phase == "read_only_open"
    assert plan.code == SAFE_RETRY
    assert plan.replay_allowed is True
    assert plan.must_reobserve is True, "재개는 새 관찰로 시작한다(옛 ref 는 죽었다)"
    assert plan.unknown_outcomes == ()


def test_a_dispatched_consequential_action_without_an_outcome_refuses_replay(tmp_path: Path) -> None:
    """핵심 계약: 보냈는데 결과를 모르는 **되돌릴 수 없는** 행동은 자동 재실행 금지."""
    journal = BrowserTaskJournal(tmp_path / "tasks.jsonl")
    journal.open_task("t1", goal="송금한다")
    intent = journal.record_intent("t1", action="click", target="송금", effect="financial")
    journal.record_dispatch("t1", intent.seq)
    plan = journal.resume_plan("t1")
    assert plan.phase == "unknown_outcome"
    assert plan.code == UNKNOWN_OUTCOME
    assert plan.replay_allowed is False
    assert plan.must_reobserve is True
    assert [item.action for item in plan.unknown_outcomes] == ["click"]
    assert "사람이 확인해야" in plan.reason


def test_an_effect_nobody_classified_is_treated_as_unrecoverable(tmp_path: Path) -> None:
    """효과를 모르면 **되돌릴 수 없는 쪽**으로 기운다 — 조용히 다시 누르지 않는다."""
    journal = BrowserTaskJournal(tmp_path / "tasks.jsonl")
    journal.open_task("t1", goal="g")
    intent = journal.record_intent("t1", action="click", target="무엇인지 모름", effect="unknown")
    journal.record_dispatch("t1", intent.seq)
    assert intent.consequential is True
    assert journal.resume_plan("t1").replay_allowed is False


def test_a_cancel_request_blocks_resume_and_is_visible_immediately(tmp_path: Path) -> None:
    """취소는 **다른 읽기**에 곧바로 보인다(화면이 같은 파일을 읽는다)."""
    writer = BrowserTaskJournal(tmp_path / "tasks.jsonl")
    writer.open_task("t1", goal="g")
    request = writer.request_cancel("t1", reason="사용자가 멈췄다")
    # 두 번째 호출은 첫 요청 시각을 그대로 돌려준다(취소는 한 번 일어난 일이다).
    assert writer.request_cancel("t1").requested_at == request.requested_at

    reader = BrowserTaskJournal(tmp_path / "tasks.jsonl")
    seen = reader.cancel_request("t1")
    assert seen is not None and seen.requested_at == request.requested_at
    assert seen.reason == "사용자가 멈췄다"
    plan = reader.resume_plan("t1")
    assert plan.phase == "cancelled"
    assert plan.code == CANCEL_REQUESTED
    assert plan.replay_allowed is False
    assert plan.resumable is False


def test_a_stale_approval_is_named_on_resume(tmp_path: Path) -> None:
    """재시작을 넘긴 승인은 살아 있지 않다 — 재개가 **다시 물어야** 한다."""
    journal = BrowserTaskJournal(tmp_path / "tasks.jsonl")
    journal.open_task("t1", goal="g")
    journal.record_intent("t1", action="click", target="제출", effect="transmit", approval="ssak1.bind.1")
    plan = journal.resume_plan("t1")
    assert plan.stale_approvals == ("ssak1.bind.1",)
    live = journal.resume_plan("t1", approval_is_live=lambda handle: handle == "ssak1.bind.1")
    assert live.stale_approvals == ()


def test_a_locked_journal_refuses_to_write_instead_of_guessing(tmp_path: Path) -> None:
    """중복 방지는 퇴화하면 거짓말이 된다 — 잠금을 못 잡으면 **기록을 거절**한다."""
    import fcntl

    journal = BrowserTaskJournal(tmp_path / "tasks.jsonl", lock_timeout=0.05)
    journal.open_task("t1", goal="g")
    handle = os.open(journal.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(JournalError) as excinfo:
            journal.open_task("t2", goal="g")
        assert excinfo.value.code == JOURNAL_UNAVAILABLE
    finally:
        os.close(handle)
    # 잠금이 풀리면 다시 쓸 수 있다(영구 차단이 아니다).
    assert journal.open_task("t2", goal="g").duplicate is False


# ── ② 루프 배선 ─────────────────────────────────────────────────────────────
def _observation() -> Observation:
    return Observation(
        session_tag="tag001",
        snapshot_id="snap1",
        generation=1,
        page_key="main",
        url="https://site.example/",
        title="t",
        captured_at="2026-09-20T00:00:00Z",
        refs=(ElementRef(ref="tag001-snap1-main-e0", role="button", name="송금", tag="button", frame="main"),),
        accessibility='button "송금"',
    )


def _goal() -> TaskGoal:
    return TaskGoal(goal="송금했다고 확인한다", postconditions=(Postcondition("flag_equals", "1", key="sent"),))


class _Host:
    """행동 하나를 실행하는 결정적 호스트. `effect` 로 위험도가 정해진다."""

    def __init__(
        self,
        *,
        effect: str = "read",
        outcome: str = "ok",
        sleep: float = 0.0,
        on_act: "Callable[[], None] | None" = None,
    ) -> None:
        self.effect = effect
        self.outcome = outcome
        self.sleep = sleep
        self.on_act = on_act
        self.acts: list[str] = []
        self.measures = 0

    def effect_of(self, action: PlannedAction) -> str:
        return self.effect

    async def observe(self) -> Observation:
        return _observation()

    async def act(self, action: PlannedAction) -> ActionResult:
        self.acts.append(action.action)
        if self.on_act is not None:
            self.on_act()  # 행동이 **진행 중**일 때 일어나는 일을 결정적으로 재현한다
        if self.sleep:
            await asyncio.sleep(self.sleep)
        if self.outcome == "explode":
            raise RuntimeError("browser died mid-action")
        if self.outcome == "blocked":
            raise TaskBlocked("approval_required(request=breq_1, effect=transmit)", kind="approval")
        if action.action == "done":
            return ActionResult(action=action.action, performed=False, goal_verified=False, detail="")
        self._sent = True
        return ActionResult(
            action=action.action,
            performed=True,
            goal_verified=True,
            detail="",
            ref=action.ref,
            snapshot_id="snap1",
            generation=1,
            url_before="https://site.example/",
            url_after="https://site.example/",
        )

    async def measure(self) -> TaskMeasurement:
        self.measures += 1
        return TaskMeasurement(
            url="https://site.example/",
            title="t",
            text="body",
            flags={"sent": "1"} if getattr(self, "_sent", False) else {},
            ref_names=frozenset({"송금"}),
            generation=1,
        )


class _BlindHost(_Host):
    """효과를 **분류하지 않는** 호스트 — 계약은 "모르면 되돌릴 수 없는 쪽" 이다.

    효과를 말하지 않는 호스트(오래된 통합·제3자 구현)가 "읽기" 로 조용히 통과하면, 보낸 뒤 죽었을 때
    재개가 같은 행동을 다시 누른다. 루프는 `getattr` 로만 분류기를 찾으므로, 클래스 속성을 없애면
    "분류하지 않는 호스트" 가 된다.
    """

    effect_of = None  # type: ignore[assignment]


class _Planner:
    """첫 계획으로 클릭 한 번, 그 다음 `done`."""

    def __init__(self, action: str = "click") -> None:
        self.action = action
        self.calls = 0

    async def plan(
        self, *, goal: TaskGoal, observation: Observation, history: object, remaining_actions: int
    ) -> PlannedAction:
        self.calls += 1
        if self.calls > 1:
            return PlannedAction(action="done", reason="끝났다")
        return PlannedAction(action=self.action, ref="tag001-snap1-main-e0", target_name="송금", reason="누른다")


async def test_a_normal_run_leaves_a_complete_journal(tmp_path: Path) -> None:
    """정상 실행: 열림 → 의도 → 발송 → 결과 → 결말이 모두 남는다."""
    journal = BrowserTaskJournal(tmp_path / "tasks.jsonl")
    journal.open_task("t1", goal="송금했다고 확인한다")
    host = _Host(effect="read")
    outcome = await BrowserTaskLoop(_Planner(), journal=journal, task_id="t1", budget=TaskBudget(action_budget=3)).run(
        _goal(), host
    )
    assert outcome.status is TaskStatus.SUCCEEDED and outcome.code == GOAL_VERIFIED
    kinds = [record.kind for record in journal.records(task_id="t1")]
    assert kinds == ["task_opened", "intent", "dispatched", "observed_outcome", "task_finished"]
    assert journal.resume_plan("t1").phase == "finished"


async def test_an_action_that_explodes_leaves_the_outcome_unknown(tmp_path: Path) -> None:
    """보냈는데 결과를 모른다 — 되돌릴 수 없는 효과면 `UNKNOWN_OUTCOME` 이고 결말을 적지 않는다."""
    journal = BrowserTaskJournal(tmp_path / "tasks.jsonl")
    journal.open_task("t1", goal="송금했다고 확인한다")
    host = _Host(effect="financial", outcome="explode")
    outcome = await BrowserTaskLoop(_Planner(), journal=journal, task_id="t1", budget=TaskBudget(action_budget=3)).run(
        _goal(), host
    )
    assert outcome.status is TaskStatus.UNKNOWN_OUTCOME
    assert outcome.code == UNKNOWN_OUTCOME
    assert host.acts == ["click"], "다시 누르지 않는다"
    kinds = [record.kind for record in journal.records(task_id="t1")]
    assert "observed_outcome" not in kinds, "모르는 결과를 적으면 재개가 그 거짓을 믿는다"
    assert "task_finished" not in kinds, "미확정 작업을 끝난 것으로 적지 않는다"
    plan = journal.resume_plan("t1")
    assert plan.phase == "unknown_outcome" and plan.replay_allowed is False


async def test_a_host_without_an_effect_classifier_is_treated_as_unrecoverable(tmp_path: Path) -> None:
    """효과를 말하지 않는 호스트: 클릭은 `unknown`(되돌릴 수 없는 쪽), 스크롤만 읽기로 단정한다."""
    journal = BrowserTaskJournal(tmp_path / "tasks.jsonl")
    journal.open_task("t1", goal="송금했다고 확인한다")
    outcome = await BrowserTaskLoop(_Planner(), journal=journal, task_id="t1", budget=TaskBudget(action_budget=3)).run(
        _goal(), _BlindHost()
    )
    assert outcome.code == GOAL_VERIFIED, "판정 자체는 정상 실행이어야 한다"
    effect = next(record.data["effect"] for record in journal.records(task_id="t1") if record.kind == "intent")
    assert effect == "unknown", f"분류하지 않는 호스트가 읽기로 통과했다: {effect}"
    assert effect in CONSEQUENTIAL_EFFECTS

    journal.open_task("t2", goal="송금했다고 확인한다")
    outcome = await BrowserTaskLoop(
        _Planner(action="scroll"), journal=journal, task_id="t2", budget=TaskBudget(action_budget=3)
    ).run(_goal(), _BlindHost())
    scroll_effect = next(record.data["effect"] for record in journal.records(task_id="t2") if record.kind == "intent")
    assert scroll_effect == "read", "읽기만은 분류 없이도 읽기다"

    # 분류 없는 호스트가 보낸 뒤 죽으면 — 다시 누르면 안 된다.
    journal.open_task("t3", goal="송금했다고 확인한다")
    exploded = await BrowserTaskLoop(_Planner(), journal=journal, task_id="t3", budget=TaskBudget(action_budget=3)).run(
        _goal(), _BlindHost(outcome="explode")
    )
    assert exploded.status is TaskStatus.UNKNOWN_OUTCOME
    assert journal.resume_plan("t3").replay_allowed is False


async def test_the_same_explosion_on_a_read_action_is_a_safe_retry(tmp_path: Path) -> None:
    """읽기 행동이 무너지면 자동 재실행을 막지 않는다 — 사이트 상태는 그대로다."""
    journal = BrowserTaskJournal(tmp_path / "tasks.jsonl")
    journal.open_task("t1", goal="송금했다고 확인한다")
    outcome = await BrowserTaskLoop(
        _Planner(action="scroll"), journal=journal, task_id="t1", budget=TaskBudget(action_budget=3)
    ).run(_goal(), _Host(effect="read", outcome="explode"))
    assert outcome.code == ACTION_FAILED, "읽기 실패를 '운명 미확정' 으로 부풀리지 않는다"
    assert outcome.status is TaskStatus.FAILED
    # 결과 기록이 없는 의도는 남지만, 프로세스가 살아 결말을 적었으므로 재개는 새 판단을 맡긴다.
    plan = journal.resume_plan("t1")
    assert plan.phase == "finished"
    assert [item.action for item in plan.open_intents] == ["scroll"]


async def test_a_contract_rejection_closes_its_intent(tmp_path: Path) -> None:
    """계약이 거절한 행동은 **결과를 적는다**(보내지 않았다) — 재개가 미확정으로 오해하지 않게."""
    journal = BrowserTaskJournal(tmp_path / "tasks.jsonl")
    journal.open_task("t1", goal="송금했다고 확인한다")
    outcome = await BrowserTaskLoop(_Planner(), journal=journal, task_id="t1", budget=TaskBudget(action_budget=2)).run(
        _goal(), _Host(effect="financial", outcome="blocked")
    )
    assert outcome.status is TaskStatus.BLOCKED and outcome.blocked_kind == "approval"
    kinds = [record.kind for record in journal.records(task_id="t1")]
    assert kinds.count("observed_outcome") == 1
    assert journal.resume_plan("t1").phase == "finished"


async def test_a_cooperative_cancel_stops_before_the_next_action(tmp_path: Path) -> None:
    """취소를 제때 보면 **다음 행동 전에** 멈춘다(실행 0회) — 협력 취소로 보고한다."""
    journal = BrowserTaskJournal(tmp_path / "tasks.jsonl")
    journal.open_task("t1", goal="송금했다고 확인한다")
    journal.request_cancel("t1")
    host = _Host(effect="read")
    outcome = await BrowserTaskLoop(_Planner(), journal=journal, task_id="t1", budget=TaskBudget(action_budget=3)).run(
        _goal(), host
    )
    assert outcome.status is TaskStatus.CANCELLED and outcome.code == CANCELLED
    assert outcome.cancel_mode == "cooperative"
    assert outcome.forced_shutdown is False
    assert host.acts == [], "취소 뒤에 새 행동이 실행됐다"
    observed = [record for record in journal.records(task_id="t1") if record.kind == "cancel_observed"]
    assert observed and observed[0].data["mode"] == "cooperative"


async def test_a_cancel_that_arrives_during_an_action_is_a_timeout_shutdown(tmp_path: Path) -> None:
    """진행 중에 들어온 취소는 되돌릴 수 없다 — 기한을 넘겼으면 **명시 timeout** 으로 보고한다.

    진행 중이던 행동은 끝나고 그 결과는 기록되지만, 그 뒤 검증은 하지 않는다. 새 행동은 0회다.
    """
    journal = BrowserTaskJournal(tmp_path / "tasks.jsonl")
    journal.open_task("t1", goal="송금했다고 확인한다")

    def _request_cancel_while_the_action_runs() -> None:
        # 행동이 시작된 뒤에 요청한다(타이밍 경쟁이 아니라 사실로 정해지는 재현).
        BrowserTaskJournal(journal.path).request_cancel("t1")

    host = _Host(effect="read", sleep=0.3, on_act=_request_cancel_while_the_action_runs)
    outcome = await BrowserTaskLoop(
        _Planner(),
        journal=journal,
        task_id="t1",
        budget=TaskBudget(action_budget=3),
        cancel_grace_seconds=0.05,
    ).run(_goal(), host)

    assert outcome.status is TaskStatus.CANCELLED
    assert outcome.cancel_mode == "timeout"
    assert outcome.forced_shutdown is True
    assert host.acts == ["click"], "진행 중이던 행동 1회, 그 뒤로는 0회"
    assert "기한" in outcome.reason
    observed = [record for record in journal.records(task_id="t1") if record.kind == "cancel_observed"]
    assert observed and observed[0].data["mode"] == "timeout"


async def test_the_loop_without_a_journal_behaves_exactly_like_task_19(tmp_path: Path) -> None:
    """저널은 선택이다 — 없으면 메모리만 쓰던 동작 그대로다."""
    host = _Host(effect="read")
    outcome = await BrowserTaskLoop(_Planner(), budget=TaskBudget(action_budget=3)).run(_goal(), host)
    assert outcome.status is TaskStatus.SUCCEEDED
    assert outcome.cancel_mode == "" and outcome.forced_shutdown is False


async def test_the_dispatch_hook_fires_after_the_record_lands(tmp_path: Path) -> None:
    """발송 훅은 **기록이 남은 뒤** 불린다(그 창을 재현할 수 있어야 크래시를 시험할 수 있다)."""
    journal = BrowserTaskJournal(tmp_path / "tasks.jsonl")
    journal.open_task("t1", goal="송금했다고 확인한다")
    seen: list[bool] = []

    def _inspect(intent: object) -> None:
        kinds = [record.kind for record in BrowserTaskJournal(journal.path).records(task_id="t1")]
        seen.append("dispatched" in kinds)

    await BrowserTaskLoop(
        _Planner(),
        journal=journal,
        task_id="t1",
        budget=TaskBudget(action_budget=3),
        on_dispatch=_inspect,
    ).run(_goal(), _Host(effect="read"))
    assert seen == [True]


async def test_a_false_done_is_still_a_false_done_with_a_journal(tmp_path: Path) -> None:
    """저널이 붙어도 판정은 그대로다 — 기록은 결말을 바꾸지 않는다."""
    journal = BrowserTaskJournal(tmp_path / "tasks.jsonl")
    journal.open_task("t1", goal="송금했다고 확인한다")
    goal = TaskGoal(goal="확인한다", postconditions=(Postcondition("flag_equals", "1", key="never"),))
    outcome = await BrowserTaskLoop(
        _Planner(action="scroll"), journal=journal, task_id="t1", budget=TaskBudget(action_budget=2)
    ).run(goal, _Host(effect="read"))
    assert outcome.code == FALSE_DONE
    assert journal.resume_plan("t1").phase == "finished"


# ── ③ 실 Chromium + mutation counter (자식 프로세스를 죽인다) ────────────────
pytest.importorskip("playwright.async_api")


class _SiteHandler(BaseHTTPRequestHandler):
    """로컬 fixture 페이지. `POST /submit` 이 **실제 변경**이고 그 횟수를 센다."""

    counter: dict[str, int] = {"reads": 0, "mutations": 0}

    def log_message(self, *args: object) -> None:  # noqa: D102 - 시험 출력을 조용히
        return

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler 규약
        if self.path.startswith("/count"):
            # 계측 자체를 세면 안 된다 — 읽기 횟수는 **브라우저가 읽은 횟수**다.
            body = json.dumps(type(self).counter).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        type(self).counter["reads"] += 1
        if self.path.startswith("/page2"):
            # 읽기 행동의 도착지 — 여기 가려면 링크를 눌러야 한다(변경은 없다).
            second = (
                "<html><body><h1>이체 내역 페이지</h1><p>이체 내역: 2026-09-20 100,000원</p></body></html>"
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(second)))
            self.end_headers()
            self.wfile.write(second)
            return
        page = (
            "<html><body><h1>송금 페이지</h1>"
            "<a href='/page2'>다음</a>"
            "<form method='POST' action='/submit'>"
            "<input type='text' name='amount' value='100'>"
            "<button id='send' type='submit'>송금</button></form>"
            "<div data-sent='0'></div>"
            "</body></html>"
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page)))
        self.end_headers()
        self.wfile.write(page)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler 규약
        length = int(self.headers.get("Content-Length") or 0)
        _ = self.rfile.read(length)
        type(self).counter["mutations"] += 1
        body = "<html><body><h1>송금 완료</h1><div data-sent='1'></div></body></html>".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def site() -> Iterator[str]:
    """실제 HTTP 서버(로컬). 자식 프로세스가 **진짜로** 요청을 보내고 변경을 남긴다."""
    _SiteHandler.counter = {"reads": 0, "mutations": 0}
    server = ThreadingHTTPServer(("127.0.0.1", 0), _SiteHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _counts(base_url: str) -> Mapping[str, int]:
    import urllib.request

    with urllib.request.urlopen(f"{base_url}/count", timeout=5) as response:  # noqa: S310 - 로컬 시험 서버
        return json.loads(response.read().decode())


def _run_child(tmp_path: Path, base_url: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["AGK_BROWSER_TASK_JOURNAL"] = str(tmp_path / "tasks.jsonl")
    env["AGK_BROWSER_SESSION_STATE"] = str(tmp_path / "sessions.json")
    env["PYTHONPATH"] = str(REPO_ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(  # noqa: S603 - 저장소 안의 자식 스크립트
        [sys.executable, str(CHILD), base_url, *args],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
        check=False,
    )


def test_a_crash_before_the_submit_leaves_an_unknown_outcome(tmp_path: Path, site: str) -> None:
    """제출 **직전**에 죽으면: 사이트는 변하지 않았고, 재개는 자동 재실행을 거부한다.

    효과는 **실제 분류기**가 정한다(task 18) — 이 자식은 진짜 브라우저로 제출 버튼을 관찰하고
    `effect_of` 로 `transmit` 을 얻은 뒤 발송 기록을 남기고 죽는다.
    """
    result = _run_child(tmp_path, site, "crash_before_submit", "task-crash-before", "req-crash-before")
    assert result.returncode == -signal.SIGKILL, f"자식이 SIGKILL 로 죽지 않았다: {result.stderr[-400:]}"
    assert _counts(site)["mutations"] == 0, "제출이 서버에 도달했다(그러면 이 시험은 다른 것을 재고 있다)"

    journal = BrowserTaskJournal(tmp_path / "tasks.jsonl")
    kinds = [record.kind for record in journal.records(task_id="task-crash-before")]
    assert "intent" in kinds and "dispatched" in kinds
    assert "observed_outcome" not in kinds, "결과를 모르는 상태여야 한다"
    intent = next(record for record in journal.records(task_id="task-crash-before") if record.kind == "intent")
    # '송금' 버튼에 대한 **실제 분류기**(task 18)의 판정은 financial 이다 — 서로 다른 두 계약이
    # 같은 요소를 같은 위험도로 읽는지 확인한다(값이 바뀌면 이 시험이 먼저 말한다).
    assert intent.data["effect"] == "financial", f"실제 분류기가 낸 효과가 아니다: {intent.data['effect']}"
    assert intent.data["effect"] in CONSEQUENTIAL_EFFECTS
    plan = journal.resume_plan("task-crash-before")
    assert plan.phase == "unknown_outcome"
    assert plan.code == UNKNOWN_OUTCOME
    assert plan.replay_allowed is False

    # 재개 요청은 **브라우저를 열지 않는다**: 두 번째 자식은 즉시 같은 판정을 돌려준다.
    resumed = _run_child(tmp_path, site, "resume_only", "task-crash-before", "req-crash-before")
    assert resumed.returncode == 0, resumed.stderr[-400:]
    payload = json.loads(resumed.stdout.strip().splitlines()[-1])
    assert payload["phase"] == "unknown_outcome" and payload["code"] == UNKNOWN_OUTCOME, payload
    assert payload["replay_allowed"] is False
    assert _counts(site)["mutations"] == 0, "재개가 사이트를 건드렸다"


def test_a_crash_after_the_submit_is_not_replayed(tmp_path: Path, site: str) -> None:
    """제출 **직후**에 죽으면: 사이트에 한 번 남았고, 재개는 다시 누르지 않는다."""
    result = _run_child(tmp_path, site, "crash_after_submit", "task-crash-after", "req-crash-after")
    assert result.returncode == -signal.SIGKILL, f"자식이 SIGKILL 로 죽지 않았다: {result.stderr[-400:]}"
    assert _counts(site)["mutations"] == 1, "제출이 한 번 일어난 상태여야 한다"

    journal = BrowserTaskJournal(tmp_path / "tasks.jsonl")
    plan = journal.resume_plan("task-crash-after")
    assert plan.code == UNKNOWN_OUTCOME and plan.replay_allowed is False
    resumed = _run_child(tmp_path, site, "resume_only", "task-crash-after", "req-crash-after")
    assert resumed.returncode == 0, resumed.stderr[-400:]
    payload = json.loads(resumed.stdout.strip().splitlines()[-1])
    assert payload["code"] == UNKNOWN_OUTCOME
    assert _counts(site)["mutations"] == 1, "재개가 송금을 두 번 보냈다"


def test_a_duplicate_request_is_not_executed_twice(tmp_path: Path, site: str) -> None:
    """같은 idempotency key 의 두 번째 요청은 **제품 경로(`run_task`)에서** 실행되지 않는다.

    두 번째 자식은 브라우저를 열지도 않는다 — 서버가 받은 요청 수가 늘지 않는 것이 그 증거다
    (읽기 작업이라 '변경' 은 없다; 대신 **읽기 횟수**가 그대로여야 한다).
    """
    first = _run_child(tmp_path, site, "duplicate_read", "task-dupe-1", "req-dupe")
    assert first.returncode == 0, first.stderr[-400:]
    first_payload = json.loads(first.stdout.strip().splitlines()[-1])
    assert first_payload["status"] == "succeeded", first_payload
    reads_after_first = _counts(site)["reads"]
    assert reads_after_first > 0

    second = _run_child(tmp_path, site, "duplicate_read", "task-dupe-2", "req-dupe")
    assert second.returncode == 0, second.stderr[-400:]
    payload = json.loads(second.stdout.strip().splitlines()[-1])
    # 실행하지 않고 **기록된 결말**을 돌려준다(그것이 중복 방지의 모습이다).
    assert payload["code"] == ALREADY_FINISHED, payload
    assert payload["actions"] == first_payload["actions"]
    assert _counts(site)["reads"] == reads_after_first, "두 번째 요청이 브라우저를 열었다"
    journal = BrowserTaskJournal(tmp_path / "tasks.jsonl")
    assert journal.task_ids() == ("task-dupe-1",), "두 번째 요청은 새 작업을 만들지 않는다"


def test_a_duplicate_request_cannot_auto_replay_an_unknown_outcome(tmp_path: Path, site: str) -> None:
    """미확정 제출을 같은 키로 다시 요청하면 **실행하지 않고** 그 사실을 돌려준다.

    이것이 "자동 replay 금지" 의 제품 경로 형태다: 화면·클라이언트가 같은 키로 재시도해도 송금은
    한 번뿐이고, 두 번째 응답은 `UNKNOWN_OUTCOME` 이다.
    """
    first = _run_child(tmp_path, site, "crash_after_submit", "task-unknown", "req-unknown")
    assert first.returncode == -signal.SIGKILL, first.stderr[-400:]
    assert _counts(site)["mutations"] == 1
    reads_after_first = _counts(site)["reads"]

    second = _run_child(tmp_path, site, "duplicate_submit", "task-unknown-retry", "req-unknown")
    assert second.returncode == 0, second.stderr[-400:]
    payload = json.loads(second.stdout.strip().splitlines()[-1])
    assert payload["code"] == UNKNOWN_OUTCOME, payload
    assert payload["status"] == "unknown_outcome", payload
    assert payload["actions"] == 0, "재요청이 행동을 실행했다"
    assert _counts(site)["mutations"] == 1, "재요청이 송금을 두 번 보냈다"
    assert _counts(site)["reads"] == reads_after_first, "재요청이 브라우저를 열었다"


def test_a_read_only_task_survives_a_pause_and_resumes_to_success(tmp_path: Path, site: str) -> None:
    """읽기 작업: 도중에 죽어도(일부 행동은 완료) 재개가 이어받아 성공한다 — 변경은 0회."""
    first = _run_child(tmp_path, site, "pause_read", "task-pause", "req-pause")
    assert first.returncode == -signal.SIGKILL, "읽기 작업이 중단되지 않았다"
    assert _counts(site)["mutations"] == 0

    journal = BrowserTaskJournal(tmp_path / "tasks.jsonl")
    plan = journal.resume_plan("task-pause")
    assert plan.code == SAFE_RETRY and plan.replay_allowed is True and plan.must_reobserve is True
    assert plan.phase in {"idle", "read_only_open"}, plan.phase
    assert plan.unknown_outcomes == ()

    resumed = _run_child(tmp_path, site, "resume_read", "task-pause", "req-pause")
    assert resumed.returncode == 0, resumed.stderr[-400:]
    payload = json.loads(resumed.stdout.strip().splitlines()[-1])
    assert payload["status"] == "succeeded", payload
    assert _counts(site)["mutations"] == 0, "읽기 작업이 사이트를 바꿨다"
    kinds = [record.kind for record in journal.records(task_id="task-pause")]
    assert "resumed" in kinds, "재개 사실이 저널에 남지 않았다"
    assert kinds.count("task_opened") == 1, "재개가 새 작업을 열었다"


def test_the_child_script_is_present_and_rejects_unknown_modes() -> None:
    """자식 스크립트가 사라지면 위 시험들이 **거짓 통과**할 수 있다 — 존재와 인자를 확인한다."""
    assert CHILD.exists(), f"자식 fixture 가 없다: {CHILD}"
    completed = subprocess.run(  # noqa: S603 - 저장소 안의 자식 스크립트
        [sys.executable, str(CHILD), "http://127.0.0.1:1", "nope", "t", "k"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode != 0
    assert "unknown mode" in (completed.stderr + completed.stdout)


def test_the_duplicate_code_and_status_exist_for_callers() -> None:
    """호출자가 분기할 수 있게 코드 이름이 모듈 표면에 있다(문자열 추측 금지)."""
    assert DUPLICATE_REQUEST == "DUPLICATE_REQUEST"
    assert STALE_APPROVAL == "STALE_APPROVAL"
    assert UNKNOWN_OUTCOME == "UNKNOWN_OUTCOME"
    assert TaskStatus.UNKNOWN_OUTCOME.value == "unknown_outcome"


def test_sequence_stays_monotonic_across_two_journal_instances(tmp_path: Path) -> None:
    """프로세스가 둘이어도 seq 는 이어진다(두 번째 인스턴스가 파일에서 이어받는다)."""
    path = tmp_path / "tasks.jsonl"
    first = BrowserTaskJournal(path)
    first.open_task("t1", goal="g")
    second = BrowserTaskJournal(path)
    second.open_task("t2", goal="g")
    assert [record.seq for record in first.records()] == [1, 2]

    for index in range(8):
        BrowserTaskJournal(path).open_task(f"t{index + 10}", goal="g")
    assert [record.seq for record in first.records()] == list(range(1, 11))


def test_concurrent_openers_do_not_lose_a_request(tmp_path: Path) -> None:
    """같은 키를 동시에 열어도 하나만 새 작업이 된다(판정과 쓰기가 한 임계구역에 있다)."""
    path = tmp_path / "tasks.jsonl"
    results: list[bool] = []
    lock = threading.Lock()

    def _open(index: int) -> None:
        journal = BrowserTaskJournal(path, lock_timeout=5.0)
        opened = journal.open_task(f"t-{index}", goal="g", idempotency_key="same-key")
        with lock:
            results.append(opened.duplicate)

    threads = [threading.Thread(target=_open, args=(index,)) for index in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(results) == [False] + [True] * 5, results
    assert len(BrowserTaskJournal(path).task_ids()) == 1


def test_journal_metadata_round_trips_without_inventing_fields(tmp_path: Path) -> None:
    """메타데이터는 그대로 읽히고, 모르는 키가 섞여도 아는 것만 남는다(전방 호환)."""
    journal = BrowserTaskJournal(tmp_path / "tasks.jsonl")
    journal.open_task("t1", goal="g", metadata={"surface": "dashboard", "attempt": 2})
    record = journal.records(task_id="t1")[0]
    assert record.data["metadata"] == {"surface": "dashboard", "attempt": 2}

    with journal.path.open("a", encoding="utf-8") as handle:
        handle.write(
            '{"schema": "ssak.browser.tasks/1.0", "seq": 2, "at": 1.0, "kind": "intent", '
            '"task_id": "t1", "future_field": "무시된다"}\n'
        )
    kinds = [item.kind for item in journal.records(task_id="t1")]
    assert kinds == ["task_opened", "intent"]

    with journal.path.open("a", encoding="utf-8") as handle:
        handle.write('{"schema": "ssak.other/9.9", "seq": 3, "at": 1.0, "kind": "intent", "task_id": "t1"}\n')
    assert len(journal.records(task_id="t1")) == 2, "다른 스키마의 줄은 이 저널의 것이 아니다"


def test_an_effect_sequence_is_readable_as_a_story(tmp_path: Path) -> None:
    """사람이 읽을 수 있어야 한다 — 기록만 보고 무슨 일이 있었는지 재구성된다."""
    journal = BrowserTaskJournal(tmp_path / "tasks.jsonl")
    journal.open_task("t1", goal="송금한다")
    intent = journal.record_intent("t1", action="click", target="송금", effect="financial", ref="r0")
    journal.record_dispatch("t1", intent.seq)
    payload = json.loads(journal.path.read_text(encoding="utf-8").strip().splitlines()[1])
    # data 는 줄에 **펼쳐져** 있다(한 줄 = 한 사건, 중첩이 없다).
    assert payload["effect"] == "financial"
    assert payload["target"] == "송금"
    assert "data" not in payload
    assert payload["task_id"] == "t1"
    assert isinstance(payload["at"], float)


def test_zero_length_journal_file_is_read_as_empty(tmp_path: Path) -> None:
    """0바이트 파일(크래시 직후)도 오류가 아니다."""
    path = tmp_path / "tasks.jsonl"
    path.write_text("", encoding="utf-8")
    journal = BrowserTaskJournal(path)
    assert journal.records() == ()
    assert journal.open_task("t1", goal="g").duplicate is False
    assert len(journal.records()) == 1


def test_order_is_visible_to_a_second_reader(tmp_path: Path) -> None:
    """다른 프로세스(새 인스턴스)가 같은 이야기를 읽는다 — 저널이 공유 상태의 유일한 근거다."""
    path = tmp_path / "tasks.jsonl"
    writer = BrowserTaskJournal(path)
    writer.open_task("t1", goal="g")
    intent = writer.record_intent("t1", action="click", effect="transmit")
    writer.record_dispatch("t1", intent.seq)
    reader = BrowserTaskJournal(path)
    assert [record.kind for record in reader.records(task_id="t1")] == ["task_opened", "intent", "dispatched"]
    assert reader.resume_plan("t1").replay_allowed is False
