from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import JsonValue

from antigravity_k.engine.quality_gate import QualityGate, QualityGrade


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)


@pytest.mark.parametrize(
    ("task_type", "user_request", "output"),
    [
        ("chat", "두 숫자 7과 9를 비교해서 더 큰 숫자 하나만 출력해.", "9"),
        ("simple_chat", "4와 12를 비교해 큰 정수만 반환해.", "12"),
        ("reasoning", "Return only the larger number after comparing 3 and 18.", "18"),
        ("reasoning", "계산 결과를 JSON만 출력해.", '{"result": 391}'),
        ("reasoning", "Return JSON only with an HTTP status code.", '{"code": 200}'),
        ("reasoning", "Return only the number used by the Python runtime.", "3"),
        ("reasoning", "없는 문서의 발행일을 알고 있니?", "확인된 정보가 없습니다."),
        ("reasoning", "Reply with just the status token.", "ready"),
        ("chat", "Compare the two choices briefly.", "A is faster. B costs less."),
        ("chat", "짧은 발표로 두 값을 설명해.", "첫째는 빠르고 둘째는 저렴합니다."),
        ("reasoning", "정수 7과 실수 9.5를 비교해서 더 큰 숫자 하나만 반환해.", "9.5"),
        ("reasoning", "Compare integer 7 and decimal 9.5. Return only the larger number.", "9.5"),
    ],
)
def test_short_response_passes_when_length_and_word_overlap_do_not_prove_failure(
    task_type: str, user_request: str, output: str
) -> None:
    # Given: a concise response with no independent semantic verifier.
    gate = QualityGate(max_retries=2)

    # When: the gate checks its observable output shape.
    result = gate.evaluate(task_type, user_request, output)

    # Then: shortness and dissimilar wording alone cannot trigger a rewrite.
    assert result.should_retry is False
    assert result.grade in (QualityGrade.A, QualityGrade.B)


@pytest.mark.parametrize(("task_type", "execution_mode"), [("reasoning", None), ("coding", None), ("complex", "build")])
@pytest.mark.parametrize(
    ("user_request", "output"),
    [
        ("Explain the purpose of this function. Return JSON only.", '{"purpose": "increment"}'),
        ("What number does this function return? Return only a number.", "9"),
        ("이 함수의 목적을 설명해. JSON만 출력해.", '{"purpose": "increment"}'),
        ("이 함수가 반환하는 숫자는 무엇이니? 숫자 하나만 출력해.", "9"),
        ("Show the number returned by this function. Return only a number.", "9"),
        ("Write a summary of this function. Return JSON only.", '{"purpose": "increment"}'),
        ("Provide the purpose of this function. Return JSON only.", '{"purpose": "increment"}'),
        ("이 함수의 설명을 작성해. JSON만 출력해.", '{"purpose": "increment"}'),
        ("이 함수의 역할을 요약해서 제공해. JSON만 출력해.", '{"purpose": "increment"}'),
    ],
)
def test_gate_accepts_constrained_reply_when_function_is_description_subject(
    task_type: str, execution_mode: str | None, user_request: str, output: str
) -> None:
    # Given: a function explanation or result question with an explicit reply format.
    gate = QualityGate(max_retries=2)

    # When: the gate evaluates the response under the routed task label.
    result = gate.evaluate(task_type, user_request, output, execution_mode=execution_mode)

    # Then: mentioning a function does not impose a source-code output contract.
    assert result.should_retry is False
    assert result.grade in (QualityGrade.A, QualityGrade.B)


@pytest.mark.parametrize(
    ("user_request", "output"),
    [
        ("Write a Python function that emits JSON only.", '{"purpose": "increment"}'),
        ("숫자 하나만 반환하는 Python 함수를 작성해.", "9"),
        ("Give me a Python function that returns only a number.", "9"),
    ],
)
def test_gate_retries_when_requested_program_source_is_replaced_by_its_output(user_request: str, output: str) -> None:
    # Given: a request to write source code whose program has a scalar output format.
    gate = QualityGate(max_retries=2)

    # When: the assistant emits only the program's value under a noncoding label.
    result = gate.evaluate("reasoning", user_request, output)

    # Then: a shape-valid value cannot replace explicitly requested source code.
    assert result.should_retry is True
    assert result.grade in (QualityGrade.C, QualityGrade.F)


@pytest.mark.parametrize(
    ("user_request", "output"),
    [
        ("Return only the larger number.", "The larger number is 18."),
        ("숫자 하나만 출력해.", "7 9"),
        ("Return JSON only.", '{"result":}'),
        ("JSON만 출력해.", 'Result: {"result": 391}'),
        ("Return JSON only.", '```json\n{"result": 391}\n```'),
        ("JSON 형식만 출력해.", '{"result":}'),
        ("Return JSON only.", "NaN"),
        ("정수만 반환해.", "1.5"),
        ("숫자 하나만 출력해.", "| 첫 수 | 둘째 수 | 큰 수 |\n| --- | --- | --- |\n| 4 | 12 | 12 |"),
    ],
)
def test_gate_retries_when_explicit_output_shape_is_not_satisfied(user_request: str, output: str) -> None:
    # Given: an explicit output-format constraint violated by the response.
    gate = QualityGate(max_retries=2)

    # When: the gate evaluates the malformed or verbose response.
    result = gate.evaluate("reasoning", user_request, output)

    # Then: real format failures still trigger bounded quality recovery.
    assert result.should_retry is True
    assert result.grade in (QualityGrade.C, QualityGrade.F)


@pytest.mark.parametrize(
    ("task_type", "user_request", "output"),
    [
        (
            "coding",
            "Write a Python function that returns only a number. Code only.",
            "```python\ndef value() -> int:\n    return 18\n```",
        ),
        (
            "complex",
            "Write a Python function that emits JSON only. Code only.",
            "```python\ndef encode() -> str:\n    return '{\"ready\": true}'\n```",
        ),
    ],
)
def test_gate_keeps_code_contract_when_requested_program_emits_a_constrained_value(
    task_type: str, user_request: str, output: str
) -> None:
    # Given: a code-only request whose program has its own output contract.
    gate = QualityGate(max_retries=2)

    # When: the gate evaluates the source code in build mode.
    result = gate.evaluate(task_type, user_request, output, execution_mode="build")

    # Then: the program output format is not imposed on the assistant's source code.
    assert result.should_retry is False
    assert result.grade in (QualityGrade.A, QualityGrade.B)


def test_gate_retries_when_explicitly_requested_table_is_missing() -> None:
    # Given: a response that omits a requested comparison table.
    gate = QualityGate(max_retries=2)

    # When: the gate evaluates a prose comparison despite the requested table.
    result = gate.evaluate("chat", "Compare A and B in a table.", "A and B are equal.")

    # Then: an explicit missing structure still triggers recovery.
    assert result.should_retry is True
    assert result.grade in (QualityGrade.C, QualityGrade.F)


def test_semantic_verifier_can_reject_when_short_response_satisfies_output_shape() -> None:
    # Given: the verifier independently rejects a shape-valid answer.
    calls: list[str] = []

    def verify(prompt: str) -> str:
        calls.append(prompt)
        return "총점: 4"

    gate = QualityGate(max_retries=1, verify_fn=verify)

    # When: the response passes structural checks and reaches verification.
    result = gate.evaluate("reasoning", "Return only a number.", "18")

    # Then: the output contract cannot override semantic verification.
    assert len(calls) == 1
    assert result.should_retry is True
    assert result.grade is QualityGrade.C


@pytest.mark.parametrize("output", ["", "<think>private</think>18"])
def test_gate_retries_when_short_output_is_empty_or_leaks_internal_reasoning(output: str) -> None:
    # Given: short output with a concrete failure independent of its length.
    gate = QualityGate(max_retries=2)

    # When: the gate evaluates the bad response.
    result = gate.evaluate("chat", "Return only a number.", output)

    # Then: constrained-response handling does not bypass failure checks.
    assert result.should_retry is True
    assert result.grade in (QualityGrade.C, QualityGrade.F)


class _Model:
    def __init__(self, response: str) -> None:
        self.response = response
        self.generations = 0

    def generate(self, prompt: str, target: str, **kwargs: JsonValue) -> str:
        self.generations += 1
        return self.response


class _Context:
    cognitive_loop: None = None
    decision_anchor: None = None

    def __init__(self) -> None:
        self.quality_gate = QualityGate(max_retries=2)


class _Orchestrator:
    def __init__(self, project_root: Path, response: str) -> None:
        self.project_root = project_root
        self.manager = _Model(response)
        self.ctx = _Context()
        self.config: dict[str, JsonValue] = {}


def test_post_loop_preserves_constrained_reply_when_real_gate_has_no_failure(tmp_path: Path) -> None:
    from antigravity_k.engine.tool_loop import ToolLoopEngine

    # Given: the real gate and an adapter that would repeat the same draft.
    request = "두 숫자 7과 9를 비교해서 더 큰 숫자 하나만 출력해."
    orchestrator = _Orchestrator(tmp_path, "9")
    engine = ToolLoopEngine(orchestrator)

    # When: the production post-loop recovery evaluates the valid output shape.
    list(engine._post_loop_checks([{"role": "user", "content": request}], "chat", "9", request, "local"))

    # Then: no redundant model revisions run, and the concise reply is preserved.
    assert orchestrator.manager.generations == 0
    assert engine.last_output == "9"


@pytest.mark.parametrize(
    ("output", "expected_generations"), [("", 1), ('{"result":}', 2), ("<think>private</think>18", 2)]
)
def test_post_loop_keeps_bounded_recovery_when_real_gate_finds_a_concrete_failure(
    tmp_path: Path, output: str, expected_generations: int
) -> None:
    from antigravity_k.engine.tool_loop import ToolLoopEngine

    # Given: malformed output and an adapter whose rewrites cannot repair it.
    request = "Return JSON only."
    orchestrator = _Orchestrator(tmp_path, output)
    engine = ToolLoopEngine(orchestrator)

    # When: the production post-loop recovery runs with the real quality gate.
    list(engine._post_loop_checks([{"role": "user", "content": request}], "chat", output, request, "local"))

    # Then: failures get the configured two attempts and retain the best output.
    assert orchestrator.manager.generations == expected_generations
    assert engine.last_output == output
