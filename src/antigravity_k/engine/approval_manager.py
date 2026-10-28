"""Ssak-Ai: 승인 관리자 (P1-3).

====================================
위험한 도구 실행 전 사용자 승인을 요청하는 인터랙티브 흐름.
Codex/Cursor 수준의 "신뢰할 수 있는 자율성"을 제공합니다.

핵심 기능:
  - 대기 중인 승인 요청 관리 (pending queue)
  - diff 미리보기 자동 생성 (파일 편집 도구)
  - 타임아웃 자동 거부 (안전 기본값)
  - "항상 허용" 옵션 (사용자 편의)
  - SSE 폴링 API 연동 지원

동작 흐름:
  1. ToolExecutor가 PROMPT 권한을 받음
  2. ApprovalManager.request_approval()로 대기 요청 생성
  3. API/SSE로 클라이언트에 알림
  4. 사용자가 수락/거부/항상허용 선택
  5. ToolExecutor가 결과를 받아 계속 진행 또는 중단
"""

from __future__ import annotations

import asyncio
import difflib
import hashlib
import json
import logging
import os
import re
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Final, Protocol, TypedDict

from pydantic import JsonValue

from antigravity_k.engine.approval_review import (
    ApprovalReview,
    ApprovalReviewDecision,
    ApprovalReviewEngine,
    ApprovalReviewInput,
    ApprovalReviewProvider,
    LocalModelApprovalReviewProvider,
)

logger = logging.getLogger("antigravity_k.approval_manager")
_SENSITIVE_PATH_MARKERS = (".env", "credential", "password", "secret", "token", "private_key")
# r37: secret-looking *content* (not only names) also masks the whole preview/arg value.
_SECRET_CONTENT_RE = re.compile(
    r"(?i)(api[_-]?key|apikey|access[_-]?key|bearer\s+[a-z0-9._-]{8,}|\bsk-[a-z0-9_-]{8,}|ghp_[a-z0-9]{8,}"
    r"|xox[abp]-|-----BEGIN [A-Z ]*PRIVATE KEY-----|aws_secret)"
)


def _text_arg(tool_args: Mapping[str, JsonValue], key: str) -> str:
    value = tool_args.get(key)
    return value if isinstance(value, str) else ""


class _ReviewModelManager(Protocol):
    def generate(self, prompt: str, target: str, **kwargs: object) -> str: ...


class _AutoReviewPayload(TypedDict):
    decision: str
    risk_score: float
    reason_codes: list[str]
    rationale: str
    reviewer: str
    reviewed_at: float


class _ApprovalRequestPayload(TypedDict):
    request_id: str
    tool_name: str
    risk_level: str
    description: str
    diff_preview: str
    status: str
    created_at: float
    timeout_sec: int
    auto_review: _AutoReviewPayload | None
    #: 이 도구에 '항상 허용' 을 줄 수 있는가. 화면이 **서버 판정**을 그대로 그리게 한다 —
    #: UI 가 "이 도구는 안 된다" 를 스스로 알면 그 정책이 두 곳으로 갈라진다.
    always_allow_allowed: bool
    #: r37: 실제 쓰기 대상(프로젝트 라벨, 정규화 상대 경로, create/modify/overwrite). 쓰기 도구가
    #: 아니면 None. 비밀 내용은 담지 않는다(경로·동작·내용 해시·길이만).
    target: dict[str, JsonValue] | None
    #: r37: 마스킹된 인자 요약(본문 계열 키는 길이·해시로 대체).
    args: dict[str, JsonValue]
    #: r37: 승인 대상+동작 바인딩 해시. 실행 시 재계산한 값과 다르면 재승인.
    binding: str


#: '항상 허용' 을 줄 수 **없는** 도구. 브라우저 효과가 그렇다(task 18): 승인은 그 순간의
#: `owner·session·origin·action·ref·payload·generation` 에 묶인 한 건이고, 한 도구에 "항상" 을
#: 주면 그 묶음이 통째로 사라진다(다음 행동은 다른 페이지·다른 금액일 수 있다).
NO_ALWAYS_ALLOW_TOOLS: Final[frozenset[str]] = frozenset(
    # r41: tools the ApprovalGate marks "always ask" (allow_always=False) are included too —
    # previously resolve(ALWAYS_ALLOW) granted them tool-wide when called outside the API route.
    {"browser_effect", "db_migration", "deploy", "create_pr", "git_push", "payment"}
)


class ApprovalStatus(str, Enum):
    """승인 상태."""

    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    TIMEOUT = "timeout"
    ALWAYS_ALLOW = "always_allow"  # 이 도구는 향후 자동 승인


class ApprovalDecision(str, Enum):
    """사용자의 승인 결정."""

    APPROVE = "approve"
    DENY = "deny"
    ALWAYS_ALLOW = "always_allow"


# ─── r37: 쓰기 대상 기술 + 승인 바인딩 ──────────────────────────────────

WRITE_TOOLS: Final[frozenset[str]] = frozenset(
    {"write_file", "write_artifact", "edit_file", "replace_file_content", "multi_replace_file_content"},
)
_CONTENT_KEYS: Final[frozenset[str]] = frozenset(
    {"content", "new_str", "old_str", "replacement", "replacement_chunks", "code", "patch", "CodeContent"},
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()


def masked_tool_args(tool_args: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    """승인 UI/로그용 인자 요약. 본문 계열 값은 길이+해시로, 민감 키는 마스킹한다."""
    out: dict[str, JsonValue] = {}
    for key, value in tool_args.items():
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
        lowered = key.lower()
        if any(marker in lowered for marker in _SENSITIVE_PATH_MARKERS):
            out[key] = "[masked]"
        elif key in _CONTENT_KEYS:
            out[key] = f"[{len(text)} chars, sha256:{_sha(text)[:12]}]"
        elif isinstance(value, str) and (
            any(m in value.lower() for m in _SENSITIVE_PATH_MARKERS) or _SECRET_CONTENT_RE.search(value)
        ):
            out[key] = "[masked]"
        else:
            out[key] = value if not isinstance(value, str) else value[:300]
    return out


def describe_write_target(
    tool_name: str,
    tool_args: Mapping[str, JsonValue],
    project_root: str | None,
) -> dict[str, JsonValue] | None:
    """쓰기 도구가 실제로 건드릴 대상을 실행 경로와 같은 규칙으로 계산한다.

    반환: project(루트 basename), path(루트 기준 정규화 상대 경로), action(create/modify/overwrite),
    content_sha256/length, outside_root(루트 밖이면 True). 루트가 없으면 None(승인 불가).
    """
    if tool_name not in WRITE_TOOLS or not project_root:
        return None
    root = os.path.realpath(project_root)
    if tool_name == "write_artifact":
        name = os.path.basename(_text_arg(tool_args, "artifact_name"))
        if "." not in name:
            kind = _text_arg(tool_args, "artifact_type") or "generic"
            name += ".html" if kind in ("html", "react") else ".md"
        raw = os.path.join(root, "artifacts", name)
    else:
        file_path = _text_arg(tool_args, "file_path") or _text_arg(tool_args, "TargetFile")
        if not file_path:
            return None
        raw = file_path if os.path.isabs(file_path) else os.path.join(root, file_path)
    real = os.path.realpath(raw)
    exists = os.path.lexists(real)
    if tool_name in ("write_file", "write_artifact"):
        action = "overwrite" if exists else "create"
    else:
        action = "modify"
    try:
        rel = os.path.relpath(real, root)
    except ValueError:
        rel = real
    outside = rel == os.pardir or rel.startswith(os.pardir + os.sep)
    body = ""
    for key in ("content", "new_str", "replacement_chunks", "CodeContent", "replacement"):
        if key in tool_args:
            v = tool_args[key]
            body = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, sort_keys=True, default=str)
            break
    return {
        "project": os.path.basename(root),
        "path": "[outside project root]" if outside else rel,
        "action": action,
        "content_length": len(body),
        "content_sha256": _sha(body),
        "outside_root": outside,
        "_real": real,
    }


def approval_binding(
    tool_name: str,
    tool_args: Mapping[str, JsonValue],
    target: Mapping[str, JsonValue] | None,
) -> str:
    """승인된 (도구, 실제 대상, 동작, 인자 전체)를 고정하는 해시."""
    canonical = json.dumps(
        {
            "tool": tool_name,
            "real": None if target is None else target.get("_real"),
            "action": None if target is None else target.get("action"),
            "args": {k: tool_args[k] for k in sorted(tool_args)},
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return _sha(canonical)


#: r40: approval policy version. Bump when the binding/scope rules change — older approvals then
#: no longer verify (fail closed -> re-approval).
APPROVAL_POLICY_VERSION: Final[str] = "r40-1"
#: r40: an APPROVED one-time decision must be used within this many seconds of the user's decision.
APPROVED_TTL_SEC: Final[int] = int(os.getenv("AGK_APPROVAL_APPROVED_TTL_SEC", "900") or "900")
#: r40: approval layers. "standard" evidence may satisfy both the GatePipeline ApprovalGate and the
#: PermissionGate risk-level PROMPT for the identical action; "strict:*" (secret-named file,
#: capability policy, path PROMPT) always needs its own separate approval.
LAYER_STANDARD: Final[str] = "standard"


def current_approval_scope(layer: str = LAYER_STANDARD) -> dict[str, str]:
    """r40: who/where/what-policy an approval is bound to, computed server-side only.

    Never derived from tool arguments or model output: actor, session, project and task come from
    the server-bound request/task execution context; the policy fields from the process policy.
    Missing values are recorded as "" and must match exactly at verification time.
    """
    actor = session = project = task = ""
    try:
        from antigravity_k.api.project_binding import get_bound_request_execution_context

        ctx = get_bound_request_execution_context()
        if ctx is not None:
            actor, session, project, task = ctx.actor_subject, ctx.session_id, ctx.project_id, ctx.task_id or ""
    except Exception:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK - scope lookup must not crash the gate
        pass
    try:
        from antigravity_k.engine.task_execution_context import current_task_execution_context

        tctx = current_task_execution_context()
        if tctx is not None:
            task = tctx.task_id
    except Exception:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK
        pass
    try:
        from antigravity_k.engine.access_mode import effective_permission_mode

        mode = effective_permission_mode()
    except Exception:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK
        mode = "unknown"
    return {
        "actor": actor,
        "session": session,
        "project": project,
        "task": task,
        "policy_version": APPROVAL_POLICY_VERSION,
        "permission_mode": mode,
        "layer": layer,
    }


@dataclass(frozen=True)
class ApprovalEvidence:
    """r40: server-side handle to one APPROVED request. Created only by ApprovalManager inside the
    trusted executor and passed as a Python object — never serialized into tool args or prompts.
    Holding it grants nothing: every layer must ``verify`` it and execution must ``consume`` it."""

    request_id: str
    tool_name: str
    binding: str
    scope_sha: str
    _token: object = field(repr=False, compare=False)


def _public_target(target: Mapping[str, JsonValue] | None) -> dict[str, JsonValue] | None:
    if target is None:
        return None
    return {k: v for k, v in target.items() if not k.startswith("_")}


@dataclass
class ApprovalRequest:
    """하나의 승인 요청."""

    request_id: str
    tool_name: str
    tool_args: dict[str, JsonValue]
    risk_level: str = "medium"
    description: str = ""
    diff_preview: str = ""
    created_at: float = field(default_factory=time.time)
    status: ApprovalStatus = ApprovalStatus.PENDING
    resolved_at: float | None = None
    timeout_sec: int = 120
    auto_review: ApprovalReview | None = None
    target: dict[str, JsonValue] | None = None
    binding: str = ""
    #: r40: server-side scope (actor/session/project/task/policy/layer) captured at request time.
    scope: dict[str, str] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        """타임아웃 만료 여부."""
        if self.status != ApprovalStatus.PENDING:
            return False
        return (time.time() - self.created_at) > self.timeout_sec

    @property
    def always_allow_allowed(self) -> bool:
        """이 요청에 '항상 허용' 을 줄 수 있는가(도구 정책이 정한다)."""
        return self.tool_name not in NO_ALWAYS_ALLOW_TOOLS

    def to_dict(self) -> _ApprovalRequestPayload:
        """API 응답용 dict."""
        return {
            "request_id": self.request_id,
            "tool_name": self.tool_name,
            "risk_level": self.risk_level,
            "description": self.description,
            "diff_preview": self.diff_preview,
            "status": self.status.value,
            "created_at": self.created_at,
            "timeout_sec": self.timeout_sec,
            "always_allow_allowed": self.always_allow_allowed,
            "target": self.target,
            "args": masked_tool_args(self.tool_args),
            "binding": self.binding,
            "auto_review": None
            if self.auto_review is None
            else {
                "decision": self.auto_review.decision.value,
                "risk_score": self.auto_review.risk_score,
                "reason_codes": list(self.auto_review.reason_codes),
                "rationale": self.auto_review.rationale,
                "reviewer": self.auto_review.reviewer,
                "reviewed_at": self.auto_review.reviewed_at,
            },
        }


@dataclass
class AlwaysAllowGrant:
    """'항상 허용' 부여 한 건.

    부여는 **도구 하나**를 덮으므로(인자·경로·프로젝트와 무관), 사용자가 무엇에 동의했는지와
    부여가 무엇을 덮는지가 **다를 수 있다** — 그래서 부여 근거(`granted_for`)와 자동 승인
    횟수(`auto_approved_count`)를 함께 보존해 감사 가능하게 둔다(F-33).
    """

    tool_name: str
    granted_at: float
    granted_for: str = ""
    auto_approved_count: int = 0
    last_auto_approved_at: float | None = None

    def to_dict(self) -> dict[str, JsonValue]:
        """API 응답용 dict."""
        return {
            "tool_name": self.tool_name,
            "granted_at": self.granted_at,
            "granted_for": self.granted_for,
            "auto_approved_count": self.auto_approved_count,
            "last_auto_approved_at": self.last_auto_approved_at,
        }


class ApprovalManager:
    """승인 요청을 관리하는 싱글톤 매니저.

    사용법:
        manager = get_approval_manager()
        request = manager.request_approval(
            tool_name="edit_file",
            tool_args={"file_path": "app.py", ...},
            description="app.py의 hello 함수 수정",
        )
        # 클라이언트가 /api/approval/{request_id}로 응답
        decision = manager.wait_for_decision(request.request_id)
        if decision == ApprovalDecision.APPROVE:
            execute_tool()
    """

    def __init__(
        self,
        default_timeout_sec: int = 120,
        review_provider: ApprovalReviewProvider | None = None,
    ):
        """Initialize the ApprovalManager.

        Args:
            default_timeout_sec: 승인 대기 타임아웃 (기본 120초).

        """
        self._pending: dict[str, ApprovalRequest] = {}
        self._futures: dict[str, asyncio.Future[ApprovalStatus]] = {}
        # "항상 허용"된 도구들 — 부여 시각·근거·자동 승인 횟수를 함께 보존한다(F-33).
        self._always_allowed: dict[tuple[str, str], AlwaysAllowGrant] = {}
        self._consumed_approvals: set[str] = set()  # 소비된 일회성 승인 요청 ID
        # r40: evidence verify/consume is atomic across threads (concurrent tool calls).
        self._lock = threading.Lock()
        self._evidence_token = object()  # identity token: forged ApprovalEvidence objects never verify
        self._default_timeout: int = default_timeout_sec
        self._event_loop: asyncio.AbstractEventLoop | None = None
        self._review_provider: ApprovalReviewProvider = review_provider or ApprovalReviewEngine()

    def is_always_allowed(self, tool_name: str, *, actor_subject: str | None = None) -> bool:
        """현재 사용자에게 해당 도구의 '항상 허용' 부여가 있는지 확인."""
        actor = current_approval_scope()["actor"] if actor_subject is None else actor_subject
        with self._lock:
            return (actor, tool_name) in self._always_allowed

    def always_allowed_grants(self, *, actor_subject: str | None = None) -> list[AlwaysAllowGrant]:
        """'항상 허용' 부여 목록(부여 순).

        부여는 사용자·도구 단위이고 프로세스 수명 동안 유지된다. 사용자 생략은 내부 감사용
        전체 조회이며, HTTP 경로는 반드시 인증된 사용자를 지정한다.
        """
        with self._lock:
            grants = [
                grant
                for (actor, _tool), grant in self._always_allowed.items()
                if actor_subject is None or actor == actor_subject
            ]
            return sorted(grants, key=lambda grant: grant.granted_at)

    def record_auto_approval(self, tool_name: str, *, actor_subject: str | None = None) -> None:
        """'항상 허용' 부여로 **동의 없이** 실행된 횟수를 기록한다.

        부여가 없으면 아무것도 하지 않는다(순수 조회인 `is_always_allowed` 와 분리한다 —
        조회가 감사 기록을 바꾸면 세는 값이 조회 횟수가 된다).
        """
        self.consume_always_allowed(tool_name, actor_subject=actor_subject)

    def consume_always_allowed(self, tool_name: str, *, actor_subject: str | None = None) -> bool:
        """부여 확인과 실행 횟수 기록을 철회와 같은 잠금에서 처리한다.

        성공한 소비 뒤의 철회는 이미 실행을 시작한 호출을 취소하지 않는다.
        """
        actor = current_approval_scope()["actor"] if actor_subject is None else actor_subject
        with self._lock:
            grant = self._always_allowed.get((actor, tool_name))
            if grant is None:
                return False
            grant.auto_approved_count += 1
            grant.last_auto_approved_at = time.time()
            return True

    def consume_one_time_approval(self, tool_name: str, binding: str | None = None) -> bool:
        """일회성 승인(APPROVED)을 소비한다.

        사용자가 '승인(1회)'으로 응답한 요청이 있으면 소비 표시하고 True를
        반환한다 — 일시정지된 태스크의 재시도 실행이 이를 1회 허용으로
        사용한다. 같은 도구에 더 최신 결정이 DENY면 허용하지 않는다.
        """
        latest: ApprovalRequest | None = None
        for request in self._pending.values():
            if request.tool_name != tool_name:
                continue
            if request.status not in (ApprovalStatus.APPROVED, ApprovalStatus.DENIED):
                continue
            if request.status == ApprovalStatus.APPROVED and request.request_id in self._consumed_approvals:
                continue
            if latest is None or (request.resolved_at or 0) > (latest.resolved_at or 0):
                latest = request
        if latest is None or latest.status != ApprovalStatus.APPROVED:
            return False
        # r37: 승인한 대상·동작과 지금 실행하려는 대상·동작이 다르면 소비하지 않는다(재승인 필요).
        if binding is not None and latest.binding and latest.binding != binding:
            logger.info("[Approval] 바인딩 불일치 — 재승인 필요: %s (%s)", tool_name, latest.request_id[:8])
            return False
        if binding is not None and not latest.binding and tool_name in WRITE_TOOLS:
            return False
        self._consumed_approvals.add(latest.request_id)
        logger.info("[Approval] 일회성 승인 소비: %s (%s)", tool_name, latest.request_id[:8])
        return True

    def request_approval(
        self,
        tool_name: str,
        tool_args: dict[str, JsonValue],
        risk_level: str = "medium",
        description: str = "",
        project_root: str | None = None,
        layer: str = LAYER_STANDARD,
        *,
        actor_subject: str | None = None,
    ) -> ApprovalRequest:
        """새로운 승인 요청을 생성합니다.

        Args:
            tool_name: 도구 이름
            tool_args: 도구 인자
            risk_level: 위험도 (safe/low/medium/high/critical)
            description: 사람이 읽을 수 있는 설명
            project_root: diff 생성용 프로젝트 루트
            actor_subject: 요청 문맥이 없는 내부 경로가 넘기는 서버 확인 사용자

        Returns:
            ApprovalRequest (PENDING 상태)
        """
        scope = current_approval_scope(layer)
        if actor_subject is not None:
            if not actor_subject.strip() or actor_subject == "anonymous":
                raise ValueError("승인 요청에는 확인된 사용자가 필요합니다")
            scope["actor"] = actor_subject
        # "항상 허용"된 도구는 자동 승인 — r41: standard 층에만. strict(비밀·경로·권한) 층 요청은
        # 도구 단위 '항상 허용'으로 자동 통과하지 않는다(이전에는 execute_approved 로 우회됨).
        if (
            layer == LAYER_STANDARD
            and tool_name not in NO_ALWAYS_ALLOW_TOOLS
            and self.consume_always_allowed(tool_name, actor_subject=scope["actor"])
        ):
            return ApprovalRequest(
                request_id="auto-" + uuid.uuid4().hex[:8],
                tool_name=tool_name,
                tool_args=tool_args,
                risk_level=risk_level,
                description=description,
                status=ApprovalStatus.ALWAYS_ALLOW,
                resolved_at=time.time(),
                scope=scope,
            )

        # diff 미리보기 생성 (파일 편집 도구)
        diff_preview = self._generate_diff_preview(tool_name, tool_args, project_root)
        target = describe_write_target(tool_name, tool_args, project_root)
        binding = approval_binding(tool_name, tool_args, target)

        request = ApprovalRequest(
            request_id=uuid.uuid4().hex,
            tool_name=tool_name,
            tool_args=tool_args,
            risk_level=risk_level,
            description=description or f"{tool_name} 실행",
            diff_preview=diff_preview,
            timeout_sec=self._default_timeout,
            target=_public_target(target),
            binding=binding,
            scope=scope,
        )
        request.auto_review = self._safe_review(request)

        self._pending[request.request_id] = request
        logger.info(
            "[Approval] 승인 요청 생성: %s (%s, risk=%s)",
            request.request_id,
            tool_name,
            risk_level,
        )
        return request

    def _safe_review(self, request: ApprovalRequest) -> ApprovalReview:
        review_input = ApprovalReviewInput(
            tool_name=request.tool_name,
            tool_args=request.tool_args,
            risk_level=request.risk_level,
            description=request.description,
            diff_preview=request.diff_preview,
        )
        try:
            return self._review_provider.review(review_input)
        except (OSError, RuntimeError, TimeoutError, TypeError, ValueError) as exc:
            logger.warning("[Approval] 자동 검토 실패, 사용자 에스컬레이션: %s", exc)
            return ApprovalReview(
                decision=ApprovalReviewDecision.ESCALATE,
                risk_score=1.0,
                reason_codes=("reviewer_error",),
                rationale="자동 검토를 완료하지 못해 사용자 결정을 요구합니다.",
                reviewer="policy-fail-closed",
            )

    def resolve(
        self, request_id: str, decision: ApprovalDecision, *, actor_subject: str | None = None
    ) -> bool:
        """사용자의 결정을 처리합니다.

        Args:
            request_id: 승인 요청 ID
            decision: 사용자 결정 (approve/deny/always_allow)

        Returns:
            성공 여부
        """
        request = self._pending.get(request_id)
        if request is None or request.status != ApprovalStatus.PENDING:
            logger.warning("[Approval] 알 수 없거나 이미 해결된 요청: %s", request_id)
            return False
        if actor_subject is not None and (
            not actor_subject.strip()
            or actor_subject == "anonymous"
            or request.scope.get("actor", "") != actor_subject
        ):
            return False
        if decision == ApprovalDecision.ALWAYS_ALLOW and (
            request.tool_name in NO_ALWAYS_ALLOW_TOOLS or request.scope.get("layer", LAYER_STANDARD) != LAYER_STANDARD
        ):
            # r41: engine-level refusal (the API route check alone left direct callers open).
            logger.warning("[Approval] '항상 허용' 거부: %s", request.tool_name)
            return False
        if request.is_expired:  # r40: a decision after the request timed out is not accepted
            request.status = ApprovalStatus.TIMEOUT
            request.resolved_at = time.time()
            logger.warning("[Approval] 만료된 요청에 대한 결정 거부: %s", request_id)
            return False

        request.resolved_at = time.time()

        if decision == ApprovalDecision.APPROVE:
            request.status = ApprovalStatus.APPROVED
        elif decision == ApprovalDecision.DENY:
            request.status = ApprovalStatus.DENIED
        elif decision == ApprovalDecision.ALWAYS_ALLOW:
            request.status = ApprovalStatus.ALWAYS_ALLOW
            # 같은 사용자의 도구 하나를 덮는다(인자·경로·프로젝트 무관).
            with self._lock:
                self._always_allowed[(request.scope.get("actor", ""), request.tool_name)] = AlwaysAllowGrant(
                    tool_name=request.tool_name,
                    granted_at=request.resolved_at,
                    granted_for=request.description,
                )
            logger.info("[Approval] '항상 허용' 부여: %s (근거: %s)", request.tool_name, request.description)

        # 대기 중인 Future 해결
        future = self._futures.pop(request_id, None)
        if future and not future.done():
            future.set_result(request.status)

        logger.info(
            "[Approval] 해결: %s → %s",
            request_id,
            request.status.value,
        )
        return True

    async def wait_for_decision(self, request_id: str) -> ApprovalStatus:
        """승인 결정을 비동기로 대기합니다.

        타임아웃 시 자동으로 DENY(안전 기본값).

        Args:
            request_id: 승인 요청 ID

        Returns:
            최종 ApprovalStatus
        """
        request = self._pending.get(request_id)
        if request is None:
            return ApprovalStatus.DENIED

        # 이미 해결된 경우
        if request.status != ApprovalStatus.PENDING:
            return request.status

        # Future 생성
        loop = asyncio.get_event_loop()
        future: asyncio.Future[ApprovalStatus] = loop.create_future()
        self._futures[request_id] = future

        try:
            # 타임아웃과 함께 대기
            async with asyncio.timeout(request.timeout_sec):
                return await future
        except TimeoutError:
            request.status = ApprovalStatus.TIMEOUT
            request.resolved_at = time.time()
            logger.warning("[Approval] 타임아웃 자동 거부: %s", request_id)
            return ApprovalStatus.TIMEOUT

    def get_pending(self) -> list[ApprovalRequest]:
        """대기 중인 승인 요청 목록."""
        # 만료된 요청 정리
        expired = [rid for rid, req in self._pending.items() if req.is_expired]
        for rid in expired:
            req = self._pending[rid]
            req.status = ApprovalStatus.TIMEOUT
            req.resolved_at = time.time()
            future = self._futures.pop(rid, None)
            if future and not future.done():
                future.set_result(ApprovalStatus.TIMEOUT)

        return [req for req in self._pending.values() if req.status == ApprovalStatus.PENDING]

    def get_request(self, request_id: str) -> ApprovalRequest | None:
        """특정 승인 요청 조회."""
        return self._pending.get(request_id)

    def clear_resolved(self) -> int:
        """해결된 요청 정리 (메모리 관리)."""
        before = len(self._pending)
        self._pending = {rid: req for rid, req in self._pending.items() if req.status == ApprovalStatus.PENDING}
        cleared = before - len(self._pending)
        if cleared > 0:
            logger.debug("[Approval] 해결된 요청 %s개 정리", cleared)
        return cleared

    def reset_always_allowed(self, *, actor_subject: str | None = None) -> list[str]:
        """'항상 허용' 목록 초기화.

        반환값은 **되돌린 도구 이름들**이다 — 해제가 무엇을 되돌렸는지 응답이 말할 수 있어야 한다.
        """
        with self._lock:
            selected = sorted(
                (
                    (key, grant)
                    for key, grant in self._always_allowed.items()
                    if actor_subject is None or key[0] == actor_subject
                ),
                key=lambda item: item[1].granted_at,
            )
            revoked = [grant.tool_name for _key, grant in selected]
            for key, _grant in selected:
                del self._always_allowed[key]
        logger.info("[Approval] '항상 허용' 목록 초기화: %s", ", ".join(revoked) or "(없음)")
        return revoked

    # ─── r40: approval evidence (verify per layer, consume once at execution start) ───

    @staticmethod
    def _scope_sha(scope: Mapping[str, str]) -> str:
        return _sha(json.dumps(dict(scope), sort_keys=True))

    def _evidence_ok_locked(self, request: ApprovalRequest, binding: str, scope: Mapping[str, str]) -> str:
        """Return "" when usable, else the reason it is not (caller holds the lock)."""
        if request.status != ApprovalStatus.APPROVED:
            return f"status={request.status.value}"
        if request.request_id in self._consumed_approvals:
            return "already_consumed"
        if not request.binding or request.binding != binding:
            return "binding_mismatch"
        if not request.scope or self._scope_sha(request.scope) != self._scope_sha(scope):
            return "scope_mismatch"
        if request.resolved_at is None or (time.time() - request.resolved_at) > APPROVED_TTL_SEC:
            return "expired"
        for other in self._pending.values():  # a newer DENY for the same action wins
            if (
                other.tool_name == request.tool_name
                and other.binding == binding
                and other.scope == request.scope
                and other.status in (ApprovalStatus.DENIED, ApprovalStatus.TIMEOUT)
                and (other.resolved_at or 0) > (request.resolved_at or 0)
            ):
                return "newer_denial"
        return ""

    def find_approved_evidence(
        self, tool_name: str, binding: str, layer: str = LAYER_STANDARD
    ) -> ApprovalEvidence | None:
        """Look up an unconsumed APPROVED request for exactly this action+scope. Does NOT consume."""
        scope = current_approval_scope(layer)
        with self._lock:
            candidates = sorted(
                (r for r in self._pending.values() if r.tool_name == tool_name and r.binding == binding),
                key=lambda r: r.resolved_at or 0,
                reverse=True,
            )
            for request in candidates:
                if not self._evidence_ok_locked(request, binding, scope):
                    return ApprovalEvidence(
                        request_id=request.request_id,
                        tool_name=tool_name,
                        binding=binding,
                        scope_sha=self._scope_sha(scope),
                        _token=self._evidence_token,
                    )
        return None

    def verify_evidence(self, evidence: object, tool_name: str, binding: str, layer: str = LAYER_STANDARD) -> str:
        """Independent per-layer check. Returns "" if valid, else a reason. Never consumes."""
        if not isinstance(evidence, ApprovalEvidence) or evidence._token is not self._evidence_token:
            return "untrusted_evidence"
        if evidence.tool_name != tool_name or evidence.binding != binding:
            return "binding_mismatch"
        scope = current_approval_scope(layer)
        if evidence.scope_sha != self._scope_sha(scope):
            return "scope_mismatch"
        with self._lock:
            request = self._pending.get(evidence.request_id)
            if request is None:
                return "unknown_request"
            return self._evidence_ok_locked(request, binding, scope)

    def consume_evidence(self, evidence: object, tool_name: str, binding: str, layer: str = LAYER_STANDARD) -> str:
        """Atomically re-verify and mark consumed. "" on success (exactly one caller wins)."""
        if not isinstance(evidence, ApprovalEvidence) or evidence._token is not self._evidence_token:
            return "untrusted_evidence"
        if evidence.tool_name != tool_name or evidence.binding != binding:
            return "binding_mismatch"
        scope = current_approval_scope(layer)
        if evidence.scope_sha != self._scope_sha(scope):
            return "scope_mismatch"
        with self._lock:
            request = self._pending.get(evidence.request_id)
            if request is None:
                return "unknown_request"
            reason = self._evidence_ok_locked(request, binding, scope)
            if reason:
                return reason
            self._consumed_approvals.add(request.request_id)
        logger.info("[Approval] r40 evidence consumed at execution start: %s (%s)", tool_name, evidence.request_id[:8])
        return ""

    # ─── diff 미리보기 생성 ──────────────────────────────────────────

    @staticmethod
    def _generate_diff_preview(
        tool_name: str,
        tool_args: dict[str, JsonValue],
        project_root: str | None,
    ) -> str:
        """파일 편집 도구의 diff 미리보기를 생성합니다."""
        # 파일 편집 도구만 diff 생성
        edit_tools = {"edit_file", "apply_patch", "multi_replace_file_content", "write_file", "write_artifact"}
        if tool_name not in edit_tools:
            return ""

        # apply_patch는 file_path가 아니라 patch 텍스트를 직접 사용
        if tool_name == "apply_patch":
            patch = _text_arg(tool_args, "patch")
            if patch:
                preview = patch[:2000] + ("\n... (truncated)" if len(patch) > 2000 else "")
                return ApprovalManager._redact_sensitive_preview("", preview)
            return ""

        if tool_name == "write_artifact":
            target = describe_write_target(tool_name, tool_args, project_root)
            if target is None:
                return ""
            real = str(target["_real"])
            content = _text_arg(tool_args, "content")
            label = f"{target['project']}/{target['path']}"
            try:
                if os.path.isfile(real):
                    with open(real, encoding="utf-8") as f:
                        old_content = f.read()
                    diff = difflib.unified_diff(
                        old_content.splitlines(keepends=True),
                        content.splitlines(keepends=True),
                        fromfile=f"{label} (before)",
                        tofile=f"{label} (after)",
                        n=3,
                    )
                    return ApprovalManager._redact_sensitive_preview(real, "".join(diff)[:4000])
            except (OSError, UnicodeDecodeError):
                return f"[기존 파일을 읽을 수 없어 diff 생략: {label}]"
            preview = f"**새 파일 생성:** {label}\n```\n{content[:1500]}\n```"
            return ApprovalManager._redact_sensitive_preview(real, preview)

        file_path = _text_arg(tool_args, "file_path")
        if not file_path:
            return ""

        # 절대 경로 변환
        if project_root and not os.path.isabs(file_path):
            file_path = os.path.join(project_root, file_path)

        try:
            # edit_file: old_str → new_str diff
            if tool_name == "edit_file":
                old_str = _text_arg(tool_args, "old_str")
                new_str = _text_arg(tool_args, "new_str")
                if old_str and new_str:
                    diff = difflib.unified_diff(
                        old_str.splitlines(keepends=True),
                        new_str.splitlines(keepends=True),
                        fromfile=f"{file_path} (before)",
                        tofile=f"{file_path} (after)",
                        n=3,
                    )
                    return ApprovalManager._redact_sensitive_preview(file_path, "".join(diff))

            # write_file: 전체 파일 내용
            elif tool_name == "write_file":
                content = _text_arg(tool_args, "content")
                if os.path.exists(file_path):
                    with open(file_path, encoding="utf-8") as f:
                        old_content = f.read()
                    diff = difflib.unified_diff(
                        old_content.splitlines(keepends=True),
                        content.splitlines(keepends=True),
                        fromfile=f"{file_path} (before)",
                        tofile=f"{file_path} (after)",
                        n=3,
                    )
                    return ApprovalManager._redact_sensitive_preview(file_path, "".join(diff))
                else:
                    preview = f"**새 파일 생성:**\n```\n{content[:1500]}\n```"
                    return ApprovalManager._redact_sensitive_preview(file_path, preview)

        except Exception:
            logger.debug("diff 미리보기 생성 실패 (non-critical)", exc_info=True)

        return ""

    @staticmethod
    def _redact_sensitive_preview(file_path: str, preview: str) -> str:
        searchable = f"{file_path} {preview}".lower()
        if any(marker in searchable for marker in _SENSITIVE_PATH_MARKERS) or _SECRET_CONTENT_RE.search(preview):
            path_label = file_path or "패치"
            return f"[민감 파일 diff가 마스킹되었습니다: {path_label}]"
        return preview


# ─── 싱글톤 ─────────────────────────────────────────────────────────

_approval_manager: ApprovalManager | None = None


def get_approval_manager() -> ApprovalManager:
    """ApprovalManager 싱글톤을 반환합니다."""
    global _approval_manager
    if _approval_manager is None:
        _approval_manager = ApprovalManager(review_provider=_build_default_review_provider())
    return _approval_manager


# 리뷰용 모델 매니저 공급자 주입 훅 — api 싱글턴/테스트 목이 여기로 연결된다.
# 엔진이 api 계층을 역방향 임포트하면 순환이 생기므로(api.dependencies →
# engine → api.dependencies) 주입으로 의존성을 반전한다.
_review_model_manager_provider: Callable[[], _ReviewModelManager] | None = None


def set_review_model_manager_provider(provider: Callable[[], _ReviewModelManager]) -> None:
    global _review_model_manager_provider
    _review_model_manager_provider = provider


def _build_default_review_provider() -> ApprovalReviewProvider:
    requested_model = os.getenv("AGK_APPROVAL_REVIEW_MODEL", "").strip()
    if not requested_model:
        return ApprovalReviewEngine()
    model_name = "qwen3.8" if requested_model.startswith("qwen3.8:") else requested_model

    if _review_model_manager_provider is not None:
        model_manager = _review_model_manager_provider()
    else:
        from antigravity_k.engine.model_manager import ModelManager
        from antigravity_k.engine.model_registry import ModelRegistry

        model_manager = ModelManager(ModelRegistry())

    def generate(prompt: str) -> str:
        return model_manager.generate(prompt, model_name)

    return LocalModelApprovalReviewProvider(generate, model_name=requested_model)


def reset_approval_manager() -> None:
    """테스트용 — ApprovalManager 재초기화."""
    global _approval_manager
    _approval_manager = None
