"""task 17 — 관찰 snapshot·grounded action·결과 증거 계약 시험.

task 16 의 실측이 가짜 페이지로 **소유권**만 쟀다면, 여기서는 **진짜 Chromium** 으로 로컬
fixture 사이트를 관찰하고 조작한다. 요구된 정상 경로(link/form/iframe/popup/download/select)와
실패 경로(DOM 교체·hidden·disabled·타 세션 ref·redirect private·샌드박스 밖 upload·실행 파일
download·크기 초과)를 모두 지난다.

판정 기준은 **행동의 성공이 아니라 계약의 준수**다: ref 는 opaque 하고 snapshot 에 묶이며,
임의 JS/selector 는 문이 없고, `performed` 와 `goal_verified` 는 서로 다른 질문이다.
"""

from __future__ import annotations

import base64
import json
import threading
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, cast
from urllib.parse import urlsplit

import pytest

from antigravity_k.tools.browser_observation import (
    DOWNLOAD_TOO_LARGE,
    DOWNLOAD_TYPE_DENIED,
    ELEMENT_NOT_ACTIONABLE,
    INVALID_ARGUMENT,
    POLICY_DENIED,
    SESSION_MISMATCH,
    STALE_SNAPSHOT,
    UNKNOWN_REF,
    UNSUPPORTED_CAPABILITY,
    BrowserObservationError,
    BrowserObserver,
    ObservationPolicy,
    mask_secret_values,
    safe_filename,
    scrub_input_values,
)
from antigravity_k.tools.browser_session_owner import BrowserOwner

if TYPE_CHECKING:  # pragma: no cover
    from playwright.async_api import Page as _AsyncPage

pytest.importorskip("playwright.async_api")

INDEX_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Fixture Home</title></head>
<body>
  <h1>fixture home</h1>
  <div id="actions">
    <a id="go" href="/page2.html">Next page</a>
    <a id="pop" href="/page2.html" target="_blank">Open popup</a>
    <button id="toggle" onclick="document.getElementById('out').textContent = 'toggled'">Toggle</button>
    <button id="dead">Do nothing</button>
    <button id="hidden" style="display:none">Hidden action</button>
    <button id="dis" disabled>Disabled action</button>
    <select id="pick" aria-label="Pick"><option value="a">A</option><option value="b">B</option></select>
    <a id="dl" href="/file.txt" download>Download file</a>
    <a id="evil" href="/evil.sh" download>Download script</a>
    <a id="big" href="/big.bin" download>Download big</a>
  </div>
  <form id="f" action="/submitted.html" method="get">
    <input id="q" name="q" type="text" placeholder="search">
    <input id="pw" name="pw" type="password" aria-label="Secret">
    <input id="up" name="up" type="file" aria-label="Upload">
    <button id="submit" type="submit" onclick="event.preventDefault(); document.title='submitted'">Submit</button>
  </form>
  <div id="out">initial</div>
  <iframe id="fr" title="embedded" src="/frame.html" width="400" height="200"></iframe>
</body></html>
"""

FRAME_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Fixture Frame</title></head>
<body>
  <button id="fbtn" aria-label="Frame button"
          onclick="document.body.setAttribute('data-clicked','1'); document.title='frame clicked'">Frame button</button>
</body></html>
"""

PAGE2_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Second</title></head><body><h1>second</h1></body></html>
"""


@dataclass(frozen=True)
class _File:
    content_type: str
    body: bytes
    headers: dict[str, str] = field(default_factory=dict)


def _attachment(name: str) -> dict[str, str]:
    return {"Content-Disposition": f'attachment; filename="{name}"'}


FILES: dict[str, _File] = {
    "/index.html": _File("text/html; charset=utf-8", INDEX_HTML.encode("utf-8")),
    "/frame.html": _File("text/html; charset=utf-8", FRAME_HTML.encode("utf-8")),
    "/page2.html": _File("text/html; charset=utf-8", PAGE2_HTML.encode("utf-8")),
    "/submitted.html": _File("text/html; charset=utf-8", b"<html><body><h1>submitted</h1></body></html>"),
    "/file.txt": _File("text/plain", b"hello download\n", _attachment("note.txt")),
    "/evil.sh": _File("application/octet-stream", b"#!/bin/sh\necho pwned\n", _attachment("evil.sh")),
    "/big.bin": _File("application/octet-stream", b"\x00" * 4096, _attachment("big.bin")),
}


# `/redirect-private` 가 향하는 목적지. **연결은 되지만 egress 규칙은 공인으로 보지 않는** 주소라
# (0.0.0.0 은 local allow 목록에 없다) 실제 302·실제 이동·실제 커밋·실제 최종 URL 검사를
# 그대로 재현할 수 있다. 검증기 주입도, 네트워크도 필요 없다.
_REDIRECT_TARGET: dict[str, str] = {"value": ""}


class _SiteHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler 규약
        path = urlsplit(self.path).path
        if path == "/redirect-private":
            self.send_response(302)
            self.send_header("Location", _REDIRECT_TARGET["value"])
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        entry = FILES.get(path)
        if entry is None:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", entry.content_type)
        self.send_header("Content-Length", str(len(entry.body)))
        for key, value in entry.headers.items():
            self.send_header(key, value)
        self.end_headers()
        _ = self.wfile.write(entry.body)

    def log_message(self, *args: object) -> None:  # 시험 로그를 조용히
        return


@dataclass(frozen=True)
class _Site:
    base: str

    def url(self, path: str) -> str:
        return f"{self.base}{path}"


def _serve(host: str) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, 0), _SiteHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture(scope="module")
def site() -> Iterator[_Site]:
    server = _serve("127.0.0.1")
    _, port = cast("tuple[str, int]", server.server_address[:2])
    _REDIRECT_TARGET["value"] = f"http://0.0.0.0:{port}/page2.html"
    try:
        yield _Site(base=f"http://127.0.0.1:{port}")
    finally:
        server.shutdown()
        server.server_close()
        _REDIRECT_TARGET["value"] = ""


@asynccontextmanager
async def _browser() -> AsyncIterator[object]:
    """페이지 팩토리. 시험은 같은 브라우저에서 필요한 만큼 context/page 를 연다."""
    from playwright.async_api import async_playwright

    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True)
    contexts: list[object] = []

    async def new_page() -> _AsyncPage:
        context = await browser.new_context(viewport={"width": 900, "height": 700}, accept_downloads=True)
        contexts.append(context)
        return cast("_AsyncPage", await context.new_page())

    try:
        yield new_page
    finally:
        for context in contexts:
            await context.close()  # type: ignore[attr-defined]
        await browser.close()
        await playwright.stop()


def _observer(
    page: object,
    *,
    owner: BrowserOwner | None = None,
    download_dir: Path | None = None,
    download_max_bytes: int = 32 * 1024 * 1024,
    upload_root: Path | None = None,
    allow_local: bool = True,
    validator: object = None,
) -> BrowserObserver:
    policy = ObservationPolicy(
        allow_local=allow_local,
        download_dir=download_dir,
        download_max_bytes=download_max_bytes,
        upload_root=upload_root,
    )
    observer = BrowserObserver(
        owner or BrowserOwner(subject="task17", scope="fixture"),
        policy=policy,
        validator=validator,  # type: ignore[arg-type]
    )
    observer.register_page(page)
    return observer


async def _open(page: _AsyncPage, site: _Site, path: str = "/index.html") -> None:
    await page.goto(site.url(path), wait_until="load")


def _expect(error: BrowserObservationError) -> tuple[str, bool]:
    return error.code, error.retryable


# ── 기본 계약 ───────────────────────────────────────────────────────────────
def test_policy_defaults_are_closed() -> None:
    """기본값은 **닫혀 있어야** 한다 — 로컬 허용도, 다운로드/업로드 경로도 없다."""
    policy = ObservationPolicy()
    assert policy.allow_local is False
    assert policy.download_dir is None
    assert policy.upload_root is None
    assert policy.block_executable_downloads is True


def test_mask_secret_values_and_safe_filename() -> None:
    assert mask_secret_values("token=hunter2 here", ["hunter2"]) == f"token={'••••'} here"
    # 너무 짧은 값은 부분 일치로 문서를 망치므로 마스킹하지 않는다.
    assert mask_secret_values("a=1", ["1"]) == "a=1"
    assert safe_filename("../../etc/passwd") == "passwd"
    assert safe_filename(".hidden") == "hidden"
    assert safe_filename("") == "download.bin"


def test_scrub_input_values_drops_every_input_value() -> None:
    """접근성 요약은 **값을 나르지 않는다** — 이름이 없는 비밀 필드도 마찬가지다."""
    raw = "\n".join(
        [
            "- form",
            '  - textbox "Secret": hunter2-secret',
            "  - textbox: unnamed-value",
            '  - combobox "Pick": b',
            '  - button "Submit"',
            '  - link "Next": page',
        ]
    )
    scrubbed = scrub_input_values(raw)
    assert "hunter2-secret" not in scrubbed
    assert "unnamed-value" not in scrubbed
    assert '"b"' not in scrubbed.replace('combobox "Pick"', "")
    assert scrubbed.startswith("- form")
    assert '  - textbox "Secret"' in scrubbed
    assert "  - textbox\n" in scrubbed + "\n"
    # 값이 없는 요소는 그대로 남는다(요약이 쓸모없어지지 않는다).
    assert '  - button "Submit"' in scrubbed


# ── 정상 경로(실 Chromium·로컬 fixture) ─────────────────────────────────────
async def test_observation_reports_refs_frames_and_accessibility(site: _Site) -> None:
    async with _browser() as new_page:
        page = await new_page()
        await _open(page, site)
        observer = _observer(page)
        observation = await observer.observe()

        assert observation.generation == 1
        assert observation.snapshot_id
        assert observation.session_tag and observation.url.endswith("/index.html")

        roles = {item.role for item in observation.refs}
        assert {"link", "button", "textbox", "combobox"} <= roles
        names = {item.name for item in observation.refs}
        assert {"Next page", "Toggle", "Pick", "Upload", "Secret"} <= names

        # ref 는 opaque 핸들이다: session 태그 + snapshot + frame 슬러그 + 원시 인덱스.
        for item in observation.refs:
            parts = item.ref.split("-")
            assert len(parts) == 4
            assert parts[0] == observation.session_tag
            assert parts[1] == observation.snapshot_id
            assert parts[3].startswith("e")

        # iframe 은 frame 경로로 식별된다.
        assert {"main", "main>f0"} <= {frame.path for frame in observation.frames}
        frame_refs = [item for item in observation.refs if item.frame != "main"]
        assert [item.name for item in frame_refs] == ["Frame button"]

        # 접근성 요약이 있고, DOM 값이 곧 ref 라는 사실이 요약에도 드러난다.
        assert observation.accessibility and "button" in observation.accessibility
        assert "[mock]" not in observation.to_summary()
        assert observation.to_summary().count("Next page") == 1


async def test_click_link_navigates_and_verifies_the_effect(site: _Site) -> None:
    async with _browser() as new_page:
        page = await new_page()
        await _open(page, site)
        observer = _observer(page)
        observation = await observer.observe()
        ref = observation.ref_for("Next page")
        assert ref is not None

        result = await observer.act("click", ref=ref)
        assert result.performed is True
        assert result.goal_verified is True
        assert result.status == "ok"
        assert result.url_after.endswith("/page2.html")
        assert result.evidence["navigated"] is True
        assert result.snapshot_id == observation.snapshot_id


async def test_fill_form_reads_back_the_value(site: _Site) -> None:
    async with _browser() as new_page:
        page = await new_page()
        await _open(page, site)
        observer = _observer(page)
        observation = await observer.observe()
        ref = observation.ref_for("search")
        assert ref is not None

        result = await observer.act("fill", ref=ref, text="hello world")
        assert result.performed is True
        assert result.goal_verified is True
        assert result.evidence["value_verified"] is True
        assert result.evidence["length"] == len("hello world")


async def test_select_option_verifies_the_selected_value(site: _Site) -> None:
    async with _browser() as new_page:
        page = await new_page()
        await _open(page, site)
        observer = _observer(page)
        observation = await observer.observe()
        ref = observation.ref_for("Pick")
        assert ref is not None

        result = await observer.act("select", ref=ref, value="b")
        assert result.performed is True
        assert result.goal_verified is True
        assert result.evidence["selected"] == "b"


async def test_iframe_element_is_actionable_through_its_frame(site: _Site) -> None:
    async with _browser() as new_page:
        page = await new_page()
        await _open(page, site)
        observer = _observer(page)
        observation = await observer.observe()
        ref = observation.ref_for("Frame button")
        assert ref is not None
        binding = next(item for item in observation.refs if item.ref == ref)
        assert binding.frame == "main>f0"

        result = await observer.act("click", ref=ref)
        assert result.performed is True
        # iframe 안의 DOM 변화가 관측 가능한 효과로 잡힌다.
        assert result.goal_verified is True
        assert await page.frame_locator("#fr").locator("body").get_attribute("data-clicked") == "1"


async def test_popup_is_identified_on_the_next_observation(site: _Site) -> None:
    async with _browser() as new_page:
        page = await new_page()
        await _open(page, site)
        observer = _observer(page)
        observation = await observer.observe()
        # 앞선 행동이 있으면 새 페이지가 **나중에** 뜼다 — 즉시 한 번만 보는 구현은 이 순서에서 놓친다.
        dead = observation.ref_for("Do nothing")
        assert dead is not None
        _ = await observer.act("click", ref=dead)
        observation = await observer.observe()
        ref = observation.ref_for("Open popup")
        assert ref is not None

        result = await observer.act("click", ref=ref)
        assert result.performed is True
        # 팝업은 **새 페이지**를 여는 효과다(현재 페이지의 DOM/URL 은 그대로다).
        assert result.goal_verified is True
        assert result.evidence["opened_pages"]
        assert str(result.evidence["opened_pages"][0]).endswith("/page2.html")

        after = await observer.observe()
        popups = [item for item in after.popups if not item.foreign]
        assert popups and popups[0].url.endswith("/page2.html")
        assert popups[0].key == "popup:0"


async def test_scroll_does_not_consume_the_observation(site: _Site) -> None:
    async with _browser() as new_page:
        page = await new_page()
        await _open(page, site)
        observer = _observer(page)
        observation = await observer.observe()
        ref = observation.ref_for("Next page")
        assert ref is not None

        first = await observer.act("scroll", ref=ref)
        second = await observer.act("scroll", ref=ref)
        assert first.performed is True
        assert second.performed is True
        assert second.status == "ok"


async def test_download_is_saved_to_the_sandbox_without_execute_bits(site: _Site, tmp_path: Path) -> None:
    async with _browser() as new_page:
        page = await new_page()
        await _open(page, site)
        directory = tmp_path / "downloads"
        observer = _observer(page, download_dir=directory)
        observation = await observer.observe()
        ref = observation.ref_for("Download file")
        assert ref is not None

        result = await observer.act("download", ref=ref)
        assert result.performed is True
        assert result.goal_verified is True
        target = directory / str(result.evidence["filename"])
        assert target.exists()
        assert target.stat().st_size == len(b"hello download\n")
        # 데이터이지 프로그램이 아니다 — 실행 비트가 없어야 한다.
        assert (target.stat().st_mode & 0o111) == 0
        assert result.evidence["executable_bits"] is False
        assert result.evidence["sha256"]


# ── 실패 경로 ───────────────────────────────────────────────────────────────
async def test_dom_replacement_rejects_the_stale_ref_then_reobserve_recovers(site: _Site) -> None:
    async with _browser() as new_page:
        page = await new_page()
        await _open(page, site)
        observer = _observer(page)
        observation = await observer.observe()
        ref = observation.ref_for("Toggle")
        assert ref is not None

        # 구조는 같지만 **우리가 표시해 둔 요소는 사라진** 교체.
        _ = await page.evaluate(
            """() => {
              const el = document.getElementById('actions');
              const clone = el.cloneNode(true);
              clone.querySelectorAll('[data-ssak-ref]').forEach((node) => node.removeAttribute('data-ssak-ref'));
              el.replaceWith(clone);
              return true;
            }""",
        )
        with pytest.raises(BrowserObservationError) as info:
            _ = await observer.act("click", ref=ref)
        assert _expect(info.value) == (STALE_SNAPSHOT, True)

        fresh = await observer.observe()
        recovered = fresh.ref_for("Toggle")
        assert recovered is not None
        result = await observer.act("click", ref=recovered)
        assert result.performed is True
        assert result.goal_verified is True


async def test_hidden_element_is_not_observable_and_becoming_hidden_blocks(site: _Site) -> None:
    async with _browser() as new_page:
        page = await new_page()
        await _open(page, site)
        observer = _observer(page)
        observation = await observer.observe()

        # 숨은 요소는 관찰 자체에 없다 — ref 를 발급하지 않으므로 조작할 문도 없다.
        assert observation.ref_for("Hidden action") is None

        ref = observation.ref_for("Toggle")
        assert ref is not None
        _ = await page.evaluate("() => { document.getElementById('toggle').style.display = 'none'; }")
        with pytest.raises(BrowserObservationError) as info:
            _ = await observer.act("click", ref=ref)
        assert _expect(info.value) == (ELEMENT_NOT_ACTIONABLE, True)


async def test_disabled_element_is_observed_but_not_actionable(site: _Site) -> None:
    async with _browser() as new_page:
        page = await new_page()
        await _open(page, site)
        observer = _observer(page)
        observation = await observer.observe()
        disabled = [item for item in observation.refs if item.disabled]
        assert [item.name for item in disabled] == ["Disabled action"]
        assert disabled[0].actionable is False

        with pytest.raises(BrowserObservationError) as info:
            _ = await observer.act("click", ref=disabled[0].ref)
        assert info.value.code == ELEMENT_NOT_ACTIONABLE


async def test_generation_advances_on_significant_dom_change(site: _Site) -> None:
    async with _browser() as new_page:
        page = await new_page()
        await _open(page, site)
        observer = _observer(page)
        first = await observer.observe()
        same = await observer.observe()
        # 아무것도 변하지 않았으면 같은 관찰을 재사용한다(ref 가 살아 있다).
        assert same.snapshot_id == first.snapshot_id
        assert same.generation == first.generation

        ref = first.ref_for("Next page")
        assert ref is not None
        _ = await page.evaluate(
            "() => { const b = document.createElement('button');"
            " b.textContent = 'Appeared'; document.getElementById('actions').appendChild(b); }",
        )
        second = await observer.observe()
        assert second.generation == first.generation + 1
        assert second.snapshot_id != first.snapshot_id
        with pytest.raises(BrowserObservationError) as info:
            _ = await observer.act("click", ref=ref)
        assert _expect(info.value) == (STALE_SNAPSHOT, True)


async def test_one_observation_authorizes_one_action(site: _Site) -> None:
    async with _browser() as new_page:
        page = await new_page()
        await _open(page, site)
        observer = _observer(page)
        observation = await observer.observe()
        ref = observation.ref_for("Do nothing")
        assert ref is not None

        first = await observer.act("click", ref=ref)
        assert first.performed is True
        with pytest.raises(BrowserObservationError) as info:
            _ = await observer.act("click", ref=ref)
        assert _expect(info.value) == (STALE_SNAPSHOT, True)


async def test_ref_from_another_session_is_rejected(site: _Site) -> None:
    async with _browser() as new_page:
        page_a = await new_page()
        page_b = await new_page()
        await _open(page_a, site)
        await _open(page_b, site)
        session_a = _observer(page_a, owner=BrowserOwner(subject="task17", scope="session-a"))
        session_b = _observer(page_b, owner=BrowserOwner(subject="task17", scope="session-b"))
        observation_a = await session_a.observe()
        observation_b = await session_b.observe()
        assert observation_a.session_tag != observation_b.session_tag

        with pytest.raises(BrowserObservationError) as info:
            _ = await session_b.act("click", ref=observation_a.ref_for("Next page"))
        assert info.value.code == SESSION_MISMATCH


async def test_arbitrary_js_and_selectors_are_not_exposed(site: _Site) -> None:
    async with _browser() as new_page:
        page = await new_page()
        await _open(page, site)
        observer = _observer(page)
        observation = await observer.observe()

        for forbidden in ("evaluate", "query_selector", "add_script_tag", "dispatch_event"):
            with pytest.raises(BrowserObservationError) as info:
                _ = await observer.act(forbidden)
            assert info.value.code == UNSUPPORTED_CAPABILITY

        # 뒤의 둘은 **ref 처럼 보이게 만든 selector** 다 — 형식 검사(대시 4조각)만 있으면
        # 통과해서 SESSION_MISMATCH 로 새어 나간다. 거절 이유는 'ref 가 아니다' 여야 한다.
        for selector_shaped in (
            "#submit",
            "button.submit",
            "//button",
            "text=Submit",
            "div > button",
            "#go-1-2-3",
            "text=a-b-c-x",
        ):
            with pytest.raises(BrowserObservationError) as info:
                _ = await observer.act("click", ref=selector_shaped)
            assert info.value.code == INVALID_ARGUMENT, selector_shaped
        assert observation.ref_for("Next page") is not None


async def test_well_formed_ref_that_was_never_issued_is_unknown(site: _Site) -> None:
    """형식이 맞아도 **이 관찰이 발급한 적 없는** ref 는 거절된다(registry 가 유일한 근거다)."""
    async with _browser() as new_page:
        page = await new_page()
        await _open(page, site)
        observer = _observer(page)
        observation = await observer.observe()
        forged = f"{observation.session_tag}-{observation.snapshot_id}-dead-e99"
        assert forged not in observation.ref_tokens()
        with pytest.raises(BrowserObservationError) as info:
            _ = await observer.act("click", ref=forged)
        assert info.value.code == UNKNOWN_REF

        # 같은 표식이 두 요소에 붙으면 계약은 '모호하다'고 거절한다(아무거나 누르지 않는다).
        ref = observation.ref_for("Toggle")
        assert ref is not None
        marker = ref.split("-")[3].lstrip("e")
        _ = await page.evaluate(
            "(marker) => document.getElementById('dead').setAttribute('data-ssak-ref', marker)",
            marker,
        )
        with pytest.raises(BrowserObservationError) as info:
            _ = await observer.act("click", ref=ref)
        assert info.value.code == ELEMENT_NOT_ACTIONABLE


async def test_page_scroll_is_verified_by_actual_movement() -> None:
    """페이지 스크롤도 `performed` 와 `goal_verified` 가 갈린다(움직이지 않으면 검증 실패)."""
    async with _browser() as new_page:
        page = await new_page()
        await page.set_content("<html><body style='height:3000px'><p>tall document</p></body></html>")
        observer = _observer(page)
        moved = await observer.act("scroll", delta=600)
        assert moved.performed is True
        assert moved.goal_verified is True
        assert int(cast("int", moved.evidence["offset_after"])) > int(cast("int", moved.evidence["offset_before"]))

        await page.set_content("<html><body><p>short document</p></body></html>")
        blocked = await observer.act("scroll", delta=600)
        assert blocked.performed is True
        assert blocked.goal_verified is False
        assert blocked.status == "partial"
        assert blocked.evidence["offset_after"] == blocked.evidence["offset_before"]


async def test_goto_rejects_a_local_target_when_local_is_disabled(site: _Site) -> None:
    async with _browser() as new_page:
        page = await new_page()
        await _open(page, site)
        observer = _observer(page, allow_local=False)
        with pytest.raises(BrowserObservationError) as info:
            _ = await observer.act("goto", url=site.url("/index.html"))
        assert info.value.code == POLICY_DENIED


async def test_goto_rechecks_the_final_url_after_a_redirect(site: _Site) -> None:
    """리다이렉트가 정책 밖 주소로 데려가면 **최종 URL** 검사가 잡는다(요청 URL 만 보면 통과한다).

    실제 HTTP 302 + 실제 이동 + 실제 커밋을 지나므로, "요청 주소만 검사해서 통과" 하는 구현은
    이 시험에서 초록이 될 수 없다.
    """
    async with _browser() as new_page:
        page = await new_page()
        observer = _observer(page)
        requested = site.url("/redirect-private")
        with pytest.raises(BrowserObservationError) as info:
            _ = await observer.act("goto", url=requested)
        assert info.value.code == POLICY_DENIED
        assert "disallowed" in str(info.value)
        # 거절된 주소는 요청 URL 이 아니라 **최종 URL** 이다(0.0.0.0 은 연결되지만 local allow 밖).
        assert "0.0.0.0" in str(info.value)
        assert "127.0.0.1" not in str(info.value)
        assert page.url.startswith("http://0.0.0.0")


async def test_upload_outside_the_sandbox_is_denied_and_inside_is_accepted(site: _Site, tmp_path: Path) -> None:
    async with _browser() as new_page:
        page = await new_page()
        await _open(page, site)
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        allowed = sandbox / "ok.txt"
        allowed.write_text("payload", encoding="utf-8")
        outside = tmp_path / "outside.txt"
        outside.write_text("nope", encoding="utf-8")
        observer = _observer(page, upload_root=sandbox)
        observation = await observer.observe()
        ref = observation.ref_for("Upload")
        assert ref is not None

        with pytest.raises(BrowserObservationError) as info:
            _ = await observer.act("upload", ref=ref, path=str(outside))
        assert info.value.code == POLICY_DENIED

        # 거절된 행동은 관찰을 소비하지 않는다 — 같은 ref 로 다시 시도할 수 있다.
        result = await observer.act("upload", ref=ref, path=str(allowed))
        assert result.performed is True
        assert result.goal_verified is True
        assert result.evidence["files_seen"] == 1
        assert result.evidence["filename"] == "ok.txt"


async def test_upload_without_a_sandbox_is_refused(site: _Site, tmp_path: Path) -> None:
    async with _browser() as new_page:
        page = await new_page()
        await _open(page, site)
        source = tmp_path / "any.txt"
        source.write_text("x", encoding="utf-8")
        observer = _observer(page)
        observation = await observer.observe()
        ref = observation.ref_for("Upload")
        assert ref is not None
        with pytest.raises(BrowserObservationError) as info:
            _ = await observer.act("upload", ref=ref, path=str(source))
        assert info.value.code == POLICY_DENIED


async def test_download_of_an_executable_payload_is_refused_and_removed(site: _Site, tmp_path: Path) -> None:
    async with _browser() as new_page:
        page = await new_page()
        await _open(page, site)
        directory = tmp_path / "downloads"
        observer = _observer(page, download_dir=directory)
        observation = await observer.observe()
        ref = observation.ref_for("Download script")
        assert ref is not None

        with pytest.raises(BrowserObservationError) as info:
            _ = await observer.act("download", ref=ref)
        assert info.value.code == DOWNLOAD_TYPE_DENIED
        assert not directory.exists() or not list(directory.iterdir())


async def test_download_over_the_size_limit_is_discarded(site: _Site, tmp_path: Path) -> None:
    async with _browser() as new_page:
        page = await new_page()
        await _open(page, site)
        directory = tmp_path / "downloads"
        observer = _observer(page, download_dir=directory, download_max_bytes=64)
        observation = await observer.observe()
        ref = observation.ref_for("Download big")
        assert ref is not None

        with pytest.raises(BrowserObservationError) as info:
            _ = await observer.act("download", ref=ref)
        assert info.value.code == DOWNLOAD_TOO_LARGE
        assert not list(directory.iterdir())


async def test_download_without_a_sandbox_is_refused(site: _Site) -> None:
    async with _browser() as new_page:
        page = await new_page()
        await _open(page, site)
        observer = _observer(page)
        observation = await observer.observe()
        ref = observation.ref_for("Download file")
        assert ref is not None
        with pytest.raises(BrowserObservationError) as info:
            _ = await observer.act("download", ref=ref)
        assert info.value.code == POLICY_DENIED


async def test_click_with_no_effect_is_performed_but_not_verified(site: _Site) -> None:
    async with _browser() as new_page:
        page = await new_page()
        await _open(page, site)
        observer = _observer(page)
        observation = await observer.observe()
        ref = observation.ref_for("Do nothing")
        assert ref is not None

        result = await observer.act("click", ref=ref)
        assert result.performed is True
        assert result.goal_verified is False
        assert result.status == "partial"
        assert result.evidence["navigated"] is False
        assert result.evidence["dom_changed"] is False


async def test_secret_fill_is_masked_in_the_next_observation_and_screenshot(site: _Site) -> None:
    secret = "hunter2-secret"
    async with _browser() as new_page:
        page = await new_page()
        await _open(page, site)
        observer = _observer(page)
        observation = await observer.observe()
        ref = observation.ref_for("Secret")
        assert ref is not None
        binding = next(item for item in observation.refs if item.ref == ref)
        assert binding.secret is True

        filled = await observer.act("fill", ref=ref, text=secret)
        assert filled.performed is True
        assert filled.evidence["secret"] is True
        # 비밀 필드는 원문을 되읽지 않는다 — 길이로만 확인한다.
        assert filled.evidence["value_verified"] is True
        assert secret not in json.dumps(filled.to_dict(), ensure_ascii=False)

        # **다른 경로로 들어온 비밀**도 새지 않아야 한다(우리가 fill 한 값만 마스킹하면 구멍이 남는다).
        await page.fill("#pw", "typed-by-someone-else")
        # 커서깜박임이 두 캡처를 다르게 만들면 픽셀 비교가 아무것도 재지 못한다 — 먼저 초점을 뺘다.
        _ = await page.evaluate("() => (document.activeElement ? document.activeElement.blur() : null)")
        unmasked = await page.screenshot()
        after = await observer.observe(screenshot=True)
        assert after.screenshot_masked is True
        assert after.masked_regions >= 1
        masked = base64.b64decode(str(after.screenshot))
        assert masked != unmasked, "비밀 필드를 덮었는데 스크린샷이 같다"
        # 같은 화면을 두 번 찍으면 같아야 한다 — 위 비교가 우연이 아님을 확인한다(대조군).
        assert unmasked == await page.screenshot()
        payload = json.dumps(after.to_dict(), ensure_ascii=False)
        assert secret not in payload
        assert "typed-by-someone-else" not in payload
        # 덮개는 관찰이 끝나면 치운다(화면을 영구히 가리지 않는다).
        assert await page.evaluate("() => document.getElementById('__ssak_secret_mask__') === null") is True


async def test_vision_agent_decides_with_a_ref_not_a_selector() -> None:
    """vision 모델의 클릭 대상은 ref 다(프롬프트와 응답 파싱이 같은 말을 해야 한다)."""
    from unittest.mock import AsyncMock, MagicMock

    from antigravity_k.agents.browser_surfing_agent import BrowserAction, BrowserSurfingAgent

    manager = MagicMock()
    response = MagicMock()
    response.text = '{"action": "click", "ref": "abcdef-1234abcd-e0", "reason": "next"}'
    manager.generate = AsyncMock(return_value=response)
    agent = BrowserSurfingAgent(model_manager=manager)

    action = await agent._decide_next_action("goal", "summary", b"")  # noqa: SLF001
    assert action == BrowserAction(action="click", target_ref="abcdef-1234abcd-e0", reason="next")
    assert not hasattr(action, "target_selector")

    prompt = str(cast("MagicMock", manager.generate).await_args.kwargs["prompt"])
    assert '"ref"' in prompt
    assert "target_selector" not in prompt
    assert "selector·XPath·JavaScript 는 받아들여지지 않습니다" in prompt


async def test_source_gate_the_vision_agent_has_no_selector_click_path() -> None:
    """모델이 selector 를 지어내 클릭하는 문이 남아 있으면 계약이 아니다(소스 게이트)."""
    source = Path("src/antigravity_k/agents/browser_surfing_agent.py").read_text(encoding="utf-8")
    assert "target_selector" not in source
    assert "page.click(" not in source
    assert "browser_observation" in source


# ── API 경로(라우트 → 소유자 lease → 관찰자 → 실제 브라우저) ──────────────────
def _api_headers(session_id: str) -> dict[str, str]:
    from antigravity_k.config import config

    headers = {"X-AGK-Browser-Session": session_id}
    if config.security.access_pin:
        headers["X-Access-Pin"] = config.security.access_pin
    return headers


def _session_key(session_id: str) -> str:
    import hashlib as _hashlib

    from antigravity_k.config import config

    subject = "pin-user" if config.security.access_pin else "loopback"
    return _hashlib.sha256(f"{subject}:{session_id}".encode("utf-8")).hexdigest()


def test_api_observe_and_grounded_click_round_trip(site: _Site, monkeypatch: pytest.MonkeyPatch) -> None:
    """API 로도 같은 계약을 지닌다: launch → observe → goto → click(ref) → 낡은 ref 409."""
    monkeypatch.setenv("AGK_BROWSER_API_ALLOW_LOCAL", "1")
    from fastapi.testclient import TestClient

    from antigravity_k.api.routes import agent_tools
    from antigravity_k.api.server import app

    session_id = "task17-api"
    headers = _api_headers(session_id)
    url = "/api/agent/tools/browser/action"
    try:
        with TestClient(app) as client:
            launched = client.post(url, json={"action": "launch"}, headers=headers)
            assert launched.status_code == 200, launched.text

            first = client.post(url, json={"action": "observe"}, headers=headers)
            assert first.status_code == 200, first.text
            observation = first.json()["observation"]
            assert observation["schema"] == "ssak.browser.observation/1.0"
            assert observation["generation"] == 1
            assert "summary" in first.json()

            moved = client.post(url, json={"action": "goto", "url": site.url("/index.html")}, headers=headers)
            assert moved.status_code == 200, moved.text
            assert moved.json()["result"]["goal_verified"] is True

            second = client.post(url, json={"action": "observe"}, headers=headers)
            assert second.status_code == 200, second.text
            refs = second.json()["observation"]["refs"]
            ref = next(item["ref"] for item in refs if item["name"] == "Next page")

            clicked = client.post(url, json={"action": "click", "ref": ref}, headers=headers)
            assert clicked.status_code == 200, clicked.text
            assert clicked.json()["result"]["goal_verified"] is True
            assert clicked.json()["result"]["url_after"].endswith("/page2.html")

            # 계약에 없는 행동은 문이 없다.
            forbidden = client.post(url, json={"action": "evaluate"}, headers=headers)
            assert forbidden.status_code == 400
            # 소진된 ref 는 409 + 재관찰 안내다(같은 관찰로 두 번 행동할 수 없다).
            stale = client.post(url, json={"action": "click", "ref": ref}, headers=headers)
            assert stale.status_code == 409
            assert stale.json()["detail"]["code"] == "STALE_SNAPSHOT"
            assert stale.json()["detail"]["retryable"] is True
            # selector 를 ref 자리에 넣으면 계약이 거부한다(환각 우회 금지).
            selector_shaped = client.post(url, json={"action": "click", "ref": "#go"}, headers=headers)
            assert selector_shaped.status_code == 400
            assert selector_shaped.json()["detail"]["code"] == "INVALID_ARGUMENT"

            assert client.post(url, json={"action": "close"}, headers=headers).status_code == 200
    finally:
        _ = agent_tools.browser_sessions.discard(_session_key(session_id))


def test_api_rejects_local_navigation_unless_explicitly_enabled(site: _Site) -> None:
    """기본값은 닫힘 — API 가 로컬 주소를 두드리려면 운영자가 명시해야 한다."""
    from fastapi.testclient import TestClient

    from antigravity_k.api.routes import agent_tools
    from antigravity_k.api.server import app

    session_id = "task17-api-local"
    headers = _api_headers(session_id)
    url = "/api/agent/tools/browser/action"
    try:
        with TestClient(app) as client:
            launched = client.post(url, json={"action": "launch"}, headers=headers)
            assert launched.status_code == 200, launched.text
            blocked = client.post(url, json={"action": "goto", "url": site.url("/index.html")}, headers=headers)
            assert blocked.status_code == 403, blocked.text
            assert blocked.json()["detail"]["code"] == "POLICY_DENIED"
            assert client.post(url, json={"action": "close"}, headers=headers).status_code == 200
    finally:
        _ = agent_tools.browser_sessions.discard(_session_key(session_id))
