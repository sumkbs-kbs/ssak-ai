import struct

import pytest

from antigravity_k.engine.voice_audio import (
    MalformedWaveError,
    UnsupportedWaveEncodingError,
    WaveAudio,
    validate_audio_for_suffix,
    validate_wav,
)


def _chunk(name: bytes, payload: bytes) -> bytes:
    padding = b"\x00" if len(payload) % 2 else b""
    return name + struct.pack("<I", len(payload)) + payload + padding


def _wav(
    *,
    format_code: int = 1,
    bits_per_sample: int = 16,
    data_chunks: tuple[bytes, ...] = (b"\x00\x00",),
    extra_chunks: tuple[bytes, ...] = (),
    riff_size: int | None = None,
) -> bytes:
    block_align = (bits_per_sample + 7) // 8
    fmt = struct.pack("<HHIIHH", format_code, 1, 16_000, 16_000 * block_align, block_align, bits_per_sample)
    chunks = (
        _chunk(b"fmt ", fmt) + b"".join(extra_chunks) + b"".join(_chunk(b"data", payload) for payload in data_chunks)
    )
    reported_size = len(chunks) + 4 if riff_size is None else riff_size
    return b"RIFF" + struct.pack("<I", reported_size) + b"WAVE" + chunks


def test_validate_wav_returns_pcm_metadata_for_complete_riff_wave() -> None:
    audio = _wav()

    result = validate_wav(audio)

    assert result == WaveAudio(channels=1, sample_rate=16_000, block_align=2, bits_per_sample=16, data_bytes=2)


def test_validate_wav_rejects_truncated_chunk() -> None:
    audio = b"RIFF\x24\x00\x00\x00WAVEfmt "

    with pytest.raises(MalformedWaveError, match="WAV"):
        _ = validate_wav(audio)


def test_validate_wav_rejects_reported_riff_size_that_does_not_match_body() -> None:
    audio = _wav(riff_size=4)

    with pytest.raises(MalformedWaveError, match="RIFF"):
        _ = validate_wav(audio)


def test_validate_wav_rejects_empty_data_chunk() -> None:
    audio = _wav(data_chunks=(b"",))

    with pytest.raises(MalformedWaveError, match="audio data"):
        _ = validate_wav(audio)


@pytest.mark.parametrize("bits_per_sample", [32, 64])
def test_validate_wav_accepts_supported_ieee_float_audio(bits_per_sample: int) -> None:
    audio = _wav(format_code=3, bits_per_sample=bits_per_sample, data_chunks=(b"\x00" * (bits_per_sample // 8),))

    result = validate_wav(audio)

    assert result.bits_per_sample == bits_per_sample


def test_validate_wav_rejects_unsupported_compressed_encoding() -> None:
    audio = _wav(format_code=6)

    with pytest.raises(UnsupportedWaveEncodingError, match="format code 6"):
        _ = validate_wav(audio)


def test_validate_wav_rejects_unsupported_float_bit_depth() -> None:
    audio = _wav(format_code=3, bits_per_sample=16)

    with pytest.raises(MalformedWaveError, match="IEEE float"):
        _ = validate_wav(audio)


def test_validate_wav_rejects_unsupported_pcm_bit_depth() -> None:
    audio = _wav(bits_per_sample=12, data_chunks=(b"\x00\x00",))

    with pytest.raises(MalformedWaveError, match="PCM"):
        _ = validate_wav(audio)


def test_validate_wav_rejects_duplicate_format_chunk() -> None:
    duplicate_format = _chunk(b"fmt ", struct.pack("<HHIIHH", 1, 1, 16_000, 32_000, 2, 16))
    audio = _wav(extra_chunks=(duplicate_format,))

    with pytest.raises(MalformedWaveError, match="duplicate fmt"):
        _ = validate_wav(audio)


def test_validate_wav_rejects_individually_misaligned_data_chunks() -> None:
    audio = _wav(data_chunks=(b"\x00", b"\x00"))

    with pytest.raises(MalformedWaveError, match="data chunk"):
        _ = validate_wav(audio)


def test_validate_audio_for_suffix_preserves_non_wav_browser_audio() -> None:
    audio = b"browser-recording"

    result = validate_audio_for_suffix(audio, ".webm")

    assert result is None
