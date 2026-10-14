"""Workspace Links module."""

import os
import urllib.parse
from typing import TypedDict

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/workspaces")


class _IDELinks(TypedDict):
    vscode: str
    jetbrains_intellij: str
    jetbrains_pycharm: str
    jetbrains_goland: str
    jetbrains_webstorm: str


class _WorkspaceLink(TypedDict):
    name: str
    path: str
    links: _IDELinks


@router.get("/links")
async def get_workspace_links():
    """현재 Ssak-Ai가 위치한 프로젝트 루트 및.

    Multiplexer를 통해 생성된 Git Worktree 샌드박스들의 경로를 바탕으로
    로컬 네이티브 IDE(VS Code, JetBrains)용 딥링크를 생성하여 반환합니다.
    """
    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    )
    worktrees_dir = os.path.join(project_root, ".ag_worktrees")

    links: list[_WorkspaceLink] = []

    # 기본 루트(Main Workspace)
    links.append(_generate_links_for_path(project_root, "Main Workspace"))

    # 서브 샌드박스(Worktrees) 스캔
    if os.path.exists(worktrees_dir):
        for entry in os.listdir(worktrees_dir):
            full_path = os.path.join(worktrees_dir, entry)
            if os.path.isdir(full_path):
                links.append(_generate_links_for_path(full_path, f"Sandbox: {entry}"))

    return JSONResponse(content={"ok": True, "workspaces": links})


def _generate_links_for_path(absolute_path: str, name: str) -> _WorkspaceLink:
    """주어진 경로에 대한 VS Code 및 JetBrains Gateway 접근 URI를 생성합니다."""
    # URL Encoding for paths
    encoded_path = urllib.parse.quote(absolute_path)

    return {
        "name": name,
        "path": absolute_path,
        "links": {
            "vscode": f"vscode://file{absolute_path}",
            "jetbrains_intellij": f"jetbrains://idea/project?projectPath={encoded_path}",
            "jetbrains_pycharm": f"jetbrains://pycharm/project?projectPath={encoded_path}",
            "jetbrains_goland": f"jetbrains://goland/project?projectPath={encoded_path}",
            "jetbrains_webstorm": f"jetbrains://webstorm/project?projectPath={encoded_path}",
        },
    }
