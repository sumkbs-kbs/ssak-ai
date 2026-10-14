"""hyperparameters — TRN-01 학습 하이퍼파라미터 단일 검증·capability·digest 모듈.

GA-100 plan §TRN-01: "iterations, batch, layers, learning rate를 validation 후
한 번 resolve하고 동일 구조에서 argv, progress, recipe digest와 결과 metadata를
만든다."

역할:
1. ``validate_hyperparameters`` — 0/음수/과대 값·미지원 키를 실행 전에 거절한다.
   lora_pipeline.apply_recipe와 training_jobs_api 시작 게이트가 모두 이 함수를
   통과하므로 validation 규칙이 한곳에 유지된다 (단일 source).
2. ``backend_capabilities`` — MLX(로컬 실행)와 Unsloth(CUDA 전용, 스크립트
   저장만 가능)의 지원 차이를 capability schema로 표시한다.
3. ``compute_recipe_digest`` — recipe 이름/베이스 모델/플랫폼/정규화된 오버라이드를
   정규 직렬화해 결정적 SHA-256 digest를 만든다. 재실행 provenance의 핵심 키.

순수 stdlib 모듈 — pydantic/fastapi 없이 어디서든 import 가능하다.
"""

from __future__ import annotations

import hashlib
import json
import math
from decimal import Decimal, InvalidOperation
from typing import Final

__all__ = [
    "HyperparameterValidationError",
    "backend_capabilities",
    "compute_recipe_digest",
    "known_hyperparameter_keys",
    "validate_hyperparameters",
]


class HyperparameterValidationError(ValueError):
    """하이퍼파라미터 검증 실패 — 실행 전 거절용."""


# 키별 허용 범위 (plan: 0/음수/과대 값 거절)
#  - iterations: mlx-lm --iters (1..1_000_000)
#  - batch_size: mlx-lm --batch-size / unsloth per_device_train_batch_size (1..128)
#  - learning_rate: 0 < lr < 1 (문자열 "1e-5"/숫자 모두 허용, 정규화 후 비교)
#  - lora_rank / lora_alpha: 1..1024 / 1..2048 (training_recipe.TrainingRecipe와 동일 상한)
#  - num_layers: mlx-lm --num-layers (1..128)
#  - gradient_accumulation_steps: unsloth 전용 (mlx 미지원 → capability 거절)
#  - num_train_epochs: unsloth 전용 (mlx는 iterations로 환산)
#  - max_seq_length: unsloth 전용 (512..131072)
_RANGES: Final[dict[str, tuple[int | float | None, int | float | None]]] = {
    "iterations": (1, 1_000_000),
    "batch_size": (1, 128),
    "learning_rate": (None, None),  # (0, 1) 열린 구간 — 아래에서 특수 처리
    "lora_rank": (1, 1024),
    "lora_alpha": (1, 2048),
    "num_layers": (1, 128),
    "gradient_accumulation_steps": (1, 4096),
    "num_train_epochs": (1, 100),
    "max_seq_length": (512, 131_072),
}

# mlx가 지원하지 않는 키 (unsloth 전용) — capability 게절 대상
_UNSLOTH_ONLY_KEYS: Final[frozenset[str]] = frozenset(
    {"num_train_epochs", "max_seq_length", "gradient_accumulation_steps"}
)

_INT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "iterations",
        "batch_size",
        "lora_rank",
        "lora_alpha",
        "num_layers",
        "gradient_accumulation_steps",
        "num_train_epochs",
        "max_seq_length",
    }
)


def known_hyperparameter_keys() -> tuple[str, ...]:
    """검증 대상 하이퍼파라미터 키 (capability schema의 supported_keys와 동일 집합)."""
    return tuple(sorted(_RANGES))


def _normalize_learning_rate(value: object) -> str:
    """learning_rate를 문자열 표기로 정규화 ("1e-5", 0.00001, Decimal 모두 수용)."""
    if isinstance(value, bool):
        raise HyperparameterValidationError("learning_rate: 숫자 또는 '1e-5' 형태의 문자열이어야 합니다")
    try:
        dec = Decimal(str(value))
    except (InvalidOperation, ValueError, ArithmeticError) as exc:
        raise HyperparameterValidationError(f"learning_rate: 숫자로 해석 불가한 값 {value!r}") from exc
    if not dec.is_finite():
        raise HyperparameterValidationError("learning_rate: 유한한 숫자여야 합니다")
    if dec <= 0:
        raise HyperparameterValidationError(f"learning_rate: 0보다 커야 합니다 (got {dec})")
    if dec >= 1:
        raise HyperparameterValidationError(f"learning_rate: 1 미만이어야 합니다 (got {dec})")
    exp = dec.as_tuple().exponent
    use_e = (isinstance(exp, int) and exp < -6) or "e" in str(value).lower()
    return format(dec, "e") if use_e else str(dec)


def _normalize_int(key: str, value: object) -> int:
    if isinstance(value, bool):
        raise HyperparameterValidationError(f"{key}: 정수여야 합니다")
    if not isinstance(value, (str, int, float)):
        raise HyperparameterValidationError(f"{key}: 정수로 해석 불가한 값 {value!r}")
    try:
        num = float(value)
    except ValueError as exc:
        raise HyperparameterValidationError(f"{key}: 정수로 해석 불가한 값 {value!r}") from exc
    if not math.isfinite(num) or num != int(num):
        raise HyperparameterValidationError(f"{key}: 정수여야 합니다 (got {value!r})")
    return int(num)


def validate_hyperparameters(
    overrides: dict[str, float | int | str] | None,
    *,
    backend: str = "mlx",
) -> dict[str, float | int | str]:
    """레시피/사용자 하이퍼파라미터를 검증·정규화한다.

    규칙 (TRN-01 수용기준 2):
      - 알 수 없는 키는 거절 (오타 조용히 무시 방지)
      - 0/음수/과대 값은 허용 범위 대조 후 거절
      - learning_rate는 0 < lr < 1 (정규화된 문자열로 반환)
      - backend="mlx"에서 unsloth 전용 키는 거절 (capability 미지원 명시)

    Returns:
        정규화된 dict (정수 키는 int, learning_rate는 정규 문자열)

    Raises:
        HyperparameterValidationError: 위반 시 — 값과 이유를 메시지에 포함
    """
    if not overrides:
        return {}

    backend_norm = backend.strip().lower()
    normalized: dict[str, float | int | str] = {}
    for key, value in overrides.items():
        if key not in _RANGES:
            raise HyperparameterValidationError(
                f"알 수 없는 하이퍼파라미터 키: {key!r} (허용: {', '.join(known_hyperparameter_keys())})"
            )
        if key == "learning_rate":
            normalized[key] = _normalize_learning_rate(value)
            continue
        ivalue = _normalize_int(key, value)
        low, high = _RANGES[key]
        if ivalue < int(low or 0):
            raise HyperparameterValidationError(f"{key}: {low} 이상이어야 합니다 (got {ivalue})")
        if high is not None and ivalue > int(high):
            raise HyperparameterValidationError(f"{key}: {high} 이하여야 합니다 (got {ivalue})")
        if key in _UNSLOTH_ONLY_KEYS and backend_norm == "mlx":
            raise HyperparameterValidationError(
                f"{key}: mlx 백엔드는 미지원 option입니다 (unsloth 전용). mlx에서는 iterations로 환산해 주세요."
            )
        normalized[key] = ivalue
    return normalized


def backend_capabilities(backend: str) -> dict[str, object]:
    """백엔드 capability schema (TRN-01 수용기준 3).

    mlx: 로컬(Apple Silicon) 실행 가능, mlx-lm 플래그 집합 사용.
    unsloth: CUDA GPU 필요 — 로컬 실행 불가, 스크립트 저장만 수행.
    """
    backend_norm = backend.strip().lower()
    if backend_norm == "mlx":
        return {
            "backend": "mlx",
            "executable": True,
            "supported_keys": list(known_hyperparameter_keys()),
            "unsupported_keys": sorted(_UNSLOTH_ONLY_KEYS),
            "reason": "mlx-lm 로컬 학습 (Apple Silicon). unsloth 전용 키는 미지원.",
        }
    if backend_norm == "unsloth":
        return {
            "backend": "unsloth",
            "executable": False,
            "supported_keys": list(known_hyperparameter_keys()),
            "unsupported_keys": [],
            "reason": "CUDA GPU 호스트에서 실행. 로컬에서는 스크립트만 저장된다.",
        }
    raise HyperparameterValidationError(f"알 수 없는 백엔드: {backend!r} (mlx / unsloth)")


def compute_recipe_digest(
    *,
    recipe: str,
    base_model: str,
    platform: str,
    overrides: dict[str, float | int | str] | None = None,
) -> str:
    """결정적 recipe digest (TRN-01 수용기준 4).

    정규화된 오버라이드 + recipe/모델/플랫폼을 정렬된 JSON으로 직렬화해
    SHA-256. 키 순서/표기 차이("1e-5" vs 0.00001)에도 동일 digest가 나온다.
    """
    try:
        normalized = validate_hyperparameters(overrides, backend=platform)
    except HyperparameterValidationError:
        # digest는 검증 전 단계의 안정적 키가 필요하므로 learning_rate만 정규화 재시도
        normalized = {}
        for key, value in (overrides or {}).items():
            if key == "learning_rate":
                normalized[key] = _normalize_learning_rate(value)
            else:
                normalized[key] = value
    payload = json.dumps(
        {
            "recipe": recipe,
            "base_model": base_model,
            "platform": platform,
            "overrides": dict(sorted(normalized.items())),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
