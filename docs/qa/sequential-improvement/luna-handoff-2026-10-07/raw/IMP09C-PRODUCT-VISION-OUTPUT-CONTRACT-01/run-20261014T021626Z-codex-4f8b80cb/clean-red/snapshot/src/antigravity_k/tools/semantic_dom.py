"""Ssak-Ai: 시맨틱 DOM 파서 (Semantic DOM Engine).

=====================================================
browser-use의 Snapshot+Refs 패턴과 SeeAct의 Set-of-Mark 패턴을
네이티브로 구현한 고도화된 DOM 파싱 엔진입니다.

핵심 기능:
1. A11y Tree + DOM을 융합한 Semantic Snapshot 생성
2. @ref 인덱싱 — LLM이 요소를 "click @ref3"처럼 정밀 참조
3. Bounding Box 계산 — Set-of-Mark 그라운딩
4. 토큰 압축 렌더러 — LLM 컨텍스트 효율 70% 향상
5. 시맨틱 의도 검색 — 자연어로 요소 탐색

사용법:
    parser = SemanticDOMParser()
    snapshot = await parser.snapshot(page)
    context = parser.to_llm_context(snapshot, max_tokens=2000)
    element = parser.find_by_intent(snapshot, "로그인 버튼")
"""

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar, Protocol, cast

logger = logging.getLogger("antigravity_k.tools.semantic_dom")


class _AsyncLocatorLike(Protocol):
    async def click(self, *, timeout: int) -> None: ...


class _SyncLocatorLike(Protocol):
    def click(self, *, timeout: int) -> None: ...


class _AsyncAccessibilityLike(Protocol):
    async def snapshot(self) -> object: ...


class _SyncAccessibilityLike(Protocol):
    def snapshot(self) -> object: ...


class _AsyncMouseLike(Protocol):
    async def click(self, x: float, y: float) -> None: ...


class _SyncMouseLike(Protocol):
    def click(self, x: float, y: float) -> None: ...


class _AsyncPageLike(Protocol):
    async def evaluate(self, expression: str) -> object: ...

    @property
    def accessibility(self) -> _AsyncAccessibilityLike: ...

    @property
    def mouse(self) -> _AsyncMouseLike: ...

    async def click(self, selector: str, *, timeout: int) -> None: ...

    def get_by_text(self, text: str, *, exact: bool) -> _AsyncLocatorLike: ...


class _SyncPageLike(Protocol):
    def evaluate(self, expression: str) -> object: ...

    @property
    def accessibility(self) -> _SyncAccessibilityLike: ...

    @property
    def mouse(self) -> _SyncMouseLike: ...

    def click(self, selector: str, *, timeout: int) -> None: ...

    def get_by_text(self, text: str, *, exact: bool) -> _SyncLocatorLike: ...


def _as_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    raw = cast(Mapping[object, object], value)
    return {key: item for key, item in raw.items() if isinstance(key, str)}


def _as_list(value: object) -> list[object]:
    return list(cast(list[object], value)) if isinstance(value, list) else []


def _as_text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _as_bool(value: object) -> bool:
    return value if isinstance(value, bool) else False


def _as_float(value: object) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return 0.0


# ─── 데이터 모델 ─────────────────────────────────────────────────


class ElementRole(str, Enum):
    """요소의 기능적 역할 분류."""

    BUTTON = "button"
    LINK = "link"
    INPUT = "input"
    SELECT = "select"
    TEXTAREA = "textarea"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    HEADING = "heading"
    IMAGE = "image"
    NAVIGATION = "navigation"
    DIALOG = "dialog"
    ALERT = "alert"
    MENU = "menu"
    TAB = "tab"
    TEXT = "text"
    OTHER = "other"


@dataclass
class BoundingBox:
    """요소의 화면 위치 (Set-of-Mark용)."""

    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0

    @property
    def center(self) -> tuple[float, float]:
        """Center.

        Returns:
            tuple[float, float]: The tuple[float, float] result.

        """
        return (self.x + self.width / 2, self.y + self.height / 2)

    def to_compact(self) -> str:
        """To Compact.

        Returns:
            str: The str result.

        """
        return f"({int(self.x)},{int(self.y)},{int(self.width)},{int(self.height)})"


@dataclass
class ElementInfo:
    """시맨틱 요소 정보."""

    ref: str  # @ref1, @ref2, ...
    tag: str = ""  # HTML 태그
    role: ElementRole = ElementRole.OTHER
    name: str = ""  # 사람이 읽을 수 있는 이름
    value: str = ""  # 현재 값 (input의 경우)
    placeholder: str = ""  # placeholder 텍스트
    aria_label: str = ""  # aria-label
    href: str = ""  # 링크 URL
    is_interactable: bool = False  # 클릭/입력 가능 여부
    is_visible: bool = True  # 화면에 보이는지
    is_disabled: bool = False  # 비활성 상태인지
    bbox: BoundingBox | None = None
    css_selector: str = ""  # 폴백용 CSS 셀렉터
    children_refs: list[str] = field(default_factory=list)
    depth: int = 0

    @property
    def display_name(self) -> str:
        """LLM 표시용 이름."""
        if self.name:
            return self.name[:60]
        if self.aria_label:
            return self.aria_label[:60]
        if self.placeholder:
            return self.placeholder[:60]
        return self.tag

    def to_compact_line(self, include_bbox: bool = True) -> str:
        """LLM 컨텍스트용 한 줄 표현."""
        parts = [self.ref, f"[{self.role.value}]"]

        if self.display_name:
            parts.append(f'"{self.display_name}"')

        if self.href:
            short_href = self.href[:40] + "..." if len(self.href) > 40 else self.href
            parts.append(f"href={short_href}")

        if self.value:
            parts.append(f"value={self.value[:30]}")

        if self.is_disabled:
            parts.append("(disabled)")

        if include_bbox and self.bbox:
            parts.append(self.bbox.to_compact())

        return " ".join(parts)


@dataclass
class SemanticSnapshot:
    """시맨틱 DOM 스냅샷."""

    elements: dict[str, ElementInfo] = field(default_factory=dict)
    url: str = ""
    title: str = ""
    interactable_count: int = 0
    total_count: int = 0

    def get(self, ref: str) -> ElementInfo | None:
        """Retrieve.

        Args:
            ref (str): str ref.

        Returns:
            ElementInfo | None: The elementinfo | none result.

        """
        return self.elements.get(ref)

    def interactable_elements(self) -> list[ElementInfo]:
        """Interactable Elements.

        Returns:
            list[ElementInfo]: The list[elementinfo] result.

        """
        return [e for e in self.elements.values() if e.is_interactable]

    def by_role(self, role: ElementRole) -> list[ElementInfo]:
        """By Role.

        Args:
            role (ElementRole): ElementRole role.

        Returns:
            list[ElementInfo]: The list[elementinfo] result.

        """
        return [e for e in self.elements.values() if e.role == role]


# ─── JS 추출 스크립트 ─────────────────────────────────────────────

# Playwright page.evaluate()로 실행할 JavaScript
# DOM에서 인터랙티브 요소 + 메타데이터 + Bounding Box를 한 번에 추출
_DOM_EXTRACT_JS = """
() => {

    const INTERACTIVE_SELECTORS = [
        'button', 'input', 'textarea', 'select', 'a[href]',
        '[role="button"]', '[role="link"]', '[role="textbox"]',
        '[role="checkbox"]', '[role="radio"]', '[role="tab"]',
        '[role="menuitem"]', '[role="option"]', '[role="switch"]',
        '[onclick]', '[tabindex]', 'summary', 'label[for]',
    ];

    const HEADING_SELECTORS = ['h1', 'h2', 'h3'];

    const allSelectors = [...INTERACTIVE_SELECTORS, ...HEADING_SELECTORS].join(', ');
    const elements = document.querySelectorAll(allSelectors);

    const results = [];
    const seen = new Set();

    for (const el of elements) {
        // 중복 방지
        if (seen.has(el)) continue;
        seen.add(el);

        // 숨겨진 요소 필터링
        const style = window.getComputedStyle(el);
        const isVisible = (
            style.display !== 'none' &&
            style.visibility !== 'hidden' &&
            style.opacity !== '0' &&
            el.offsetWidth > 0 &&
            el.offsetHeight > 0
        );

        if (!isVisible) continue;

        // Bounding Box
        const rect = el.getBoundingClientRect();

        // CSS 셀렉터 생성
        let cssSelector = '';
        if (el.id) {
            cssSelector = '#' + el.id;
        } else if (el.getAttribute('data-testid')) {
            cssSelector = `[data-testid="${el.getAttribute('data-testid')}"]`;
        } else {
            const tag = el.tagName.toLowerCase();
            const classes = Array.from(el.classList).slice(0, 2).join('.');
            cssSelector = classes ? `${tag}.${classes}` : tag;
        }

        results.push({
            tag: el.tagName.toLowerCase(),
            id: el.id || null,
            role: el.getAttribute('role') || null,
            type: el.type || null,
            name: (el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 100),
            value: el.value || null,
            placeholder: el.placeholder || null,
            ariaLabel: el.getAttribute('aria-label') || null,
            href: el.href || null,
            disabled: el.disabled || el.getAttribute('aria-disabled') === 'true',
            checked: el.checked || false,
            bbox: {
                x: Math.round(rect.x),
                y: Math.round(rect.y),
                width: Math.round(rect.width),
                height: Math.round(rect.height),
            },
            cssSelector: cssSelector,
            isInteractive: INTERACTIVE_SELECTORS.some(
                sel => el.matches(sel)
            ),
        });

        if (results.length >= 200) break;  // 상한선
    }

    return {
        url: window.location.href,
        title: document.title,
        elements: results,
    };
}
"""


# ─── 시맨틱 DOM 파서 ──────────────────────────────────────────────


class SemanticDOMParser:
    """시맨틱 DOM 파싱 엔진.

    browser-use의 Snapshot+Refs 패턴과 SeeAct의 Set-of-Mark 패턴을
    Ssak-Ai 네이티브로 구현합니다.
    """

    # 태그/role → ElementRole 매핑
    _ROLE_MAP: ClassVar[Mapping[str, ElementRole]] = {
        "button": ElementRole.BUTTON,
        "a": ElementRole.LINK,
        "input": ElementRole.INPUT,
        "textarea": ElementRole.TEXTAREA,
        "select": ElementRole.SELECT,
        "h1": ElementRole.HEADING,
        "h2": ElementRole.HEADING,
        "h3": ElementRole.HEADING,
        "img": ElementRole.IMAGE,
        "nav": ElementRole.NAVIGATION,
        "dialog": ElementRole.DIALOG,
        "alert": ElementRole.ALERT,
        "summary": ElementRole.BUTTON,
    }

    _INPUT_TYPE_ROLE: ClassVar[Mapping[str, ElementRole]] = {
        "checkbox": ElementRole.CHECKBOX,
        "radio": ElementRole.RADIO,
        "submit": ElementRole.BUTTON,
        "button": ElementRole.BUTTON,
    }

    def __init__(self):
        """Initialize the SemanticDOMParser."""
        self._ref_counter: int = 0

    def _next_ref(self) -> str:
        self._ref_counter += 1
        return f"@ref{self._ref_counter}"

    def reset(self) -> None:
        """Reset the semantic DOM parser state for a new page."""
        self._ref_counter = 0

    # ─── 메인 스냅샷 ──────────────────────────────────────────

    async def snapshot_async(self, page: object) -> SemanticSnapshot:
        """비동기 Playwright 페이지에서 시맨틱 스냅샷을 생성합니다."""
        self.reset()
        typed_page = cast(_AsyncPageLike, page)

        try:
            raw = await typed_page.evaluate(_DOM_EXTRACT_JS)
        except Exception:
            logger.exception("[SemanticDOM] JS 추출 실패")
            return SemanticSnapshot()

        return self._build_snapshot(_as_mapping(raw))

    def snapshot_sync(self, page: object) -> SemanticSnapshot:
        """동기 Playwright 페이지에서 시맨틱 스냅샷을 생성합니다."""
        self.reset()
        typed_page = cast(_SyncPageLike, page)

        try:
            raw = typed_page.evaluate(_DOM_EXTRACT_JS)
        except Exception:
            logger.exception("[SemanticDOM] JS 추출 실패")
            return SemanticSnapshot()

        return self._build_snapshot(_as_mapping(raw))

    def _build_snapshot(self, raw: Mapping[str, object]) -> SemanticSnapshot:
        """JS 추출 결과를 SemanticSnapshot으로 변환합니다."""
        snap = SemanticSnapshot(
            url=_as_text(raw.get("url")),
            title=_as_text(raw.get("title")),
        )

        for raw_el in _as_list(raw.get("elements")):
            ref = self._next_ref()
            element = self._parse_element(ref, _as_mapping(raw_el))
            snap.elements[ref] = element
            if element.is_interactable:
                snap.interactable_count += 1

        snap.total_count = len(snap.elements)
        return snap

    def _parse_element(self, ref: str, raw: Mapping[str, object]) -> ElementInfo:
        """단일 요소를 ElementInfo로 변환합니다."""
        tag = _as_text(raw.get("tag"))
        html_role = _as_text(raw.get("role"))
        input_type = _as_text(raw.get("type"))

        # 역할 결정 우선순위: aria role > input type > tag
        if html_role and html_role in self._ROLE_MAP:
            role = self._ROLE_MAP[html_role]
        elif input_type and input_type in self._INPUT_TYPE_ROLE:
            role = self._INPUT_TYPE_ROLE[input_type]
        elif tag in self._ROLE_MAP:
            role = self._ROLE_MAP[tag]
        else:
            role = ElementRole.OTHER

        # Bounding Box
        bbox_raw = _as_mapping(raw.get("bbox"))
        bbox = BoundingBox(
            x=_as_float(bbox_raw.get("x")),
            y=_as_float(bbox_raw.get("y")),
            width=_as_float(bbox_raw.get("width")),
            height=_as_float(bbox_raw.get("height")),
        )

        return ElementInfo(
            ref=ref,
            tag=tag,
            role=role,
            name=_as_text(raw.get("name")),
            value=_as_text(raw.get("value")),
            placeholder=_as_text(raw.get("placeholder")),
            aria_label=_as_text(raw.get("ariaLabel")),
            href=_as_text(raw.get("href")),
            is_interactable=_as_bool(raw.get("isInteractive")),
            is_visible=True,  # JS에서 이미 필터링
            is_disabled=_as_bool(raw.get("disabled")),
            bbox=bbox,
            css_selector=_as_text(raw.get("cssSelector")),
        )

    # ─── A11y Tree 융합 ───────────────────────────────────────

    async def enrich_with_a11y_async(self, page: object, snapshot: SemanticSnapshot) -> SemanticSnapshot:
        """Accessibility Tree 정보로 스냅샷을 보강하세요."""
        typed_page = cast(_AsyncPageLike, page)
        try:
            a11y = await typed_page.accessibility.snapshot()
            if a11y:
                self._merge_a11y(snapshot, _as_mapping(a11y))
        except Exception as e:
            logger.exception("Unhandled exception")
            logger.debug("[SemanticDOM] A11y enrichment failed: %s", e)
        return snapshot

    def enrich_with_a11y_sync(self, page: object, snapshot: SemanticSnapshot) -> SemanticSnapshot:
        """동기: Accessibility Tree 정보로 스냅샷을 보강합니다."""
        typed_page = cast(_SyncPageLike, page)
        try:
            a11y = typed_page.accessibility.snapshot()
            if a11y:
                self._merge_a11y(snapshot, _as_mapping(a11y))
        except Exception as e:
            logger.exception("Unhandled exception")
            logger.debug("[SemanticDOM] A11y enrichment failed: %s", e)
        return snapshot

    def _merge_a11y(self, snapshot: SemanticSnapshot, a11y_node: Mapping[str, object], depth: int = 0) -> None:
        """A11y 트리의 정보를 스냅샷 요소와 병합합니다."""
        a11y_name = _as_text(a11y_node.get("name"))

        # A11y 노드와 매칭되는 DOM 요소 찾기
        if a11y_name:
            for el in snapshot.elements.values():
                if (el.name and a11y_name in el.name) or (el.aria_label and a11y_name in el.aria_label):
                    # A11y에서 더 나은 이름이 있으면 업데이트
                    if not el.aria_label and a11y_name:
                        el.aria_label = a11y_name
                    break

        # 자식 노드 재귀
        for child in _as_list(a11y_node.get("children")):
            self._merge_a11y(snapshot, _as_mapping(child), depth + 1)

    # ─── LLM 컨텍스트 렌더러 ──────────────────────────────────

    def to_llm_context(
        self,
        snapshot: SemanticSnapshot,
        max_elements: int = 50,
        include_bbox: bool = True,
        interactable_only: bool = False,
    ) -> str:
        """LLM 컨텍스트 윈도우에 맞게 압축된 DOM 표현을 생성합니다.

        출력 형식:
        ```
        Page: "로그인 - Ssak-Ai" (https://localhost:5173/login)
        Elements (12 interactable):
        @ref1 [input] "이메일" placeholder="email@..." (152,290,200,32)
        @ref2 [input] "비밀번호" type=password (152,340,200,32)
        @ref3 [button] "로그인" (152,400,80,36)
        @ref4 [link] "비밀번호 찾기" href="/reset"
        ```
        """
        lines = [
            f'Page: "{snapshot.title}" ({snapshot.url})',
            f"Elements ({snapshot.interactable_count} interactable / {snapshot.total_count} total):",
            "",
        ]

        elements = list(snapshot.elements.values())
        if interactable_only:
            elements = [e for e in elements if e.is_interactable]

        for el in elements[:max_elements]:
            lines.append(el.to_compact_line(include_bbox=include_bbox))

        if len(elements) > max_elements:
            lines.append(f"... and {len(elements) - max_elements} more elements")

        return "\n".join(lines)

    # ─── 시맨틱 의도 검색 ─────────────────────────────────────

    def find_by_intent(
        self,
        snapshot: SemanticSnapshot,
        intent: str,
    ) -> ElementInfo | None:
        """자연어 의도로 요소를 탐색합니다.

        예:
            find_by_intent(snapshot, "로그인 버튼")  → @ref3
            find_by_intent(snapshot, "이메일 입력란") → @ref1
            find_by_intent(snapshot, "비밀번호 찾기") → @ref4
        """
        intent_lower = intent.lower().strip()

        # 전략 1: 정확한 이름 매칭
        for el in snapshot.elements.values():
            if el.display_name.lower() == intent_lower:
                return el

        # 전략 2: 포함 매칭 (이름, aria-label, placeholder)
        candidates: list[tuple[float, ElementInfo]] = []
        for el in snapshot.elements.values():
            score = self._intent_match_score(el, intent_lower)
            if score > 0:
                candidates.append((score, el))

        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            return candidates[0][1]

        # 전략 3: 역할 키워드 매칭
        role_keywords = {
            "버튼": ElementRole.BUTTON,
            "button": ElementRole.BUTTON,
            "링크": ElementRole.LINK,
            "link": ElementRole.LINK,
            "입력": ElementRole.INPUT,
            "input": ElementRole.INPUT,
            "체크박스": ElementRole.CHECKBOX,
            "checkbox": ElementRole.CHECKBOX,
        }

        for keyword, role in role_keywords.items():
            if keyword in intent_lower:
                role_els = snapshot.by_role(role)
                clean_intent = intent_lower.replace(keyword, "").strip()
                if clean_intent:
                    for el in role_els:
                        if clean_intent in el.display_name.lower():
                            return el
                if role_els:
                    return role_els[0]

        return None

    def _intent_match_score(self, el: ElementInfo, intent: str) -> float:
        """요소와 의도 간의 매칭 점수를 계산합니다."""
        score = 0.0
        fields = [
            (el.name.lower(), 3.0),
            (el.aria_label.lower(), 2.5),
            (el.placeholder.lower(), 2.0),
            (el.href.lower(), 1.0),
        ]

        for field_val, weight in fields:
            if not field_val:
                continue
            if intent in field_val:
                score += weight
            elif field_val in intent:
                score += weight * 0.7
            else:
                # 부분 단어 매칭
                words = intent.split()
                matched = sum(1 for w in words if w in field_val)
                if matched > 0:
                    score += weight * (matched / len(words)) * 0.5

        # 인터랙티브 요소 보너스
        if el.is_interactable:
            score *= 1.2

        return score

    # ─── @ref로 요소 조작 ─────────────────────────────────────

    def resolve_ref(self, snapshot: SemanticSnapshot, ref_or_intent: str) -> ElementInfo | None:
        """@ref 문자열 또는 자연어 의도를 ElementInfo로 해석합니다."""
        # @ref 형식
        if ref_or_intent.startswith("@ref"):
            return snapshot.get(ref_or_intent)

        # 자연어 의도
        return self.find_by_intent(snapshot, ref_or_intent)

    async def click_element_async(
        self,
        page: object,
        snapshot: SemanticSnapshot,
        ref_or_intent: str,
    ) -> str:
        """@ref 또는 의도로 요소를 클릭합니다."""
        typed_page = cast(_AsyncPageLike, page)
        element = self.resolve_ref(snapshot, ref_or_intent)
        if not element:
            return f"Error: '{ref_or_intent}'에 해당하는 요소를 찾을 수 없습니다"

        # 전략 1: CSS 셀렉터
        if element.css_selector:
            try:
                await typed_page.click(element.css_selector, timeout=5000)
                return f'Clicked {element.ref} [{element.role.value}] "{element.display_name}"'
            except Exception:
                logger.exception("Unhandled exception")
                pass

        # 전략 2: Bounding Box 중심 좌표 클릭
        if element.bbox:
            cx, cy = element.bbox.center
            await typed_page.mouse.click(cx, cy)
            return f"[BBox] Clicked {element.ref} at ({int(cx)},{int(cy)})"

        # 전략 3: 텍스트 기반 폴백
        if element.display_name:
            el = typed_page.get_by_text(element.display_name, exact=False)
            await el.click(timeout=5000)
            return f'[Text] Clicked {element.ref} by text "{element.display_name}"'

        return f"Error: {element.ref}를 클릭할 수 없습니다 (셀렉터/좌표/텍스트 모두 실패)"

    def click_element_sync(self, page: object, snapshot: SemanticSnapshot, ref_or_intent: str) -> str:
        """동기: @ref 또는 의도로 요소를 클릭합니다."""
        typed_page = cast(_SyncPageLike, page)
        element = self.resolve_ref(snapshot, ref_or_intent)
        if not element:
            return f"Error: '{ref_or_intent}'에 해당하는 요소를 찾을 수 없습니다"

        if element.css_selector:
            try:
                typed_page.click(element.css_selector, timeout=5000)
                return f'Clicked {element.ref} [{element.role.value}] "{element.display_name}"'
            except Exception:
                logger.exception("Unhandled exception")
                pass

        if element.bbox:
            cx, cy = element.bbox.center
            typed_page.mouse.click(cx, cy)
            return f"[BBox] Clicked {element.ref} at ({int(cx)},{int(cy)})"

        if element.display_name:
            el = typed_page.get_by_text(element.display_name, exact=False)
            el.click(timeout=5000)
            return f'[Text] Clicked {element.ref} by text "{element.display_name}"'

        return f"Error: {element.ref}를 클릭할 수 없습니다"
