"""NX-01: structured retention of explicit user constraints across compactions.

The EX-05 soft-max auto-compact (Decision A) bounds conversation memory by
replacing older messages with a single store-generated summary.  Before this
module the summary itself was *not* authoritative state: on the next
compaction the previous summary was dropped (its role is ``system``, so the
deterministic fallback skipped it) and the earliest user constraints
("네트워크 사용 금지", approval requirements, ...) disappeared from the
conversation after ~123 appends.

This module makes the retained decisions explicit and durable:

* only messages authored by the **user** can create a retained constraint
  (tool/assistant text can never be promoted to policy authority),
* every constraint has a stable id, a kind, a status (``active`` /
  ``superseded``) and its source message id,
* a later explicit user change supersedes an earlier item **without deleting**
  the earlier item (history is preserved, status is what changes),
* the rendered prompt view is bounded by an explicit character budget; when
  the budget forces prompt-side omission, the omission is stated in the
  summary text instead of being silent, and the structured record keeps the
  full set.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Final, Iterable, Mapping, Sequence

# ── Schema / budget contract ────────────────────────────────────────────

SUMMARY_SCHEMA_VERSION: Final[str] = "agk.summary.v1"
MARKER_PREFIX: Final[str] = "<!-- agk-summary "
MARKER_SUFFIX: Final[str] = " -->"
MARKER_RE: Final[re.Pattern[str]] = re.compile(r"<!--\s*agk-summary\s+(?P<body>[^>]*?)-->")

SUMMARY_TEXT_BUDGET_CHARS: Final[int] = 4000
CONSTRAINT_LINE_MAX_CHARS: Final[int] = 160
CARRIED_SUMMARY_MAX_CHARS: Final[int] = 900
CONSTRAINTS_SECTION_MAX_CHARS: Final[int] = 2400
SUPERSEDED_RENDER_MAX: Final[int] = 3
MAX_ACTIVE_CONSTRAINTS: Final[int] = 128
MAX_SUPERSEDED_CONSTRAINTS: Final[int] = 32
MAX_SUMMARIZED_RANGES: Final[int] = 8

CONSTRAINT_KIND_REQUIREMENT: Final[str] = "requirement"
CONSTRAINT_KIND_PROHIBITION: Final[str] = "prohibition"
CONSTRAINT_KIND_APPROVAL: Final[str] = "approval"
CONSTRAINT_KINDS: Final[tuple[str, ...]] = (
    CONSTRAINT_KIND_REQUIREMENT,
    CONSTRAINT_KIND_PROHIBITION,
    CONSTRAINT_KIND_APPROVAL,
)

STATUS_ACTIVE: Final[str] = "active"
STATUS_SUPERSEDED: Final[str] = "superseded"
CONSTRAINT_STATUSES: Final[tuple[str, ...]] = (STATUS_ACTIVE, STATUS_SUPERSEDED)

# Cue lexicon (deterministic, Korean + English).  Priority order decides the
# kind when a message matches several groups.
_PROHIBITION_CUES: Final[tuple[str, ...]] = (
    "금지",
    "하지 마",
    "하지마",
    "하지 말",
    "쓰지 마",
    "쓰지마",
    "사용하지",
    "허용하지",
    "차단",
    "제한적",
    "오프라인",
    "offline",
    "do not",
    "don't",
    "never",
    "must not",
    "forbid",
    "block",
)
_APPROVAL_CUES: Final[tuple[str, ...]] = (
    "승인",
    "허가",
    "동의",
    "허락",
    "먼저 물어",
    "확인 후",
    "물어보고",
    "approval",
    "approve",
    "permission",
    "ask before",
    "confirm before",
)

_REQUIREMENT_CUES: Final[tuple[str, ...]] = (
    "반드시",
    "필수",
    "유지",
    "제한",
    "한정",
    "only",
    "must",
    "require",
    "required",
    "always",
    "keep",
)

_SUPERSEDE_CUES: Final[tuple[str, ...]] = (
    "더 이상",
    "더이상",
    "취소",
    "무효",
    "철회",
    "해제",
    "이제부터",
    "이제는",
    "변경",
    "대신",
    "없앴",
    "풀어",
    "no longer",
    "cancel",
    "revoke",
    "supersede",
    "instead",
    "override",
    "now allowed",
)

_STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "you",
        "your",
        "from",
        "not",
        "use",
        "사용",
        "그리고",
        "그러나",
        "하는",
        "하도록",
        "해주세요",
        "주세요",
        "이거",
        "저거",
        "지금",
    }
)

_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"[0-9a-z가-힣_]+")
_WS_RE: Final[re.Pattern[str]] = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return _WS_RE.sub(" ", (text or "").strip()).lower()


def constraint_id(text: str) -> str:
    """Stable id for a constraint statement (same text -> same id)."""
    # NX-10: bandit B324(약한 해시) — 이 용도는 **보안이 아니다**(같은 문장에 같은 id 를 주는
    # 결정론적 지문). `usedforsecurity=False` 로 의도를 명시한다. sha256 으로 바꾸면
    # 이미 저장된 제약의 id 가 전부 달라진다(마이그레이션 없음).
    digest = hashlib.sha1(_normalize(text).encode("utf-8"), usedforsecurity=False).hexdigest()
    return f"c_{digest[:10]}"


def significant_tokens(text: str) -> frozenset[str]:
    """Tokens used only for deterministic supersede matching (no NLP claim)."""
    return frozenset(
        token for token in _TOKEN_RE.findall(_normalize(text)) if len(token) >= 2 and token not in _STOPWORDS
    )


def detect_kind(text: str) -> str | None:
    """Return the constraint kind implied by explicit cues, else ``None``."""
    normalized = _normalize(text)
    for cue in _PROHIBITION_CUES:
        if cue in normalized:
            return CONSTRAINT_KIND_PROHIBITION
    for cue in _APPROVAL_CUES:
        if cue in normalized:
            return CONSTRAINT_KIND_APPROVAL
    for cue in _REQUIREMENT_CUES:
        if cue in normalized:
            return CONSTRAINT_KIND_REQUIREMENT
    return None


def detect_supersede(text: str) -> str | None:
    """Return the supersede cue found in a user message, else ``None``."""
    normalized = _normalize(text)
    for cue in _SUPERSEDE_CUES:
        if cue in normalized:
            return cue
    return None


@dataclass(frozen=True)
class Constraint:
    """One retained user constraint with provenance and lifecycle status."""

    id: str
    kind: str
    text: str
    status: str = STATUS_ACTIVE
    source_message_id: str = ""
    source_revision: int = 0
    superseded_by: str | None = None
    superseded_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "text": self.text,
            "status": self.status,
            "source_message_id": self.source_message_id,
            "source_revision": self.source_revision,
            "superseded_by": self.superseded_by,
            "superseded_reason": self.superseded_reason,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Constraint | None:
        text = str(data.get("text") or "").strip()
        if not text:
            return None
        kind = str(data.get("kind") or CONSTRAINT_KIND_REQUIREMENT)
        if kind not in CONSTRAINT_KINDS:
            kind = CONSTRAINT_KIND_REQUIREMENT
        status = str(data.get("status") or STATUS_ACTIVE)
        if status not in CONSTRAINT_STATUSES:
            status = STATUS_ACTIVE
        superseded_by = data.get("superseded_by")
        superseded_reason = data.get("superseded_reason")
        return cls(
            id=str(data.get("id") or constraint_id(text)),
            kind=kind,
            text=text[:CONSTRAINT_LINE_MAX_CHARS],
            status=status,
            source_message_id=str(data.get("source_message_id") or ""),
            source_revision=int(data.get("source_revision") or 0),
            superseded_by=str(superseded_by) if isinstance(superseded_by, str) and superseded_by else None,
            superseded_reason=str(superseded_reason)
            if isinstance(superseded_reason, str) and superseded_reason
            else None,
        )


@dataclass
class SummaryMemory:
    """Durable structured state carried across compaction generations."""

    schema: str = SUMMARY_SCHEMA_VERSION
    generation: int = 0
    constraints: list[Constraint] = field(default_factory=list)
    summarized_ranges: list[dict[str, Any]] = field(default_factory=list)
    carried_summary: str = ""

    # ── query helpers ───────────────────────────────────────────────────
    def active_constraints(self) -> list[Constraint]:
        return [c for c in self.constraints if c.status == STATUS_ACTIVE]

    def superseded_constraints(self) -> list[Constraint]:
        return [c for c in self.constraints if c.status == STATUS_SUPERSEDED]

    def find(self, text: str) -> Constraint | None:
        target = constraint_id(text)
        for constraint in self.constraints:
            if constraint.id == target:
                return constraint
        return None

    # ── serialisation ───────────────────────────────────────────────────
    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "generation": self.generation,
            "constraints": [c.to_dict() for c in self.constraints],
            "summarized_ranges": [dict(r) for r in self.summarized_ranges],
            "carried_summary": self.carried_summary,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> SummaryMemory:
        """Load memory, tolerating legacy records that have no such field."""
        if not isinstance(data, Mapping):
            return cls()
        raw_schema = data.get("schema")
        # Unknown/newer schema: keep the record readable but start from a clean
        # structured state instead of guessing at semantics we do not own.
        if isinstance(raw_schema, str) and raw_schema and raw_schema != SUMMARY_SCHEMA_VERSION:
            return cls(carried_summary=str(data.get("carried_summary") or "")[:CARRIED_SUMMARY_MAX_CHARS])
        constraints: list[Constraint] = []
        for item in data.get("constraints") or []:
            if isinstance(item, Mapping):
                parsed = Constraint.from_dict(item)
                if parsed is not None:
                    constraints.append(parsed)
        ranges: list[dict[str, Any]] = []
        for item in data.get("summarized_ranges") or []:
            if isinstance(item, Mapping):
                ranges.append(dict(item))
        generation = data.get("generation")
        return cls(
            schema=SUMMARY_SCHEMA_VERSION,
            generation=int(generation) if isinstance(generation, int) else 0,
            constraints=constraints,
            summarized_ranges=ranges,
            carried_summary=str(data.get("carried_summary") or "")[:CARRIED_SUMMARY_MAX_CHARS],
        )


def update_from_messages(
    memory: SummaryMemory,
    messages: Iterable[Mapping[str, str]],
    *,
    revision: int,
) -> None:
    """Fold ``messages`` into ``memory`` in order (user-authored only).

    * user text matching a cue becomes a constraint with a stable id,
    * a user message that explicitly supersedes an earlier item flips that
      item's status to ``superseded`` (the item itself is never removed),
    * text from ``system`` / ``tool`` / ``assistant`` roles can never create a
      constraint or supersede one.
    """
    for message in messages:
        role = str(message.get("role") or "")
        content = str(message.get("content") or "")
        if role != "user" or not content.strip():
            continue
        message_id = str(message.get("id") or "")
        snippet = _WS_RE.sub(" ", content.strip())[:CONSTRAINT_LINE_MAX_CHARS]
        kind = detect_kind(content)
        incoming_id = constraint_id(content) if kind else None
        cue = detect_supersede(content)
        if cue is not None:
            tokens = significant_tokens(content)
            superseded: list[Constraint] = []
            for constraint in memory.constraints:
                if constraint.status != STATUS_ACTIVE:
                    continue
                if incoming_id is not None and constraint.id == incoming_id:
                    continue
                if tokens and tokens & significant_tokens(constraint.text):
                    superseded.append(constraint)
            if superseded:
                superseded_ids = {c.id for c in superseded}
                memory.constraints = [
                    (
                        Constraint(
                            id=c.id,
                            kind=c.kind,
                            text=c.text,
                            status=STATUS_SUPERSEDED,
                            source_message_id=c.source_message_id,
                            source_revision=c.source_revision,
                            superseded_by=message_id or "user_turn",
                            superseded_reason=cue,
                        )
                        if c.id in superseded_ids
                        else c
                    )
                    for c in memory.constraints
                ]
        if kind is None:
            continue
        if incoming_id is not None and any(c.id == incoming_id for c in memory.constraints):
            continue
        memory.constraints.append(
            Constraint(
                id=incoming_id or constraint_id(content),
                kind=kind,
                text=snippet,
                status=STATUS_ACTIVE,
                source_message_id=message_id,
                source_revision=int(revision),
            )
        )
    _trim(memory)


def _trim(memory: SummaryMemory) -> None:
    """Bound stored structured state without dropping active constraints."""
    active = memory.active_constraints()
    superseded = memory.superseded_constraints()
    if len(active) > MAX_ACTIVE_CONSTRAINTS:
        active = active[-MAX_ACTIVE_CONSTRAINTS:]
    if len(superseded) > MAX_SUPERSEDED_CONSTRAINTS:
        superseded = superseded[-MAX_SUPERSEDED_CONSTRAINTS:]
    memory.constraints = active + superseded
    if len(memory.summarized_ranges) > MAX_SUMMARIZED_RANGES:
        memory.summarized_ranges = memory.summarized_ranges[-MAX_SUMMARIZED_RANGES:]
    memory.carried_summary = memory.carried_summary[:CARRIED_SUMMARY_MAX_CHARS]


def record_generation(
    memory: SummaryMemory,
    *,
    revision: int,
    message_count: int,
    source_ids: Sequence[str],
) -> None:
    """Record one compaction generation and the range it covered."""
    memory.generation += 1
    memory.summarized_ranges.append(
        {
            "generation": memory.generation,
            "revision": int(revision),
            "message_count": int(message_count),
            "first_message_id": source_ids[0] if source_ids else "",
            "last_message_id": source_ids[-1] if source_ids else "",
        }
    )
    _trim(memory)


def render_constraint_block(memory: SummaryMemory, *, budget: int = CONSTRAINTS_SECTION_MAX_CHARS) -> str:
    """Deterministic, budgeted prompt view of the retained constraints.

    Active items are rendered newest-last and are the last thing to be
    truncated; any prompt-side omission is stated explicitly.
    """
    active = memory.active_constraints()
    superseded = memory.superseded_constraints()[-SUPERSEDED_RENDER_MAX:]
    if not active and not superseded:
        return ""
    lines: list[str] = ["[보존된 사용자 제약 (구조화)]"]
    omitted = 0
    used = len(lines[0])
    for constraint in active:
        line = f"- ({constraint.id}) {_label(constraint.kind)}: {constraint.text}"[:CONSTRAINT_LINE_MAX_CHARS]
        cost = len(line) + 1
        if used + cost > budget:
            omitted += 1
            continue
        lines.append(line)
        used += cost
    for constraint in superseded:
        line = f"- ({constraint.id}) {_label(constraint.kind)} [SUPERSEDED by {constraint.superseded_by or '?'}]: {constraint.text}"
        cost = len(line[:CONSTRAINT_LINE_MAX_CHARS]) + 1
        if used + cost > budget:
            omitted += 1
            continue
        lines.append(line[:CONSTRAINT_LINE_MAX_CHARS])
        used += cost
    if omitted:
        lines.append(
            f"[예산 초과로 prompt 표시에서 생략된 항목 {omitted}개 — 구조화 저장소에는 유지됨 (schema={memory.schema})]"
        )
    return "\n".join(lines)


def _label(kind: str) -> str:
    return {
        CONSTRAINT_KIND_PROHIBITION: "금지",
        CONSTRAINT_KIND_APPROVAL: "승인조건",
        CONSTRAINT_KIND_REQUIREMENT: "요구",
    }.get(kind, kind)


def render_marker(memory: SummaryMemory) -> str:
    """Distinguishable metadata line that identifies a store-generated summary.

    Compact on purpose: this line is part of the prompt budget on every
    generation, so the terse ``key=value`` form is used instead of prose.
    """
    return (
        f"{MARKER_PREFIX}schema={memory.schema} g={memory.generation} "
        f"c={len(memory.constraints)} a={len(memory.active_constraints())} "
        f"b={SUMMARY_TEXT_BUDGET_CHARS}{MARKER_SUFFIX}"
    )


def parse_marker(text: str) -> dict[str, str] | None:
    """Parse a store-generated summary marker (``None`` for legacy/summary-less text)."""
    match = MARKER_RE.search(text or "")
    if match is None:
        return None
    parsed: dict[str, str] = {}
    for chunk in match.group("body").split():
        if "=" in chunk:
            key, _, value = chunk.partition("=")
            parsed[key] = value
    return parsed


def is_store_generated_summary(text: str) -> bool:
    """True when ``text`` carries this store's summary marker."""
    return parse_marker(text) is not None


_SECTION_HEADERS: Final[tuple[str, ...]] = (
    "[보존된 사용자 제약 (구조화)]",
    "[이전 압축 요약 — 보존]",
)
_DROP_PREFIXES: Final[tuple[str, ...]] = (
    "[예산 초과로 prompt 표시에서 생략된",
    "[이전 압축 요약 — 예산 초과로 생략",
    # Nested generation headers would otherwise stack one per compaction.
    "[대화 요약 — ",
)


def carryover_prose(text: str) -> str:
    """Return only the prose of a previous store summary for re-carryover.

    Store scaffolding (schema marker, the structured constraint section, the
    nested carryover header and budget notices) is stripped so prose does not
    accumulate generation over generation: those parts are re-rendered from the
    structured state instead of being copied as text.
    """
    kept: list[str] = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if MARKER_RE.search(stripped) and stripped.startswith(MARKER_PREFIX):
            continue
        if any(stripped.startswith(header) for header in _SECTION_HEADERS):
            continue
        if any(stripped.startswith(prefix) for prefix in _DROP_PREFIXES):
            continue
        kept.append(line.rstrip())
    return "\n".join(kept)[:CARRIED_SUMMARY_MAX_CHARS]


def compose_summary(
    *,
    header: str,
    memory: SummaryMemory,
    carryover: str,
    body: str,
    budget: int = SUMMARY_TEXT_BUDGET_CHARS,
    marker: str = "",
) -> str:
    """Assemble header + carryover + constraints + body under a finite budget.

    Section order is deliberate: retained constraints survive truncation for the
    longest, then the carried-over previous summary, then new prose.  ``marker``
    is the store-owned schema line; legacy callers pass an empty string.
    """
    constraint_block = render_constraint_block(memory)
    sections: list[str] = [header]
    used = len(header) + len(marker) + 2

    if constraint_block:
        sections.append(constraint_block)
        used += len(constraint_block) + 1
    carried = (carryover or "").strip()[:CARRIED_SUMMARY_MAX_CHARS]
    if carried:
        section = f"[이전 압축 요약 — 보존]\n{carried}"
        remaining = budget - used
        if remaining > 64:
            sections.append(section[:remaining])
            used += min(len(section), remaining) + 1
        else:
            sections.append("[이전 압축 요약 — 예산 초과로 생략, 구조화 항목은 위에 보존됨]")
    body_text = (body or "").strip()
    if body_text:
        remaining = budget - used
        if remaining > 0:
            sections.append(body_text[:remaining])
    if marker:
        sections.append(marker)
    return "\n".join(sections)


__all__ = [
    "CARRIED_SUMMARY_MAX_CHARS",
    "CONSTRAINT_KINDS",
    "CONSTRAINT_LINE_MAX_CHARS",
    "Constraint",
    "MARKER_PREFIX",
    "STATUS_ACTIVE",
    "STATUS_SUPERSEDED",
    "SUMMARY_SCHEMA_VERSION",
    "SUMMARY_TEXT_BUDGET_CHARS",
    "SummaryMemory",
    "compose_summary",
    "constraint_id",
    "carryover_prose",
    "detect_kind",
    "detect_supersede",
    "is_store_generated_summary",
    "parse_marker",
    "record_generation",
    "render_constraint_block",
    "render_marker",
    "significant_tokens",
    "update_from_messages",
]
