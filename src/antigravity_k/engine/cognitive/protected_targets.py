"""Protected target enforcement (P03) — 헌법·Human authority·premise·역사 삭제 보호.

원칙:
- 헌법, Human authority ceiling, project premise 변경은 사람 승인 record가 있어야 한다.
- learned policy / brain / plugin / evolution / migration actor는 protected class를 **직접 변경할 수 없다**.
- 문서 hash 검사만으로는 보호가 아니다. 여기서 runtime writer allowlist를 강제한다.
- path는 realpath로 해석해 symlink 우회를 검출하고, project 밖으로 나가는 쓰기를 거부한다.
- policy가 바꿀 수 있는 것은 §36 운영 knob(allowlist)뿐이다. rule 문자열로 protected 경로를 우회하려는 시도도 거부한다.

이 모듈은 provider/UI를 import하지 않는다. 기존 tool gate와 store는 이 모듈의 판정을 그대로 사용한다.
"""

from __future__ import annotations

import os
import re
import shlex
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Final, final

from antigravity_k.engine.cognitive.models import PolicyTarget, same_enum

CONSTITUTION_DOC: Final[str] = "docs/ssak-ai-core/SSAK_AI_CONSTITUTION.md"
SOURCE_MANIFEST_DOC: Final[str] = "docs/ssak-ai-core/SOURCE_MANIFEST.json"
MASTER_PROMPT_DOC: Final[str] = "docs/ssak-ai-core/MASTER_PROMPT_V2_SOURCE.md"

STORE_CONTROL_COMMITTED: Final[str] = ".cognitive/committed"
STORE_LEGACY_MAP: Final[str] = ".cognitive/legacy/agency_map.json"
STORE_RECORDS_AUTHORITY: Final[str] = "records/authority_profile"
STORE_RECORDS_CONSTITUTION: Final[str] = "records/constitution_rule"
STORE_RECORDS_PROJECT: Final[str] = "records/project"


class ProtectedClass(StrEnum):
    CONSTITUTION = "CONSTITUTION"
    HUMAN_AUTHORITY = "HUMAN_AUTHORITY"
    PROJECT_PREMISE = "PROJECT_PREMISE"
    HISTORICAL_DELETION = "HISTORICAL_DELETION"


class WriteChannel(StrEnum):
    FILE_TOOL = "FILE_TOOL"
    SHELL = "SHELL"
    PLUGIN = "PLUGIN"
    MIGRATION = "MIGRATION"
    EVOLUTION = "EVOLUTION"
    CANONICAL_STORE = "CANONICAL_STORE"
    POLICY_APPLICATION = "POLICY_APPLICATION"


class ActorKind(StrEnum):
    HUMAN = "human"
    BODY = "body"
    BRAIN = "brain"
    LEARNED_POLICY = "learned_policy"
    PLUGIN = "plugin"
    EVOLUTION = "evolution"
    MIGRATION = "migration"
    TOOL = "tool"


class WriteOperation(StrEnum):
    CREATE = "CREATE"
    APPEND = "APPEND"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    MOVE = "MOVE"


class DecisionCode(StrEnum):
    ALLOWED = "ALLOWED"
    PROTECTED_WITHOUT_APPROVAL = "PROTECTED_WITHOUT_APPROVAL"
    ACTOR_FORBIDDEN = "ACTOR_FORBIDDEN"
    APPROVAL_DIGEST_MISMATCH = "APPROVAL_DIGEST_MISMATCH"
    APPROVAL_SCOPE_MISMATCH = "APPROVAL_SCOPE_MISMATCH"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    APPROVAL_REVOKED = "APPROVAL_REVOKED"
    APPROVAL_CLASS_MISMATCH = "APPROVAL_CLASS_MISMATCH"
    PATH_ESCAPE = "PATH_ESCAPE"
    SHELL_WRITE_INDETERMINATE = "SHELL_WRITE_INDETERMINATE"
    POLICY_TARGET_NOT_ALLOWED = "POLICY_TARGET_NOT_ALLOWED"


#: protected class를 직접 변경할 수 없는 actor. 사람 승인으로도 열리지 않는다.
FORBIDDEN_ACTORS: Final[frozenset[ActorKind]] = frozenset(
    {ActorKind.BRAIN, ActorKind.LEARNED_POLICY, ActorKind.PLUGIN, ActorKind.EVOLUTION, ActorKind.MIGRATION}
)

#: 사람 승인이 있어야 쓰기를 허용하는 actor.
APPROVAL_REQUIRED_ACTORS: Final[frozenset[ActorKind]] = frozenset({ActorKind.BODY, ActorKind.TOOL})

#: policy가 대상으로 삼을 수 있는 운영 knob(§36). protected class는 여기에 없다.
ALLOWED_POLICY_TARGETS: Final[frozenset[str]] = frozenset(target.value for target in PolicyTarget)

_SHELL_WRITE_TOKENS: Final[tuple[str, ...]] = (
    ">",
    ">>",
    "tee ",
    "cp ",
    "mv ",
    "rm ",
    "rmdir ",
    "sed -i",
    "truncate ",
    "dd ",
    "install ",
    "chmod ",
    "chown ",
    "patch ",
    "ln -s",
    "open(",
    "write_text",
    "Path.write",
)
_PROTECTED_NAME_HINTS: Final[tuple[str, ...]] = (
    "ssak_ai_constitution",
    "source_manifest",
    "master_prompt_v2_source",
    "agency_map",
    "authority_profile",
    "constitution_rule",
)
_PATH_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9_./~$-]*(?:/[A-Za-z0-9_.*-]+)+")


class ProtectionViolation(PermissionError):
    """protected target 쓰기 시도가 거부됐다."""

    def __init__(self, decision: ProtectionDecision) -> None:
        self.decision = decision
        super().__init__(f"{decision.code}: {decision.detail}")


@dataclass(frozen=True, slots=True)
class ProtectedRoot:
    absolute_path: str
    protected_class: ProtectedClass
    reason: str

    @staticmethod
    def of(root: str | Path, relative_path: str, protected_class: ProtectedClass, reason: str) -> ProtectedRoot:
        return ProtectedRoot(
            absolute_path=os.path.realpath(str(Path(root) / relative_path)),
            protected_class=protected_class,
            reason=reason,
        )


@dataclass(frozen=True, slots=True)
class HumanApproval:
    """사람 승인 record. action digest와 범위에 결박한다."""

    protected_class: ProtectedClass
    action_digest: str
    approved_by: str
    resource_scope: str
    issued_at: datetime
    revision: int
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.approved_by.startswith("human:"):
            raise ValueError("approval must be issued by a human actor id (human:...)")
        if self.issued_at.tzinfo is None:
            raise ValueError("approval issued_at must be timezone-aware UTC")

    def is_expired(self, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        reference = now if now is not None else datetime.now(UTC)
        return self.expires_at <= reference

    @property
    def revocation_key(self) -> tuple[str, str, int]:
        """취소 대상을 특정하는 key — 발급자·결박된 digest·개정."""

        return (self.approved_by, self.action_digest, self.revision)


def issue_human_approval(
    *,
    issuer: str,
    protected_class: ProtectedClass,
    action_digest: str,
    resource_scope: str,
    revision: int = 1,
    expires_at: datetime | None = None,
) -> HumanApproval:
    """사람 승인의 **발급** 경로. 검증(guard)만 있고 발급이 없으면 승인은 시험 fixture에서만 존재한다.

    발급 단계에서 계약을 강제한다: 발급자는 사람 식별자여야 하고(Body/Brain이 대신 발급할 수 없다),
    digest 결박 없는 승인은 만들어질 수 없다(빈 digest 승인은 모든 쓰기에 재사용되는 면허가 된다).
    발급 주체의 진위(그 사람이 실제로 입력했는가)는 사용자 표면(P11)의 몫이다 — 여기는 그 표면이
    지켜야 할 계약을 정의한다.
    """

    if not issuer.startswith("human:"):
        raise ValueError(f"approval issuer must be a human actor id (human:...), got {issuer!r}")
    if not action_digest:
        raise ValueError("approval must bind the action digest of the exact change being approved")
    return HumanApproval(
        protected_class=protected_class,
        action_digest=action_digest,
        approved_by=issuer,
        resource_scope=resource_scope,
        issued_at=datetime.now(UTC),
        revision=revision,
        expires_at=expires_at,
    )


@dataclass(frozen=True, slots=True)
class ProtectedWriteRequest:
    channel: WriteChannel
    actor_kind: ActorKind
    actor_id: str
    targets: tuple[str, ...]
    operation: WriteOperation = WriteOperation.UPDATE
    action_digest: str = ""
    project_root: str = ""
    approvals: tuple[HumanApproval, ...] = ()


@dataclass(frozen=True, slots=True)
class ProtectionDecision:
    allowed: bool
    code: DecisionCode
    detail: str
    matched_class: ProtectedClass | None = None
    matched_path: str | None = None
    matched_root: str | None = None
    evidence: Mapping[str, object] = field(default_factory=dict)


def default_protected_roots(
    project_root: str | Path,
    *,
    store_roots: Sequence[str | Path] = (),
) -> tuple[ProtectedRoot, ...]:
    """프로젝트 문서와 canonical store의 protected root를 만든다."""

    root = Path(project_root)
    roots: list[ProtectedRoot] = [
        ProtectedRoot.of(root, CONSTITUTION_DOC, ProtectedClass.CONSTITUTION, "헌법 원칙 원문"),
        ProtectedRoot.of(root, SOURCE_MANIFEST_DOC, ProtectedClass.CONSTITUTION, "원문 digest 증거"),
        ProtectedRoot.of(root, MASTER_PROMPT_DOC, ProtectedClass.CONSTITUTION, "원문 사본"),
    ]
    for store_root in store_roots:
        roots.extend(
            (
                ProtectedRoot.of(
                    store_root, STORE_RECORDS_CONSTITUTION, ProtectedClass.CONSTITUTION, "헌법 rule record"
                ),
                ProtectedRoot.of(
                    store_root, STORE_RECORDS_AUTHORITY, ProtectedClass.HUMAN_AUTHORITY, "authority profile record"
                ),
                ProtectedRoot.of(store_root, STORE_RECORDS_PROJECT, ProtectedClass.PROJECT_PREMISE, "project premise"),
                ProtectedRoot.of(
                    store_root, STORE_CONTROL_COMMITTED, ProtectedClass.HISTORICAL_DELETION, "공개된 이력 manifest"
                ),
                ProtectedRoot.of(store_root, STORE_LEGACY_MAP, ProtectedClass.HUMAN_AUTHORITY, "legacy 계보 mapping"),
            )
        )
    return tuple(roots)


@final
class ProtectedWriteGuard:
    """protected target write allowlist 판정기. 판정만 담당하고 부작용이 없다."""

    def __init__(
        self,
        project_root: str | Path,
        *,
        protected_roots: Sequence[ProtectedRoot] | None = None,
        store_roots: Sequence[str | Path] = (),
        clock: object | None = None,
    ) -> None:
        self.project_root = os.path.realpath(str(project_root))
        self.protected_roots: tuple[ProtectedRoot, ...] = tuple(
            protected_roots
            if protected_roots is not None
            else default_protected_roots(self.project_root, store_roots=store_roots)
        )
        self._clock = clock
        self._revoked: set[tuple[str, str, int]] = set()

    def revoke(self, approval: HumanApproval) -> None:
        """승인을 취소한다. 취소된 승인은 즉시 아무 쓰기도 열지 않는다(만료 전이라도)."""

        self._revoked.add(approval.revocation_key)

    # ── 분류 ────────────────────────────────────────────
    def _now(self) -> datetime:
        if self._clock is not None and callable(self._clock):
            value = self._clock()
            if isinstance(value, datetime):
                return value
        return datetime.now(UTC)

    def classify(self, target: str) -> ProtectedRoot | None:
        """대상 경로가 protected root에 속하는지 판정한다(symlink·traversal 해석 후)."""

        resolved = self._resolve(target)
        best: ProtectedRoot | None = None
        for root in self.protected_roots:
            if resolved == root.absolute_path or resolved.startswith(root.absolute_path + os.sep):
                if best is None or len(root.absolute_path) > len(best.absolute_path):
                    best = root
        return best

    def _resolve(self, target: str) -> str:
        candidate = Path(target)
        if not candidate.is_absolute():
            candidate = Path(self.project_root) / target
        return os.path.realpath(str(candidate))

    def _escapes_project(self, resolved: str) -> bool:
        return not (resolved == self.project_root or resolved.startswith(self.project_root + os.sep))

    # ── 판정 ────────────────────────────────────────────
    def evaluate(self, request: ProtectedWriteRequest) -> ProtectionDecision:
        resolved_targets: list[tuple[str, str]] = []
        for target in request.targets:
            resolved = self._resolve(target)
            if self._escapes_project(resolved):
                return ProtectionDecision(
                    allowed=False,
                    code=DecisionCode.PATH_ESCAPE,
                    detail=f"write target escapes project root: {target} -> {resolved}",
                    matched_path=target,
                )
            resolved_targets.append((target, resolved))

        for target, resolved in resolved_targets:
            root = self.classify(resolved)
            if root is None:
                continue
            return self._evaluate_protected(request, target, resolved, root)

        return ProtectionDecision(allowed=True, code=DecisionCode.ALLOWED, detail="not a protected target")

    def _evaluate_protected(
        self,
        request: ProtectedWriteRequest,
        target: str,
        resolved: str,
        root: ProtectedRoot,
    ) -> ProtectionDecision:
        if same_enum(request.actor_kind, ActorKind.HUMAN):
            return ProtectionDecision(
                allowed=True,
                code=DecisionCode.ALLOWED,
                detail="human partner has final authority over protected targets",
                matched_class=root.protected_class,
                matched_path=target,
                matched_root=root.absolute_path,
            )
        if request.actor_kind in FORBIDDEN_ACTORS:
            return ProtectionDecision(
                allowed=False,
                code=DecisionCode.ACTOR_FORBIDDEN,
                detail=f"{request.actor_kind} cannot change {root.protected_class}",
                matched_class=root.protected_class,
                matched_path=target,
                matched_root=root.absolute_path,
            )

        approval = self._match_approval(request, root)
        if isinstance(approval, ProtectionDecision):
            return approval
        return ProtectionDecision(
            allowed=True,
            code=DecisionCode.ALLOWED,
            detail=f"approved by {approval.approved_by} (revision {approval.revision})",
            matched_class=root.protected_class,
            matched_path=target,
            matched_root=root.absolute_path,
            evidence={"approval_digest": approval.action_digest, "scope": approval.resource_scope},
        )

    def _match_approval(
        self, request: ProtectedWriteRequest, root: ProtectedRoot
    ) -> HumanApproval | ProtectionDecision:
        candidates = [approval for approval in request.approvals if approval.protected_class is root.protected_class]
        if not candidates:
            code = (
                DecisionCode.APPROVAL_CLASS_MISMATCH if request.approvals else DecisionCode.PROTECTED_WITHOUT_APPROVAL
            )
            return ProtectionDecision(
                allowed=False,
                code=code,
                detail=f"{root.protected_class} 변경에는 같은 class의 사람 승인 record가 필요하다",
                matched_class=root.protected_class,
                matched_path=root.absolute_path,
                matched_root=root.absolute_path,
            )
        digest_matched = False
        scope_matched = False
        for approval in candidates:
            if request.action_digest and approval.action_digest != request.action_digest:
                continue
            digest_matched = True
            scope = self._resolve(approval.resource_scope)
            if not all(
                self._resolve(target) == scope or self._resolve(target).startswith(scope + os.sep)
                for target in request.targets
            ):
                continue
            scope_matched = True
            if approval.is_expired(self._now()):
                return ProtectionDecision(
                    allowed=False,
                    code=DecisionCode.APPROVAL_EXPIRED,
                    detail=f"approval expired at {approval.expires_at}",
                    matched_class=root.protected_class,
                    matched_path=root.absolute_path,
                    matched_root=root.absolute_path,
                )
            if approval.revocation_key in self._revoked:
                return ProtectionDecision(
                    allowed=False,
                    code=DecisionCode.APPROVAL_REVOKED,
                    detail=f"approval by {approval.approved_by} (revision {approval.revision}) was revoked",
                    matched_class=root.protected_class,
                    matched_path=root.absolute_path,
                    matched_root=root.absolute_path,
                )
            return approval
        if not digest_matched:
            return ProtectionDecision(
                allowed=False,
                code=DecisionCode.APPROVAL_DIGEST_MISMATCH,
                detail="approval does not bind the requested action digest",
                matched_class=root.protected_class,
                matched_path=root.absolute_path,
                matched_root=root.absolute_path,
            )
        if not scope_matched:
            return ProtectionDecision(
                allowed=False,
                code=DecisionCode.APPROVAL_SCOPE_MISMATCH,
                detail="approval scope does not cover every requested target",
                matched_class=root.protected_class,
                matched_path=root.absolute_path,
                matched_root=root.absolute_path,
            )
        return ProtectionDecision(
            allowed=False,
            code=DecisionCode.PROTECTED_WITHOUT_APPROVAL,
            detail="no usable approval",
            matched_class=root.protected_class,
            matched_path=root.absolute_path,
            matched_root=root.absolute_path,
        )

    def assert_allowed(self, request: ProtectedWriteRequest) -> ProtectionDecision:
        decision = self.evaluate(request)
        if not decision.allowed:
            raise ProtectionViolation(decision)
        return decision

    # ── shell / plugin / migration ──────────────────────
    def evaluate_shell_command(
        self,
        command: str,
        *,
        actor_kind: ActorKind = ActorKind.BODY,
        actor_id: str = "body:shell",
        action_digest: str = "",
        approvals: Sequence[HumanApproval] = (),
    ) -> ProtectionDecision:
        """shell 문자열에서 쓰기 대상을 추출해 같은 보호 경계로 판정한다."""

        lowered = command.lower()
        if not any(token in lowered for token in _SHELL_WRITE_TOKENS):
            return ProtectionDecision(allowed=True, code=DecisionCode.ALLOWED, detail="no write indicator")

        targets = extract_shell_write_targets(command, self.project_root)
        if not targets:
            if any(hint in lowered for hint in _PROTECTED_NAME_HINTS):
                return ProtectionDecision(
                    allowed=False,
                    code=DecisionCode.SHELL_WRITE_INDETERMINATE,
                    detail="protected 이름을 포함한 쓰기 명령을 안전하게 해석할 수 없다",
                )
            return ProtectionDecision(allowed=True, code=DecisionCode.ALLOWED, detail="no protected write target")

        return self.evaluate(
            ProtectedWriteRequest(
                channel=WriteChannel.SHELL,
                actor_kind=actor_kind,
                actor_id=actor_id,
                targets=targets,
                operation=WriteOperation.UPDATE,
                action_digest=action_digest,
                project_root=self.project_root,
                approvals=tuple(approvals),
            )
        )

    def evaluate_policy_target(
        self,
        target: str,
        *,
        rule: str = "",
        parameters: Mapping[str, object] | None = None,
        actor_kind: ActorKind = ActorKind.LEARNED_POLICY,
    ) -> ProtectionDecision:
        """learned policy가 protected authority를 바꾸려는 직접·간접 시도를 거부한다."""

        if target not in ALLOWED_POLICY_TARGETS:
            return ProtectionDecision(
                allowed=False,
                code=DecisionCode.POLICY_TARGET_NOT_ALLOWED,
                detail=f"policy target is not an allowlisted operational knob: {target}",
            )
        haystack = " ".join(
            [rule, *(str(key) for key in (parameters or {})), *(str(v) for v in (parameters or {}).values())]
        )
        lowered = haystack.lower()
        for hint in _PROTECTED_NAME_HINTS:
            if hint in lowered:
                return ProtectionDecision(
                    allowed=False,
                    code=DecisionCode.POLICY_TARGET_NOT_ALLOWED,
                    detail=f"policy text references a protected target: {hint}",
                )
        for root in self.protected_roots:
            relative = os.path.relpath(root.absolute_path, self.project_root)
            if relative.lower() in lowered:
                return ProtectionDecision(
                    allowed=False,
                    code=DecisionCode.POLICY_TARGET_NOT_ALLOWED,
                    detail=f"policy text references a protected path: {relative}",
                )
        return ProtectionDecision(
            allowed=True,
            code=DecisionCode.ALLOWED,
            detail=f"{actor_kind} may change operational knob {target}",
        )


def extract_shell_write_targets(command: str, project_root: str) -> tuple[str, ...]:
    """쓰기 명령에서 후보 경로를 뽑는다. 확신할 수 없으면 빈 결과를 돌려주고 호출부가 fail-closed로 처리한다."""

    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()

    candidates: list[str] = []
    for index, token in enumerate(tokens):
        if token in (">", ">>") and index + 1 < len(tokens):
            candidates.append(tokens[index + 1])
            continue
        if token.startswith(">") and len(token) > 1:
            candidates.append(token.lstrip(">"))
            continue
        if token.startswith("of=") and len(token) > 3:
            candidates.append(token[3:])
            continue
        if token.startswith("-"):
            continue
    for match in _PATH_TOKEN_RE.finditer(command):
        candidates.append(match.group(0))

    targets: list[str] = []
    for candidate in candidates:
        cleaned = candidate.strip().strip("'\"").rstrip(",;")
        if not cleaned or cleaned in ("/dev/null", "/dev/stderr", "/dev/stdout"):
            continue
        if not (cleaned.startswith("~") or "/" in cleaned):
            continue
        expanded = os.path.expanduser(cleaned)
        if not os.path.isabs(expanded):
            expanded = os.path.join(project_root, expanded)
        targets.append(os.path.normpath(expanded))
    return tuple(dict.fromkeys(targets))


def migration_guard(target_root: str | Path) -> ProtectedWriteGuard:
    """legacy migration 대상 root용 guard. migration 실제 경로(LegacyMigrationRunner)가 쓴다.

    migration의 **선언된 임무**는 사람이 dry-run report로 검토하는 새 canonical root에 legacy
    identity를 최초로 구축하는 일이다 — 그래서 PROJECT_PREMISE의 최초 CREATE는 이 guard가 연다.
    그 외의 protected class(헌법 rule·authority profile·공개 이력 manifest·계보 mapping)는
    migration 경로로 몰래 들어올 수 없다(ActorKind.MIGRATION은 승인이 있어도 금지다).
    이미 세워진 운영 store의 premise 변경은 이 guard가 아니라 그 store의 보호가 담당한다.
    """

    root = Path(target_root)
    store_dir = root / "canonical"
    roots = [
        protected
        for protected in default_protected_roots(root, store_roots=(store_dir,))
        if not same_enum(protected.protected_class, ProtectedClass.PROJECT_PREMISE)
    ]
    return ProtectedWriteGuard(root, protected_roots=tuple(roots))


__all__ = [
    "ALLOWED_POLICY_TARGETS",
    "APPROVAL_REQUIRED_ACTORS",
    "ActorKind",
    "DecisionCode",
    "FORBIDDEN_ACTORS",
    "HumanApproval",
    "ProtectedClass",
    "ProtectedRoot",
    "ProtectedWriteGuard",
    "ProtectedWriteRequest",
    "ProtectionDecision",
    "ProtectionViolation",
    "WriteChannel",
    "WriteOperation",
    "default_protected_roots",
    "extract_shell_write_targets",
    "issue_human_approval",
    "migration_guard",
]
