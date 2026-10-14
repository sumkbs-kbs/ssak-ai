"""SEC-03 — WebSocket Origin allowlist.

GA-100 plan §SEC-03: cross-site browser 시나리오(다른 사이트의 페이지가
사용자의 브라우저로 로컬 서버 WS에 연결해 이벤트를 읽거나 side effect를
일으키는 공격)를 차단한다.

정책:
- **browser가 아닌 클라이언트**(curl, CLI, 테스트)는 Origin 헤더를 보내지
  않는다 — origin이 없으면 허용한다 (missing origin은 browser 공격이 아니다).
- **browser 클라이언트**는 반드시 Origin을 보내며, allowlist와 정확히 일치해야
  한다 (scheme + host + port). 일치하지 않으면 4403으로 거절한다.
- allowlist는 HTTP CORS allowlist(server.py의 cors_origins)와 **같은 소스**를
  쓴다: ``AGK_CORS_ORIGINS`` env 또는 같은 기본값. CORS로 REST가 보호되는데
  WS만 열려 있는 비대칭을 없앤다. localhost의 포트 변형은 자동 포함한다.
- 서브패스나 대소문자 변형 우회를 막기 위해 정확 문자열 비교만 사용한다
  (suffix/suffix-match 없음).
"""

from __future__ import annotations

import os
from typing import Final

__all__ = ["ws_origin_allowed", "ws_origin_allowlist"]

_CORS_ENV: Final[str] = "AGK_CORS_ORIGINS"

# 기본 허용 origin — server.py의 cors_origins 기본값과 동일 유지.
_DEFAULT_ORIGINS: Final[tuple[str, ...]] = (
    "http://localhost:5173",  # Vite dev server
    "http://localhost:5174",
    "http://localhost:4178",  # Vite preview server
    "http://localhost:8000",  # Production uvicorn
    "http://localhost:8012",  # Test / E2E uvicorn
    "http://127.0.0.1:5173",
    "http://127.0.0.1:4178",
    "http://127.0.0.1:8000",
    "http://127.0.0.1:8012",
)


def ws_origin_allowlist() -> frozenset[str]:
    """현재 허용 origin 집합을 반환한다 (요청마다 재판독 — 캐시 금지).

    AGK_CORS_ORIGINS가 설정되어 있으면 그 목록을 신뢰하고(운영자가 CORS와
    WS를 한 곳에서 제어), 없으면 기본값을 쓴다.
    """
    env = os.environ.get(_CORS_ENV, "").strip()
    if env:
        origins = {o.strip().rstrip("/") for o in env.split(",") if o.strip()}
        return frozenset(origins)
    return frozenset(_DEFAULT_ORIGINS)


def ws_origin_allowed(origin: str | None) -> bool:
    """WS 연결의 Origin 헤더를 판정한다.

    - ``None``/빈 값: browser가 아닌 클라이언트 — 허용.
    - 그 외: allowlist 정확 일치만 허용.
    """
    if not origin:
        return True
    normalized = origin.strip().rstrip("/")
    if not normalized:
        return True
    return normalized in ws_origin_allowlist()
