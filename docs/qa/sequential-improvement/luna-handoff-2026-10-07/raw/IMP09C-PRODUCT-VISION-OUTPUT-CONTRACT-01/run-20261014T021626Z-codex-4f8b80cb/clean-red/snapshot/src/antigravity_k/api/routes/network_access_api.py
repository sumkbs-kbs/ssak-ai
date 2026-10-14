"""Personal-use mobile / LAN access introspection (read-only)."""

from __future__ import annotations

import socket
from typing import Any

from fastapi import APIRouter

from antigravity_k.api.startup_security import is_loopback_host
from antigravity_k.config import config

router = APIRouter(tags=["network"])


def _lan_ipv4() -> list[str]:
    """Best-effort private IPv4 list for personal LAN / Tailscale hints."""
    found: list[str] = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, family=socket.AF_INET):
            ip = info[4][0]
            # NX-10: typeshed 는 `info[4][0]` 을 `str | int` 로 넓힌다(IPv6 scope-id 형태).
            # 이 목록은 문자열 IPv4 만 담으므로 비문자열은 건너뛴다 — 동작은 그대로다.
            if not isinstance(ip, str):
                continue
            if ip and not ip.startswith("127.") and ip not in found:
                found.append(ip)
    except OSError:
        pass
    # Also probe a UDP connect trick for primary outbound interface.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("1.1.1.1", 80))
            ip = sock.getsockname()[0]
            if ip and not ip.startswith("127.") and ip not in found:
                found.insert(0, ip)
    except OSError:
        pass
    return found[:8]


@router.get("/api/network/access-info")
async def network_access_info() -> dict[str, Any]:
    """Return current bind posture and mobile connection hints.

    Does not change bind. Enabling mobile access still requires restarting
    Host with a non-loopback ``--host`` (and a configured PIN).
    """
    host = str(getattr(config.server, "host", "127.0.0.1") or "127.0.0.1")
    port = int(getattr(config.server, "port", 8000) or 8000)
    loopback = is_loopback_host(host)
    lan = _lan_ipv4()
    urls = [f"http://{ip}:{port}" for ip in lan]
    return {
        "bind_host": host,
        "port": port,
        "is_loopback": loopback,
        "lan_ipv4": lan,
        "suggested_mobile_urls": urls,
        "mobile_bind_default": False,
        "restart_command_lan": f"agk serve --host 0.0.0.0 --port {port}",
        "notes": [
            "기본은 loopback(127.0.0.1) — 개인 데스크톱 전용.",
            "모바일 접속은 명시적으로 non-loopback bind + PIN 필요 (startup_security).",
            "가능하면 Tailscale 등 사설망을 쓰고, 불특정 인터넷 공개는 피하세요.",
            "Agent 시작 페이지의 Cloudflare/LAN 안내도 참고하세요.",
        ],
    }
