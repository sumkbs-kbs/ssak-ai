"""task 16 계약 시험 — 브라우저 세션 소유권 단일화.

여기서 고정하는 문장:

- **누가 여는지 모르면 열지 않는다**: 모든 세션은 `BrowserOwner`(subject·scope·task)에 묶이고,
  같은 owner 는 같은 세션을 재사용하며, 다른 owner 는 다른 세션을 받는다.
- **호스트는 기본 2개만 연다**: 세 번째는 기다리지 않고 거절되고, 예약이 **미리 상한을 차지**하므로
  동시 첫 호출 10개가 브라우저 10개를 띄우지 않는다.
- **시간 축이 있다**: 놀고 있으면(기본 15분) 작업 시간을 넘겼으면(기본 10분) 회수되고, 회수는
  세션의 close 콜백을 실제로 부른다.
- **기본은 격리된 일회용 컨텍스트**: persistent profile 은 명시 owner + 명시 동의일 때만 열린다.
- **개인 Chrome/CDP 가 열어 둔 페이지를 채택하지 않는다**: 관찰만 하고 항상 새 페이지를 연다.
- **egress 는 한 곳에 있다**: 진입점들이 각자 판단하지 않고 소유자의 규칙을 지난다.
"""

from __future__ import annotations

import asyncio
import warnings
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import cast

import pytest

from antigravity_k.tools import browser_session_owner as owner_module
from antigravity_k.tools.browser_session_owner import (
    ANONYMOUS_SUBJECT,
    DEFAULT_IDLE_TTL_SECONDS,
    DEFAULT_MAX_ACTIVE_SESSIONS,
    DEFAULT_TASK_DEADLINE_SECONDS,
    BrowserOwner,
    BrowserSessionLimitError,
    BrowserSessionOwner,
    BrowserSessionRefusedError,
    current_browser_owner,
    get_browser_session_owner,
    personal_profile_allowed,
    shutdown_browser_sessions,
)

REPO = Path(__file__).resolve().parent.parent


class _FakePage:
    """페이지의 최소 계약: url 과 close(). 실제 Playwright 없이 정책만 잰다."""

    def __init__(self, url: str = "about:blank") -> None:
        self.url: str = url
        self.closed: int = 0

    def close(self) -> None:
        self.closed += 1


class _Clock:
    def __init__(self) -> None:
        self.now: float = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _owner(subject: str = "user@example.com", scope: str = "web-1", task_id: str = "t-1") -> BrowserOwner:
    return BrowserOwner(subject=subject, scope=scope, task_id=task_id)


def _open(owner: BrowserSessionOwner, who: BrowserOwner, *, purpose: str = "test") -> object:
    reservation = owner.begin(who, purpose=purpose)
    if reservation.is_reuse:
        reuse = reservation.reuse
        assert reuse is not None
        return reuse
    page = _FakePage()
    return owner.commit(reservation, page=page, close=lambda: cast(_FakePage, page).close())


# ── 소유권 ──────────────────────────────────────────────────────────────────


def test_the_same_owner_reuses_one_session() -> None:
    owner = BrowserSessionOwner()
    first = _open(owner, _owner())
    second = _open(owner, _owner())

    assert first is second
    assert owner.active_count == 1


def test_different_owners_get_different_sessions() -> None:
    owner = BrowserSessionOwner()
    first = _open(owner, _owner(scope="web-1"))
    second = _open(owner, _owner(scope="web-2"))

    assert first is not second
    assert owner.active_count == 2


def test_the_same_subject_with_a_different_task_is_a_different_owner() -> None:
    """task 가 다르면 다른 세션이다 — 다른 작업의 탭을 이어받으면 그게 소유권 붕괴다."""
    owner = BrowserSessionOwner()
    first = _open(owner, _owner(task_id="t-1"))
    second = _open(owner, _owner(task_id="t-2"))

    assert first is not second


def test_owner_key_never_exposes_the_raw_identity_in_status() -> None:
    owner = BrowserSessionOwner()
    _ = _open(owner, _owner(subject="secret-user@example.com"))
    status = owner.status()
    sessions = cast(list[dict[str, object]], status["sessions"])
    described = cast(dict[str, str], sessions[0]["owner"])

    assert described["key"] and len(described["key"]) == 12
    assert described["subject"] == "secret-user@example.com"  # 주체는 보이지만 주소 전체/토큰은 없다
    assert "|" not in described["key"]


# ── 상한과 예약 ─────────────────────────────────────────────────────────────


def test_the_host_default_is_two_sessions_and_the_third_is_refused() -> None:
    owner = BrowserSessionOwner()
    _ = _open(owner, _owner(scope="a"))
    _ = _open(owner, _owner(scope="b"))

    with pytest.raises(BrowserSessionLimitError):
        _ = owner.begin(_owner(scope="c"))

    assert owner.active_count == DEFAULT_MAX_ACTIVE_SESSIONS == 2


def test_a_reservation_takes_the_slot_before_the_browser_is_launched() -> None:
    """동시 첫 호출이 전부 통과하면 안 된다 — launch 는 await/IO 라 예약이 없으면 10개가 뜬다."""
    owner = BrowserSessionOwner()
    reservations = [owner.begin(_owner(scope=f"s{i}")) for i in range(2)]

    assert len(reservations) == 2
    with pytest.raises(BrowserSessionLimitError):
        _ = owner.begin(_owner(scope="s3"))

    # 하나를 반납하면 자리가 난다.
    owner.abort(reservations[1])
    _ = owner.begin(_owner(scope="s3"))


def test_the_same_owner_calling_twice_while_launching_gets_one_reservation() -> None:
    owner = BrowserSessionOwner()
    who = _owner()
    first = owner.begin(who)
    second = owner.begin(who)

    assert first is second, "같은 owner 의 동시 첫 호출이 두 개의 launch 를 만들면 안 된다"
    assert not first.is_reuse


def test_aborting_a_reservation_returns_the_slot() -> None:
    owner = BrowserSessionOwner(max_active_sessions=1)
    reservation = owner.begin(_owner(scope="a"))
    owner.abort(reservation)

    assert owner.active_count == 0
    _ = owner.begin(_owner(scope="b"))


def test_release_drops_the_session_and_the_next_begin_creates_a_new_one() -> None:
    owner = BrowserSessionOwner()
    who = _owner()
    first = _open(owner, who)

    assert owner.release(who) is True
    assert owner.release(who) is False, "없는 세션을 닫았다고 답하면 안 된다"

    second = _open(owner, who)
    assert second is not first


# ── 시간 축 ─────────────────────────────────────────────────────────────────


def test_defaults_are_fifteen_minutes_idle_and_ten_minutes_deadline() -> None:
    owner = BrowserSessionOwner()

    assert owner.idle_ttl_seconds == DEFAULT_IDLE_TTL_SECONDS == 900
    assert owner.task_deadline_seconds == DEFAULT_TASK_DEADLINE_SECONDS == 600


def test_an_idle_session_is_reaped_and_closed() -> None:
    clock = _Clock()
    owner = BrowserSessionOwner(clock=clock)
    lease = cast(object, _open(owner, _owner()))
    page = cast(_FakePage, lease.page)  # type: ignore[attr-defined]

    clock.advance(DEFAULT_IDLE_TTL_SECONDS + 1)
    reaped = owner.reap()

    assert [item["reason"] for item in reaped] == ["idle_ttl"]
    assert page.closed == 1, "회수는 close 를 실제로 불러야 한다"
    assert owner.active_count == 0


def test_a_session_that_outlives_the_task_deadline_is_reaped_even_if_busy() -> None:
    """계속 쓰고 있어도 작업 시간을 넘기면 회수한다 — 안 그러면 끝나지 않는 작업이 브라우저를 붙잡는다."""
    clock = _Clock()
    owner = BrowserSessionOwner(clock=clock)
    lease = cast(object, _open(owner, _owner()))
    page = cast(_FakePage, lease.page)  # type: ignore[attr-defined]

    for _ in range(12):
        clock.advance(DEFAULT_IDLE_TTL_SECONDS / 2)
        lease.touch(clock())  # type: ignore[attr-defined]

    reaped = owner.reap()

    assert [item["reason"] for item in reaped] == ["task_deadline"]
    assert page.closed == 1


def test_reaping_happens_before_the_limit_is_checked() -> None:
    """만료된 세션이 자리를 계속 차지하면, 살아 있는 사용자가 영원히 429 를 받는다."""
    clock = _Clock()
    owner = BrowserSessionOwner(max_active_sessions=1, clock=clock)
    _ = _open(owner, _owner(scope="old"))

    clock.advance(DEFAULT_IDLE_TTL_SECONDS + 1)

    fresh = owner.begin(_owner(scope="new"))
    assert not fresh.is_reuse
    assert owner.status()["reaped"] != []  # type: ignore[comparison-overlap]


def test_an_abandoned_reservation_does_not_hold_the_slot_forever() -> None:
    clock = _Clock()
    owner = BrowserSessionOwner(clock=clock)
    _ = owner.begin(_owner(scope="stuck"))

    clock.advance(DEFAULT_TASK_DEADLINE_SECONDS + 1)
    reaped = owner.reap()

    assert any(item["reason"] == "abandoned_reservation" for item in reaped)
    assert owner.active_count == 0


def test_idle_and_deadline_are_configurable_and_measured_from_the_same_clock() -> None:
    clock = _Clock()
    owner = BrowserSessionOwner(idle_ttl_seconds=5, task_deadline_seconds=50, clock=clock)
    _ = _open(owner, _owner())

    clock.advance(6)
    assert [item["reason"] for item in owner.reap()] == ["idle_ttl"]


# ── persistent profile ──────────────────────────────────────────────────────


def test_an_ephemeral_session_has_no_profile() -> None:
    owner = BrowserSessionOwner()
    lease = _open(owner, _owner())

    assert cast(object, lease).persistent_profile is None  # type: ignore[attr-defined]


def test_a_persistent_profile_requires_an_explicit_owner(tmp_path: Path) -> None:
    owner = BrowserSessionOwner()
    profile = str(tmp_path)

    with pytest.raises(BrowserSessionRefusedError):
        _ = owner.begin(BrowserOwner(), persistent_profile=profile)

    with pytest.raises(BrowserSessionRefusedError):
        _ = owner.begin(BrowserOwner(subject="user@example.com"), persistent_profile=profile)

    assert owner.active_count == 0, "거절은 자리를 남기면 안 된다"


def test_a_persistent_profile_must_be_a_real_absolute_directory(tmp_path: Path) -> None:
    owner = BrowserSessionOwner()
    who = _owner()

    with pytest.raises(BrowserSessionRefusedError):
        _ = owner.begin(who, persistent_profile="relative/profile")

    with pytest.raises(BrowserSessionRefusedError):
        _ = owner.begin(who, persistent_profile=str(tmp_path / "does-not-exist"))

    reservation = owner.begin(who, persistent_profile=str(tmp_path))
    lease = owner.commit(reservation, page=_FakePage(), close=lambda: None)

    assert lease.persistent_profile == str(tmp_path.resolve())


def test_policy_configuration_only_turns_persistence_on_for_an_explicit_owner(tmp_path: Path) -> None:
    owner = BrowserSessionOwner()
    anonymous_lease = _open(owner, BrowserOwner(scope="web-1"))  # 주체가 익명
    explicit_lease = _open(owner, _owner(scope="web-2"))

    assert anonymous_lease.owner.subject == ANONYMOUS_SUBJECT  # type: ignore[attr-defined]
    assert not anonymous_lease.owner.is_explicit  # type: ignore[attr-defined]
    assert explicit_lease.owner.is_explicit  # type: ignore[attr-defined]


# ── 개인 프로필 ─────────────────────────────────────────────────────────────


def test_the_personal_profile_is_off_by_default() -> None:
    assert personal_profile_allowed({}) is False
    assert personal_profile_allowed({"AGK_BROWSER_ALLOW_PERSONAL_PROFILE": "1"}) is True
    assert personal_profile_allowed({"AGK_BROWSER_ALLOW_PERSONAL_PROFILE": "true"}) is True
    assert personal_profile_allowed({"AGK_BROWSER_ALLOW_PERSONAL_PROFILE": "0"}) is False


def test_the_policy_summary_reports_the_personal_profile_switch() -> None:
    described = owner_module.describe_policy(BrowserSessionOwner())

    assert described["personal_profile_allowed"] is False
    assert "AGK_BROWSER_ALLOW_PERSONAL_PROFILE" in cast(dict[str, str], described["env"]).values()


# ── 남의 페이지를 채택하지 않기 ─────────────────────────────────────────────


def test_foreign_pages_are_recorded_but_never_used() -> None:
    owner = BrowserSessionOwner()
    foreign = [_FakePage("https://mail.example.com/inbox")]
    recorded = owner.remember_foreign_pages(foreign)

    assert list(recorded) == ["https://mail.example.com/inbox"]
    assert owner.active_count == 0, "남의 페이지를 관찰했다고 우리 세션이 생기면 안 된다"


def test_a_lease_keeps_the_list_of_pages_it_refused_to_adopt() -> None:
    owner = BrowserSessionOwner()
    reservation = owner.begin(_owner())
    lease = owner.commit(
        reservation,
        page=_FakePage(),
        close=lambda: None,
        foreign_pages=[_FakePage("https://personal-chrome.example/"), _FakePage()],
    )
    described = lease.to_dict(owner_module.time.monotonic())

    assert len(cast(list[str], described["foreign_pages"])) == 2


def test_no_entrypoint_adopts_an_existing_page() -> None:
    """소스 게이트: `pages[0]` 로 남의 탭을 골라 쓰는 코드가 다시 들어오지 못하게 한다.

    런타임으로 재기 어려운 이유: 개인 Chrome/CDP 가 페이지를 미리 열어 둔 상황을 만들려면 실제
    브라우저가 필요하다. 대신 **규칙을 어기는 모양**을 소스에서 막는다.
    """
    entrypoints = [
        REPO / "src" / "antigravity_k" / "engine" / "external_brain.py",
        REPO / "src" / "antigravity_k" / "tools" / "browser_tools.py",
        REPO / "src" / "antigravity_k" / "tools" / "browser_tool.py",
        REPO / "src" / "antigravity_k" / "agents" / "browser_surfing_agent.py",
        REPO / "src" / "antigravity_k" / "api" / "routes" / "agent_tools.py",
    ]
    for path in entrypoints:
        source = path.read_text(encoding="utf-8")
        assert "pages[0]" not in source, f"{path.name} 가 이미 열려 있는 페이지를 채택한다"
    brain = (REPO / "src" / "antigravity_k" / "engine" / "external_brain.py").read_text(encoding="utf-8")
    assert "remember_foreign_pages" in brain, "무시한 페이지를 기록하지도 않는다"


# ── egress 단일화 ───────────────────────────────────────────────────────────


def test_egress_is_validated_through_the_owner() -> None:
    owner = BrowserSessionOwner()

    assert owner.validate_navigation("https://example.com/a") == "https://example.com/a"
    with pytest.raises(Exception):
        _ = owner.validate_navigation("http://127.0.0.1:8080/private")


def test_every_entrypoint_routes_navigation_through_the_owner() -> None:
    expectations = {
        "browser_tools.py": "get_browser_session_owner().validate_navigation",
        "browser_tool.py": "get_browser_session_owner().validate_navigation",
        "browser_surfing_agent.py": "session_owner.validate_navigation",
        # task 17 부터 API 의 이동은 **관찰/행동 계약**을 지난다. 계약은 규칙을 다시 쓰지 않고
        # 소유자에게 위임하므로, 두 파일을 함께 검사해 사슬을 고정한다(한쪽만 보면 우회를 못 잡는다).
        "agent_tools.py": "_BROWSER_CONTRACT_ACTIONS",
        "harness.py": "session_owner.validate_navigation(self.dashboard_url, allow_local=True)",
        "autonomous_qa.py": "session_owner.validate_navigation(target_url, allow_local=True)",
    }
    for name, snippet in expectations.items():
        found = [path for path in (REPO / "src").rglob(name) if path.is_file() and "dashboard_dist" not in str(path)]
        assert found, f"{name} 를 찾지 못했다"
        assert snippet in found[0].read_text(encoding="utf-8"), f"{name} 가 소유자의 egress 규칙을 지나지 않는다"

    contract = (REPO / "src" / "antigravity_k" / "tools" / "browser_observation.py").read_text(encoding="utf-8")
    assert "validate_navigation(url, allow_local=allow_local)" in contract, (
        "관찰/행동 계약이 소유자의 egress 규칙에 위임하지 않는다"
    )


# ── 정책 설정과 종료 ────────────────────────────────────────────────────────


def test_the_policy_can_be_set_from_the_environment() -> None:
    configured = BrowserSessionOwner.from_env(
        {
            "AGK_BROWSER_MAX_SESSIONS": "5",
            "AGK_BROWSER_IDLE_TTL_SECONDS": "60",
            "AGK_BROWSER_TASK_DEADLINE_SECONDS": "120",
        },
    )

    assert (configured.max_active_sessions, configured.idle_ttl_seconds, configured.task_deadline_seconds) == (
        5,
        60.0,
        120.0,
    )


def test_a_malformed_environment_value_falls_back_instead_of_breaking_startup() -> None:
    configured = BrowserSessionOwner.from_env(
        {
            "AGK_BROWSER_MAX_SESSIONS": "carrier-pigeon",
            "AGK_BROWSER_IDLE_TTL_SECONDS": "0",
            "AGK_BROWSER_TASK_DEADLINE_SECONDS": "",
        },
    )

    assert configured.max_active_sessions == DEFAULT_MAX_ACTIVE_SESSIONS
    assert configured.idle_ttl_seconds == DEFAULT_IDLE_TTL_SECONDS
    assert configured.task_deadline_seconds == DEFAULT_TASK_DEADLINE_SECONDS


def test_a_non_positive_limit_is_rejected() -> None:
    with pytest.raises(ValueError):
        _ = BrowserSessionOwner(max_active_sessions=0)


def test_shutdown_does_not_create_a_session_owner_that_never_existed() -> None:
    owner_module.reset_browser_session_owner()

    assert shutdown_browser_sessions() is None
    assert owner_module._owner is None  # type: ignore[attr-defined]  # 종료 경로가 새로 만들지 않았다


def test_shutdown_closes_every_open_session_once() -> None:
    owner = owner_module.configure_browser_session_owner()
    first = _open(owner, _owner(scope="a"))
    second = _open(owner, _owner(scope="b"))
    try:
        report = shutdown_browser_sessions()

        assert report is not None and report["closed"] == 2
        assert cast(_FakePage, first.page).closed == 1  # type: ignore[attr-defined]
        assert cast(_FakePage, second.page).closed == 1  # type: ignore[attr-defined]
        assert owner.active_count == 0
    finally:
        owner_module.reset_browser_session_owner()


def test_the_host_lifespan_closes_browser_sessions() -> None:
    server = (REPO / "src" / "antigravity_k" / "api" / "server.py").read_text(encoding="utf-8")

    assert "shutdown_browser_sessions" in server, "종료 훅이 빠지면 호스트가 죽어도 브라우저가 남는다"


def test_the_api_registry_cap_follows_the_owner_policy() -> None:
    """두 개의 상한이 서로 다른 말을 하면, 하나는 반드시 거짓말이 된다."""
    from antigravity_k.api.routes import agent_tools

    assert agent_tools.browser_sessions.max_sessions == get_browser_session_owner().max_active_sessions


def test_the_closed_resource_is_not_reused_by_a_later_launch() -> None:
    owner = BrowserSessionOwner()
    who = _owner()
    page = cast(_FakePage, _open(owner, who).page)  # type: ignore[attr-defined]
    owner.release(who)

    reported = owner.status()
    assert reported["sessions"] == []
    assert page.closed == 1


# ── 진입점이 실제로 소유자를 지나가는가 (배선) ───────────────────────────────


def test_every_entrypoint_asks_the_owner_before_opening_a_browser() -> None:
    for name in (
        "browser_tools.py",
        "browser_tool.py",
        "browser_surfing_agent.py",
        "agent_tools.py",
        "harness.py",
        "autonomous_qa.py",
    ):
        candidates = [
            path for path in (REPO / "src").rglob(name) if path.is_file() and "dashboard_dist" not in str(path)
        ]
        assert candidates, f"{name} 를 찾지 못했다"
        source = candidates[0].read_text(encoding="utf-8")
        assert "get_browser_session_owner" in source, f"{name} 가 소유자를 가져다 쓰지 않는다"
        assert ".begin(" in source, f"{name} 가 소유자에게 자리를 묻지 않고 브라우저를 연다"
        assert ".abort(" in source, f"{name} 가 launch 실패 시 예약을 반납하지 않는다"


def test_the_entrypoints_do_not_keep_their_own_session_counter() -> None:
    """진입점이 자기 나름의 상한을 다시 들면 두 개의 상한이 생긴다(하나는 반드시 거짓말이 된다)."""
    tools = (REPO / "src" / "antigravity_k" / "tools" / "browser_tools.py").read_text(encoding="utf-8")
    class_based = (REPO / "src" / "antigravity_k" / "tools" / "browser_tool.py").read_text(encoding="utf-8")
    route = (REPO / "src" / "antigravity_k" / "api" / "routes" / "agent_tools.py").read_text(encoding="utf-8")

    assert "max_sessions=32" not in route, "상한이 소유자 정책 밖에 다시 적혀 있다"
    assert "get_browser_session_owner().max_active_sessions" in route
    for source in (tools, class_based):
        assert "max_active_sessions" not in source, "도구가 자기 상한을 따로 들고 있다"


def _fake_sync_playwright() -> object:
    """실제 브라우저 없이 "도구 경로가 소유자를 지나가는가"만 재기 위한 최소 대역."""

    class _Page:
        url = "about:blank"

        def is_closed(self) -> bool:
            return False

        def close(self) -> None:
            return None

    class _Context:
        def new_page(self) -> object:
            return _Page()

        def close(self) -> None:
            return None

    class _Browser:
        def is_connected(self) -> bool:
            return True

        def new_context(self) -> object:
            return _Context()

        def close(self) -> None:
            return None

    class _Chromium:
        def launch(self, *, headless: bool) -> object:
            assert headless is True, "도구가 헤드리스가 아니면 호출마다 사용자 화면에 창이 뜡다"
            return _Browser()

    class _Playwright:
        chromium = _Chromium()

        def start(self) -> object:
            return self

        def stop(self) -> None:
            return None

    return _Playwright


def test_the_dom_tool_opens_its_session_for_the_current_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """도구 경로도 **주체를 갖는다** — 익명 owner 로 열면 누가 그 세션을 가졌는지 아무도 모른다."""
    import sys
    import types

    from antigravity_k.tools import browser_tools

    module = types.ModuleType("playwright.sync_api")
    setattr(module, "sync_playwright", _fake_sync_playwright())
    monkeypatch.setitem(sys.modules, "playwright.sync_api", module)
    monkeypatch.setattr(browser_tools, "_page", None, raising=False)
    monkeypatch.setattr(browser_tools, "_browser", None, raising=False)
    monkeypatch.setattr(browser_tools, "_playwright", None, raising=False)

    who = _owner(scope="tool-web")
    with owner_module.bound_browser_owner(who):
        page = browser_tools.get_browser_page()

    assert page is not None
    lease = get_browser_session_owner().lease_for(who)
    assert lease is not None, "도구가 연 세션이 그 owner 의 것으로 등록되지 않았다"
    assert lease.owner is who
    assert browser_tools.get_browser_page() is page, "두 번째 호출은 같은 세션을 쓴다"


def test_the_api_owner_is_derived_from_the_request_identity() -> None:
    """헤더가 owner 가 된다 — 인증 주체·명시 scope·작업 id 가 요청에서 그대로 읽혀야 한다."""
    import contextlib

    from starlette.requests import Request

    from antigravity_k.api.routes.agent_tools import _browser_owner

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/agent/tools/browser/action",
            "headers": [(b"x-agk-browser-session", b"web-7"), (b"x-agk-task-id", b"task-9")],
        },
    )
    with contextlib.suppress(AttributeError):
        request.state.auth_subject = "user@example.com"
    who = _browser_owner(request)

    assert who.subject == "user@example.com"
    assert who.scope == "web-7"
    assert who.task_id == "task-9"
    assert who.is_explicit, "명시 헤더가 있는 요청은 명시 owner 여야 한다(개인 프로필을 요구할 수 있는 유일한 경우)"
    assert not _browser_owner(None).is_explicit


def test_only_the_operator_configured_targets_allow_local_navigation() -> None:
    """로컬 허용은 **명시**여야 한다 — 에이전트가 고른 주소를 로컬로 여는 순간 SSRF 규칙이 뚫린다."""
    owner = BrowserSessionOwner()

    assert owner.validate_navigation("http://127.0.0.1:8000/", allow_local=True) == "http://127.0.0.1:8000/"
    with pytest.raises(Exception):
        _ = owner.validate_navigation("http://127.0.0.1:8000/")

    for name in ("browser_tools.py", "browser_tool.py", "browser_surfing_agent.py", "agent_tools.py"):
        source = next(
            path for path in (REPO / "src").rglob(name) if path.is_file() and "dashboard_dist" not in str(path)
        ).read_text(encoding="utf-8")
        # 파일 어딘가의 allow_local 이 아니라, **이 호출**에 붙었는지를 본다(다른 egress 호출은 별개).
        for segment in source.split("validate_navigation(")[1:]:
            call = segment.split(")", 1)[0]
            assert "allow_local" not in call, f"{name} 가 에이전트 경로에서 로컬 이그레스를 열었다: {call}"


# ── 엔진 하네스도 같은 소유자 ───────────────────────────────────────────


def test_the_engine_harnesses_rent_the_host_browser() -> None:
    for name in ("harness.py", "autonomous_qa.py"):
        source = next(
            path for path in (REPO / "src").rglob(name) if path.is_file() and "dashboard_dist" not in str(path)
        ).read_text(encoding="utf-8")
        assert "get_browser_session_owner" in source, f"{name} 가 자기 브라우저를 따로 연다"
        assert "session_owner.release" in source, f"{name} 가 빌린 세션을 돌려주지 않는다"


def test_the_owner_is_imported_from_one_module_only() -> None:
    """소유자 모듈이 갈라지면 정책도 갈라진다 — 진입점은 이 모듈만 가져다 쓴다."""
    defined_in = [
        path.name
        for path in (REPO / "src").rglob("*.py")
        if "dashboard_dist" not in str(path) and "class BrowserSessionOwner" in path.read_text(encoding="utf-8")
    ]

    assert defined_in == ["browser_session_owner.py"]


def test_the_current_owner_defaults_to_a_local_tool_subject_without_a_persistent_profile() -> None:
    assert current_browser_owner().subject in {"local-tool", ANONYMOUS_SUBJECT}
    assert not current_browser_owner().is_explicit


def test_a_bound_owner_wins_over_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    bound = _owner(scope="bound")
    with owner_module.bound_browser_owner(bound):
        assert current_browser_owner() is bound
    assert current_browser_owner() is not bound


def test_the_bound_owner_is_released_even_when_the_body_raises() -> None:
    bound = _owner(scope="bound-raises")

    def _raise() -> Iterator[None]:
        with owner_module.bound_browser_owner(bound):
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        list(_raise())

    assert current_browser_owner() is not bound


def test_an_async_closer_is_discarded_without_warning() -> None:
    """회수는 동기 경로다 — 코루틴 close 를 그냥 버리면 'never awaited' 경고가 진짜 누수를 가린다."""

    async def _closer() -> None:
        return None

    owner = BrowserSessionOwner()
    reservation = owner.begin(_owner())
    lease = owner.commit(reservation, page=_FakePage(), close=cast(Callable[[], object], _closer))

    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        assert owner.release(lease.owner) is True

    assert asyncio.iscoroutinefunction(_closer)
