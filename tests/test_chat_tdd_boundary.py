from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from httpx import Response
from pydantic import BaseModel, ConfigDict

from antigravity_k.api.contracts import ConversationSnapshot
from antigravity_k.engine.access_mode import AccessMode
from tests.chat_boundary_helpers import Boundary, ModelDouble
from tests.chat_boundary_helpers import boundary as boundary

if TYPE_CHECKING:
    from antigravity_k.engine.tdd_engine import TDDReport


class _Message(BaseModel):
    model_config = ConfigDict(frozen=True)
    role: str = "user"
    content: str


class _Request(BaseModel):
    model_config = ConfigDict(frozen=True)
    model: str = "test-model"
    project_id: str
    messages: tuple[_Message, ...]
    stream: bool = True
    agent_mode: bool = True
    web_search: bool = False
    tdd_mode: bool = False
    code_mode: bool | int | str | None = None
    conversation_id: str | None = None
    conversation_revision: int | None = None
    new_turn: _Message | None = None


class _Delta(BaseModel):
    model_config = ConfigDict(frozen=True)
    content: str = ""


class _Choice(BaseModel):
    model_config = ConfigDict(frozen=True)
    delta: _Delta


class _Conflict(BaseModel):
    model_config = ConfigDict(frozen=True)
    expected_revision: int
    current_revision: int


class _Frame(BaseModel):
    model_config = ConfigDict(frozen=True)
    agk_final_content: str | None = None
    agk_conversation: ConversationSnapshot | None = None
    agk_conversation_conflict: _Conflict | None = None
    choices: tuple[_Choice, ...] = ()


@dataclass(frozen=True, slots=True)
class _TddRunner:
    report: TDDReport
    calls: list[tuple[str, str | None]]

    async def run_tdd_loop(self, prompt: str, target_file_path: str | None = None) -> TDDReport:
        self.calls.append((prompt, target_file_path))
        return self.report


@dataclass(frozen=True, slots=True)
class _TddBoundary:
    http: Boundary
    runner: _TddRunner
    constructions: list[str]


@pytest.fixture
def tdd_boundary(boundary: Boundary, monkeypatch: pytest.MonkeyPatch) -> _TddBoundary:
    from antigravity_k.engine import access_mode, tdd_engine

    report = tdd_engine.TDDReport(
        prompt="controlled-task",
        status=tdd_engine.TDDStatus.PASSED,
        final_code="value = 1",
        explanation="validated-result",
        winner_source="controlled-model",
        total_iterations=1,
        duration_ms=10,
    )
    runner = _TddRunner(report, [])
    constructions: list[str] = []

    def make_runner(
        *, model_manager: ModelDouble, coding_model: str, max_iterations: int = 3, workspace_dir: str = ""
    ) -> _TddRunner:
        constructions.append(coding_model)
        return runner

    monkeypatch.setattr(tdd_engine, "OmniTDDEngine", make_runner)
    monkeypatch.setattr(access_mode, "get_access_mode", lambda: AccessMode.FULL_ACCESS)
    return _TddBoundary(boundary, runner, constructions)


def _post(boundary: Boundary, request: _Request) -> Response:
    return boundary.client.post("/v1/chat/completions", json=request.model_dump(mode="json", exclude_none=True))


def _frames(response: Response) -> list[_Frame]:
    return [
        _Frame.model_validate_json(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ") and line != "data: [DONE]"
    ]


def _request(boundary: Boundary, explicit: bool, code_mode: bool | int | str | None) -> _Request:
    message = _Message(
        content="Explain a concept" if explicit else "missing_module.py를 읽어줘. 수정과 파일 생성은 하지마."
    )
    return _Request(project_id=boundary.project_id, messages=(message,), tdd_mode=explicit, code_mode=code_mode)


@pytest.mark.parametrize("explicit", [False, True], ids=["automatic", "explicit"])
@pytest.mark.parametrize("code_mode", [False, 0, "false"])
def test_disabled_code_prevents_tdd_and_uses_policy_runtime(
    tdd_boundary: _TddBoundary, explicit: bool, code_mode: bool | int | str
) -> None:
    response = _post(tdd_boundary.http, _request(tdd_boundary.http, explicit, code_mode))

    assert response.status_code == 200
    assert tdd_boundary.constructions == []
    assert tdd_boundary.runner.calls == []
    assert len(tdd_boundary.http.runtime.calls) == 1
    assert tdd_boundary.http.runtime.code_denials[0] is not None
    assert tdd_boundary.http.runtime.side_effects_allowed == [True]
    assert tdd_boundary.http.runtime.search_denials[0] is not None


@pytest.mark.parametrize("explicit", [False, True], ids=["automatic", "explicit"])
@pytest.mark.parametrize("code_mode", [None, True], ids=["omitted", "enabled"])
def test_read_only_prevents_tdd_and_uses_policy_runtime(
    tdd_boundary: _TddBoundary, monkeypatch: pytest.MonkeyPatch, explicit: bool, code_mode: bool | None
) -> None:
    from antigravity_k.engine import access_mode

    monkeypatch.setattr(access_mode, "get_access_mode", lambda: AccessMode.READ_ONLY)
    response = _post(tdd_boundary.http, _request(tdd_boundary.http, explicit, code_mode))

    assert response.status_code == 200
    assert tdd_boundary.constructions == []
    assert tdd_boundary.runner.calls == []
    assert len(tdd_boundary.http.runtime.calls) == 1
    assert tdd_boundary.http.runtime.side_effects_allowed == [False]
    assert tdd_boundary.http.runtime.search_denials[0] is not None


@pytest.mark.parametrize("code_mode", [None, True], ids=["omitted", "enabled"])
def test_legacy_full_access_explicit_tdd_keeps_engine_and_delta_contract(
    tdd_boundary: _TddBoundary, code_mode: bool | None
) -> None:
    response = _post(tdd_boundary.http, _request(tdd_boundary.http, True, code_mode))

    assert response.status_code == 200
    assert tdd_boundary.constructions == ["test-model"]
    assert len(tdd_boundary.runner.calls) == 1
    assert tdd_boundary.http.runtime.calls == []
    frames = _frames(response)
    assert any(frame.choices for frame in frames)
    assert all(frame.agk_final_content is None and frame.agk_conversation is None for frame in frames)
    assert response.text.endswith("data: [DONE]\n\n")


@pytest.mark.parametrize("passed", [False, True], ids=["failed-report", "passed-report"])
def test_revision_tdd_persists_terminal_answer_and_accepts_next_turn(tdd_boundary: _TddBoundary, passed: bool) -> None:
    from antigravity_k.engine.tdd_engine import TDDStatus

    boundary = tdd_boundary.http
    tdd_boundary.runner.report.status = TDDStatus.PASSED if passed else TDDStatus.FAILED
    tdd_boundary.runner.report.error = "controlled-failure" if not passed else ""
    message = _Message(content="Explain a concept")
    request = _Request(
        project_id=boundary.project_id,
        messages=(message,),
        new_turn=message,
        tdd_mode=True,
        code_mode=True,
        conversation_id="conv_tdd",
        conversation_revision=0,
    )
    response = _post(boundary, request)

    assert response.status_code == 200
    assert len(tdd_boundary.runner.calls) == 1
    stored = boundary.store.get(project_id=boundary.project_id, conversation_id="conv_tdd")
    assert stored is not None
    assert stored.revision == 2
    assert [message.role for message in stored.messages] == ["user", "assistant"]
    frames = _frames(response)
    snapshots = [frame.agk_conversation for frame in frames if frame.agk_conversation is not None]
    assert [snapshot.revision for snapshot in snapshots] == [1, 2]
    assert frames[0].agk_conversation is snapshots[0]
    assert snapshots[-1].revision == stored.revision
    finals = [frame.agk_final_content for frame in frames if frame.agk_final_content is not None]
    deltas = [choice.delta.content for frame in frames for choice in frame.choices if choice.delta.content]
    assert stored.messages[-1].content == (finals[-1] if finals else deltas[-1]).strip()
    assert response.text.endswith("data: [DONE]\n\n")

    next_message = _Message(content="Explain another concept")
    follow_up = _post(
        boundary,
        _Request(
            project_id=boundary.project_id,
            messages=(next_message,),
            new_turn=next_message,
            code_mode=False,
            conversation_id="conv_tdd",
            conversation_revision=snapshots[-1].revision,
        ),
    )

    assert follow_up.status_code == 200
    assert len(tdd_boundary.runner.calls) == 1
    assert [message["content"] for message in boundary.runtime.calls[-1]] == [
        message.content,
        stored.messages[-1].content,
        next_message.content,
    ]
    updated = boundary.store.get(project_id=boundary.project_id, conversation_id="conv_tdd")
    assert updated is not None
    assert updated.revision == 4


def test_revision_tdd_reports_cas_conflict_without_overwriting_other_answer(
    tdd_boundary: _TddBoundary, monkeypatch: pytest.MonkeyPatch
) -> None:
    boundary = tdd_boundary.http

    async def concurrent_answer(self: _TddRunner, prompt: str, target_file_path: str | None = None) -> TDDReport:
        self.calls.append((prompt, target_file_path))
        boundary.store.append(
            project_id=boundary.project_id,
            conversation_id="conv_tdd_race",
            expected_revision=1,
            role="assistant",
            content="concurrent-result",
        )
        return self.report

    monkeypatch.setattr(_TddRunner, "run_tdd_loop", concurrent_answer)
    message = _Message(content="Explain a concept")
    response = _post(
        boundary,
        _Request(
            project_id=boundary.project_id,
            messages=(message,),
            new_turn=message,
            tdd_mode=True,
            code_mode=True,
            conversation_id="conv_tdd_race",
            conversation_revision=0,
        ),
    )

    assert response.status_code == 200
    frames = _frames(response)
    conflicts = [frame.agk_conversation_conflict for frame in frames if frame.agk_conversation_conflict is not None]
    assert len(conflicts) == 1
    assert (conflicts[0].expected_revision, conflicts[0].current_revision) == (1, 2)
    snapshots = [frame.agk_conversation for frame in frames if frame.agk_conversation is not None]
    assert [snapshot.revision for snapshot in snapshots] == [1]
    assert frames[0].agk_conversation is snapshots[0]
    stored = boundary.store.get(project_id=boundary.project_id, conversation_id="conv_tdd_race")
    assert stored is not None
    assert stored.revision == 2
    assert stored.messages[-1].content == "concurrent-result"
    assert response.text.endswith("data: [DONE]\n\n")
