"""검색 통합 API — 상태·설정·증거·재시도·연결 확인 (task 14).

화면(설정 → 검색 통합)이 쓰는 다섯 개의 문이다.

- `GET  /api/search/status`   — 지금 쓸 수 있는가(사용자 의미로 옮긴 라벨/톤/다음 행동) + 설정·런타임 스냅숏
- `GET  /api/search/evidence` — 최근 검색 시도의 출처·수집시각·부분 수집·상한 초과
- `POST /api/search/settings` — 켜기/끄기·경로·모드·대체 정책 저장(검증 후 `.env` + 즉시 반영)
- `POST /api/search/retry`    — 회로를 닫고 시작을 한 번 시도(명시적 회복 행동)
- `POST /api/search/probe`    — 번들 provider 로 **정확히 한 번** 실제 검색(연결 확인)

설계 원칙:

1. **조회는 부작용이 없다.** `status`/`evidence` 는 child 를 만들지 않는다 — 아직 시작하지 않았으면
   `idle`("시작 전")이라고 정직하게 말한다. 상태를 보려고 프로세스를 띄우면 조회가 배포가 된다.
2. **변경은 권한 게이트를 지난다.** 설정 저장·재시도·연결 확인은 프로세스를 만들고 외부 질의를
   내보내므로 `critical` 위험도로 `PermissionGate` 를 지난다(다른 시스템 API 와 같은 규칙).
3. **비밀을 돌려주지 않는다.** artifact 는 파일명만, 토큰은 존재 여부조차 이 응답에 없다.
4. **사용자 결정을 뒤집지 않는다.** 연결 확인(probe)은 legacy 로 대체하지 않는다 — 질문이
   "번들이 되느냐"이기 때문이다(라우팅 계층의 fallback 과 다른 자리이며, 그 이유는 모듈 docstring 에 있다).
5. **검증이 먼저, 쓰기가 나중.** 켜져 있는데 경로가 없으면 `.env` 를 건드리지 않고 400 으로 거절한다.
   잘못된 설정을 저장해 놓고 "나중에 상태가 이상하다"고 말하는 화면은 사용자를 함정에 빠뜨린다.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

# 게이트 규칙을 두 곳에서 따로 만들면 갈라진다(위험도·모드 판정은 시스템 API 한 곳의 규칙이다).
from antigravity_k.api.routes.system_api import _require_allowed  # pyright: ignore[reportPrivateUsage]
from antigravity_k.engine.secret_settings import (
    EnvSettingError,
    apply_env_settings,
    resolve_env_file_path,
)
from antigravity_k.tools.ssak_search_provider import (
    EVIDENCE_HISTORY_LIMIT,
    SsakSearchSettings,
    extra_trusted_roots,
    settings_snapshot,
)

# 검증 규칙은 `search.ssak` 계약을 소유한 한 곳에서 가져온다(여기서 다시 쓰면 두 규칙이 갈라진다).
from antigravity_k.tools.ssak_search_provider import (
    _validate as _validate_search_section,  # pyright: ignore[reportPrivateUsage]
)
from antigravity_k.tools.ssak_search_status import (
    availability_snapshot,
    evidence_snapshot,
    probe_search,
    retry_availability,
)

logger = logging.getLogger("antigravity_k.api.search_api")
router = APIRouter()

#: 연결 확인의 질의 길이 상한(사용자가 실수로 거대한 본문을 보내도 child 를 망치지 않는다).
MAX_QUERY_LENGTH = 400
MAX_PROBE_RESULTS = 10

#: 설정 화면이 쓰는 필드 ↔ 환경변수. `AGK_SEARCH_SSAK_*` 는 이미 yaml 보다 우선하므로(task 13)
#: `.env` 에 쓰고 프로세스 env 를 갱신하면 **재시작 없이** 다음 호출부터 반영된다.
SEARCH_SETTING_ENV: dict[str, str] = {
    "enabled": "AGK_SEARCH_SSAK_ENABLED",
    "mode": "AGK_SEARCH_SSAK_MODE",
    "fallback": "AGK_SEARCH_SSAK_FALLBACK",
    "artifact_path": "AGK_SEARCH_SSAK_ARTIFACT_PATH",
}


def _settings_project_root() -> str:
    """`.env` 를 찾을 프로젝트 루트 — 설정 API(`/api/settings/env`)와 같은 규칙을 쓴다."""
    from antigravity_k.config import config as app_config

    return str(app_config.paths.project_root)


def _overlay(settings: SsakSearchSettings, updates: dict[str, object]) -> SsakSearchSettings:
    """현재 설정에 저장할 값을 **덮어쓴** 스냅숏(검증·응답용, 저장 전).

    `problem` 은 저장 뒤에 다시 계산한다 — 이전 problem 을 그대로 들고 가면 고친 뒤에도
    오류로 남는다.
    """
    artifact = updates.get("artifact_path", settings.artifact_path)
    return SsakSearchSettings(
        enabled=bool(updates.get("enabled", settings.enabled)),
        mode=str(updates.get("mode", settings.mode)),
        fallback=str(updates.get("fallback", settings.fallback)),
        artifact_path=str(artifact) if artifact else None,
        manifest_path=settings.manifest_path,
        problem=None,
        extra_trusted_roots=extra_trusted_roots(),
    )


def _validate_candidate(candidate: SsakSearchSettings) -> str | None:
    """저장 전 검증 — `search.ssak` 계약의 규칙을 그대로 쓴다(두 곳에서 따로 판단하지 않는다)."""
    return _validate_search_section(
        {
            "enabled": candidate.enabled,
            "mode": candidate.mode,
            "fallback": candidate.fallback,
            "artifact_path": candidate.artifact_path,
        }
    )


@router.get("/api/search/status")
async def search_status(
    include_evidence: Annotated[bool, Query(description="최근 검색 시도를 함께 포함할지")] = True,
) -> dict[str, object]:
    """검색 통합 상태 — 사용자에게 보여줄 의미(라벨·톤·다음 행동)와 설정·런타임 스냅숏.

    child 를 만들지 않는다(조회는 부작용이 없다). 아직 시작 전이면 `availability: "idle"`.
    """
    snapshot = await asyncio.to_thread(availability_snapshot, None, include_evidence=include_evidence)
    return snapshot


@router.get("/api/search/evidence")
async def search_evidence(
    limit: Annotated[int, Query(ge=0, le=EVIDENCE_HISTORY_LIMIT)] = EVIDENCE_HISTORY_LIMIT,
) -> dict[str, object]:
    """최근 검색 시도 — 출처·수집시각·부분 수집·상한 초과(최신이 앞)."""
    return await asyncio.to_thread(evidence_snapshot, limit)


class _SearchSettingsRequest(BaseModel):
    """부분 갱신. **보내지 않은 필드는 유지**한다.

    `artifact_path` 는 빈 문자열과 누락이 다르다: 누락 = 유지, `""` = 지우기(yaml 기본으로 되돌림).
    그 구분이 없으면 화면이 "경로를 지우는 것"과 "경로를 건드리지 않는 것"을 구분할 수 없다.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    mode: str | None = None
    fallback: str | None = None
    artifact_path: str | None = Field(default=None, max_length=1024)


@router.post("/api/search/settings")
async def save_search_settings(request: Request) -> dict[str, object]:
    """검색 설정을 검증하고 저장한다(켜기/끄기·경로·모드·대체 정책).

    검증이 실패하면 **아무것도 쓰지 않는다**. 성공하면 `.env` 를 원자적으로 갱신하고 프로세스 env 도
    같이 바꿔 다음 검색부터 즉시 반영되게 한다(설정 화면의 API 키와 달리 재시작을 기다리지 않는다).
    살아 있는 child 가 옛 설정으로 돌고 있으면 상태가 `restart_required` 로 그 사실을 알린다.
    """
    try:
        payload = _SearchSettingsRequest.model_validate(await request.json())
    except (ValidationError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid request body") from exc

    updates: dict[str, object] = {}
    if payload.enabled is not None:
        updates["enabled"] = payload.enabled
    if payload.mode is not None:
        updates["mode"] = payload.mode.strip()
    if payload.fallback is not None:
        updates["fallback"] = payload.fallback.strip()
    if payload.artifact_path is not None:
        updates["artifact_path"] = payload.artifact_path.strip() or None
    if not updates:
        raise HTTPException(status_code=400, detail="no search settings to change")

    current = await asyncio.to_thread(settings_snapshot)
    candidate = _overlay(current, updates)
    problem = _validate_candidate(candidate)
    if problem:
        raise HTTPException(status_code=400, detail=problem)

    _require_allowed("save_search_settings", {"fields": sorted(updates)}, "critical")

    env_updates: dict[str, str] = {}
    env_deletions: list[str] = []
    for field, value in updates.items():
        key = SEARCH_SETTING_ENV[field]
        if field == "artifact_path":
            if value:
                env_updates[key] = str(value)
            else:
                env_deletions.append(key)
        elif field == "enabled":
            env_updates[key] = "true" if value else "false"
        else:
            env_updates[key] = str(value)

    try:
        await asyncio.to_thread(
            apply_env_settings,
            resolve_env_file_path(_settings_project_root()),
            updates=env_updates,
            deletions=env_deletions,
        )
    except EnvSettingError:
        logger.warning("Rejected search settings write: invalid env assignment")
        raise HTTPException(status_code=400, detail="Invalid search setting") from None

    # 프로세스 env 도 같이 바꾼다 — `.env` 만 바꾸면 다음 재시작까지 화면과 동작이 갈라진다.
    for key, value in env_updates.items():
        os.environ[key] = value
    for key in env_deletions:
        os.environ.pop(key, None)

    snapshot = await asyncio.to_thread(availability_snapshot, None)
    snapshot["saved"] = sorted(updates)
    return snapshot


class _ProbeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(default="", max_length=MAX_QUERY_LENGTH)
    max_results: int = Field(default=5, ge=1, le=MAX_PROBE_RESULTS)


@router.post("/api/search/probe")
async def search_probe(request: Request) -> dict[str, object]:
    """연결 확인 — 번들 provider 로 실제 검색 한 번.

    legacy 로 대체하지 않는다: 여기서 답하려는 질문은 "번들이 되느냐"이고, 대체하면 답이 사라진다.
    """
    try:
        payload = _ProbeRequest.model_validate(await request.json())
    except (ValidationError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid request body") from exc
    query = payload.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")
    _require_allowed("search_probe", {"query_length": len(query)}, "critical")
    result = await asyncio.to_thread(
        probe_search,
        query,
        max_results=payload.max_results,
    )
    # 실패도 200 으로 돌려준다 — 이 응답의 본문이 곧 관측 결과이고, 화면은 evidence.failure_class 로
    # 성공/실패를 구분한다(HTTP 상태로 실패를 표현하면 "요청이 틀렸다"는 다른 뜻이 된다).
    return result


@router.post("/api/search/retry")
async def search_retry() -> dict[str, object]:
    """회로를 닫고 child 시작을 한 번 시도한 뒤 상태를 돌려준다."""
    _require_allowed("search_retry", {}, "critical")
    snapshot = await asyncio.to_thread(retry_availability)
    return snapshot


__all__ = ["router"]
