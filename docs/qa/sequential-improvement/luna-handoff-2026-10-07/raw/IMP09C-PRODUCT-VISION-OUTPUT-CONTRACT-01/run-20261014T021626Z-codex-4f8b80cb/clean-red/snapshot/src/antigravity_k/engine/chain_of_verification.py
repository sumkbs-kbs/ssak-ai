"""Ssak-Ai: Chain-of-Verification (CoV) 자기검증 루프.

========================================================
모델이 생성한 답변을 동일 모델의 별도 호출로 검증하여
복잡한 추론에서의 환각과 논리적 오류를 자가 수정합니다.

격차 해소 대상: 추론 깊이 및 정확도
"""

import ast
import logging
import re
import time
from collections.abc import Callable
from typing import Final

from .chain_of_verification_models import (
    CoVTrace,
    VerificationResult,
    estimate_complexity,
)

logger = logging.getLogger("antigravity_k.chain_of_verification")


CODE_BLOCK_PATTERN: Final[re.Pattern[str]] = re.compile(r"```python\n(.*?)```", re.DOTALL)


class ChainOfVerification:
    """Generate → Verify → Revise 3-pass 자기검증 파이프라인.

    단순 질문은 1-pass로 통과시키고,
    복잡한 코드 생성/아키텍처 설계만 선택적으로 3-pass를 적용합니다.
    """

    def __init__(
        self,
        generate_fn: Callable[[str], str] | None = None,
        min_response_length: int = 200,
        complexity_threshold: float = 0.4,
        max_revise_iterations: int = 1,
    ) -> None:
        """Args:
        generate_fn: 모델 호출 함수 (prompt: str) -> str
        min_response_length: CoV를 적용할 최소 응답 길이
        complexity_threshold: 복잡도 점수 임계값 (0.0~1.0)
        max_revise_iterations: revise→verify 폐루프 반복 한계 (기본 1)

        """
        self._generate_fn: Callable[[str], str] | None = generate_fn
        self.min_response_length: int = min_response_length
        self.complexity_threshold: float = complexity_threshold
        self.max_revise_iterations: int = max_revise_iterations

    def set_generate_fn(self, fn: Callable[[str], str]) -> None:
        """모델 호출 함수를 설정합니다."""
        self._generate_fn = fn

    def should_verify(self, task: str, response: str) -> bool:
        """이 응답에 CoV 검증이 필요한지 판단합니다."""
        # 너무 짧은 응답은 스킵
        if len(response) < self.min_response_length:
            return False

        # 복잡도 점수 계산
        score = self.estimate_complexity(task)
        return score >= self.complexity_threshold

    def estimate_complexity(self, task: str) -> float:
        """작업의 복잡도를 모듈 수준 estimate_complexity에 위임한다."""
        return estimate_complexity(task)

    def verify(self, task: str, response: str) -> VerificationResult:
        """생성된 응답을 검증합니다 (Pass 2)."""
        issues_found = self._rule_based_check(task, response)
        suggested_fixes: list[str] = []
        verification_reasoning = ""

        if self._generate_fn and len(response) >= self.min_response_length:
            llm_result = self._llm_verify(task, response)
            if llm_result:
                issues_found.extend(llm_result.issues_found)
                suggested_fixes.extend(llm_result.suggested_fixes)
                verification_reasoning = llm_result.verification_reasoning

        issue_count = len(issues_found)
        if issue_count == 0:
            severity = "none"
            passed = True
        elif issue_count <= 2:
            severity = "low"
            passed = True
        elif issue_count <= 4:
            severity = "medium"
            passed = False
        else:
            severity = "high"
            passed = False

        return VerificationResult(
            issues_found=issues_found,
            severity=severity,
            suggested_fixes=suggested_fixes,
            verification_reasoning=verification_reasoning,
            passed=passed,
        )

    def revise(self, task: str, response: str, verification: VerificationResult) -> str:
        """검증 결과를 바탕으로 응답을 수정합니다 (Pass 3)."""
        if verification.passed or not self._generate_fn:
            return response

        issues_text = "\n".join(f"- {issue}" for issue in verification.issues_found)
        fixes_text = "\n".join(f"- {fix}" for fix in verification.suggested_fixes)

        revise_prompt = (
            "아래는 사용자의 질문에 대한 이전 답변입니다. "
            "검증 과정에서 다음 문제점이 발견되었습니다.\n\n"
            f"## 원래 질문\n{task}\n\n"
            f"## 이전 답변\n{response[:3000]}\n\n"
            f"## 발견된 문제\n{issues_text}\n\n"
        )

        if fixes_text:
            revise_prompt += f"## 제안된 수정 방향\n{fixes_text}\n\n"

        revise_prompt += (
            "위 문제를 모두 수정하여 개선된 답변을 작성해주세요. "
            "기존 답변에서 올바른 부분은 유지하고, 문제가 있는 부분만 수정하세요."
        )

        try:
            revised = self._generate_fn(revise_prompt)
            if revised and len(revised.strip()) > 50:
                return revised
        except (OSError, RuntimeError, TypeError, ValueError, TimeoutError):
            logger.exception("[CoV] Revision failed")

        return response  # 수정 실패 시 원본 유지

    def run(self, task: str, response: str) -> CoVTrace:
        """전체 CoV 파이프라인을 실행합니다.

        Returns:
            CoVTrace with original, verification, and revised response

        """
        start = time.time()

        if not self.should_verify(task, response):
            return CoVTrace(
                original_response=response,
                revised_response=response,
                total_latency_ms=(time.time() - start) * 1000,
                skipped=True,
                skip_reason="Low complexity or short response",
            )

        verification = self.verify(task, response)
        total_passes = 2

        current = response
        current_verification = verification
        if not verification.passed:
            for it in range(self.max_revise_iterations):
                revised = self.revise(task, current, current_verification)
                total_passes += 1
                if revised == current:
                    break
                current = revised
                if self.max_revise_iterations > 1:
                    re_verification = self.verify(task, current)
                    total_passes += 1
                    if re_verification.passed:
                        current_verification = re_verification
                        logger.info("[CoV] revise 루프 %s회차 검증 통과", it + 1)
                        break
                    current_verification = re_verification
                    logger.debug(
                        "[CoV] revise 루프 %s회차 재검증 실패 (issues=%s)",
                        it + 1,
                        len(re_verification.issues_found),
                    )
        latency_ms = (time.time() - start) * 1000
        logger.info(
            "[CoV] %s-pass complete. Issues: %s, Severity: %s, Latency: %sms",
            total_passes,
            len(current_verification.issues_found),
            current_verification.severity,
            latency_ms,
        )

        return CoVTrace(
            original_response=response,
            verification_result=current_verification,
            revised_response=current,
            total_passes=total_passes,
            total_latency_ms=latency_ms,
        )

    # ─── 규칙 기반 빠른 검증 ──────────────────────────────────

    def _rule_based_check(self, task: str, response: str) -> list[str]:
        """LLM 호출 없이 규칙 기반으로 빠르게 검증합니다."""
        _ = task
        issues: list[str] = []

        for i, match in enumerate(CODE_BLOCK_PATTERN.finditer(response)):
            code = match.group(1)
            try:
                _ = ast.parse(code)
            except SyntaxError as e:
                issues.append(f"코드 블록 #{i + 1}에 구문 오류: {e.msg} (line {e.lineno})")

        # 2. 자기 모순 감지 (동일 답변 내 상반된 주장)
        response_lower = response.lower()
        contradiction_pairs = [
            ("동기", "비동기"),
            ("O(1)", "O(n)"),
            ("thread-safe", "not thread-safe"),
            ("가능합니다", "불가능합니다"),
        ]
        for a, b in contradiction_pairs:
            if a.lower() in response_lower and b.lower() in response_lower:
                # 같은 문단에서 모순이면 문제
                for para in response.split("\n\n"):
                    if a.lower() in para.lower() and b.lower() in para.lower():
                        issues.append(f"자기 모순 감지: '{a}'와 '{b}'가 같은 문단에 동시 존재")
                        break

        # 3. 과도한 반복 감지
        sentences = [s.strip() for s in response.split(".") if len(s.strip()) > 20]
        seen: set[str] = set()
        for s in sentences:
            normalized = s.lower().strip()
            if normalized in seen:
                issues.append(f"반복 문장 감지: '{s[:50]}...'")
                break
            seen.add(normalized)

        return issues

    def _llm_verify(self, task: str, response: str) -> VerificationResult | None:
        """LLM을 호출하여 심층 검증합니다."""
        if not self._generate_fn:
            return None

        verify_prompt = (
            "당신은 엄격한 테크니컬 리뷰어입니다. 아래 답변에서 다음 사항들을 검증해주세요:\n"
            "1. 사실 오류 (부정확한 정보)\n"
            "2. 의미론적/논리적 모순 (앞뒤가 안 맞는 주장)\n"
            "3. 코드 버그 및 구문 오류\n"
            "4. 보안 취약점\n\n"
            f"## 원본 질문\n{task[:500]}\n\n"
            f"## 검증할 답변\n{response[:3000]}\n\n"
            "발견된 문제점만 명확하게 번호 목록으로 작성하세요.\n"
            "문제가 없다면 오직 '문제 없음'이라고만 출력하세요.\n"
            "문제를 지적할 때는 어떻게 수정해야 하는지도 함께 제안해주세요."
        )

        try:
            result_text = self._generate_fn(verify_prompt)
            if not result_text:
                return None

            if "문제 없음" in result_text or "no issues" in result_text.lower():
                return VerificationResult(verification_reasoning=result_text)

            issues_found: list[str] = []
            lines = result_text.split("\n")
            for line in lines:
                stripped = line.strip()
                if re.match(r"^\d+[\.\)]\s", stripped):
                    issue = re.sub(r"^\d+[\.\)]\s*", "", stripped)
                    if len(issue) > 10:
                        issues_found.append(issue)

            return VerificationResult(issues_found=issues_found, verification_reasoning=result_text)

        except (OSError, RuntimeError, TypeError, ValueError, TimeoutError):
            logger.exception("[CoV] LLM verification failed")
            return None
