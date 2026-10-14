"""Inference Providers module."""

from __future__ import annotations

import json
import logging
import time
import urllib.request
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from importlib import import_module
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, ContextManager, Protocol, TypeAlias, cast, override, runtime_checkable

from antigravity_k.engine.context_budget import context_budget_for_context_length

# NX-10: `from antigravity_k.engine import multimodal` 는 **패키지 루트**를 요구해
# `engine/__init__ → model_manager → inference_providers` 와 순환한다(게이트:
# reportImportCycles). leaf 모듈에서 이름을 직접 가져온다.
from antigravity_k.engine.multimodal import adapter_messages
from antigravity_k.tools.egress_policy import safe_urlopen

if TYPE_CHECKING:
    from antigravity_k.engine.model_registry import ModelProfile

logger = logging.getLogger("antigravity_k.inference_providers")

Message = dict[str, object]
Prompt = str | list[Message]

# 공유 ModelRegistry — 생성 시마다 config.yaml을 다시 읽고 구문분석하므로
# 호출 단위 생성은 per-request 지연+I/O 낭비다 (provider base_url 조회용).
_shared_model_registry_cache: Any = None


def _shared_model_registry() -> Any:
    global _shared_model_registry_cache
    if _shared_model_registry_cache is None:
        from antigravity_k.engine.model_registry import ModelRegistry

        _shared_model_registry_cache = ModelRegistry()
    return _shared_model_registry_cache


DynamicValue: TypeAlias = object
JsonMap: TypeAlias = dict[str, Any]  # pyright: ignore[reportExplicitAny]
DynamicConfig: TypeAlias = tuple[str, float, JsonMap | None, str]


class _AnthropicStream(Protocol):
    text_stream: Iterator[str]


class _AnthropicMessages(Protocol):
    def stream(self, **kwargs: object) -> ContextManager[_AnthropicStream]: ...


class _AnthropicClient(Protocol):
    messages: _AnthropicMessages


class _AnthropicModule(Protocol):
    def Anthropic(self, *, api_key: str) -> _AnthropicClient: ...


@runtime_checkable
class _ReadableError(Protocol):
    def read(self) -> bytes: ...


def _as_json_map(value: object) -> JsonMap:
    return cast(JsonMap, value) if isinstance(value, dict) else {}


def _first_choice(payload: JsonMap) -> JsonMap:
    choices = payload.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        return cast(JsonMap, choices[0])
    return {}


def _as_json_maps(value: object) -> list[JsonMap]:
    if not isinstance(value, list):
        return []
    items = cast(list[object], value)
    return [_as_json_map(cast(object, item)) for item in items if isinstance(item, dict)]


class LoadedModelLike(Protocol):
    profile: ModelProfile
    model: DynamicValue
    tokenizer: DynamicValue


LoadedModelArg = LoadedModelLike | SimpleNamespace


class BaseInferenceProvider(ABC):
    """Baseinferenceprovider.

    Bases: ABC
    """

    @abstractmethod
    def generate(self, loaded: LoadedModelArg, prompt: Prompt, **kwargs: DynamicValue) -> str:
        """Generate.

        Args:
            loaded: loaded.
            prompt: prompt.
            **kwargs: Additional keyword arguments.

        Returns:
            str: The str result.

        """
        pass

    @abstractmethod
    def stream_generate(self, loaded: LoadedModelArg, prompt: Prompt, **kwargs: DynamicValue) -> Iterator[str]:
        """Stream Generate.

        Args:
            loaded: loaded.
            prompt: prompt.
            **kwargs: Additional keyword arguments.

        """
        pass

    def _suppress_model_thinking(self, model_name: str, messages: list[Message]) -> list[Message]:
        if "qwen3" not in model_name.lower():
            return messages

        directive = (
            "/no_think\nAnswer directly. Do not output hidden reasoning, thinking traces, <think>, or <thought> blocks."
        )
        prepared = [dict(message) for message in messages]
        if prepared and prepared[0].get("role") == "system":
            content = str(prepared[0].get("content", ""))
            if "/no_think" not in content:
                prepared[0]["content"] = f"{directive}\n{content}".strip()
            return prepared

        return [{"role": "system", "content": directive}, *prepared]

    def _apply_dynamic_inference_config(
        self,
        loaded_profile: ModelProfile,
        prompt_or_messages: Prompt,
        kwargs: JsonMap,
    ) -> DynamicConfig:
        import hashlib

        model_name = loaded_profile.name
        thinking_config = None
        temperature = cast(float, kwargs.get("temperature", 0.7))
        max_tokens = cast(float, kwargs.get("max_tokens", 8192))

        if ":" in model_name:
            base_model, spec = model_name.split(":", 1)
            budget = None

            if spec.isdigit():
                budget = max(int(spec), 1024)
            else:
                ratios = {"high": 0.8, "medium": 0.5, "low": 0.2}
                ratio = ratios.get(spec.lower())
                if ratio:
                    budget = max(int(max_tokens * ratio), 1024)

            if budget:
                thinking_config = {"type": "enabled", "budget_tokens": budget}
                temperature = 1.0
                model_name = base_model

        if isinstance(prompt_or_messages, list) and len(prompt_or_messages) > 0:
            first_user_text = str(prompt_or_messages[0].get("content", ""))
        else:
            first_user_text = str(prompt_or_messages)

        fingerprint_input = f"antigravity_k_59cf53e54c78_{first_user_text[:30]}"
        fingerprint = hashlib.sha256(fingerprint_input.encode("utf-8")).hexdigest()[:6]
        attribution = f"\nx-antigravity-k-agent: id={fingerprint}; cch=00000;"

        return model_name, temperature, thinking_config, attribution

    @staticmethod
    def _native_tool_call_xml(tool_name: str, arguments: DynamicValue) -> str:
        if not tool_name:
            return ""
        if isinstance(arguments, str):
            try:
                arguments = cast(object, json.loads(arguments))
            except json.JSONDecodeError:
                arguments = {}
        if not isinstance(arguments, dict):
            arguments = {}
        payload: JsonMap = {"name": tool_name, "arguments": arguments}
        return f"\n<tool_call>\n{json.dumps(payload, ensure_ascii=False)}\n</tool_call>\n"


class AnthropicProvider(BaseInferenceProvider):
    """Anthropicprovider.

    Bases: BaseInferenceProvider
    """

    @override
    def generate(self, loaded: LoadedModelArg, prompt: Prompt, **kwargs: DynamicValue) -> str:
        """Generate.

        Args:
            loaded: loaded.
            prompt: prompt.
            **kwargs: Additional keyword arguments.

        Returns:
            str: The str result.

        """
        result = ""
        for chunk in self.stream_generate(loaded, prompt, **kwargs):
            result += chunk
        return result

    @override
    def stream_generate(self, loaded: LoadedModelArg, prompt: Prompt, **kwargs: DynamicValue) -> Iterator[str]:
        """Stream Generate.

        Args:
            loaded: loaded.
            prompt: prompt.
            **kwargs: Additional keyword arguments.

        """
        anthropic = cast(_AnthropicModule, cast(object, import_module("anthropic")))

        from antigravity_k.engine.secure_key import get_api_key

        api_key = get_api_key("anthropic")
        if not api_key:
            yield "[Error] Anthropic API Key not found. Run: export AGK_ANTHROPIC_KEY=sk-ant-... (or: agk key set anthropic <key>)"  # noqa: E501
            return

        client = anthropic.Anthropic(api_key=api_key)
        system_prompt = cast(str, kwargs.get("system_prompt", ""))
        # NX-09-F03: Anthropic 은 이미지를 `source.base64` 블록으로 받는다.
        raw_messages = adapter_messages(
            surface="anthropic",
            prompt=prompt,
            raw_messages=kwargs.get("raw_messages"),
            images=kwargs.get("images"),
        )
        model_name, temperature, thinking_config, attribution = self._apply_dynamic_inference_config(
            loaded.profile,
            raw_messages,
            kwargs,
        )

        anthropic_msgs: list[JsonMap] = []
        for msg in raw_messages:
            if msg["role"] in ["user", "assistant"]:
                anthropic_msgs.append({"role": msg["role"], "content": msg["content"]})

        cache_blocks: list[JsonMap] = []
        system_blocks: list[JsonMap] = []
        if system_prompt:
            system_blocks.append(
                {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}},
            )
            cache_blocks.append(system_blocks[0])

        for msg in anthropic_msgs:
            if isinstance(msg["content"], list):
                for block in cast(list[object], msg["content"]):
                    if isinstance(block, dict) and "cache_control" in block:
                        cache_blocks.append(cast(JsonMap, block))

        if len(cache_blocks) > 4:
            keep_first = cache_blocks[0]
            keep_last = cache_blocks[-3:]
            to_keep = set([id(keep_first)] + [id(b) for b in keep_last])
            for block in cache_blocks:
                if id(block) not in to_keep:
                    del block["cache_control"]

        if system_blocks:
            system_blocks[0]["text"] += attribution
        else:
            system_blocks.append(
                {"type": "text", "text": attribution, "cache_control": {"type": "ephemeral"}},
            )

        request_params: JsonMap = {
            "max_tokens": kwargs.get("max_tokens", 8192),
            "system": system_blocks if system_blocks else system_prompt,
            "messages": anthropic_msgs,
            "model": model_name,
            "temperature": temperature,
        }

        if thinking_config:
            request_params["thinking"] = thinking_config

        try:
            with client.messages.stream(**cast(dict[str, object], request_params)) as stream:
                for text in stream.text_stream:
                    yield text
        except Exception as e:
            logger.exception("Anthropic API generation failed")
            yield f"[API Error for {model_name}] {e}"


class OpenRouterProvider(BaseInferenceProvider):
    """Openrouterprovider.

    Bases: BaseInferenceProvider
    """

    requires_api_key: bool = True
    includes_openrouter_attribution: bool = True
    forwards_native_tools: bool = True

    @override
    def generate(self, loaded: LoadedModelArg, prompt: Prompt, **kwargs: DynamicValue) -> str:
        """Generate.

        Args:
            loaded: loaded.
            prompt: prompt.
            **kwargs: Additional keyword arguments.

        Returns:
            str: The str result.

        """
        result = ""
        for chunk in self.stream_generate(loaded, prompt, **kwargs):
            result += chunk
        return result

    def _resolve_endpoint(self, loaded: LoadedModelArg) -> tuple[str, str]:
        """loaded.profile에서 per-model 엔드포인트와 키를 해석 (멀티 프로바이더)."""
        import os

        from antigravity_k.engine.secure_key import get_api_key

        profile = loaded.profile
        # per-model api_base 오버라이드 → OpenRouter 기본값
        base_url = getattr(profile, "api_base", "") or "https://openrouter.ai/api/v1"
        base_url = base_url.rstrip("/")

        # API 키: profile.api_key_env → OPENROUTER_API_KEY → AGK_OPENROUTER_KEY → secure_key
        key_env = getattr(profile, "api_key_env", "") or "OPENROUTER_API_KEY"
        api_key = os.environ.get(key_env) or os.environ.get("AGK_OPENROUTER_KEY") or ""
        if not api_key:
            api_key = get_api_key("openrouter") or ""
        return base_url, api_key

    @override
    def stream_generate(self, loaded: LoadedModelArg, prompt: Prompt, **kwargs: DynamicValue) -> Iterator[str]:
        """Stream Generate.

        Args:
            loaded: loaded.
            prompt: prompt.
            **kwargs: Additional keyword arguments.

        """
        api_key = None
        base_url, api_key = self._resolve_endpoint(loaded)
        if self.requires_api_key and not api_key:
            yield (
                "[Error] OpenRouter API Key not found. Run: export AGK_OPENROUTER_KEY=..."
                "(or: agk key set openrouter <key>)"
            )
            return

        url = f"{base_url}/chat/completions"
        # NX-09-F03: 첨부까지 포함해 표면별로 변환한다(여기서 각자 풀어 쓰면 이미지가 샌다).
        api_msgs: list[Message] = adapter_messages(
            surface="openai",
            prompt=prompt,
            raw_messages=kwargs.get("raw_messages"),
            system_prompt=cast(str, kwargs.get("system_prompt", "")),
            images=kwargs.get("images"),
        )

        model_name, temperature, thinking_config, _ = self._apply_dynamic_inference_config(
            loaded.profile,
            cast(Prompt, api_msgs),
            kwargs,
        )
        model_id = getattr(loaded.profile, "repo", "") or model_name
        if model_id.startswith("openrouter/"):
            model_id = model_id[len("openrouter/") :]

        data: dict[str, object] = {
            "model": model_id,
            "messages": api_msgs,
            "stream": True,
            "temperature": temperature,
            "max_tokens": kwargs.get("max_tokens", 4096),
        }
        # "model:high/4096" 사양 → OpenRouter reasoning 파라미터로 매핑
        if thinking_config is not None and isinstance(thinking_config, dict):
            budget = thinking_config.get("budget_tokens", 1024)
            data["reasoning"] = {"max_tokens": int(budget) if isinstance(budget, (int, float)) else 1024}

        # 네이티브 function calling 지원 (P1-1): tools 스키마가 제공되면 전송
        tools_schema = kwargs.get("tools") if self.forwards_native_tools else None
        if tools_schema and isinstance(tools_schema, list):
            data["tools"] = tools_schema
            # tool_choice: "auto" (모델이 자동 판단)
            data["tool_choice"] = kwargs.get("tool_choice", "auto")

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        if self.includes_openrouter_attribution:
            headers["HTTP-Referer"] = "https://github.com/ssak-comp/Ssak-Ai"
            headers["X-Title"] = "Ssak-Ai"

        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers=headers,
        )
        try:
            with safe_urlopen(req, timeout=300) as response:
                # 네이티브 tool_call 누적 버퍼 (스트리밍 tool_calls 조립용)
                pending_tool_calls: dict[int, JsonMap] = {}
                for line in response:
                    line_text = line.decode("utf-8").strip()
                    if not line_text or line_text == "data: [DONE]":
                        continue
                    if line_text.startswith("data: "):
                        line_text = line_text[6:]
                    try:
                        chunk = _as_json_map(cast(object, json.loads(line_text)))
                        choice = _first_choice(chunk)
                        if choice:
                            delta = cast(JsonMap, choice.get("delta", {}))
                            # 1. 일반 텍스트 content
                            if "content" in delta and delta["content"]:
                                yield delta["content"]
                            # 2. 네이티브 tool_calls 누적 (P1-1)
                            if "tool_calls" in delta:
                                for tc in _as_json_maps(cast(object, delta["tool_calls"])):
                                    idx = cast(int, tc.get("index", 0))
                                    if idx not in pending_tool_calls:
                                        pending_tool_calls[idx] = {
                                            "id": tc.get("id", ""),
                                            "type": "function",
                                            "function": {"name": "", "arguments": ""},
                                        }
                                    func = _as_json_map(cast(object, tc.get("function", {})))
                                    if func.get("name"):
                                        pending_tool_calls[idx]["function"]["name"] += func["name"]
                                    if func.get("arguments"):
                                        pending_tool_calls[idx]["function"]["arguments"] += func["arguments"]
                            # 3. finish_reason이 tool_calls면 조립된 tool_call을 이벤트로 yield
                            finish_reason = choice.get("finish_reason")
                            if finish_reason == "tool_calls" and pending_tool_calls:
                                for idx in sorted(pending_tool_calls):
                                    tc = pending_tool_calls[idx]
                                    # 표준 XML 도구 호출 포맷으로 변환하여 ToolCallParser가 처리하도록
                                    tool_event = (
                                        f"\n<tool_call>\n"
                                        f"{json.dumps({'name': tc['function']['name'], 'arguments': json.loads(tc['function']['arguments'] or '{}')}, ensure_ascii=False)}\n"
                                        f"</tool_call>\n"
                                    )
                                    yield tool_event
                                pending_tool_calls.clear()
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            err_body = ""
            if isinstance(e, _ReadableError):
                try:
                    err_body = f" Body: {e.read().decode('utf-8', errors='replace')}"
                except Exception:
                    pass
            logger.exception("API stream failed (%s)%s", url, err_body)
            yield f"[API Error for {loaded.profile.name}] {e}{err_body}"


class OllamaProvider(BaseInferenceProvider):
    """Ollamaprovider.

    Bases: BaseInferenceProvider
    """

    def _resolve_endpoint(self, loaded: LoadedModelArg) -> tuple[str, str]:
        """loaded.profile에서 per-model Ollama 엔드포인트와 키를 해석 (멀티 프로바이더)."""
        import os

        from antigravity_k.config import config

        profile = loaded.profile
        # per-model api_base → registry providers 섹션 → 전역 config 폴백
        base_url = getattr(profile, "api_base", "") or ""
        api_key = ""
        if base_url:
            key_env = getattr(profile, "api_key_env", "") or "OLLAMA_API_KEY"
            api_key = os.environ.get(key_env, "") or "ollama"
        else:
            # registry에서 provider 기본 base_url 조회
            try:
                base_url = self._registry_provider_base("ollama") or config.model.api_base
            except Exception:
                base_url = config.model.api_base
            api_key = os.environ.get("OLLAMA_API_KEY", "") or config.model.api_key or "ollama"

        # Ollama OpenAI 호환 엔드포인트는 /v1 접미사 필수 — 누락 시 자동 추가
        # (registry providers 섹션의 base_url이 http://localhost:11434 형태일 수 있음)
        base_url = base_url.rstrip("/")
        if "/v1" not in base_url and ":11434" in base_url:
            base_url = base_url + "/v1"

        return base_url, api_key

    @staticmethod
    def _registry_provider_base(provider: str) -> str:
        """ModelRegistry의 providers 섹션에서 base_url을 조회합니다."""
        try:
            prov_cfg = _shared_model_registry().get_provider_config(provider)
            base_url = prov_cfg.get("base_url")
            return base_url if isinstance(base_url, str) else ""
        except Exception:
            return ""

    @staticmethod
    def _context_window(loaded: LoadedModelArg, kwargs: JsonMap) -> int:
        return context_budget_for_context_length(
            getattr(loaded.profile, "context_length", None),
            kwargs.get("context_token_limit"),
        ).token_limit

    @override
    def generate(self, loaded: LoadedModelArg, prompt: Prompt, **kwargs: DynamicValue) -> str:
        """Generate.

        Args:
            loaded: loaded.
            prompt: prompt.
            **kwargs: Additional keyword arguments.

        Returns:
            str: The str result.

        """
        from antigravity_k.engine.sampling_config import resolve_sampling_profile

        base_url, api_key = self._resolve_endpoint(loaded)
        url = f"{base_url}/chat/completions"

        # task_type 정규화 — 라이브 경로는 소문자("code")로 전달되므로
        # 대소문자 무시 조회가 없으면 항상 GENERAL로 폴백되었다.
        profile = resolve_sampling_profile(kwargs.get("task_type"))
        temperature = cast(float, kwargs.get("temperature", profile.temperature))
        min_p = cast(float, kwargs.get("min_p", profile.min_p))
        repeat_penalty = cast(float, kwargs.get("repeat_penalty", profile.repeat_penalty))
        if "qwen3" in loaded.profile.name.lower():
            return self._generate_native(
                loaded,
                prompt,
                kwargs,
                base_url,
                api_key,
                temperature,
                min_p,
                repeat_penalty,
            )

        data = {
            "model": loaded.profile.name,
            "stream": False,
            "temperature": temperature,
            "max_tokens": kwargs.get("max_tokens", 4096),
            "repeat_penalty": repeat_penalty,
            "options": {"min_p": min_p},
        }

        json_schema = kwargs.get("response_format")
        if json_schema:
            data["format"] = json_schema

        tools_schema = kwargs.get("tools")
        if tools_schema and isinstance(tools_schema, list):
            data["tools"] = tools_schema

        # NX-09-F03: 이 표면은 OpenAI 호환 `/chat/completions` — 파트로 변환해 보낸다.
        api_msgs: list[Message] = adapter_messages(
            surface="openai",
            prompt=prompt,
            raw_messages=kwargs.get("raw_messages"),
            system_prompt=cast(str, kwargs.get("system_prompt", "")),
            images=kwargs.get("images"),
        )

        api_msgs = self._suppress_model_thinking(loaded.profile.name, api_msgs)
        data["messages"] = api_msgs

        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        )
        try:
            with safe_urlopen(req, timeout=300) as response:
                result = _as_json_map(cast(object, json.loads(response.read().decode("utf-8"))))
                message = _as_json_map(_first_choice(result).get("message"))
                content = cast(str, message.get("content", ""))
                native_tool_calls = _as_json_maps(cast(object, message.get("tool_calls")))
                if native_tool_calls:
                    content += "".join(
                        self._native_tool_call_xml(
                            cast(str, _as_json_map(cast(object, call.get("function", {}))).get("name", "")),
                            cast(object, _as_json_map(cast(object, call.get("function", {}))).get("arguments", {})),
                        )
                        for call in native_tool_calls
                    )
                # qwen3.6 등 thinking 모델은 content가 비고 reasoning/thinking에 담길 수 있음
                # — reasoning을 content로 승격 (비어 있을 때만)
                if not content:
                    reasoning = cast(str, message.get("reasoning") or message.get("thinking") or "")
                    if reasoning:
                        # reasoning이 아직 진행 중이면 (완결된 content가 없음) 빈 응답 방지
                        content = reasoning.strip()
                return content
        except Exception as e:
            logger.exception("Local API generation failed")
            return f"[API Error for {loaded.profile.name}] {e}"

    def _generate_native(
        self,
        loaded: LoadedModelArg,
        prompt: Prompt,
        kwargs: JsonMap,
        base_url: str,
        api_key: str,
        temperature: float,
        min_p: float,
        repeat_penalty: float,
    ) -> str:
        import re

        native_base = re.sub(r"/v\d+$", "", base_url.rstrip("/"))
        url = f"{native_base}/api/chat"
        # NX-09-F03: Ollama 네이티브는 `content`(텍스트) + `images`(base64) 로 받는다.
        api_msgs: list[Message] = adapter_messages(
            surface="ollama",
            prompt=prompt,
            raw_messages=kwargs.get("raw_messages"),
            system_prompt=cast(str, kwargs.get("system_prompt", "")),
            images=kwargs.get("images"),
        )
        # thinking이 명시적으로 켜진 경우 /no_think 주입을 건너뛴다(충돌 방지)
        think_enabled = bool(kwargs.get("think", False))
        if not think_enabled:
            api_msgs = self._suppress_model_thinking(loaded.profile.name, api_msgs)
        data = {
            "model": loaded.profile.name,
            "stream": False,
            "keep_alive": "30m",
            "think": think_enabled,
            "options": {
                "num_ctx": self._context_window(loaded, kwargs),
                "num_predict": kwargs.get("max_tokens", 4096),
                "temperature": temperature,
                "min_p": min_p,
                "repeat_penalty": repeat_penalty,
            },
            "messages": api_msgs,
        }
        json_schema = kwargs.get("response_format")
        if json_schema:
            data["format"] = json_schema
        tools_schema = kwargs.get("tools")
        if tools_schema and isinstance(tools_schema, list):
            data["tools"] = tools_schema
        request = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        )
        try:
            with safe_urlopen(request, timeout=300) as response:
                message = _as_json_map(
                    _as_json_map(cast(object, json.loads(response.read().decode("utf-8")))).get("message")
                )
                content = cast(str, message.get("content", ""))
                native_tool_calls = _as_json_maps(cast(object, message.get("tool_calls")))
                if native_tool_calls:
                    content += "".join(
                        self._native_tool_call_xml(
                            cast(str, _as_json_map(cast(object, call.get("function", {}))).get("name", "")),
                            cast(object, _as_json_map(cast(object, call.get("function", {}))).get("arguments", {})),
                        )
                        for call in native_tool_calls
                    )
                return content
        except Exception as e:
            logger.exception("Local native API generation failed")
            return f"[API Error for {loaded.profile.name}] {e}"

    def _iter_stream_response(
        self, response: Iterator[bytes], tools_schema: list[DynamicValue] | None = None
    ) -> Iterator[str]:
        pending_tool_calls: list[JsonMap] = []
        buffered_content: list[str] = []
        for line in response:
            line_text = line.decode("utf-8").strip()
            if not line_text:
                continue
            try:
                chunk = _as_json_map(cast(object, json.loads(line_text)))
                msg = _as_json_map(cast(object, chunk.get("message")))
                if msg:
                    native_tool_calls = _as_json_maps(cast(object, msg.get("tool_calls")))
                    pending_tool_calls.extend(native_tool_calls)
                    if msg.get("content"):
                        content = cast(str, msg["content"])
                        if tools_schema:
                            buffered_content.append(content)
                        else:
                            yield content
            except json.JSONDecodeError:
                continue
        if pending_tool_calls:
            # 네이티브 도구 호출과 함께 생성된 텍스트는 폐기하지 않는다 —
            # 모델이 "검색하겠습니다" 같은 안내/추론 텍스트를 쓰고 도구를
            # 호출하는 경우가 많다. 텍스트를 먼저, 도구 호출을 뒤에.
            yield from buffered_content
            for call in pending_tool_calls:
                function = _as_json_map(cast(object, call.get("function", {})))
                yield self._native_tool_call_xml(
                    cast(str, function.get("name", "")),
                    cast(object, function.get("arguments", {})),
                )
            return
        synthesized_call = self._single_tool_content_call("".join(buffered_content), tools_schema)
        if synthesized_call:
            yield synthesized_call
            return
        yield from buffered_content

    def _single_tool_content_call(self, content: str, tools_schema: list[DynamicValue] | None) -> str:
        if not isinstance(tools_schema, list) or len(tools_schema) != 1:
            return ""
        tool = _as_json_map(tools_schema[0])
        function = _as_json_map(cast(object, tool.get("function")))
        tool_name = function.get("name")
        parameters = _as_json_map(cast(object, function.get("parameters")))
        if not isinstance(tool_name, str) or not parameters:
            return ""
        required_fields = cast(object, parameters.get("required"))
        if not isinstance(required_fields, list) or not required_fields:
            return ""
        required_fields = cast(list[object], required_fields)
        import re

        match = re.fullmatch(r"\s*```(?:json)?\s*(\{.*\})\s*```\s*", content, re.IGNORECASE | re.DOTALL)
        if match is None:
            return ""
        try:
            arguments = _as_json_map(cast(object, json.loads(match.group(1))))
        except json.JSONDecodeError:
            return ""
        if not all(isinstance(field, str) and field in arguments for field in required_fields):
            return ""
        return self._native_tool_call_xml(tool_name, cast(object, arguments))

    @override
    def stream_generate(self, loaded: LoadedModelArg, prompt: Prompt, **kwargs: DynamicValue) -> Iterator[str]:
        """Stream Generate.

        Args:
            loaded: loaded.
            prompt: prompt.
            **kwargs: Additional keyword arguments.

        """
        base_url, api_key = self._resolve_endpoint(loaded)
        # Ollama Native API (/api/chat) — /v1 접미사 정규화
        import re

        native_base = re.sub(r"/v\d+$", "", base_url)
        url = f"{native_base}/api/chat"

        # NX-09-F03: 예전에는 여기서 파트를 텍스트로 납작하게 만들어 **이미지를 버렸다**
        # ("Normalize: ensure content is a string"). 이제 표면별 변환은 multimodal 이 소유한다.
        api_msgs = adapter_messages(
            surface="ollama",
            prompt=prompt,
            raw_messages=kwargs.get("raw_messages"),
            system_prompt=cast(str, kwargs.get("system_prompt", "")),
            images=kwargs.get("images"),
        )

        model_name, temperature, thinking_config, attribution = self._apply_dynamic_inference_config(
            loaded.profile,
            api_msgs,
            kwargs,
        )

        # thinking이 명시적으로 켜진 경우 /no_think 주입을 건너뛴다(충돌 방지).
        # "model:high/4096" 사양(thinking_config)도 thinking 활성으로 해석한다 —
        # 사양이 파싱되는데 요청에 반영되지 않으면 이름만 잘린 채 실행된다.
        think_enabled = bool(kwargs.get("think", False)) or thinking_config is not None
        if not think_enabled:
            api_msgs = self._suppress_model_thinking(loaded.profile.name, api_msgs)

        # attribution 지문을 메시지에 주입하지 않는다 — 다시 파싱되지 않는
        # 프롬프트 오염이다 (토큰 낭비 + 요청마다 달라지는 접두사).
        _ = attribution

        default_repeat_penalty = 1.0 if "qwen3" in loaded.profile.name.lower() else 1.3

        # 스트리밍 경로(실 라이브 에이전트 경로)에도 작업 유형별 샘플링
        # 프로파일을 적용한다 — 기존에는 비스트리밍 generate에만 적용되었다.
        from antigravity_k.engine.sampling_config import resolve_sampling_profile

        profile = resolve_sampling_profile(kwargs.get("task_type"))
        if thinking_config is None and "temperature" not in kwargs:
            temperature = profile.temperature

        data: dict[str, object] = {
            "model": model_name,
            "stream": True,
            "keep_alive": "30m",
            # 기본은 off(빈 content 스트리밍 방지). 복잡 태스크 증폭을 위해
            # kwargs.think=true로 켤 수 있다 — thinking은 content와 분리되어
            # 반환되므로 사용자 스트림은 오염되지 않는다.
            "think": think_enabled,
            "options": {
                "num_ctx": self._context_window(loaded, kwargs),
                "num_predict": kwargs.get("max_tokens", 4096),
                "temperature": temperature,
                "repeat_penalty": kwargs.get("repeat_penalty", default_repeat_penalty),
                "min_p": kwargs.get("min_p", profile.min_p),
            },
            "messages": api_msgs,
        }

        tools_schema = kwargs.get("tools")
        if tools_schema and isinstance(tools_schema, list):
            data["tools"] = tools_schema

        # 구조화 출력 (제어 평면용): Ollama /api/chat은 format에 "json" 또는
        # JSON 스키마를 받아 문법 제약 디코딩을 수행한다. thinking과 동시
        # 적용은 불가하지만 제어 평면은 항상 no-think이므로 안전하다.
        json_format = kwargs.get("response_format")
        if json_format:
            data["format"] = json_format

        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        )
        try:
            with safe_urlopen(req, timeout=300) as response:
                yield from self._iter_stream_response(response, cast(list[DynamicValue] | None, tools_schema))
                return
        except Exception as outer_error:
            error_message = str(outer_error)
            if tools_schema:
                logger.warning("Ollama native tools rejected; retrying with XML tool protocol")
                fallback_data = dict(data)
                _ = fallback_data.pop("tools", None)
                fallback_req = urllib.request.Request(
                    url,
                    data=json.dumps(fallback_data).encode("utf-8"),
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
                )
                try:
                    with safe_urlopen(fallback_req, timeout=300) as response:
                        yield from self._iter_stream_response(response)
                        return
                except Exception as fallback_error:
                    error_message = str(fallback_error)
            logger.exception("Local API stream failed")
            yield f"[API Error for {loaded.profile.name}] {error_message}"


class NimProvider(BaseInferenceProvider):
    """NVIDIA NIM (build.nvidia.com) 프로바이더.

    OpenAI 호환 엔드포인트(https://integrate.api.nvidia.com/v1)를 사용하므로
    OpenRouterProvider와 유사한 SSE 스트리밍 로직을 사용하지만,
    NIM 고유의 설정(무료 rate limit 40rpm, 별도 헤더)을 갖습니다.
    """

    # NIM 무료 티어 rate limit: 분당 40 요청 (초당 약 0.67)
    _RATE_LIMIT_RPM: int = 40
    _RATE_LIMIT_WINDOW_SEC: float = 60.0

    def __init__(self):
        """Initialize the NimProvider — 분당 rate 카운터 초기화."""
        self._request_timestamps: list[float] = []

    def _check_rate_limit(self) -> bool:
        """분당 rate limit 내인지 확인. 초과 시 False 반환.

        호출 시마다 타임스탬프를 기록하고, 최근 60초 창의 요청 수가
        _RATE_LIMIT_RPM을 초과하면 False 반환 (라우터가 다른 폴백으로 전환 유도).
        """
        now = time.time()
        cutoff = now - self._RATE_LIMIT_WINDOW_SEC
        self._request_timestamps = [t for t in self._request_timestamps if t > cutoff]
        if len(self._request_timestamps) >= self._RATE_LIMIT_RPM:
            return False
        self._request_timestamps.append(now)
        return True

    def _resolve_endpoint(self, loaded: LoadedModelArg) -> tuple[str, str]:
        """loaded.profile과 registry에서 NIM 엔드포인트와 API 키를 해석합니다."""
        import os

        profile = loaded.profile
        # per-model 오버라이드 → registry providers 섹션 → 환경변수 순서
        base_url = getattr(profile, "api_base", "") or "https://integrate.api.nvidia.com/v1"
        base_url = base_url.rstrip("/")

        # API 키: profile.api_key_env → NVIDIA_API_KEY 환경변수
        key_env = getattr(profile, "api_key_env", "") or "NVIDIA_API_KEY"
        api_key = os.environ.get(key_env, "")
        if not api_key:
            # secure_key vault 폴백
            try:
                from antigravity_k.engine.secure_key import get_api_key

                api_key = get_api_key("nim") or get_api_key("nvidia") or ""
            except Exception:
                api_key = ""

        return base_url, api_key

    @override
    def generate(self, loaded: LoadedModelArg, prompt: Prompt, **kwargs: DynamicValue) -> str:
        """Generate.

        Args:
            loaded: loaded.
            prompt: prompt.
            **kwargs: Additional keyword arguments.

        Returns:
            str: The str result.

        """
        # rate limit 검사는 stream_generate에서 단일로 수행한다 — 여기서도
        # 검사하면 요청 1건에 타임스탬프가 2개 기록되어 실효 한도가 절반으로
        # 줄어든다. 제한 초과 시 stream_generate가 에러 문자열을 yield하고
        # 여기서 그대로 반환된다.
        result = ""
        for chunk in self.stream_generate(loaded, prompt, **kwargs):
            result += chunk
        return result

    @override
    def stream_generate(self, loaded: LoadedModelArg, prompt: Prompt, **kwargs: DynamicValue) -> Iterator[str]:
        """Stream Generate.

        Args:
            loaded: loaded.
            prompt: prompt.
            **kwargs: Additional keyword arguments.

        """
        base_url, api_key = self._resolve_endpoint(loaded)
        if not api_key:
            yield (
                "[Error] NVIDIA NIM API Key not found. "
                "build.nvidia.com에서 무료 키를 발급받아 NVIDIA_API_KEY 환경변수로 설정하세요."
            )
            return

        if not self._check_rate_limit():
            yield "[API Error for NIM] rate limit(40rpm) 초과 — 다른 폴백 모델로 전환 권장."
            return

        url = f"{base_url}/chat/completions"

        # NX-09-F03: 첨부까지 포함한 표면별 변환은 multimodal 이 단독 소유한다.
        api_msgs: list[Message] = adapter_messages(
            surface="openai",
            prompt=prompt,
            raw_messages=kwargs.get("raw_messages"),
            system_prompt=cast(str, kwargs.get("system_prompt", "")),
            images=kwargs.get("images"),
        )

        # 메시지 정규화 (string content 보장)
        normalized: list[Message] = []
        for msg in api_msgs:
            content = msg.get("content", "")
            if isinstance(content, list):
                parts: list[str] = []
                for part in cast(list[object], content):
                    part_map = _as_json_map(part)
                    if isinstance(part, dict) and part_map.get("type") == "text":
                        parts.append(cast(str, part_map.get("text", "")))
                    elif isinstance(part, str):
                        parts.append(part)
                content = " ".join(parts)
            normalized.append({**msg, "content": content})
        api_msgs = self._suppress_model_thinking(loaded.profile.name, normalized)

        model_name, temperature, _, _ = self._apply_dynamic_inference_config(
            loaded.profile,
            cast(Prompt, api_msgs),
            kwargs,
        )
        # NIM 모델명은 이미 "nvidia/..." 또는 "meta/..." 형태 — 그대로 사용

        data = {
            "model": model_name,
            "messages": api_msgs,
            "stream": True,
            "temperature": temperature,
            "max_tokens": kwargs.get("max_tokens", 4096),
        }

        # 네이티브 function calling 지원 (P1-1)
        tools_schema = kwargs.get("tools")
        if tools_schema and isinstance(tools_schema, list):
            data["tools"] = tools_schema
            data["tool_choice"] = kwargs.get("tool_choice", "auto")

        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "Accept": "text/event-stream",
            },
        )
        try:
            with safe_urlopen(req, timeout=300) as response:
                pending_tool_calls: dict[int, JsonMap] = {}
                for line in response:
                    line_text = line.decode("utf-8").strip()
                    if not line_text or line_text == "data: [DONE]":
                        continue
                    if line_text.startswith("data: "):
                        line_text = line_text[6:]
                    try:
                        chunk = _as_json_map(cast(object, json.loads(line_text)))
                        choice = _first_choice(chunk)
                        if choice:
                            delta = cast(JsonMap, choice.get("delta", {}))
                            if "content" in delta and delta["content"]:
                                yield delta["content"]
                            # 네이티브 tool_calls 누적 (P1-1)
                            if "tool_calls" in delta:
                                for tc in _as_json_maps(cast(object, delta["tool_calls"])):
                                    idx = cast(int, tc.get("index", 0))
                                    if idx not in pending_tool_calls:
                                        pending_tool_calls[idx] = {
                                            "id": tc.get("id", ""),
                                            "type": "function",
                                            "function": {"name": "", "arguments": ""},
                                        }
                                    func = _as_json_map(cast(object, tc.get("function", {})))
                                    if func.get("name"):
                                        pending_tool_calls[idx]["function"]["name"] += func["name"]
                                    if func.get("arguments"):
                                        pending_tool_calls[idx]["function"]["arguments"] += func["arguments"]
                            finish_reason = choice.get("finish_reason")
                            if finish_reason == "tool_calls" and pending_tool_calls:
                                for idx in sorted(pending_tool_calls):
                                    tc = pending_tool_calls[idx]
                                    tool_event = (
                                        f"\n<tool_call>\n"
                                        f"{json.dumps({'name': tc['function']['name'], 'arguments': json.loads(tc['function']['arguments'] or '{}')}, ensure_ascii=False)}\n"
                                        f"</tool_call>\n"
                                    )
                                    yield tool_event
                                pending_tool_calls.clear()
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.exception("NVIDIA NIM API stream failed")
            yield f"[API Error for {loaded.profile.name}] {e}"


class OpenAIDirectProvider(OpenRouterProvider):
    """OpenAI 직접 API provider (api.openai.com).

    OpenRouterProvider와 동일한 OpenAI 호환 프로토콜을 사용하지만,
    base_url이 https://api.openai.com/v1 이고 OPENAI_API_KEY를 사용.
    HTTP-Referer/X-Title 헤더 없음.
    """

    @override
    def _resolve_endpoint(self, loaded: LoadedModelArg) -> tuple[str, str]:
        """OpenAI 직접 엔드포인트와 키를 해석."""
        import os

        profile = loaded.profile
        base_url = getattr(profile, "api_base", "") or "https://api.openai.com/v1"
        base_url = base_url.rstrip("/")

        key_env = getattr(profile, "api_key_env", "") or "OPENAI_API_KEY"
        api_key = os.environ.get(key_env, "")
        if not api_key:
            try:
                from antigravity_k.engine.secure_key import get_api_key

                api_key = get_api_key("openai") or ""
            except Exception:
                api_key = ""
        return base_url, api_key

    @override
    def stream_generate(self, loaded: LoadedModelArg, prompt: Prompt, **kwargs: DynamicValue) -> Iterator[str]:
        """OpenAI 직접 스트리밍 (HTTP-Referer 헤더 없음)."""
        base_url, api_key = self._resolve_endpoint(loaded)
        if not api_key:
            # provider별 적절한 키 환경변수명 표시
            provider_name = getattr(loaded.profile, "provider", "openai")
            key_hints = {
                "openai": "OPENAI_API_KEY",
                "gemini": "GEMINI_API_KEY",
                "zai": "ZAI_API_KEY",
            }
            key_hint = key_hints.get(provider_name, "OPENAI_API_KEY")
            yield f"[Error] {provider_name.upper()} API Key not found. {key_hint} 환경변수를 설정하세요."
            return

        # 부모의 stream_generate를 사용하되 endpoint만 오버라이드
        # OpenRouterProvider는 _resolve_endpoint를 호출하므로 상속으로 충분
        # 단 헤더에서 HTTP-Referer 제거를 위해 직접 처리
        import json
        import urllib.request

        if "raw_messages" in kwargs:
            sys_msg = cast(str, kwargs.get("system_prompt", ""))
            raw_messages = cast(list[Message], kwargs["raw_messages"])
            api_msgs: list[Message] = (
                [cast(Message, {"role": "system", "content": sys_msg})] + raw_messages if sys_msg else raw_messages
            )
        else:
            api_msgs = [{"role": "user", "content": prompt}] if not isinstance(prompt, list) else prompt

        model_name, temperature, _, _ = self._apply_dynamic_inference_config(
            loaded.profile,
            cast(Prompt, api_msgs),
            kwargs,
        )

        data = {
            "model": model_name,
            "messages": api_msgs,
            "stream": True,
            "temperature": temperature,
            "max_tokens": kwargs.get("max_tokens", 4096),
        }
        tools_schema = kwargs.get("tools")
        if tools_schema and isinstance(tools_schema, list):
            data["tools"] = tools_schema
            data["tool_choice"] = kwargs.get("tool_choice", "auto")

        req = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=json.dumps(data).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        try:
            with safe_urlopen(req, timeout=300) as response:
                pending_tool_calls: dict[int, JsonMap] = {}
                for line in response:
                    line_text = line.decode("utf-8").strip()
                    if not line_text or line_text == "data: [DONE]":
                        continue
                    if line_text.startswith("data: "):
                        line_text = line_text[6:]
                    try:
                        chunk = _as_json_map(cast(object, json.loads(line_text)))
                        choice = _first_choice(chunk)
                        if choice:
                            delta = cast(JsonMap, choice.get("delta", {}))
                            if "content" in delta and delta["content"]:
                                yield delta["content"]
                            if "tool_calls" in delta:
                                for tc in _as_json_maps(cast(object, delta["tool_calls"])):
                                    idx = cast(int, tc.get("index", 0))
                                    if idx not in pending_tool_calls:
                                        pending_tool_calls[idx] = {
                                            "id": tc.get("id", ""),
                                            "type": "function",
                                            "function": {"name": "", "arguments": ""},
                                        }
                                    func = _as_json_map(cast(object, tc.get("function", {})))
                                    if func.get("name"):
                                        pending_tool_calls[idx]["function"]["name"] += func["name"]
                                    if func.get("arguments"):
                                        pending_tool_calls[idx]["function"]["arguments"] += func["arguments"]
                            finish_reason = choice.get("finish_reason")
                            if finish_reason == "tool_calls" and pending_tool_calls:
                                for idx in sorted(pending_tool_calls):
                                    tc = pending_tool_calls[idx]
                                    yield f"\n<tool_call>\n{json.dumps({'name': tc['function']['name'], 'arguments': json.loads(tc['function']['arguments'] or '{}')}, ensure_ascii=False)}\n</tool_call>\n"
                                pending_tool_calls.clear()
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.exception("OpenAI direct API stream failed")
            yield f"[API Error for {loaded.profile.name}] {e}"


class GeminiProvider(OpenAIDirectProvider):
    """Google Gemini 직접 API provider (OpenAI 호환 엔드포인트).

    Google는 OpenAI 호환 엔드포인트를 제공하므로 OpenAIDirectProvider와 유사.
    base_url: https://generativelanguage.googleapis.com/v1beta/openai
    """

    @override
    def _resolve_endpoint(self, loaded: LoadedModelArg) -> tuple[str, str]:
        import os

        profile = loaded.profile
        base_url = getattr(profile, "api_base", "") or "https://generativelanguage.googleapis.com/v1beta/openai"
        base_url = base_url.rstrip("/")
        key_env = getattr(profile, "api_key_env", "") or "GEMINI_API_KEY"
        api_key = os.environ.get(key_env, "")
        if not api_key:
            try:
                from antigravity_k.engine.secure_key import get_api_key

                api_key = get_api_key("gemini") or ""
            except Exception:
                api_key = ""
        return base_url, api_key


class ZaiProvider(OpenAIDirectProvider):
    """ZAI/Zhipu GLM 직접 API provider.

    Zhipu BigModel은 OpenAI 호환 API를 제공.
    base_url: https://open.bigmodel.cn/api/paas/v4
    """

    @override
    def _resolve_endpoint(self, loaded: LoadedModelArg) -> tuple[str, str]:
        import os

        profile = loaded.profile
        base_url = getattr(profile, "api_base", "") or "https://open.bigmodel.cn/api/paas/v4"
        base_url = base_url.rstrip("/")
        key_env = getattr(profile, "api_key_env", "") or "ZAI_API_KEY"
        api_key = os.environ.get(key_env, "")
        if not api_key:
            try:
                from antigravity_k.engine.secure_key import get_api_key

                api_key = get_api_key("zai") or ""
            except Exception:
                api_key = ""
        return base_url, api_key


class LMStudioProvider(OpenRouterProvider):
    requires_api_key: bool = False
    includes_openrouter_attribution: bool = False

    @override
    def _resolve_endpoint(self, loaded: LoadedModelArg) -> tuple[str, str]:
        import os

        from antigravity_k.config import config

        profile = loaded.profile
        base_url = getattr(profile, "api_base", "") or ""
        if not base_url:
            try:
                base_url = cast(str, _shared_model_registry().get_provider_config("lmstudio").get("base_url", ""))
            except (ImportError, OSError, RuntimeError, TypeError, ValueError):
                base_url = ""
        if not base_url:
            base_url = (
                config.model.api_base
                if config.model.api_engine in {"lm_studio", "lmstudio"}
                else "http://127.0.0.1:1234/v1"
            )

        key_env = getattr(profile, "api_key_env", "") or "LM_STUDIO_API_KEY"
        api_key = os.environ.get(key_env, "")
        if not api_key and config.model.api_engine in {"lm_studio", "lmstudio"}:
            api_key = config.model.api_key if config.model.api_key != "lm-studio" else ""
        return base_url.rstrip("/"), api_key


class MlxProvider(BaseInferenceProvider):
    @override
    def generate(self, loaded: LoadedModelArg, prompt: Prompt, **kwargs: DynamicValue) -> str:
        """Generate.

        Args:
            loaded: loaded.
            prompt: prompt.
            **kwargs: Additional keyword arguments.

        Returns:
            str: The str result.

        """
        try:
            mlx_generate = cast(
                Callable[..., str],
                cast(object, import_module("mlx_lm").__dict__["generate"]),
            )

            max_tokens = cast(int, kwargs.get("max_tokens", 1024))
            return mlx_generate(
                model=loaded.model,
                tokenizer=loaded.tokenizer,
                prompt=prompt,
                max_tokens=max_tokens,
            )
        except ImportError as exc:
            raise RuntimeError("mlx-lm is required for direct MLX inference; install the mlx extra first") from exc

    @override
    def stream_generate(self, loaded: LoadedModelArg, prompt: Prompt, **kwargs: DynamicValue) -> Iterator[str]:
        """Stream Generate.

        Args:
            loaded: loaded.
            prompt: prompt.
            **kwargs: Additional keyword arguments.

        """
        try:
            mlx_stream_generate = cast(
                Callable[..., Iterator[str]],
                cast(object, import_module("mlx_lm").__dict__["stream_generate"]),
            )

            max_tokens = cast(int, kwargs.get("max_tokens", 1024))
            yield from mlx_stream_generate(
                model=loaded.model,
                tokenizer=loaded.tokenizer,
                prompt=prompt,
                max_tokens=max_tokens,
            )
        except ImportError as exc:
            raise RuntimeError("mlx-lm is required for direct MLX inference; install the mlx extra first") from exc


def get_inference_provider(loaded: LoadedModelArg) -> BaseInferenceProvider:
    """loaded.profile.provider 기반으로 적절한 추론 프로바이더를 반환합니다.

    우선순위 (작업 2):
      1. profile.provider 명시적 값 (ollama/openrouter/nim/anthropic/mlx)
      2. 취약한 이름 휴리스틱 폴백 (레거시 호환)
      3. 전역 config.model.api_engine

    Args:
        loaded: LoadedModel 인스턴스 (profile, model, tokenizer 포함).

    Returns:
        BaseInferenceProvider: 해당 모델을 처리할 프로바이더.
    """
    import platform

    from antigravity_k.config import config

    profile = loaded.profile
    provider = (getattr(profile, "provider", "") or "").lower()

    # 1. 명시적 provider 필드 우선 (멀티 프로바이더 핵심)
    if provider == "nim":
        return NimProvider()
    if provider == "openrouter":
        return OpenRouterProvider()
    if provider == "ollama":
        return OllamaProvider()
    if provider == "anthropic":
        return AnthropicProvider()
    if provider == "openai":
        return OpenAIDirectProvider()
    if provider == "gemini":
        return GeminiProvider()
    if provider == "zai":
        return ZaiProvider()
    if provider in {
        "lmstudio",
        "lm_studio",
        "llama.cpp",
        "llamacpp",
        "openai-compatible-local",
        "vllm",
        "tgi",
        "koboldcpp",
        "text-generation-webui",
    }:
        return LMStudioProvider()
    if provider == "unsloth":
        from pathlib import Path

        local_repo = Path(getattr(profile, "repo", ""))
        if (local_repo / "adapter_config.json").is_file() or (
            (local_repo / "config.json").is_file()
            and any(local_repo.glob(pattern) for pattern in ("*.safetensors", "*.bin", "*.pt", "*.pth"))
        ):
            transformers_module = import_module(".transformers_provider", package=__package__)
            provider_class = cast(type[BaseInferenceProvider], transformers_module.__dict__["TransformersProvider"])
            return provider_class()
        unsloth_module = import_module(".unsloth_provider", package=__package__)
        provider_class = cast(type[BaseInferenceProvider], unsloth_module.__dict__["UnslothProvider"])
        return provider_class()
    if provider == "mlx":
        return MlxProvider()
    if provider == "transformers":
        transformers_module = import_module(".transformers_provider", package=__package__)
        provider_class = cast(type[BaseInferenceProvider], transformers_module.__dict__["TransformersProvider"])
        return provider_class()

    # 2. 레거시 휴리스틱 폴백 (provider 필드가 빈 경우)
    if profile.name.startswith("claude") and "anthropic/" not in (profile.repo or "").lower():
        return AnthropicProvider()
    if (profile.repo or "").startswith("openrouter/"):
        return OpenRouterProvider()
    # NIM 카탈로그 식별자 휴리스틱
    name_lower = (profile.name or "").lower()
    if name_lower.startswith("nvidia/") or name_lower.startswith("deepseek-ai/"):
        return NimProvider()

    # 3. 전역 config 기반 폴백
    engine = (config.model.api_engine or "").lower()
    if engine == "openrouter":
        return OpenRouterProvider()
    if engine == "nim":
        return NimProvider()

    if (
        config.model.force_api
        or platform.system() != "Darwin"
        or type(cast(object, loaded.model)).__name__ == "_OllamaModel"
    ):
        return OllamaProvider()

    return MlxProvider()
