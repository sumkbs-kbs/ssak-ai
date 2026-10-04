from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import JsonValue

from antigravity_k.engine.chat_stream_events import ProgressChunk
from antigravity_k.engine.quality_gate import QualityGate
from antigravity_k.engine.stream_processor import StreamProcessor
from tests.test_quality_context_approval import _Model, _Orchestrator


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)


class _ChunkedModel(_Model):
    def __init__(self, chunks: list[str]) -> None:
        super().__init__("unused")
        self.chunks = chunks

    def stream_generate(self, **kwargs: JsonValue) -> Iterator[str]:
        yield from self.chunks


class _DeferredWhitespaceProcessor(StreamProcessor):
    def __init__(self) -> None:
        super().__init__()
        self.tail = ""

    def process_text(self, text: str) -> tuple[str, bool]:
        combined = self.tail + text
        body = combined.rstrip()
        self.tail = combined[len(body) :]
        return super().process_text(body)

    def process_flush_text(self, text: str) -> str:
        combined, self.tail = self.tail + text, ""
        return super().process_flush_text(combined)


@pytest.mark.parametrize("deferred_flush", [False, True])
def test_real_tool_loop_preserves_provider_whitespace_through_stream_and_flush(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, deferred_flush: bool
) -> None:
    from antigravity_k.engine import stream_processor
    from antigravity_k.engine.tool_loop import ToolLoopEngine

    chunks = ["# 제목", "\n\n", "- 항목", "\n", "```python", "\n", "print(1)", "\n", "```", "\n\t "]
    orch = _Orchestrator(tmp_path, "unused")
    monkeypatch.setattr(orch, "manager", _ChunkedModel(chunks))
    monkeypatch.setattr(orch.ctx, "quality_gate", QualityGate(max_retries=0))
    if deferred_flush:
        monkeypatch.setattr(stream_processor, "StreamProcessor", _DeferredWhitespaceProcessor)
    engine = ToolLoopEngine(orch)

    emitted = list(engine.run_loop([{"role": "user", "content": "render source text"}], "SELF", "chat"))

    content = "".join(chunk for chunk in emitted if not isinstance(chunk, ProgressChunk))
    assert content == "".join(chunks)
    assert engine.last_output == "".join(chunks)


def test_real_tool_loop_hides_thoughts_and_tool_markup_while_preserving_approval_pause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from antigravity_k.engine.tool_loop import ToolLoopEngine

    chunks = [
        "<think>",
        "private thought",
        "\n",
        "</think>",
        "visible",
        "\n",
        '<tool_call>{"name":"write_artifact","arguments":{}}</tool_call>',
    ]
    orch = _Orchestrator(tmp_path, "unused")
    monkeypatch.setattr(orch, "manager", _ChunkedModel(chunks))
    engine = ToolLoopEngine(orch)

    emitted = list(engine.run_loop([{"role": "user", "content": "create an artifact"}], "SELF", "chat"))

    content = "".join(chunk for chunk in emitted if not isinstance(chunk, ProgressChunk))
    assert content.startswith("visible\n")
    assert "private thought" not in content
    assert "<tool_call>" not in content
    assert engine.approval_required is True
    assert any(isinstance(chunk, ProgressChunk) for chunk in emitted)
