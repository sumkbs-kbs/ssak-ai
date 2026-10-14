"""검색 통합 상태 — 런타임 내부 용어를 **사용자 의미**로 옮긴다 (task 14).

task 12 는 상태기계(`disabled/stopped/starting/ready/degraded/failed/stopping`)를 만들었고
task 13 은 라우팅 결정(`enabled/mode/fallback/artifact_path`)을 만들었다. 둘 다 **구현 용어**다.
화면이 그대로 보여주면 사용자는 "degraded 가 뭔데?"를 묻게 되고, 더 나쁘게는 아무 뜻 없는
"ready" 를 성공으로 읽는다. 이 모듈이 그 사이의 번역기다:

    settings + runtime 상태  →  {availability, label, detail, recoverable, action}

그리고 화면이 버튼 하나로 회복할 수 있게 **재시도**와 **연결 확인(실제 검색 1회)** 을 제공한다.
둘 다 명시적이고 유계다: 재시도는 회로를 닫고 bounded timeout 안에서 시작을 시도하며, 연결 확인은
`search_with_bundled_provider` 를 **정확히 한 번** 부른다(fanout 없음).

비밀 위생: 이 모듈은 어떤 비밀도 돌려주지 않는다. artifact 는 **파일명만** 노출하고(경로는
사용자 자신이 입력한 값이므로 설정 화면이 따로 보여준다), 토큰은 존재 여부조차 여기서 다루지 않는다.
"""

from __future__ import annotations

import concurrent.futures
import logging
from typing import TYPE_CHECKING, cast

from antigravity_k.tools.ssak_search_provider import (
    EVIDENCE_HISTORY_LIMIT,
    SsakSearchSettings,
    bundled_runtime_config,
    effective_bundle,
    is_trusted_artifact_path,
    latest_search_evidence,
    search_with_bundled_provider,
    settings_snapshot,
)

if TYPE_CHECKING:  # pragma: no cover — 순환 import 방지
    from antigravity_k.tools.ssak_search_runtime import SsakSearchRuntime

logger = logging.getLogger(__name__)

# ── availability 어휘 ────────────────────────────────────────────────────────
# 값은 API 계약이다(화면·시험이 문자열로 비교한다). 라벨은 화면 문구다.
DISABLED = "disabled"
MISCONFIGURED = "misconfigured"
IDLE = "idle"
STARTING = "starting"
AVAILABLE = "available"
UNAVAILABLE = "unavailable"

AVAILABILITY_LABELS: dict[str, str] = {
    DISABLED: "검색 꺼짐",
    MISCONFIGURED: "설정 확인 필요",
    IDLE: "시작 전",
    STARTING: "시작 중",
    AVAILABLE: "사용 가능",
    UNAVAILABLE: "연결 실패 · 재시도 가능",
}

#: 화면이 상태 배지에 붙일 의미(색/아이콘). 제품의 디자인 시스템 토큰 이름을 그대로 쓴다.
AVAILABILITY_TONES: dict[str, str] = {
    DISABLED: "muted",
    MISCONFIGURED: "warning",
    IDLE: "info",
    STARTING: "info",
    AVAILABLE: "success",
    UNAVAILABLE: "error",
}

#: 상태에서 **할 수 있는 일**의 문구. 사용자에게 다음 행동을 알려준다.
AVAILABILITY_ACTIONS: dict[str, str] = {
    DISABLED: "켜면 번들 검색이 대신 답합니다.",
    MISCONFIGURED: "번들 경로를 신뢰된 위치로 지정하세요.",
    IDLE: "첫 검색에서 자동으로 시작합니다.",
    STARTING: "잠시 기다리거나 연결을 확인하세요.",
    AVAILABLE: "검색이 준비됐습니다.",
    UNAVAILABLE: "다시 시도하면 회로를 닫고 재시작합니다.",
}

#: 런타임 상태 → 사용자 의미. 여기 없는 상태는 **연결 실패**로 본다(모르는 것을 성공으로 읽지 않는다).
_STATE_TO_AVAILABILITY: dict[str, str] = {
    "disabled": DISABLED,
    "stopped": IDLE,
    "starting": STARTING,
    "ready": AVAILABLE,
    "degraded": UNAVAILABLE,
    "failed": UNAVAILABLE,
    "stopping": STARTING,
}

#: 재시도가 시도해 볼 가치가 있는 상태(회복 가능). `misconfigured` 는 사용자가 고쳐야 한다.
_RECOVERABLE: frozenset[str] = frozenset({IDLE, STARTING, UNAVAILABLE})

#: 재시도/연결 확인이 기다리는 상한(초). 이 시간을 넘기면 "아직 시작 중"으로 정직하게 보고한다.
DEFAULT_RETRY_TIMEOUT = 25.0
DEFAULT_PROBE_TIMEOUT = 20.0


def _availability_for(settings: SsakSearchSettings, runtime: SsakSearchRuntime | None) -> str:
    if settings.problem:
        return MISCONFIGURED
    if not settings.enabled:
        return DISABLED
    if not settings.mode_supported:
        return MISCONFIGURED
    if not is_trusted_artifact_path(settings.artifact_path, settings.extra_trusted_roots):
        # 켰는데 경로가 신뢰 밖이다 — 런타임도 fail-closed 로 거절하므로 여기서 정직하게 말한다.
        return MISCONFIGURED
    if runtime is None:
        return IDLE
    state = runtime.state.value
    availability = _STATE_TO_AVAILABILITY.get(state)
    if availability is None:
        # 모르는 상태를 성공으로 읽지 않는다 — 상태기계가 커졌는데 이 표를 안 고치면
        # 화면은 "사용 가능"을 말하고 사용자는 실패를 성공으로 읽는다.
        logger.warning("알 수 없는 검색 런타임 상태를 연결 실패로 보고합니다: %s", state)
        return UNAVAILABLE
    return availability


def _settings_dict(settings: SsakSearchSettings) -> dict[str, object]:
    artifact = str(settings.artifact_path or "").strip()
    # 명시 경로가 없어도 설치 패키지/갱신 저장소가 번들을 갖고 있으면 `configured` 이다 — "실행할
    # artifact 가 정해져 있는가"가 이 필드의 의미이고, 그 판단은 store 한 곳에서 온다(task 15).
    bundle = effective_bundle(settings)
    layout = bundle.layout
    name = artifact.rsplit("/", 1)[-1] if artifact else (layout.binary.name if layout else None)
    return {
        "enabled": settings.enabled,
        "mode": settings.mode,
        "mode_supported": settings.mode_supported,
        "fallback": settings.fallback,
        "artifact_configured": bool(artifact) or layout is not None,
        # 경로 전체가 아니라 파일명 — 화면이 사용자 입력값을 다시 보여주는 자리는 설정 입력란이다.
        "artifact_name": name,
        "artifact_trusted": is_trusted_artifact_path(
            settings.artifact_path or (str(layout.binary) if layout else None), settings.extra_trusted_roots
        ),
        # 어느 출처의 바이트인가(explicit/store/package) + 갱신 버전 — 경로는 싣지 않는다.
        "bundle_source": layout.source if layout else None,
        "bundle_version": layout.version if layout else None,
        "problem": settings.problem,
    }


def _runtime_dict(runtime: SsakSearchRuntime | None, settings: SsakSearchSettings) -> dict[str, object]:
    if runtime is None:
        return {
            "present": False,
            "state": None,
            "circuit_open": False,
            "last_error": None,
            "child_count": 0,
            "start_attempts": 0,
            # 아직 만든 적이 없다 = 지금 설정이 그대로 적용된다.
            "restart_required": False,
        }
    status = runtime.status()
    child_pids = status.get("child_pids")
    child_count = len(cast(list[object], child_pids)) if isinstance(child_pids, list) else 0
    config = runtime.config
    settings_artifact = str(settings.artifact_path or "").strip()
    runtime_artifact = str(config.artifact_path or "").strip()
    # 설정이 바뀌었는데 살아 있는 child 가 있으면 **호스트 재시작 없이는** 새 bytes 가 안 쓰인다.
    # 그 사실을 화면이 알아야 "왜 켰는데 안 되지"를 묻지 않는다.
    restart_required = bool(child_count) and (
        settings_artifact != runtime_artifact or bool(config.enabled) != bool(settings.enabled)
    )
    return {
        "present": True,
        "state": status.get("state"),
        "circuit_open": bool(status.get("circuit_open")),
        "last_error": status.get("last_error"),
        "child_count": child_count,
        "start_attempts": status.get("start_attempts_in_episode", 0),
        "spawn_attempts": status.get("spawn_attempts", 0),
        "restart_required": restart_required,
    }


def _existing_runtime() -> SsakSearchRuntime | None:
    """이미 만들어진 호스트 싱글턴만 본다(없으면 None) — 상태 조회는 child 를 만들지 않는다."""
    from antigravity_k.tools import ssak_search_runtime as runtime_module

    return runtime_module._host_runtime  # noqa: SLF001 — 같은 패키지의 소유권 상태를 읽는다


def availability_snapshot(
    settings: SsakSearchSettings | None = None,
    *,
    runtime: SsakSearchRuntime | None = None,
    include_evidence: bool = True,
    evidence_limit: int = EVIDENCE_HISTORY_LIMIT,
) -> dict[str, object]:
    """화면이 그대로 그릴 수 있는 상태 스냅숏.

    `runtime` 을 주지 않으면 **이미 존재하는** 호스트 싱글턴만 본다(조회가 부작용을 갖지 않게).
    """
    resolved = settings if settings is not None else settings_snapshot()
    if runtime is None:
        runtime = _existing_runtime()
    availability = _availability_for(resolved, runtime)
    snapshot: dict[str, object] = {
        "ok": True,
        "availability": availability,
        "label": AVAILABILITY_LABELS[availability],
        "tone": AVAILABILITY_TONES[availability],
        "detail": AVAILABILITY_ACTIONS[availability],
        "recoverable": availability in _RECOVERABLE,
        "settings": _settings_dict(resolved),
        "runtime": _runtime_dict(runtime, resolved),
    }
    if include_evidence:
        snapshot["evidence"] = [item.as_dict() for item in latest_search_evidence(max(0, evidence_limit))]
    return snapshot


def retry_availability(
    settings: SsakSearchSettings | None = None,
    *,
    timeout: float = DEFAULT_RETRY_TIMEOUT,
    runtime: SsakSearchRuntime | None = None,
) -> dict[str, object]:
    """회로를 닫고 child 시작을 **한 번** 시도한 뒤 상태를 돌려준다.

    재시도는 새 child 를 만들 뿐이며, 이름/pgid 로 다른 프로세스를 죽이지 않는다(런타임 소유 규칙).
    timeout 안에 ready 가 되지 못하면 그 사실을 담은 스냅숏을 돌려준다 — 거짓 성공을 만들지 않는다.
    """
    resolved = settings if settings is not None else settings_snapshot()
    availability = _availability_for(resolved, runtime if runtime is not None else _existing_runtime())
    if availability in (DISABLED, MISCONFIGURED):
        snapshot = availability_snapshot(resolved, runtime=runtime)
        snapshot["retried"] = False
        snapshot["detail"] = (
            "검색이 꺼져 있습니다 — 먼저 켠 뒤 다시 시도하세요."
            if availability == DISABLED
            else "설정을 먼저 고쳐야 합니다."
        )
        return snapshot
    if runtime is None:
        from antigravity_k.tools.ssak_search_runtime import resolve_ssak_search_runtime

        runtime = resolve_ssak_search_runtime(bundled_runtime_config(resolved), replace_when_idle=True)
    runtime.reset_circuit()
    ready = False
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="ssak-retry") as pool:
            ready = bool(pool.submit(runtime.ensure_ready, timeout).result(timeout=timeout + 5.0))
    except (concurrent.futures.TimeoutError, RuntimeError, OSError) as exc:
        logger.warning("검색 재시도가 bounded timeout 안에 끝나지 않았습니다: %s", exc)
    snapshot = availability_snapshot(resolved, runtime=runtime)
    snapshot["retried"] = True
    snapshot["ready"] = ready
    if not ready and snapshot["availability"] in (STARTING, IDLE):
        snapshot["detail"] = "아직 시작 중입니다 — 조금 뒤에 다시 확인하세요."
    return snapshot


def probe_search(
    query: str,
    *,
    max_results: int = 5,
    settings: SsakSearchSettings | None = None,
    runtime: object | None = None,
    timeout: float = DEFAULT_PROBE_TIMEOUT,
) -> dict[str, object]:
    """연결 확인 — 번들 provider 로 **정확히 한 번** 검색한다(legacy 대체 없음).

    사용자가 "연결 확인" 을 눌렀을 때 도는 경로다. 여기서 실패를 legacy 로 대체하지 않는 이유:
    이 질문의 답은 "번들이 되느냐" 이지 "검색이 되느냐"가 아니다 — 대체하면 답을 잃는다.
    """
    resolved = settings if settings is not None else settings_snapshot()
    result: dict[str, object] = {"ok": False, "query": query}
    if not resolved.enabled:
        result["evidence"] = {
            "query": query,
            "ok": False,
            "route": "blocked (RUNTIME_DISABLED)",
            "error_code": "RUNTIME_DISABLED",
            "failure_class": "permanent",
            "message": "번들 검색이 꺼져 있습니다. 먼저 설정에서 켜세요.",
            "partial": False,
            "sources": [],
            "retrieved_at": None,
            "budget": None,
        }
        return result
    with concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="ssak-probe") as pool:
        future = pool.submit(
            search_with_bundled_provider,
            query,
            max_results=max_results,
            settings=resolved,
            runtime=runtime,
        )
        try:
            attempt = future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            result["evidence"] = {
                "query": query,
                "ok": False,
                "route": "bundled (timeout)",
                "error_code": "TIMEOUT",
                "failure_class": "transient",
                "message": f"연결 확인이 {timeout:.0f}초 안에 끝나지 않았습니다.",
                "partial": False,
                "sources": [],
                "retrieved_at": None,
                "budget": None,
            }
            return result
    result["ok"] = attempt.ok
    result["evidence"] = attempt.evidence.as_dict() if attempt.evidence is not None else None
    result["error_code"] = attempt.error_code
    result["failure_class"] = attempt.failure_class
    return result


def evidence_snapshot(limit: int = EVIDENCE_HISTORY_LIMIT) -> dict[str, object]:
    """최근 검색 시도들 — 화면이 출처·수집시각·부분 수집·상한 초과를 그리는 재료."""
    items = [item.as_dict() for item in latest_search_evidence(max(0, limit))]
    return {"ok": True, "count": len(items), "evidence": items}


__all__ = [
    "AVAILABILITY_ACTIONS",
    "AVAILABILITY_LABELS",
    "AVAILABILITY_TONES",
    "AVAILABLE",
    "DEFAULT_PROBE_TIMEOUT",
    "DEFAULT_RETRY_TIMEOUT",
    "DISABLED",
    "IDLE",
    "MISCONFIGURED",
    "STARTING",
    "UNAVAILABLE",
    "availability_snapshot",
    "evidence_snapshot",
    "probe_search",
    "retry_availability",
]
