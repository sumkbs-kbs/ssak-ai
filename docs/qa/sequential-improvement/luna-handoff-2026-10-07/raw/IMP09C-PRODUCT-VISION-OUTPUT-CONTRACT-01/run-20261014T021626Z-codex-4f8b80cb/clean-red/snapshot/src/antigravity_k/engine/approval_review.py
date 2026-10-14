from __future__ import annotations

import json
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar, Final, Protocol, assert_never

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class ApprovalReviewDecision(str, Enum):
    APPROVE = "approve"
    DENY = "deny"
    ESCALATE = "escalate"


@dataclass(frozen=True, slots=True)
class ApprovalReviewInput:
    tool_name: str
    tool_args: Mapping[str, JsonValue]
    risk_level: str
    description: str
    diff_preview: str


@dataclass(frozen=True, slots=True)
class ApprovalReview:
    decision: ApprovalReviewDecision
    risk_score: float
    reason_codes: tuple[str, ...]
    rationale: str
    reviewer: str = "policy-v1"
    reviewed_at: float = field(default_factory=time.time)


class ApprovalReviewProvider(Protocol):
    def review(self, request: ApprovalReviewInput, /) -> ApprovalReview: ...


class ApprovalReviewParseError(ValueError):
    reason: str

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class _ModelReviewPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    decision: ApprovalReviewDecision
    risk_score: float = Field(ge=0.0, le=100.0)
    reason_codes: tuple[str, ...] = ()
    rationale: str = Field(min_length=1)


class ApprovalReviewGenerator(Protocol):
    def __call__(self, prompt: str, /) -> str: ...


class LocalModelApprovalReviewProvider:
    _DECISION_RANK: Final[dict[ApprovalReviewDecision, int]] = {
        ApprovalReviewDecision.APPROVE: 0,
        ApprovalReviewDecision.ESCALATE: 1,
        ApprovalReviewDecision.DENY: 2,
    }
    _SENSITIVE_MARKERS: Final[tuple[str, ...]] = (
        ".env",
        "credential",
        "password",
        "private_key",
        "secret",
        "token",
    )

    def __init__(
        self,
        generate: ApprovalReviewGenerator,
        model_name: str,
        policy_engine: ApprovalReviewEngine | None = None,
    ) -> None:
        self._generate: ApprovalReviewGenerator = generate
        self._model_name: str = model_name
        self._policy_engine: ApprovalReviewEngine = policy_engine or ApprovalReviewEngine()

    def review(self, request: ApprovalReviewInput, /) -> ApprovalReview:
        policy_review = self._policy_engine.review(request)
        try:
            payload = self._parse(self._generate(self._prompt(request)))
        except (OSError, RuntimeError, TimeoutError, ValueError):
            match policy_review.decision:
                case ApprovalReviewDecision.DENY:
                    return ApprovalReview(
                        decision=policy_review.decision,
                        risk_score=policy_review.risk_score,
                        reason_codes=(*policy_review.reason_codes, "model_error"),
                        rationale=policy_review.rationale,
                        reviewer=f"qwen:{self._model_name}-fail-closed",
                    )
                case ApprovalReviewDecision.APPROVE | ApprovalReviewDecision.ESCALATE:
                    raise
            assert_never(policy_review.decision)
        decision = max(
            (policy_review.decision, payload.decision),
            key=self._DECISION_RANK.__getitem__,
        )
        model_codes = tuple(f"model_{code}" for code in payload.reason_codes)
        reason_codes = tuple(
            dict.fromkeys((*policy_review.reason_codes, "model_review", *model_codes)),
        )
        model_risk = payload.risk_score / 100 if payload.risk_score > 1 else payload.risk_score
        return ApprovalReview(
            decision=decision,
            risk_score=round(max(policy_review.risk_score, model_risk), 2),
            reason_codes=reason_codes,
            rationale=payload.rationale,
            reviewer=f"qwen:{self._model_name}",
        )

    def _prompt(self, request: ApprovalReviewInput) -> str:
        context = self._safe_context(request)
        return json.dumps(
            {
                "task": "approval_review",
                "request": context,
                "output_schema": _ModelReviewPayload.model_json_schema(),
            },
            ensure_ascii=False,
        )

    def _safe_context(self, request: ApprovalReviewInput) -> dict[str, JsonValue]:
        raw_args = json.dumps(dict(request.tool_args), ensure_ascii=False, default=str)
        searchable = " ".join((request.tool_name, request.description, raw_args, request.diff_preview)).lower()
        if any(marker in searchable for marker in self._SENSITIVE_MARKERS):
            safe_keys: list[JsonValue] = [key for key in sorted(request.tool_args)]
            safe_args: dict[str, JsonValue] = {"keys": safe_keys}
            safe_diff = "[sensitive context omitted]"
        else:
            safe_args = dict(request.tool_args)
            safe_diff = request.diff_preview[:4000]
        return {
            "tool_name": request.tool_name,
            "tool_args": safe_args,
            "risk_level": request.risk_level,
            "description": request.description,
            "diff_preview": safe_diff,
        }

    @staticmethod
    def _parse(raw: str) -> _ModelReviewPayload:
        candidate = raw.strip()
        if candidate.startswith("```"):
            lines = candidate.splitlines()
            candidate = "\n".join(lines[1:-1]).strip()
        start = candidate.find("{")
        if start < 0:
            raise ApprovalReviewParseError("structured review JSON is missing")
        try:
            end_index = LocalModelApprovalReviewProvider._json_end_index(candidate, start)
            return _ModelReviewPayload.model_validate_json(candidate[start : start + end_index])
        except (TypeError, ValueError) as exc:
            raise ApprovalReviewParseError("structured review JSON is invalid") from exc

    @staticmethod
    def _json_end_index(candidate: str, start: int) -> int:
        depth = 0
        in_string = False
        escaped = False
        for index, character in enumerate(candidate[start:]):
            if in_string:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == '"':
                    in_string = False
                continue
            if character == '"':
                in_string = True
            elif character == "{":
                depth += 1
            elif character == "}":
                depth -= 1
                if depth == 0:
                    return index + 1
        raise ApprovalReviewParseError("structured review JSON is incomplete")


class ApprovalReviewEngine:
    _RISK_SCORES: Final[dict[str, float]] = {
        "safe": 0.05,
        "low": 0.20,
        "medium": 0.50,
        "high": 0.80,
        "critical": 0.95,
    }
    _READ_ONLY_TOOLS: Final[frozenset[str]] = frozenset(
        {"read_file", "list_directory", "search_files", "git_diff", "get_status"},
    )
    _SENSITIVE_MARKERS: Final[tuple[str, ...]] = (
        ".env",
        "credential",
        "password",
        "private_key",
        "secret",
        "token",
    )
    _DESTRUCTIVE_MARKERS: Final[tuple[str, ...]] = (
        "rm -rf",
        "drop database",
        "truncate table",
        "delete all",
        "chmod 777",
    )
    _NETWORK_MARKERS: Final[tuple[str, ...]] = (
        "curl ",
        "wget ",
        "http://",
        "https://",
    )

    def review(self, request: ApprovalReviewInput) -> ApprovalReview:
        if not request.tool_name or not request.description:
            return ApprovalReview(
                decision=ApprovalReviewDecision.ESCALATE,
                risk_score=1.0,
                reason_codes=("insufficient_context",),
                rationale="도구 이름 또는 설명이 없어 자동 판단을 보류합니다.",
            )

        risk_score = self._RISK_SCORES.get(request.risk_level, 0.9)
        searchable = self._searchable_text(request)
        reason_codes: list[str] = []

        if request.tool_name in self._READ_ONLY_TOOLS and not request.diff_preview:
            reason_codes.append("read_only")
        if any(marker in searchable for marker in self._SENSITIVE_MARKERS):
            risk_score = max(risk_score, 0.95)
            reason_codes.append("sensitive_target")
        if any(marker in searchable for marker in self._DESTRUCTIVE_MARKERS):
            risk_score = 1.0
            reason_codes.append("destructive_operation")
        if any(marker in searchable for marker in self._NETWORK_MARKERS):
            risk_score = max(risk_score, 0.75)
            reason_codes.append("network_effect")
        if request.diff_preview:
            reason_codes.append("file_change")

        decision = self._decision_for(risk_score, reason_codes)
        rationale = self._rationale(decision, reason_codes)
        return ApprovalReview(
            decision=decision,
            risk_score=round(risk_score, 2),
            reason_codes=tuple(dict.fromkeys(reason_codes)),
            rationale=rationale,
        )

    @staticmethod
    def _searchable_text(request: ApprovalReviewInput) -> str:
        try:
            args = json.dumps(dict(request.tool_args), ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            args = ""
        return " ".join((request.tool_name, request.description, args)).lower()

    @staticmethod
    def _decision_for(
        risk_score: float,
        reason_codes: list[str],
    ) -> ApprovalReviewDecision:
        if "sensitive_target" in reason_codes or "destructive_operation" in reason_codes:
            return ApprovalReviewDecision.DENY
        if risk_score >= 0.75:
            return ApprovalReviewDecision.ESCALATE
        return ApprovalReviewDecision.APPROVE

    @staticmethod
    def _rationale(
        decision: ApprovalReviewDecision,
        reason_codes: list[str],
    ) -> str:
        if decision is ApprovalReviewDecision.DENY:
            return "민감 대상 또는 파괴적 동작이 감지되어 사용자 확인 전 실행을 권고하지 않습니다."
        if decision is ApprovalReviewDecision.ESCALATE:
            return "위험도가 높거나 영향 범위가 불명확하여 사용자 결정을 요구합니다."
        if "read_only" in reason_codes:
            return "읽기 전용 도구이며 파일 변경이 없어 자동 승인 후보입니다."
        return "정책상 낮은 위험 요청으로 자동 승인 후보입니다."
