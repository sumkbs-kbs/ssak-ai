from antigravity_k.engine.chat_stream_events import FinalChunk, ProgressChunk
from antigravity_k.engine.language_normalizer import normalize_streaming_chunks


def test_normalizer_preserves_progress_and_authoritative_final_channels() -> None:
    progress = ProgressChunk("working")
    final = FinalChunk('{"total":35140}')
    chunks = list(normalize_streaming_chunks(iter(["draft", progress, final])))
    assert chunks == ["draft", "working", '{"total":35140}']
    assert chunks[1] is progress
    assert chunks[2] is final


def test_progress_does_not_break_normalization_across_content_chunks() -> None:
    chunks = list(normalize_streaming_chunks(iter(["复", ProgressChunk("working"), "杂度"])))
    assert "".join(chunk for chunk in chunks if not isinstance(chunk, ProgressChunk)) == "복잡도"
