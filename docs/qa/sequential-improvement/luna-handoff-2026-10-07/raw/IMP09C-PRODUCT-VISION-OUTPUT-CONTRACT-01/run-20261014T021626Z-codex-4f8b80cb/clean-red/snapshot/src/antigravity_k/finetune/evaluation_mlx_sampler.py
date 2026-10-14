from __future__ import annotations

from importlib import import_module
from typing import Protocol, runtime_checkable


@runtime_checkable
class MlxHandle(Protocol): ...


class MlxSampler(Protocol):
    def __call__(self, logits: MlxHandle) -> MlxHandle: ...


class MlxSamplerFactory(Protocol):
    def __call__(self, *, temp: float) -> bool | MlxSampler: ...


class MlxGenerate(Protocol):
    def __call__(
        self,
        *,
        model: MlxHandle,
        tokenizer: MlxHandle,
        prompt: str,
        max_tokens: int,
        sampler: bool | MlxSampler,
    ) -> str: ...


@runtime_checkable
class MlxSamplerModule(Protocol):
    make_sampler: MlxSamplerFactory


class MlxSamplerError(RuntimeError):
    pass


def make_mlx_sampler(temperature: float) -> bool | MlxSampler:
    if temperature <= 0.0:
        return False
    module = import_module("mlx_lm.sample_utils")
    if not isinstance(module, MlxSamplerModule):
        raise MlxSamplerError("mlx_lm sampler API is incompatible.")
    return module.make_sampler(temp=temperature)
