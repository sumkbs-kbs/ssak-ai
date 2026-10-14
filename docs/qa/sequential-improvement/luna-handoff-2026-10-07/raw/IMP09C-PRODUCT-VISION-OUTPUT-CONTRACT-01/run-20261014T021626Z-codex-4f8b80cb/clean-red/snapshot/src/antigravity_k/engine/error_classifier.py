"""ErrorClassifier — API 에러 분류 및 자동 복구 결정 시스템.

========================================================
Hermes Agent의 error_classifier.py 패턴을 Ssak-Ai에 이식.

구조화된 에러 분류 파이프라인:
  1. 프로바이더 특수 패턴 (Anthropic thinking sig, context tier 등)
  2. HTTP 상태 코드 + 메시지 정밀 분류
  3. 에러 코드 분류 (응답 body에서)
  4. 메시지 패턴 매칭 (billing vs rate_limit vs context overflow)
  5. 트랜스포트 에러 추정 (timeout, connection)
  6. 폴백: unknown (재시도 가능)

사용법:
    from antigravity_k.engine.error_classifier import classify_api_error

    try:
        response = await llm_call(...)
    except Exception as e:
        classified = classify_api_error(e, provider="openrouter", model="gpt-4o")
        if classified.retryable:
            await retry(...)
        elif classified.should_compress:
            await compress_context(...)
        elif classified.should_fallback:
            await try_fallback_model(...)
"""

from __future__ import annotations

import enum
import json
import logging
from dataclasses import dataclass, field
from typing import Protocol, TypedDict, Unpack, cast

logger = logging.getLogger("antigravity_k.engine.error_classifier")


class ClassifiedErrorOverrides(TypedDict, total=False):
    retryable: bool
    should_compress: bool
    should_rotate_credential: bool
    should_fallback: bool


class ResultFn(Protocol):
    def __call__(self, reason: FailoverReason, **overrides: Unpack[ClassifiedErrorOverrides]) -> ClassifiedError: ...


# ── 에러 유형 분류 ──


class FailoverReason(enum.Enum):
    """API 호출 실패 원인 — 복구 전략 결정에 사용."""

    # 인증
    auth = "auth"  # 일시적 401/403 — 자격 증명 갱신/교체
    auth_permanent = "auth_permanent"  # 갱신 후에도 실패 — 중단

    # 과금/할당량
    billing = "billing"  # 402 또는 크레딧 소진 — 즉시 교체
    rate_limit = "rate_limit"  # 429 또는 쿼터 스로틀링 — 백오프

    # 서버 측
    overloaded = "overloaded"  # 503/529 — 프로바이더 과부하
    server_error = "server_error"  # 500/502 — 내부 서버 오류

    # 네트워크
    timeout = "timeout"  # 연결/읽기 타임아웃 — 재시도

    # 컨텍스트/페이로드
    context_overflow = "context_overflow"  # 컨텍스트 초과 — 압축 필요
    payload_too_large = "payload_too_large"  # 413 — 페이로드 축소

    # 모델
    model_not_found = "model_not_found"  # 404 또는 잘못된 모델 — 폴백

    # 요청 형식
    format_error = "format_error"  # 400 잘못된 요청 — 중단 또는 수정

    # 프로바이더 특수
    thinking_signature = "thinking_signature"  # Anthropic thinking 블록 서명 오류

    # 기본
    unknown = "unknown"  # 분류 불가 — 백오프 재시도


# ── 분류 결과 ──


@dataclass
class ClassifiedError:
    """API 에러의 구조화된 분류 + 복구 힌트."""

    reason: FailoverReason
    status_code: int | None = None
    provider: str | None = None
    model: str | None = None
    message: str = ""
    error_context: dict[str, object] = field(default_factory=dict)

    # 복구 힌트 — 재시도 루프에서 사용
    retryable: bool = True
    should_compress: bool = False
    should_rotate_credential: bool = False
    should_fallback: bool = False

    @property
    def is_auth(self) -> bool:
        """Check if auth.

        Returns:
            bool: The bool result.

        """
        return self.reason in (FailoverReason.auth, FailoverReason.auth_permanent)

    @property
    def is_context_related(self) -> bool:
        """Check if context related.

        Returns:
            bool: The bool result.

        """
        return self.reason in (FailoverReason.context_overflow, FailoverReason.payload_too_large)

    def to_dict(self) -> dict[str, object]:
        """To Dict.

        Returns:
            dict[str, object]: The serialized error result.

        """
        return {
            "reason": self.reason.value,
            "status_code": self.status_code,
            "provider": self.provider,
            "model": self.model,
            "message": self.message,
            "retryable": self.retryable,
            "should_compress": self.should_compress,
            "should_fallback": self.should_fallback,
        }


# ── 패턴 정의 ──

_BILLING_PATTERNS = [
    "insufficient credits",
    "insufficient_quota",
    "insufficient balance",
    "credit balance",
    "credits have been exhausted",
    "top up your credits",
    "payment required",
    "billing hard limit",
    "exceeded your current quota",
    "account is deactivated",
    "plan does not include",
]

_RATE_LIMIT_PATTERNS = [
    "rate limit",
    "rate_limit",
    "too many requests",
    "throttled",
    "requests per minute",
    "tokens per minute",
    "requests per day",
    "try again in",
    "please retry after",
    "resource_exhausted",
]

_CONTEXT_OVERFLOW_PATTERNS = [
    "context length",
    "context size",
    "maximum context",
    "token limit",
    "too many tokens",
    "reduce the length",
    "exceeds the limit",
    "context window",
    "prompt is too long",
    "prompt exceeds max length",
    "max_tokens",
    "maximum number of tokens",
    "input is too long",
    "max_model_len",
    "context length exceeded",
    # 중국어 에러 메시지
    "超过最大长度",
    "上下文长度",
]

_MODEL_NOT_FOUND_PATTERNS = [
    "is not a valid model",
    "invalid model",
    "model not found",
    "model_not_found",
    "does not exist",
    "no such model",
    "unknown model",
    "unsupported model",
]

_AUTH_PATTERNS = [
    "invalid api key",
    "invalid_api_key",
    "authentication",
    "unauthorized",
    "forbidden",
    "invalid token",
    "token expired",
    "token revoked",
    "access denied",
]

_TRANSPORT_ERROR_TYPES = frozenset(
    {
        "ReadTimeout",
        "ConnectTimeout",
        "PoolTimeout",
        "ConnectError",
        "RemoteProtocolError",
        "ConnectionError",
        "ConnectionResetError",
        "ConnectionAbortedError",
        "BrokenPipeError",
        "TimeoutError",
        "ReadError",
        "ServerDisconnectedError",
        "SSLError",
        "SSLEOFError",
        "APIConnectionError",
        "APITimeoutError",
    },
)

_SERVER_DISCONNECT_PATTERNS = [
    "server disconnected",
    "peer closed connection",
    "connection reset by peer",
    "connection was closed",
    "network connection lost",
    "unexpected eof",
    "incomplete chunked read",
]

_USAGE_LIMIT_TRANSIENT_SIGNALS = [
    "try again",
    "retry",
    "resets at",
    "reset in",
    "wait",
    "requests remaining",
    "window",
]


# ── 메인 분류 함수 ──


def classify_api_error(
    error: Exception,
    *,
    provider: str = "",
    model: str = "",
    approx_tokens: int = 0,
    context_length: int = 200_000,
    num_messages: int = 0,
) -> ClassifiedError:
    """API 에러를 구조화된 복구 권고로 분류하세요.

    우선순위 파이프라인:
      1. 프로바이더 특수 패턴
      2. HTTP 상태 코드 + 메시지 정밀 분류
      3. 메시지 패턴 매칭
      4. 서버 연결 끊김 + 대용량 세션 → context overflow
      5. 트랜스포트 에러 추정
      6. 폴백: unknown
    """
    status_code = _extract_status_code(error)
    error_type = type(error).__name__
    error_msg = str(error).lower()
    body = _extract_error_body(error)

    # body 메시지도 패턴 매칭에 포함
    if isinstance(body, dict):
        body_map = cast(dict[str, object], cast(object, body))
        err_obj = body_map.get("error", {})
        if isinstance(err_obj, dict):
            err_map = cast(dict[str, object], cast(object, err_obj))
            body_msg = str(err_map.get("message", "")).lower()
            if body_msg and body_msg not in error_msg:
                error_msg = f"{error_msg} {body_msg}"

    def _result(reason: FailoverReason, **overrides: Unpack[ClassifiedErrorOverrides]) -> ClassifiedError:
        return ClassifiedError(
            reason=reason,
            status_code=status_code,
            provider=provider,
            model=model,
            message=str(error)[:500],
            **overrides,
        )

    # ── 1. 프로바이더 특수 패턴 ──

    # Anthropic thinking 블록 서명 오류
    if status_code == 400 and "signature" in error_msg and "thinking" in error_msg:
        return _result(FailoverReason.thinking_signature, retryable=True)

    # ── 2. HTTP 상태 코드 분류 ──

    if status_code is not None:
        classified = _classify_by_status(
            status_code,
            error_msg,
            approx_tokens,
            context_length,
            num_messages,
            _result,
        )
        if classified is not None:
            return classified

    # ── 3. 메시지 패턴 매칭 (상태 코드 없음) ──

    # 과금 소진
    if any(p in error_msg for p in _BILLING_PATTERNS):
        return _result(
            FailoverReason.billing,
            retryable=False,
            should_rotate_credential=True,
            should_fallback=True,
        )

    # Rate limit
    if any(p in error_msg for p in _RATE_LIMIT_PATTERNS):
        return _result(FailoverReason.rate_limit, retryable=True, should_rotate_credential=True)

    # Context overflow
    if any(p in error_msg for p in _CONTEXT_OVERFLOW_PATTERNS):
        return _result(FailoverReason.context_overflow, retryable=True, should_compress=True)

    # 인증
    if any(p in error_msg for p in _AUTH_PATTERNS):
        return _result(FailoverReason.auth, retryable=False, should_fallback=True)

    # 모델 미발견
    if any(p in error_msg for p in _MODEL_NOT_FOUND_PATTERNS):
        return _result(FailoverReason.model_not_found, retryable=False, should_fallback=True)

    # ── 4. 서버 연결 끊김 + 대용량 세션 ──

    is_disconnect = any(p in error_msg for p in _SERVER_DISCONNECT_PATTERNS)
    if is_disconnect and not status_code:
        is_large = approx_tokens > context_length * 0.6 or approx_tokens > 120_000 or num_messages > 200
        if is_large:
            return _result(FailoverReason.context_overflow, retryable=True, should_compress=True)
        return _result(FailoverReason.timeout, retryable=True)

    # ── 5. 트랜스포트 에러 ──

    if error_type in _TRANSPORT_ERROR_TYPES or isinstance(
        error,
        (TimeoutError, ConnectionError, OSError),
    ):
        return _result(FailoverReason.timeout, retryable=True)

    # ── 6. 폴백 ──

    return _result(FailoverReason.unknown, retryable=True)


# ── 상태 코드 기반 분류 ──


def _classify_by_status(
    status_code: int,
    error_msg: str,
    approx_tokens: int,
    context_length: int,
    num_messages: int,
    result_fn: ResultFn,
) -> ClassifiedError | None:
    """HTTP 상태 코드 기반 에러 분류."""
    if status_code == 401:
        return result_fn(
            FailoverReason.auth,
            retryable=False,
            should_rotate_credential=True,
            should_fallback=True,
        )

    if status_code == 403:
        if "key limit exceeded" in error_msg or "spending limit" in error_msg:
            return result_fn(
                FailoverReason.billing,
                retryable=False,
                should_rotate_credential=True,
                should_fallback=True,
            )
        return result_fn(FailoverReason.auth, retryable=False, should_fallback=True)

    if status_code == 402:
        # 일시적 사용량 한도 vs 영구 과금 소진 구분
        has_transient = any(p in error_msg for p in _USAGE_LIMIT_TRANSIENT_SIGNALS)
        if has_transient:
            return result_fn(
                FailoverReason.rate_limit,
                retryable=True,
                should_rotate_credential=True,
            )
        return result_fn(
            FailoverReason.billing,
            retryable=False,
            should_rotate_credential=True,
            should_fallback=True,
        )

    if status_code == 404:
        if any(p in error_msg for p in _MODEL_NOT_FOUND_PATTERNS):
            return result_fn(FailoverReason.model_not_found, retryable=False, should_fallback=True)
        return result_fn(FailoverReason.unknown, retryable=True)

    if status_code == 413:
        return result_fn(FailoverReason.payload_too_large, retryable=True, should_compress=True)

    if status_code == 429:
        return result_fn(
            FailoverReason.rate_limit,
            retryable=True,
            should_rotate_credential=True,
            should_fallback=True,
        )

    if status_code == 400:
        return _classify_400(error_msg, approx_tokens, context_length, num_messages, result_fn)

    if status_code in (500, 502):
        return result_fn(FailoverReason.server_error, retryable=True)

    if status_code in (503, 529):
        return result_fn(FailoverReason.overloaded, retryable=True)

    if 400 <= status_code < 500:
        return result_fn(FailoverReason.format_error, retryable=False, should_fallback=True)

    if 500 <= status_code < 600:
        return result_fn(FailoverReason.server_error, retryable=True)

    return None


def _classify_400(
    error_msg: str,
    approx_tokens: int,
    context_length: int,
    num_messages: int,
    result_fn: ResultFn,
) -> ClassifiedError:
    """400 Bad Request 세부 분류."""
    # Context overflow
    if any(p in error_msg for p in _CONTEXT_OVERFLOW_PATTERNS):
        return result_fn(FailoverReason.context_overflow, retryable=True, should_compress=True)

    # 모델 미발견 (일부 프로바이더는 400으로 반환)
    if any(p in error_msg for p in _MODEL_NOT_FOUND_PATTERNS):
        return result_fn(FailoverReason.model_not_found, retryable=False, should_fallback=True)

    # Rate limit (일부 프로바이더는 400으로 반환)
    if any(p in error_msg for p in _RATE_LIMIT_PATTERNS):
        return result_fn(FailoverReason.rate_limit, retryable=True, should_rotate_credential=True)

    # 제네릭 400 + 대용량 세션 → 추정 context overflow
    is_large = approx_tokens > context_length * 0.4 or approx_tokens > 80_000 or num_messages > 80
    if is_large:
        return result_fn(FailoverReason.context_overflow, retryable=True, should_compress=True)

    return result_fn(FailoverReason.format_error, retryable=False, should_fallback=True)


# ── 에러 정보 추출 유틸리티 ──


def _extract_status_code(error: Exception) -> int | None:
    """예외에서 HTTP 상태 코드 추출."""
    for attr in ("status_code", "status", "code", "http_status"):
        code = getattr(error, attr, None)
        if isinstance(code, int):
            return code
    # httpx.HTTPStatusError 호환
    response = cast(object, getattr(error, "response", None))
    if response is not None:
        code = getattr(response, "status_code", None)
        if isinstance(code, int):
            return code
    return None


class JsonCallable(Protocol):
    def __call__(self) -> object: ...


def _extract_error_body(error: Exception) -> dict[str, object] | None:
    """예외에서 응답 body JSON 추출."""
    response = cast(object, getattr(error, "response", None))
    if response is None:
        # OpenAI SDK: .body 속성
        body = cast(object, getattr(error, "body", None))
        if isinstance(body, dict):
            return cast(dict[str, object], cast(object, body))
        return None

    # httpx 응답
    try:
        json_method = cast(JsonCallable | None, getattr(response, "json", None))
        if json_method is not None:
            parsed = json_method()
            if isinstance(parsed, dict):
                return cast(dict[str, object], cast(object, parsed))
    except Exception as e:
        logger.exception("Unhandled exception")
        logger.debug("Failed to read json from response: %s", e)

    text = cast(object, getattr(response, "text", None))
    if isinstance(text, str) and text:
        try:
            parsed = cast(object, json.loads(text))
            if isinstance(parsed, dict):
                return cast(dict[str, object], cast(object, parsed))
        except (json.JSONDecodeError, TypeError):
            logger.warning("예외 발생 (silent swallow 제거)", exc_info=True)

    return None
