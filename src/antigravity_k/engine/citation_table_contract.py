"""Decimal table row contracts for evidence-backed answers."""

import ast
import io
import re
import tokenize
from typing import Final

_ROW_REQUEST: Final = re.compile(
    r"(?:(\d+)\s*(?:행(?:짜리)?\s*표|[- ]?rows?\s+table)|table\s+(?:with\s+)?(\d+)\s+rows?)",
    re.IGNORECASE,
)
_SEPARATOR: Final = re.compile(r"\s*\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)+\|?\s*")


def requested_table_rows(task: str) -> int | None:
    """Return an explicitly numbered data-row requirement, if present."""
    match = _ROW_REQUEST.search(task)
    return int(match.group(1) or match.group(2)) if match else None


def satisfies_table_rows(output: str, expected: int | None, supported_claims: int) -> bool:
    """Count actual Markdown table data rows, excluding fenced examples."""
    if expected is None:
        return True
    if supported_claims < expected:
        return False
    lines = output.splitlines()
    fenced = False
    for index, line in enumerate(lines):
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if fenced or not _SEPARATOR.fullmatch(line) or index == 0 or "|" not in lines[index - 1]:
            continue

        def cells(value: str) -> list[str]:
            return re.split(r"(?<!\\)\|", value.strip().strip("|"))

        if len(cells(lines[index - 1])) != len(cells(line)):
            continue
        rows = 0
        for row in lines[index + 1 :]:
            if "|" not in row or not row.strip().strip("|").strip():
                break
            rows += 1
        if rows == expected:
            return True
    return False


_LINK_REQUEST: Final = re.compile(r"(?:링크\s*(\d+)\s*개|(\d+)\s+(?:source\s+)?links?)", re.IGNORECASE)


def requested_source_links(task: str) -> int | None:
    match = _LINK_REQUEST.search(task)
    return int(match.group(1) or match.group(2)) if match else None


def displayed_urls(output: str) -> set[str]:
    """Collect explicit HTTP destinations, including GFM bare-URL autolinks."""
    return {url.rstrip(")]>.,;\"'") for url in re.findall(r"https?://[^\s<>`]+", output)}


def satisfies_presentation(output: str, task: str, source_urls: dict[str, str]) -> bool:
    """Check explicit source count and accidental HTML in requested syntax cells."""
    expected = requested_source_links(task)
    if expected is not None:
        used_urls = {url for source_id, url in source_urls.items() if f"[citation:{source_id}]" in output and url}
        displayed = displayed_urls(output)
        if len(displayed) > expected or not displayed <= set(source_urls.values()):
            return False
        if len(used_urls | displayed) < expected:
            return False
    if requested_table_rows(task) is not None and re.search(r"문법|syntax", task, re.IGNORECASE):
        if not re.search(r"<br|HTML", task, re.IGNORECASE):
            if any(re.search(r"<br\s*/?>", code, re.IGNORECASE) for code in re.findall(r"`([^`\n]+)`", output)):
                return False
    return not syntax_errors(output, task)


def normalize_syntax_separators(output: str, task: str) -> str:
    """Render accidental HTML separators only between independently valid Python fragments."""
    if not re.search(r"\bpython\b|파이썬", task, re.IGNORECASE) or not re.search(r"문법|syntax", task, re.IGNORECASE):
        return output

    def normalize(match: re.Match[str]) -> str:
        code = match.group(1)
        breaks = list(re.finditer(r"<br\s*/?>", code, re.IGNORECASE))
        if not breaks:
            return match.group(0)
        try:
            ast.parse(code.strip())
        except (SyntaxError, ValueError, RecursionError):
            pass
        else:
            return match.group(0)
        try:
            strings = [
                (token.start[1], token.end[1])
                for token in tokenize.generate_tokens(io.StringIO(code).readline)
                if token.type == tokenize.STRING
            ]
            if any(start <= br.start() < end for br in breaks for start, end in strings):
                return match.group(0)
            fragments = re.split(r"<br\s*/?>", code, flags=re.IGNORECASE)
            for fragment in fragments:
                if not ast.parse(fragment.strip()).body:
                    return match.group(0)
        except (SyntaxError, ValueError, RecursionError, tokenize.TokenError):
            return match.group(0)
        return " → ".join("`" + fragment + "`" for fragment in fragments)

    return "\n".join(
        re.sub(r"(?<!`)`([^`\n]+)`(?!`)", normalize, line) if "|" in line else line for line in output.splitlines()
    )


def render_verified_exception_output(output: str, task: str, source_texts: dict[str, str]) -> str:
    """Keep cited verbatim runtime output outside Python source-code styling."""
    if not re.search(r"\bpython\b|파이썬", task, re.IGNORECASE) or not re.search(r"문법|syntax", task, re.IGNORECASE):
        return output
    pattern = re.compile(r"(?<!`)`([^`\n]+)`(?!`)")
    rendered: list[str] = []
    for row in output.splitlines():
        cited = set(re.findall(r"\[citation:([A-Za-z0-9_-]+)\]", row))
        verified_lines = {line.strip() for source_id in cited for line in source_texts.get(source_id, "").splitlines()}

        def unwrap(match: re.Match[str]) -> str:
            result = match.group(1)
            preceding = re.search(r"(?<!`)`([^`\n]+)`(?!`)\s*(?:→|⇒|->|❌)\s*$", row[: match.start()])
            if preceding is None:
                return match.group(0)
            code = preceding.group(1)
            exception = re.match(r"([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*): .+", result)
            if (
                exception is None
                or not exception.group(1).endswith(("Error", "Exception"))
                or result not in verified_lines
            ):
                return match.group(0)
            try:
                if not ast.parse(code.strip()).body:
                    return match.group(0)
            except (SyntaxError, ValueError, RecursionError):
                return match.group(0)
            try:
                ast.parse(result)
            except (SyntaxError, ValueError, RecursionError):
                return result
            return match.group(0)

        rendered.append(pattern.sub(unwrap, row) if "|" in row else row)
    return "\n".join(rendered)


def _missing_syntax_examples(output: str) -> tuple[str, ...]:
    errors: list[str] = []
    syntax_columns: list[int] = []
    lines = output.splitlines()
    for index, row in enumerate(lines):
        if "|" not in row:
            syntax_columns = []
            continue
        cells = re.split(r"(?<!\\)\|", row.strip().strip("|"))
        if index + 1 < len(lines) and _SEPARATOR.fullmatch(lines[index + 1]):
            syntax_columns = [i for i, cell in enumerate(cells) if re.search(r"문법|syntax", cell, re.IGNORECASE)]
            continue
        if _SEPARATOR.fullmatch(row):
            continue
        targets = syntax_columns
        if cells and re.search(r"문법|syntax", cells[0], re.IGNORECASE):
            targets = list(range(1, len(cells)))
        for column in targets:
            if column < len(cells) and re.search(r"`[^`\n]+`", cells[column]):
                continue
            # Citation identity is checked separately by the citation evaluator.
            plain = re.sub(r"\[citation:[A-Za-z0-9_-]+\]", "", cells[column]).strip() if column < len(cells) else ""
            try:
                valid_plain = bool(ast.parse(plain).body)
            except (SyntaxError, ValueError, RecursionError):
                valid_plain = False
            if not valid_plain:
                errors.append("Requested syntax cell lacks a valid code example")
    return tuple(errors)


def syntax_errors(output: str, task: str) -> tuple[str, ...]:
    """Validate requested Python examples without executing generated code."""
    if not re.search(r"\bpython\b|파이썬", task, re.IGNORECASE) or not re.search(r"문법|syntax", task, re.IGNORECASE):
        return ()
    errors: list[str] = list(_missing_syntax_examples(output))
    for row in output.splitlines():
        if "|" not in row:
            continue
        for code in re.findall(r"`([^`\n]+)`", row):
            try:
                ast.parse(code.strip())
            except (SyntaxError, ValueError, RecursionError) as error:
                errors.append(f"{code[:160]}: {str(error)[:160]}")
    return tuple(errors)


CITATION_FAILURE_MESSAGE: Final = (
    "웹 검색은 실행했지만, 검색 근거와 요청한 표·예시·출처 형식을 함께 충족하는 답변을 "
    "검증하지 못했습니다. 검증에 실패한 초안은 최종 답변으로 제공하지 않습니다. "
    "(citation_validation_failed)"
)


def requires_source_verification(task: str) -> bool:
    return bool(
        re.search(r"web_search|웹\s*검색|\bsearch\b", task, re.IGNORECASE)
        and re.search(r"출처|공식|검증|확인|\bsources?\b|official|verif", task, re.IGNORECASE)
    )


def unwrap_verified_citation_metadata(output: str, source_ids: set[str]) -> str:
    """Remove code styling only from standalone, verified citation metadata."""

    def unwrap(match: re.Match[str]) -> str:
        identifiers = set(re.findall(r"\[citation:([A-Za-z0-9_-]+)\]", match.group(1)))
        return match.group(1) if identifiers <= source_ids else match.group(0)

    return re.sub(r"(?<!`)`((?:\[citation:[A-Za-z0-9_-]+\][ \t]*)+)`(?!`)", unwrap, output)
