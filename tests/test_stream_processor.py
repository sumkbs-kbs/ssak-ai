import pytest

from antigravity_k.engine.stream_processor import StreamProcessor


def test_stream_processor_suppresses_complete_think_block():
    processor = StreamProcessor()

    output, is_repeat = processor.process_text("앞<think>secret plan</think>뒤")

    assert is_repeat is False
    assert output == "앞뒤"
    assert "secret" not in output
    assert "Thinking Process" not in output


def test_stream_processor_suppresses_split_think_block():
    processor = StreamProcessor()

    first, _ = processor.process_text("앞<think>secret plan")
    second, _ = processor.process_text("</think>뒤")

    combined = first + second
    assert combined == "앞뒤"
    assert "secret" not in combined
    assert "Thinking Process" not in combined


def test_stream_processor_flush_suppresses_unclosed_thought_block():
    processor = StreamProcessor()

    output = processor.process_flush_text("사용자 답변<thought>internal plan")

    assert output == "사용자 답변"
    assert "internal plan" not in output


@pytest.mark.parametrize(
    "chunks",
    [
        ["alpha", " ", "beta"],
        ["45", "\n", "78", "\n", "96", "\n", "97", "\n", "98"],
        ["# 제목", "\n\n", "- 항목", "\n", "- 다음", "\n\n", "```python", "\n", "print(1)", "\n", "```", "\n"],
        ["\n", "한국어", " ", "설명", "\n", "日本語", "\n"],
    ],
)
def test_content_whitespace_chunks_preserve_provider_format(chunks: list[str]) -> None:
    processor = StreamProcessor()

    rendered = "".join(processor.process_text(chunk)[0] for chunk in chunks)
    rendered += processor.process_flush_text("")

    assert rendered == "".join(chunks)
    assert processor.repetition_detected is False


@pytest.mark.parametrize("tail", [" ", "\n", "\n\t "])
def test_flush_preserves_whitespace_only_content(tail: str) -> None:
    processor = StreamProcessor()

    assert processor.process_flush_text(tail) == tail


def test_hidden_thoughts_and_scratchpad_do_not_leak_with_visible_whitespace() -> None:
    processor = StreamProcessor()
    chunks = [
        "앞",
        "<think>",
        "private thought",
        "\n",
        "</think>",
        "\n",
        "<scratch_pad>",
        "private scratchpad",
        "\n",
        "</scratch_pad>",
        "%%THINK_START%%",
        "%%THINK_END%%",
        "뒤",
    ]

    rendered = "".join(processor.process_text(chunk)[0] for chunk in chunks)
    rendered += processor.process_flush_text("")

    assert rendered == "앞\n뒤"
    assert "private" not in rendered
    assert "%%" not in rendered


def test_whitespace_does_not_disable_repetition_detection() -> None:
    processor = StreamProcessor()
    repeated = "repeated visible content " * 4

    processor.process_text(repeated)
    processor.process_text("\n")
    processor.process_text(repeated)
    processor.process_text(" ")
    _, is_repeat = processor.process_text(repeated)

    assert is_repeat is True
