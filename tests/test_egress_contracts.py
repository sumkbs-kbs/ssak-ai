"""egress / SSRF 보안 계약 고정 (Phase 58).

================================================================
배경: Phase 56이 path_security·git_api·filesystem 경로 경계를 모듈
레벨에서 잠근 것과 같이, egress_policy + is_public_http_url 경계를
엔드포인트/재시도 테스트 우연에 맡기지 않고 **계약 자체**로 고정한다.

잠근 계약:

A. ``validate_egress_url`` — URL 스키마·자격증명·로컬 게이트
   1. HTTP(S)만 허용 (file/ftp/자격증명 URL 거부)
   2. ``allow_local=True`` 일 때 localhost / 127.0.0.1 / ::1 / *.localhost 허용
   3. ``allow_local=False`` 일 때 위 로컬 호스트 거부
   4. RFC1918·링크로컬·미지정 등 private literal IP 거부
   5. 모호한 IPv4 표기(decimal/short/hex/octal)도 private로 취급 (DNS 우회 차단)

B. DNS 재바인딩 가드
   6. ``resolve_dns=True``(기본)에서 공개 호스트명이 private A/AAAA로
      해석되면 거부 — resolve 훅을 빼는 재작성 차단

C. 공개 커넥터 훅
   7. ``validate_public_httpx_request`` 는 항상 ``allow_local=False``
   8. ``validate_httpx_request`` 기본은 로컬 허용 (Ollama 등 내부 커넥터
      carve-out — 공개 웹훅/에이전트 도구는 public 훅을 써야 함)

D. ``safe_urlopen`` 선검증
   9. urlopen 호출 **전에** 정책을 적용 — 검증 실패 시 urlopen 미호출

E. 교차 일관성
   10. ``is_public_http_url`` 이 False인 대상은 ``validate_egress_url(...,
       allow_local=False, resolve_dns=False)`` 도 거부해야 한다.
"""

from __future__ import annotations

from urllib.request import Request

import httpx
import pytest

from antigravity_k.tools.egress_policy import (
    EgressPolicyError,
    safe_urlopen,
    validate_egress_url,
    validate_httpx_request,
    validate_public_httpx_request,
)
from antigravity_k.tools.web_search_quality import is_public_http_url

# ── A. validate_egress_url 스키마·로컬·private ──────────────────


def test_egress_rejects_non_http_and_credential_urls() -> None:
    for url in (
        "file:///etc/passwd",
        "ftp://example.com/x",
        "https://user:pass@example.com/v1",
        "not-a-url",
        "",
    ):
        with pytest.raises(EgressPolicyError):
            _ = validate_egress_url(url, resolve_dns=False)


def test_egress_allows_local_hosts_only_when_enabled() -> None:
    locals_ = (
        "http://localhost:11434/api/tags",
        "http://127.0.0.1:11434/api/tags",
        "http://[::1]:11434/api/tags",
        "http://ollama.localhost/api/tags",
    )
    for url in locals_:
        assert validate_egress_url(url, allow_local=True, resolve_dns=False)
        with pytest.raises(EgressPolicyError):
            _ = validate_egress_url(url, allow_local=False, resolve_dns=False)


def test_egress_rejects_private_literal_ips() -> None:
    for url in (
        "http://10.0.0.8/x",
        "http://192.168.1.20/x",
        "http://172.16.5.1/x",
        "http://169.254.169.254/latest/meta-data/",
        "http://0.0.0.0/",
    ):
        with pytest.raises(EgressPolicyError):
            _ = validate_egress_url(url, allow_local=False, resolve_dns=False)


def test_egress_rejects_ambiguous_ipv4_encodings_even_without_dns() -> None:
    """decimal/short/hex/octal loopback 표기는 DNS 없이도 차단되어야 한다.

    getaddrinfo 와 inet_aton 이 서로 다른 주소로 해석하는 플랫폼(macOS octal)
    에서 DNS 가드만 믿으면 우회가 열린다 — is_public_http_url 이 모호 표기를
    먼저 private로 판정해야 한다.
    """
    for url in (
        "http://2130706433/",  # decimal 127.0.0.1
        "http://127.1/",  # short 127.0.0.1
        "http://0x7f.0.0.1/",  # hex
        "http://0177.0.0.1/",  # octal-leading (inet_aton → 127.0.0.1)
    ):
        assert is_public_http_url(url) is False
        with pytest.raises(EgressPolicyError):
            _ = validate_egress_url(url, allow_local=False, resolve_dns=False)


# ── B. DNS 재바인딩 ─────────────────────────────────────────────


def test_egress_dns_guard_rejects_public_name_resolving_private(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "antigravity_k.tools.egress_policy.resolve_public_http_url_sync",
        lambda _url: None,
    )
    with pytest.raises(EgressPolicyError):
        _ = validate_egress_url("https://provider.example/v1", allow_local=False, resolve_dns=True)


def test_egress_dns_guard_default_is_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """resolve_dns 기본값(True)을 False로 바꾸는 재작성을 잡는다."""
    seen: list[bool] = []

    def fake_resolve(url: str) -> None:
        _ = url
        seen.append(True)
        return None

    monkeypatch.setattr(
        "antigravity_k.tools.egress_policy.resolve_public_http_url_sync",
        fake_resolve,
    )
    with pytest.raises(EgressPolicyError):
        _ = validate_egress_url("https://provider.example/v1")
    assert seen, "기본 경로가 DNS 가드를 건너뛰면 안 된다"


# ── C. httpx 훅 ─────────────────────────────────────────────────


def test_public_httpx_hook_never_allows_local() -> None:
    request = httpx.Request("POST", "http://127.0.0.1:8080/webhook")
    with pytest.raises(EgressPolicyError):
        validate_public_httpx_request(request)


def test_default_httpx_hook_allows_local_ollama_carve_out() -> None:
    """내부 커넥터용 기본 훅 — 공개 웹훅은 validate_public_* 를 써야 한다."""
    request = httpx.Request("GET", "http://localhost:11434/api/tags")
    validate_httpx_request(request)  # does not raise


# ── D. safe_urlopen 선검증 ──────────────────────────────────────


def test_safe_urlopen_validates_before_urlopen(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[str] = []

    def boom(_opener: object, target: object, *_a: object, **_k: object) -> None:
        opened.append("opened")
        raise AssertionError("urlopen must not run after policy failure")

    monkeypatch.setattr("urllib.request.OpenerDirector.open", boom)
    with pytest.raises(EgressPolicyError):
        _ = safe_urlopen("http://192.168.0.9/secret", allow_local=False, timeout=1)
    assert opened == []


def test_safe_urlopen_opens_only_after_policy_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[str] = []

    def fake_urlopen(_opener: object, target: str | Request, *_a: object, **_k: object) -> str:
        opened.append(target.full_url if isinstance(target, Request) else target)
        return "ok"

    monkeypatch.setattr("urllib.request.OpenerDirector.open", fake_urlopen)
    assert safe_urlopen("http://127.0.0.1:11434/api/tags", allow_local=True, timeout=1) == "ok"
    assert opened == ["http://127.0.0.1:11434/api/tags"]


# ── E. 교차 일관성 ──────────────────────────────────────────────


def test_non_public_urls_are_rejected_by_egress_without_local() -> None:
    samples = (
        "http://10.1.2.3/",
        "http://169.254.169.254/",
        "http://2130706433/",
        "http://service.internal/x",
        "file:///etc/passwd",
    )
    for url in samples:
        assert is_public_http_url(url) is False
        with pytest.raises(EgressPolicyError):
            _ = validate_egress_url(url, allow_local=False, resolve_dns=False)
