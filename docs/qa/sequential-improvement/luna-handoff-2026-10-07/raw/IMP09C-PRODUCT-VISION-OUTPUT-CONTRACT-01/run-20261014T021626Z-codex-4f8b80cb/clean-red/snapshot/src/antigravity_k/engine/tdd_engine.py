"""Tdd Engine module."""

import asyncio
import json
import logging
import os
import re
import shutil
import time
from collections.abc import Awaitable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Protocol, cast

from antigravity_k.engine.external_brain import ExternalBrainRouter
from antigravity_k.engine.quality_gate import QualityGate, QualityGrade
from antigravity_k.engine.sandbox import run_sandboxed_argv

logger = logging.getLogger("antigravity_k.tdd_engine")


class _ModelManagerLike(Protocol):
    def generate(self, *, prompt: str, target: str, temperature: float) -> str: ...

    def get_target_for_role(self, role: str, default_role: str = "") -> str | None: ...


class TDDStatus(str, Enum):
    """Tddstatus.

    Bases: str, Enum
    """

    PENDING = "pending"
    GENERATING = "generating"
    TESTING = "testing"
    FIXING = "fixing"
    PASSED = "passed"
    FAILED = "failed"


@dataclass
class TDDCandidate:
    """A candidate code snippet to be validated via TDD (red-green-refactor)."""

    source: str
    code: str
    stdout: str = ""
    stderr: str = ""
    exit_code: int = -1
    passed: bool = False
    duration_ms: float = 0.0


@dataclass
class TDDAttempt:
    """A single TDD attempt (test run result + generated code)."""

    iteration: int
    test_code: str
    candidates: list[TDDCandidate] = field(default_factory=list)
    winner_source: str = ""
    duration_ms: float = 0.0


@dataclass
class TDDReport:
    """Aggregated TDD cycle report (attempts, pass/fail, final code)."""

    prompt: str
    status: TDDStatus = TDDStatus.PENDING
    final_code: str = ""
    explanation: str = ""
    winner_source: str = ""
    total_iterations: int = 0
    attempts: list[TDDAttempt] = field(default_factory=list)
    duration_ms: float = 0.0
    error: str = ""
    skipped_racing: bool = False

    def to_dict(self) -> dict[str, object]:
        """To Dict.

        Returns:
            dict: The dict result.

        """
        return {
            "prompt": self.prompt,
            "status": self.status.value,
            "final_code": self.final_code,
            "explanation": self.explanation,
            "winner_source": self.winner_source,
            "total_iterations": self.total_iterations,
            "duration_ms": round(self.duration_ms, 1),
            "error": self.error,
            "skipped_racing": self.skipped_racing,
            "attempts": [
                {
                    "iteration": a.iteration,
                    "winner_source": a.winner_source,
                    "candidates": [
                        {
                            "source": c.source,
                            "passed": c.passed,
                            "exit_code": c.exit_code,
                            "duration_ms": round(c.duration_ms, 1),
                        }
                        for c in a.candidates
                    ],
                    "duration_ms": round(a.duration_ms, 1),
                }
                for a in self.attempts
            ],
        }


class OmniTDDEngine:
    """Omni-Resource Test-Driven Generation Engine.

    가용 가능한 모든 두뇌(로컬 모델, ChatGPT 웹, Gemini 앱 등)를 동시에 호출하여
    코드를 작성하고, 테스트를 통과한 최적의 코드를 선별(Racing & Synthesis)합니다.
    """

    def __init__(
        self,
        model_manager: object,
        coding_model: str = "qwen3.6:latest",
        max_iterations: int = 3,
        workspace_dir: str = "",
    ):
        """Initialize the OmniTDDEngine.

        Args:
            model_manager: ModelManager instance.
            coding_model (str): str coding model.
            max_iterations (int): int max iterations.
            workspace_dir (str): str workspace dir.

        """
        self.model_manager: object = model_manager
        self.coding_model: str = coding_model
        self.max_iterations: int = max_iterations
        self.workspace_dir: str = workspace_dir or os.path.join(
            os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            ),
            "tests",
            ".tdd_tmp",
        )
        self.brain_router: ExternalBrainRouter = ExternalBrainRouter()

    def _should_skip_racing(self, prompt: str) -> bool:
        """단순한 코딩 요청은 멀티모델 레이싱을 건너뛰고 로컬 모델만 사용합니다.

        Adaptive Mode: 토큰 수가 적고, 설명/작성/구현 등 단순 지시어만 포함된 경우
        외부 브레인 호출을 생략하여 10~15배 빠른 응답을 제공합니다.
        """
        token_count = len(re.findall(r"[\w가-힣]+", prompt))
        simple_indicators = {
            "작성",
            "만들어",
            "구현",
            "알려",
            "설명",
            "보여",
            "짜줘",
            "코드",
            "write",
            "create",
            "implement",
            "show",
        }
        has_simple = any(ind in prompt.lower() for ind in simple_indicators)
        # 30토큰 미만 + 단순 지시어 → 레이싱 불필요
        return token_count < 30 and has_simple

    def _resolve_coding_target(self) -> str:
        if self.coding_model != "qwen3.6:latest":
            return self.coding_model
        try:
            model_manager = cast(_ModelManagerLike, self.model_manager)
            target = model_manager.get_target_for_role("tdd", default_role="coding")
            if isinstance(target, str) and target:
                return target
        except Exception:
            logger.warning("TDD coding target resolution failed", exc_info=True)
        return self.coding_model

    async def run_tdd_loop(
        self,
        prompt: str,
        target_file_path: str | None = None,
        test_file_path: str | None = None,
    ) -> TDDReport:
        """Run tdd loop.

        Args:
            prompt (str): str prompt.
            target_file_path (str): str target file path.
            test_file_path (str): Optional externally generated pytest file.

        Returns:
            TDDReport: The tddreport result.

        """
        report = TDDReport(prompt=prompt)
        start_time = time.time()
        skip_racing = self._should_skip_racing(prompt)
        report.skipped_racing = skip_racing

        os.makedirs(self.workspace_dir, exist_ok=True)
        test_file = os.path.join(self.workspace_dir, "test_solution.py")

        current_test_code = ""
        # 에러 로그 풀 (각 소스별 에러를 저장하여 다음 라운드에 피드백)
        error_logs: dict[str, str] = {}

        try:
            for iteration in range(1, self.max_iterations + 1):
                report.total_iterations = iteration
                attempt_start = time.time()
                attempt = TDDAttempt(iteration=iteration, test_code="")

                logger.info(
                    "[OmniTDD] Iteration %s starting... (racing=%s)",
                    iteration,
                    "OFF" if skip_racing else "ON",
                )

                if iteration == 1:
                    report.status = TDDStatus.GENERATING
                    if test_file_path:
                        current_test_code = await asyncio.to_thread(
                            Path(test_file_path).read_text,
                            encoding="utf-8",
                        )
                    else:
                        _, current_test_code = await self._generate_local_baseline(prompt)
                    attempt.test_code = current_test_code

                    # 테스트 파일 기록
                    with open(test_file, "w", encoding="utf-8") as f:
                        test_code_to_write = current_test_code
                        if "import solution" not in test_code_to_write and "from solution" not in test_code_to_write:
                            test_code_to_write = "import solution\n\n" + test_code_to_write
                        _ = f.write(test_code_to_write)

                    # 2. Adaptive: 단순 요청이면 로컬만, 복잡하면 멀티모델 레이싱
                    if skip_racing:
                        candidates = await self._get_local_only_candidate(prompt)
                    else:
                        candidates = await self._get_initial_candidates(prompt)
                else:
                    report.status = TDDStatus.FIXING
                    attempt.test_code = current_test_code
                    # 2. 다중 모델 병렬 버그 픽스
                    candidates = await self._get_fixed_candidates(
                        prompt,
                        current_test_code,
                        error_logs,
                    )

                if not candidates:
                    raise Exception("모든 모델이 코드 생성을 실패했습니다.")

                report.status = TDDStatus.TESTING
                # 3. 샌드박스에서 각각 테스트 실행
                for cand in candidates:
                    await self._test_candidate(cand, test_file)

                attempt.candidates = candidates

                # 4. 결과 종합 (Synthesis)
                passed_candidates = [c for c in candidates if c.passed]

                if passed_candidates:
                    report.status = TDDStatus.PASSED
                    # 한 명만 통과했으면 그대로 우승, 여럿이면 심판이 결정
                    winner = await self._synthesize_results(passed_candidates, prompt)
                    attempt.winner_source = winner.source
                    report.winner_source = winner.source
                    report.final_code = winner.code
                    attempt.duration_ms = (time.time() - attempt_start) * 1000
                    report.attempts.append(attempt)
                    logger.info(
                        "[OmniTDD] Iteration %s Success! Winner: %s",
                        iteration,
                        winner.source,
                    )

                    # Response Reconstructor: 코드 + 한국어 설명 생성
                    report.explanation = await self._reconstruct_response(prompt, winner.code)

                    if target_file_path:
                        try:
                            os.makedirs(
                                os.path.dirname(os.path.abspath(target_file_path)),
                                exist_ok=True,
                            )
                            with open(target_file_path, "w", encoding="utf-8") as tf:
                                _ = tf.write(winner.code)
                            logger.info(
                                "[OmniTDD] Saved winning code to target path: %s",
                                target_file_path,
                            )
                        except Exception:
                            logger.exception(
                                "[OmniTDD] Failed to write target file %s",
                                target_file_path,
                            )

                    break
                else:
                    logger.warning("[OmniTDD] Iteration %s failed for all candidates.", iteration)
                    # 다음 라운드 피드백용 에러 저장
                    for c in candidates:
                        error_logs[c.source] = (
                            f"Code:\n{c.code}\nExit code: {c.exit_code}\nSTDOUT:\n{c.stdout}\nSTDERR:\n{c.stderr}"
                        )

                    attempt.duration_ms = (time.time() - attempt_start) * 1000
                    report.attempts.append(attempt)

            if report.status != TDDStatus.PASSED:
                report.status = TDDStatus.FAILED
                report.error = "Max iterations reached. All models failed to pass the tests."

        except Exception as e:
            logger.exception("[OmniTDD] Error")
            report.status = TDDStatus.FAILED
            report.error = str(e)
        finally:
            report.duration_ms = (time.time() - start_time) * 1000
            # Clean up
            shutil.rmtree(self.workspace_dir, ignore_errors=True)

        return report

    async def _test_candidate(self, cand: TDDCandidate, test_file_path: str) -> None:
        """특정 후보의 코드를 solution.py로 저장하고 pytest를 실행합니다."""
        main_file = os.path.join(self.workspace_dir, "solution.py")
        start = time.time()

        with open(main_file, "w", encoding="utf-8") as f:
            _ = f.write(cand.code)

        cmd = ["python3", "-m", "pytest", test_file_path, "-v", "--tb=short"]
        try:
            result = await asyncio.to_thread(
                run_sandboxed_argv,
                cmd,
                cwd=self.workspace_dir,
                timeout=60,
            )
            cand.stdout = result.stdout
            cand.stderr = result.stderr or result.error
            cand.exit_code = result.return_code
            cand.passed = cand.exit_code == 0
        except Exception as e:
            logger.exception("Unhandled exception")
            cand.exit_code = -1
            cand.stderr = str(e)
            cand.passed = False

        cand.duration_ms = (time.time() - start) * 1000

    async def _generate_local_baseline(self, prompt: str) -> tuple[str, str]:
        """로컬 모델로부터 기준 테스트 코드(pytest)를 추출합니다."""
        sys_prompt = (
            "You are an expert Test-Driven Python Engineer. "
            "Given a requirement, you must produce BOTH the implementation code AND pytest test code. "
            "Output ONLY a single raw JSON object (no markdown fences, no explanations before or after). "
            'The JSON must have exactly two keys: "code" (the implementation) and "test_code" (the pytest tests). '
            "The test_code must import from 'solution' module (e.g. 'from solution import ...'). "
            'Example output format: {"code": "def add(a,b):\\n    return a+b", "test_code": "from solution'
            'import add\\n\\ndef test_add():\\n    assert add(1,2)==3"}'
        )
        user_prompt = f"Requirement:\n{prompt}\n\nReturn only the JSON object:"

        content = await self._call_llm(sys_prompt, user_prompt)
        # JSON 추출: 마크다운 펜스 안에 있을 수도 있고 바로 있을 수도 있음
        # 1차: 가장 바깥쪽 { ... } 블록 추출
        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if json_match:
            try:
                data = cast(dict[str, object], json.loads(json_match.group()))
                code = data.get("code", "")
                test_code = data.get("test_code", "")
                return code if isinstance(code, str) else "", test_code if isinstance(test_code, str) else ""
            except json.JSONDecodeError:
                # 2차: 이스케이프 문제 → 코드 블록에서 분리 시도
                code_blocks = re.findall(r"```(?:python)?\s*(.*?)\s*```", content, re.DOTALL)
                if len(code_blocks) >= 2:
                    return code_blocks[0], code_blocks[1]
                elif len(code_blocks) == 1:
                    return code_blocks[0], ""
        return "", ""

    async def _get_local_only_candidate(self, prompt: str) -> list[TDDCandidate]:
        """Adaptive Mode: 로컬 모델만으로 단독 코드 생성 (레이싱 스킵)."""
        logger.info("[OmniTDD] Adaptive mode — local model only (skip racing)")
        sys = "You are an expert Python engineer. Provide only the raw python code. No markdown formatting, no explanations."  # noqa: E501
        res = await self._call_llm(sys, f"Requirement:\n{prompt}")
        code = self._extract_python_code(res)
        if code:
            return [TDDCandidate(source=f"local({self.coding_model})", code=code)]
        return []

    async def _get_initial_candidates(self, prompt: str) -> list[TDDCandidate]:
        """모든 가용 두뇌에 코딩을 요청합니다."""
        logger.info("[OmniTDD] Racing all available models...")
        tasks: list[Awaitable[object]] = []

        # 1. 로컬 모델
        async def local_task():
            sys = "You are an expert Python engineer. Provide only the raw python code. No markdown formatting, no explanations."  # noqa: E501
            res = await self._call_llm(sys, f"Requirement:\n{prompt}")
            code = self._extract_python_code(res)
            return TDDCandidate(source=f"local({self.coding_model})", code=code)

        tasks.append(local_task())

        # 2. 외부 두뇌 (ChatGPT, Gemini 등)
        ext_prompt = (
            "You are an expert Python engineer. Implement the following requirement. "
            "Provide only the raw python code without markdown formatting or explanations.\n\n"
            f"Requirement:\n{prompt}"
        )

        async def external_task() -> list[TDDCandidate]:
            try:
                resp = await self.brain_router.send(ext_prompt, strategy="compare")
                cands: list[TDDCandidate] = []
                # Compare strategy returns a combined markdown report. We must parse it.
                if resp.success and "## 🧠 외부 두뇌 비교 결과" in resp.text:
                    blocks = resp.text.split("### [")
                    for block in blocks[1:]:
                        source_end = block.find("]")
                        if source_end != -1:
                            source = block[:source_end]
                            content = block[source_end + 1 :].split("---")[0].strip()
                            code = self._extract_python_code(content)
                            if code:
                                cands.append(TDDCandidate(source=source, code=code))
                return cands
            except Exception:
                logger.exception("[OmniTDD] External brain task failed")
                return []

        tasks.append(external_task())

        results = await asyncio.gather(*tasks, return_exceptions=True)

        candidates: list[TDDCandidate] = []
        for result in results:
            if isinstance(result, TDDCandidate) and result.code:
                candidates.append(result)
            elif isinstance(result, list):
                for candidate in cast(list[object], result):
                    if isinstance(candidate, TDDCandidate) and candidate.code:
                        candidates.append(candidate)

        logger.info("[OmniTDD] Received %s candidates.", len(candidates))
        return candidates

    async def _get_fixed_candidates(
        self,
        prompt: str,
        test_code: str,
        error_logs: dict[str, str],
    ) -> list[TDDCandidate]:
        """실패한 각 두뇌에 자신의 에러 로그를 주어 버그 픽스를 요청합니다."""
        logger.info("[OmniTDD] Requesting bug fixes from all models...")
        tasks: list[Awaitable[TDDCandidate | None]] = []

        # 로컬 모델 픽스
        local_source = f"local({self.coding_model})"
        if local_source in error_logs:

            async def local_fix():
                sys = (
                    "You are an expert Python engineer. The previous code failed the tests. "
                    "Provide only the raw fixed python code. No markdown formatting."
                )
                user = (
                    f"Requirement:\n{prompt}\n\nTests:\n{test_code}\n\n"
                    f"My Previous Attempt & Error:\n{error_logs[local_source]}\n\nPlease fix the code."
                )
                res = await self._call_llm(sys, user)
                return TDDCandidate(source=local_source, code=self._extract_python_code(res))

            tasks.append(local_fix())

        # 외부 두뇌 픽스
        for source, error in error_logs.items():
            if source.startswith("local"):
                continue

            async def ext_fix(src: str = source, err: str = error) -> TDDCandidate | None:
                ext_prompt = (
                    "You are an expert Python engineer. The previous code failed. "
                    "Provide only the raw fixed python code. No markdown formatting.\n\n"
                    f"Requirement:\n{prompt}\n\nTests:\n{test_code}\n\n"
                    f"My Previous Attempt & Error:\n{err}"
                )
                resp = await self.brain_router.send(ext_prompt, target=src)
                if resp.success:
                    return TDDCandidate(source=src, code=self._extract_python_code(resp.text))
                return None

            tasks.append(ext_fix())

        results = await asyncio.gather(*tasks, return_exceptions=True)
        candidates = [r for r in results if isinstance(r, TDDCandidate) and r.code]
        logger.info("[OmniTDD] Received %s fixed candidates.", len(candidates))
        return candidates

    async def _synthesize_results(
        self,
        passed_candidates: list[TDDCandidate],
        prompt: str,
    ) -> TDDCandidate:
        """통과한 여러 후보 중 최고의 코드를 로컬 심판 모델이 채택합니다."""
        if len(passed_candidates) == 1:
            return passed_candidates[0]

        logger.info("[OmniTDD] Synthesizing %s passing candidates...", len(passed_candidates))
        sys_prompt = "You are a senior principal engineer evaluating multiple working implementations."
        user_prompt = f"Requirement: {prompt}\n\n"

        for i, c in enumerate(passed_candidates):
            user_prompt += f"Implementation {i + 1} (Source: {c.source}):\n```python\n{c.code}\n```\n\n"

        user_prompt += (
            "All implementations pass the tests. Choose the best one based on performance, "
            "readability, security, and thread-safety. "
            "Reply strictly with the integer index of the best implementation (e.g., '1' or '2')."
        )

        choice_str = await self._call_llm(sys_prompt, user_prompt)

        match = re.search(r"\d+", choice_str)
        if match:
            idx = int(match.group()) - 1
            if 0 <= idx < len(passed_candidates):
                return passed_candidates[idx]

        # 기본값으로 가장 짧은 코드(또는 첫 번째) 선택
        return passed_candidates[0]

    async def _reconstruct_response(self, original_prompt: str, winning_code: str) -> str:
        """Response Reconstructor: 우승 코드를 기반으로 완전한 한국어 응답을 생성합니다.

        TDD 엔진의 핵심 품질 게이트. 코드-only 응답을
        '분석 → 코드 → 설명(복잡도/비교)' 3단 구조로 재구성합니다.
        """
        sys_prompt = (
            "당신은 시니어 소프트웨어 엔지니어이자 기술 교육자입니다. "
            "아래의 '사용자 원본 질문'과 '검증 완료된 구현물'을 바탕으로 "
            "완전한 한국어 기술 응답을 작성하세요.\n\n"
            "반드시 다음 3단 구조를 지키세요:\n"
            "### 🔍 분석\n사용자 요구사항의 핵심 파악 (2~3문장)\n\n"
            "### 💻 구현 코드\n검증 완료된 코드를 적절한 언어(python, html 등)의 코드 블록으로 제시\n\n"
            "### 📊 설명\n"
            "- 각 방법/함수의 동작 원리를 간결하게 설명\n"
            "- 여러 방법 비교 시 비교 표(마크다운 테이블) 포함\n"
            "- '💡 팁:' 섹션으로 실무 활용 팁 제공\n\n"
            "[CRITICAL RULES]\n"
            "1. 반드시 100% 자연스러운 한국어(Korean)로만 작성하세요.\n"
            "2. 절대로 일본어(日本語), 중국어(中文) 문자를 섞어 쓰지 마세요 (품질 게이트 탈락의 원인이 됩니다).\n"
            "3. 영어는 변수명이나 고유 명사에만 사용하세요.\n"
            "4. 같은 문단이나 문장을 2회 이상 반복하지 마세요.\n"
            "5. 불필요한 'Implementation Plan' 등의 영어 제목을 생성하지 마세요."
        )
        user_prompt = f"사용자 원본 질문:\n{original_prompt}\n\n검증 완료된 구현물:\n```\n{winning_code}\n```"
        try:
            explanation = await self._call_llm(sys_prompt, user_prompt)
            if explanation and len(explanation.strip()) > 50:
                quality = QualityGate(max_retries=0).evaluate(
                    "coding",
                    original_prompt,
                    explanation,
                )
                if quality.grade in (QualityGrade.A, QualityGrade.B):
                    return explanation.strip()
                logger.warning(
                    "[OmniTDD] Reconstructed response failed quality gate: %s",
                    ", ".join(quality.issues),
                )
        except Exception:
            logger.exception("[OmniTDD] Response reconstruction failed")
        return self._fallback_reconstructed_response(original_prompt, winning_code)

    def _fallback_reconstructed_response(self, original_prompt: str, winning_code: str) -> str:
        """LLM 재구성이 실패해도 코드-only 응답을 피하는 결정론적 폴백."""
        prompt_lower = original_prompt.lower()
        complexity_requested = bool(
            re.search(
                r"(복잡도|big-?o|성능|시간\s*복잡도|공간\s*복잡도|" + r"time complexity|space complexity)",
                prompt_lower,
            ),
        )
        comparison_requested = bool(
            re.search(r"(비교|차이|장단점|compare|comparison|trade-?off)", prompt_lower),
        )
        gcd_requested = "gcd" in prompt_lower or "최대공약수" in original_prompt

        if complexity_requested and gcd_requested:
            complexity_note = (
                "- 시간복잡도: 유클리드 호제법은 `O(log(min(a, b)))`입니다.\n"
                "- 단순 감소/탐색형 반복 구현은 최악의 경우 `O(min(a, b))`까지 커질 수 있습니다.\n"
                "- 반복문 기반 구현의 공간복잡도는 보통 `O(1)`입니다."
            )
        elif complexity_requested:
            complexity_note = (
                "- 시간복잡도: 선형 탐색 구조는 보통 `O(n)`, 입력을 절반씩 줄이는 구조는 `O(log n)`입니다.\n"
                "- 공간복잡도는 추가 자료구조 사용 여부를 기준으로 산정해야 합니다."
            )
        else:
            complexity_note = "- 검증 완료된 코드를 기준으로 입력, 출력, 예외 조건을 함께 확인하세요."

        comparison_table = ""
        if comparison_requested:
            if gcd_requested:
                comparison_table = (
                    "\n\n| 방법 | 시간복잡도 | 공간복잡도 | 특징 |\n"
                    "| --- | --- | --- | --- |\n"
                    "| 유클리드 호제법 | `O(log(min(a, b)))` | `O(1)` | 가장 효율적인 일반 해법 |\n"
                    "| 단순 반복 탐색 | `O(min(a, b))` | `O(1)` | 이해하기 쉽지만 큰 입력에서 느림 |"
                )
            else:
                comparison_table = (
                    "\n\n| 관점 | 확인 기준 | 설명 |\n"
                    "| --- | --- | --- |\n"
                    "| 성능 | Big-O | 입력 크기 증가에 따른 실행 시간 변화 |\n"
                    "| 안정성 | 테스트 통과 여부 | 생성 코드가 샌드박스 검증을 통과했는지 |\n"
                    "| 유지보수성 | 구조 | 함수 분리와 가독성 수준 |"
                )

        return (
            "### 🔍 분석\n\n"
            "요청은 검증 가능한 코드를 작성하고, 그 코드가 왜 적절한지 설명하는 것입니다. "
            "아래 코드는 TDD 루프에서 검증을 통과한 최종 구현을 그대로 제시합니다.\n\n"
            "### 💻 구현 코드\n\n"
            f"```\n{winning_code}\n```\n\n"
            "### 📊 설명\n\n"
            f"{complexity_note}"
            f"{comparison_table}\n\n"
            "💡 팁: 실제 프로젝트에 반영할 때는 정상 입력뿐 아니라 0, 음수, 같은 값, 매우 큰 값 같은 "
            "경계 조건을 테스트에 포함하면 출력 품질과 런타임 안정성을 함께 높일 수 있습니다."
        )

    def _extract_python_code(self, text: str) -> str:
        """마크다운이나 불필요한 텍스트에서 파이썬 코드만 추출합니다."""
        # 마크다운 코드 블록 찾기
        matches = cast(list[str], re.findall(r"```(?:python)?\s*(.*?)\s*```", text, re.DOTALL))
        if matches:
            # 가장 긴 블록 반환 (보통 그게 정답)
            longest = ""
            for match in matches:
                if len(match) > len(longest):
                    longest = match
            return longest
        return text.strip()

    async def _call_llm(self, sys_prompt: str, user_prompt: str) -> str:
        """ModelManager를 사용하여 메인 코디네이터(로컬/Gemini 등) 모델을 호출합니다."""
        combined_prompt = f"{sys_prompt}\n\n{user_prompt}"
        try:
            model_manager = cast(_ModelManagerLike, self.model_manager)
            return await asyncio.to_thread(
                model_manager.generate,
                prompt=combined_prompt,
                target=self._resolve_coding_target(),
                temperature=0.1,
            )
        except Exception as e:
            logger.error("LLM Generation error in OmniTDD: %s", str(e))
            return ""
