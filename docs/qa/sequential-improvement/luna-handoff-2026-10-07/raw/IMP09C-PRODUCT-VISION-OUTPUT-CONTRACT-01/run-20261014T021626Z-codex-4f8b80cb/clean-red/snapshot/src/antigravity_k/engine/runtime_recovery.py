"""RuntimeRecovery — 에이전트 상태 분류 & 자동 복구 파이프라인.

===========================================================
NemoClaw의 runtime-recovery.ts + validation-recovery.ts + validation.ts 이식.

상태 분류:
  - classify_agent_state()     → present / missing / unavailable / degraded
  - classify_inference_failure() → transport / credential / model / endpoint / unknown

복구 결정:
  - determine_recovery()       → retry / credential_reset / model_switch / restart

시스템 Health Check:
  - deep_health_check()        → 인퍼런스, 메모리, 가드레일 전체 상태

사용법:
    state = classify_agent_state(orchestrator)
    recovery = determine_recovery(state)
    health = deep_health_check(components)
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, cast

logger = logging.getLogger("antigravity_k.engine.runtime_recovery")


class _ModelManagerLike(Protocol):
    def list_models(self) -> list[object]: ...

    def loaded_names(self) -> list[str]: ...


class _SessionManagerLike(Protocol):
    def get_session_info(self) -> object: ...


class _MemoryManagerLike(Protocol):
    def get_stats(self) -> object: ...


class _ToolsetManagerLike(Protocol):
    def get_active_tools(self) -> list[str]: ...


class _ShieldsManagerLike(Protocol):
    @property
    def is_up(self) -> bool: ...


# ── 상태 분류 열거형 ──


class AgentState(str, Enum):
    """에이전트 런타임 상태."""

    PRESENT = "present"
    MISSING = "missing"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"


class FailureKind(str, Enum):
    """인퍼런스 실패 유형."""

    TRANSPORT = "transport"
    CREDENTIAL = "credential"
    MODEL = "model"
    ENDPOINT = "endpoint"
    UNKNOWN = "unknown"


class RecoveryAction(str, Enum):
    """복구 행동."""

    RETRY = "retry"
    CREDENTIAL_RESET = "credential_reset"
    MODEL_SWITCH = "model_switch"
    PROVIDER_SWITCH = "provider_switch"
    RESTART = "restart"
    MANUAL = "manual"


class HealthStatus(str, Enum):
    """Health Check 상태."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


# ── 데이터 클래스 ──


@dataclass
class StateClassification:
    """에이전트 상태 분류 결과."""

    state: AgentState
    reason: str
    details: str | None = None


@dataclass
class InferenceClassification:
    """인퍼런스 실패 분류 결과."""

    kind: FailureKind
    retry_action: RecoveryAction
    message: str = ""


@dataclass
class RecoveryDecision:
    """복구 결정."""

    action: RecoveryAction
    message: str
    auto_executable: bool = True
    suggested_command: str | None = None


@dataclass
class ComponentHealth:
    """개별 컴포넌트 Health."""

    name: str
    status: HealthStatus
    detail: str
    latency_ms: float | None = None


@dataclass
class SystemHealth:
    """전체 시스템 Health."""

    status: HealthStatus
    components: list[ComponentHealth]
    diagnosis: str = ""
    checked_at: str = ""


# ── 에이전트 상태 분류 ──


def classify_agent_state(
    orchestrator: object | None = None,
    *,
    model_manager: object | None = None,
    session_manager: object | None = None,
) -> StateClassification:
    """에이전트의 현재 런타임 상태를 분류합니다.

    NemoClaw 패턴: 에이전트 상태 → present / missing / unavailable / degraded
    """
    # 1. Orchestrator 존재 확인
    if orchestrator is None:
        return StateClassification(
            state=AgentState.MISSING,
            reason="orchestrator_not_initialized",
            details="OrchestratorAgent가 초기화되지 않았습니다.",
        )

    # 2. 모델 매니저 상태 확인
    if model_manager is not None:
        try:
            models = cast(_ModelManagerLike, model_manager).list_models()
            if not models:
                return StateClassification(
                    state=AgentState.DEGRADED,
                    reason="no_models_available",
                    details="사용 가능한 모델이 없습니다.",
                )
        except Exception as e:
            logger.exception("Unhandled exception")
            error_text = str(e).lower()
            if any(kw in error_text for kw in ["connection", "timeout", "refused"]):
                return StateClassification(
                    state=AgentState.UNAVAILABLE,
                    reason="model_manager_unreachable",
                    details=f"모델 매니저에 접근할 수 없습니다: {e}",
                )
            return StateClassification(
                state=AgentState.DEGRADED,
                reason="model_manager_error",
                details=str(e),
            )

    # 3. 세션 매니저 상태 확인
    if session_manager is not None:
        try:
            _ = cast(_SessionManagerLike, session_manager).get_session_info()
        except Exception as e:
            logger.exception("Unhandled exception")
            return StateClassification(
                state=AgentState.DEGRADED,
                reason="session_manager_error",
                details=str(e),
            )

    return StateClassification(
        state=AgentState.PRESENT,
        reason="ok",
    )


# ── 인퍼런스 실패 분류 ──


def classify_inference_failure(
    *,
    http_status: int = 0,
    curl_status: int = 0,
    message: str = "",
) -> InferenceClassification:
    """인퍼런스 실패를 유형별로 분류합니다.

    NemoClaw의 classifyValidationFailure() 포팅:
    HTTP 상태 + 에러 메시지를 분석하여 실패 원인과 복구 방법을 결정합니다.
    """
    normalized = " ".join(message.lower().split())

    # curl 에러 (네트워크 단)
    if curl_status:
        return InferenceClassification(
            kind=FailureKind.TRANSPORT,
            retry_action=RecoveryAction.RETRY,
            message=_transport_message(curl_status, normalized),
        )

    # HTTP 429 (Rate Limit) / 5xx (서버 에러)
    if http_status == 429 or (500 <= http_status < 600):
        return InferenceClassification(
            kind=FailureKind.TRANSPORT,
            retry_action=RecoveryAction.RETRY,
            message=f"서버 에러 (HTTP {http_status}). 재시도합니다.",
        )

    # HTTP 401/403 (인증 에러)
    if http_status in (401, 403):
        return InferenceClassification(
            kind=FailureKind.CREDENTIAL,
            retry_action=RecoveryAction.CREDENTIAL_RESET,
            message="인증 실패. API 키를 확인하세요.",
        )

    # 메시지 기반 인증 에러 (HTTP 400 반환하는 프로바이더 포함)
    credential_patterns = [
        "api key expired",
        "api key not valid",
        "api_key_invalid",
        "unauthorized",
        "forbidden",
        "invalid api key",
        "invalid_auth",
        "permission denied",
    ]
    if any(pat in normalized for pat in credential_patterns):
        return InferenceClassification(
            kind=FailureKind.CREDENTIAL,
            retry_action=RecoveryAction.CREDENTIAL_RESET,
            message="API 키가 유효하지 않습니다.",
        )

    # HTTP 400 (모델 에러)
    if http_status == 400:
        return InferenceClassification(
            kind=FailureKind.MODEL,
            retry_action=RecoveryAction.MODEL_SWITCH,
            message="모델 요청 에러. 다른 모델을 사용하세요.",
        )

    # 모델 관련 메시지
    model_patterns = [
        "model.*not found",
        "unknown model",
        "unsupported model",
        "bad model",
    ]
    import re

    if any(re.search(pat, normalized) for pat in model_patterns):
        return InferenceClassification(
            kind=FailureKind.MODEL,
            retry_action=RecoveryAction.MODEL_SWITCH,
            message="모델을 찾을 수 없습니다.",
        )

    # HTTP 404/405 (엔드포인트 에러)
    if http_status in (404, 405):
        return InferenceClassification(
            kind=FailureKind.ENDPOINT,
            retry_action=RecoveryAction.PROVIDER_SWITCH,
            message="API 엔드포인트를 찾을 수 없습니다.",
        )

    return InferenceClassification(
        kind=FailureKind.UNKNOWN,
        retry_action=RecoveryAction.MANUAL,
        message=f"알 수 없는 에러 (HTTP {http_status}): {message[:200]}",
    )


# ── 복구 결정 ──


def determine_recovery(
    agent_state: StateClassification,
    inference_failure: InferenceClassification | None = None,
) -> RecoveryDecision:
    """상태 분류에 기반하여 복구 전략을 결정합니다.

    NemoClaw의 shouldAttemptGatewayRecovery() + getRecoveryCommand() 포팅.
    """
    # 에이전트 레벨 복구
    if agent_state.state == AgentState.MISSING:
        return RecoveryDecision(
            action=RecoveryAction.RESTART,
            message="에이전트가 초기화되지 않았습니다. 서버를 재시작하세요.",
            auto_executable=False,
            suggested_command="서버 재시작",
        )

    if agent_state.state == AgentState.UNAVAILABLE:
        return RecoveryDecision(
            action=RecoveryAction.RETRY,
            message=f"에이전트에 접근할 수 없습니다: {agent_state.details}",
            auto_executable=True,
        )

    # 인퍼런스 레벨 복구
    if inference_failure:
        return RecoveryDecision(
            action=inference_failure.retry_action,
            message=inference_failure.message,
            auto_executable=inference_failure.retry_action == RecoveryAction.RETRY,
        )

    if agent_state.state == AgentState.DEGRADED:
        return RecoveryDecision(
            action=RecoveryAction.MANUAL,
            message=f"시스템이 저하 상태입니다: {agent_state.reason}",
            auto_executable=False,
        )

    return RecoveryDecision(
        action=RecoveryAction.RETRY,
        message="시스템 정상",
        auto_executable=True,
    )


# ── Deep Health Check ──


def deep_health_check(
    *,
    model_manager: object | None = None,
    session_manager: object | None = None,
    memory_manager: object | None = None,
    toolset_manager: object | None = None,
    shields_manager: object | None = None,
) -> SystemHealth:
    """시스템 전체 깊은 Health Check를 수행합니다.

    NemoClaw의 verifyDashboardChain() 패턴:
    각 컴포넌트를 독립적으로 확인하고 종합 상태를 반환합니다.
    """
    import datetime

    components: list[ComponentHealth] = []

    # 1. Model Manager
    components.append(
        _check_component(
            "model_manager",
            model_manager,
            check_fn=lambda mm: bool(cast(_ModelManagerLike, mm).loaded_names()),
        ),
    )

    # 2. Session Manager
    components.append(
        _check_component(
            "session_manager",
            session_manager,
            check_fn=lambda sm: cast(_SessionManagerLike, sm).get_session_info() is not None,
        ),
    )

    # 3. Memory Manager
    components.append(
        _check_component(
            "memory_manager",
            memory_manager,
            check_fn=lambda mm: cast(_MemoryManagerLike, mm).get_stats() is not None,
        ),
    )

    # 4. Toolset Manager
    components.append(
        _check_component(
            "toolset_manager",
            toolset_manager,
            check_fn=lambda ts: len(cast(_ToolsetManagerLike, ts).get_active_tools()) > 0,
        ),
    )

    # 5. Shields
    if shields_manager:
        components.append(
            ComponentHealth(
                name="shields",
                status=HealthStatus.HEALTHY,
                detail=f"{'UP' if cast(_ShieldsManagerLike, shields_manager).is_up else 'DOWN'}",
            ),
        )
    else:
        components.append(
            ComponentHealth(
                name="shields",
                status=HealthStatus.HEALTHY,
                detail="not configured",
            ),
        )

    # 종합 상태 결정
    unhealthy = [c for c in components if c.status == HealthStatus.UNHEALTHY]
    degraded = [c for c in components if c.status == HealthStatus.DEGRADED]

    if unhealthy:
        overall = HealthStatus.UNHEALTHY
        diagnosis = "; ".join(f"{c.name}: {c.detail}" for c in unhealthy)
    elif degraded:
        overall = HealthStatus.DEGRADED
        diagnosis = "; ".join(f"{c.name}: {c.detail}" for c in degraded)
    else:
        overall = HealthStatus.HEALTHY
        diagnosis = ""

    return SystemHealth(
        status=overall,
        components=components,
        diagnosis=diagnosis,
        checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    )


# ── 내부 헬퍼 ──


def _check_component(
    name: str,
    component: object | None,
    check_fn: Callable[[object], bool] | None = None,
) -> ComponentHealth:
    """개별 컴포넌트를 체크합니다."""
    if component is None:
        return ComponentHealth(
            name=name,
            status=HealthStatus.HEALTHY,
            detail="not configured",
        )

    start = time.time()
    try:
        if check_fn and check_fn(component):
            latency = (time.time() - start) * 1000
            return ComponentHealth(
                name=name,
                status=HealthStatus.HEALTHY,
                detail="ok",
                latency_ms=round(latency, 1),
            )
        else:
            latency = (time.time() - start) * 1000
            return ComponentHealth(
                name=name,
                status=HealthStatus.DEGRADED,
                detail="check returned false",
                latency_ms=round(latency, 1),
            )
    except Exception as e:
        logger.exception("Unhandled exception")
        latency = (time.time() - start) * 1000
        return ComponentHealth(
            name=name,
            status=HealthStatus.UNHEALTHY,
            detail=str(e)[:200],
            latency_ms=round(latency, 1),
        )


def _transport_message(curl_status: int, text: str) -> str:
    """네트워크 에러에 대한 상세 메시지를 생성합니다."""
    if curl_status == 6 or "could not resolve host" in text:
        return "호스트 이름을 확인할 수 없습니다. DNS 또는 VPN을 확인하세요."
    if curl_status == 7 or "connection refused" in text:
        return "서버에 연결할 수 없습니다. URL과 서비스 상태를 확인하세요."
    if curl_status == 28 or "timed out" in text or "timeout" in text:
        return "요청 시간이 초과되었습니다. 네트워크 상태를 확인하세요."
    if curl_status in (35, 60) or "ssl" in text or "tls" in text or "certificate" in text:
        return "TLS/인증서 에러입니다. HTTPS 연결을 확인하세요."
    if "proxy" in text:
        return "프록시 에러입니다. 프록시 설정을 확인하세요."
    return "네트워크 또는 전송 에러가 발생했습니다."
