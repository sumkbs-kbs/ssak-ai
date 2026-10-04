from __future__ import annotations

from typing import Annotated, ClassVar, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from antigravity_k.api.dependencies import get_scheduled_job_service, get_voice_service
from antigravity_k.engine.scheduled_job_models import JobCreate, JobSchedule, utc_now
from antigravity_k.engine.voice_audio import MalformedWaveError, UnsupportedWaveEncodingError, validate_audio_for_suffix
from antigravity_k.engine.voice_service import VoiceExecutionError, VoiceUnavailableError

router = APIRouter(prefix="/api/voice")
_MAX_AUDIO_BYTES = 25 * 1024 * 1024


class VoiceTranscript(BaseModel):
    transcript: str


class VoiceCommandAccepted(BaseModel):
    status: Literal["accepted"] = "accepted"
    transcript: str
    job_id: str
    run_id: str
    task_id: str | None


class VoiceSpeakRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(min_length=1, max_length=20_000)

    @field_validator("text")
    @classmethod
    def strip_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("text must not be blank")
        return normalized


async def _audio_body(request: Request) -> bytes:
    chunks: list[bytes] = []
    total_bytes = 0
    async for chunk in request.stream():
        total_bytes += len(chunk)
        if total_bytes > _MAX_AUDIO_BYTES:
            raise HTTPException(status_code=413, detail="Audio body exceeds 25 MiB")
        if chunk:
            chunks.append(chunk)
    audio = b"".join(chunks)
    if not audio:
        raise HTTPException(status_code=422, detail="Audio body must not be empty")
    return audio


def _validate_audio(audio: bytes, suffix: str) -> bytes:
    try:
        _ = validate_audio_for_suffix(audio, suffix)
    except (MalformedWaveError, UnsupportedWaveEncodingError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return audio


def _transcribe(audio: bytes, suffix: str) -> str:
    try:
        return get_voice_service().transcribe(audio, suffix)
    except VoiceUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except VoiceExecutionError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/transcribe", response_model=VoiceTranscript)
async def transcribe_voice(
    request: Request,
    suffix: Annotated[str, Query(pattern=r"^\.[A-Za-z0-9]{1,8}$")] = ".wav",
) -> VoiceTranscript:
    transcript = _transcribe(_validate_audio(await _audio_body(request), suffix), suffix)
    return VoiceTranscript(transcript=transcript)


@router.post("/commands", response_model=VoiceCommandAccepted, status_code=status.HTTP_202_ACCEPTED)
async def submit_voice_command(
    request: Request,
    suffix: Annotated[str, Query(pattern=r"^\.[A-Za-z0-9]{1,8}$")] = ".wav",
    model: Annotated[str, Query(max_length=200)] = "",
) -> VoiceCommandAccepted:
    transcript = _transcribe(_validate_audio(await _audio_body(request), suffix), suffix)
    service = get_scheduled_job_service()
    now = utc_now()
    job = service.create_job(
        JobCreate(
            name="voice:local",
            prompt=transcript,
            model=model,
            context={"gateway": {"channel": "voice", "sender_id": "local"}},
            context_mode="continue",
            schedule=JobSchedule(kind="once", run_at=now),
        ),
        now=now,
    )
    run = service.trigger_job(job.job_id, now=now)
    return VoiceCommandAccepted(
        transcript=transcript,
        job_id=job.job_id,
        run_id=run.run_id,
        task_id=run.task_id,
    )


@router.post("/speak", response_class=Response)
def synthesize_voice(request: VoiceSpeakRequest) -> Response:
    try:
        audio = get_voice_service().synthesize(request.text)
    except VoiceUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except VoiceExecutionError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return Response(content=audio, media_type="audio/aiff")


__all__ = ["router"]
