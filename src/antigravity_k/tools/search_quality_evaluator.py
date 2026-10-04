from __future__ import annotations

import html
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from types import MappingProxyType
from typing import Final
from urllib.parse import urlsplit

from pydantic import JsonValue, TypeAdapter, ValidationError

from .search_conflicts import source_conflict_sets
from .web_search_models import SearchResult
from .web_search_quality import canonicalize_url, source_id_for_url

_CITATION_PATTERN = re.compile(r"\[citation:([A-Za-z0-9][A-Za-z0-9_-]*)\]")
_CLAIM_SPLIT_PATTERN = re.compile(r"(?<=[.!?。！？])\s+(?!\[citation:)|\n+")
_TABLE_SEPARATOR_PATTERN: Final = re.compile(r"\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*")
_SOURCE_LINK_FOOTER_PATTERN: Final = re.compile(
    r"출처:\s*(?:\[[^\]]+\]\(<https?://[^>\s]+>\)(?:,\s*)?)+",
)
_SOURCE_LINK_PATTERN: Final = re.compile(r"\[([^\]]+)\]\(<(https?://[^>\s]+)>\)")
_UNTRUSTED_BLOCK_PATTERN = re.compile(
    r"\[untrusted_web_content\]\s*(.*?)\s*\[/untrusted_web_content\]",
    re.DOTALL,
)
_TOKEN_PATTERN: Final[re.Pattern[str]] = re.compile(r"[^\W_]+", re.UNICODE)
_ASCII_ANCHOR_PATTERN: Final[re.Pattern[str]] = re.compile(r"[a-z]+|\d+", re.IGNORECASE)
_CJK_PATTERN: Final[re.Pattern[str]] = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7a3]")
_CROSS_LANGUAGE_MIN_OVERLAP: Final = 0.25
_CROSS_LANGUAGE_MIN_SHARED_ANCHORS: Final = 3
_CONFLICT_MARKERS = frozenset(
    {
        "conflict",
        "contradict",
        "disagree",
        "disputed",
        "uncertain",
        "different",
        "상충",
        "불일치",
        "다르",
        "불확실",
        "논쟁",
    },
)
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "with",
        "그리고",
        "대한",
        "또한",
        "및",
    },
)
_URL_LIST_ADAPTER: Final[TypeAdapter[list[JsonValue]]] = TypeAdapter(list[JsonValue])
_GRADED_RELEVANCE_ADAPTER: Final[TypeAdapter[dict[str, JsonValue]]] = TypeAdapter(dict[str, JsonValue])


@dataclass(frozen=True, slots=True)
class SearchGoldenCase:
    case_id: str
    query: str
    relevant_urls: tuple[str, ...]
    graded_relevance: tuple[tuple[str, int], ...] = ()

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> SearchGoldenCase:
        case_id = payload.get("case_id")
        query = payload.get("query")
        relevant_urls = payload.get("relevant_urls")
        graded_relevance = payload.get("graded_relevance", {})
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError("golden case requires a non-empty case_id")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("golden case requires a non-empty query")
        try:
            relevant_url_values = _URL_LIST_ADAPTER.validate_python(relevant_urls)
        except ValidationError:
            raise ValueError("golden case relevant_urls must be a list of strings")
        validated_urls: list[str] = []
        for url in relevant_url_values:
            if not isinstance(url, str):
                raise ValueError("golden case relevant_urls must be a list of strings")
            validated_urls.append(url)
        canonical_urls = tuple(filter(None, (canonicalize_url(url) for url in validated_urls)))
        if not canonical_urls:
            raise ValueError("golden case requires at least one valid relevant URL")
        try:
            graded_values = _GRADED_RELEVANCE_ADAPTER.validate_python(graded_relevance)
        except ValidationError as exc:
            raise TypeError("golden case graded_relevance must be an object") from exc
        grades: dict[str, int] = {url: 1 for url in canonical_urls}
        for url, grade_value in graded_values.items():
            grade = grade_value
            if not isinstance(grade, int) or isinstance(grade, bool):
                raise TypeError("golden case graded_relevance values must be integer grades")
            canonical = canonicalize_url(url)
            if not canonical or grade < 0:
                raise ValueError("golden case graded_relevance requires valid non-negative grades")
            grades[canonical] = grade
        positive_urls = tuple(url for url, grade in grades.items() if grade > 0)
        if not positive_urls:
            raise ValueError("golden case requires at least one positive relevance grade")
        return cls(
            case_id=case_id,
            query=query,
            relevant_urls=positive_urls,
            graded_relevance=tuple(grades.items()),
        )


@dataclass(frozen=True, slots=True)
class SearchQualityReport:
    case_id: str
    k: int
    retrieved_count: int
    relevant_count: int
    retrieved_relevant: int
    precision_at_k: float
    recall_at_k: float
    reciprocal_rank: float
    ndcg_at_k: float
    domain_diversity: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CitationSource:
    source_id: str
    title: str
    text: str
    url: str = ""
    freshness: str = ""

    @classmethod
    def from_search_result(cls, result: SearchResult) -> CitationSource:
        source_id = result.source_id or source_id_for_url(result.url)
        return cls(
            source_id=source_id,
            title=result.title,
            text=result.snippet,
            url=result.canonical_url or canonicalize_url(result.url),
            freshness=result.timestamp,
        )


@dataclass(frozen=True, slots=True)
class ClaimEvaluation:
    claim: str
    cited_source_ids: tuple[str, ...]
    supported_source_ids: tuple[str, ...]
    unknown_source_ids: tuple[str, ...]
    conflicting_source_ids: tuple[str, ...]
    best_overlap: float
    supported: bool
    conflict_acknowledged: bool


@dataclass(frozen=True, slots=True)
class CitationEvaluationReport:
    claims: tuple[ClaimEvaluation, ...]

    @property
    def claim_count(self) -> int:
        return len(self.claims)

    @property
    def supported_claim_count(self) -> int:
        return sum(claim.supported for claim in self.claims)

    @property
    def unsupported_claim_count(self) -> int:
        return self.claim_count - self.supported_claim_count

    @property
    def citation_coverage(self) -> float:
        if not self.claims:
            return 0.0
        return self.supported_claim_count / self.claim_count

    @property
    def cited_claim_count(self) -> int:
        return sum(bool(claim.cited_source_ids) for claim in self.claims)

    @property
    def citation_precision(self) -> float:
        if not self.cited_claim_count:
            return 0.0
        return self.supported_claim_count / self.cited_claim_count

    @property
    def unknown_citation_count(self) -> int:
        return sum(len(claim.unknown_source_ids) for claim in self.claims)

    @property
    def conflicted_claim_count(self) -> int:
        return sum(bool(claim.conflicting_source_ids) for claim in self.claims)

    @property
    def unacknowledged_conflict_count(self) -> int:
        return sum(bool(claim.conflicting_source_ids) and not claim.conflict_acknowledged for claim in self.claims)

    @property
    def conflict_rate(self) -> float:
        if not self.claims:
            return 0.0
        return self.conflicted_claim_count / self.claim_count

    def to_dict(self) -> dict[str, object]:
        return {
            "claim_count": self.claim_count,
            "supported_claim_count": self.supported_claim_count,
            "unsupported_claim_count": self.unsupported_claim_count,
            "citation_coverage": self.citation_coverage,
            "citation_precision": self.citation_precision,
            "unknown_citation_count": self.unknown_citation_count,
            "conflicted_claim_count": self.conflicted_claim_count,
            "unacknowledged_conflict_count": self.unacknowledged_conflict_count,
            "conflict_rate": self.conflict_rate,
            "claims": [asdict(claim) for claim in self.claims],
        }


def evaluate_golden_case(
    case: SearchGoldenCase,
    results: Sequence[SearchResult],
    k: int | None = None,
) -> SearchQualityReport:
    limit = len(results) if k is None else k
    if limit <= 0:
        raise ValueError("k must be positive")

    relevant_urls = {canonical for url in case.relevant_urls if (canonical := canonicalize_url(url))}
    retrieved_urls: list[str] = []
    seen_urls: set[str] = set()
    for result in results:
        canonical = canonicalize_url(result.url)
        if canonical and canonical not in seen_urls:
            retrieved_urls.append(canonical)
            seen_urls.add(canonical)
        if len(retrieved_urls) == limit:
            break

    relevance_grades = dict(case.graded_relevance) or {url: 1 for url in relevant_urls}
    relevance = [relevance_grades.get(url, 0) > 0 for url in retrieved_urls]
    retrieved_relevant = sum(relevance)
    precision = retrieved_relevant / limit if limit else 0.0
    recall = retrieved_relevant / len(relevant_urls) if relevant_urls else 0.0
    reciprocal_rank = next(
        (1.0 / rank for rank, is_relevant in enumerate(relevance, start=1) if is_relevant),
        0.0,
    )
    dcg = sum(
        relevance_grades[url] / math.log2(rank + 1)
        for rank, url in enumerate(retrieved_urls, start=1)
        if relevance_grades.get(url, 0) > 0
    )
    ideal_grades = sorted((grade for grade in relevance_grades.values() if grade > 0), reverse=True)[:limit]
    ideal_dcg = sum(grade / math.log2(rank + 1) for rank, grade in enumerate(ideal_grades, start=1))
    ndcg = dcg / ideal_dcg if ideal_dcg else 0.0
    domains = {urlsplit(url).hostname for url in retrieved_urls if urlsplit(url).hostname}
    domain_diversity = len(domains) / len(retrieved_urls) if retrieved_urls else 0.0
    return SearchQualityReport(
        case_id=case.case_id,
        k=limit,
        retrieved_count=len(retrieved_urls),
        relevant_count=len(relevant_urls),
        retrieved_relevant=retrieved_relevant,
        precision_at_k=precision,
        recall_at_k=recall,
        reciprocal_rank=reciprocal_rank,
        ndcg_at_k=ndcg,
        domain_diversity=domain_diversity,
    )


def citation_sources_from_results(results: Iterable[SearchResult]) -> tuple[CitationSource, ...]:
    return tuple(CitationSource.from_search_result(result) for result in results if result.url)


def citation_sources_from_context(context: str) -> tuple[CitationSource, ...]:
    matches = tuple(_CITATION_PATTERN.finditer(context))
    sources: list[CitationSource] = []
    seen: set[str] = set()
    for index, match in enumerate(matches):
        source_id = match.group(1)
        if source_id in seen:
            continue
        seen.add(source_id)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(context)
        block = context[match.end() : end]
        title_match = re.search(r"\*\*(.*?)\*\*", block, re.DOTALL)
        title = _clean_context_fragment(title_match.group(1) if title_match else "")
        evidence_blocks = _UNTRUSTED_BLOCK_PATTERN.findall(block)
        evidence = evidence_blocks[1] if len(evidence_blocks) > 1 else (evidence_blocks[0] if evidence_blocks else "")
        metadata = _UNTRUSTED_BLOCK_PATTERN.sub("", block)
        url_match = re.search(r"(?m)^\s*🔗\s+(https?://[^\s)\]]+)", metadata)
        url = canonicalize_url(url_match.group(1).rstrip(".,")) if url_match else ""
        if title or evidence:
            sources.append(
                CitationSource(
                    source_id=source_id,
                    title=title,
                    text=html.unescape(evidence).strip(),
                    url=url,
                ),
            )
    return tuple(sources)


def _citation_claim_content(response_text: str, sources: tuple[CitationSource, ...]) -> str:
    lines = response_text.splitlines()
    known_urls = {
        canonicalize_url(source.url).replace("<", "%3C").replace(">", "%3E") for source in sources if source.url
    }
    claims: list[str] = []
    for index, line in enumerate(lines):
        is_table_header = (
            "|" in line and index + 1 < len(lines) and _TABLE_SEPARATOR_PATTERN.fullmatch(lines[index + 1])
        )
        is_source_footer = _SOURCE_LINK_FOOTER_PATTERN.fullmatch(line) and all(
            url in known_urls and label == urlsplit(url).hostname for label, url in _SOURCE_LINK_PATTERN.findall(line)
        )
        if is_table_header or _TABLE_SEPARATOR_PATTERN.fullmatch(line) or is_source_footer:
            continue
        claims.append(line)
    return "\n".join(claims)


def evaluate_citations(
    response_text: str,
    sources: Iterable[CitationSource],
    min_overlap: float = 0.6,
    conflict_sets: Iterable[Iterable[str]] = (),
) -> CitationEvaluationReport:
    if not 0.0 < min_overlap <= 1.0:
        raise ValueError("min_overlap must be greater than 0 and at most 1")
    source_values = tuple(sources)
    source_map: Mapping[str, CitationSource] = MappingProxyType(
        {source.source_id: source for source in source_values if source.source_id},
    )
    normalized_conflict_sets = tuple(
        frozenset(source_id for source_id in group if source_id in source_map)
        for group in (*tuple(conflict_sets), *source_conflict_sets(source_values))
    )
    claims: list[ClaimEvaluation] = []
    prior_claim_acknowledged_conflict = False
    for raw_claim in _CLAIM_SPLIT_PATTERN.split(_citation_claim_content(response_text, source_values)):
        citation_ids: list[str] = [match.group(1) for match in _CITATION_PATTERN.finditer(raw_claim)]
        cited_ids: tuple[str, ...] = tuple(dict.fromkeys(citation_ids))
        claim = _CITATION_PATTERN.sub("", raw_claim).strip(" \t-*•")
        claim_tokens = _tokens(claim)
        if len(claim_tokens) < 2:
            continue
        claim_acknowledges_conflict = _has_conflict_marker(claim)
        supported_ids: list[str] = []
        unknown_ids = tuple(source_id for source_id in cited_ids if source_id not in source_map)
        conflicting_ids = _conflicting_source_ids(cited_ids, normalized_conflict_sets)
        best_overlap = 0.0
        for source_id in cited_ids:
            source = source_map.get(source_id)
            if source is None:
                continue
            source_text = f"{source.title} {source.text}"
            source_tokens = _tokens(source_text)
            overlap = _overlap(claim_tokens, source_tokens)
            best_overlap = max(best_overlap, overlap)
            if _claim_is_supported(claim, source_text, claim_tokens, source_tokens, overlap, min_overlap):
                supported_ids.append(source_id)
        claims.append(
            ClaimEvaluation(
                claim=claim,
                cited_source_ids=cited_ids,
                supported_source_ids=tuple(supported_ids),
                unknown_source_ids=unknown_ids,
                conflicting_source_ids=conflicting_ids,
                best_overlap=best_overlap,
                supported=bool(supported_ids),
                conflict_acknowledged=claim_acknowledges_conflict
                or (prior_claim_acknowledged_conflict and bool(conflicting_ids)),
            ),
        )
        prior_claim_acknowledged_conflict = claim_acknowledges_conflict
    return CitationEvaluationReport(claims=tuple(claims))


def _tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for token_match in _TOKEN_PATTERN.finditer(text):
        token = token_match.group().casefold()
        if token not in _STOPWORDS and (len(token) >= 2 or token.isdigit()):
            tokens.add(token)
        for anchor_match in _ASCII_ANCHOR_PATTERN.finditer(token):
            anchor = anchor_match.group()
            if anchor not in _STOPWORDS and (len(anchor) >= 2 or anchor.isdigit()):
                tokens.add(anchor)
    return tokens


def _overlap(claim_tokens: set[str], source_tokens: set[str]) -> float:
    return len(claim_tokens & source_tokens) / len(claim_tokens) if claim_tokens else 0.0


def _claim_is_supported(
    claim: str,
    source_text: str,
    claim_tokens: set[str],
    source_tokens: set[str],
    overlap: float,
    min_overlap: float,
) -> bool:
    if overlap >= min_overlap:
        return True
    cross_language = bool(_CJK_PATTERN.search(claim)) != bool(_CJK_PATTERN.search(source_text))
    return (
        cross_language
        and overlap >= min(min_overlap, _CROSS_LANGUAGE_MIN_OVERLAP)
        and len(claim_tokens & source_tokens) >= _CROSS_LANGUAGE_MIN_SHARED_ANCHORS
    )


def _conflicting_source_ids(
    cited_ids: Sequence[str],
    conflict_sets: Sequence[frozenset[str]],
) -> tuple[str, ...]:
    conflicting: list[str] = []
    for conflict_set in conflict_sets:
        matched = [source_id for source_id in cited_ids if source_id in conflict_set]
        if len(matched) > 1:
            conflicting.extend(matched)
    return tuple(dict.fromkeys(conflicting))


def _has_conflict_marker(claim: str) -> bool:
    tokens = _tokens(claim)
    return bool(tokens & _CONFLICT_MARKERS)


def _clean_context_fragment(value: str) -> str:
    return html.unescape(value.replace("[untrusted_web_content]", "").replace("[/untrusted_web_content]", "")).strip()


__all__ = [
    "CitationEvaluationReport",
    "CitationSource",
    "ClaimEvaluation",
    "SearchGoldenCase",
    "SearchQualityReport",
    "citation_sources_from_context",
    "citation_sources_from_results",
    "evaluate_citations",
    "evaluate_golden_case",
]
