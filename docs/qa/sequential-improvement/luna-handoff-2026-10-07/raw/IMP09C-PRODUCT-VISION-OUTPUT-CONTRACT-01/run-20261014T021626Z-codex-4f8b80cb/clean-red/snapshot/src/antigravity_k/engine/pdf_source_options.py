"""pdf_source_options — PDF 레시피 소스용 페이지 범위·헤더 필터 옵션.

Phase 21: PDF 변환기(`data_recipes._pdf_records`)에 페이지 범위 선택과
페이지 헤더 필터링을 제공한다. 문법은 CLI 친화적 문자열:

페이지 범위 (`pages`):
    "" 또는 None   → 전체 페이지
    "3"            → 3페이지만
    "1-5,8,11-13"  → 하이픈 범위 + 쉼표 목록 (중복/역순 허용, 정규화됨)
    잘못된 문법     → ValueError (0 이하/역방향 범위/비숫자)

헤더 필터 (`header_filter`):
    "" 또는 None   → 필터 없음 (헤더 규칙은 기존대로: 첫 줄이 제목처럼 보이면 질문)
    "regex"        → 헤더가 정규식에 매칭되는 페이지만 Q&A로 변환
    접두사 "!"     → 부정 필터: 매칭되는 페이지를 제외
    매칭 안 된 페이지는 건너뛴다 (요약 질문 폴백도 생성하지 않음)

질문 템플릿 (`question_template`, Phase 48):
    "" 또는 None   → 기본 동작 (헤더가 제목처럼 보이면 헤더, 아니면 페이지 요약 질문)
    지정하면       → 모든 페이지의 질문을 템플릿으로 강제 생성 (헤더 질문 미사용).
                     플레이스홀더: {page}(페이지 번호), {title}(문서 파일명),
                     {header}(페이지 첫 줄, 없으면 빈 문자열), {body}(페이지 본문).
                     템플릿에 플레이스홀더가 없어도 허용 — 페이지마다 같은 질문이 되어도
                     답(본문)이 다르면 Q&A로 유효하다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# 질문 템플릿 플레이스홀더 — {page}, {title}, {header}, {body}만 치환한다.
# 알 수 없는 {토큰}은 그대로 남는다(에러 아님) — 정규식/포맷 문자열 주입 방지를 위해
# str.format 대신 명시적 치환을 쓴다.
_QUESTION_PLACEHOLDER_RE = re.compile(r"\{(page|title|header|body)\}")


def render_question_template(template: str, *, page: int, title: str, header: str, body: str) -> str:
    """질문 템플릿의 플레이스홀더를 치환한다.

    Args:
        template: "{page}페이지의 내용을 설명해줘" 형태 템플릿.
        page: 1-based 페이지/단위 번호.
        title: 문서 제목(파일명 스템).
        header: 해당 단위의 헤더(첫 줄). 없으면 빈 문자열.
        body: 해당 단위의 본문 텍스트.

    Returns:
        치환된 질문 문자열. 알 수 없는 {토큰}은 그대로 유지된다.

    """

    def _sub(match: re.Match[str]) -> str:
        token = match.group(1)
        return {"page": str(page), "title": title, "header": header, "body": body}[token]

    return _QUESTION_PLACEHOLDER_RE.sub(_sub, template)


def parse_page_ranges(spec: str | None, total_pages: int) -> list[int] | None:
    """페이지 범위 문자열 → 1-based 페이지 번호 목록 (오름차순, 중복 제거).

    Args:
        spec: "" / None이면 None 반환(전체 페이지). 아니면 "1-5,8" 문법.
        total_pages: PDF의 실제 페이지 수 — 범위 상한 클램프와 검증에 사용.

    Returns:
        None(전체) 또는 정렬된 페이지 번호 목록.

    Raises:
        ValueError: 문법 오류 또는 문서 범위를 벗어난 페이지.

    """
    if spec is None or not spec.strip():
        return None

    selected: set[int] = set()
    for part in spec.split(","):
        token = part.strip()
        if not token:
            continue
        if "-" in token:
            start_raw, _, end_raw = token.partition("-")
            start_raw, end_raw = start_raw.strip(), end_raw.strip()
            if not start_raw.isdigit() or not end_raw.isdigit():
                raise ValueError(f"잘못된 페이지 범위: '{token}' (예: 1-5,8,11-13)")
            start, end = int(start_raw), int(end_raw)
            if start < 1 or start > end:
                raise ValueError(f"잘못된 페이지 범위: '{token}' (시작 ≤ 끝, 1 이상)")
            if end > total_pages:
                raise ValueError(f"페이지 범위 초과: '{token}' (문서는 {total_pages}페이지)")
            selected.update(range(start, end + 1))
        else:
            if not token.isdigit():
                raise ValueError(f"잘못된 페이지 번호: '{token}' (예: 1-5,8,11-13)")
            page = int(token)
            if page < 1:
                raise ValueError(f"잘못된 페이지 번호: '{token}' (1 이상)")
            if page > total_pages:
                raise ValueError(f"페이지 번호 초과: '{token}' (문서는 {total_pages}페이지)")
            selected.add(page)

    if not selected:
        raise ValueError(f"빈 페이지 범위: '{spec}'")
    return sorted(selected)


@dataclass(frozen=True)
class PdfSourceOptions:
    """문서 변환 옵션 (범위 선택 + 헤더 필터 + 질문 템플릿)."""

    pages: str = ""
    header_filter: str = ""
    question_template: str = ""
    _compiled: re.Pattern[str] | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        header = (self.header_filter or "").strip()
        object.__setattr__(self, "header_filter", header)
        object.__setattr__(self, "question_template", (self.question_template or "").strip())
        if header:
            pattern = header[1:] if header.startswith("!") else header
            try:
                compiled = re.compile(pattern)
            except re.error as exc:
                raise ValueError(f"잘못된 헤더 필터 정규식: '{pattern}' ({exc})") from exc
            object.__setattr__(self, "_compiled", compiled)

    @property
    def exclude_mode(self) -> bool:
        """부정 필터(!접두사) 여부 — 매칭 페이지를 제외한다."""
        return bool(self.header_filter) and self.header_filter.startswith("!")

    def header_matches(self, header: str) -> bool:
        """헤더가 필터를 통과하는지. 필터가 없으면 항상 True."""
        compiled = self._compiled
        if compiled is None:
            return True
        matched = compiled.search(header) is not None
        return (not matched) if self.exclude_mode else matched

    def select_pages(self, total_pages: int) -> list[int] | None:
        """페이지 범위를 문서 크기에 맞춰 해석. None이면 전체."""
        return parse_page_ranges(self.pages, total_pages)

    @property
    def has_question_template(self) -> bool:
        """질문 템플릿 강제 모드 여부 — 헤더 질문 대신 템플릿 질문을 사용한다."""
        return bool(self.question_template)
