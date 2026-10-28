"""r27: one allowed-path rule for project register/activate/chat; launcher keeps explicit project root."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
from fastapi import HTTPException

from antigravity_k.api.contracts.errors import ProjectRootInvalidError
from antigravity_k.engine.orchestrator_analysis_handlers import ceo_gate_decision
from antigravity_k.engine.request_execution_context import validate_project_root_path
from antigravity_k.engine.state_graph import AgentState

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    allowed, outside = tmp_path / "allowed" / "proj", tmp_path / "outside"
    allowed.mkdir(parents=True)
    outside.mkdir()
    monkeypatch.setenv("AGK_ALLOWED_ROOTS", str(allowed))
    return allowed, outside


def test_same_rule_accepts_allowed_and_rejects_outside_and_symlink_out(roots: tuple[Path, Path]) -> None:
    allowed, outside = roots
    assert validate_project_root_path(str(allowed)) == str(allowed.resolve())
    with pytest.raises(ProjectRootInvalidError):
        _ = validate_project_root_path(str(outside))
    link = allowed / "escape"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ProjectRootInvalidError):
        _ = validate_project_root_path(str(link))


def _create(path: Path) -> object:
    from antigravity_k.api.routes import filesystem

    req = filesystem.CreateProjectRequest(name="x", path=str(path))
    return asyncio.run(filesystem.create_project(req, SimpleNamespace(headers={})))  # type: ignore[arg-type]


def test_register_rejects_what_chat_would_reject(roots: tuple[Path, Path]) -> None:
    _allowed, outside = roots
    registry = mock.MagicMock()
    with mock.patch("antigravity_k.engine.project_registry.get_project_registry", return_value=registry):
        for bad in (outside, outside / "new-sub"):
            with pytest.raises(HTTPException) as exc:
                _ = _create(bad)
            assert exc.value.status_code == 403
    registry.add_project.assert_not_called()
    assert not (outside / "new-sub").exists()  # rejected before creating anything


def test_switch_rejects_registered_project_outside_rule(roots: tuple[Path, Path]) -> None:
    from antigravity_k.api.routes import filesystem

    _allowed, outside = roots
    registry = mock.MagicMock()
    registry.get_project.return_value = SimpleNamespace(id="p1", path=str(outside))
    with mock.patch("antigravity_k.engine.project_registry.get_project_registry", return_value=registry):
        req = filesystem.SwitchProjectRequest(project_id="p1")
        with pytest.raises(HTTPException) as exc:
            _ = asyncio.run(filesystem.switch_project(req, SimpleNamespace(headers={})))  # type: ignore[arg-type]
    assert exc.value.status_code == 403
    registry.switch_project.assert_not_called()


def test_launcher_keeps_explicit_project_root_and_rag_off_default() -> None:
    script = (REPO / "scripts" / "build_mac_dmg.sh").read_text()
    assert 'export AGK_PATH_PROJECT_ROOT="${AGK_PATH_PROJECT_ROOT:-$USER_DATA_DIR}"' in script
    assert 'export AGK_PATH_PROJECT_ROOT="$USER_DATA_DIR"' not in script


@pytest.mark.parametrize(
    ("rag", "msg", "expected"),
    [
        ("true", "이 프로젝트 문서에 따르면 정산 규칙은?", AgentState.CONTEXT_ENRICH),
        ("true", "안녕 고마워", AgentState.ROUTE),
        (None, "이 프로젝트 문서에 따르면 정산 규칙은?", AgentState.ROUTE),
        ("false", "project docs rule?", AgentState.ROUTE),
    ],
)
def test_simple_chat_gets_project_context_only_when_grounding_needed(
    monkeypatch: pytest.MonkeyPatch, rag: str | None, msg: str, expected: AgentState
) -> None:
    if rag is None:
        monkeypatch.delenv("AGK_PROJECT_RAG_ENABLED", raising=False)
    else:
        monkeypatch.setenv("AGK_PROJECT_RAG_ENABLED", rag)
    ctx = SimpleNamespace(task_type="simple_chat", user_message=msg)
    assert ceo_gate_decision(ctx) is expected  # type: ignore[arg-type]
    ctx.task_type = "coding"
    assert ceo_gate_decision(ctx) is AgentState.CONTEXT_ENRICH  # type: ignore[arg-type]
