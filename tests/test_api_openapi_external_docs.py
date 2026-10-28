"""외부 문서 메타데이터는 최종 OpenAPI 에 실리고, 기존 보안 스키마·캐시를 보존한다 (CR-14 recovery4)."""

from __future__ import annotations


def test_openapi_carries_external_docs_and_keeps_security_and_cache() -> None:
    from antigravity_k.api import server

    server.app.openapi_schema = None
    first = server.app.openapi()
    assert first["externalDocs"] == {
        "description": "온보딩 가이드",
        "url": "https://github.com/ssak-comp/Ssak-Ai/blob/main/ONBOARDING.md",
    }
    assert "OAuth2Password" in first["components"]["securitySchemes"]
    assert first["security"] == [{"OAuth2Password": []}]
    assert first["info"]["license"]["identifier"] == "MIT"
    assert "/health" in first["paths"]
    second = server.app.openapi()
    assert second is first, "반복 호출은 캐시된 같은 스키마를 돌려준다(래퍼 누적 없음)"
    assert server.app.openapi is server._custom_openapi
