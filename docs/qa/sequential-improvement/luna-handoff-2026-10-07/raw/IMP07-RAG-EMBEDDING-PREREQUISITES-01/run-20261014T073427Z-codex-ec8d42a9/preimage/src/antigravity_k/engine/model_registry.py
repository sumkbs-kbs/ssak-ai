"""Ssak-Ai: 모델 레지스트리.

config.yaml에서 모델 프로필을 읽어 카탈로그로 관리합니다.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias, cast, final

import yaml

from antigravity_k.runtime_paths import default_config_path as _default_config_path

from .local_model_discovery import DiscoveredLocalModel, LocalModelDiscovery

logger = logging.getLogger("antigravity_k.model_registry")

ConfigScalar: TypeAlias = str | int | float | bool | None
ProviderConfigValue: TypeAlias = str | int | float | bool | None


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    raw = cast(dict[object, object], value)
    return {str(key): item for key, item in raw.items()}


def _text(data: Mapping[str, object], key: str, default: str = "") -> str:
    value = data.get(key, default)
    return value if isinstance(value, str) else default


def _number(data: Mapping[str, object], key: str, default: float = 0.0) -> float:
    value = data.get(key, default)
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else default


def _integer(data: Mapping[str, object], key: str, default: int = 0) -> int:
    value = data.get(key, default)
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _boolean(data: Mapping[str, object], key: str, default: bool = False) -> bool:
    value = data.get(key, default)
    return value if isinstance(value, bool) else default


def _provider_mapping(value: object) -> dict[str, ProviderConfigValue]:
    return {
        key: item for key, item in _mapping(value).items() if isinstance(item, (str, int, float, bool)) or item is None
    }


@dataclass
class ModelProfile:
    """하나의 모델 프로필."""

    name: str
    repo: str
    role: str  # reasoning | coding | embedding | vision
    quantization: str = ""
    estimated_memory_gb: float = 0.0
    parameter_count_b: float = 0.0
    context_length: int = 0
    dimensions: int = 0
    description: str = ""
    # ─── 멀티 프로바이더 지원 (작업 1) ───
    # provider: ollama | openrouter | nim | anthropic | mlx (빈 값이면 _infer_provider로 추론)
    provider: str = ""
    # api_base: per-model 오버라이드 (빈 값이면 providers 섹션의 기본 base_url 사용)
    api_base: str = ""
    # api_key_env: 이 모델이 사용할 환경변수명 (예: "NVIDIA_API_KEY"). 빈 값이면 providers 기본값 사용.
    api_key_env: str = ""
    roles: tuple[str, ...] = ()
    # 1k 토큰당 평균 비용(USD). 0.0이면 비용 미설정/로컬 — 라우팅 비용 상한 검사에서 제외.
    cost_per_1k_tokens_usd: float = 0.0
    disk_path: str = ""

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ModelProfile:
        """From Dict.

        Args:
            data (dict): dict data.

        Returns:
            'ModelProfile': The 'modelprofile' result.

        """
        primary_role = _text(data, "role")
        raw_roles = data.get("roles", ())
        if isinstance(raw_roles, str):
            role_values = [raw_roles]
        elif isinstance(raw_roles, (list, tuple)):
            role_values = [item for item in cast(list[object] | tuple[object, ...], raw_roles) if isinstance(item, str)]
        else:
            role_values = []
        roles = tuple(dict.fromkeys(role for role in (primary_role, *role_values) if role))
        profile = cls(
            name=_text(data, "name"),
            repo=_text(data, "repo"),
            role=primary_role or (roles[0] if roles else ""),
            quantization=_text(data, "quantization"),
            estimated_memory_gb=_number(data, "estimated_memory_gb"),
            parameter_count_b=_number(data, "parameter_count_b"),
            context_length=_integer(data, "context_length"),
            dimensions=_integer(data, "dimensions"),
            description=_text(data, "description"),
            provider=_text(data, "provider"),
            api_base=_text(data, "api_base"),
            api_key_env=_text(data, "api_key_env"),
            roles=roles,
            cost_per_1k_tokens_usd=_as_cost(data.get("cost_per_1k_tokens_usd")),
            disk_path=_text(data, "disk_path"),
        )
        # provider가 명시되지 않았으면 이름/repo에서 자동 추론
        if not profile.provider:
            profile.provider = _infer_provider(profile.name, profile.repo, profile.estimated_memory_gb)
        return profile

    @property
    def backend(self) -> str:
        """backend 속성 — provider의 alias.

        model_manager.py:1068의 getattr(profile, "backend", "ollama") 코드와의
        하위 호환성을 위해 제공됨.
        """
        return self.provider or "ollama"

    @property
    def supported_roles(self) -> tuple[str, ...]:
        """Return every configured role while preserving legacy ``role``."""
        return self.roles or ((self.role,) if self.role else ())

    @property
    def effective_parameter_count_b(self) -> float:
        """Return the best available parameter-count estimate in billions.

        Some remote catalog entries omit an explicit parameter count. Keep the
        fallback consistent for routing, API discovery, and the CLI instead of
        letting each caller invent its own model-size heuristic.
        """
        try:
            parameter_count = float(self.parameter_count_b)
        except (TypeError, ValueError):
            parameter_count = 0.0
        if parameter_count > 0:
            return parameter_count

        model_text = f"{self.name} {self.repo} {self.description}"
        import re

        size_match = re.search(r"(?<!\d)(\d+(?:\.\d+)?)\s*b\b", model_text, re.IGNORECASE)
        if size_match:
            return float(size_match.group(1))

        if self.role != "embedding":
            try:
                memory = float(self.estimated_memory_gb)
            except (TypeError, ValueError):
                memory = 0.0
            if memory > 0:
                return memory
        return 0.0

    @property
    def capability_tier(self) -> str:
        """Return the coarse 7B/14B/30B/70B routing tier."""
        count = self.effective_parameter_count_b
        if count <= 0:
            return "unknown"
        if count <= 7:
            return "7B"
        if count <= 14:
            return "14B"
        if count <= 40:
            return "30B"
        if count <= 70:
            return "70B"
        return ">70B"

    @property
    def is_local(self) -> bool:
        """Whether this profile is backed by a local runtime."""
        provider = (self.provider or "").lower()
        if provider in {
            "ollama",
            "mlx",
            "llama.cpp",
            "llamacpp",
            "lmstudio",
            "lm_studio",
            "unsloth",
            "transformers",
            "vllm",
            "tgi",
            "koboldcpp",
            "text-generation-webui",
            "openai-compatible-local",
            "local",
        }:
            return True
        if provider:
            return False
        return ":" in self.name and "/" not in self.name

    @property
    def is_20b_plus(self) -> bool:
        """Whether this model is eligible for quality evaluation."""
        return self.effective_parameter_count_b >= 20.0

    def routing_metadata(self) -> dict[str, object]:
        """Return stable capability metadata for routers and user interfaces."""
        return {
            "provider": self.backend,
            "role": self.role,
            "roles": list(self.supported_roles),
            "parameter_count_b": self.effective_parameter_count_b,
            "capability_tier": self.capability_tier,
            "is_local": self.is_local,
            "is_20b_plus": self.is_20b_plus,
            "context_length": self.context_length,
        }

    def to_dict(self) -> dict[str, object]:
        """To Dict.

        Returns:
            dict: The dict result.

        """
        result: dict[str, object] = {
            "name": self.name,
            "repo": self.repo,
            "role": self.role,
            "estimated_memory_gb": self.estimated_memory_gb,
            "parameter_count_b": self.parameter_count_b,
            "provider": self.provider,
        }
        if self.quantization:
            result["quantization"] = self.quantization
        if self.context_length:
            result["context_length"] = self.context_length
        if self.dimensions:
            result["dimensions"] = self.dimensions
        if self.description:
            result["description"] = self.description
        if self.cost_per_1k_tokens_usd:
            result["cost_per_1k_tokens_usd"] = self.cost_per_1k_tokens_usd
        if self.api_base:
            result["api_base"] = self.api_base
        if self.api_key_env:
            result["api_key_env"] = self.api_key_env
        if len(self.supported_roles) > 1:
            result["roles"] = list(self.supported_roles)
        return result


# ─── Provider 추론 헬퍼 (작업 1) ──────────────────────────────────────


# 알려진 OpenRouter 슬래시 프리픽스 (provider/model 형식)
_OPENROUTER_PREFIXES = frozenset(
    {
        "openai/",
        "anthropic/",
        "google/",
        "meta-llama/",
        "mistralai/",
        "cohere/",
        "qwen/",
        "deepseek/",
        "x-ai/",
        "amazon/",
        "microsoft/",
    }
)

# NVIDIA NIM(build.nvidia.com) 모델 식별자
_NIM_PREFIXES = frozenset(
    {
        "nvidia/",
        "meta/llama",  # NIM 카탈로그의 meta/llama-* 시리즈
        "deepseek-ai/",
        "microsoft/phi",
    }
)


def _infer_provider(name: str, repo: str, estimated_memory_gb: float = 0.0) -> str:
    """모델 이름/repo에서 provider를 추론합니다.

    명시적 provider 필드가 없을 때 사용되는 휴리스틱:
      - 로컬 Ollama 모델: ":tag" 형식 (예: "qwen3.6:latest") 또는 메모리 > 0
      - NVIDIA NIM: nvidia/, meta/llama, deepseek-ai/, microsoft/phi 접두사
      - OpenRouter: openai/, anthropic/, google/, qwen/ 등 슬래시 프리픽스
      - Anthropic 직접: claude-* 이름 (OpenRouter 경유가 아닌 경우)
      - 기본값: config.model.api_engine (호환성)

    Args:
        name: 모델 이름 (예: "qwen3.6:latest", "openai/gpt-4o", "nvidia/llama-3.1-nemotron-70b-instruct")
        repo: 리포지토리 식별자
        estimated_memory_gb: 예상 메모리 (0보다 크면 로컬 모델로 간주)

    Returns:
        provider 문자열: ollama | openrouter | nim | anthropic | mlx
    """
    name_lower = (name or "").lower()
    repo_lower = (repo or "").lower()

    if repo_lower.startswith(("mlx-community/", "mlx/")):
        return "mlx"

    # 1. 로컬 Ollama 모델: ":tag" 형식이거나 메모리 > 0 (원격 API 모델은 메모리 0)
    # 단, ":free" 접미사는 OpenRouter 무료 모델이므로 제외
    if ":" in name_lower and "/" not in name_lower and not name_lower.endswith(":free"):
        return "ollama"
    if estimated_memory_gb > 0 and "/" not in name_lower:
        return "ollama"

    # 2. OpenRouter 무료 모델: ":free" 접미사는 항상 OpenRouter (NIM은 :free 안 씀)
    if name_lower.endswith(":free"):
        return "openrouter"

    # 3. Anthropic 직접 호출 대상 (claude-* 이름, 단 openrouter/ 프리픽스 제외)
    if name_lower.startswith("claude-") and "anthropic/" not in repo_lower:
        return "anthropic"

    # 3.5 Google Gemini 직접 (gemini- 접두사, google/ 프리픽스 없음)
    if name_lower.startswith("gemini-") and not name_lower.startswith("google/"):
        return "gemini"

    # 3.6 ZAI/Zhipu 직접 (glm- 접두사)
    if name_lower.startswith(("glm-", "glm")):
        return "zai"

    # 3.7 OpenAI 직접 (gpt- 접두사, openai/ 프리픽스 없음 → OpenRouter가 아닌 직접)
    if name_lower.startswith("gpt-") and not name_lower.startswith("openai/"):
        return "openai"
    if name_lower.startswith(("o1", "o3", "o4")) and not name_lower.startswith("openai/"):
        return "openai"

    # 4. NVIDIA NIM 카탈로그 식별자
    for prefix in _NIM_PREFIXES:
        if name_lower.startswith(prefix) or repo_lower.startswith(prefix):
            # 단, OpenRouter에도 같은 이름이 있을 수 있으므로 repo 기반 우선순위 확인
            # nvidia/ 접두사는 확실히 NIM
            if prefix == "nvidia/":
                return "nim"
            # meta/, deepseek-ai/, microsoft/phi는 명시적 판단이 필요 —
            # config의 provider 섹션에서 NIM base를 쓰는지로 최종 결정되므로
            # 여기서는 휴리스틱만 제공. 실제 config에서 provider: nim 명시 권장.
            return "nim"

    # 4. OpenRouter 슬래시 프리픽스
    for prefix in _OPENROUTER_PREFIXES:
        if name_lower.startswith(prefix) or repo_lower.startswith(prefix):
            return "openrouter"

    # 5. 기본값: 빈 문자열 (ModelManager가 config.model.api_engine으로 폴백)
    return ""


@dataclass
class DefaultModels:
    """서버 시작 시 기본 활성 모델."""

    reasoning: str | None = None
    coding: str | None = None
    embedding: str | None = None
    vision: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> DefaultModels:
        """From Dict.

        Args:
            data (dict): dict data.

        Returns:
            'DefaultModels': The 'defaultmodels' result.

        """
        return cls(
            reasoning=_text(data, "reasoning") or None,
            coding=_text(data, "coding") or None,
            embedding=_text(data, "embedding") or None,
            vision=_text(data, "vision") or None,
        )


@dataclass
class MemoryConfig:
    """메모리 관리 설정."""

    total_system_gb: float = 128.0
    max_loaded_gb: float = 100.0
    system_reserve_gb: float = 16.0
    auto_unload: bool = True
    unload_cooldown_sec: int = 30

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> MemoryConfig:
        """From Dict.

        Args:
            data (dict): dict data.

        Returns:
            'MemoryConfig': The 'memoryconfig' result.

        """
        return cls(
            total_system_gb=_number(data, "total_system_gb", 128.0),
            max_loaded_gb=_number(data, "max_loaded_gb", 100.0),
            system_reserve_gb=_number(data, "system_reserve_gb", 16.0),
            auto_unload=_boolean(data, "auto_unload", True),
            unload_cooldown_sec=_integer(data, "unload_cooldown_sec", 30),
        )


@dataclass
class ServerConfig:
    """Server runtime configuration (host, port, workers)."""

    host: str = "127.0.0.1"
    port: int = 8000
    workers: int = 1
    log_level: str = "info"
    enable_caveman_compression: bool = False

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ServerConfig:
        """From Dict.

        Args:
            data (dict): dict data.

        Returns:
            'ServerConfig': The 'serverconfig' result.

        """
        return cls(
            host=_text(data, "host", "127.0.0.1"),
            port=_integer(data, "port", 8000),
            workers=_integer(data, "workers", 1),
            log_level=_text(data, "log_level", "info"),
            enable_caveman_compression=_boolean(data, "enable_caveman_compression"),
        )


@dataclass(frozen=True)
class ActiveArtifactConfig:
    state_path: Path
    model_name: str
    role: str

    @classmethod
    def from_dict(cls, data: Mapping[str, ConfigScalar]) -> ActiveArtifactConfig | None:
        if not isinstance(data, dict):
            return None
        state_path_value = data.get("state_path", "")
        model_name_value = data.get("model_name", "")
        role_value = data.get("role", "reasoning")
        match state_path_value, model_name_value, role_value:
            case str() as state_path, str() as model_name, str() as role:
                pass
            case _:
                return None
        state_path = state_path.strip()
        model_name = model_name.strip()
        role = role.strip()
        if not state_path or not model_name or not role:
            return None
        return cls(state_path=Path(state_path), model_name=model_name, role=role)


@final
class ModelRegistry:
    """config.yaml 기반 모델 카탈로그.

    list_models(), get_model(name), find_by_role(role), get_default(role) 제공.
    """

    def __init__(self, config_path: str | None = None):
        """Initialize the ModelRegistry.

        Args:
            config_path (str | None): str | None config path.

        """
        if config_path is None:
            config_path = str(_default_config_path())
        self._config_path: str = config_path
        self._models: dict[str, ModelProfile] = {}
        self._defaults = DefaultModels()
        self._memory = MemoryConfig()
        self._server = ServerConfig()
        self._providers: dict[str, dict[str, ProviderConfigValue]] = {}
        self._active_artifact: ActiveArtifactConfig | None = None
        self._raw: dict[str, object] = {}
        self._load_config()

    def _load_config(self) -> None:
        path = Path(self._config_path)
        if not path.exists():
            raise FileNotFoundError(f"설정 파일 없음: {path}")
        with open(path, encoding="utf-8") as f:
            self._raw = _mapping(cast(object, yaml.safe_load(f) or {}))

        self._models.clear()
        models_raw = _mapping(self._raw.get("models", {}))
        for role, items in models_raw.items():
            if not isinstance(items, list):
                continue
            for item in cast(list[object], items):
                if not isinstance(item, dict):
                    continue
                item_data = _mapping(cast(object, item))
                _ = item_data.setdefault("role", role)
                p = ModelProfile.from_dict(item_data)
                if not p.name:
                    continue
                existing = self._models.get(p.name)
                if existing is None:
                    self._models[p.name] = p
                    continue
                existing.roles = tuple(dict.fromkeys((*existing.supported_roles, *p.supported_roles)))

        self._defaults = DefaultModels.from_dict(_mapping(self._raw.get("defaults", {})))
        self._active_artifact = ActiveArtifactConfig.from_dict(
            cast(Mapping[str, ConfigScalar], _mapping(self._raw.get("active_artifact", {})))
        )
        self._register_active_artifact()
        for default_role in ("reasoning", "coding", "embedding", "vision"):
            default_name = cast(str | None, getattr(self._defaults, default_role, None))
            profile = self._models.get(default_name) if default_name else None
            if profile is not None:
                profile.roles = tuple(dict.fromkeys((*profile.supported_roles, default_role)))
        self._memory = MemoryConfig.from_dict(_mapping(self._raw.get("memory", {})))
        self._server = ServerConfig.from_dict(_mapping(self._raw.get("server", {})))
        # providers 섹션 로드 (멀티 프로바이더 지원 — 작업 1)
        providers_raw = self._raw.get("providers", {})
        self._providers = {
            str(provider): _provider_mapping(cast(object, settings))
            for provider, settings in _mapping(providers_raw).items()
            if isinstance(settings, dict)
        }

    def _register_active_artifact(self) -> None:
        config = self._active_artifact
        if config is None:
            return
        from antigravity_k.finetune.active_artifact import (
            ActiveArtifactError,
            read_active_artifact,
            validate_active_artifact_output,
        )

        try:
            active = read_active_artifact(config.state_path)
            _ = validate_active_artifact_output(active)
        except ActiveArtifactError:
            logger.warning("Active artifact model is unavailable.")
            return
        profile = ModelProfile(
            name=config.model_name,
            repo=str(active.output_path),
            role=config.role,
            quantization="fused",
            description=f"Promoted artifact revision {active.promotion_revision}",
            provider="mlx",
        )
        self._models[profile.name] = profile

    def reload(self) -> None:
        """설정 핫 리로드."""
        self._load_config()

    def list_models(self) -> list[ModelProfile]:
        """List Models.

        Returns:
            list[ModelProfile]: The list[modelprofile] result.

        """
        return list(self._models.values())

    def get_model(self, name: str) -> ModelProfile | None:
        """Retrieve model.

        Args:
            name (str): str name.

        Returns:
            ModelProfile | None: The modelprofile | none result.

        """
        profile = self._models.get(name)
        if profile is not None:
            return profile
        for candidate in self._models.values():
            if candidate.repo == name:
                return candidate
        return None

    def merge_discovered_models(
        self,
        discovered: Iterable[DiscoveredLocalModel],
    ) -> tuple[ModelProfile, ...]:
        added: list[ModelProfile] = []
        for item in discovered:
            if not item.name or self.get_model(item.name) is not None or self.get_model(item.repo) is not None:
                continue
            profile = ModelProfile(
                name=item.name,
                repo=item.repo or item.name,
                role=item.role or "reasoning",
                quantization=item.quantization,
                estimated_memory_gb=item.estimated_memory_gb,
                parameter_count_b=item.parameter_count_b,
                context_length=item.context_length,
                description=f"Auto-discovered local model ({item.source or item.provider})",
                provider=item.provider,
                api_base=item.api_base,
                roles=(item.role,) if item.role else ("reasoning",),
                disk_path=item.disk_path,
            )
            self._models[profile.name] = profile
            added.append(profile)
        return tuple(added)

    def refresh_local_models(
        self,
        *,
        discovery: LocalModelDiscovery | None = None,
    ) -> tuple[ModelProfile, ...]:
        source = discovery or LocalModelDiscovery()
        return self.merge_discovered_models(source.discover())

    # ─── 멀티 프로바이더 조회 API (작업 1) ──────────────────────────────

    @property
    def providers(self) -> dict[str, dict[str, ProviderConfigValue]]:
        """providers 섹션 반환 (ollama/openrouter/nim/anthropic/mlx 별 base_url, api_key_env 등)."""
        return self._providers

    def get_provider_config(self, provider: str) -> dict[str, ProviderConfigValue]:
        """특정 provider의 설정(base_url, api_key_env, rate_limit 등)을 반환합니다.

        Args:
            provider: provider 이름 (ollama/openrouter/nim/anthropic/mlx)

        Returns:
            provider 설정 dict. 없으면 빈 dict.
        """
        return self._providers.get(provider, {})

    def resolve_endpoint(self, name: str) -> tuple[str, str, str]:
        """모델의 실제 API 엔드포인트와 키를 해석합니다 (멀티 프로바이더 핵심).

        우선순위:
          1. ModelProfile.api_base / api_key_env (per-model 오버라이드)
          2. providers[profile.provider].base_url / api_key_env (provider 기본값)
          3. config.model.api_base / api_key (전역 폴백 — 하위 호환)

        Args:
            name: 모델 이름

        Returns:
            (base_url, api_key_env_or_value, provider) 튜플.
            api_key는 실제 값이 아니라 환경변수명을 반환 — 호출자가 os.environ에서 조회.
        """
        import os

        from antigravity_k.config import config as app_config

        profile = self.get_model(name)
        provider = profile.provider if profile else ""

        # per-model 오버라이드
        if profile and profile.api_base:
            base_url = profile.api_base
            key_env = profile.api_key_env
        elif provider and provider in self._providers:
            prov_cfg = self._providers[provider]
            base_url = _text(prov_cfg, "base_url")
            key_env = _text(prov_cfg, "api_key_env")
        else:
            # 전역 config로 폴백 (레거시 단일 프로바이더 호환)
            base_url = app_config.model.api_base
            key_env = ""
            provider = app_config.model.api_engine or "ollama"

        # API 키 해석: 환경변수명이 있으면 조회, 없으면 전역 config 키 사용
        if key_env and key_env in os.environ:
            api_key = str(os.environ[key_env])
        elif provider == "ollama":
            api_key = os.environ.get("OLLAMA_API_KEY", "") or "ollama"
        elif provider in {"lmstudio", "lm_studio"}:
            api_key = os.environ.get("LM_STUDIO_API_KEY", "")
            if not api_key and app_config.model.api_engine in {"lm_studio", "lmstudio"}:
                api_key = app_config.model.api_key if app_config.model.api_key != "lm-studio" else ""
        elif profile and profile.api_key_env and profile.api_key_env in os.environ:
            api_key = os.environ[profile.api_key_env]
        else:
            api_key = app_config.model.api_key

        return base_url, api_key, provider

    def find_by_role(self, role: str) -> list[ModelProfile]:
        """Find by role.

        Args:
            role (str): str role.

        Returns:
            list[ModelProfile]: The list[modelprofile] result.

        """
        return [m for m in self._models.values() if role in m.supported_roles]

    def get_default(self, role: str) -> ModelProfile | None:
        """Retrieve default.

        Args:
            role (str): str role.

        Returns:
            ModelProfile | None: The modelprofile | none result.

        """
        name = cast(str | None, getattr(self._defaults, role, None))
        return self._models.get(name) if name else None

    def model_exists(self, name: str) -> bool:
        """Model Exists.

        Args:
            name (str): str name.

        Returns:
            bool: The bool result.

        """
        return self.get_model(name) is not None

    @property
    def defaults(self) -> DefaultModels:
        """Defaults.

        Returns:
            DefaultModels: The defaultmodels result.

        """
        return self._defaults

    @property
    def memory_config(self) -> MemoryConfig:
        """Memory Config.

        Returns:
            MemoryConfig: The memoryconfig result.

        """
        return self._memory

    @property
    def server_config(self) -> ServerConfig:
        """Server Config.

        Returns:
            ServerConfig: The serverconfig result.

        """
        return self._server

    @property
    def model_cache_path(self) -> Path:
        """Model Cache Path.

        Returns:
            Path: The path result.

        """
        paths = _mapping(self._raw.get("paths", {}))
        cache = _text(paths, "model_cache", "~/.cache/antigravity-k/models")
        return Path(os.path.expanduser(cache))

    def summary(self) -> str:
        """Summary.

        Returns:
            str: The str result.

        """
        lines = ["=== Model Registry ==="]
        roles: dict[str, list[ModelProfile]] = {}
        for m in self._models.values():
            roles.setdefault(m.role, []).append(m)
        for role, models in sorted(roles.items()):
            default_name = getattr(self._defaults, role, None)
            lines.append(f"\n[{role}] ({len(models)}개)")
            for m in models:
                marker = " ★" if m.name == default_name else ""
                mem = f"{m.estimated_memory_gb}GB"
                lines.append(f"  - {m.name} ({mem}){marker}")
        lines.append(f"\n메모리 한도: {self._memory.max_loaded_gb}GB")
        return "\n".join(lines)


def _as_cost(value: object) -> float:
    """config의 비용 값을 안전하게 파싱해 음수/비숫자를 0.0(미설정)으로 정규화한다."""
    match value:
        case bool():
            return 0.0
        case int() | float() | str() as raw:
            try:
                parsed = float(raw)
            except ValueError:
                return 0.0
            return max(0.0, parsed)
        case _:
            return 0.0
