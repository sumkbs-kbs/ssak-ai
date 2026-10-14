"""번들 ssak-search provider 로 기존 web_search 를 연결하는 routing 계층 (task 13).

이 모듈이 정하는 **세 가지 결정**과, 그 결정을 어기지 않게 지키는 규칙:

1. **켤 것인가** — `search.ssak.enabled`(기본 **false**). 꺼져 있으면 아무 일도 일어나지 않고
   기존 4-engine 경로가 그대로 돈다(기존 결과 계약 유지).
2. **어디로 보낼 것인가** — `mode=bundled_stdio` → task 12 의 런타임(호스트당 child 1개).
   성공하면 그 호출 **한 번**으로 끝난다 — 같은 질의를 legacy engine 으로 다시 훑지 않는다.
3. **실패하면 어떻게 할 것인가** — `fallback=legacy_on_transient` → **transient** 실패에만
   **정확히 1회** legacy 로 대체한다. 그 밖의 실패는 장애가 아니라 **결정**이므로 대체하지 않는다:
   POLICY_DENIED(사용자가 이 요청에서 껐다) · INVALID_ARGUMENT(우리 입력이 틀렸다) ·
   AUTH_REQUIRED(자격 증명 문제) · RUNTIME_DISABLED(설정으로 껐다) · artifact 거절(어느 bytes 를
   실행하는지 모른다) · 알 수 없는 예외. 대체하면 그 결정이 조용히 사라진다.

그리고 `artifact_path` 는 **신뢰된 루트 아래**의 파일만 받는다(심볼릭 링크를 해석한 뒤 판정).
경로 하나가 임의 실행 지점이 되는 것을 막는 자리다.

동기 `execute` 안에서 이 경로는 **이벤트 루프를 중첩 실행하지 않는다** — 런타임의 `call_tool` 은
자기 전용 루프에 큐로 넘기는 동기 호출이라, 이미 돌고 있는 루프 안에서도 `run_until_complete` 가
필요 없다(acceptance 의 "sync wrapper 는 nested run 으로 막지 않는다").
"""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, cast

from antigravity_k.engine.tool_policy import mcp_server_policy_denial

# 번들 배치는 store 한 곳이 소유한다(task 15). store 는 런타임만 import 하므로 순환이 없다.
from antigravity_k.tools.ssak_bundle_store import BundleResolution, resolve_bundle

if TYPE_CHECKING:  # pragma: no cover — 순환 import 방지(설정/런타임은 지연 import)
    from antigravity_k.tools.mcp_tool_result import MCPToolOutcome
    from antigravity_k.tools.ssak_search_runtime import SearchRuntimeConfig

logger = logging.getLogger(__name__)

BUNDLED_SERVER_NAME = "ssak_search"
BUNDLED_TOOL_NAME = "ssak_search"
SUPPORTED_MODES: frozenset[str] = frozenset({"bundled_stdio"})
FALLBACK_POLICIES: frozenset[str] = frozenset({"legacy_on_transient", "none"})
DEFAULT_MANIFEST_NAME = "ssak-search-manifest.json"
MANIFEST_RELATIVE_DIR = "release"
# `TRUSTED_ROOTS_ENV` 는 아래에서 `ssak_search_trust` 로부터 재-export 된다(정의는 한 곳).

# 일시적 장애: 대체(fallback)가 허용된다. `CIRCUIT_OPEN` 은 **반복된 transient 실패의 결과**이므로
# 여기 포함한다(회로가 열려 있다는 사실 자체가 "지금은 번들이 못 한다"는 뜻이다).
TRANSIENT_ERROR_CODES: frozenset[str] = frozenset(
    {
        "TIMEOUT",
        "TRANSPORT_LOST",
        "CHILD_EXITED",
        "RUNTIME_STOPPED",
        "RUNTIME_NOT_READY",
        "CIRCUIT_OPEN",
        "UPSTREAM_UNAVAILABLE",
    }
)

# 결정적인 실패: 대체 금지. 대체하면 사용자/설정의 **결정**이 조용히 뒤집힌다.
#: 네트워크가 없어서 실패한 경우(task 15). **영구**로 분류한다: 재시도로 낫지 않고, legacy 로 대체해도
#: 마찬가지로 네트워크가 필요하다 — 대체하면 사용자에게 "두 번 실패한 결과"만 보여준다.
NETWORK_UNAVAILABLE = "NETWORK_UNAVAILABLE"

#: 오프라인 판정의 명시적 스위치(검증 스크립트 `--offline-start` 와 시험이 쓴다).
#: `1`/`true` = 네트워크 없음으로 취급, `0`/`false` = 있다고 취급, 비어 있으면 실제 probe.
OFFLINE_ENV = "AGK_SEARCH_OFFLINE"

#: 실제 probe 에 쓰는 대상·타임아웃. IP 로 두는 이유: DNS 실패와 "네트워크 없음"을 섞지 않기 위해서다.
_NETWORK_PROBE_TARGET = ("1.1.1.1", 443)
_NETWORK_PROBE_TIMEOUT_SECONDS = 0.6
_NETWORK_PROBE_CACHE_SECONDS = 5.0

PERMANENT_ERROR_CODES: frozenset[str] = frozenset(
    {
        NETWORK_UNAVAILABLE,
        "POLICY_DENIED",
        "INVALID_ARGUMENT",
        "INVALID_TOOL_ARGS",
        "AUTH_REQUIRED",
        "UNKNOWN_TOOL",
        "RUNTIME_DISABLED",
        "NON_IDEMPOTENT_NOT_RETRIED",
        "ARTIFACT_REJECTED",
        "UNTRUSTED_ARTIFACT_PATH",
        "CANCELLED",
    }
)


@dataclass(frozen=True)
class SsakSearchSettings:
    """`search.ssak.*` 의 스냅숏. `problem` 이 있으면 설정 자체가 잘못된 것이다(라우팅하지 않는다)."""

    enabled: bool = False
    mode: str = "bundled_stdio"
    fallback: str = "legacy_on_transient"
    artifact_path: str | None = None
    manifest_path: str | None = None
    problem: str | None = None
    extra_trusted_roots: tuple[str, ...] = ()

    @property
    def mode_supported(self) -> bool:
        return self.mode in SUPPORTED_MODES

    @property
    def fallback_on_transient(self) -> bool:
        return self.fallback == "legacy_on_transient"

    def route_reason(self) -> str:
        """왜 legacy 로 가는가 — 로그/시험에서 읽는 한 줄."""
        if not self.enabled:
            return "search.ssak.enabled=false (opt-in 하지 않음)"
        if self.problem:
            return f"invalid search.ssak configuration: {self.problem}"
        if not self.mode_supported:
            return f"unsupported search.ssak.mode={self.mode}"
        return "bundled_stdio"


@dataclass(frozen=True)
class ProviderAttempt:
    """번들 provider 호출 결과. `transient` 는 "대체가 허용되는가"의 답이다."""

    ok: bool
    transient: bool
    message: str
    results: list[tuple[str, str, str]] = field(default_factory=list)
    error_code: str | None = None
    engine: str = "SsakBundle"
    evidence: SearchEvidence | None = None

    @property
    def failure_class(self) -> str:
        if self.ok:
            return "ok"
        return "transient" if self.transient else "permanent"


# ── 증거(evidence) — UI 가 사용자에게 보여줄 수 있는 형태 ─────────────────────
#
# 번들 응답은 텍스트 안에 JSON 봉투로 온다(W `AgentSearchResult`):
# ``{query, took_ms, hits[{title,url,snippet,score,source,authority_boost,security_warning}],
#   aborted_backends[], signal_confidence, decomposed_subqueries?, cached?, cache_age_ms?,
#   phishing_filtered?}`` 그리고 상한을 넘겨 항목이 잘린 경우에만 ``budget`` 이 붙는다.
# 여기서 그 필드들을 **버리지 않고** 보존한다 — UI 가 출처·수집시각·부분 수집·상한 초과를
# 사용자에게 그대로 보여주려면 이 값들이 필요하고, 문자열을 다시 파싱하게 두면 두 계층이 갈라진다.

#: 보관하는 최근 시도 수(링 버퍼). 메모리 사용을 유계로 두기 위한 값이며,
#: 자격 증명·질의 원문 외에는 아무것도 담지 않는다(결과 본문만).
EVIDENCE_HISTORY_LIMIT = 5


@dataclass(frozen=True)
class SearchSource:
    """출처 한 건 — 원문 링크와 (가능하면) 수집시각을 함께 나른다."""

    title: str
    url: str
    snippet: str = ""
    score: float | None = None
    provider: str | None = None
    authority_boost: bool = False
    security_warning: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "score": self.score,
            "provider": self.provider,
            "authority_boost": self.authority_boost,
            "security_warning": self.security_warning,
        }


@dataclass(frozen=True)
class SearchBudget:
    """응답 상한 때문에 항목을 잘라낸 사실(잘린 게 없으면 UI 는 아무것도 표시하지 않는다)."""

    bytes: int | None = None
    tokens: int | None = None
    exceeded: str | None = None
    trimmed_items: int = 0

    @property
    def truncated(self) -> bool:
        return self.trimmed_items > 0 or self.exceeded is not None

    def as_dict(self) -> dict[str, object]:
        return {
            "bytes": self.bytes,
            "tokens": self.tokens,
            "exceeded": self.exceeded,
            "trimmed_items": self.trimmed_items,
            "truncated": self.truncated,
        }


@dataclass(frozen=True)
class SearchEvidence:
    """검색 시도 한 건의 관측 가능한 사실 전부(성공·실패·부분 수집을 한 모양으로)."""

    query: str
    ok: bool
    route: str
    error_code: str | None = None
    failure_class: str = "ok"
    message: str = ""
    engine: str = "SsakBundle"
    sources: tuple[SearchSource, ...] = ()
    #: 결과가 실제로 수집된 시각(ISO-8601 UTC). 캐시 응답이면 캐시가 담긴 시점이다.
    retrieved_at: str | None = None
    #: 검색에 걸린 시간(ms). 캐시 응답은 그 실행의 시간이 아니다.
    took_ms: int | None = None
    from_cache: bool = False
    cache_age_ms: int | None = None
    #: 응답하지 않은 백엔드 — "일부 소스만 수집됨"의 근거다(추측이 아니라 보고된 값).
    aborted_backends: tuple[str, ...] = ()
    signal_confidence: str | None = None
    decomposed_subqueries: tuple[str, ...] = ()
    phishing_filtered: int | None = None
    budget: SearchBudget | None = None
    #: 어떤 artifact 가 이 결과를 만들었는지(파일명만 — 경로는 노출하지 않는다).
    artifact_name: str | None = None

    @property
    def partial(self) -> bool:
        """부분 수집인가 — 백엔드가 빠졌거나 신뢰도가 HIGH 가 아닐 때."""
        if self.aborted_backends:
            return True
        return self.signal_confidence in {"LOW", "MEDIUM"}

    def as_dict(self) -> dict[str, object]:
        return {
            "query": self.query,
            "ok": self.ok,
            "route": self.route,
            "error_code": self.error_code,
            "failure_class": self.failure_class,
            "message": self.message,
            "engine": self.engine,
            "sources": [source.as_dict() for source in self.sources],
            "retrieved_at": self.retrieved_at,
            "took_ms": self.took_ms,
            "from_cache": self.from_cache,
            "cache_age_ms": self.cache_age_ms,
            "aborted_backends": list(self.aborted_backends),
            "signal_confidence": self.signal_confidence,
            "decomposed_subqueries": list(self.decomposed_subqueries),
            "phishing_filtered": self.phishing_filtered,
            "partial": self.partial,
            "budget": self.budget.as_dict() if self.budget is not None else None,
            "artifact_name": self.artifact_name,
        }


_network_probe_cache: tuple[float, bool] | None = None


def network_available(env: Mapping[str, str] | None = None, *, force_probe: bool = False) -> bool:
    """네트워크가 있는가 — 짧은 TCP probe(결과는 몇 초간 캐시).

    왜 필요한가(task 15): 오프라인에서 검색은 **실패한다**. 그때 "일시 장애"라고 말하면 사용자는
    번들이 고장났다고 읽고 영원히 재시도한다. 사실은 "네트워크가 없다"이고, 그건 사용자가 고칠 수
    있는 문제다. 그래서 실패가 transport/timeout 류일 때만 이 함수를 보고 코드를 바꿔 단다.

    probe 대상이 IP 인 이유: DNS 실패를 "네트워크 없음"으로 단정하지 않기 위해서다.
    """
    global _network_probe_cache
    source = env if env is not None else os.environ
    raw = str(source.get(OFFLINE_ENV, "") or "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return False
    if raw in {"0", "false", "no", "off"}:
        return True

    now = time.monotonic()
    cached = _network_probe_cache
    if cached is not None and not force_probe and now - cached[0] < _NETWORK_PROBE_CACHE_SECONDS:
        return cached[1]
    try:
        with socket.create_connection(_NETWORK_PROBE_TARGET, timeout=_NETWORK_PROBE_TIMEOUT_SECONDS):
            reachable = True
    except OSError:
        reachable = False
    _network_probe_cache = (now, reachable)
    return reachable


def classify_error_code(code: str | None) -> str:
    """오류 코드를 ok/transient/permanent 로 분류한다(알 수 없는 코드는 **permanent**).

    모르는 실패를 transient 로 넘기면 legacy 가 조용히 2차 실행된다 — 그게 이 계층이 막으려는
    실패 모드다. 모르면 대체하지 않고 드러낸다.
    """
    if not code:
        return "permanent"
    if code in TRANSIENT_ERROR_CODES:
        return "transient"
    if code in PERMANENT_ERROR_CODES:
        return "permanent"
    return "permanent"


# ── 설정 ─────────────────────────────────────────────────────────────────────


def settings_snapshot(app_config: object | None = None) -> SsakSearchSettings:
    """현재 설정에서 `search.ssak.*` 를 읽는다.

    설정 로드 실패는 **꺼진 것으로 처리**한다(검색 도구가 설정 오류로 죽으면 안 되고, 꺼진 상태는
    기존 동작 그대로다). 다만 이유는 `problem` 에 남겨 로그/시험에서 보이게 한다.
    """
    try:
        section = _read_section(app_config)
    except Exception as exc:  # noqa: BLE001 — 설정 오류로 도구를 죽이지 않는다
        logger.warning("search.ssak 설정을 읽지 못했습니다: %s", exc)
        return SsakSearchSettings(problem=f"config load failed: {exc}")
    if section is None:
        return SsakSearchSettings()
    return SsakSearchSettings(
        enabled=bool(_field(section, "enabled", False)),
        mode=str(_field(section, "mode", "bundled_stdio")),
        fallback=str(_field(section, "fallback", "legacy_on_transient")),
        artifact_path=_optional_text(_field(section, "artifact_path", None)),
        manifest_path=_optional_text(_field(section, "manifest_path", None)),
        problem=_validate(section),
        extra_trusted_roots=extra_trusted_roots(),
    )


def _read_section(app_config: object | None) -> Mapping[str, object] | None:
    if app_config is None:
        from antigravity_k.config import AppConfig

        app_config = AppConfig()
    search = getattr(app_config, "search", None)
    if search is None:
        return None
    ssak = getattr(search, "ssak", None)
    if ssak is None:
        return None
    if isinstance(ssak, Mapping):
        return cast(Mapping[str, object], ssak)
    dump = getattr(ssak, "model_dump", None)
    if callable(dump):
        return cast(Mapping[str, object], dump())
    return None


def _field(section: Mapping[str, object], key: str, default: object) -> object:
    value = section.get(key, default)
    return default if value is None else value


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _validate(section: Mapping[str, object]) -> str | None:
    mode = str(_field(section, "mode", "bundled_stdio"))
    if mode not in SUPPORTED_MODES:
        return f"mode must be one of {sorted(SUPPORTED_MODES)}, got {mode!r}"
    fallback = str(_field(section, "fallback", "legacy_on_transient"))
    if fallback not in FALLBACK_POLICIES:
        return f"fallback must be one of {sorted(FALLBACK_POLICIES)}, got {fallback!r}"
    enabled = bool(_field(section, "enabled", False))
    if enabled and not _optional_text(_field(section, "artifact_path", None)):
        # task 15: 명시 경로가 없어도 **설치 패키지 리소스가 있으면** 유효하다(그게 정상 설치의 모습니다).
        # 어느 쪽도 없을 때만 "어느 bytes 를 실행할지 모른다"고 거절한다 — fail-closed 는 그대로다.
        resolution = effective_bundle(section=section)
        if not resolution.found:
            return (
                "enabled=true requires either artifact_path or a bundled artifact in the installation "
                f"({resolution.reason})"
            )
    return None


def effective_bundle(
    settings: SsakSearchSettings | None = None,
    *,
    section: Mapping[str, object] | None = None,
) -> BundleResolution:
    """실제로 실행될 번들 — 명시 설정 → 갱신 저장소의 현재 버전 → 설치 패키지 리소스.

    화면·상태·검증 스크립트가 모두 이 함수를 쓴다: "어느 bytes 를 실행하는가"를 두 곳에서 따로
    판단하면 한쪽만 알아채는 갈라짐이 생긴다.
    """
    if settings is None:
        if section is not None:
            settings = SsakSearchSettings(
                artifact_path=_optional_text(_field(section, "artifact_path", None)),
                manifest_path=_optional_text(_field(section, "manifest_path", None)),
            )
        else:
            settings = settings_snapshot()
    return resolve_bundle(settings.artifact_path, settings.manifest_path)


# ── 신뢰 경로 ────────────────────────────────────────────────────────────────


def bundle_status() -> dict[str, object]:
    """설치 패키지·갱신 저장소의 번들 상황(상태 화면·검증 스크립트용). 지연 import 로 순환을 피한다."""
    from antigravity_k.tools.ssak_bundle_store import bundle_status as _bundle_status

    return _bundle_status()


# 신뢰 규칙은 별도 모듈 한 곳에 있다 — provider 와 bundle store 가 같은 문장을 쓰게 하려는 것이다
# (task 15: 두 곳에 복사했더니 순환 import 가 생기고 규칙이 갈라질 위험이 드러났다).
from antigravity_k.tools.ssak_search_trust import (  # noqa: E402 — 아래 정의들과 함께 쓰인다
    TRUSTED_ROOTS_ENV,
    extra_trusted_roots,
    is_trusted_artifact_path,
    trusted_roots,
)


def resolve_manifest_path(artifact: str | os.PathLike[str] | None, explicit: str | None) -> Path | None:
    """매니페스트 경로를 찾는다: 명시 > artifact 옆 `release/` 규약 > env.

    task 11 의 번들 배치가 `bin/ssak-mcp` + `release/ssak-search-manifest.json` 이므로 그 규약을
    따른다. 못 찾으면 `None` 을 돌려주고, 런타임이 **fail-closed** 로 거절한다(여기서 추측하지 않는다).
    """

    def _from_env() -> Path | None:
        # 빈 문자열은 "설정하지 않음"이다 — `Path("")` 은 `.` 이라 매니페스트 검사가 디렉터리를 읽는다.
        raw = str(os.environ.get("AGK_SEARCH_MANIFEST", "") or "").strip()
        return Path(raw) if raw else None

    if explicit:
        return Path(explicit).expanduser()
    if not artifact:
        return _from_env()
    parent = Path(artifact).expanduser().resolve().parent
    for candidate in (
        parent / DEFAULT_MANIFEST_NAME,  # artifact 옆
        parent / MANIFEST_RELATIVE_DIR / DEFAULT_MANIFEST_NAME,  # <root>/bin/x + <root>/bin/release/x
        parent.parent / MANIFEST_RELATIVE_DIR / DEFAULT_MANIFEST_NAME,  # task 11 배치: <root>/bin/x + <root>/release/x
    ):
        if candidate.is_file():
            return candidate
    return _from_env()


# ── 호출 ─────────────────────────────────────────────────────────────────────


def bundled_runtime_config(settings: SsakSearchSettings) -> SearchRuntimeConfig:
    from antigravity_k.tools.ssak_search_runtime import SearchRuntimeConfig

    # 명시 설정이 없으면 설치 패키지/갱신 저장소의 번들을 쓴다(task 15). 그래야 "정상 설치"에서
    # 사용자가 경로를 적어 넣지 않아도 켜진 검색이 실제로 동작한다.
    bundle = effective_bundle(settings)
    artifact = settings.artifact_path or (str(bundle.layout.binary) if bundle.layout else None)
    manifest = resolve_manifest_path(artifact, settings.manifest_path)
    if manifest is None and bundle.layout is not None:
        manifest = bundle.layout.manifest
    return SearchRuntimeConfig(
        artifact_path=artifact,
        manifest_path=str(manifest) if manifest is not None else None,
        enabled=True,
        server_name=BUNDLED_SERVER_NAME,
    )


def _hits_from_outcome(outcome: MCPToolOutcome) -> list[tuple[str, str, str]]:
    """MCP 결과에서 (title, url, snippet) 을 꺼낸다 — `_sources_from_payload` 와 같은 파서를 쓴다.

    같은 봉투를 두 번 다르게 읽으면 두 소비자가 갈라진다(한쪽만 `description` 폴백을 알아챈다).
    """
    payload = _payload_from_outcome(outcome)
    if payload is None:
        return []
    return [(source.title, source.url, source.snippet) for source in _sources_from_payload(payload)]


def _payload_from_outcome(outcome: MCPToolOutcome) -> Mapping[str, object] | None:
    """MCP 결과에서 JSON 봉투를 꺼낸다 — structuredContent 우선, 없으면 본문 JSON."""
    structured = getattr(outcome, "structured_content", None)
    if isinstance(structured, Mapping):
        return cast(Mapping[str, object], structured)
    text = str(outcome)
    start = text.find("{")
    if start < 0:
        return None
    try:
        parsed: object = json.loads(text[start:])
    except json.JSONDecodeError:
        return None
    return cast(Mapping[str, object], parsed) if isinstance(parsed, Mapping) else None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _float_or_none(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(text for text in (_text(item) for item in cast(list[object], value)) if text)


def _is_true(value: object) -> bool:
    """JSON 불리언만 참으로 본다 — `"false"` 문자열을 참으로 읽지 않는다."""
    return value is True


def _sources_from_payload(payload: Mapping[str, object]) -> tuple[SearchSource, ...]:
    raw = payload.get("hits", payload.get("results", []))
    if not isinstance(raw, list):
        return ()
    sources: list[SearchSource] = []
    for item in cast(list[object], raw):
        if not isinstance(item, Mapping):
            continue
        entry = cast(Mapping[str, object], item)
        title = _text(entry.get("title"))
        url = _text(entry.get("url"))
        if not title and not url:
            continue
        warning: str | None = None
        raw_warning = entry.get("security_warning")
        if isinstance(raw_warning, Mapping):
            warning_entry = cast(Mapping[str, object], raw_warning)
            warning = _text(warning_entry.get("detail")) or _text(warning_entry.get("code")) or None
        elif raw_warning is not None:
            warning = _text(raw_warning) or None
        sources.append(
            SearchSource(
                title=title or url,
                url=url,
                snippet=_text(entry.get("snippet", entry.get("description"))),
                score=_float_or_none(entry.get("score")),
                provider=_text(entry.get("source")) or None,
                authority_boost=_is_true(entry.get("authority_boost")),
                security_warning=warning,
            )
        )
    return tuple(sources)


def _budget_from_payload(payload: Mapping[str, object]) -> SearchBudget | None:
    raw = payload.get("budget")
    if not isinstance(raw, Mapping):
        return None
    entry = cast(Mapping[str, object], raw)
    return SearchBudget(
        bytes=_int_or_none(entry.get("bytes")),
        tokens=_int_or_none(entry.get("tokens")),
        exceeded=_text(entry.get("exceeded")) or None,
        trimmed_items=_int_or_none(entry.get("trimmed_items")) or 0,
    )


def _retrieved_at(now: datetime, from_cache: bool, cache_age_ms: int | None) -> str:
    """결과가 실제로 수집된 시각.

    캐시 응답은 **지금** 수집한 게 아니다 — 그 사실을 숨기면 UI 가 오래된 결과를 "방금 수집"으로
    표시하게 된다. 캐시 나이가 있으면 그만큼 되돌린다.
    """
    if from_cache and cache_age_ms and cache_age_ms > 0:
        now = now - timedelta(milliseconds=cache_age_ms)
    return now.isoformat().replace("+00:00", "Z")


def _artifact_name(path: str | None) -> str | None:
    if not path:
        return None
    try:
        return Path(path).name or None
    except (OSError, ValueError):  # pragma: no cover — 비정상 경로는 이름을 만들지 않는다
        return None


def _evidence_from_outcome(
    outcome: MCPToolOutcome,
    *,
    query: str,
    settings: SsakSearchSettings,
    route: str,
    fallback_used: bool = False,
) -> SearchEvidence:
    """성공·실패 결과를 **같은 모양의** 증거로 만든다(UI 가 분기 없이 그릴 수 있게)."""
    now = datetime.now(timezone.utc)
    artifact = _artifact_name(settings.artifact_path)
    is_error = bool(getattr(outcome, "is_error", False))
    if is_error:
        code = getattr(outcome, "error_code", None)
        code_text = str(code) if code else None
        failure = classify_error_code(code_text)
        return SearchEvidence(
            query=query,
            ok=False,
            route=route,
            error_code=code_text or "UNKNOWN_ERROR",
            failure_class=failure,
            message=str(outcome),
            retrieved_at=now.isoformat().replace("+00:00", "Z"),
            artifact_name=artifact,
        )
    payload = _payload_from_outcome(outcome)
    if payload is None:
        return SearchEvidence(
            query=query,
            ok=True,
            route=route,
            message=str(outcome),
            engine="SsakBundle(0 hits)",
            retrieved_at=now.isoformat().replace("+00:00", "Z"),
            artifact_name=artifact,
        )
    from_cache = _is_true(payload.get("cached"))
    cache_age_ms = _int_or_none(payload.get("cache_age_ms"))
    sources = _sources_from_payload(payload)
    return SearchEvidence(
        query=query,
        ok=True,
        route=route,
        message=str(outcome),
        engine="SsakBundle(0 hits)" if not sources else "SsakBundle",
        sources=sources,
        retrieved_at=_retrieved_at(now, from_cache, cache_age_ms),
        took_ms=_int_or_none(payload.get("took_ms")),
        from_cache=from_cache,
        cache_age_ms=cache_age_ms,
        aborted_backends=_string_tuple(payload.get("aborted_backends")),
        signal_confidence=_text(payload.get("signal_confidence")) or None,
        decomposed_subqueries=_string_tuple(payload.get("decomposed_subqueries")),
        phishing_filtered=_int_or_none(payload.get("phishing_filtered")),
        budget=_budget_from_payload(payload),
        artifact_name=artifact,
    )


def _refused_evidence(
    query: str,
    *,
    code: str,
    message: str,
    settings: SsakSearchSettings,
) -> SearchEvidence:
    """라우팅 **이전에** 거절한 경우(설정 오류·신뢰 경로 밖·정책 거절)의 증거."""
    return SearchEvidence(
        query=query,
        ok=False,
        route=f"blocked ({code})",
        error_code=code,
        failure_class=classify_error_code(code),
        message=message,
        retrieved_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        artifact_name=_artifact_name(settings.artifact_path),
    )


# ── 증거 링 버퍼(호스트 전역) ────────────────────────────────────────────────

_EVIDENCE_LOCK = threading.Lock()
_EVIDENCE_RING: deque[SearchEvidence] = deque(maxlen=EVIDENCE_HISTORY_LIMIT)


def record_search_evidence(evidence: SearchEvidence) -> SearchEvidence:
    """최근 시도에 기록한다(최신이 뒤). 기록 실패가 검색을 깨면 안 되므로 예외를 내지 않는다."""
    try:
        with _EVIDENCE_LOCK:
            _EVIDENCE_RING.append(evidence)
    except Exception:  # noqa: BLE001 — 증거는 부가 정보지 검색의 결과가 아니다
        logger.debug("검색 증거 기록 실패", exc_info=True)
    return evidence


def latest_search_evidence(limit: int = EVIDENCE_HISTORY_LIMIT) -> list[SearchEvidence]:
    """최근 시도들을 **최신이 앞**으로 돌려준다."""
    with _EVIDENCE_LOCK:
        items = list(_EVIDENCE_RING)
    items.reverse()
    return items[: max(0, limit)]


def clear_search_evidence() -> None:
    """링을 비운다(시험 전용 — 운영 경로에서 부르지 않는다)."""
    with _EVIDENCE_LOCK:
        _EVIDENCE_RING.clear()


def search_with_bundled_provider(
    query: str,
    *,
    max_results: int = 8,
    settings: SsakSearchSettings,
    runtime: object | None = None,
) -> ProviderAttempt:
    """번들 child 에 **한 번** 질의한다. 예외는 실패 결과로 돌려준다(도구가 죽지 않는다).

    `runtime` 은 시험/대체용 주입 지점이다. 주지 않으면 호스트 싱글턴(task 12)을 쓴다 —
    "한 host instance 가 한 child 를 관리한다"를 여기서도 깨지 않는다.
    """
    if settings.problem:
        evidence = _refused_evidence(query, code="INVALID_ARGUMENT", message=settings.problem, settings=settings)
        return ProviderAttempt(
            False, False, settings.problem, error_code="INVALID_ARGUMENT", evidence=record_search_evidence(evidence)
        )
    # 신뢰 판정은 **실제로 실행할 바이트**를 본다. 명시 경로가 없으면 설치 패키지/갱신 저장소의
    # 번들이 그 대상이다 — 예전에는 `settings.artifact_path`(None)만 보아서, 정상 설치(경로를 손으로
    # 적지 않은 상태)의 모든 검색이 UNTRUSTED_ARTIFACT_PATH 로 거절됐다. 오프라인 실측이 이 결함을
    # 드러냈다(E/task-15/artifacts/offline-api.txt).
    resolved = effective_bundle(settings)
    effective_artifact = settings.artifact_path or (str(resolved.layout.binary) if resolved.layout else None)
    if not is_trusted_artifact_path(effective_artifact, settings.extra_trusted_roots):
        message = (
            f"artifact is outside the trusted roots (set {TRUSTED_ROOTS_ENV} to add one): "
            f"{effective_artifact or '<no bundle found>'}"
        )
        evidence = _refused_evidence(query, code="UNTRUSTED_ARTIFACT_PATH", message=message, settings=settings)
        return ProviderAttempt(
            False, False, message, error_code="UNTRUSTED_ARTIFACT_PATH", evidence=record_search_evidence(evidence)
        )
    denial = mcp_server_policy_denial(BUNDLED_TOOL_NAME, BUNDLED_SERVER_NAME)
    if denial is not None:
        # 사용자가 이 요청에서 검색을 껐다 — legacy 로 대체하면 그 결정을 뒤집게 된다.
        evidence = _refused_evidence(query, code="POLICY_DENIED", message=denial, settings=settings)
        return ProviderAttempt(
            False, False, denial, error_code="POLICY_DENIED", evidence=record_search_evidence(evidence)
        )
    try:
        if runtime is None:
            from antigravity_k.tools.ssak_search_runtime import resolve_ssak_search_runtime

            # 설정이 바뀌었고 child 가 없으면 교체한다 — 아니면 설정 화면이 바꿔도 옛 경로를 계속 쓴다.
            runtime = resolve_ssak_search_runtime(bundled_runtime_config(settings), replace_when_idle=True)
        call_tool = getattr(runtime, "call_tool")
        outcome = cast("MCPToolOutcome", call_tool(BUNDLED_TOOL_NAME, {"query": query, "max_results": max_results}))
    except Exception as exc:  # noqa: BLE001 — 알 수 없는 예외는 대체하지 않는다(모르면 드러낸다)
        logger.warning("번들 검색 provider 호출이 예외로 끝났습니다: %s", exc, exc_info=True)
        evidence = _refused_evidence(
            query,
            code="UNKNOWN_ERROR",
            message=f"bundled provider raised: {exc}",
            settings=settings,
        )
        return ProviderAttempt(
            False, False, evidence.message, error_code="UNKNOWN_ERROR", evidence=record_search_evidence(evidence)
        )
    is_error = bool(getattr(outcome, "is_error", False))
    if is_error:
        code = getattr(outcome, "error_code", None)
        code_text = str(code) if code else None
        offline = False
        if classify_error_code(code_text) == "transient" and not network_available():
            # child 를 먼저 부른다(오프라인에서도 캐시 응답은 정상 결과이므로 먼저 막지 않는다). 실패했고
            # 네트워크도 없으면 그 사실을 **사실대로** 말한다 — "일시 장애"는 거짓 안내다.
            code_text = NETWORK_UNAVAILABLE
            offline = True
        evidence = _evidence_from_outcome(outcome, query=query, settings=settings, route="bundled (error)")
        if offline:
            evidence = replace(
                evidence,
                message=(
                    f"{evidence.message} — 네트워크에 연결하지 못했습니다(오프라인): 번들·legacy 어느 쪽도 "
                    "검색에는 네트워크가 필요합니다. 연결을 확인한 뒤 다시 시도하세요."
                ),
                error_code=NETWORK_UNAVAILABLE,
                failure_class="permanent",
            )
        return ProviderAttempt(
            False,
            classify_error_code(code_text) == "transient",
            # 오프라인이면 **사용자에게 설명하는 문장**을 쓴다 — child 의 raw 문자열(`ENOTFOUND`)만
            # 보여주면 사용자는 그것이 "네트워크가 없다"는 뜻임을 알 수 없다.
            evidence.message if offline else str(outcome),
            error_code=code_text or "UNKNOWN_ERROR",
            evidence=record_search_evidence(evidence),
        )
    evidence = _evidence_from_outcome(outcome, query=query, settings=settings, route="bundled")
    record_search_evidence(evidence)
    hits = [(source.title, source.url, source.snippet) for source in evidence.sources]
    if not hits:
        # 응답은 성공인데 쓸 수 있는 결과가 없다 — 그건 검색 결과 0건이지 장애가 아니다.
        return ProviderAttempt(True, False, str(outcome), results=[], engine="SsakBundle(0 hits)", evidence=evidence)
    return ProviderAttempt(True, False, str(outcome), results=hits, evidence=evidence)


__all__ = [
    "BUNDLED_SERVER_NAME",
    "BUNDLED_TOOL_NAME",
    "DEFAULT_MANIFEST_NAME",
    "EVIDENCE_HISTORY_LIMIT",
    "NETWORK_UNAVAILABLE",
    "OFFLINE_ENV",
    "PERMANENT_ERROR_CODES",
    "SUPPORTED_MODES",
    "TRANSIENT_ERROR_CODES",
    "TRUSTED_ROOTS_ENV",
    "ProviderAttempt",
    "SearchBudget",
    "SearchEvidence",
    "SearchSource",
    "SsakSearchSettings",
    "bundle_status",
    "bundled_runtime_config",
    "effective_bundle",
    "network_available",
    "classify_error_code",
    "clear_search_evidence",
    "extra_trusted_roots",
    "is_trusted_artifact_path",
    "latest_search_evidence",
    "record_search_evidence",
    "resolve_manifest_path",
    "search_with_bundled_provider",
    "settings_snapshot",
    "trusted_roots",
]
