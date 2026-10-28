from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import ClassVar, TypedDict, final

import pytest
from pydantic import TypeAdapter

from antigravity_k.finetune.evaluation import (
    CandidateKind,
    EvaluationCase,
    EvaluationDataset,
    EvaluationPair,
    evaluate_candidates,
)
from antigravity_k.finetune.evaluation_backends import (
    MlxCandidate,
    MlxEvaluationInference,
    MlxLoaded,
    OllamaEvaluationInference,
    RequestBody,
    _MlxModuleRuntime,
)
from antigravity_k.finetune.evaluation_mlx_sampler import MlxHandle, MlxSampler, make_mlx_sampler

_pair_adapter: TypeAdapter[EvaluationPair] = TypeAdapter(EvaluationPair)


class ChatMessage(TypedDict):
    role: str
    content: str


class ChatOptions(TypedDict):
    num_predict: int
    temperature: float


class OllamaChatRequest(TypedDict):
    model: str
    messages: list[ChatMessage]
    stream: bool
    think: bool
    options: ChatOptions


_payload_adapter: TypeAdapter[OllamaChatRequest] = TypeAdapter(OllamaChatRequest)


@final
class FakeMlxModel:
    name: str

    def __init__(self) -> None:
        self.name = "model"


@final
class FakeMlxTokenizer:
    name: str

    def __init__(self) -> None:
        self.name = "tokenizer"


@final
class TupleMlxLoaded:
    values: tuple[FakeMlxModel, FakeMlxTokenizer]

    def __init__(self, values: tuple[FakeMlxModel, FakeMlxTokenizer]) -> None:
        self.values = values

    def __len__(self) -> int:
        return len(self.values)

    def __getitem__(self, index: int) -> MlxHandle:
        return self.values[index]


@final
class FakeTupleMlxRuntime:
    generate_calls: list[tuple[MlxHandle, MlxHandle, str, int, bool | MlxSampler]]

    def __init__(self) -> None:
        self.generate_calls = []

    def load(
        self,
        *,
        path_or_hf_repo: str | None = None,
        revision: str | None = None,
        adapter_path: str | None = None,
    ) -> MlxLoaded:
        return TupleMlxLoaded((FakeMlxModel(), FakeMlxTokenizer()))

    def generate(
        self,
        *,
        model: MlxHandle,
        tokenizer: MlxHandle,
        prompt: str,
        max_tokens: int,
        sampler: bool | MlxSampler,
    ) -> str:
        self.generate_calls.append((model, tokenizer, prompt, max_tokens, sampler))
        return "answer"


@final
class FakeMlxSampler:
    temperature: float

    def __init__(self, temperature: float) -> None:
        self.temperature = temperature


@final
class FakeMlxGenerateCall:
    model: MlxHandle
    tokenizer: MlxHandle
    prompt: str
    max_tokens: int
    sampler: bool | MlxSampler

    def __init__(
        self,
        *,
        model: MlxHandle,
        tokenizer: MlxHandle,
        prompt: str,
        max_tokens: int,
        sampler: bool | MlxSampler,
    ) -> None:
        self.model = model
        self.tokenizer = tokenizer
        self.prompt = prompt
        self.max_tokens = max_tokens
        self.sampler = sampler


class FakeMlxRuntime:
    load_calls: list[dict[str, str | None]]
    generate_calls: list[FakeMlxGenerateCall]

    def __init__(self) -> None:
        self.load_calls = []
        self.generate_calls = []

    def load(
        self,
        *,
        path_or_hf_repo: str,
        revision: str | None = None,
        adapter_path: str | None = None,
    ) -> MlxCandidate:
        self.load_calls.append(
            {
                "path_or_hf_repo": path_or_hf_repo,
                "revision": revision,
                "adapter_path": adapter_path,
            },
        )
        return MlxCandidate(model=FakeMlxModel(), tokenizer=FakeMlxTokenizer())

    def generate(
        self,
        *,
        model: FakeMlxModel,
        tokenizer: FakeMlxTokenizer,
        prompt: str,
        max_tokens: int,
        sampler: bool,
    ) -> str:
        self.generate_calls.append(
            FakeMlxGenerateCall(
                model=model,
                tokenizer=tokenizer,
                prompt=prompt,
                max_tokens=max_tokens,
                sampler=sampler,
            ),
        )
        return "answer"


class FakeResponse:
    payload: ClassVar[str] = json.dumps({"message": {"content": "candidate answer"}})

    def read(self) -> bytes:
        return self.payload.encode("utf-8")


class FakeRequestOpener:
    requests: list[RequestBody]
    timeouts: list[float]

    def __init__(self) -> None:
        self.requests = []
        self.timeouts = []

    def __call__(self, request: RequestBody, timeout: float) -> FakeResponse:
        self.requests.append(request)
        self.timeouts.append(timeout)
        return FakeResponse()


def _case() -> EvaluationCase:
    return EvaluationCase(
        id="ko",
        category="korean_reasoning",
        prompt="answer",
        expected_keywords=("answer",),
        expected_output="",
        forbidden_for_training=True,
    )


def _dataset(path: Path) -> EvaluationDataset:
    return EvaluationDataset(
        path=path,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        case_ids=("ko",),
    )


def _write_dataset(root: Path) -> EvaluationDataset:
    path = root / "held_out_v1.jsonl"
    _ = path.write_text(
        json.dumps(
            {
                "id": "ko",
                "category": "korean_reasoning",
                "prompt": "answer",
                "expected_keywords": ["answer"],
                "forbidden_for_training": True,
            },
        )
        + "\n",
        encoding="utf-8",
    )
    return _dataset(path)


def test_mlx_inference_uses_revision_for_base_and_adapter_for_tuned(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeMlxRuntime()
    adapter_path = tmp_path / "adapter"
    monkeypatch.setattr("antigravity_k.finetune.evaluation_backends._load_mlx_runtime", lambda: runtime)
    inference = MlxEvaluationInference(
        base_model="/models/base",
        base_revision="sha256:base-revision",
        adapter_path=adapter_path,
        max_tokens=17,
    )
    monkeypatch.setattr(inference, "runtime", runtime)

    assert inference(_case(), CandidateKind.BASE) == "answer"
    assert inference(_case(), CandidateKind.TUNED) == "answer"

    assert runtime.load_calls == [
        {
            "path_or_hf_repo": "/models/base",
            "revision": "sha256:base-revision",
            "adapter_path": None,
        },
        {
            "path_or_hf_repo": "/models/base",
            "revision": None,
            "adapter_path": str(adapter_path),
        },
    ]
    assert len(runtime.generate_calls) == 2
    assert runtime.generate_calls[0].model is not runtime.generate_calls[0].tokenizer
    assert runtime.generate_calls[0].max_tokens == 17


def test_mlx_inference_normalizes_tuple_loaded_from_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = FakeTupleMlxRuntime()
    monkeypatch.setattr(
        "antigravity_k.finetune.evaluation_backends._load_mlx_runtime",
        lambda: _MlxModuleRuntime(runtime),
    )
    inference = MlxEvaluationInference(
        base_model="/models/base",
        base_revision="sha256:base-revision",
        adapter_path=Path("/models/adapter"),
    )

    assert inference(_case(), CandidateKind.TUNED) == "answer"

    assert len(runtime.generate_calls) == 1
    model, tokenizer, _, _, _ = runtime.generate_calls[0]
    assert type(model) is FakeMlxModel
    assert type(tokenizer) is FakeMlxTokenizer


def test_mlx_inference_passes_sampler_for_real_api(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = FakeTupleMlxRuntime()

    def fake_make_sampler(temperature: float) -> FakeMlxSampler:
        return FakeMlxSampler(temperature)

    monkeypatch.setattr(
        "antigravity_k.finetune.evaluation_backends.make_mlx_sampler",
        fake_make_sampler,
    )
    monkeypatch.setattr(
        "antigravity_k.finetune.evaluation_backends._load_mlx_runtime",
        lambda: _MlxModuleRuntime(runtime),
    )
    inference = MlxEvaluationInference(
        base_model="/models/base",
        base_revision="sha256:base-revision",
        adapter_path=Path("/models/adapter"),
        max_tokens=19,
        temperature=0.25,
    )

    assert inference(_case(), CandidateKind.BASE) == "answer"

    assert len(runtime.generate_calls) == 1
    assert runtime.generate_calls[0][3] == 19
    assert isinstance(runtime.generate_calls[0][4], FakeMlxSampler)
    assert runtime.generate_calls[0][4].temperature == 0.25


def test_make_mlx_sampler_returns_greedy_sampler_below_positive_temperature() -> None:
    sampler = make_mlx_sampler(0.0)

    assert sampler is False


def test_ollama_inference_selects_exact_candidate_model() -> None:
    opener = FakeRequestOpener()
    inference = OllamaEvaluationInference(
        endpoint="http://127.0.0.1:11434",
        base_model="base-model:latest",
        tuned_model="tuned-model:latest",
        max_tokens=23,
        request_opener=opener,
    )

    assert inference(_case(), CandidateKind.TUNED) == "candidate answer"

    request = opener.requests[0]
    payload = _payload_adapter.validate_json(request.data.decode())
    assert request.full_url == "http://127.0.0.1:11434/api/chat"
    assert payload["model"] == "tuned-model:latest"
    assert payload["think"] is False
    assert payload["messages"] == [{"role": "user", "content": "answer"}]
    # The backend still asks for 300 s; the direct-model-call guard (approved per-request cap,
    # LLM_REQUEST_TIMEOUT_CAP_S) bounds it. Pin both: the requested value and the cap applied.
    from antigravity_k.engine.direct_model_call import LLM_REQUEST_TIMEOUT_CAP_S

    assert opener.timeouts == [min(300.0, LLM_REQUEST_TIMEOUT_CAP_S)]
    assert LLM_REQUEST_TIMEOUT_CAP_S == 120.0


def test_evaluate_candidates_uses_backend_adapter(tmp_path: Path) -> None:
    dataset = _write_dataset(tmp_path)
    opener = FakeRequestOpener()
    inference = OllamaEvaluationInference(
        endpoint="http://127.0.0.1:11434",
        base_model="base-model:latest",
        tuned_model="tuned-model:latest",
        request_opener=opener,
    )

    pair = evaluate_candidates(
        dataset=dataset,
        model="base-model:latest",
        model_revision="sha256:base-revision",
        adapter_path=tmp_path / "adapter",
        recipe_sha256="b" * 64,
        environment={"backend": "ollama"},
        inference=inference,
    )

    assert pair.base.scores == (1.0,)
    assert pair.tuned.scores == (1.0,)
    assert [json.loads(request.data.decode())["model"] for request in opener.requests] == [
        "base-model:latest",
        "tuned-model:latest",
    ]


def test_evaluate_cli_uses_mlx_backend_with_injected_fake_package(tmp_path: Path) -> None:
    fake_root = tmp_path / "fake"
    package = fake_root / "mlx_lm"
    package.mkdir(parents=True)
    _ = (package / "__init__.py").write_text(
        "\n".join(
            [
                "from antigravity_k.finetune.evaluation_backends import MlxCandidate",
                "",
                "def load(**kwargs):",
                "    return ('loaded', 'tokenizer')",
                "",
                "def generate(**kwargs):",
                "    return 'answer'",
            ],
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "training_result.json"
    _ = manifest.write_text(
        json.dumps(
            {
                "status": "success",
                "return_code": 0,
                "dataset_sha256": "a" * 64,
                "adapter_path": str(tmp_path / "adapter"),
                "data_dir": str(tmp_path / "data"),
                "iterations": 1,
                "stdout": "",
                "stderr": "",
                "base_model": "/models/base",
                "base_revision": "sha256:base-revision",
                "recipe_sha256": "b" * 64,
                "environment": {"python": "3.13"},
                "evaluation_sha256": "c" * 64,
            },
        ),
        encoding="utf-8",
    )
    dataset = _write_dataset(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "antigravity_k.finetune.trainer",
            "evaluate",
            "--run",
            str(manifest),
            "--dataset",
            str(dataset.path),
            "--backend",
            "mlx",
            "--output",
            str(tmp_path / "evaluation.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
        env={
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": f"{fake_root}{os.pathsep}src",
        },
    )

    assert result.returncode == 0
    payload = _pair_adapter.validate_json((tmp_path / "evaluation.json").read_text(encoding="utf-8"))
    assert payload.base.model == "/models/base"
    assert payload.tuned.adapter_path == tmp_path / "adapter"
