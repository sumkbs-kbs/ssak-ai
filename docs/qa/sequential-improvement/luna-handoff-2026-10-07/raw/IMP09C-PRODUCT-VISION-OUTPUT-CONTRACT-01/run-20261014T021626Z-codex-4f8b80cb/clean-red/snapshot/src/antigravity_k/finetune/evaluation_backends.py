from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from importlib import import_module
from pathlib import Path
from typing import ClassVar, Protocol, TypedDict, final, override, runtime_checkable
from urllib.request import Request

from pydantic import BaseModel, ConfigDict

from antigravity_k.finetune.evaluation import CandidateKind, EvaluationCase
from antigravity_k.finetune.evaluation_mlx_sampler import (
    MlxGenerate,
    MlxHandle,
    MlxSamplerError,
    make_mlx_sampler,
)
from antigravity_k.tools.egress_policy import safe_urlopen


class EvaluationInferenceError(RuntimeError):
    __slots__: ClassVar[tuple[str, ...]] = ("reason",)
    reason: str

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason

    @override
    def __str__(self) -> str:
        return self.reason


class EvaluationBackend(StrEnum):
    MLX = "mlx"
    OLLAMA = "ollama"


@runtime_checkable
class MlxLoaded(Protocol):
    def __len__(self) -> int: ...

    def __getitem__(self, index: int) -> MlxHandle: ...


@dataclass(frozen=True, slots=True)
class MlxCandidate:
    model: MlxHandle
    tokenizer: MlxHandle

    def __len__(self) -> int:
        return 2

    def __getitem__(self, index: int) -> MlxHandle:
        return (self.model, self.tokenizer)[index]


class MlxLoad(Protocol):
    def __call__(
        self,
        *,
        path_or_hf_repo: str | None,
        revision: str | None = None,
        adapter_path: str | None = None,
    ) -> MlxLoaded: ...


class MlxCandidateLoad(Protocol):
    def __call__(
        self,
        *,
        path_or_hf_repo: str | None = None,
        revision: str | None = None,
        adapter_path: str | None = None,
    ) -> MlxCandidate: ...


class MlxRuntime(Protocol):
    load: MlxCandidateLoad

    generate: MlxGenerate


@runtime_checkable
class MlxModule(Protocol):
    load: MlxLoad

    generate: MlxGenerate


class OllamaChatMessage(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="allow")

    content: str


class OllamaChatResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="allow")

    message: OllamaChatMessage


class OllamaChatOptions(TypedDict):
    num_predict: int
    temperature: float


class OllamaChatRequest(TypedDict):
    model: str
    messages: list[dict[str, str]]
    stream: bool
    think: bool
    options: OllamaChatOptions


class RequestBody(Protocol):
    @property
    def data(self) -> bytes: ...

    @property
    def full_url(self) -> str: ...


class RequestResponse(Protocol):
    def read(self) -> bytes: ...


class RequestOpener(Protocol):
    def __call__(self, request: RequestBody, timeout: float) -> RequestResponse: ...


@final
class _OllamaRequest:
    url: str
    body: bytes

    def __init__(self, url: str, body: bytes) -> None:
        self.url = url
        self.body = body

    @property
    def data(self) -> bytes:
        return self.body

    @property
    def full_url(self) -> str:
        return self.url


@final
class MlxEvaluationInference:
    base_model: str
    base_revision: str
    adapter_path: Path
    max_tokens: int
    temperature: float
    runtime: MlxRuntime
    candidates: dict[CandidateKind, MlxCandidate] | None

    def __init__(
        self,
        *,
        base_model: str,
        base_revision: str,
        adapter_path: Path,
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> None:
        self.base_model = base_model
        self.base_revision = base_revision
        self.adapter_path = adapter_path
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.runtime = _load_mlx_runtime()
        self.candidates = None

    def __call__(self, case: EvaluationCase, kind: CandidateKind) -> str:
        if self.candidates is None:
            self.candidates = {
                CandidateKind.BASE: self.runtime.load(
                    path_or_hf_repo=self.base_model,
                    revision=self.base_revision,
                ),
                CandidateKind.TUNED: self.runtime.load(
                    path_or_hf_repo=self.base_model,
                    adapter_path=str(self.adapter_path),
                ),
            }
        selected = self.candidates[kind]
        try:
            sampler = make_mlx_sampler(self.temperature)
        except MlxSamplerError as error:
            raise EvaluationInferenceError(str(error)) from error
        output = self.runtime.generate(
            model=selected.model,
            tokenizer=selected.tokenizer,
            prompt=case.prompt,
            max_tokens=self.max_tokens,
            sampler=sampler,
        )
        if not output:
            raise EvaluationInferenceError(f"MLX {kind.value} evaluation returned no content.")
        return output


@final
class OllamaEvaluationInference:
    endpoint: str
    base_model: str
    tuned_model: str
    max_tokens: int
    temperature: float
    request_opener: RequestOpener

    def __init__(
        self,
        *,
        endpoint: str,
        base_model: str,
        tuned_model: str,
        max_tokens: int = 256,
        temperature: float = 0.0,
        request_opener: RequestOpener | None = None,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.base_model = base_model
        self.tuned_model = tuned_model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.request_opener = _open_request if request_opener is None else request_opener

    def __call__(self, case: EvaluationCase, kind: CandidateKind) -> str:
        model = {
            CandidateKind.BASE: self.base_model,
            CandidateKind.TUNED: self.tuned_model,
        }[kind]
        request = _build_request(
            f"{self.endpoint}/api/chat",
            {
                "model": model,
                "messages": [{"role": "user", "content": case.prompt}],
                "stream": False,
                "think": False,
                "options": {
                    "num_predict": self.max_tokens,
                    "temperature": self.temperature,
                },
            },
        )
        try:
            response = self.request_opener(request, 300)
            raw = response.read().decode("utf-8")
        except OSError as error:
            raise EvaluationInferenceError(f"Ollama {kind.value} evaluation failed: {error}") from error
        try:
            body = OllamaChatResponse.model_validate_json(raw)
        except ValueError as error:
            raise EvaluationInferenceError(f"Ollama {kind.value} evaluation failed: {error}") from error
        if not body.message.content:
            raise EvaluationInferenceError(f"Ollama {kind.value} evaluation returned no content.")
        return body.message.content


def _load_mlx_runtime() -> MlxRuntime:
    try:
        module = import_module("mlx_lm")
    except ImportError as error:
        raise EvaluationInferenceError(
            "MLX evaluation is unavailable because mlx_lm is not installed.",
        ) from error
    if not isinstance(module, MlxModule):
        raise EvaluationInferenceError("MLX evaluation is unavailable because mlx_lm has an incompatible API.")
    return _MlxModuleRuntime(module)


@final
class _MlxModuleRuntime:
    load: MlxCandidateLoad
    generate: MlxGenerate

    _module: MlxModule

    def __init__(self, module: MlxModule) -> None:
        self._module = module
        self.generate = module.generate

        def load(
            *,
            path_or_hf_repo: str | None = None,
            revision: str | None = None,
            adapter_path: str | None = None,
        ) -> MlxCandidate:
            loaded = self._module.load(
                path_or_hf_repo=path_or_hf_repo,
                revision=revision,
                adapter_path=adapter_path,
            )
            if len(loaded) != 2:
                raise EvaluationInferenceError(
                    "MLX evaluation is unavailable because mlx_lm returned an incompatible model.",
                )
            return MlxCandidate(model=loaded[0], tokenizer=loaded[1])

        self.load = load


def _open_request(request: RequestBody, timeout: float) -> RequestResponse:
    return safe_urlopen(
        Request(request.full_url, data=request.data, headers={"Content-Type": "application/json"}),
        timeout=timeout,
    )


def _build_request(url: str, payload: OllamaChatRequest) -> RequestBody:
    return _OllamaRequest(url, json.dumps(payload).encode("utf-8"))
