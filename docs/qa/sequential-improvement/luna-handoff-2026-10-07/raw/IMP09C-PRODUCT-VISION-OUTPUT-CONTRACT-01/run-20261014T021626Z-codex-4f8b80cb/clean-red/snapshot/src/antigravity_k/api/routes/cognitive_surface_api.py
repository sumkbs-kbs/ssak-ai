"""인지 표면 상태 API — read-only 조회(P11).

계약:

- **읽기 전용:** episode를 실행하지 않고 canonical store에 아무 것도 쓰지 않는다. 설정이 없으면
  ``source=legacy``(신규 core OFF)를 그대로 보고한다.
- **legacy 계약 유지:** 기존 라우트 응답·경로를 바꾸지 않고 새 prefix(``/api/cognitive/surface``)만 추가한다.
- **실측 캐시:** ``/reach``는 정적 import 그래프를 스캔하므로 프로세스당 1회 계산해 캐시한다
  (``?refresh=true``로 재계산). 캐시는 파일을 쓰지 않는다.
- **스트림도 read-only·유한:** ``/stream``은 표면 상태 snapshot을 ``limit``회 보내고 ``done``으로 끝난다.
  무한 폴링·자동 갱신을 만들지 않으며, 스트림이 상태를 바꾸지 않는다(episode·dispatch 0).

decision trace·policy version의 실제 값 노출은 Body store 결선이 필요하므로 아직 ``null``이며 P11 잔여 항목이다.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from antigravity_k.config import config
from antigravity_k.engine.cognitive_surface import (
    CognitiveCoreSettings,
    CognitiveSurfaceAdapter,
    DurableSurfaceHistoryStore,
    SurfaceMeasurement,
    measure_surface_reach,
)

from .cognitive_active_api import router as active_router

router = APIRouter(prefix="/api/cognitive/surface", tags=["cognitive"])
router.include_router(active_router)

_reach_cache: SurfaceMeasurement | None = None


def _history_store_from_config() -> DurableSurfaceHistoryStore | None:
    """Optional durable history path from cognitive_core.surface_history_path or default under project."""

    from pathlib import Path as _Path

    raw = getattr(config, "_raw", None)
    section: dict[str, object] = {}
    if isinstance(raw, dict):
        section = raw.get("cognitive_core") or {}
    path_value = None
    if isinstance(section, dict):
        path_value = section.get("surface_history_path")
    if not path_value:
        root = getattr(getattr(config, "paths", None), "project_root", None)
        if root:
            path_value = str(_Path(str(root)) / ".ssak" / "surface_history.sqlite")
    if not path_value:
        return None
    path = _Path(str(path_value))
    # Read-only status may open an empty store; that is still a durable projection, not invented counters.
    return DurableSurfaceHistoryStore(path)


def get_surface_adapter() -> CognitiveSurfaceAdapter:
    """설정에서 만든 read-only adapter. 실행 port·brain은 연결하지 않는다.

    history_store가 있으면 새 빈 adapter라도 durable episode/dispatch를 보고한다.
    """

    return CognitiveSurfaceAdapter(
        CognitiveCoreSettings.from_config(config),
        history_store=_history_store_from_config(),
    )


def get_surface_measurement(*, refresh: bool = False) -> SurfaceMeasurement:
    """표면 도달 실측. 프로세스당 1회 계산하고 결과만 캐시한다."""

    global _reach_cache
    if _reach_cache is None or refresh:
        _reach_cache = measure_surface_reach()
    return _reach_cache


def reset_surface_measurement_cache() -> None:
    """테스트·설정 변경 후 캐시를 비운다(파일 캐시가 아니다)."""

    global _reach_cache
    _reach_cache = None


@router.get("/status")
def cognitive_surface_status(
    adapter: Annotated[CognitiveSurfaceAdapter, Depends(get_surface_adapter)],
) -> dict[str, object]:
    """현재 표면이 legacy loop와 신규 core 중 무엇을 쓰는지, 어떤 mode인지 보고한다.

    configured/requested mode · actual activation · durable history는 분리된 필드로 노출한다.
    이 조회는 episode/Brain/action/learning을 실행하지 않는다(side effect 0).
    """

    status = adapter.status()
    payload = dict(status.as_mapping())
    payload["configured_mode"] = status.mode.value if hasattr(status.mode, "value") else str(status.mode)
    payload["requested_mode"] = status.requested_mode
    payload["actual_active"] = status.activation is not None
    payload["static_reach_is_runtime_evidence"] = False
    hist_notes = [n for n in status.notes if n.startswith("history_source=")]
    payload["history_source"] = hist_notes[0].split("=", 1)[1] if hist_notes else "in_memory"
    return payload


@router.get("/reach")
def cognitive_surface_reach(
    refresh: Annotated[bool, Query(description="정적 import 그래프를 다시 스캔한다")] = False,
) -> dict[str, object]:
    """entrypoint별로 legacy loop와 신규 core에 도달하는지(정적 import 그래프) 보고한다."""

    return dict(get_surface_measurement(refresh=refresh).as_mapping())


@router.get("/stream")
def cognitive_surface_stream(
    adapter: Annotated[CognitiveSurfaceAdapter, Depends(get_surface_adapter)],
    limit: Annotated[int, Query(ge=1, le=10, description="보낼 snapshot 수")] = 1,
    interval_ms: Annotated[int, Query(ge=0, le=5000, description="snapshot 간 간격(ms)")] = 0,
) -> StreamingResponse:
    """표면 상태를 SSE로 보낸다. 기본은 snapshot 1건 뒤 `done`으로 끝나는 유한 스트림이다."""

    async def events() -> AsyncIterator[str]:
        for index in range(limit):
            snapshot = {
                "event": "surface_status",
                "index": index + 1,
                "limit": limit,
                "status": dict(adapter.status().as_mapping()),
            }
            yield f"event: surface_status\ndata: {json.dumps(snapshot)}\n\n"
            if interval_ms:
                await asyncio.sleep(interval_ms / 1000)
        yield f"event: done\ndata: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
