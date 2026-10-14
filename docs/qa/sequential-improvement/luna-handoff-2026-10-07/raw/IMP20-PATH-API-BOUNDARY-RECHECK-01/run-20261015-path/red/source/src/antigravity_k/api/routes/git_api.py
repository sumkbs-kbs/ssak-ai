"""Git API routes for the dashboard Git GUI.

Provides structured JSON endpoints for common Git operations:
status, log, diff, add, commit, branch, stash, and graph.
"""

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, ClassVar, TypeAlias, TypedDict, TypeVar

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, ValidationError

from antigravity_k.config import config
from antigravity_k.engine.api_cache import TAG_GIT, api_cache, cached
from antigravity_k.tools.permission_gate import PermissionGate
from antigravity_k.tools.tool_contracts import Permission, ToolInvocation, ToolSpec

logger = logging.getLogger("antigravity_k.api.git_api")
router = APIRouter()
_ModelT = TypeVar("_ModelT", bound=BaseModel)
JsonMap: TypeAlias = dict[str, object]


class GitStatusEntry(TypedDict):
    x: str
    y: str
    staged_status: str
    unstaged_status: str
    file_path: str
    old_path: str | None
    is_renamed: bool


class _GitLogRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)
    path: StrictStr = "."
    count: StrictInt = Field(default=20, ge=1, le=500)
    branch: StrictStr = ""


class _GitDiffRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)
    path: StrictStr = "."
    file: StrictStr = ""
    staged: StrictBool = False
    unified: StrictInt = Field(default=3, ge=0, le=100)


class _GitFilesRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)
    path: StrictStr = "."
    files: list[StrictStr] = Field(default_factory=list)


class _GitAddRequest(_GitFilesRequest):
    all: StrictBool = False


class _GitCommitRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)
    path: StrictStr = "."
    message: StrictStr = ""
    stage_all: StrictBool = True


class _GitBranchCreateRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True, populate_by_name=True)
    path: StrictStr = "."
    name: StrictStr = ""
    from_branch: StrictStr = Field(default="", alias="from")


class _GitBranchRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)
    path: StrictStr = "."
    name: StrictStr = ""


class _GitBranchDeleteRequest(_GitBranchRequest):
    force: StrictBool = False


async def _parse_json_body(request: Request, model: type[_ModelT]) -> _ModelT:
    try:
        return model.model_validate(await request.json())
    except (ValidationError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid request body") from exc


# ─── Helpers ────────────────────────────────────────────────────


def _permission_gate() -> PermissionGate:
    return PermissionGate(project_root=str(config.paths.project_root), mode="auto-pilot")


def _require_allowed(tool_name: str, args: JsonMap, risk_level: str) -> None:
    decision = _permission_gate().decide(
        ToolInvocation(ToolSpec(name=tool_name, risk_level=risk_level, category="api"), args),
    )
    if decision.permission != Permission.ALLOW:
        raise HTTPException(status_code=403, detail=f"Permission denied for {tool_name}: {decision.permission.value}")


def _resolve_git_dir(cwd: str = ".") -> Path:
    """Git 명령의 작업 디렉터리를 검증·해석한다.

    기준(base) 우선순위: ``config.paths.project_root`` → 등록 프로젝트의 active path.
    테스트가 ``config.paths.project_root``를 monkeypatch하는 계약을 지키려면 config가
    항상 먼저 적용되어야 하고, 등록 프로젝트 경로는 그 아래에 허용 루트로 추가된다
    (``allowed_roots()``가 레지스트리 프로젝트를 이미 포함한다).
    """
    from antigravity_k.api.path_security import allowed_roots

    roots = allowed_roots()
    config_root = Path(config.paths.project_root).expanduser().resolve()

    try:
        from antigravity_k.engine.project_registry import get_project_registry

        active = get_project_registry().get_active_project()
    except Exception:  # noqa: BLE001 — 레지스트리 미가용 시 config 기준으로 폴백
        active = None
    active_path = Path(active.path).expanduser().resolve() if active and active.path else None
    # config와 일치하지 않는 활성 프로젝트(스태일 캐시 등)는 베이스로 쓰지 않는다
    active_root = active_path if active_path in roots else None

    requested_path = Path(cwd).expanduser()
    if cwd in ("", "."):
        candidate = config_root
    elif requested_path.is_absolute():
        candidate = requested_path.resolve()
    else:
        # 상대 경로는 config 루트 기준으로 해석 (기존 계약).
        # active_root가 유효하면 해당 위치도 시도해 본다.
        base_candidates = [config_root]
        if active_root is not None and active_root != config_root:
            base_candidates.append(active_root)
        candidate = (
            next((base / requested_path).resolve() for base in base_candidates if (base / requested_path).is_dir())
            if any((base / requested_path).is_dir() for base in base_candidates)
            else (config_root / requested_path).resolve()
        )

    if not candidate.is_dir():
        raise HTTPException(status_code=400, detail="Git working directory does not exist.")

    is_allowed = False
    for r in roots:
        try:
            candidate.relative_to(r)
            is_allowed = True
            break
        except ValueError:
            continue
    if not is_allowed and ((candidate / ".git").exists() or (candidate / ".git").is_file()):
        is_allowed = True

    if not is_allowed:
        raise HTTPException(status_code=403, detail="Git working directory must remain inside the project root.")
    return candidate


def _resolve_repo_file(file_path: str, cwd: str = ".") -> str:
    """Ensure a target file belongs to the repository working directory."""
    base = _resolve_git_dir(cwd)
    candidate = (base / file_path).resolve()
    try:
        relative = candidate.relative_to(base)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Git file path must remain inside the repository.") from exc
    return relative.as_posix()


_validate_repo_relative_file = _resolve_repo_file


def _git(args: list[str], cwd: str = ".", timeout: int = 30) -> str:
    """Run a git command and return stdout."""
    candidate = _resolve_git_dir(cwd)
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=str(candidate),
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        return result.stdout
    except FileNotFoundError:
        raise HTTPException(status_code=400, detail="Git is not installed or not in PATH.")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=408, detail="Git command timed out.")
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _parse_status_line(line: str) -> GitStatusEntry | None:
    """Parse a single git status --short line into structured data."""
    line = line.rstrip("\n")
    if not line or line.startswith("#"):
        return None

    # Handle copied/renamed files with ->
    if "->" in line:
        # Renamed/copied: R  old -> new
        parts = line[3:].split(" -> ")
        x = line[0]
        y = line[1]
        old_path = parts[0].strip()
        new_path = parts[1].strip() if len(parts) > 1 else old_path
        return {
            "x": x,
            "y": y,
            "staged_status": _status_char(x),
            "unstaged_status": _status_char(y),
            "file_path": new_path,
            "old_path": old_path,
            "is_renamed": True,
        }

    # Normal file
    x = line[0]
    y = line[1]
    file_path = line[3:]

    return {
        "x": x,
        "y": y,
        "staged_status": _status_char(x),
        "unstaged_status": _status_char(y),
        "file_path": file_path,
        "old_path": None,
        "is_renamed": False,
    }


def _status_char(c: str) -> str:
    """Convert status character to human-readable label."""
    mapping = {
        "M": "modified",
        "A": "added",
        "D": "deleted",
        "R": "renamed",
        "C": "copied",
        "U": "updated",
        "?": "untracked",
        "!": "ignored",
        " ": "unchanged",
    }
    return mapping.get(c, "unknown")


@dataclass
class BranchInfo:
    name: str
    is_current: bool
    is_remote: bool = False
    upstream: str | None = None
    ahead: int = 0
    behind: int = 0


# ─── API Endpoints ──────────────────────────────────────────────


@router.get("/api/git/status")
@cached(ttl=10, tags=[TAG_GIT])
async def git_status(path: Annotated[str, Query(description="Repository path")] = ".") -> JsonMap:
    """Get git status with structured file changes."""
    try:
        # Status short
        status_output = _git(["status", "--short", "--branch"], cwd=path)

        # Parse files
        lines = status_output.split("\n")
        files: list[GitStatusEntry] = []
        branch_line = ""

        for line in lines:
            if line.startswith("##"):
                branch_line = line
            else:
                parsed = _parse_status_line(line)
                if parsed:
                    files.append(parsed)

        # Parse branch line: "## main...origin/main [ahead 1, behind 2]"
        branch_parts = branch_line.replace("## ", "").split("...")
        current_branch = branch_parts[0]
        upstream = branch_parts[1] if len(branch_parts) > 1 else None

        ahead = 0
        behind = 0
        if upstream and "[" in upstream:
            bracket = upstream[upstream.index("[") :]
            upstream = upstream[: upstream.index("[")].strip()
            if "ahead" in bracket:
                ahead = int(bracket.split("ahead")[1].split()[0].replace("]", ""))
            if "behind" in bracket:
                behind = int(bracket.split("behind")[1].split()[0].replace("]", ""))

        # Count by status
        staged = sum(1 for f in files if f["x"] != " " and f["x"] != "?")
        unstaged = sum(1 for f in files if f["y"] != " " and f["y"] != "?")
        untracked = sum(1 for f in files if f["x"] == "?" or f["y"] == "?")

        return {
            "ok": True,
            "branch": current_branch,
            "upstream": upstream,
            "ahead": ahead,
            "behind": behind,
            "files": files,
            "counts": {
                "staged": staged,
                "unstaged": unstaged,
                "untracked": untracked,
                "total": len(files),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Git status error")
        return {"ok": False, "error": str(e)}


@router.post("/api/git/log")
async def git_log(request: Request) -> JsonMap:
    """Get commit log with structured data."""
    payload = await _parse_json_body(request, _GitLogRequest)
    try:
        path = payload.path
        count = payload.count
        branch = payload.branch

        args = ["log", f"-n{count}", "--format=%H||%h||%an||%ae||%ai||%s||%D"]
        if branch:
            args.extend([branch, "--"])

        output = _git(args, cwd=path)
        commits: list[JsonMap] = []
        for line in output.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("||", 6)
            if len(parts) >= 6:
                commits.append(
                    {
                        "hash": parts[0],
                        "short_hash": parts[1],
                        "author_name": parts[2],
                        "author_email": parts[3],
                        "date": parts[4],
                        "message": parts[5],
                        "refs": parts[6] if len(parts) > 6 else "",
                    }
                )

        return {"ok": True, "commits": commits, "count": len(commits)}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Git log error")
        return {"ok": False, "error": str(e)}


@router.post("/api/git/diff")
async def git_diff(request: Request) -> JsonMap:
    """Get diff for a file or all changes."""
    payload = await _parse_json_body(request, _GitDiffRequest)
    try:
        path = payload.path
        file_path = payload.file
        staged = payload.staged
        unified = payload.unified
        safe_file_path = _resolve_repo_file(file_path, path) if file_path else ""

        args = ["diff", f"--unified={unified}"]
        if staged:
            args.append("--cached")
        if safe_file_path:
            args.extend(["--", safe_file_path])

        output = _git(args, cwd=path)

        # Parse diff stats
        stat_args = ["diff", "--stat"]
        if staged:
            stat_args.append("--cached")
        if safe_file_path:
            stat_args.extend(["--", safe_file_path])
        stat_output = _git(stat_args, cwd=path)

        return {
            "ok": True,
            "diff": output,
            "stat": stat_output,
            "staged": staged,
            "file": file_path,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Git diff error")
        return {"ok": False, "error": str(e)}


@router.post("/api/git/add")
async def git_add(request: Request):
    """Stage files."""
    payload = await _parse_json_body(request, _GitAddRequest)
    try:
        path = payload.path
        files = payload.files
        all_files = payload.all
        _require_allowed("git_add", {"path": path, "files": files, "all": all_files}, "medium")

        if all_files:
            _ = _git(["add", "-A"], cwd=path)
            _ = await api_cache.invalidate_tag(TAG_GIT)
            return {"ok": True, "message": "All files staged.", "all": True}
        elif files:
            _ = _git(["add", "--"] + files, cwd=path)
            _ = await api_cache.invalidate_tag(TAG_GIT)
            return {"ok": True, "message": f"{len(files)} file(s) staged.", "files": files}
        else:
            return {"ok": False, "error": "No files specified."}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Git add error")
        return {"ok": False, "error": str(e)}


@router.post("/api/git/unstage")
async def git_unstage(request: Request):
    """Unstage files."""
    payload = await _parse_json_body(request, _GitFilesRequest)
    try:
        path = payload.path
        files = payload.files
        _require_allowed("git_unstage", {"path": path, "files": files}, "medium")

        if files:
            _ = _git(["restore", "--staged", "--"] + files, cwd=path)
            _ = await api_cache.invalidate_tag(TAG_GIT)
            return {"ok": True, "message": f"{len(files)} file(s) unstaged.", "files": files}
        else:
            # Unstage all
            _ = _git(["restore", "--staged", "."], cwd=path)
            _ = await api_cache.invalidate_tag(TAG_GIT)
            return {"ok": True, "message": "All files unstaged.", "all": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Git unstage error")
        return {"ok": False, "error": str(e)}


@router.post("/api/git/commit")
async def git_commit(request: Request) -> JsonMap:
    """Create a commit."""
    payload = await _parse_json_body(request, _GitCommitRequest)
    try:
        path = payload.path
        message = payload.message
        stage_all = payload.stage_all

        if not message.strip():
            return {"ok": False, "error": "Commit message is required."}
        _require_allowed("git_commit", {"path": path, "message": message}, "critical")

        if stage_all:
            _ = _git(["add", "-A"], cwd=path)

        output = _git(["commit", "-m", message], cwd=path)
        _ = await api_cache.invalidate_tag(TAG_GIT)
        return {"ok": True, "message": "Commit created.", "output": output}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Git commit error")
        return {"ok": False, "error": str(e)}


@router.get("/api/git/branches")
@cached(ttl=30, tags=[TAG_GIT])
async def git_branches(path: Annotated[str, Query(description="Repository path")] = ".") -> JsonMap:
    """List branches with current indicator."""
    try:
        output = _git(["branch", "-a", "--format=%(refname:short)|%(HEAD)|%(upstream:short)"], cwd=path)

        branches: list[JsonMap] = []
        for line in output.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("|")
            name = parts[0]
            is_head = parts[1] == "*"
            upstream = parts[2] if len(parts) > 2 and parts[2] else None

            branches.append(
                {
                    "name": name,
                    "is_current": is_head,
                    "is_remote": name.startswith("remotes/"),
                    "upstream": upstream,
                }
            )

        # Get current branch
        current = _git(["branch", "--show-current"], cwd=path).strip()

        return {"ok": True, "branches": branches, "current": current}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Git branches error")
        return {"ok": False, "error": str(e)}


@router.post("/api/git/branch/create")
async def git_branch_create(request: Request):
    """Create a new branch."""
    payload = await _parse_json_body(request, _GitBranchCreateRequest)
    try:
        path = payload.path
        name = payload.name
        from_branch = payload.from_branch

        if not name.strip():
            return {"ok": False, "error": "Branch name is required."}
        _require_allowed("git_branch_create", {"path": path, "name": name}, "medium")

        if from_branch:
            _ = _git(["checkout", from_branch], cwd=path)

        _ = _git(["checkout", "-b", name], cwd=path)
        _ = await api_cache.invalidate_tag(TAG_GIT)
        return {"ok": True, "message": f"Branch '{name}' created and checked out.", "branch": name}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Git branch create error")
        return {"ok": False, "error": str(e)}


@router.post("/api/git/checkout")
async def git_checkout(request: Request):
    """Checkout a branch."""
    payload = await _parse_json_body(request, _GitBranchRequest)
    try:
        path = payload.path
        name = payload.name

        if not name.strip():
            return {"ok": False, "error": "Branch name is required."}
        _require_allowed("git_checkout", {"path": path, "name": name}, "high")

        _ = _git(["checkout", name], cwd=path)
        _ = await api_cache.invalidate_tag(TAG_GIT)
        return {"ok": True, "message": f"Switched to branch '{name}'.", "branch": name}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Git checkout error")
        return {"ok": False, "error": str(e)}


@router.post("/api/git/branch/delete")
async def git_branch_delete(request: Request):
    """Delete a branch."""
    payload = await _parse_json_body(request, _GitBranchDeleteRequest)
    try:
        path = payload.path
        name = payload.name
        force = payload.force

        if not name.strip():
            return {"ok": False, "error": "Branch name is required."}
        _require_allowed("git_branch_delete", {"path": path, "name": name, "force": force}, "critical")

        flag = "-D" if force else "-d"
        _ = _git(["branch", flag, name], cwd=path)
        _ = await api_cache.invalidate_tag(TAG_GIT)
        return {"ok": True, "message": f"Branch '{name}' deleted."}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Git branch delete error")
        return {"ok": False, "error": str(e)}


@router.get("/api/git/graph")
@cached(ttl=30, tags=[TAG_GIT])
async def git_graph(
    path: Annotated[str, Query(description="Repository path")] = ".",
    count: Annotated[int, Query(description="Number of commits")] = 30,
) -> JsonMap:
    """Get branch graph visualization data."""
    try:
        output = _git(
            [
                "log",
                "--all",
                f"-n{count}",
                "--format=%H||%h||%an||%s||%ai||%D",
                "--graph",
            ],
            cwd=path,
        )

        nodes: list[JsonMap] = []
        for line in output.strip().split("\n"):
            if not line.strip():
                continue
            # Extract graph characters prefix
            graph_chars = ""
            content = line
            for ch in line:
                if ch in "*|/\\ _.-":
                    graph_chars += ch
                    content = content[1:]
                else:
                    break
            content = content.strip()
            parts = content.split("||", 5)
            if len(parts) >= 4:
                nodes.append(
                    {
                        "graph": graph_chars,
                        "hash": parts[0],
                        "short_hash": parts[1],
                        "author": parts[2],
                        "message": parts[3],
                        "date": parts[4] if len(parts) > 4 else "",
                        "refs": parts[5] if len(parts) > 5 else "",
                    }
                )

        return {"ok": True, "nodes": nodes, "count": len(nodes)}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Git graph error")
        return {"ok": False, "error": str(e)}


@router.get("/api/git/file-content")
async def git_file_content(
    file: Annotated[str, Query(description="File path")],
    path: Annotated[str, Query(description="Repository path")] = ".",
    ref: Annotated[str, Query(description="Git ref")] = "HEAD",
) -> JsonMap:
    """Get file content from a specific git ref."""
    try:
        safe_file_path = _resolve_repo_file(file, path)
        output = _git(["show", f"{ref}:{safe_file_path}"], cwd=path)
        return {"ok": True, "content": output, "ref": ref, "file": file}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Git file content error")
        return {"ok": False, "error": str(e)}


@router.get("/api/git/stash/list")
@cached(ttl=30, tags=[TAG_GIT])
async def git_stash_list(path: Annotated[str, Query(description="Repository path")] = ".") -> JsonMap:
    """List stashes."""
    try:
        output = _git(["stash", "list", "--format=%h||%ai||%s"], cwd=path)
        stashes: list[JsonMap] = []
        for line in output.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("||", 2)
            if len(parts) >= 2:
                stashes.append(
                    {
                        "short_hash": parts[0],
                        "date": parts[1],
                        "message": parts[2] if len(parts) > 2 else "",
                    }
                )
        return {"ok": True, "stashes": stashes}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Git stash list error")
        return {"ok": False, "error": str(e)}
