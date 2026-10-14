"""Unified Agent module.

Combines task classification, Graphify hybrid retrieval, Ssak-Search grounding,
pytest repair loops, and adaptive stability routing.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from antigravity_k.engine.optimizers import HeadroomCompressor
from antigravity_k.engine.optimizers.graphify_builder import (
    KnowledgeGraph,
    build_file_index_rows,
    build_graph,
    hybrid_retrieve,
)
from antigravity_k.engine.sandbox import run_sandboxed_argv
from antigravity_k.tools.ssak_search_client import search as web_search

_TASK_CLASSIFY = (
    "You classify a task into exactly one action category. Reply with one word only.\n"
    "- 'code' if the task asks to write, fix, debug, implement, or modify code or a function\n"
    "- 'explore' if the task asks where/what/how something is in a codebase or project\n"
    "- 'web' if the task needs current, recent, or external information (versions, news, docs)\n"
    "- 'answer' if it is a general stable-knowledge question (concepts, definitions)\n\n"
    "IMPORTANT: any task mentioning 'fix', 'write', 'implement', 'modify', 'function', "
    "'bug', or 'code' is 'code'.\n\n"
    "Task: {task}\n\nAction (one word):"
)

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
_FENCE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)


def _strip_think(text: str) -> str:
    text = _THINK.sub("", text)
    if "<think>" in text:
        text = text.split("<think>")[0]
    return text.strip()


def _extract_code(text: str) -> str:
    m = _FENCE.search(text)
    if m:
        return m.group(1).strip()
    idx = text.find("def ")
    if idx == -1:
        idx = text.find("class ")
    if idx != -1:
        return text[idx:].split("```")[0].strip()
    return text.strip()


@dataclass(slots=True)
class AgentStep:
    action: str
    detail: str
    tokens_in: int = 0


@dataclass(slots=True)
class AgentOutcome:
    task: str
    answer: str
    steps: list[AgentStep] = field(default_factory=list)
    used_web: bool = False
    used_graphify: bool = False
    total_seconds: float = 0.0
    passed: bool | None = None


class UnifiedAgent:
    def __init__(
        self,
        generate_fn: Callable[..., str],
        model: str,
        *,
        project_root: Path | None = None,
        headroom: bool = True,
    ) -> None:
        self._gen = generate_fn
        self._model = model
        self._root = project_root or Path.cwd()
        self._compressor = HeadroomCompressor() if headroom else None
        self._graph: KnowledgeGraph | None = None

    def _generate(self, prompt: str, max_tokens: int = 2048) -> str:
        if self._compressor and len(prompt) > 2000:
            prompt, _ = self._compressor.compress(prompt)
        raw = self._gen(prompt=prompt, target=self._model, max_tokens=max_tokens, temperature=0.0)
        return _strip_think(str(raw))

    def _classify(self, task: str) -> str:
        task_lower = task.lower()
        explore_markers = (
            "where is",
            "which file",
            "which module",
            "where defined",
            "where are",
            "in this codebase",
            "in the codebase",
        )
        if any(m in task_lower for m in explore_markers):
            return "explore"
        web_markers = ("latest", "current", "version", "recent", "news", "2024", "2025", "2026", "today", "now")
        if any(m in task_lower for m in web_markers) and "codebase" not in task_lower:
            return "web"
        code_markers = (
            "fix",
            "write",
            "implement",
            "modify",
            "debug",
            "bug",
            "refactor",
            "push",
            "pop",
            "thread-safe",
            "thread safety",
            "atomic",
            "decode",
            "encode",
            "stack",
            "queue",
            "o(1)",
            "o(n)",
        )
        if any(m in task_lower for m in code_markers):
            return "code"
        raw = self._generate(_TASK_CLASSIFY.format(task=task), max_tokens=50)
        for word in ("code", "explore", "web", "answer"):
            if word in raw.lower():
                return word
        return "answer"

    def _graphify_context(self, task: str) -> str:
        if self._graph is None:
            self._graph = build_graph(self._root)
        graph = self._graph
        files = hybrid_retrieve(graph, task, top_k=12)
        rows = build_file_index_rows(graph, files, symbols_per_file=10)
        return "\n".join(rows)

    def _web_context(self, task: str) -> str:
        hits = web_search(task, max_results=5)
        return "\n".join(f"[{i + 1}] {h.title}\n{h.url}\n{h.content[:300]}" for i, h in enumerate(hits)) if hits else ""

    def _run_explore(self, task: str) -> AgentOutcome:
        outcome = AgentOutcome(task=task, answer="")
        ctx = self._graphify_context(task)
        outcome.used_graphify = bool(ctx)
        prompt = (
            f"Using this codebase structural index (file: symbols), answer the question.\n\n"
            f"{ctx}\n\nQuestion: {task}\n\nAnswer concisely with file and symbol names:"
        )
        outcome.answer = self._generate(prompt, max_tokens=800)
        outcome.steps.append(AgentStep("explore+graphify", f"{len(ctx)} chars context"))
        return outcome

    def _run_web(self, task: str) -> AgentOutcome:
        outcome = AgentOutcome(task=task, answer="")
        ctx = self._web_context(task)
        outcome.used_web = bool(ctx)
        prompt = (
            f"Answer using these web search results.\n\n{ctx}\n\nQuestion: {task}\n\nAnswer:"
            if ctx
            else f"Question: {task}\n\nAnswer:"
        )
        outcome.answer = self._generate(prompt, max_tokens=800)
        outcome.steps.append(AgentStep("web+ssak-search", f"{len(ctx)} chars context"))
        return outcome

    def _run_test_suite(self, workdir: Path) -> tuple[bool, str]:
        """Run ``test_solution.py`` inside the mandatory OS sandbox.

        Returns ``(passed, feedback)``. Backend unavailability, execution
        refusal and timeouts all surface as failure — there is no host-process
        fallback for user/model generated code.
        """
        argv = [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            "-x",
            "-q",
            "--tb=short",
            "-o",
            "pythonpath=.",
            "-p",
            "no:cacheprovider",
            "test_solution.py",
        ]
        home = workdir / ".sandbox-home"
        tmpdir = workdir / ".sandbox-tmp"
        home.mkdir(exist_ok=True)
        tmpdir.mkdir(exist_ok=True)
        env = {
            "PATH": f"{os.path.dirname(sys.executable)}:/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(home),
            "TMPDIR": str(tmpdir),
            "PYTHONPATH": str(workdir),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        }
        result = run_sandboxed_argv(argv, cwd=str(workdir), timeout=15, env=env)
        combined = (result.stdout or "") + (result.stderr or "")
        notes: list[str] = []
        if result.error:
            notes.append(f"[sandbox] {result.error}")
        if result.timed_out:
            notes.append("[sandbox] test execution timed out")
        if not result.sandboxed:
            notes.append("[sandbox] execution did not run under OS sandbox")
        detail = combined[-2000:]
        if notes:
            detail = detail + "\n" + "\n".join(notes)
        return result.success and not notes, detail

    def _run_code(
        self,
        task: str,
        test_code: str | None = None,
        max_repairs: int = 2,
        *,
        consistency_samples: int = 1,
    ) -> AgentOutcome:
        outcome = AgentOutcome(task=task, answer="")
        ctx = self._graphify_context(task)
        outcome.used_graphify = bool(ctx)
        code_ctx = f"\n\nRelevant codebase structure:\n{ctx}\n" if ctx else ""
        workdir = Path(tempfile.mkdtemp())
        try:
            if consistency_samples > 1 and test_code:
                return self._run_code_consistent(task, test_code, code_ctx, workdir, max_repairs, consistency_samples)
            feedback = ""
            for attempt in range(max_repairs + 1):
                prompt = f"You are fixing/writing Python code.{code_ctx}\n\nTask: {task}\n"
                if feedback:
                    prompt += f"\nPrevious attempt failed:\n{feedback}\n"
                prompt += "\nReturn the complete code in a ```python fenced block."
                raw = self._generate(prompt, max_tokens=2048)
                code = _extract_code(raw)
                outcome.answer = code
                if test_code:
                    (workdir / "solution.py").write_text(code, encoding="utf-8")
                    (workdir / "test_solution.py").write_text(test_code, encoding="utf-8")
                    passed, combined = self._run_test_suite(workdir)
                    if passed:
                        outcome.passed = True
                        outcome.steps.append(AgentStep(f"code+repair({attempt})", "passed"))
                        return outcome
                    feedback = combined
                    outcome.steps.append(AgentStep(f"code+repair({attempt})", "failed, retrying"))
                else:
                    outcome.passed = True
                    outcome.steps.append(AgentStep("code", "no test"))
                    return outcome
            outcome.passed = False
            return outcome
        finally:
            import shutil

            shutil.rmtree(workdir, ignore_errors=True)

    def _run_answer(self, task: str) -> AgentOutcome:
        outcome = AgentOutcome(task=task, answer="")
        outcome.answer = self._generate(f"Question: {task}\n\nAnswer concisely:", max_tokens=800)
        outcome.steps.append(AgentStep("answer", "direct"))
        return outcome

    def _run_code_consistent(
        self,
        task: str,
        test_code: str,
        code_ctx: str,
        workdir: Path,
        max_repairs: int,
        samples: int,
    ) -> AgentOutcome:
        outcome = AgentOutcome(task=task, answer="")
        outcome.used_graphify = bool(code_ctx)
        passing_codes: list[str] = []
        for sample in range(samples):
            feedback = ""
            for attempt in range(max_repairs + 1):
                prompt = f"You are writing Python code.{code_ctx}\n\nTask: {task}\n"
                if feedback:
                    prompt += f"\nPrevious attempt failed:\n{feedback}\n"
                prompt += "\nReturn the complete code in a ```python fenced block."
                raw = self._generate(prompt, max_tokens=2048)
                code = _extract_code(raw)
                (workdir / "solution.py").write_text(code, encoding="utf-8")
                (workdir / "test_solution.py").write_text(test_code, encoding="utf-8")
                passed, combined = self._run_test_suite(workdir)
                if passed:
                    normalized = re.sub(r"\s+", " ", code).strip()[:600]
                    passing_codes.append(normalized)
                    outcome.answer = code
                    outcome.steps.append(AgentStep(f"consistency({sample},{attempt})", "passed"))
                    break
                feedback = combined
            else:
                outcome.steps.append(AgentStep(f"consistency({sample})", "no pass"))
        if passing_codes:
            outcome.passed = True
        else:
            outcome.passed = False
        return outcome

    def _probe_diversity(self, task: str, code_ctx: str) -> bool:
        probe_prompt = (
            f"You are writing Python code.{code_ctx}\n\n"
            f"Task: {task}\n\nReturn the complete code in a ```python fenced block."
        )
        samples = []
        for _ in range(2):
            raw = self._generate(probe_prompt, max_tokens=1024)
            code = _extract_code(raw)
            normalized = re.sub(r"\s+", " ", code)
            normalized = re.sub(r"#.*", "", normalized)
            samples.append(normalized[:500])
        return samples[0] != samples[1]

    def _run_code_adaptive(
        self,
        task: str,
        test_code: str,
        code_ctx: str,
        workdir: Path,
        max_repairs: int,
        consistency_samples: int,
    ) -> AgentOutcome:
        diverse = self._probe_diversity(task, code_ctx)
        if diverse:
            outcome = self._run_code_consistent(task, test_code, code_ctx, workdir, max_repairs, consistency_samples)
            outcome.steps.append(AgentStep("adaptive", "diverse -> consistency"))
            return outcome
        deeper = self._run_code(task, test_code, max_repairs + 1, consistency_samples=1)
        deeper.steps.append(AgentStep("adaptive", "converged -> deeper repair"))
        return deeper

    def run(
        self,
        task: str,
        *,
        test_code: str | None = None,
        max_repairs: int = 2,
        consistency_samples: int = 1,
        adaptive: bool = False,
        use_web: bool = False,
    ) -> AgentOutcome:
        t0 = time.time()
        action = "web" if use_web else self._classify(task)
        outcome = AgentOutcome(task=task, answer="")
        if action == "explore":
            outcome = self._run_explore(task)
        elif action == "web":
            outcome = self._run_web(task)
        elif action == "code":
            if adaptive and test_code:
                ctx = self._graphify_context(task)
                code_ctx = f"\n\nRelevant codebase structure:\n{ctx}\n" if ctx else ""
                workdir = Path(tempfile.mkdtemp())
                try:
                    outcome = self._run_code_adaptive(
                        task, test_code, code_ctx, workdir, max_repairs, consistency_samples
                    )
                finally:
                    import shutil

                    shutil.rmtree(workdir, ignore_errors=True)
            else:
                outcome = self._run_code(task, test_code, max_repairs, consistency_samples=consistency_samples)
        else:
            outcome = self._run_answer(task)
        outcome.total_seconds = time.time() - t0
        return outcome
