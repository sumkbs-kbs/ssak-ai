from __future__ import annotations

import importlib.util
from collections.abc import Iterator, Mapping, Sized
from typing import Protocol, TypeAlias, cast, override, runtime_checkable

from .inference_providers import BaseInferenceProvider, DynamicValue, LoadedModelArg, Prompt

TensorIndex: TypeAlias = int | slice


class _Indexable(Protocol):
    def __getitem__(self, index: TensorIndex, /) -> object: ...


class _ParameterLike(Protocol):
    device: object


class _ModelLike(Protocol):
    generation_config: object

    def parameters(self) -> Iterator[_ParameterLike]: ...

    def generate(self, **kwargs: object) -> object: ...


class _TokenizerLike(Protocol):
    def __call__(self, prompt: Prompt, *, return_tensors: str) -> Mapping[str, object]: ...

    def decode(self, tokens: object, *, skip_special_tokens: bool) -> str: ...


@runtime_checkable
class _MovableValue(Protocol):
    def to(self, device: object, /) -> object: ...


class TransformersProvider(BaseInferenceProvider):
    @override
    def generate(self, loaded: LoadedModelArg, prompt: Prompt, **kwargs: DynamicValue) -> str:
        tokenizer = cast(_TokenizerLike, loaded.tokenizer)
        model = cast(_ModelLike, loaded.model)
        encoded = tokenizer(prompt, return_tensors="pt")
        encoded = _move_inputs_to_model_device(encoded, model)
        input_ids = encoded["input_ids"]
        do_sample = _as_float(kwargs.get("temperature", 0.7)) > 0
        generation: dict[str, object] = {
            "max_new_tokens": _as_int(kwargs.get("max_tokens", 8192)),
            "do_sample": do_sample,
        }
        execution_plan = kwargs.get("execution_plan")
        plan = cast(Mapping[str, object], execution_plan) if isinstance(execution_plan, Mapping) else None
        if plan is not None and plan.get("native_attention_enabled") is True:
            generation["use_cache"] = True
            if plan.get("kv_cache_compression_enabled") is True and _quantized_cache_is_available(model):
                generation["cache_implementation"] = "quantized"
        if do_sample:
            generation["temperature"] = _as_float(kwargs.get("temperature", 0.7))
        generated = model.generate(**encoded, **generation)
        prompt_length = _sequence_length(input_ids)
        generated_sequence = cast(_Indexable, cast(_Indexable, generated)[0])
        return str(tokenizer.decode(generated_sequence[prompt_length:], skip_special_tokens=True))

    @override
    def stream_generate(self, loaded: LoadedModelArg, prompt: Prompt, **kwargs: DynamicValue) -> Iterator[str]:
        text = self.generate(loaded, prompt, **kwargs)
        chunk_size = max(1, _as_int(kwargs.get("stream_chunk_size", 256)))
        for start in range(0, len(text), chunk_size):
            yield text[start : start + chunk_size]


def _as_int(value: object) -> int:
    return int(cast(str | int | float | bool, value))


def _as_float(value: object) -> float:
    return float(cast(str | int | float | bool, value))


def _sequence_length(input_ids: object) -> int:
    shape = getattr(input_ids, "shape", None)
    if shape is not None:
        return _as_int(cast(_Indexable, shape)[-1])
    first_sequence = cast(_Indexable, cast(_Indexable, input_ids)[0])
    return len(cast(Sized, cast(object, first_sequence)))


def _move_inputs_to_model_device(encoded: Mapping[str, object], model: object) -> Mapping[str, object]:
    model_like = cast(_ModelLike, model)
    try:
        device = next(model_like.parameters()).device
    except (AttributeError, StopIteration):
        return encoded

    moved: dict[str, object] = {}
    for key, value in encoded.items():
        moved[key] = value.to(device) if isinstance(value, _MovableValue) else value
    return moved


def _quantized_cache_is_available(model: object) -> bool:
    generation_config = cast(object, getattr(model, "generation_config", None))
    if generation_config is None or not hasattr(generation_config, "cache_implementation"):
        return False
    return any(_module_is_available(module) for module in ("optimum.quanto", "hqq"))


def _module_is_available(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False
