"""Identifier-only recall must not impose a source-code fence contract."""

from __future__ import annotations

import pytest

from antigravity_k.engine.quality_gate import QualityGate, QualityGrade

FACT = "R43-SYNTH-BADGE-4812"


@pytest.mark.parametrize("task_type", ["simple_chat", "reasoning", "coding"])
@pytest.mark.parametrize(
    "user_request",
    [
        "Quillmere 오프사이트 배지 색상으로 우리가 정했던 것은 무엇이었지? 코드만 답해줘.",
        "지난번에 정한 배지 색상 코드는 무엇이었나요? 코드만 답해줘.",
        "What badge colour code did we agree on for the offsite? Return code only.",
        "우리가 정한 릴리스 코드명은 무엇이었지? 코드만 답해줘.",
        "우리가 저장한 프로젝트 badge_code 기억은 무엇이었지? 코드만 답해줘.",
        "우리가 기록한 프로젝트 region_id는 무엇이었지? 코드만 답해줘.",
        "What did we save as our project badge code? Return code only.",
        "read_file로 notes.txt 파일을 실제로 읽고, 마지막 줄 코드만 답해줘.",
        "Read notes.txt and return the last line code only.",
    ],
)
def test_identifier_only_answer_does_not_require_program_source(task_type: str, user_request: str) -> None:
    result = QualityGate().evaluate(task_type, user_request, FACT)

    assert "요청된 코드 블록 누락" not in result.issues
    assert result.grade in (QualityGrade.A, QualityGrade.B)
    assert result.should_retry is False


@pytest.mark.parametrize(
    "user_request",
    [
        "Python factorial 함수를 작성해. 코드만 답해줘.",
        "Write a Python function that returns the badge colour code. Code only.",
        "배지 색상으로 우리가 정했던 것을 상수로 반환하는 함수를 작성해. 코드만 답해줘.",
        "What badge colour code did we agree on? Then write code to validate it. Code only.",
        "What badge colour code did we agree on? Debug it. Code only.",
        "우리가 정한 릴리스 코드명을 확인하고, 그 값을 출력하는 Python 프로그램을 작성해. 코드만 답해줘.",
        "배지 색상을 보여주는 버튼을 만들어. 코드만 답해줘.",
        "우리가 저장한 badge_code를 반환하는 함수를 작성해. 코드만 답해줘.",
        "Recall our stored Python function. Return code only.",
        "마지막 줄 코드를 생성하는 Python 함수를 작성해. 코드만 답해줘.",
        "What did we save as our project code? Then implement a validator. Code only.",
        "코드만 답해줘.",
    ],
)
def test_identifier_subject_does_not_exempt_explicit_program_source(user_request: str) -> None:
    result = QualityGate().evaluate("simple_chat", user_request, FACT)

    assert "요청된 코드 블록 누락" in result.issues
    assert result.should_retry is True


def test_identifier_answer_still_reaches_semantic_verification() -> None:
    calls: list[str] = []

    def verify(prompt: str) -> str:
        calls.append(prompt)
        return "총점: 4"

    result = QualityGate(verify_fn=verify).evaluate(
        "simple_chat", "지난번에 정한 배지 색상은 무엇이었지? 코드만 답해줘.", FACT
    )

    assert len(calls) == 1
    assert result.grade is QualityGrade.C
    assert result.should_retry is True


def test_identifier_answer_does_not_bypass_internal_reasoning_check() -> None:
    result = QualityGate().evaluate(
        "simple_chat", "지난번에 정한 배지 색상은 무엇이었지? 코드만 답해줘.", "<think>private</think>" + FACT
    )

    assert result.should_retry is True
    assert result.grade in (QualityGrade.C, QualityGrade.F)
