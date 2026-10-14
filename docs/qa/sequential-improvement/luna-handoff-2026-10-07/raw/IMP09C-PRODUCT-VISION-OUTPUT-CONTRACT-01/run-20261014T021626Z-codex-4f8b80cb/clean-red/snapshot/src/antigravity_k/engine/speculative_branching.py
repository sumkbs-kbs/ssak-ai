"""Speculative Branching Engine — 병렬 가설 검증 in 격리 워크스페이스.

27B급 모델이 어려운 알고리즘/디버깅 과제에서 단일 선형 시도로 막히는 문제를
테스트타임 컴퓨트 스케일링으로 돌파한다:

1. 격리된 가설 브랜치별 작업 공간 생성 (git worktree 우선, 비-git은 임시 디렉터리)
2. ThreadPoolExecutor로 후보 패치를 **진짜 병렬** 적용 + 테스트 실행
3. 최초 통과(green) 가설을 승자로 채택하고 나머지는 폐기
4. 실패 가설의 교훈을 반환해 ReflexionMemory 등 상위 피드백에 재사용

v1(순차+빈 tempdir) 대비 변경:
  - 진짜 병렬 실행 (max_workers 제한 동시성)
  - git 저장소면 worktree로 실제 코드베이스 스냅샷에서 검증
  - 하위호환: evaluate_hypotheses 기존 시그니처/동작 유지
"""

import logging
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from antigravity_k.engine.sandbox import run_sandboxed_argv

logger = logging.getLogger("antigravity_k.speculative_branching")

PatchGenerator = Callable[[Path], bool]


@dataclass
class Workspace:
    """가설 검증용 격리 작업 공간 (worktree 또는 임시 디렉터리)."""

    path: Path
    kind: str  # "worktree" | "tempdir"
    _cleanup_cmd: list[str] | None = None

    def cleanup(self) -> None:
        """작업 공간을 정리한다. worktree면 git에서 먼저 제거한다."""
        if self._cleanup_cmd:
            try:
                _ = subprocess.run(
                    self._cleanup_cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
            except Exception as exc:
                logger.debug("worktree cleanup failed for %s: %s", self.path, exc)
        try:
            shutil.rmtree(self.path, ignore_errors=True)
        except Exception as exc:
            logger.debug("workspace rmtree failed for %s: %s", self.path, exc)


@dataclass
class SpeculativeResult:
    """Outcome of speculative branch execution."""

    winner_branch: str | None
    success: bool
    passed_tests_count: int
    discarded_branches: list[str]
    failure_lessons: list[str]
    elapsed_ms: float = 0.0
    evaluated: int = 0
    workspace_kinds: dict[str, str] = field(default_factory=dict)


class SpeculativeBranchingEngine:
    """Coordinates parallel branch creation, test execution, and atomic merging."""

    def __init__(self, project_root: str | Path) -> None:
        self.project_root: Path = Path(project_root).resolve()

    # ─── 작업 공간 준비 ───────────────────────────────────────────────

    def _is_git_repo(self) -> bool:
        git_dir = self.project_root / ".git"
        return git_dir.exists()

    def _make_worktree(self, name: str) -> Workspace:
        """HEAD 기준 detached worktree를 생성한다. 실패 시 None."""
        base = Path(tempfile.mkdtemp(prefix=f"agk_spec_{name}_"))
        wt_path = base / "wt"
        add_cmd = [
            "git",
            "-C",
            str(self.project_root),
            "worktree",
            "add",
            "--detach",
            str(wt_path),
            "HEAD",
        ]
        try:
            res = subprocess.run(add_cmd, capture_output=True, text=True, timeout=120, check=False)
        except Exception as exc:
            logger.debug("worktree add failed (%s): %s", name, exc)
            shutil.rmtree(base, ignore_errors=True)
            raise OSError(f"worktree add failed: {exc}") from exc
        if res.returncode != 0 or not wt_path.exists():
            shutil.rmtree(base, ignore_errors=True)
            raise OSError(f"worktree add rejected: {(res.stderr or res.stdout).strip()[:200]}")
        return Workspace(
            path=wt_path,
            kind="worktree",
            _cleanup_cmd=["git", "-C", str(self.project_root), "worktree", "remove", "--force", str(wt_path)],
        )

    @staticmethod
    def _make_tempdir(_name: str) -> Workspace:
        """v1 호환 폴백: 빈 임시 디렉터리 (generator가 파일을 직접 쓴다)."""
        path = Path(tempfile.mkdtemp(prefix="agk_spec_fb_"))
        return Workspace(path=path, kind="tempdir")

    def open_workspace(self, name: str, prefer_worktree: bool) -> Workspace:
        if prefer_worktree and self._is_git_repo():
            try:
                return self._make_worktree(name)
            except OSError as exc:
                logger.warning("worktree 폴백(tempdir) — %s", exc)
        return self._make_tempdir(name)

    # ─── 단일 가설 평가 ──────────────────────────────────────────────

    def _evaluate_one(
        self,
        name: str,
        generator: PatchGenerator,
        cmd: list[str],
        timeout_sec: float,
        prefer_worktree: bool,
    ) -> tuple[str, bool, str, Workspace]:
        """단일 가설을 격리 공간에서 평가. (name, passed, lesson, workspace) 반환.

        workspace는 호출자가 cleanup() 해야 한다.
        """
        workspace = self.open_workspace(name, prefer_worktree)
        try:
            applied = generator(workspace.path)
        except Exception as ex:
            return name, False, f"Hypothesis '{name}' threw exception during patch: {ex}", workspace
        if not applied:
            return name, False, f"Hypothesis '{name}' failed during patch generation.", workspace

        try:
            res = run_sandboxed_argv(cmd, cwd=str(workspace.path), timeout=timeout_sec)
        except OSError:
            return name, False, f"Hypothesis '{name}' test spawn failed.", workspace
        if res.timed_out:
            return name, False, f"Hypothesis '{name}' timed out after {timeout_sec:.0f}s", workspace
        if res.error and res.return_code == -1:
            return name, False, f"Hypothesis '{name}' test spawn failed: {res.error}", workspace
        if res.return_code == 0:
            return name, True, "", workspace
        output = (res.stderr or res.stdout).strip()
        short_err = output.splitlines()[-1] if output else "Tests failed"
        return name, False, f"Hypothesis '{name}' failed test with: {short_err}", workspace

    # ─── 공개 API ────────────────────────────────────────────────────

    def evaluate_hypotheses(
        self,
        hypothesis_names: list[str],
        patch_generators: dict[str, Callable[[Path], bool]],
        test_command: list[str] | None = None,
        *,
        parallel: bool = True,
        max_workers: int | None = None,
        use_worktrees: bool = True,
        timeout_sec: float = 20.0,
    ) -> SpeculativeResult:
        """Run candidate patches in isolated workspaces and pick the winner.

        승자 선정은 결정론적이다: 통과한 가설 중 원본 hypothesis_names 순서에서
        가장 앞선 것을 채택한다. 병렬 모드에서는 전부 평가한 뒤 선택하므로
        실행 순서가 결과에 영향을 주지 않는다.

        Args:
            hypothesis_names: List of hypothesis identifiers (e.g. ['strategy_a', 'strategy_b']).
            patch_generators: Mapping of hypothesis name -> function(workspace_path) that applies the patch.
            test_command: Command to run to verify the patch (default: ['pytest', '-q']).
            parallel: ThreadPoolExecutor 병렬 평가 여부 (기본 True). False면
                첫 성공 시점에 중단해 후속 가설의 실행 자체를 생략한다.
            max_workers: 동시 실행 상한 (None = min(len(names), 8)).
            use_worktrees: git 저장소에서 HEAD 기준 worktree 격리 사용 (기본 True).
            timeout_sec: 가설별 테스트 명령 타임아웃.

        Returns:
            SpeculativeResult indicating winning candidate and lessons from discarded ones.
        """
        cmd = test_command or ["pytest", "-q"]
        started = time.perf_counter()
        jobs = [(n, patch_generators[n]) for n in hypothesis_names if n in patch_generators]

        winner: str | None = None
        lessons: list[str] = []
        discarded: list[str] = []
        workspace_kinds: dict[str, str] = {}

        if not jobs:
            return SpeculativeResult(
                winner_branch=None,
                success=False,
                passed_tests_count=0,
                discarded_branches=[],
                failure_lessons=["No matching patch generators supplied."],
                elapsed_ms=(time.perf_counter() - started) * 1000,
                evaluated=0,
            )

        def run_job(item: tuple[str, PatchGenerator]) -> tuple[str, bool, str, Workspace]:
            name, generator = item
            return self._evaluate_one(name, generator, cmd, timeout_sec, use_worktrees)

        outcomes: dict[str, tuple[bool, str]] = {}
        if not parallel or len(jobs) == 1:
            # 순차 모드: 첫 성공 시 중단 (실행 생략으로 실제 비용 절약)
            for name, generator in jobs:
                result_name, passed, lesson, ws = run_job((name, generator))
                workspace_kinds[result_name] = ws.kind
                ws.cleanup()
                outcomes[result_name] = (passed, lesson)
                if passed:
                    break
        else:
            workers = max_workers or min(len(jobs), 8)
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(run_job, job): job[0] for job in jobs}
                for fut in futures:
                    name = futures[fut]
                    try:
                        result_name, passed, lesson, ws = fut.result()
                    except Exception as ex:  # 방어: 개별 실패가 전체를 깨지 않게 한다
                        result_name, passed, lesson = name, False, f"Hypothesis '{name}' crashed evaluator: {ex}"
                        workspace_kinds[name] = "unknown"
                    else:
                        workspace_kinds[result_name] = ws.kind
                        ws.cleanup()
                    outcomes[result_name] = (passed, lesson)

        # 결정론적 승자 선택: 원본 순서에서 최초 통과 가설
        for name, _generator in jobs:
            passed, lesson = outcomes.get(name, (False, ""))
            if passed:
                winner = name
                break
            discarded.append(name)
            lessons.append(lesson)

        return SpeculativeResult(
            winner_branch=winner,
            success=winner is not None,
            passed_tests_count=1 if winner else 0,
            discarded_branches=discarded,
            failure_lessons=lessons,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            evaluated=len(jobs),
            workspace_kinds=workspace_kinds,
        )
