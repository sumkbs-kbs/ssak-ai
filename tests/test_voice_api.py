import os
import struct
import tempfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

_TEST_HOME = Path(tempfile.mkdtemp(prefix="agk-voice-test-home-"))
os.environ["HOME"] = str(_TEST_HOME)

from antigravity_k.api.routes import voice_api
from antigravity_k.engine.scheduled_job_service import ScheduledJobService
from antigravity_k.engine.scheduled_job_store import ScheduledJobStore
from antigravity_k.engine.voice_service import VoiceService


class TranscriberSpy:
    def __init__(self) -> None:
        self.calls: list[tuple[bytes, str]] = []

    def __call__(self, audio: bytes, suffix: str) -> str:
        self.calls.append((audio, suffix))
        return "오늘 할 일을 정리해줘"


def _synthesize(text: str) -> bytes:
    assert text == "완료했습니다"
    return b"aiff-bytes"


def _wav(format_code: int, bits_per_sample: int, payload: bytes) -> bytes:
    block_align = (bits_per_sample + 7) // 8
    fmt = struct.pack("<HHIIHH", format_code, 1, 16_000, 16_000 * block_align, block_align, bits_per_sample)
    chunks = b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(payload)) + payload
    return b"RIFF" + struct.pack("<I", len(chunks) + 4) + b"WAVE" + chunks


def _pcm_wav(payload: bytes = b"\x00\x00") -> bytes:
    return _wav(1, 16, payload)


class FakeRuntime:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def submit_task(self, **kwargs: object) -> str:
        self.calls.append(kwargs)
        return "task-voice-1"

    def get_task_status(self, task_id: str) -> dict[str, object]:
        return {"task_id": task_id, "status": "done", "output": "voice result"}


@pytest.fixture
def voice_fixture(monkeypatch: pytest.MonkeyPatch) -> TranscriberSpy:
    transcriber = TranscriberSpy()
    voice_service = VoiceService(transcriber=transcriber, synthesizer=_synthesize)
    monkeypatch.setattr(voice_api, "get_voice_service", lambda: voice_service)
    return transcriber


@pytest.fixture
def runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, voice_fixture: TranscriberSpy) -> FakeRuntime:
    _ = voice_fixture
    fake = FakeRuntime()
    jobs = ScheduledJobService(
        ScheduledJobStore(str(tmp_path / "jobs.db")),
        fake.submit_task,
        fake.get_task_status,
    )
    monkeypatch.setattr(voice_api, "get_scheduled_job_service", lambda: jobs)
    return fake


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(voice_api.router)
    return TestClient(app)


def test_voice_transcription_endpoint_uses_validated_wav(
    client: TestClient, runtime: FakeRuntime, voice_fixture: TranscriberSpy
) -> None:
    audio = _pcm_wav()
    response = client.post(
        "/api/voice/transcribe?suffix=.wav",
        content=audio,
        headers={"Content-Type": "audio/wav"},
    )

    assert response.status_code == 200
    assert response.json() == {"transcript": "오늘 할 일을 정리해줘"}
    assert voice_fixture.calls == [(audio, ".wav")]
    assert runtime.calls == []


def test_voice_transcription_accepts_valid_ieee_float_wav(client: TestClient, voice_fixture: TranscriberSpy) -> None:
    audio = _wav(3, 32, b"\x00" * 4)

    response = client.post("/api/voice/transcribe?suffix=.wav", content=audio)

    assert response.status_code == 200
    assert voice_fixture.calls == [(audio, ".wav")]


def test_voice_transcription_reads_stream_without_request_body(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, voice_fixture: TranscriberSpy
) -> None:
    async def forbidden_body(_: Request) -> bytes:
        raise AssertionError("request.body must not be called")

    monkeypatch.setattr(Request, "body", forbidden_body)
    audio = _pcm_wav()

    response = client.post("/api/voice/transcribe?suffix=.wav", content=audio)

    assert response.status_code == 200
    assert voice_fixture.calls == [(audio, ".wav")]


def test_voice_transcription_rejects_malformed_wav_before_transcription(
    client: TestClient, voice_fixture: TranscriberSpy
) -> None:
    response = client.post(
        "/api/voice/transcribe?suffix=.wav",
        content=b"RIFF\x24\x00\x00\x00WAVEfmt ",
        headers={"Content-Type": "audio/wav"},
    )

    assert response.status_code == 422
    assert "WAV" in response.json()["detail"]
    assert voice_fixture.calls == []


def test_voice_transcription_rejects_bad_chunk_before_transcription(
    client: TestClient, voice_fixture: TranscriberSpy
) -> None:
    audio = (
        b"RIFF" + (14).to_bytes(4, byteorder="little") + b"WAVEdata" + (4).to_bytes(4, byteorder="little") + b"\x00\x00"
    )

    response = client.post("/api/voice/transcribe?suffix=.wav", content=audio)

    assert response.status_code == 422
    assert "WAV" in response.json()["detail"]
    assert voice_fixture.calls == []


def test_voice_transcription_rejects_empty_body_before_transcription(
    client: TestClient, voice_fixture: TranscriberSpy
) -> None:
    response = client.post("/api/voice/transcribe?suffix=.wav", content=b"")

    assert response.status_code == 422
    assert response.json() == {"detail": "Audio body must not be empty"}
    assert voice_fixture.calls == []


def test_voice_transcription_rejects_oversize_body_before_transcription(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, voice_fixture: TranscriberSpy
) -> None:
    monkeypatch.setattr(voice_api, "_MAX_AUDIO_BYTES", 32)

    response = client.post("/api/voice/transcribe?suffix=.wav", content=b"x" * 33)

    assert response.status_code == 413
    assert response.json() == {"detail": "Audio body exceeds 25 MiB"}
    assert voice_fixture.calls == []


def test_voice_transcription_preserves_suffix_query_validation(
    client: TestClient, voice_fixture: TranscriberSpy
) -> None:
    response = client.post("/api/voice/transcribe?suffix=wav", content=_pcm_wav())

    assert response.status_code == 422
    assert voice_fixture.calls == []


def test_voice_transcription_preserves_non_wav_browser_audio(client: TestClient, voice_fixture: TranscriberSpy) -> None:
    audio = b"browser-media"

    response = client.post("/api/voice/transcribe?suffix=.webm", content=audio)

    assert response.status_code == 200
    assert voice_fixture.calls == [(audio, ".webm")]


def test_voice_command_submits_transcript_to_jarvis(
    client: TestClient, runtime: FakeRuntime, voice_fixture: TranscriberSpy
) -> None:
    audio = _pcm_wav()
    response = client.post(
        "/api/voice/commands?suffix=.wav&model=qwen3.8:27b",
        content=audio,
        headers={"Content-Type": "audio/wav"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["transcript"] == "오늘 할 일을 정리해줘"
    assert body["task_id"] == "task-voice-1"
    assert runtime.calls[0]["target_model"] == "qwen3.8:27b"
    assert voice_fixture.calls == [(audio, ".wav")]


def test_voice_synthesis_returns_playable_audio(client: TestClient, runtime: FakeRuntime) -> None:
    response = client.post("/api/voice/speak", json={"text": "완료했습니다"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/aiff"
    assert response.content == b"aiff-bytes"
    assert runtime.calls == []
