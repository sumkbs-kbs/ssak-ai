"""Current trusted requests, rather than negative or quoted mentions, bind tools."""

from __future__ import annotations

from pathlib import Path

import pytest

from antigravity_k.engine.direct_task_execution import DirectTaskExecution
from tests.test_search_request_contract import _Orchestrator


@pytest.mark.parametrize("case", [
    ("read_file을 호출하지 마세요. 프로젝트 사실을 기억해줘.", []),
    ("read_file 도구는 사용하지 마세요. 기억한 값만 답해줘.", []),
    ("Do not call read_file. Answer from memory.", []),
    ("도구를 사용하지 마세요. read_file 도구로 읽을 필요가 없습니다.", []),
    ("파일을 읽지 마세요. read_file 도구의 사용은 금지합니다.", []),
    ("read_file 도구로 README.md를 읽어줘.", ["read_file"]),
    ("`read_file` 도구로 README.md를 읽어줘.", ["read_file"]),
    ("Use the `read_file` tool to read README.md.", ["read_file"]),
    ("Explain the `read_file` tool.", []),
    ("인라인 이름 `read_file` 도구의 역할을 설명해줘.", []),
    ("`read_file`을 설명해줘.", []),
    ("`read_file`을 호출해서 README.md를 읽어줘.", ["read_file"]),
    ("다른 파일은 읽지 말고 read_file 도구로 README.md만 읽어줘.", ["read_file"]),
    ('예시: "read_file을 호출하지 마세요"를 설명해줘.', []),
    ("예시: `read_file 도구로 읽어줘`를 설명해줘.", []),
    ("예시:\n```text\nread_file 도구로 README.md를 읽어줘\n```", []),
    ("예시:\n> read_file 도구로 README.md를 읽어줘", []),
    ('예시: "read_file을 호출하지 마세요". read_file 도구로 README.md를 읽어줘.', ["read_file"]),
    ("웹 검색으로 공식 문서를 확인하고 추가 검색은 하지 마세요.", ["web_search"]),
    ("웹 검색하지 마세요. 기존 지식만 사용하세요.", []),
    ("도구를 사용하지 마세요. web_search 도구로 검색하는 것은 필요 없습니다.", []),
])
def test_expected_tools_follow_active_request_and_shared_constraints(tmp_path: Path, case: tuple[str, list[str]]) -> None:
    # Given: registered production tool names and a current user request.
    request_text, expected = case
    execution = DirectTaskExecution(_Orchestrator(tmp_path, []), None)
    # When: the real contract parser selects the required tools.
    tools = execution._explicit_tool_contract(request_text)
    # Then: only trusted, allowed requests create mandatory tool contracts.
    assert tools == expected
