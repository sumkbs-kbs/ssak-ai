"""r33: quality gate must not demand code blocks for non-code work, but still flag missing code."""

from __future__ import annotations

import pytest

from antigravity_k.engine.quality_gate import QualityGate

GREETINGS = "\n".join(f"{i}. 안녕하세요, 오늘은 색상 {i}번처럼 밝은 하루 보내세요!" for i in range(1, 31))


def _issues(task_type: str, request: str, output: str) -> list[str]:
    _score, issues = QualityGate()._check_output_contract(request, output, task_type)
    return issues


@pytest.mark.parametrize(
    ("task_type", "req"),
    [
        ("coding", "Synthetic r32 task (no tools needed): write 30 numbered one-line friendly greetings, each naming a different color."),
        ("complex", "프로젝트 노트를 깔끔하게 유지하는 팁 40개를 번호 목록으로 적어 주세요."),
        ("complex", "회의록 문서를 요약해서 정리해 주세요."),
    ],
)
def test_non_code_requests_do_not_require_code_blocks(task_type: str, req: str) -> None:
    assert "요청된 코드 블록 누락" not in _issues(task_type, req, GREETINGS)


@pytest.mark.parametrize(
    ("task_type", "req"),
    [
        ("coding", "Write a Python function that reverses a list."),
        ("coding", "정렬 함수를 구현해 주세요."),
        ("complex", "Refactor the login endpoint in api.py to use async."),
        ("simple_chat", "Implement a bash script that counts lines."),
    ],
)
def test_real_code_requests_still_flag_missing_code(task_type: str, req: str) -> None:
    assert "요청된 코드 블록 누락" in _issues(task_type, req, GREETINGS)


def test_numbered_list_counts_as_structure() -> None:
    _score, issues = QualityGate()._check_information_density(GREETINGS * 2)
    assert not any("구조 요소 부족" in issue for issue in issues)


def test_long_unstructured_prose_still_flagged() -> None:
    prose = " ".join(f"문장 {i} 에서는 서로 다른 단어 조합 alpha{i} beta{i} 으로 설명이 길게 이어집니다." for i in range(40))
    _score, issues = QualityGate()._check_information_density(prose)
    assert any("구조 요소 부족" in issue for issue in issues)
