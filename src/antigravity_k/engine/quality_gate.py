"""Ssak-Ai: 품질 검증 게이트 (QualityGate).

=============================================
E-5: 에이전트 출력물의 품질을 자가 평가하고,
기준 미달 시 재시도 루프를 트리거합니다.
"""

import ast
import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Never

logger = logging.getLogger(__name__)


def _reject_json_constant(value: str) -> Never:
    raise json.JSONDecodeError("Non-finite numeric constant", value, 0)


class QualityGrade(Enum):
    """Qualitygrade.

    Bases: Enum
    """

    A = "excellent"
    B = "good"
    C = "retry"
    F = "fail"


@dataclass
class QualityScore:
    """Multi-axis quality assessment score (correctness, clarity, completeness, etc.)."""

    grade: QualityGrade
    score: float
    feedback: str
    user_message: str
    should_retry: bool
    issues: list[str]


class QualityGate:
    """에이전트 출력 품질 자동 평가. A/B는 통과, C/F는 재시도."""

    max_retries: int
    _retry_count: int
    _verify_fn: Callable[[str], str] | None

    def __init__(self, max_retries: int = 1, verify_fn: Callable[[str], str] | None = None):
        """Args:
        max_retries: 최대 재시도 횟수
        verify_fn: LLM 기반 자가검증 함수 (prompt -> str).
                   경량 모델(예: qwen3:4b)로 의미론적 품질 검증을 수행.
                   None이면 LLM 검증을 건너뜁니다.

        """
        self.max_retries = max_retries
        self._retry_count = 0
        self._verify_fn = verify_fn

    def evaluate(
        self, task_type: str, user_request: str, agent_output: str, execution_mode: str | None = None
    ) -> QualityScore:
        """Evaluate.

        Args:
            task_type (str): str task type.
            user_request (str): str user request.
            agent_output (str): str agent output.
            execution_mode (str | None): 실행 모드 ("plan", "build", "interactive", None)
                                         BUILD 모드에서는 plan 체크를 건너뜁니다.

        Returns:
            QualityScore: The qualityscore result.

        """
        task_type = task_type.lower()
        if not agent_output or not agent_output.strip():
            return QualityScore(
                QualityGrade.F,
                0.0,
                "출력이 비어 있습니다.",
                "⚠️ 응답 없음",
                True,
                ["empty"],
            )

        issues: list[str] = []
        score = 1.0

        if task_type in ("code", "coding", "complex", "complex_step"):
            s, i = self._check_code(agent_output)
            score *= s
            issues.extend(i)

        s, i = self._check_output_contract(user_request, agent_output, task_type, execution_mode)
        score *= s
        issues.extend(i)

        s, i = self._check_safety(agent_output)
        score *= s
        issues.extend(i)

        s, i = self._check_planning_mode(user_request, agent_output, task_type, execution_mode)
        score *= s
        issues.extend(i)

        s, i = self._check_repetition(agent_output)
        score *= s
        issues.extend(i)

        s, i = self._check_internal_tag_leak(agent_output)
        score *= s
        issues.extend(i)

        s, i = self._check_language_contamination(agent_output)
        score *= s
        issues.extend(i)

        s, i = self._check_korean_readability(agent_output)
        score *= s
        issues.extend(i)

        s, i = self._check_current_info_grounding(user_request, agent_output)
        score *= s
        issues.extend(i)

        s, i = self._check_comparison_table(user_request, agent_output)
        score *= s
        issues.extend(i)

        s, i = self._check_information_density(agent_output)
        score *= s
        issues.extend(i)

        s, i = self._check_antigravity_markdown_standards(agent_output)
        score *= s
        issues.extend(i)

        s, i = self._check_github_alerts(agent_output)
        score *= s
        issues.extend(i)

        s, i = self._check_artifact_format(agent_output)
        score *= s
        issues.extend(i)

        # ─── LLM 기반 자가 검증 (Semantic Self-Verification) ───
        # 정규식 기반 점수가 통과권(B 이상)일 때만 LLM 검증 실행하여 비용 절약
        verify_fn = self._verify_fn
        if verify_fn and score >= 0.6:
            llm_score, llm_issues = self._llm_self_verify(user_request, agent_output, task_type)
            score *= llm_score
            issues.extend(llm_issues)

        grade = (
            QualityGrade.A
            if score >= 0.8
            else (QualityGrade.B if score >= 0.6 else QualityGrade.C if score >= 0.3 else QualityGrade.F)
        )
        should_retry = grade in (QualityGrade.C, QualityGrade.F) and self._retry_count < self.max_retries

        feedback = ""
        if grade in (QualityGrade.C, QualityGrade.F):
            feedback = "[QUALITY GATE] 품질 미달. 문제: " + "; ".join(issues) + ". 개선하세요."

        user_msg = "" if grade == QualityGrade.A else f"📊 *품질: {grade.value} ({score:.0%})*"
        if should_retry:
            user_msg = f"🔄 *품질 미달 ({score:.0%}) — 자동 개선 중...*"

        return QualityScore(grade, round(score, 2), feedback, user_msg, should_retry, issues)

    def mark_retry(self):
        """Mark Retry."""
        self._retry_count += 1

    def reset(self):
        """Reset accumulated quality gate statistics."""
        self._retry_count = 0

    def _llm_self_verify(self, user_request: str, agent_output: str, task_type: str) -> tuple[float, list[str]]:
        """경량 LLM으로 응답의 의미론적 품질을 검증합니다.

        연구 근거: Self-RAG, Corrective RAG (2024-2025)

        Returns:
            (score_multiplier: float, issues: list[str])

        """
        try:
            _ = task_type
            verify_fn = self._verify_fn
            if verify_fn is None:
                return 1.0, []
            verify_prompt = (
                "[ROLE]\n당신은 AI 응답 품질 검증관입니다.\n\n"
                "[TASK]\n아래의 사용자 질문과 AI 응답을 비교하여 품질을 평가하세요.\n"
                "다음 3가지 항목을 각각 1~5점으로 채점하고, "
                "총점(15점 만점)을 마지막 줄에 '총점: N' 형식으로 출력하세요.\n\n"
                "1. 정확성 — 질문에 정확히 답했는가?\n"
                "2. 완결성 — 빠진 핵심 정보 없이 충분한가?\n"
                "3. 간결성 — 불필요한 반복이나 사족 없이 핵심만 전달했는가?\n\n"
                f"[사용자 질문]\n{user_request[:300]}\n\n"
                f"[AI 응답]\n{agent_output[:800]}\n\n"
                "채점:"
            )

            result = verify_fn(verify_prompt)
            if not result:
                return 1.0, []

            # "총점: N" 패턴 추출
            import re

            match = re.search(r"총점[:\s]*(\d+)", result)
            if match:
                total = int(match.group(1))
                # 15점 만점 → 0.0~1.0 스케일링 (7점 미만이면 감점)
                if total >= 12:
                    return 1.0, []
                elif total >= 9:
                    return 0.9, [f"LLM검증: 중간 품질 ({total}/15점)"]
                elif total >= 7:
                    return 0.75, [f"LLM검증: 미흡 ({total}/15점)"]
                else:
                    return 0.5, [f"LLM검증: 심각한 품질 문제 ({total}/15점)"]

            return 1.0, []  # 파싱 실패 시 감점하지 않음

        except Exception:
            logger.exception("LLM self-verification failed")
            return 1.0, []  # 검증 실패 시 패스스루

    def _check_code(self, output: str) -> tuple[float, list[str]]:
        score = 1.0
        issues: list[str] = []
        blocks: list[str] = re.findall(r"```python\n(.*?)```", output, re.DOTALL)
        for i, block in enumerate(blocks):
            try:
                _ = ast.parse(block)
            except SyntaxError as e:
                score *= 0.5
                issues.append(f"코드블록{i + 1} 구문오류: {e.msg}")
            if "..." in block or "NotImplemented" in block:
                score *= 0.8
                issues.append(f"코드블록{i + 1} 미완성")
        return score, issues

    def _check_output_contract(
        self, request: str, output: str, task_type: str, execution_mode: str | None = None
    ) -> tuple[float, list[str]]:
        """Codex/Claude 수준 응답 형식 계약을 휴리스틱으로 검증합니다.

        Args:
            request: 사용자 요청
            output: 에이전트 출력
            task_type: 태스크 유형
            execution_mode: 실행 모드 ("plan", "build", "interactive", None)
                           PLAN 모드에서는 코드 블록 체크를 건너뜁니다.
        """
        score = 1.0
        issues: list[str] = []
        request_lower = request.lower()
        code_only_requested = bool(re.search(r"(코드만|code\s+only|only\s+code)", request_lower))
        source_requested = code_only_requested or bool(
            re.search(
                r"(?:^|[.!?\n]\s*|\b(?:and|then)\s+)(?:(?:please|can you|could you|would you)\s+)?"
                + r"(?:write|implement|create|generate|build|make|provide|show|give(?:\s+me)?)\s+"
                + r"(?:(?:a|an|the|some|new|complete|working|python|javascript|typescript)\s+){0,4}"
                + r"(?:source(?:\s+code)?|code|implementation|(?:\w+\s+)?(?:function|algorithm|script|program))\b"
                + r"(?!\s+(?:summary|description|explanation|purpose|result|output)\b|['’]s\b)|"
                + r"(?:코드|함수|알고리즘|스크립트|프로그램)(?:를|을)?\s*(?:(?:새로|직접|다시)\s+)?"
                + r"(?:작성(?:해|하)|구현(?:해|하)|만들(?:어|어줘)|짜(?:줘|라)|보여(?:줘|주)|제공(?:해|하))",
                request_lower,
            ),
        )
        json_only = bool(
            re.search(
                r"\bonly(?:\s+\w+){0,3}\s+json\b|\bjson\s+only\b|json(?:으로|\s*형식(?:으로)?)?\s*만",
                request_lower,
            )
        )
        number_only = bool(
            re.search(
                r"\bonly(?:\s+\w+){0,4}\s+(?:number|integer|decimal)\b|"
                + r"\b(?:number|integer|decimal)\s+only\b|(?:숫자|정수|소수)\s*(?:하나|한\s*개|1\s*개)?\s*만",
                request_lower,
            )
        )
        if json_only and not source_requested:
            try:
                json.loads(output, parse_constant=_reject_json_constant)
            except json.JSONDecodeError:
                return 0.3, ["요청된 JSON 형식 위반"]
            return score, issues
        if number_only and not source_requested:
            integer_only = bool(
                re.search(
                    r"\bonly(?:\s+\w+){0,4}\s+integer\b|\binteger\s+only\b|" + r"정수\s*(?:하나|한\s*개|1\s*개)?\s*만",
                    request_lower,
                )
            )
            number_pattern = r"[+-]?\d+" if integer_only else r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?"
            if not re.fullmatch(number_pattern, output.strip()):
                return 0.3, ["요청된 단일 숫자 형식 위반"]
            return score, issues

        # PLAN 모드: 코드 블록 체크 건너뜀 (Phase 1 D5)
        if execution_mode == "plan" or task_type == "search":
            return score, issues

        explanation_requested = bool(
            re.search(r"\b(?:explain|describe|what|why|how|purpose)\b|설명|목적|역할|반환값|무엇", request_lower)
        )
        asks_for_code = source_requested or (
            task_type in ("code", "coding", "complex", "complex_step") and not explanation_requested
        )
        if not asks_for_code:
            return score, issues

        code_blocks = re.findall(r"```(?:\w+)?\s*.*?```", output, re.DOTALL)
        prose = re.sub(r"```(?:\w+)?\s*.*?```", "", output, flags=re.DOTALL).strip()
        has_korean_prose = bool(re.search(r"[가-힣]{2,}", prose))

        if not code_blocks:
            score *= 0.3
            issues.append("요청된 코드 블록 누락")
        elif not code_only_requested and (len(prose) < 80 or not has_korean_prose):
            score *= 0.45
            issues.append("코드-only 응답")
        elif not code_only_requested and len(output) < 200:
            score *= 0.75
            issues.append("코딩 응답 설명 부족")

        complexity_requested = bool(
            re.search(
                r"(복잡도|big-?o|성능|시간\s*복잡도|공간\s*복잡도|time complexity|space complexity)",
                request_lower,
            ),
        )
        if complexity_requested and not re.search(r"\bO\s*\([^)]+\)", output):
            score *= 0.55
            issues.append("Big-O 복잡도 누락")

        comparison_requested = bool(
            re.search(r"(비교|차이|장단점|compare|comparison|trade-?off)", request_lower),
        )
        output_lower = output.lower()
        markdown_table = bool(re.search(r"^\s*\|.+\|\s*$", output, re.MULTILINE))
        structured_comparison = markdown_table or bool(
            re.search(
                r"(장점|단점|기준|차이점|trade-?off|pros|cons|1\.\s+.+\n\s*2\.\s+)",
                output_lower,
                re.DOTALL,
            ),
        )
        if comparison_requested and not structured_comparison:
            score *= 0.55
            issues.append("비교 구조 부족")

        return score, issues

    def _check_planning_mode(
        self, request: str, output: str, task_type: str, execution_mode: str | None = None
    ) -> tuple[float, list[str]]:
        """대규모/복잡한 아키텍처 변경 요청 시 Planning Mode (Artifacts) 작동 여부 검증.

        Args:
            request: 사용자 요청
            output: 에이전트 출력
            task_type: 태스크 유형
            execution_mode: 실행 모드 ("plan", "build", "interactive", None)
                           BUILD 모드에서는 Plan 체크를 건너뜁니다.
        """
        score = 1.0
        issues: list[str] = []

        # BUILD 모드에서는 Plan 체크 건너뜀 (Phase 1 D5)
        if execution_mode == "build":
            return score, issues

        request_lower = request.lower()

        is_complex_request = task_type == "complex" or bool(
            re.search(
                r"(아키텍처|구조|전면|대규모|마이그레이션|리팩토링|architecture|refactor|migrate)",
                request_lower,
            ),
        )

        if is_complex_request:
            has_plan_artifact = bool(re.search(r"implementation_plan\.md", output, re.IGNORECASE))
            has_approval = bool(re.search(r"\[APPROVAL REQUIRED\]", output))
            has_structured_plan = bool(
                re.search(
                    r"(#{1,3}\s*(계획|plan)|계획\s*(및|/)\s*의존성|checkpoint|implementation_plan\.md)",
                    output,
                    re.IGNORECASE,
                ),
            )

            structured_plan_allowed = task_type not in ("coding", "complex", "complex_step")
            if not has_plan_artifact and not has_approval and not (structured_plan_allowed and has_structured_plan):
                score *= 0.4
                issues.append(
                    "복잡한 태스크에서 Planning Mode(계획안 및 승인 요청) 누락 (재시도 필요)",
                )

        return score, issues

    def _check_safety(self, output: str) -> tuple[float, list[str]]:
        score = 1.0
        issues: list[str] = []
        for pattern, desc in [
            (r"rm\s+-rf\s+/", "루트삭제"),
            (r":(){ :\|:& };:", "포크폭탄"),
            (r"mkfs\.", "디스크포맷"),
        ]:
            if re.search(pattern, output):
                score *= 0.3
                issues.append(f"위험명령: {desc}")
        return score, issues

    def _check_repetition(self, output: str) -> tuple[float, list[str]]:
        """동일 문단이 3회 이상 반복되면 품질 감점."""
        score = 1.0
        issues: list[str] = []
        # 코드 대안들은 출력/분석 heading 같은 경계 보일러플레이트를 공유한다.
        # 반복 루프 탐지는 prose만 대상으로 한다.
        prose = re.sub(r"```.*?```", "", output, flags=re.DOTALL)
        # 표 행/헤딩/수평선은 구조지 prose가 아니다 — 여러 표가 같은
        # 헤더·구분자 패턴을 공유해 오탐한 사례가 있다(라이브 E2E 관찰).
        structural = re.compile(r"^\s*(\||-{3,}|={3,}|#)")
        lines = [line for line in prose.split("\n") if not structural.match(line)]
        if len(lines) > 20:
            block_size = 4
            occurrences: dict[str, list[int]] = {}
            for i in range(len(lines) - block_size + 1):
                block = "\n".join(lines[i : i + block_size]).strip()
                if len(block) < 40:  # 너무 짧은 블록은 무시
                    continue
                occurrences.setdefault(block, []).append(i)
            # 슬라이딩 윈도우의 겹침 등장은 하나로 묶는다 — 서로 다른 위치에
            # 재등장한 횟수(비중복 등장)만 센다. 진짜 루프는 같은 블록이
            # 문서 전역에 여러 번 나타난다.
            max_repeats = 0
            for starts in occurrences.values():
                non_overlapping = 0
                last_end = -1
                for start in starts:
                    if start > last_end:
                        non_overlapping += 1
                        last_end = start + block_size - 1
                max_repeats = max(max_repeats, non_overlapping)
            if max_repeats >= 5:
                score *= 0.1
                issues.append(f"심각한 반복 루프 탐지 ({max_repeats}회 반복)")
            elif max_repeats >= 3:
                score *= 0.3
                issues.append(f"반복 콘텐츠 탐지 ({max_repeats}회 반복)")
        return score, issues

    def _check_internal_tag_leak(self, output: str) -> tuple[float, list[str]]:
        """내부 태그/추론 흔적이 사용자에게 유출되면 강하게 감점."""
        score = 1.0
        issues: list[str] = []
        leak_patterns = [
            (r"%%THINK_START%%", "%%THINK_START%% 태그 유출"),
            (r"%%THINK_END%%", "%%THINK_END%% 태그 유출"),
            (r"</?think>", "<think> 태그 유출"),
            (r"</?thought>", "<thought> 태그 유출"),
            (r"<algorithm>.*?</algorithm>", "<algorithm> 태그 유출"),
            (r"\bhere(?:'|’)s\s+a\s+thinking\s+process\b", "영어 내부 사고 과정 서문 유출"),
            (r"\bthinking\s+process\b", "Thinking Process 문구 유출"),
            (r"\banalyze\s+user\s+input\b", "영어 내부 분석 절차 유출"),
            (r"---\s*\*?Thinking Process\*?\s*---", "Thinking Process 섹션 유출"),
            (r"---\s*\*?End of Thinking\*?\s*---", "End of Thinking 섹션 유출"),
            (r"The user wants me to", "영어 혼잣말(monologue) 유출"),
            (r"\bOkay,\s*I need to\b", "영어 내부 추론 유출"),
            (r"\bI need to:?\n", "영어 내부 계획(plan) 유출"),
            (r"\bI should\b", "영어 내부 계획(plan) 유출"),
            (r"\bThe first step is\b", "영어 내부 절차 서술 유출"),
            (r"\bSo the plan is\b", "영어 내부 계획(plan) 유출"),
            (r"\bLooking at the persistent context\b", "내부 컨텍스트 언급 유출"),
        ]
        for pattern, desc in leak_patterns:
            if re.search(pattern, output, re.DOTALL | re.IGNORECASE):
                score *= 0.35
                issues.append(desc)
        return score, issues

    def _check_language_contamination(self, output: str) -> tuple[float, list[str]]:
        """한국어 응답에 중국어/일본어 문자가 혼입되면 감점.
        코드 블록 내부는 제외합니다.
        """
        score = 1.0
        issues: list[str] = []
        # 코드 블록 제거 후 산문(prose)만 검사
        prose = re.sub(r"```(?:\w+)?\s*.*?```", "", output, flags=re.DOTALL).strip()
        # 중국어 간체/번체 (한국어 한자 범위 밖)
        chinese_chars = re.findall(r"[\u4e00-\u9fff]", prose)
        # 한국어 한자(한문) 사용은 허용하되, 중국어 문장 패턴 감지
        chinese_phrases = re.findall(r"[\u4e00-\u9fff]{3,}", prose)
        # 일본어 히라가나/카타카나 혼입
        japanese_chars = re.findall(r"[\u3040-\u309f\u30a0-\u30ff]", prose)
        suspicious_cjk_terms = re.findall(
            r"(文件|产能|先进|先進|できません|アップ|アップグレード|グレード|できます)",
            prose,
            flags=re.IGNORECASE,
        )
        if suspicious_cjk_terms:
            score *= 0.35
            issues.append(
                f"한국어 응답 내 외국어 오염 감지 ({', '.join(sorted(set(suspicious_cjk_terms))[:3])})",
            )
        if len(chinese_phrases) >= 2:
            score *= 0.4
            issues.append(
                f"중국어 문자열 혼입 감지 ({len(chinese_phrases)}개 구절: {'、'.join(chinese_phrases[:3])})",
            )
        elif len(chinese_chars) > 5:
            score *= 0.6
            issues.append(f"중국어 문자 다수 혼입 ({len(chinese_chars)}자)")
        if japanese_chars:
            score *= 0.35 if len(japanese_chars) > 3 else 0.55
            issues.append(f"일본어 문자 혼입 ({len(japanese_chars)}자)")
        return score, issues

    def _check_korean_readability(self, output: str) -> tuple[float, list[str]]:
        """한국어 산문의 띄어쓰기/문장 경계 붕괴를 탐지합니다."""
        score = 1.0
        issues: list[str] = []
        prose = re.sub(r"```(?:\w+)?\s*.*?```", "", output, flags=re.DOTALL).strip()
        prose = re.sub(r"`[^`\n]+`", " ", prose)
        prose = re.sub(r"^\s*\|.*\|\s*$", " ", prose, flags=re.MULTILINE)
        prose = re.sub(r"\[[^\]\n]+\]\([^\n)]+\)", " ", prose)
        prose = re.sub(r"https?://\S+", " ", prose)
        if not re.search(r"[가-힣]{2,}", prose):
            return score, issues

        bad_spacing_terms = re.findall(
            r"(할수|될수|사용할수|작성할수|확인할수|알려줄래|당신의프로젝트|확인하고어떻게|로컬LLM모델의을|"
            + r"모델의을|내가업|응답でき|업グレ?드)",
            prose,
        )
        long_glued_hangul = re.findall(r"[가-힣]{20,}", prose)
        missing_sentence_spaces = re.findall(r"(?<![A-Za-z0-9])[.!?。][가-힣A-Za-z]", prose)
        korean_foreign_glue = re.findall(
            r"(?:[가-힣][A-Za-z]{3,}[가-힣]|[가-힣]{3,}[A-Za-z]{3,}|[A-Za-z]{3,}[가-힣]{3,})",
            prose,
        )

        weighted_defect_count = (
            (len(bad_spacing_terms) * 3)
            + (len(long_glued_hangul) * 2)
            + (len(missing_sentence_spaces) * 2)
            + max(0, len(korean_foreign_glue) - 2)
        )
        if weighted_defect_count >= 8:
            score *= 0.35
            issues.append(f"한국어 띄어쓰기/가독성 붕괴 (오류 후보 {weighted_defect_count}개)")
        elif weighted_defect_count >= 4:
            score *= 0.6
            issues.append(f"한국어 띄어쓰기/문장 경계 품질 저하 (오류 후보 {weighted_defect_count}개)")
        return score, issues

    def _check_current_info_grounding(self, request: str, output: str) -> tuple[float, list[str]]:
        """최신/현재 정보 요청에서 cutoff 핑계나 미검증 답변을 감점합니다."""
        score = 1.0
        issues: list[str] = []
        request_lower = request.lower()
        asks_current_info = bool(
            re.search(
                r"(최신|최근|동향|실시간|현재|오늘|이번\s*주|latest|recent|current|trend|news|today)",
                request_lower,
            ),
        )
        if not asks_current_info:
            return score, issues

        output_lower = output.lower()
        stale_or_ungrounded = bool(
            re.search(
                r"(knowledge cutoff|as of my knowledge cutoff|october\s+2023|"
                + r"2023년\s*10월|실시간\s*데이터.*없|인터넷.*접속.*없|"
                + r"real[- ]?time data.*not|available up until)",
                output_lower,
            ),
        )
        has_date_or_source = bool(
            re.search(
                r"(20\d{2}[년./-]\s*\d{1,2}|출처|source|검색|확인|https?://|github|hugging\s*face)",
                output_lower,
            ),
        )
        if stale_or_ungrounded:
            score *= 0.35
            issues.append("최신 정보 요청에서 지식 cutoff/비검증 답변")
        elif not has_date_or_source:
            score *= 0.7
            issues.append("최신 정보 요청에 날짜/출처/검증 근거 부족")
        return score, issues

    def _check_comparison_table(self, request: str, output: str) -> tuple[float, list[str]]:
        score = 1.0
        issues: list[str] = []
        request_lower = request.lower()
        table_requested = bool(
            re.search(
                r"비교\s*표|(?<![가-힣])표(?:로|\s*(?:형식|형태))|테이블(?:로|\s*(?:형식|형태))|"
                + r"\b(?:in|as)\s+(?:a\s+)?(?:markdown\s+)?table\b|"
                + r"\b(?:comparison|markdown)\s+table\b|\btable\s+(?:format|comparing)\b",
                request_lower,
            ),
        )
        if not table_requested:
            return score, issues

        has_table = bool(re.search(r"^\s*\|.+\|.+\|\s*$", output, re.MULTILINE))
        if not has_table:
            score *= 0.55
            issues.append("비교 요청에 Markdown 비교표(table) 누락")
        return score, issues

    def _check_information_density(self, output: str) -> tuple[float, list[str]]:
        """출력물의 정보 밀도를 검증합니다.
        장황하지만 정보가 없는 답변(filler)을 감점합니다.
        """
        score = 1.0
        issues: list[str] = []
        if len(output) < 300:
            return score, issues

        prose = re.sub(r"```(?:\w+)?\s*.*?```", "", output, flags=re.DOTALL).strip()
        if not prose:
            return score, issues

        # 1. 문장 단위 반복 감지
        sentences = re.split(r"[.!?。\n]", prose)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
        if sentences:
            unique = set(sentences)
            dup_ratio = 1.0 - (len(unique) / len(sentences))
            if dup_ratio > 0.4:
                score *= 0.4
                issues.append(f"문장 수준 반복 과다 (중복률 {dup_ratio:.0%})")
            elif dup_ratio > 0.25:
                score *= 0.7
                issues.append(f"문장 수준 반복 감지 (중복률 {dup_ratio:.0%})")

        # 2. 구조 요소 밀도 (heading, list, code block)
        if len(output) > 800:
            headings = len(re.findall(r"^#{1,3}\s", output, re.MULTILINE))
            lists = len(re.findall(r"^\s*[-*]\s", output, re.MULTILINE))
            code_blocks = len(re.findall(r"```", output))
            tables = len(re.findall(r"^\s*\|.+\|\s*$", output, re.MULTILINE))
            structure_count = headings + lists + code_blocks // 2 + tables
            chars_per_structure = len(output) / max(structure_count, 1)
            if chars_per_structure > 600 and structure_count < 3:
                score *= 0.75
                issues.append("구조 요소 부족 (heading/list/table 없는 긴 산문)")

        # 3. 고유 단어 비율 (filler 탐지)
        words = re.findall(r"[가-힣a-zA-Z]{2,}", prose.lower())
        if len(words) > 50:
            unique_words = set(words)
            vocab_richness = len(unique_words) / len(words)
            if vocab_richness < 0.2:
                score *= 0.5
                issues.append(f"어휘 다양성 극히 낮음 ({vocab_richness:.0%})")
            elif vocab_richness < 0.3:
                score *= 0.75
                issues.append(f"어휘 다양성 낮음 ({vocab_richness:.0%})")

        return score, issues

    def _check_antigravity_markdown_standards(self, output: str) -> tuple[float, list[str]]:
        """Ssak-Ai 모델 수준의 마크다운 규약(Mermaid, Carousel, 파일 링크 등) 준수 여부 검증."""
        score = 1.0
        issues: list[str] = []

        # 1. Mermaid 블록에 HTML 태그 포함 여부 (에러 유발)
        mermaid_blocks: list[str] = re.findall(r"```mermaid\n(.*?)\n```", output, re.DOTALL)
        for block in mermaid_blocks:
            if re.search(r"<[a-zA-Z]+.*?>", block):
                score *= 0.8
                issues.append("Mermaid 다이어그램 내 HTML 태그 포함 (렌더링 에러 위험)")

        # 2. Carousel syntax 오류 (슬라이드 주석은 있으나 백틱 선언이 틀린 경우)
        if re.search(r"<!--\s*slide\s*-->", output, re.IGNORECASE) and not re.search(
            r"````carousel", output, re.IGNORECASE
        ):
            score *= 0.75
            issues.append("Carousel 마크다운 문법 오류 (백틱 4개 ````carousel 선언 필요)")

        # 3. 잘못된 파일 링크 포맷 (링크 텍스트를 백틱으로 감싸면 렌더링 깨짐)
        if re.search(r"\[`[^`]+`\]\(file://", output):
            score *= 0.85
            issues.append("파일 링크 텍스트에 백틱 사용 (마크다운 링크 포맷 깨짐 위험)")

        # 4. Old Note Block 감지 (GitHub Alerts로 유도)
        if re.search(r"\*\*(Note|Warning|Important)\*\*:", output, re.IGNORECASE):
            score *= 0.9  # 경고성 감점
            issues.append("구형 경고 블록 감지 (GitHub Alerts `> [!NOTE]` 스타일 권장)")

        return score, issues

    def _check_github_alerts(self, output: str) -> tuple[float, list[str]]:
        """GitHub-Style Alert 블록의 문법 정확성을 검증합니다.

        올바른 형식:
        > [!NOTE]
        > content

        잘못된 형식:
        >[!NOTE]  (공백 누락)
        > [!NOTE] content (빈 줄 없이 바로 내용)

        Returns:
            (score_multiplier: float, issues: list[str])

        """
        score = 1.0
        issues: list[str] = []

        # GitHub Alert 찾기
        alerts_found = list(re.finditer(r">\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]", output, re.IGNORECASE))

        if not alerts_found:
            # 구형 경고 블록 사용 감지 (GitHub Alerts로 전환 권장)
            old_style = re.findall(
                r"\*\*(?:Note|Warning|Important|Tip|Caution)\*\*:\s*(.+?)(?:\n\n|$)",
                output,
                re.IGNORECASE | re.DOTALL,
            )
            if old_style:
                score *= 0.85
                issues.append(
                    f"GitHub Alert 미사용: {len(old_style)}개의 구형 경고 블록을 `> [!NOTE]` 스타일로 전환하세요"
                )
            return score, issues

        for match in alerts_found:
            start = match.start()
            alert_type = match.group(1)
            after_alert = output[start : start + 200]
            lines = after_alert.split("\n")

            # 첫 번째 라인: "> [!TYPE]" 만 있어야 함 (내용이 바로 오면 안 됨)
            first_line = lines[0] if lines else ""
            if re.search(r"\[!(?:NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s+\S", first_line, re.IGNORECASE):
                score *= 0.7
                issues.append(f"GitHub Alert `{alert_type}`: 내용이 Alert 헤더와 같은 라인에 있음")

            # 두 번째 라인: "> content" 형식이어야 함
            if len(lines) > 1:
                second_line = lines[1].strip()
                if second_line and not second_line.startswith(">"):
                    score *= 0.8
                    issues.append(f"GitHub Alert `{alert_type}`: Alert 내용이 `>` 블록으로 시작하지 않음")

        return score, issues

    def _check_artifact_format(self, output: str) -> tuple[float, list[str]]:
        """Artifact 파일(implementation_plan.md, task.md 등)의 포맷을 검증합니다.

        Plan 모드에서 생성된 출력물이 아티팩트 규칙을 준수하는지 확인합니다.

        Returns:
            (score_multiplier: float, issues: list[str])

        """
        score = 1.0
        issues: list[str] = []

        # 1. Plan 아티팩트 필수 섹션 검증
        plan_sections = [
            (r"#+\s*(?:개요|목표|Overview|Goal)", "Overview"),
            (r"#+\s*(?:기술\s*접근|설계|아키텍처|Technical Approach|Architecture|Design)", "Technical Approach"),
            (r"#+\s*(?:구현\s*단계|작업\s*계획|Implementation Steps|Plan|Steps|Tasks)", "Implementation Steps"),
            (r"[-*]\s*\[[\sx]\]", "Task List (checkbox)"),
            (r"#+\s*(?:일정|우선순위|Timeline|Priority)", "Timeline/Priority"),
        ]

        is_plan_context = bool(
            re.search(r"implementation_plan\.md|\bplanning\b|\bplan\s+mode\b", output, re.IGNORECASE)
        )

        if is_plan_context:
            found_sections: list[str] = []
            missing_sections: list[str] = []
            for pattern, name in plan_sections:
                if re.search(pattern, output, re.IGNORECASE | re.MULTILINE):
                    found_sections.append(name)
                else:
                    missing_sections.append(name)

            if missing_sections:
                section_penalty = len(missing_sections) * 0.1
                score *= max(0.5, 1.0 - section_penalty)
                issues.append(f"Plan 아티팩트 필수 섹션 누락: {', '.join(missing_sections)}")

        # 2. [APPROVAL REQUIRED] 마커 검증
        has_approval = bool(re.search(r"\[APPROVAL REQUIRED\]", output))
        is_pending_approval = bool(
            re.search(r"implementation_plan\.md|\bplanning\b", output, re.IGNORECASE)
            and not re.search(r"승인|approve|build\s+mode|executing", output, re.IGNORECASE)
        )
        if is_pending_approval and not has_approval:
            score *= 0.75
            issues.append("Plan 작성 후 `[APPROVAL REQUIRED]` 마커 누락")

        # 3. Task.md 형식 검증 (체크박스 태스크 존재 여부)
        has_task_context = bool(re.search(r"\btask\.md\b|\btasks\s*:|할\s*일|\bTODO\b", output, re.IGNORECASE))
        if has_task_context:
            checkbox_count = len(re.findall(r"[-*]\s*\[[\sx]\]", output))
            if checkbox_count == 0:
                score *= 0.7
                issues.append("Task.md 컨텍스트에서 체크박스 태스크(`- [ ]`) 없음")
            elif checkbox_count > 20:
                score *= 0.9
                issues.append(f"체크박스 태스크가 {checkbox_count}개로 과도하게 많음 — 그룹화 필요")

        # 4. Mermaid 블록 검증
        mermaid_blocks: list[str] = re.findall(r"```mermaid\n(.*?)\n```", output, re.DOTALL)
        mermaid_keywords = r"(?:graph|flowchart|sequenceDiagram|classDiagram|stateDiagram|erDiagram|gantt|pie|gitGraph|journey|mindmap|timeline|xychart|block|quadrantChart)"
        for block in mermaid_blocks:
            if not re.search(
                rf"[A-Za-z_]+\(?\s*--[>-]\s*[A-Za-z_]+\(?|[A-Za-z_]+\[|{mermaid_keywords}",
                block,
            ):
                score *= 0.85
                issues.append("Mermaid 블록에 유효한 다이어그램 문법 없음")
                break

        return score, issues
