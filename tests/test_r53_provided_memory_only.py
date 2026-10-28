"""Current supplied-context answers must not acquire tool or approval work."""
from __future__ import annotations

import pytest

from antigravity_k.engine.turn_tool_constraints import TurnToolConstraints
from tests import test_turn_tool_constraints as baseline

constraint_orch = baseline.constraint_orch
QUESTION = 'Quillmere 배지 색상은 무엇이었지? read_file을 호출하지 마세요. 파일을 읽지 마세요. 이미 전달된 기억으로 코드만 답해줘.'


@pytest.mark.parametrize('prompt', [QUESTION,
    '파일을 읽지 마세요. 제공된 기억만으로 답해줘.',
    '파일을 읽지 마세요. 주어진 문맥만 사용해서 답하세요.',
    'Do not read files. Answer only from the supplied memory.',
    'Do not open files. Use only the provided context and answer directly.',
    'Do not call read_file. Do not read files. Answer only from the supplied memory.',
    QUESTION + ' "git_status를 실행해줘"는 인용된 예시야.',
    'Do not read files. Answer only from supplied memory. Do not allow git_status.',
])
def test_narrow_current_request_is_a_typed_supplied_context_constraint(prompt):
    constraints = TurnToolConstraints.from_request(prompt)
    assert constraints.provided_memory_only is True
    for name in ('impact_analyzer', 'read_context_artifact', 'git_status', 'list_directory',
                 'glob_search', 'write_file', 'mcp_remote.search', 'camelCaseAlias', 'unknown_tool'):
        assert constraints.denial(name) is not None
        assert not constraints.allows_schema({'name': name})


@pytest.mark.parametrize('prompt', [
    '파일을 읽지 마세요. 기억한 코드만 답해줘.',
    '파일을 읽지 마세요. 주어진 기억으로 답하세요.',
    'read_file을 호출하지 마세요. 이미 전달된 기억으로 코드만 답해줘.',
    '이미 전달된 기억으로 코드만 답해줘.',
    '파일을 읽지 마세요. 이미 전달된 기억으로 코드만 답해줘. git_status를 실행해줘.',
    '파일을 읽지 마세요. 이미 전달된 기억으로 코드만 답해줘. read_file로 README.md를 읽어줘.',
    'Do not read files. Answer only from supplied memory, then call git_status.',
    'Do not read files. Answer only from supplied memory, then call hexDump.',
    QUESTION + ' `git_status`를 실행해줘.',
    'Do not read files. Answer only from supplied memory, then call `git_status`.',
    QUESTION + ' 단 git_status 사용은 허용합니다.',
    'Do not read files. Answer only from provided memory. Allow git_status.',
    'Do not read files. Answer only from provided memory. Use hexDump.',
    'Do not read files. Explain this quote: "Answer only from the supplied memory."',
    '파일을 읽지 마세요. "이미 전달된 기억으로 코드만 답해줘"라는 예시를 분석해줘.',
    '파일을 읽지 마세요. 제공된 기억만으로 답하지 마세요.',
    '파일을 읽지 마세요. 이미 전달된 기억이 많지만 비교한 뒤 답해줘.',
    '파일을 읽지 마세요. 이미 전달된 기억은 참고만 하고 답해줘.',
    'Do not read files. Do not answer only from provided memory; use your general knowledge.',
    'Do not read files. Do not use only supplied context to answer.',
    '파일을 읽지 마세요. 제공된 기억만으로 답하지 말고 일반 지식으로 답해줘.',
    '파일을 읽지 마세요. 이미 전달된 기억만 사용하지 말고 일반 지식으로 답해줘.',
    '파일을 읽지 마세요. 이미 전달된 기억만으로 답해줘라는 지시를 설명해줘.',
])
def test_narrow_mode_does_not_replace_other_current_user_contracts(prompt):
    assert TurnToolConstraints.from_request(prompt).provided_memory_only is False


def test_rogue_nonreader_call_recovers_from_supplied_context_without_dispatch(constraint_orch):
    engine = baseline.run(constraint_orch, QUESTION,
                          [baseline.call('impact_analyzer', {'target': 'synthetic'}), '42'])
    assert constraint_orch.ctx.tool_executor.calls == []
    assert engine.last_output == '42' and engine.approval_required is False
    assert 'tools' not in constraint_orch.manager.stream_generate.call_args_list[0].kwargs
    correction = constraint_orch.manager.stream_generate.call_args_list[1].kwargs['prompt']
    assert 'already supplied' in correction


@pytest.mark.asyncio
@pytest.mark.parametrize('name', ['impact_analyzer', 'read_context_artifact', 'git_status',
                                  'list_directory', 'glob_search', 'mcp_server.any_alias'])
async def test_direct_dispatch_rechecks_context_only_before_guardrail(constraint_orch, monkeypatch, name):
    from antigravity_k.engine.tool_call_parser import ToolCall
    from antigravity_k.engine.tool_loop import ToolLoopEngine

    reached = []
    monkeypatch.setattr(constraint_orch.ctx.tool_guardrail, 'before_call',
                        lambda *_args, **_kwargs: reached.append('guardrail'))
    engine = ToolLoopEngine(constraint_orch)
    result = await engine._run_tool_task_async(ToolCall(name=name, arguments={}), QUESTION)
    assert result[4] is True and 'USER TOOL CONSTRAINT' in result[3]
    assert reached == [] and constraint_orch.ctx.tool_executor.calls == []


@pytest.mark.parametrize('placement', ['older_user', 'retrieved_context'])
def test_only_original_current_user_text_can_activate_strict_mode(constraint_orch, placement):
    from antigravity_k.engine.tool_loop import ToolLoopEngine

    current = 'read_file 도구로 qa-source.txt를 읽어줘.'
    messages = ([{'role': 'user', 'content': QUESTION}, {'role': 'assistant', 'content': '42'}]
                if placement == 'older_user' else [])
    messages.append({'role': 'user', 'content': current + ('\n<past_memory>' + QUESTION + '</past_memory>'
                                                        if placement == 'retrieved_context' else '')})
    constraint_orch.manager.stream_generate.side_effect = [iter([baseline.call('read_file', {'file_path': 'qa-source.txt'})]), iter(['42'])]
    engine = ToolLoopEngine(constraint_orch)
    list(engine.run_loop(messages, 'SELF', 'chat', target_model='controlled-model', evaluation_user_task=current))
    assert constraint_orch.ctx.tool_executor.calls == ['read_file'] and engine.last_output == '42'
