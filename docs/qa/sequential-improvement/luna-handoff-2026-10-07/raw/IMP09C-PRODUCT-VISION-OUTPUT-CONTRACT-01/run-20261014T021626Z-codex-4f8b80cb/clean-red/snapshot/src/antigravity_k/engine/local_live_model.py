"""Loopback-only Ollama model port with digest pinning and raw inference trace."""

from __future__ import annotations

import json
import platform
import socket
from dataclasses import asdict, dataclass, field
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict

from antigravity_k.engine.cognitive.live_context import LIVE_MODEL_INPUT_BYTES
from antigravity_k.engine.cognitive.live_pilot import LiveTrialRequest, LiveTrialTimeout, ProviderAttestation
from antigravity_k.engine.cognitive.live_trial_types import ModelChoice, ModelTask


class LocalModelError(RuntimeError):
    """Unavailable local provider or invalid provider response."""


class ModelTag(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    digest: str


class ModelTags(BaseModel):
    model_config = ConfigDict(frozen=True)
    models: tuple[ModelTag, ...]


class RunningModel(ModelTag):
    context_length: int


class RunningModels(BaseModel):
    models: tuple[RunningModel, ...]


class GeneratedText(BaseModel):
    model_config = ConfigDict(frozen=True)
    response: str
    prompt_eval_count: int = 0
    eval_count: int = 0


class GeneratedChoice(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    append_content: str
    expand_missing: bool = False
    ground_refs: tuple[str, ...] = ()


@dataclass
class LocalOllamaModelPort:
    """Owns local inference counters; endpoint cannot be redirected off loopback."""

    model_id: str
    trace_path: Path
    timeout_seconds: float = 45
    attestation: ProviderAttestation = field(init=False)

    def __post_init__(self) -> None:
        digest = self._digest()
        self.attestation = ProviderAttestation(
            provider_id="ollama-loopback",
            model_id=self.model_id,
            model_snapshot=digest,
            decoding="temperature=0;seed=20260927;num_predict=512;num_ctx=40960;input_bytes=32768;think=false",
            hardware=f"{platform.system()} {platform.machine()}",
            snapshot_pinned=True,
            reproducibility_limits=("Local model inference over synthetic tasks; not a general capability claim",),
        )

    def _client(self) -> httpx.Client:
        # The repository explicitly depends on httpx; do not introduce another HTTP stack.
        transport = httpx.HTTPTransport(
            retries=0,
            limits=httpx.Limits(max_connections=200, max_keepalive_connections=40, keepalive_expiry=30),
            socket_options=[(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)],
        )
        return httpx.Client(
            base_url="http://127.0.0.1:11434",
            transport=transport,
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(connect=3, read=self.timeout_seconds, write=10, pool=10),
        )

    def _digest(self) -> str:
        with self._client() as client:
            response = client.get("/api/tags")
            response.raise_for_status()
            tags = ModelTags.model_validate_json(response.content)
        for tag in tags.models:
            if tag.name == self.model_id:
                return tag.digest
        raise LocalModelError(f"Model is not installed locally: {self.model_id}")

    def choose(
        self, request: LiveTrialRequest, task: ModelTask, *, missing_refs: tuple[str, ...], workspace: Path
    ) -> ModelChoice:
        if self._digest() != self.attestation.model_snapshot:
            raise LocalModelError("Local model digest changed after preregistration")
        task_wire = asdict(task)
        if len(json.dumps(task_wire, ensure_ascii=False).encode()) > LIVE_MODEL_INPUT_BYTES:
            raise LocalModelError("ModelTask exceeds preregistered input byte budget")
        prompt = (
            "You execute a synthetic append task. Return JSON with append_content and expand_missing. "
            "The append line is the task_id followed by a space and the word appended. "
            "Do not include a newline. Include ground_refs listing evidence IDs you used from task.evidence. If required evidence is missing, request expansion using "
            "expand_missing=true. Use only the supplied context.\n"
            + json.dumps({"task": task_wire, "missing_refs": missing_refs}, sort_keys=True, ensure_ascii=False)
        )
        payload = {
            "model": self.model_id,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "format": GeneratedChoice.model_json_schema(),
            "options": {"temperature": 0, "seed": 20260927, "num_predict": 512, "num_ctx": 40960},
        }
        input_bytes = len(prompt.encode()) + len(json.dumps(payload["format"]).encode())
        if input_bytes + 512 + 2048 > 40960:
            raise LocalModelError("Prompt/schema/output reserve exceeds preregistered context window")
        try:
            with self._client() as client:
                response = client.post("/api/generate", json=payload)
                response.raise_for_status()
                generated = GeneratedText.model_validate_json(response.content)
        except httpx.TimeoutException as error:
            raise LiveTrialTimeout(str(error)) from error
        with self._client() as client:
            running_response = client.get("/api/ps")
            running_response.raise_for_status()
            running = RunningModels.model_validate_json(running_response.content)
        loaded_context = next(
            (
                item.context_length
                for item in running.models
                if item.name == self.model_id and item.digest == self.attestation.model_snapshot
            ),
            None,
        )
        self.trace_path.parent.mkdir(parents=True, exist_ok=True)
        with self.trace_path.open("a", encoding="utf-8") as trace:
            trace.write(
                json.dumps(
                    {
                        "request": request.as_mapping(),
                        "input": payload,
                        "input_bytes": input_bytes,
                        "loaded_context_length": loaded_context,
                        "output": generated.model_dump(),
                    },
                    sort_keys=True,
                )
                + "\n"
            )
        if loaded_context != 40960:
            raise LocalModelError("Provider did not confirm the preregistered context window")
        choice = GeneratedChoice.model_validate_json(generated.response)
        if any(ref not in task.evidence for ref in choice.ground_refs):
            raise LocalModelError("Model cited evidence outside the supplied context")
        return ModelChoice(
            append_content=choice.append_content,
            expand_missing=choice.expand_missing,
            detail="local Ollama inference",
            ground_refs=choice.ground_refs,
            tokens=generated.prompt_eval_count + generated.eval_count,
        )
