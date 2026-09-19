"""브라우저 관찰(snapshot)과 grounded action 계약 — task 17.

**모델은 보는 것만 조작한다.** 관찰이 돌려준 opaque `ref` 만 행동의 대상이 될 수 있고,
CSS selector·XPath·임의 JS 는 계약에 아예 없다 — 환각으로 우회할 문을 만들지 않는 것이
이 모듈의 목적이다. `ref` 는 `session + snapshot + generation` 에 묶여 있어, 페이지가
바뀌면 낡은 ref 는 **거절되고 재관찰**을 요구한다.

계약(요약):

- 관찰은 `session_tag`·`snapshot_id`·`generation`·`url`·`captured_at`·refs·접근성 요약·
  (명시 요청 시) 마스킹한 스크린샷을 준다. DOM/접근성 요약이 기본이고 스크린샷은 부가다.
- iframe 은 **frame 경로**로, popup 은 **식별해서** 알려 준다. 우리가 열지 않은 페이지
  (개인 Chrome/CDP)는 `foreign=True` 로 표시하고 ref 를 발급하지 않는다.
- 행동은 `goto`/`click`/`fill`/`scroll`/`select`/`upload`/`download` **7종으로 제한**한다.
  (`scroll` 은 ref 를 주면 그 요소를 보이게 하고, ref 없이 `delta` 를 주면 페이지를 그만큼 움직인다.)
  `evaluate`·`query_selector`·`add_script_tag` 같은 것은 `UNSUPPORTED_CAPABILITY` 로 거절한다.
- 권한은 도구 이름이 아니라 **실제 동작·목적지·입력 데이터**로 판정한다: `goto` 는 egress 를
  통과한 뒤 **최종 URL** 까지 다시 검사한다(차단은 라우트 가드가 하고, 여기 검사는 가드를
  지나친 이동을 조용한 성공이 아니라 `POLICY_DENIED` 로 만든다),
  업로드는 샌드박스 밖 경로를 거절하며, 다운로드는 크기·형식 제한을 지키고 **실행 권한을 주지 않는다**.
- 결과는 `performed`(행동했다)와 `goal_verified`(의도한 효과를 **따로 확인**했다)를 구분한다.
  버튼을 눌렀지만 아무 일도 일어나지 않았으면 `performed=True, goal_verified=False` 다.
- 스크린샷은 비밀 필드를 **덮어서** 찍는다(`screenshot_masked`). 관찰 텍스트에서도 우리가 아는
  비밀 문자열은 지운다(`fill` 로 넣은 값은 페이지를 떠나지 않는 대신, 이후 관찰에서 마스킹된다).
- 한 관찰은 **한 번의 행동**을 위한 것이다. 행동은 페이지를 바꿨을 수 있으므로 같은 snapshot 의
  ref 로 다시 행동하면 `STALE_SNAPSHOT` 이고, 다시 관찰해야 한다(읽기 성격인 `scroll` 은 예외).

오류 코드는 공통 결과 계약(v1)과 맞물린다: `POLICY_DENIED`(egress/샌드박스),
`UNSUPPORTED_CAPABILITY`(임의 JS), `INVALID_ARGUMENT`(ref 형식·인자), `STALE_SNAPSHOT`(낡은
관찰), 그리고 브라우저 고유의 `UNKNOWN_REF`·`SESSION_MISMATCH`·`ELEMENT_NOT_ACTIONABLE`·
`DOWNLOAD_TOO_LARGE`·`DOWNLOAD_TYPE_DENIED`.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol, cast
from uuid import uuid4

from antigravity_k.tools.browser_session_owner import BrowserOwner, current_browser_owner

if TYPE_CHECKING:  # pragma: no cover - 정적 분석 전용
    from antigravity_k.tools.browser_session_owner import BrowserLease

logger = logging.getLogger(__name__)

OBSERVATION_SCHEMA: Final = "ssak.browser.observation/1.0"
ACTION_SCHEMA: Final = "ssak.browser.action/1.0"

# ── 오류 코드 ────────────────────────────────────────────────────────────────
STALE_SNAPSHOT: Final = "STALE_SNAPSHOT"
UNKNOWN_REF: Final = "UNKNOWN_REF"
SESSION_MISMATCH: Final = "SESSION_MISMATCH"
ELEMENT_NOT_ACTIONABLE: Final = "ELEMENT_NOT_ACTIONABLE"
UNSUPPORTED_CAPABILITY: Final = "UNSUPPORTED_CAPABILITY"
INVALID_ARGUMENT: Final = "INVALID_ARGUMENT"
POLICY_DENIED: Final = "POLICY_DENIED"
DOWNLOAD_TOO_LARGE: Final = "DOWNLOAD_TOO_LARGE"
DOWNLOAD_TYPE_DENIED: Final = "DOWNLOAD_TYPE_DENIED"

ALLOWED_ACTIONS: Final = frozenset({"goto", "click", "fill", "scroll", "select", "upload", "download"})

# 모델이 시도하기 쉬운 "탈출구". 계약에 없으면 그 이유를 밝혀 거절한다 —
# 조용히 다른 일을 하거나 selector 로 대충 처리하지 않는다.
FORBIDDEN_ACTIONS: Final = frozenset(
    {
        "evaluate",
        "evaluate_handle",
        "query_selector",
        "query_selector_all",
        "add_script_tag",
        "add_style_tag",
        "set_content",
        "dispatch_event",
        "expose_function",
        "route",
    }
)

# ref 처럼 보이지 않는 입력(selector·XPath·URL·JS)은 ref 가 아니다.
_SELECTOR_SHAPED: Final = re.compile(
    r"(^\s*[#.\[])|(//)|(\s)|((css|text|xpath|role|js)=)|(=>)|(document\.)|(javascript:)|[<>+]",
)

MAX_ELEMENTS_PER_FRAME: Final = 60
MAX_ELEMENTS_TOTAL: Final = 120
MAX_NAME_CHARS: Final = 120
MAX_VALUE_CHARS: Final = 80
MAX_ACCESSIBILITY_CHARS: Final = 4000
MAX_SECRETS_REMEMBERED: Final = 32
MAX_KEPT_SNAPSHOTS: Final = 8
MASK: Final = "••••"

DEFAULT_DOWNLOAD_MAX_BYTES: Final = 32 * 1024 * 1024
DEFAULT_UPLOAD_MAX_BYTES: Final = 32 * 1024 * 1024

# 실행 파일로 이어지는 형식은 받지 않는다(다운로드는 데이터이지 프로그램이 아니다).
_BLOCKED_SUFFIXES: Final = frozenset(
    {
        ".app",
        ".bat",
        ".cmd",
        ".com",
        ".command",
        ".dll",
        ".dmg",
        ".exe",
        ".jar",
        ".msi",
        ".pkg",
        ".ps1",
        ".run",
        ".scr",
        ".sh",
        ".so",
        ".vbs",
        ".workflow",
        ".zsh",
    }
)
_BLOCKED_MAGIC: Final = (
    b"MZ",  # PE/DOS
    b"\x7fELF",  # ELF
    b"\xca\xfe\xba\xbe",  # Mach-O fat
    b"\xcf\xfa\xed\xfe",  # Mach-O 64
    b"\xce\xfa\xed\xfe",  # Mach-O 32
    b"#!",  # 스크립트 shebang
)


class BrowserObservationError(RuntimeError):
    """관찰/행동 계약 위반. `code` 는 공통 결과 계약의 오류 코드다."""

    def __init__(self, code: str, message: str, *, retryable: bool = False, stage: str = "observe") -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.stage = stage

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code, "message": str(self), "retryable": self.retryable, "stage": self.stage}


# ── 페이지 최소 계약(런타임에 playwright 를 import 하지 않는다) ──────────────────
class _LocatorLike(Protocol):
    def count(self) -> object: ...
    def is_visible(self) -> object: ...
    def is_enabled(self) -> object: ...


class _FrameLike(Protocol):
    @property
    def child_frames(self) -> Sequence[object]: ...
    def evaluate(self, expression: str, arg: object = None) -> object: ...
    def locator(self, selector: str) -> object: ...


class _PageLike(Protocol):
    @property
    def url(self) -> str: ...
    @property
    def context(self) -> object: ...
    @property
    def main_frame(self) -> object: ...
    def title(self) -> object: ...
    def screenshot(self, **kwargs: object) -> object: ...
    def goto(self, url: str, **kwargs: object) -> object: ...
    def wait_for_load_state(self, state: str | None = None, **kwargs: object) -> object: ...


async def _maybe_await(value: object) -> object:
    """playwright async API 는 async 지만 시험용 가짜 페이지는 동기일 수 있다 — 둘 다 받는다."""
    if hasattr(value, "__await__"):
        return await cast("Awaitable[object]", value)
    return value


async def _call(target: object, name: str, *args: object, **kwargs: object) -> object:
    method = getattr(target, name, None)
    if not callable(method):
        raise BrowserObservationError(UNSUPPORTED_CAPABILITY, f"page object has no '{name}'", stage="observe")
    return await _maybe_await(method(*args, **kwargs))


# ── 수집 스크립트 ────────────────────────────────────────────────────────────
_COLLECT_JS = """
(() => {
  const MAX = %MAX%;
  const CANDIDATES = 'a[href], button, input, select, textarea, summary, [role], [contenteditable="true"], [tabindex]';
  document.querySelectorAll('[data-ssak-ref]').forEach((el) => el.removeAttribute('data-ssak-ref'));
  const roleOf = (el, tag) => {
    const explicit = (el.getAttribute('role') || '').trim();
    if (explicit) return explicit;
    const map = {a: 'link', button: 'button', input: 'textbox', select: 'combobox',
                 textarea: 'textbox', summary: 'button', option: 'option'};
    return map[tag] || tag;
  };
  const out = [];
  const nodes = document.querySelectorAll(CANDIDATES);
  for (let i = 0; i < nodes.length && out.length < MAX; i++) {
    const el = nodes[i];
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    const visible = style.visibility !== 'hidden' && style.display !== 'none'
      && !(rect.width === 0 && rect.height === 0);
    if (!visible) continue;
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute('type') || '').toLowerCase();
    const secret = type === 'password' || el.hasAttribute('data-ssak-secret');
    const disabled = el.disabled === true || el.getAttribute('aria-disabled') === 'true';
    let name = (el.getAttribute('aria-label') || '').trim();
    if (!name) name = (el.innerText || '').trim().split('\\n')[0];
    if (!name) {
      name = (el.getAttribute('title') || el.getAttribute('placeholder') || el.getAttribute('alt') || '').trim();
    }
    if (!name && type) name = type;
    let value = '';
    let filled = false;
    if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement || el instanceof HTMLSelectElement) {
      const raw = typeof el.value === 'string' ? el.value : '';
      filled = raw.length > 0;
      // 비밀 필드의 **원문은 페이지를 떠나지 않는다** — 있는지 여부만 알린다.
      value = secret ? '' : raw.slice(0, %VALUE%);
    }
    const marker = String(out.length);
    el.setAttribute('data-ssak-ref', marker);
    out.push({ref: marker, tag, role: roleOf(el, tag), name: name.slice(0, %NAME%), type,
              secret, disabled, filled, value, actionable: !disabled});
  }
  return out;
})()
"""

_SECRET_BOXES_JS = """
(() => {
  const out = [];
  for (const el of document.querySelectorAll('input[type="password"], [data-ssak-secret]')) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    out.push({x: r.x, y: r.y, w: r.width, h: r.height});
  }
  return out;
})()
"""

_FRAME_RECTS_JS = """
(() => Array.from(document.querySelectorAll('iframe, frame')).map((el) => {
  const r = el.getBoundingClientRect();
  return {x: r.x, y: r.y};
}))()
"""

_CONTENT_JS = """
(() => {
  const root = document.documentElement;
  if (!root) return {nodes: 0, hash: 0};
  let nodes = 0;
  let hash = 0;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
  let node = walker.nextNode();
  while (node && nodes < 4000) {
    nodes++;
    if (node.nodeType === 1) {
      hash = (hash * 31 + node.tagName.length) | 0;
      const attrs = node.attributes;
      for (let i = 0; i < attrs.length; i++) {
        const name = attrs[i].name;
        // 우리 표식과 style 은 **내용이 아니다** — 관찰/행동이 스스로 만든 변화를
        // '효과' 로 세면 performed 와 goal_verified 를 구분하는 의미가 사라진다.
        if (name === 'data-ssak-ref' || name === 'style') continue;
        hash = (hash * 31 + name.length) | 0;
        hash = (hash * 31 + String(attrs[i].value).length) | 0;
      }
    } else {
      const value = (node.nodeValue || '').slice(0, 64);
      for (let i = 0; i < value.length; i++) hash = (hash * 31 + value.charCodeAt(i)) | 0;
    }
    node = walker.nextNode();
  }
  return {nodes, hash};
})()
"""

_MASK_OVERLAY_JS = """
((boxes) => {
  const id = '__ssak_secret_mask__';
  const existing = document.getElementById(id);
  if (existing) existing.remove();
  const layer = document.createElement('div');
  layer.id = id;
  layer.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:2147483647';
  for (const b of boxes) {
    const cover = document.createElement('div');
    cover.style.cssText = 'position:fixed;background:#111;pointer-events:none';
    cover.style.left = b.x + 'px';
    cover.style.top = b.y + 'px';
    cover.style.width = b.w + 'px';
    cover.style.height = b.h + 'px';
    layer.appendChild(cover);
  }
  document.documentElement.appendChild(layer);
  return layer.childElementCount;
})
"""

_UNMASK_OVERLAY_JS = (
    "(() => { const el = document.getElementById('__ssak_secret_mask__'); if (el) el.remove(); return true; })()"
)

_COLLECT_SCRIPT: Final = (
    _COLLECT_JS.replace("%MAX%", str(MAX_ELEMENTS_PER_FRAME))
    .replace("%VALUE%", str(MAX_VALUE_CHARS))
    .replace("%NAME%", str(MAX_NAME_CHARS))
)


# ── 값 객체 ─────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ElementRef:
    """관찰이 발급한 opaque 핸들. selector 가 아니고, 다른 session 에서 쓸 수 없다."""

    ref: str
    role: str
    name: str
    tag: str
    frame: str
    actionable: bool = True
    disabled: bool = False
    secret: bool = False
    filled: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "ref": self.ref,
            "role": self.role,
            "name": self.name,
            "tag": self.tag,
            "frame": self.frame,
            "actionable": self.actionable,
            "disabled": self.disabled,
            "secret": self.secret,
            "filled": self.filled,
        }


@dataclass(frozen=True)
class FrameInfo:
    path: str
    url: str

    def to_dict(self) -> dict[str, object]:
        return {"path": self.path, "url": self.url}


@dataclass(frozen=True)
class PopupInfo:
    key: str
    url: str
    foreign: bool

    def to_dict(self) -> dict[str, object]:
        return {"key": self.key, "url": self.url, "foreign": self.foreign}


@dataclass(frozen=True)
class Observation:
    session_tag: str
    snapshot_id: str
    generation: int
    page_key: str
    url: str
    title: str
    captured_at: str
    refs: tuple[ElementRef, ...] = ()
    frames: tuple[FrameInfo, ...] = ()
    popups: tuple[PopupInfo, ...] = ()
    accessibility: str | None = None
    screenshot: str | None = None
    screenshot_masked: bool = False
    masked_regions: int = 0
    warnings: tuple[str, ...] = ()
    schema: str = OBSERVATION_SCHEMA

    def ref_tokens(self) -> frozenset[str]:
        return frozenset(item.ref for item in self.refs)

    def ref_for(self, name: str) -> str | None:
        """이름으로 ref 를 찾는 **편의**(시험·하네스용). 계약 판정에는 쓰지 않는다."""
        for item in self.refs:
            if item.name == name:
                return item.ref
        return None

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "session_tag": self.session_tag,
            "snapshot_id": self.snapshot_id,
            "generation": self.generation,
            "page": self.page_key,
            "url": self.url,
            "title": self.title,
            "captured_at": self.captured_at,
            "refs": [item.to_dict() for item in self.refs],
            "frames": [item.to_dict() for item in self.frames],
            "popups": [item.to_dict() for item in self.popups],
            "accessibility": self.accessibility,
            "screenshot_base64": self.screenshot,
            "screenshot_masked": self.screenshot_masked,
            "masked_regions": self.masked_regions,
            "warnings": list(self.warnings),
        }

    def to_summary(self) -> str:
        """모델에게 주는 compact 텍스트. ref 가 유일한 조작 수단임이 드러나게 쓴다."""
        lines = [f"url: {self.url}", f"title: {self.title}", f"generation: {self.generation}"]
        if len(self.frames) > 1:
            lines.append("frames: " + ", ".join(f"{item.path}={item.url}" for item in self.frames))
        if self.popups:
            lines.append(
                "popups: "
                + ", ".join(f"{item.key}{'(foreign)' if item.foreign else ''}={item.url}" for item in self.popups)
            )
        for item in self.refs:
            flags = "".join(
                [
                    " disabled" if item.disabled else "",
                    " secret" if item.secret else "",
                    " filled" if item.filled else "",
                ]
            )
            lines.append(f'[{item.ref}] {item.role} "{item.name}"{flags}')
        return "\n".join(lines)


@dataclass(frozen=True)
class ActionResult:
    """`performed`(행동했다)와 `goal_verified`(효과를 확인했다)는 **다른 질문**이다."""

    action: str
    performed: bool
    goal_verified: bool
    detail: str
    ref: str | None
    snapshot_id: str
    generation: int
    url_before: str
    url_after: str
    evidence: Mapping[str, object] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    schema: str = ACTION_SCHEMA

    @property
    def status(self) -> str:
        if not self.performed:
            return "blocked"
        return "ok" if self.goal_verified else "partial"

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "action": self.action,
            "status": self.status,
            "performed": self.performed,
            "goal_verified": self.goal_verified,
            "detail": self.detail,
            "ref": self.ref,
            "snapshot_id": self.snapshot_id,
            "generation": self.generation,
            "url_before": self.url_before,
            "url_after": self.url_after,
            "evidence": dict(self.evidence),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class ObservationPolicy:
    """무엇을 볼 수 있고 무엇을 받아들일지. 기본값은 **닫혀 있다**."""

    allow_local: bool = False
    max_elements: int = MAX_ELEMENTS_TOTAL
    download_dir: Path | None = None
    download_max_bytes: int = DEFAULT_DOWNLOAD_MAX_BYTES
    upload_root: Path | None = None
    upload_max_bytes: int = DEFAULT_UPLOAD_MAX_BYTES
    block_executable_downloads: bool = True
    action_timeout_ms: int = 5000

    def __post_init__(self) -> None:
        if self.download_max_bytes <= 0 or self.upload_max_bytes <= 0:
            raise ValueError("download/upload size limits must be positive")


# ── 마스킹 ──────────────────────────────────────────────────────────────────
# 값이 실릴 수 있는 접근성 role. 실측(Playwright 1.60/chromium): `aria_snapshot()` 은
# password 입력의 값을 **평문으로** 포함한다(`- textbox "Secret": hunter2-secret`).
_VALUE_BEARING_ROLES: Final = frozenset({"textbox", "combobox", "searchbox", "spinbutton"})
_VALUE_LINE: Final = re.compile(r"^-\s*([A-Za-z]+)")
_VALUE_SUFFIX: Final = re.compile(r"^(-\s*\S+.*?):\s.*$")


def mask_secret_values(text: str, secrets: Sequence[str]) -> str:
    """우리가 아는 비밀 문자열을 관찰 텍스트에서 지운다(부분 일치 포함)."""
    masked = text
    for secret in secrets:
        if len(secret) >= 4 and secret in masked:
            masked = masked.replace(secret, MASK)
    return masked


def scrub_input_values(text: str) -> str:
    """접근성 요약에서 **입력값**을 지운다.

    이름 기반 삭제는 이름 없는 비밀 필드를 놓치고, 값 기반 마스킹은 우리가 넣은 값만 안다.
    값이 실릴 수 있는 role 의 `: 값` 접미사를 전부 제거하면 둘 다 필요 없다 — 값이 있는지는
    refs 의 `filled` 가 답한다. 비밀 필드가 화면에 있어도 원문은 페이지를 떠나지 않는다.
    """
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        role = _VALUE_LINE.match(stripped)
        if role is not None and role.group(1) in _VALUE_BEARING_ROLES:
            match = _VALUE_SUFFIX.match(stripped)
            if match:
                indent = line[: len(line) - len(line.lstrip())]
                lines.append(f"{indent}{match.group(1)}")
                continue
        lines.append(line)
    return "\n".join(lines)


def _looks_executable(head: bytes, filename: str) -> bool:
    if Path(filename).suffix.casefold() in _BLOCKED_SUFFIXES:
        return True
    stripped = head.lstrip()
    for magic in (*_BLOCKED_MAGIC, b"<script", b"<?php"):
        if head.startswith(magic) or stripped.startswith(magic):
            return True
    return False


def _sniff_head(path: Path, size: int = 8) -> bytes:
    try:
        with path.open("rb") as handle:
            return handle.read(size)
    except OSError:
        return b""


_UNSAFE_FILENAME: Final = re.compile(r"[^A-Za-z0-9._-]")


def safe_filename(name: str) -> str:
    """다운로드 파일명은 서버가 정한다 — 경로 문자를 지우고 basename 만 남긴다."""
    cleaned = _UNSAFE_FILENAME.sub("_", Path(name).name).lstrip(".") or "download.bin"
    return cleaned[:120]


# ── 관찰자 ──────────────────────────────────────────────────────────────────
@dataclass
class _RefBinding:
    token: str
    raw_ref: str
    page_key: str
    frame_path: tuple[int, ...]
    frame_label: str
    role: str
    name: str
    tag: str
    secret: bool
    disabled: bool


@dataclass
class _Snapshot:
    snapshot_id: str
    generation: int
    page_key: str
    url: str
    digest: str
    observed_at: float
    observation: Observation
    bindings: dict[str, _RefBinding] = field(default_factory=dict)


@dataclass
class _Outcome:
    """행동 하나의 관측 결과(`act` 가 `ActionResult` 로 감싼다)."""

    performed: bool
    goal_verified: bool
    detail: str
    ref: str | None
    snapshot_id: str
    url_after: str
    evidence: dict[str, object] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()


class BrowserObserver:
    """한 세션(owner)의 관찰·행동 상태기계.

    페이지 객체는 소유자(`browser_session_owner`)가 준 lease 에서 온다 — 이 클래스는 브라우저를
    띄우지 않는다. 하는 일은 **무엇을 보여 주고 무엇을 허용할지**를 정하는 것뿐이다.
    """

    def __init__(
        self,
        owner: BrowserOwner | None = None,
        *,
        lease: BrowserLease | None = None,
        policy: ObservationPolicy | None = None,
        validator: Callable[[str, bool], str] | None = None,
    ) -> None:
        self.owner: BrowserOwner = owner or current_browser_owner()
        self.policy: ObservationPolicy = policy or ObservationPolicy()
        self.session_tag: str = hashlib.sha256(self.owner.key.encode("utf-8")).hexdigest()[:6]
        self.generation: int = 0
        self._pages: dict[str, object] = {}
        self._primary: str = "main"
        self._snapshots: dict[str, _Snapshot] = {}
        self._current: str | None = None
        self._secrets: list[str] = []
        self._foreign: tuple[str, ...] = ()
        self._validate: Callable[[str, bool], str] | None = validator
        if lease is not None:
            self._foreign = tuple(lease.foreign_pages)
            self.register_page(lease.page, "main")

    # ── 상태 ───────────────────────────────────────────────────────────────
    def configure_policy(self, policy: ObservationPolicy) -> None:
        """정책을 바꾼다(다운로드/업로드 샌드박스 경로는 요청마다 달라진다)."""
        self.policy = policy

    def register_page(self, page: object, key: str = "main") -> None:
        self._pages[key] = page
        if key == "main":
            self._primary = "main"

    def status(self) -> dict[str, object]:
        return {
            "session_tag": self.session_tag,
            "owner": self.owner.describe(),
            "generation": self.generation,
            "snapshots": len(self._snapshots),
            "current_snapshot": self._current,
            "pages": sorted(self._pages),
            "secrets_remembered": len(self._secrets),
            "policy": {
                "allow_local": self.policy.allow_local,
                "download_dir": self.policy.download_dir.name if self.policy.download_dir else None,
                "upload_root": self.policy.upload_root.name if self.policy.upload_root else None,
            },
        }

    def _validator(self) -> Callable[[str, bool], str]:
        if self._validate is None:
            # 소유자의 egress 규칙과 **같은 함수**를 쓴다(여기서 규칙을 다시 쓰지 않는다).
            from antigravity_k.tools.browser_session_owner import get_browser_session_owner

            owner_rule = get_browser_session_owner()

            def _delegate(url: str, allow_local: bool) -> str:
                return owner_rule.validate_navigation(url, allow_local=allow_local)

            self._validate = _delegate
        return self._validate

    # ── 관찰 ───────────────────────────────────────────────────────────────
    async def observe(
        self,
        *,
        screenshot: bool = False,
        page_key: str | None = None,
        accessibility: bool = True,
    ) -> Observation:
        key = page_key or self._primary
        registered = self._pages.get(key)
        if registered is None:
            raise BrowserObservationError(UNKNOWN_REF, f"no page registered as {key!r}", stage="observe")
        page = cast("_PageLike", registered)

        collected: list[tuple[tuple[int, ...], str, list[dict[str, object]]]] = []
        frames: list[FrameInfo] = []
        warnings: list[str] = []
        await self._collect_frame(page.main_frame, (), "main", collected, frames, warnings)

        url = str(page.url)
        title = await self._title(page)
        digest = self._digest(url, title, collected)
        previous = self._snapshots.get(self._current) if self._current else None
        # 구조 지문이 그대로면 snapshot 을 **재사용**해 이전 ref 를 살려 둔다(바뀔 때만 generation+1).
        # `cast` 를 쓰지 않는 이유: pre-commit 훅은 `--no-strict-optional` 로 돌아 여기서 cast 가
        # _Snapshot → _Snapshot 이 되어 `redundant-cast` 오류를 낸다(로컬 `mypy src` 는 strict
        # optional 이라 통과해 버린다). 분기 구조로 좁히면 두 설정 모두에서 통과한다.
        if previous is None or previous.digest != digest or previous.page_key != key:
            self.generation += 1
            snapshot_id = uuid4().hex[:10]
        else:
            snapshot_id = previous.snapshot_id

        bindings: dict[str, _RefBinding] = {}
        refs: list[ElementRef] = []
        truncated = False
        for frame_path, label, items in collected:
            for item in items:
                if len(refs) >= self.policy.max_elements:
                    truncated = True
                    break
                token = self._token(snapshot_id, label, str(item.get("ref", "")))
                name = mask_secret_values(str(item.get("name", "")), self._secrets)
                binding = _RefBinding(
                    token=token,
                    raw_ref=str(item.get("ref", "")),
                    page_key=key,
                    frame_path=frame_path,
                    frame_label=label,
                    role=str(item.get("role", "")),
                    name=name,
                    tag=str(item.get("tag", "")),
                    secret=bool(item.get("secret")),
                    disabled=bool(item.get("disabled")),
                )
                bindings[token] = binding
                refs.append(
                    ElementRef(
                        ref=token,
                        role=binding.role,
                        name=name,
                        tag=binding.tag,
                        frame=label,
                        actionable=bool(item.get("actionable", True)) and not binding.disabled,
                        disabled=binding.disabled,
                        secret=binding.secret,
                        filled=bool(item.get("filled")),
                    )
                )
            if truncated:
                break
        if truncated:
            warnings.append(f"observation truncated at {self.policy.max_elements} elements")

        screenshot_b64: str | None = None
        masked = False
        masked_regions = 0
        if screenshot:
            screenshot_b64, masked, masked_regions = await self._screenshot(page)
        accessibility_text: str | None = None
        if accessibility:
            accessibility_text = await self._accessibility(page)
            if accessibility_text:
                accessibility_text = mask_secret_values(accessibility_text, self._secrets)[:MAX_ACCESSIBILITY_CHARS]

        observation = Observation(
            session_tag=self.session_tag,
            snapshot_id=snapshot_id,
            generation=self.generation,
            page_key=key,
            url=url,
            title=title,
            captured_at=datetime.now(UTC).isoformat(timespec="seconds"),
            refs=tuple(refs),
            frames=tuple(frames),
            popups=await self._popups(registered),
            accessibility=accessibility_text,
            screenshot=screenshot_b64,
            screenshot_masked=masked,
            masked_regions=masked_regions,
            warnings=tuple(warnings),
        )
        self._snapshots[snapshot_id] = _Snapshot(
            snapshot_id=snapshot_id,
            generation=self.generation,
            page_key=key,
            url=url,
            digest=digest,
            observed_at=0.0,
            observation=observation,
            bindings=bindings,
        )
        self._current = snapshot_id
        # 관찰 이력이 페이지 전체를 붙잡지 않도록 최근 것만 남긴다(그보다 오래된 ref 는 어차피 거절된다).
        for stale_id in list(self._snapshots)[:-MAX_KEPT_SNAPSHOTS]:
            self._snapshots.pop(stale_id, None)
        logger.info(
            "[BrowserObserve] session=%s snapshot=%s generation=%d refs=%d frames=%d popups=%d",
            self.session_tag,
            snapshot_id,
            self.generation,
            len(refs),
            len(frames),
            len(observation.popups),
        )
        return observation

    async def _title(self, page: _PageLike) -> str:
        try:
            return str(await _call(page, "title"))[:MAX_NAME_CHARS]
        except Exception:  # noqa: BLE001 - 제목은 없어도 관찰은 계속된다
            return ""

    async def _collect_frame(
        self,
        frame: object,
        path: tuple[int, ...],
        label: str,
        collected: list[tuple[tuple[int, ...], str, list[dict[str, object]]]],
        frames: list[FrameInfo],
        warnings: list[str],
    ) -> None:
        frames.append(FrameInfo(path=label, url=str(getattr(frame, "url", ""))))
        try:
            raw = await _maybe_await(cast("_FrameLike", frame).evaluate(_COLLECT_SCRIPT))
            items = [
                cast("dict[str, object]", item) for item in cast("list[object]", raw or []) if isinstance(item, dict)
            ]
            collected.append((path, label, items))
        except BrowserObservationError:
            raise
        except Exception as exc:  # noqa: BLE001 - 한 frame 이 죽어도 나머지는 관찰한다
            warnings.append(f"frame {label} could not be observed: {type(exc).__name__}")
            collected.append((path, label, []))
        for index, child in enumerate(list(getattr(frame, "child_frames", []) or [])):
            await self._collect_frame(child, (*path, index), f"{label}>f{index}", collected, frames, warnings)

    def _digest(
        self, url: str, title: str, collected: Sequence[tuple[tuple[int, ...], str, list[dict[str, object]]]]
    ) -> str:
        """**구조적** 변경 판정용 지문. `filled` 를 넣어야 fill 이후 재관찰이 새 generation 이 된다."""
        material: list[object] = [url, title]
        for _path, label, items in collected:
            for item in items:
                material.append(
                    (
                        label,
                        item.get("ref"),
                        item.get("tag"),
                        item.get("role"),
                        item.get("name"),
                        bool(item.get("disabled")),
                        bool(item.get("filled")),
                        bool(item.get("secret")),
                    )
                )
        encoded = json.dumps(material, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]

    def _token(self, snapshot_id: str, frame_label: str, raw_ref: str) -> str:
        slug = hashlib.sha1(frame_label.encode("utf-8")).hexdigest()[:4]  # noqa: S324 - 식별용, 보안용 아님
        return f"{self.session_tag}-{snapshot_id}-{slug}-e{raw_ref}"

    async def _popups(self, page: object) -> tuple[PopupInfo, ...]:
        """우리가 열지 않은 페이지(foreign)와 새로 열린 페이지를 **식별**한다."""
        context = getattr(page, "context", None)
        pages = list(getattr(context, "pages", []) or [])
        popups: list[PopupInfo] = []
        index = 0
        for candidate in pages:
            if candidate is page:
                continue
            url = str(getattr(candidate, "url", ""))
            foreign = bool(self._foreign) and (url in self._foreign or url == "")
            popups.append(PopupInfo(key=f"popup:{index}", url=url, foreign=foreign))
            self._pages.setdefault(f"popup:{index}", candidate)
            index += 1
        return tuple(popups)

    async def _accessibility(self, page: _PageLike) -> str | None:
        """접근성 요약(있으면). 없으면 DOM 요약만으로 계약은 성립한다."""
        try:
            # 가짜 페이지(async mock)는 locator 호출이 코루틴일 수 있다 — 버리지 않고 받아 준다
            # (안 그러면 'coroutine was never awaited' 경고가 진짜 누수를 가린다).
            body = await _maybe_await(cast("_FrameLike", page.main_frame).locator("body"))
            snapshotter = getattr(body, "aria_snapshot", None)
            if not callable(snapshotter):
                return None
            value = await _maybe_await(snapshotter())
            text = value if isinstance(value, str) else ""
            # 값(특히 비밀 필드의 원문)은 요약에 싣지 않는다.
            return scrub_input_values(text)[:MAX_ACCESSIBILITY_CHARS] or None
        except Exception as exc:  # noqa: BLE001 - 접근성 요약은 부가 정보다
            logger.debug("[BrowserObserve] accessibility snapshot unavailable: %s", exc)
            return None

    # ── 스크린샷(비밀 필드 마스킹) ────────────────────────────────────────────
    async def _screenshot(self, page: _PageLike) -> tuple[str, bool, int]:
        boxes = await self._secret_boxes(page.main_frame, 0.0, 0.0)
        if boxes:
            _ = await _maybe_await(cast("_FrameLike", page.main_frame).evaluate(_MASK_OVERLAY_JS, boxes))
        try:
            raw = await _call(page, "screenshot", type="png")
            data = raw if isinstance(raw, bytes) else b""
        finally:
            if boxes:
                try:
                    _ = await _maybe_await(cast("_FrameLike", page.main_frame).evaluate(_UNMASK_OVERLAY_JS))
                except Exception:  # noqa: BLE001 - 덮개 제거 실패가 관찰을 막지 않는다
                    logger.warning("[BrowserObserve] failed to remove secret mask overlay")
        return base64.b64encode(data).decode("utf-8"), bool(boxes), len(boxes)

    async def _secret_boxes(self, frame: object, ox: float, oy: float) -> list[dict[str, float]]:
        """비밀 필드의 **페이지 좌표** 사각형. 중첩 iframe 도 오프셋을 누적해 덮는다."""
        boxes: list[dict[str, float]] = []
        try:
            raw = await _maybe_await(cast("_FrameLike", frame).evaluate(_SECRET_BOXES_JS))
            for item in cast("list[object]", raw or []):
                if isinstance(item, dict):
                    mapping = cast("Mapping[str, object]", item)
                    boxes.append(
                        {
                            "x": ox + float(cast("float", mapping.get("x", 0))),
                            "y": oy + float(cast("float", mapping.get("y", 0))),
                            "w": float(cast("float", mapping.get("w", 0))),
                            "h": float(cast("float", mapping.get("h", 0))),
                        }
                    )
        except Exception as exc:  # noqa: BLE001
            logger.debug("[BrowserObserve] secret box probe failed: %s", exc)
        children = list(getattr(frame, "child_frames", []) or [])
        if not children:
            return boxes
        offsets: list[dict[str, float]] = []
        try:
            raw_offsets = await _maybe_await(cast("_FrameLike", frame).evaluate(_FRAME_RECTS_JS))
            for item in cast("list[object]", raw_offsets or []):
                if isinstance(item, dict):
                    mapping = cast("Mapping[str, object]", item)
                    offsets.append(
                        {
                            "x": float(cast("float", mapping.get("x", 0))),
                            "y": float(cast("float", mapping.get("y", 0))),
                        }
                    )
        except Exception as exc:  # noqa: BLE001
            logger.debug("[BrowserObserve] frame rect probe failed: %s", exc)
        for index, child in enumerate(children):
            if index >= len(offsets):
                break
            boxes.extend(await self._secret_boxes(child, ox + offsets[index]["x"], oy + offsets[index]["y"]))
        return boxes

    # ── 행동 ───────────────────────────────────────────────────────────────
    async def act(
        self,
        action: str,
        *,
        ref: str | None = None,
        url: str | None = None,
        text: str | None = None,
        value: str | None = None,
        path: str | None = None,
        delta: int = 800,
        page_key: str | None = None,
    ) -> ActionResult:
        """계약된 행동 7종만 수행한다. ref 는 **현재 관찰**의 것이어야 한다."""
        if action in FORBIDDEN_ACTIONS:
            raise BrowserObservationError(
                UNSUPPORTED_CAPABILITY,
                f"action {action!r} is not exposed: the browser contract has no arbitrary JS/selector escape hatch",
                stage="act",
            )
        if action not in ALLOWED_ACTIONS:
            raise BrowserObservationError(INVALID_ARGUMENT, f"unknown action: {action!r}", stage="act")

        key = page_key or self._primary
        page = self._pages.get(key)
        if page is None:
            raise BrowserObservationError(UNKNOWN_REF, f"no page registered as {key!r}", stage="act")
        url_before = str(cast("_PageLike", page).url)

        if action == "goto":
            outcome = await self._act_goto(cast("_PageLike", page), url)
        elif action == "scroll" and ref is None:
            # 페이지 수준 스크롤은 조작할 요소가 없다 — ref 가 필요 없다.
            outcome = await self._act_page_scroll(cast("_PageLike", page), delta)
        else:
            binding = self._resolve(ref, key)
            outcome = await self._act_with_ref(
                cast("_PageLike", page), action, binding, text=text, value=value, path=path
            )

        # 행동은 페이지를 바꿨을 수 있다 — 같은 관찰로 다시 행동하지 못하게 소비한다.
        # (`scroll` 은 읽기 성격이라 예외: 요소를 보이게 할 뿐 페이지 상태를 바꾸지 않는다.)
        if action != "scroll" and self._current is not None:
            self._snapshots.pop(self._current, None)
            self._current = None
        return ActionResult(
            action=action,
            performed=outcome.performed,
            goal_verified=outcome.goal_verified,
            detail=outcome.detail,
            ref=outcome.ref,
            snapshot_id=outcome.snapshot_id,
            generation=self.generation,
            url_before=url_before,
            url_after=outcome.url_after,
            evidence=outcome.evidence,
            warnings=outcome.warnings,
        )

    def _current_snapshot(self) -> _Snapshot:
        snapshot = self._snapshots.get(self._current) if self._current else None
        if snapshot is None:
            raise BrowserObservationError(
                STALE_SNAPSHOT,
                "no current observation: take a new observation before acting",
                retryable=True,
                stage="act",
            )
        return snapshot

    def _resolve(self, ref: str | None, page_key: str) -> _RefBinding:
        if not ref or not ref.strip():
            raise BrowserObservationError(
                INVALID_ARGUMENT, "a ref from the latest observation is required", stage="act"
            )
        if _SELECTOR_SHAPED.search(ref):
            raise BrowserObservationError(
                INVALID_ARGUMENT,
                "refs are opaque handles from an observation; selectors/XPath/JS are not accepted",
                stage="act",
            )
        parts = ref.split("-")
        if len(parts) < 4:
            raise BrowserObservationError(INVALID_ARGUMENT, "malformed ref", stage="act")
        if parts[0] != self.session_tag:
            raise BrowserObservationError(SESSION_MISMATCH, "this ref was issued to a different session", stage="act")
        snapshot = self._current_snapshot()
        if parts[1] != snapshot.snapshot_id:
            raise BrowserObservationError(
                STALE_SNAPSHOT,
                "this ref belongs to an older observation: take a new observation",
                retryable=True,
                stage="act",
            )
        binding = snapshot.bindings.get(ref)
        if binding is None:
            raise BrowserObservationError(
                UNKNOWN_REF,
                "unknown ref: it was not part of the current observation",
                stage="act",
            )
        if binding.page_key != page_key:
            raise BrowserObservationError(
                UNKNOWN_REF,
                f"this ref belongs to page {binding.page_key!r}, not {page_key!r}",
                stage="act",
            )
        return binding

    async def _locator(self, binding: _RefBinding) -> object:
        page = self._pages.get(binding.page_key)
        if page is None:
            raise BrowserObservationError(STALE_SNAPSHOT, "the page this ref belonged to is gone", retryable=True)
        frame: object = cast("_PageLike", page).main_frame
        for index in binding.frame_path:
            children = list(getattr(frame, "child_frames", []) or [])
            if index >= len(children):
                raise BrowserObservationError(
                    STALE_SNAPSHOT,
                    "the frame this ref belonged to is gone: take a new observation",
                    retryable=True,
                    stage="act",
                )
            frame = children[index]
        locator = await _maybe_await(cast("_FrameLike", frame).locator(f'[data-ssak-ref="{binding.raw_ref}"]'))
        count = int(cast("int", await _maybe_await(cast("_LocatorLike", locator).count())) or 0)
        if count == 0:
            raise BrowserObservationError(
                STALE_SNAPSHOT,
                "the element behind this ref no longer exists: take a new observation",
                retryable=True,
                stage="act",
            )
        if count > 1:
            raise BrowserObservationError(
                ELEMENT_NOT_ACTIONABLE,
                f"this ref matched {count} elements; the page state is ambiguous",
                stage="act",
            )
        visible = True
        enabled = not binding.disabled
        checker = getattr(locator, "is_visible", None)
        if callable(checker):
            visible = bool(await _maybe_await(checker()))
        checker = getattr(locator, "is_enabled", None)
        if callable(checker):
            enabled = bool(await _maybe_await(checker()))
        if not visible or not enabled:
            raise BrowserObservationError(
                ELEMENT_NOT_ACTIONABLE,
                "the element behind this ref is hidden or disabled now: take a new observation",
                retryable=True,
                stage="act",
            )
        return locator

    async def _act_page_scroll(self, page: _PageLike, delta: int) -> _Outcome:
        """페이지 전체를 `delta` 픽셀 움직인다(요소 목표가 없는 스크롤)."""
        before = await self._scroll_offset(page)
        mouse = getattr(page, "mouse", None)
        wheel = getattr(mouse, "wheel", None)
        if callable(wheel):
            await _maybe_await(wheel(0, delta))
        else:
            _ = await _maybe_await(
                cast("_FrameLike", page.main_frame).evaluate(f"(() => window.scrollBy(0, {int(delta)}))()"),
            )
        after = await self._wait_for_scroll(page, before)
        return _Outcome(
            performed=True,
            goal_verified=after != before,
            detail=f"scrolled the page by {delta}px",
            ref=None,
            snapshot_id=self._snapshot_id(),
            url_after=str(page.url),
            evidence={"delta": delta, "offset_before": before, "offset_after": after},
        )

    async def _wait_for_scroll(self, page: _PageLike, before: int, timeout_ms: int = 300) -> int:
        """휠 이벤트는 **즉시 반영되지 않는다** — 값이 바뀌거나 짧은 시간이 지날 때까지 확인한다.

        (실측: `mouse.wheel` 직후 `window.scrollY` 를 읽으면 0 이라, 검증을 먼저 읽으면
        성공한 스크롤이 '움직이지 않았다'로 기록된다.)
        """
        deadline = time.monotonic() + timeout_ms / 1000
        current = await self._scroll_offset(page)
        while current == before and time.monotonic() < deadline:
            await asyncio.sleep(0.02)
            current = await self._scroll_offset(page)
        return current

    async def _scroll_offset(self, page: _PageLike) -> int:
        try:
            value = await _maybe_await(
                cast("_FrameLike", page.main_frame).evaluate("(() => Math.round(window.scrollY))()")
            )
            return int(cast("int", value) or 0)
        except Exception:  # noqa: BLE001
            return 0

    async def _act_goto(self, page: _PageLike, url: str | None) -> _Outcome:
        if not url or not url.strip():
            raise BrowserObservationError(INVALID_ARGUMENT, "url is required for goto", stage="act")
        validate = self._validator()
        try:
            target = validate(url, self.policy.allow_local)
        except Exception as exc:  # noqa: BLE001 - egress 규칙 위반은 정책 거절이다
            raise BrowserObservationError(
                POLICY_DENIED, f"navigation target is not allowed: {exc}", stage="act"
            ) from exc
        response = await _maybe_await(page.goto(target, wait_until="load"))
        final_url = str(page.url)
        # 리다이렉트가 사설 주소로 데려갔을 수 있다 — **최종 URL** 을 다시 검사한다.
        if final_url and not final_url.startswith(("about:", "data:")):
            try:
                validate(final_url, self.policy.allow_local)
            except Exception as exc:  # noqa: BLE001
                raise BrowserObservationError(
                    POLICY_DENIED,
                    f"navigation landed on a disallowed address: {exc}",
                    stage="act",
                ) from exc
        status = getattr(response, "status", None)
        return _Outcome(
            performed=True,
            goal_verified=final_url != "",
            detail=f"navigated to {final_url}",
            ref=None,
            snapshot_id=self._snapshot_id(),
            url_after=final_url,
            evidence={
                "requested_url": target,
                "final_url": final_url,
                "status": status if isinstance(status, int) else None,
            },
        )

    async def _act_with_ref(
        self,
        page: _PageLike,
        action: str,
        binding: _RefBinding,
        *,
        text: str | None,
        value: str | None,
        path: str | None,
    ) -> _Outcome:
        locator = await self._locator(binding)
        before_url = str(page.url)
        timeout = self.policy.action_timeout_ms
        base: dict[str, object] = {"role": binding.role, "name": binding.name, "frame": binding.frame_label}

        if action == "click":
            before_digest = await self._live_digest(page)
            before_pages = self._pages_snapshot(page)
            await _call(locator, "click", timeout=timeout)
            await self._settle(page)
            after_url = str(page.url)
            navigated = after_url != before_url
            mutated = (await self._live_digest(page)) != before_digest
            opened = await self._wait_for_new_pages(page, before_pages)
            # popup 을 여는 클릭도 **관측 가능한 효과**다 — 다만 그 페이지는 다음 관찰에서
            # 식별되어(ref 발급) 다루어진다.
            if navigated:
                effect = " (navigated)"
            elif mutated:
                effect = " (dom changed)"
            elif opened:
                effect = " (opened new page)"
            else:
                effect = " (no observable effect)"
            return _Outcome(
                performed=True,
                goal_verified=navigated or mutated or bool(opened),
                detail=f"clicked {binding.role} {binding.name!r}{effect}",
                ref=binding.token,
                snapshot_id=self._snapshot_id(),
                url_after=after_url,
                evidence={**base, "navigated": navigated, "dom_changed": mutated, "opened_pages": opened},
            )

        if action == "fill":
            if text is None:
                raise BrowserObservationError(INVALID_ARGUMENT, "text is required for fill", stage="act")
            await _call(locator, "fill", text, timeout=timeout)
            if binding.secret:
                self._remember_secret(text)
            actual = await self._read_value(locator)
            # 비밀 필드는 원문을 되읽지 않는다 — 길이만 확인한다.
            verified = (len(actual) == len(text)) if binding.secret else (actual == text)
            return _Outcome(
                performed=True,
                goal_verified=verified,
                detail=f"filled {binding.role} {binding.name!r}",
                ref=binding.token,
                snapshot_id=self._snapshot_id(),
                url_after=str(page.url),
                evidence={**base, "secret": binding.secret, "length": len(text), "value_verified": verified},
            )

        if action == "scroll":
            await _call(locator, "scroll_into_view_if_needed", timeout=timeout)
            in_view = await self._in_viewport(locator)
            return _Outcome(
                performed=True,
                goal_verified=in_view,
                detail=f"scrolled {binding.role} {binding.name!r} into view",
                ref=binding.token,
                snapshot_id=self._snapshot_id(),
                url_after=str(page.url),
                evidence={**base, "in_viewport": in_view},
            )

        if action == "select":
            target = value if value is not None else text
            if target is None:
                raise BrowserObservationError(INVALID_ARGUMENT, "value is required for select", stage="act")
            try:
                await _call(locator, "select_option", target, timeout=timeout)
            except Exception as exc:  # noqa: BLE001 - 없는 option 은 계약 위반이 아니라 실패다
                return _Outcome(
                    performed=False,
                    goal_verified=False,
                    detail=f"could not select {target!r}: {type(exc).__name__}",
                    ref=binding.token,
                    snapshot_id=self._snapshot_id(),
                    url_after=str(page.url),
                    evidence=base,
                )
            actual = await self._read_value(locator)
            return _Outcome(
                performed=True,
                goal_verified=actual == target,
                detail=f"selected {target!r} on {binding.role} {binding.name!r}",
                ref=binding.token,
                snapshot_id=self._snapshot_id(),
                url_after=str(page.url),
                evidence={**base, "selected": actual},
            )

        if action == "upload":
            if path is None:
                raise BrowserObservationError(INVALID_ARGUMENT, "path is required for upload", stage="act")
            safe = self._authorize_upload(path)
            await _call(locator, "set_input_files", str(safe), timeout=timeout)
            count = await self._input_file_count(locator)
            return _Outcome(
                performed=True,
                goal_verified=count >= 1,
                detail=f"uploaded {safe.name} to {binding.role} {binding.name!r}",
                ref=binding.token,
                snapshot_id=self._snapshot_id(),
                url_after=str(page.url),
                evidence={**base, "filename": safe.name, "bytes": safe.stat().st_size, "files_seen": count},
            )

        if action == "download":
            return await self._act_download(page, locator, binding, base, timeout)

        raise BrowserObservationError(INVALID_ARGUMENT, f"unknown action: {action!r}", stage="act")

    async def _act_download(
        self,
        page: _PageLike,
        locator: object,
        binding: _RefBinding,
        base: dict[str, object],
        timeout: int,
    ) -> _Outcome:
        directory = self.policy.download_dir
        if directory is None:
            raise BrowserObservationError(
                POLICY_DENIED,
                "downloads require a task sandbox directory; none is configured",
                stage="act",
            )
        directory.mkdir(parents=True, exist_ok=True)
        expect = getattr(page, "expect_download", None)
        if not callable(expect):
            raise BrowserObservationError(UNSUPPORTED_CAPABILITY, "this page cannot capture downloads", stage="act")
        context = cast("_DownloadContext", expect(timeout=timeout))
        async with context as info:
            await _call(locator, "click", timeout=timeout)
        download = await _maybe_await(getattr(info, "value", None))
        if download is None:
            return _Outcome(
                performed=False,
                goal_verified=False,
                detail="no download was produced by this element",
                ref=binding.token,
                snapshot_id=self._snapshot_id(),
                url_after=str(page.url),
                evidence=base,
            )
        failure = await _maybe_await(cast("_DownloadLike", download).failure())
        filename = safe_filename(str(getattr(download, "suggested_filename", "") or "download.bin"))
        destination = directory / filename
        await cast("_DownloadLike", download).save_as(str(destination))
        size = destination.stat().st_size
        if self.policy.block_executable_downloads and _looks_executable(_sniff_head(destination), filename):
            destination.unlink(missing_ok=True)
            raise BrowserObservationError(
                DOWNLOAD_TYPE_DENIED,
                f"refused a download that looks executable: {filename}",
                stage="act",
            )
        if size > self.policy.download_max_bytes:
            destination.unlink(missing_ok=True)
            raise BrowserObservationError(
                DOWNLOAD_TOO_LARGE,
                f"download exceeded {self.policy.download_max_bytes} bytes and was discarded",
                stage="act",
            )
        # 데이터이지 프로그램이 아니다 — 실행 권한을 주지 않는다.
        try:
            os.chmod(destination, 0o600)
        except OSError as exc:  # pragma: no cover - 플랫폼 예외
            logger.warning("[BrowserAct] could not restrict download permissions: %s", exc)
        mode = destination.stat().st_mode
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        verified = failure is None and size > 0 and (mode & 0o111) == 0
        return _Outcome(
            performed=True,
            goal_verified=verified,
            detail=f"saved download {filename} ({size} bytes)",
            ref=binding.token,
            snapshot_id=self._snapshot_id(),
            url_after=str(page.url),
            evidence={
                **base,
                "filename": filename,
                "bytes": size,
                "sha256": digest,
                "failure": str(failure) if failure else None,
                "executable_bits": bool(mode & 0o111),
            },
        )

    # ── 보조 ───────────────────────────────────────────────────────────────
    def _snapshot_id(self) -> str:
        snapshot = self._snapshots.get(self._current) if self._current else None
        return snapshot.snapshot_id if snapshot else ""

    def _remember_secret(self, secret: str) -> None:
        if len(secret) < 4 or secret in self._secrets:
            return
        self._secrets.append(secret)
        del self._secrets[:-MAX_SECRETS_REMEMBERED]

    def _authorize_upload(self, path: str) -> Path:
        root = self.policy.upload_root
        if root is None:
            raise BrowserObservationError(
                POLICY_DENIED,
                "uploads require a task sandbox directory; none is configured",
                stage="act",
            )
        candidate = Path(path).expanduser()
        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise BrowserObservationError(
                INVALID_ARGUMENT,
                f"upload source is not readable: {candidate.name}",
                stage="act",
            ) from exc
        if not resolved.is_file():
            raise BrowserObservationError(INVALID_ARGUMENT, "upload source must be a regular file", stage="act")
        root_resolved = root.expanduser().resolve()
        if root_resolved != resolved and root_resolved not in resolved.parents:
            raise BrowserObservationError(POLICY_DENIED, "upload source is outside the task sandbox", stage="act")
        if resolved.stat().st_size > self.policy.upload_max_bytes:
            raise BrowserObservationError(
                POLICY_DENIED,
                f"upload source exceeds {self.policy.upload_max_bytes} bytes",
                stage="act",
            )
        return resolved

    async def _read_value(self, locator: object) -> str:
        getter = getattr(locator, "input_value", None)
        if not callable(getter):
            return ""
        try:
            return str(await _maybe_await(getter()))
        except Exception:  # noqa: BLE001 - 값 확인 실패는 검증 실패다
            return ""

    async def _input_file_count(self, locator: object) -> int:
        prober = getattr(locator, "evaluate", None)
        if not callable(prober):
            return 0
        try:
            value = await _maybe_await(prober("(el) => (el.files ? el.files.length : 0)"))
            return int(cast("int", value) or 0)
        except Exception:  # noqa: BLE001
            return 0

    async def _in_viewport(self, locator: object) -> bool:
        prober = getattr(locator, "evaluate", None)
        if not callable(prober):
            return True
        try:
            value = await _maybe_await(
                prober(
                    "(el) => { const r = el.getBoundingClientRect();"
                    " return r.top < window.innerHeight && r.bottom > 0; }",
                ),
            )
            return bool(value)
        except Exception:  # noqa: BLE001
            return True

    def _pages_snapshot(self, page: _PageLike) -> list[object]:
        return list(getattr(page.context, "pages", []) or [])

    def _new_pages(self, page: _PageLike, before: Sequence[object]) -> list[str]:
        known = {id(item) for item in before}
        return [str(getattr(item, "url", "")) for item in self._pages_snapshot(page) if id(item) not in known]

    async def _wait_for_new_pages(
        self,
        page: _PageLike,
        before: Sequence[object],
        timeout_ms: int = 400,
    ) -> list[str]:
        """popup 은 **비동기로** 열린다 — 클릭 직후 한 번만 보면 놓친다.

        (실측: 앞선 행동 뒤의 클릭에서는 새 페이지가 몇백 ms 뒤에 나타나, 즉시 확인하면
        '무효과' 로 기록되고 다음 관찰도 `popup:0` 을 못 본다.)
        """
        deadline = time.monotonic() + timeout_ms / 1000
        opened = self._new_pages(page, before)
        while not opened and time.monotonic() < deadline:
            await asyncio.sleep(0.02)
            opened = self._new_pages(page, before)
        return opened

    async def _settle(self, page: _PageLike) -> None:
        try:
            _ = await _maybe_await(page.wait_for_load_state("networkidle"))
        except Exception:  # noqa: BLE001 - 조용한 페이지에서도 행동은 성공이다
            return

    async def _content_probe(self, frame: object, label: str, acc: list[tuple[str, int, int]]) -> None:
        """페이지 **내용** 지문(요소 수 + 속성/텍스트 해시). `[data-ssak-ref]` 는 세지 않는다."""
        try:
            raw = await _maybe_await(cast("_FrameLike", frame).evaluate(_CONTENT_JS))
            if isinstance(raw, Mapping):
                mapping = cast("Mapping[str, object]", raw)
                acc.append(
                    (
                        label,
                        int(cast("int", mapping.get("nodes", 0)) or 0),
                        int(cast("int", mapping.get("hash", 0)) or 0),
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("[BrowserAct] content probe failed for %s: %s", label, exc)
        for index, child in enumerate(list(getattr(frame, "child_frames", []) or [])):
            await self._content_probe(child, f"{label}>f{index}", acc)

    async def _live_digest(self, page: _PageLike) -> str:
        """행동 직후의 내용 지문 — 'performed' 와 'goal_verified' 를 가르는 실제 측정.

        관찰용 `_digest`(조작 가능 구조)와 달리 **텍스트와 속성 변화**까지 본다. 그래야
        "눌렀지만 아무 일도 없었다" 와 "눌러서 페이지가 바뀌었다" 가 갈린다. 이 지문은
        페이지를 **바꾸지 않는다**(예전 구현은 ref 표식을 다시 칠해 관찰 상태를 건드렸다).
        """
        acc: list[tuple[str, int, int]] = []
        try:
            await self._content_probe(page.main_frame, "main", acc)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[BrowserAct] live digest failed: %s", exc)
            return ""
        encoded = json.dumps([str(page.url), acc], sort_keys=True)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


class _DownloadLike(Protocol):
    def failure(self) -> Awaitable[object]: ...
    def save_as(self, path: str) -> Awaitable[object]: ...
    @property
    def suggested_filename(self) -> str: ...


class _DownloadContext(Protocol):
    async def __aenter__(self) -> object: ...
    async def __aexit__(self, *args: object) -> object: ...


# ── observer 레지스트리(owner 당 하나) ───────────────────────────────────────
_observers: dict[str, BrowserObserver] = {}


def observer_for_owner(
    owner: BrowserOwner | None = None,
    *,
    lease: BrowserLease | None = None,
    policy: ObservationPolicy | None = None,
    validator: Callable[[str, bool], str] | None = None,
) -> BrowserObserver:
    """owner 의 관찰자를 준다. `lease` 를 주면 그 페이지를 등록한다(소유자가 준 것만)."""
    resolved = owner or current_browser_owner()
    observer = _observers.get(resolved.key)
    if observer is None:
        observer = BrowserObserver(resolved, lease=lease, policy=policy, validator=validator)
        _observers[resolved.key] = observer
    elif lease is not None:
        observer.register_page(lease.page, "main")
    return observer


def drop_browser_observer(owner: BrowserOwner | None = None) -> bool:
    """세션이 닫히면 관찰 이력도 버린다 — 닫힌 페이지의 ref 를 들고 있지 않는다."""
    resolved = owner or current_browser_owner()
    return _observers.pop(resolved.key, None) is not None


def reset_browser_observers() -> None:
    """시험용: 모든 관찰자를 버린다."""
    _observers.clear()


def describe_browser_observers() -> dict[str, object]:
    return {"count": len(_observers), "observers": [item.status() for item in _observers.values()]}


__all__ = [
    "ACTION_SCHEMA",
    "ALLOWED_ACTIONS",
    "ActionResult",
    "BrowserObservationError",
    "BrowserObserver",
    "DOWNLOAD_TOO_LARGE",
    "DOWNLOAD_TYPE_DENIED",
    "ELEMENT_NOT_ACTIONABLE",
    "ElementRef",
    "FORBIDDEN_ACTIONS",
    "FrameInfo",
    "INVALID_ARGUMENT",
    "OBSERVATION_SCHEMA",
    "Observation",
    "ObservationPolicy",
    "POLICY_DENIED",
    "PopupInfo",
    "SESSION_MISMATCH",
    "STALE_SNAPSHOT",
    "UNKNOWN_REF",
    "UNSUPPORTED_CAPABILITY",
    "describe_browser_observers",
    "drop_browser_observer",
    "mask_secret_values",
    "observer_for_owner",
    "scrub_input_values",
    "reset_browser_observers",
    "safe_filename",
]
