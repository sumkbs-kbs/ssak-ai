"""task 26 (B04) — 목표 중심 작업 기억의 **선택기 prototype 과 대조군**.

질문은 하나다: *"같은 토큰 예산에서, 필요한 증거를 더 많이 남기면서 더 적게 쓰는가?"*

## 조건

| 조건 | 무엇을 하는가 | 약점(재는 대상) |
|---|---|---|
| `fifo_window` | 최근 순서로 채운다 | 오래된 필수 증거가 밀린다 |
| `pinned` | 핀(제약+필수) 먼저, 그 다음 최근 | 예산을 넘으면 조용히 버린다 |
| `summary` | 같은 예산에 맞춰 **모두 요약** | 출처 근거가 사라진 요약은 사실로 승격할 수 없다 |
| `selector` | 목표 관련성+최근성+검증된 진전−중복 | (후보) |

## 불변식(모든 조건이 지킨다 — 지키지 못한 상태는 측정으로 드러내고, 주입으로 문을 잰다)

  1. **제약은 삭제할 수 없다.** 사용자 목표·승인 범위·금지 정책은 점수로 밀려나지 않는다.
  2. **세션 경계를 넘지 않는다.** 다른 세션의 항목은 이 세션의 문맥에 들어가지 않는다.
  3. **조용히 버리지 않는다.** 넘치면 보고(`overflow_reported`)하거나 비핵심 참조를 외부화한다.

`select()` 는 순수 함수다 — 시계·난수·전역 상태에 기대지 않는다. 그래야 같은 입력이 같은 선택을
낳고, 이빨(변이) 하네스가 "시험이 계약을 재고 있는가"를 잴 수 있다.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

# `research/flywire` 는 패키지가 아니라 **스크립트 묶음**이다(형제 모듈은 스크립트 디렉터리 기준으로 import).
import memory_contract as contract  # pyright: ignore[reportImplicitRelativeImport]
from memory_contract import (  # pyright: ignore[reportImplicitRelativeImport]
    ItemKind,
    MemoryItem,
    WMCase,
    WMSelection,
)

CONDITIONS: Final[tuple[str, ...]] = ("fifo_window", "pinned", "summary", "selector")
# 베이스라인은 지금 제품 동작을 재현한다: 넘치면 **조용히 잘린다**(보고하지 않는다).
# 후보(`selector`)는 넘치면 보고하거나 외부화한다 — 그 차이가 gate 의 `silent_drops` 축이다.
REPORTS_OVERFLOW: Final[Mapping[str, bool]] = {
    "fifo_window": False,
    "pinned": False,
    "summary": True,
    "selector": True,
}
# 악성 페이지 문장은 **그대로 옮기지 않는다**. 옵션 인용으로 낮추거나 버린다(관찰 자료로만 유지).
MALICIOUS_QUARANTINE_PREFIX: Final = "페이지가 실행을 지시한 문장(신뢰하지 않음): "
SUMMARY_RATIO: Final = 0.4
# 결정적 선택기 가중치 — calibration 에서 고정한다(holdout 을 보고 바꾸면 새 평가로 등록해야 한다).
SELECTOR_WEIGHTS: Final[Mapping[str, float]] = {
    "goal_relevance": 1.0,
    "recency": 0.35,
    "verified_progress": 0.5,
    "duplicate_penalty": 1.0,
    "low_trust_penalty": 0.3,
}
WEIGHTS_VERSION: Final = "selector-weights/2026-09-22"


class SelectorFixtureError(RuntimeError):
    pass


# ── fixture 로드 ─────────────────────────────────────────────────────────────
def load_cases(path: Path) -> tuple[WMCase, ...]:
    if not path.is_file():
        raise FileNotFoundError(f"작업 기억 fixture 가 없다: {path}")
    payload: Any = json.loads(path.read_text(encoding="utf-8"))
    raw_cases = payload.get("cases") if isinstance(payload, dict) else None
    if not isinstance(raw_cases, list) or not raw_cases:
        raise SelectorFixtureError("fixture 에 cases 가 없다")
    cases: list[WMCase] = []
    for raw in raw_cases:
        if not isinstance(raw, dict):
            raise SelectorFixtureError("case 가 객체가 아니다")
        items: list[MemoryItem] = []
        raw_items = raw.get("items", [])
        if not isinstance(raw_items, list):
            raise SelectorFixtureError("case.items 가 리스트가 아니다")
        for entry in raw_items:
            if not isinstance(entry, dict):
                raise SelectorFixtureError("item 이 객체가 아니다")
            items.append(
                MemoryItem(
                    item_id=str(entry["item_id"]),
                    kind=ItemKind(str(entry["kind"])),
                    text=str(entry["text"]),
                    session=str(entry.get("session", "a")),
                    goal_relevance=float(entry.get("goal_relevance", 0.0)),
                    recency=float(entry.get("recency", 0.0)),
                    verified=bool(entry.get("verified", False)),
                    has_evidence=bool(entry.get("has_evidence", False)),
                    observed_at=float(entry.get("observed_at", 0.0)),
                    pinned=bool(entry.get("pinned", False)),
                    required=bool(entry.get("required", False)),
                    superseded_by=str(entry.get("superseded_by", "")),
                    duplicate_of=str(entry.get("duplicate_of", "")),
                    externalizable=bool(entry.get("externalizable", False)),
                )
            )
        cases.append(
            WMCase(
                case_id=str(raw["case_id"]),
                kind=str(raw["kind"]),
                goal=str(raw.get("goal", "")),
                token_budget=int(raw["token_budget"]),
                items=tuple(items),
                required_ids=tuple(str(value) for value in raw.get("required_ids", [])),
                constraint_ids=tuple(str(value) for value in raw.get("constraint_ids", [])),
                session=str(raw.get("session", "a")),
            )
        )
    return tuple(cases)


# ── 선택 ─────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class _Candidate:
    item: MemoryItem
    text: str
    tokens: int
    has_evidence: bool
    score: float


def _summarize(text: str) -> str:
    """요약 조건의 압축 — 문장을 줄이는 대신 **출처 참조를 버린다**(그 대가를 잰다)."""
    stripped = " ".join(text.split())
    if not stripped:
        return ""
    keep = max(1, int(len(stripped) * SUMMARY_RATIO))
    clipped = stripped[:keep]
    if " " in clipped:
        clipped = clipped[: clipped.rfind(" ")]
    return clipped.rstrip(".,;:") + "…"


def _scoped(case: WMCase, *, session: str, enforce: bool) -> list[MemoryItem]:
    """불변식 2 — 세션 경계. `enforce=False` 는 주입된 위반(시험이 문을 재는 경로)뿐이다."""
    items = [item for item in case.items if item.session == session or not enforce]
    # 정정된(stale) 항목은 바뀐 항목이 남아 있으면 후보가 아니다.
    live = {item.item_id for item in items}
    return [item for item in items if not (item.superseded_by and item.superseded_by in live)]


def total_tokens(case: WMCase) -> int:
    """그 케이스의 모든 항목이 문맥에 그대로 들어갈 때의 입력 토큰(현재 제품 동작의 비용)."""
    return sum(contract.estimate_tokens(item.text) for item in case.items)


def budget_for(condition: str, case: WMCase) -> int:
    """조건별 상한 — **이 정책이 한 곳에 있어야** 벤치마크와 시험이 같은 것을 잰다.

    `fifo_window` 는 상한 없이(전부) 돌려 "최근 창을 그대로 밀어 넣는" 현재 동작을 재현하고,
    나머지 조건은 케이스가 정한 압축 상한에서 돈다.
    """
    return total_tokens(case) if condition == "fifo_window" else case.token_budget


def _score(item: MemoryItem, weights: Mapping[str, float]) -> float:
    score = weights["goal_relevance"] * item.goal_relevance
    score += weights["recency"] * item.recency
    score += weights["verified_progress"] * (1.0 if item.verified else 0.0)
    if item.duplicate_of:
        score -= weights["duplicate_penalty"]
    if item.kind in (ItemKind.OBSERVATION, ItemKind.MALICIOUS):
        score -= weights["low_trust_penalty"]
    if item.kind is ItemKind.STALE and not item.superseded_by:
        score -= weights["duplicate_penalty"]
    return score


def _pack(
    *,
    case: WMCase,
    condition: str,
    session: str,
    candidates: Sequence[_Candidate],
    budget: int,
    report_overflow: bool,
    externalize: bool,
    enforce_scope: bool,
    enforce_constraints: bool,
) -> WMSelection:
    ordered_candidates = list(candidates)
    if enforce_constraints:
        # 불변식 1 을 **한 곳에서** 집행한다 — 조건마다 따로 구현하면 언젠가 하나가 어긋난다.
        ordered_candidates = [c for c in ordered_candidates if c.item.kind is ItemKind.CONSTRAINT] + [
            c for c in ordered_candidates if c.item.kind is not ItemKind.CONSTRAINT
        ]
    else:
        # 주입된 실패 모드: 제약이 다른 항목과 같이 점수 경쟁을 한다(그리고 밀려날 수 있다).
        # 이것이 실제 위험이므로 문을 여기서 열고, 검출되는지를 시험이 잰다.
        ordered_candidates = [c for c in ordered_candidates if c.item.kind is not ItemKind.CONSTRAINT]
    kept: list[_Candidate] = []
    dropped: list[str] = []
    externalized: list[str] = []
    used = 0
    skipped_due_to_budget: list[_Candidate] = []
    for candidate in ordered_candidates:
        if used + candidate.tokens <= budget:
            kept.append(candidate)
            used += candidate.tokens
        elif externalize and candidate.item.externalizable:
            externalized.append(candidate.item.item_id)
        else:
            skipped_due_to_budget.append(candidate)
    silent_drop: tuple[str, ...] = ()
    for candidate in skipped_due_to_budget:
        # 불변식 3 — 넘치면 **보고**해야 한다. 보고하지 않는 조건에서는 버려진 것이 조용히 사라진다.
        # 외부화는 이미 위에서 처리됐다(그것도 '남긴' 것으로 세지 않되, 보고된 것으로는 센다).
        if report_overflow:
            dropped.append(candidate.item.item_id)
        else:
            silent_drop = (*silent_drop, candidate.item.item_id)
    kept_ids = [candidate.item.item_id for candidate in kept]
    verbatim = tuple(
        sorted(
            candidate.item.item_id
            for candidate in kept
            if candidate.item.kind is ItemKind.MALICIOUS and candidate.text == candidate.item.text
        )
    )
    constraints = set(case.constraint_ids)
    omissions = tuple(sorted(constraints - set(kept_ids)))
    # 교차 세션은 **집행 여부와 무관하게** 센다 — 집행을 꺼 둔 실행에서 위반이 안 보이면 검사가 아니다.
    cross = tuple(sorted(candidate.item.item_id for candidate in kept if candidate.item.session != session))
    evidence_loss = tuple(
        sorted(
            candidate.item.item_id
            for candidate in kept
            if candidate.item.verified and candidate.item.has_evidence and not candidate.has_evidence
        )
    )
    return WMSelection(
        condition=condition,
        case_id=case.case_id,
        kept=tuple(kept_ids),
        dropped=tuple(sorted(dropped)),
        externalized=tuple(sorted(externalized)),
        tokens=used,
        overflow_reported=bool(report_overflow and (skipped_due_to_budget or externalized)),
        silent_drop=silent_drop,
        cross_session=cross,
        constraint_omissions=omissions,
        evidence_loss_without_source=evidence_loss,
        malicious_verbatim=verbatim,
        payload=tuple((candidate.item.item_id, candidate.text) for candidate in kept),
    )


def select(
    condition: str,
    case: WMCase,
    *,
    session: str | None = None,
    budget: int | None = None,
    report_overflow: bool | None = None,
    enforce_scope: bool = True,
    enforce_constraints: bool = True,
    summarize: bool | None = None,
    quarantine_malicious: bool = True,
) -> WMSelection:
    """조건 하나를 결정적으로 실행한다. `enforce_*` 는 **주입된 위반 경로**를 위한 문이다.

    `budget` 은 상한 override 다 — 베이스라인(`fifo_window`)은 **상한 없이** 돌려
    "현재 제품 동작(최근 창을 그대로 밀어 넣는다)"을 재현하고, 후보는 작은 상한에서 돈다.
    """
    if condition not in CONDITIONS:
        raise SelectorFixtureError(f"알 수 없는 조건: {condition}")
    report_overflow = REPORTS_OVERFLOW[condition] if report_overflow is None else report_overflow
    active_session = session if session is not None else case.session
    items = _scoped(case, session=active_session, enforce=enforce_scope)
    summarize_items = condition == "summary" if summarize is None else summarize
    candidates: list[_Candidate] = []
    for item in items:
        text = _summarize(item.text) if summarize_items else item.text
        if item.kind is ItemKind.MALICIOUS and quarantine_malicious:
            # 격리: 지시문을 그대로 나르지 않는다(그대로 나르면 `malicious_verbatim` 이 오른다).
            text = f"{MALICIOUS_QUARANTINE_PREFIX}{_summarize(item.text)}"
        candidates.append(
            _Candidate(
                item=item,
                text=text,
                tokens=contract.estimate_tokens(text),
                has_evidence=False if summarize_items else item.has_evidence,
                score=_score(item, SELECTOR_WEIGHTS),
            )
        )

    ceiling = budget_for(condition, case) if budget is None else budget
    if condition == "fifo_window":
        ordered = sorted(candidates, key=lambda candidate: (-candidate.item.observed_at, candidate.item.item_id))
        return _pack(
            case=case,
            condition=condition,
            session=active_session,
            candidates=ordered,
            budget=ceiling,
            report_overflow=report_overflow,
            externalize=False,
            enforce_scope=enforce_scope,
            enforce_constraints=enforce_constraints,
        )
    if condition == "pinned":
        ordered = sorted(
            candidates,
            key=lambda candidate: (
                not (candidate.item.pinned or candidate.item.required or candidate.item.kind is ItemKind.CONSTRAINT),
                -candidate.item.observed_at,
                candidate.item.item_id,
            ),
        )
        return _pack(
            case=case,
            condition=condition,
            session=active_session,
            candidates=ordered,
            budget=ceiling,
            report_overflow=report_overflow,
            externalize=False,
            enforce_scope=enforce_scope,
            enforce_constraints=enforce_constraints,
        )
    if condition == "summary":
        ordered = sorted(candidates, key=lambda candidate: (-candidate.score, candidate.item.item_id))
        return _pack(
            case=case,
            condition=condition,
            session=active_session,
            candidates=ordered,
            budget=ceiling,
            report_overflow=report_overflow,
            externalize=False,
            enforce_scope=enforce_scope,
            enforce_constraints=enforce_constraints,
        )
    # selector: 제약(불변식) → 필수 → 점수, 남는 자리에서 비핵심을 외부화한다.
    ordered = sorted(
        candidates,
        key=lambda candidate: (
            0
            if enforce_constraints and candidate.item.kind is ItemKind.CONSTRAINT
            else (1 if candidate.item.required else 2),
            -candidate.score,
            candidate.item.item_id,
        ),
    )
    return _pack(
        case=case,
        condition=condition,
        session=active_session,
        candidates=ordered,
        budget=ceiling,
        report_overflow=report_overflow,
        externalize=True,
        enforce_scope=enforce_scope,
        enforce_constraints=enforce_constraints,
    )


# ── 평가 ─────────────────────────────────────────────────────────────────────
def evaluate_selection(case: WMCase, selection: WMSelection) -> dict[str, object]:
    """결정적 성공 판정 — 모델이 필요 없다(그래서 `model_success` 는 별도로 NOT_RUN 이다).

    성공 = (가) 필수 증거가 전부 남았고 (나) 그 증거가 **출처를 잃지 않았고**
           (다) 악성 페이지 문장이 검증된 사실로 승격되지 않았다.
    """
    kept = set(selection.kept)
    payload = dict(selection.payload)
    missing_required = sorted(set(case.required_ids) - kept)
    lost_source = sorted(
        item_id
        for item_id in case.required_ids
        if item_id in kept
        and any(item.item_id == item_id and item.verified and item.has_evidence for item in case.items)
        and item_id in set(selection.evidence_loss_without_source)
    )
    malicious_verbatim = sorted(selection.malicious_verbatim)
    success = not missing_required and not lost_source and not malicious_verbatim
    return {
        "case_id": case.case_id,
        "kind": case.kind,
        "condition": selection.condition,
        "success": success,
        "missing_required": missing_required,
        "lost_source": lost_source,
        "malicious_verbatim": malicious_verbatim,
        "tokens": selection.tokens,
        "kept_count": len(selection.kept),
        "overflow_reported": selection.overflow_reported,
        "silent_drop": list(selection.silent_drop),
        "constraint_omissions": list(selection.constraint_omissions),
        "cross_session": list(selection.cross_session),
        "payload_chars": sum(len(text) for text in payload.values()),
    }


def aggregate(condition: str, results: Sequence[Mapping[str, Any]]) -> dict[str, object]:
    total = len(results)
    if not total:
        return {"condition": condition, "case_count": 0}
    successes = sum(1 for result in results if result["success"])
    tokens = [float(result["tokens"]) for result in results]
    return {
        "condition": condition,
        "case_count": total,
        "success_rate": successes / total,
        "mean_tokens": contract.mean(tokens),
        "constraint_omissions": sum(len(result["constraint_omissions"]) for result in results),  # type: ignore[arg-type]
        "cross_session_leaks": sum(len(result["cross_session"]) for result in results),  # type: ignore[arg-type]
        "silent_drops": sum(len(result["silent_drop"]) for result in results),  # type: ignore[arg-type]
        "lost_source": sum(len(result["lost_source"]) for result in results),  # type: ignore[arg-type]
        "malicious_verbatim": sum(len(result["malicious_verbatim"]) for result in results),  # type: ignore[arg-type]
        "overflow_reported": sum(1 for result in results if result["overflow_reported"]),
        "cases": [
            {
                "case_id": result["case_id"],
                "kind": result["kind"],
                "success": result["success"],
                "missing_required": result["missing_required"],
                "lost_source": result["lost_source"],
                "tokens": result["tokens"],
            }
            for result in results
        ],
    }
