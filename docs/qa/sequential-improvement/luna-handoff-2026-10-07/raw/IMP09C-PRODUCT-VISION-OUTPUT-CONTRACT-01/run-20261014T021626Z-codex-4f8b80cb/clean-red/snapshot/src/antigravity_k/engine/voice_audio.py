from __future__ import annotations

from dataclasses import dataclass
from typing import Final, override

_RIFF_HEADER_BYTES: Final = 12
_CHUNK_HEADER_BYTES: Final = 8
_PCM_FORMAT_CODE: Final = 1
_IEEE_FLOAT_FORMAT_CODE: Final = 3
_SUPPORTED_PCM_BITS: Final[frozenset[int]] = frozenset({8, 16, 24, 32})
_SUPPORTED_IEEE_FLOAT_BITS: Final[frozenset[int]] = frozenset({32, 64})


class MalformedWaveError(ValueError):
    detail: str

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)

    @override
    def __str__(self) -> str:
        return f"invalid WAV: {self.detail}"


class UnsupportedWaveEncodingError(ValueError):
    format_code: int

    def __init__(self, format_code: int) -> None:
        self.format_code = format_code
        super().__init__(format_code)

    @override
    def __str__(self) -> str:
        return f"unsupported WAV encoding: format code {self.format_code}"


@dataclass(frozen=True, slots=True)
class WaveAudio:
    channels: int
    sample_rate: int
    block_align: int
    bits_per_sample: int
    data_bytes: int


def validate_audio_for_suffix(audio: bytes, suffix: str) -> WaveAudio | None:
    if suffix.casefold() != ".wav":
        return None
    return validate_wav(audio)


def validate_wav(audio: bytes) -> WaveAudio:
    if len(audio) < _RIFF_HEADER_BYTES:
        raise MalformedWaveError("header is truncated")
    if audio[:4] != b"RIFF":
        raise MalformedWaveError("missing RIFF signature")
    if audio[8:12] != b"WAVE":
        raise MalformedWaveError("missing WAVE signature")

    reported_size = int.from_bytes(audio[4:8], byteorder="little")
    if reported_size + _CHUNK_HEADER_BYTES != len(audio):
        raise MalformedWaveError("reported RIFF size does not match body length")

    offset = _RIFF_HEADER_BYTES
    metadata: WaveAudio | None = None
    data_chunk_sizes: list[int] = []
    while offset < len(audio):
        if len(audio) - offset < _CHUNK_HEADER_BYTES:
            raise MalformedWaveError("chunk header is truncated")
        chunk_id = audio[offset : offset + 4]
        chunk_size = int.from_bytes(audio[offset + 4 : offset + _CHUNK_HEADER_BYTES], byteorder="little")
        chunk_start = offset + _CHUNK_HEADER_BYTES
        chunk_end = chunk_start + chunk_size
        padded_chunk_end = chunk_end + (chunk_size % 2)
        if padded_chunk_end > len(audio):
            raise MalformedWaveError("chunk extends beyond the body")

        if chunk_id == b"fmt ":
            if metadata is not None:
                raise MalformedWaveError("duplicate fmt chunk")
            metadata = _parse_format_chunk(audio[chunk_start:chunk_end])
        elif chunk_id == b"data":
            if chunk_size == 0:
                raise MalformedWaveError("audio data chunk is empty")
            data_chunk_sizes.append(chunk_size)
        offset = padded_chunk_end

    if metadata is None:
        raise MalformedWaveError("missing fmt chunk")
    if not data_chunk_sizes:
        raise MalformedWaveError("missing audio data chunk")
    if any(chunk_size % metadata.block_align != 0 for chunk_size in data_chunk_sizes):
        raise MalformedWaveError("data chunk is not aligned to the reported block alignment")
    return WaveAudio(
        channels=metadata.channels,
        sample_rate=metadata.sample_rate,
        block_align=metadata.block_align,
        bits_per_sample=metadata.bits_per_sample,
        data_bytes=sum(data_chunk_sizes),
    )


def _parse_format_chunk(chunk: bytes) -> WaveAudio:
    if len(chunk) < 16:
        raise MalformedWaveError("fmt chunk is truncated")
    format_code = int.from_bytes(chunk[:2], byteorder="little")
    channels = int.from_bytes(chunk[2:4], byteorder="little")
    sample_rate = int.from_bytes(chunk[4:8], byteorder="little")
    byte_rate = int.from_bytes(chunk[8:12], byteorder="little")
    block_align = int.from_bytes(chunk[12:14], byteorder="little")
    bits_per_sample = int.from_bytes(chunk[14:16], byteorder="little")
    if format_code == _PCM_FORMAT_CODE:
        if bits_per_sample not in _SUPPORTED_PCM_BITS:
            raise MalformedWaveError("PCM bit depth must be 8, 16, 24, or 32")
    elif format_code == _IEEE_FLOAT_FORMAT_CODE:
        if bits_per_sample not in _SUPPORTED_IEEE_FLOAT_BITS:
            raise MalformedWaveError("IEEE float bit depth must be 32 or 64")
    else:
        raise UnsupportedWaveEncodingError(format_code)
    if channels == 0 or sample_rate == 0 or block_align == 0 or bits_per_sample == 0:
        raise MalformedWaveError("fmt chunk contains a zero channel, rate, block alignment, or bit depth")
    expected_block_align = channels * ((bits_per_sample + 7) // 8)
    if block_align != expected_block_align:
        raise MalformedWaveError("reported block alignment does not match channels and bit depth")
    if byte_rate != sample_rate * block_align:
        raise MalformedWaveError("reported byte rate does not match sample rate and block alignment")
    return WaveAudio(
        channels=channels,
        sample_rate=sample_rate,
        block_align=block_align,
        bits_per_sample=bits_per_sample,
        data_bytes=0,
    )


__all__ = [
    "MalformedWaveError",
    "UnsupportedWaveEncodingError",
    "WaveAudio",
    "validate_audio_for_suffix",
    "validate_wav",
]
