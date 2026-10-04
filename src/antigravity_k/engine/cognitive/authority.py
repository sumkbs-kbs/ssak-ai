"""Authority evaluation (P05) — 다차원 grant와 delegation 계약.

GOVERNANCE_AND_AUTHORITY.md 구현:

- **단일 Autonomy Score를 만들지 않는다.** 판정은 dimension별로 수행하고 결과도 dimension별로 남긴다.
- 판정 순서: ``protected/human-only boundary → 명시적 deny/revocation → 유효한 grant → limits → 부족한 범위 승인 요청``.
- grant는 ``subject, dimension, resource_scope, allowed_operations, constraints, granted_by,
  issued_at, expires_at, revision, revoked_at``를 가진다.
- learned policy는 인간 ceiling **아래의 실행 선택**만 바꾼다. grant 생성·ceiling 상향은 사람 결정이다.
- subagent delegation은 parent grant의 **부분집합**이며 만료·취소가 전파된다.
- 과거 승인 재사용은 같은 principal·scope·operation·유효기간 안에서만 한다.

판정 결과에는 scalar score가 없다. 감사·표시 계층이 합성 점수를 만들더라도 이 모듈의 근거가 될 수 없다.

이 모듈은 provider/UI/저장소를 import하지 않는다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final

from antigravity_k.engine.cognitive.models import (
    AuthorityDimension,
    AuthorityGrant,
    AuthorityProfilePayload,
    ProducerKind,
    Record,
    same_enum,
)
from antigravity_k.engine.cognitive.references import EntityType

#: 사람 결정 없이는 열리지 않는 operation. Body·Brain·learned policy가 스스로 수행할 수 없다.
HUMAN_ONLY_OPERATIONS: Final[frozenset[str]] = frozenset(
    {
        "grant_authority",
        "revoke_authority",
        "raise_ceiling",
        "change_human_ceiling",
        "constitution_change",
        "delete_history",
    }
)

#: 사람 결정이 필요한 dimension.
HUMAN_ONLY_DIMENSIONS: Final[frozenset[AuthorityDimension]] = frozenset({AuthorityDimension.CONSTITUTIONAL})

#: scope cover-all 표식.
ANY_SCOPE: Final[str] = "*"


class AuthorityVerdict(StrEnum):
    """dimension 단위 판정. 합산하지 않는다."""

    ALLOWED = "ALLOWED"
    HUMAN_ONLY_BOUNDARY = "HUMAN_ONLY_BOUNDARY"
    REVOKED = "REVOKED"
    NOT_GRANTED = "NOT_GRANTED"
    EXPIRED = "EXPIRED"
    SCOPE_OUT_OF_RANGE = "SCOPE_OUT_OF_RANGE"
    OPERATION_NOT_ALLOWED = "OPERATION_NOT_ALLOWED"
    CONSTRAINT_VIOLATED = "CONSTRAINT_VIOLATED"
    CEILING_EXCEEDED = "CEILING_EXCEEDED"
    DELEGATION_NOT_SUBSET = "DELEGATION_NOT_SUBSET"


class ApprovalReuseVerdict(StrEnum):
    REUSED = "REUSED"
    PRINCIPAL_MISMATCH = "PRINCIPAL_MISMATCH"
    SCOPE_MISMATCH = "SCOPE_MISMATCH"
    OPERATION_MISMATCH = "OPERATION_MISMATCH"
    EXPIRED = "EXPIRED"
    DIGEST_MISMATCH = "DIGEST_MISMATCH"


class AuthorityViolation(PermissionError):
    """권한 계약 위반. grant 생성·ceiling 상향 같은 사람 전용 행위를 actor가 시도했다."""


def scope_covers(outer: str, inner: str) -> bool:
    """``outer`` scope가 ``inner`` scope를 포함하는지 판정한다."""

    if outer == ANY_SCOPE or outer == inner:
        return True
    return inner.startswith(outer.rstrip("/") + "/")


def _expired(grant: AuthorityGrant, now: datetime) -> bool:
    return grant.expires_at is not None and grant.expires_at <= now


def _is_external_authority_subject(subject: str) -> bool:
    """프로필에 grant가 없는 사람/외부 주체(루트 발급자)로 본다."""

    return subject.startswith("human:") or subject.startswith("external:")


@dataclass(frozen=True, slots=True)
class AuthorityQuery:
    """특정 dimension의 특정 operation/scope에 대한 권한 질의."""

    subject: str
    dimension: AuthorityDimension
    resource_scope: str
    operation: str
    constraints: tuple[str, ...] = ()
    human_decision_id: str = ""


@dataclass(frozen=True, slots=True)
class AuthorityDecision:
    """dimension 단위 판정 결과. score field는 의도적으로 존재하지 않는다."""

    allowed: bool
    verdict: AuthorityVerdict
    reason: str
    dimension: AuthorityDimension
    grant: AuthorityGrant | None = None
    limits: tuple[str, ...] = ()
    resource_scope: str = ""
    human_decision_required: bool = False
    profile_revision: int = 0
    evidence: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DelegationRequest:
    """subagent/child에게 넘기는 grant 요청. parent의 부분집합이어야 한다."""

    parent_subject: str
    child_subject: str
    dimension: AuthorityDimension
    resource_scope: str
    allowed_operations: tuple[str, ...]
    constraints: tuple[str, ...] = ()
    expires_at: datetime | None = None
    revision: int = 1


@dataclass(frozen=True, slots=True)
class DelegationOutcome:
    ok: bool
    verdict: AuthorityVerdict
    reason: str
    grant: AuthorityGrant | None = None
    dropped_operations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RevocationRequest:
    subject: str
    revoked_at: datetime
    revision: int
    dimension: AuthorityDimension | None = None
    resource_scope: str | None = None
    reason: str = ""


@dataclass(frozen=True, slots=True)
class ApprovalUse:
    """재사용하려는 과거 승인. 유효기간·principal·scope·operation·digest로 결박한다."""

    approval_id: str
    principal: str
    resource_scope: str
    operation: str
    issued_at: datetime
    expires_at: datetime | None = None
    action_digest: str = ""


@dataclass(frozen=True, slots=True)
class ApprovalReuse:
    reusable: bool
    verdict: ApprovalReuseVerdict
    reason: str
    approval_id: str = ""


@dataclass(frozen=True, slots=True)
class AuthorityProfile:
    """grant 집합 + 인간 ceiling + revision. grant를 추가하려면 새 revision을 만든다."""

    revision: int
    grants: tuple[AuthorityGrant, ...] = ()
    human_ceiling: Mapping[AuthorityDimension, str] = field(default_factory=dict)
    ceiling_constraints: tuple[str, ...] = ()

    # ── 구성 ────────────────────────────────────────────
    @classmethod
    def from_grants(
        cls,
        grants: Sequence[AuthorityGrant],
        *,
        revision: int = 1,
        human_ceiling: Mapping[AuthorityDimension, str] | None = None,
    ) -> AuthorityProfile:
        return cls(revision=revision, grants=tuple(grants), human_ceiling=dict(human_ceiling or {}))

    @classmethod
    def from_record(cls, record: Record) -> AuthorityProfile:
        """canonical AuthorityProfile record를 평가 가능한 profile로 해석한다."""

        if not same_enum(record.entity_type, EntityType.AUTHORITY_PROFILE):
            raise AuthorityViolation(f"record is not an AuthorityProfile: {record.entity_type}")
        payload = record.payload
        if not isinstance(payload, AuthorityProfilePayload):
            raise AuthorityViolation("AuthorityProfile record payload mismatch")
        return cls(revision=payload.revision, grants=tuple(payload.grants))

    def publishable_payload(self, *, human_ceiling_ref: str | None = None) -> AuthorityProfilePayload:
        return AuthorityProfilePayload(
            grants=self.grants,
            human_ceiling_ref=human_ceiling_ref,
            revision=self.revision,
        )

    def _ancestor_failure(
        self, grant: AuthorityGrant, reference: datetime, *, trail: frozenset[str] | None = None
    ) -> AuthorityVerdict | None:
        """조상 체인이 유효하면 None, 아니면 EXPIRED/REVOKED/DELEGATION_NOT_SUBSET."""

        if grant.issued_at > reference:
            return AuthorityVerdict.NOT_GRANTED
        seen = set(trail or ())
        parent_subject = grant.granted_by
        if parent_subject in seen or parent_subject == grant.subject:
            return AuthorityVerdict.DELEGATION_NOT_SUBSET
        seen.add(grant.subject)

        parents = [
            candidate
            for candidate in self.grants
            if candidate.subject == parent_subject and same_enum(candidate.dimension, grant.dimension)
        ]
        if not parents:
            if _is_external_authority_subject(parent_subject):
                return None
            # dangling parent: 위임 그래프가 끊긴 자식은 거절
            return AuthorityVerdict.DELEGATION_NOT_SUBSET

        live = [candidate for candidate in parents if candidate.revoked_at is None]
        if not live:
            return AuthorityVerdict.REVOKED
        unexpired = [candidate for candidate in live if not _expired(candidate, reference)]
        if not unexpired:
            return AuthorityVerdict.EXPIRED
        covering = [parent for parent in unexpired if scope_covers(parent.resource_scope, grant.resource_scope)]
        if not covering:
            return AuthorityVerdict.SCOPE_OUT_OF_RANGE
        failures: list[AuthorityVerdict] = []
        for parent in covering:
            if (
                (
                    ANY_SCOPE not in parent.allowed_operations
                    and not set(grant.allowed_operations).issubset(parent.allowed_operations)
                )
                or not set(parent.constraints).issubset(grant.constraints)
                or (
                    parent.expires_at is not None and (grant.expires_at is None or grant.expires_at > parent.expires_at)
                )
            ):
                failures.append(AuthorityVerdict.DELEGATION_NOT_SUBSET)
                continue
            failure = self._ancestor_failure(parent, reference, trail=frozenset(seen))
            if failure is None:
                return None
            failures.append(failure)
        return failures[0]

    # ── 판정 ────────────────────────────────────────────
    def evaluate(self, query: AuthorityQuery, *, now: datetime | None = None) -> AuthorityDecision:
        reference = now if now is not None else datetime.now(UTC)

        if query.operation in HUMAN_ONLY_OPERATIONS or query.dimension in HUMAN_ONLY_DIMENSIONS:
            if query.human_decision_id:
                return AuthorityDecision(
                    allowed=True,
                    verdict=AuthorityVerdict.ALLOWED,
                    reason=f"human decision {query.human_decision_id} covers the human-only boundary",
                    dimension=query.dimension,
                    resource_scope=query.resource_scope,
                    profile_revision=self.revision,
                )
            return AuthorityDecision(
                allowed=False,
                verdict=AuthorityVerdict.HUMAN_ONLY_BOUNDARY,
                reason=(
                    f"{query.dimension} / {query.operation}는 사람 결정이 필요한 경계다. "
                    "Body·Brain·learned policy가 스스로 열 수 없다."
                ),
                dimension=query.dimension,
                resource_scope=query.resource_scope,
                human_decision_required=True,
                profile_revision=self.revision,
            )

        ceiling = self.human_ceiling.get(query.dimension)
        if ceiling is not None and not scope_covers(ceiling, query.resource_scope) and not query.human_decision_id:
            return AuthorityDecision(
                allowed=False,
                verdict=AuthorityVerdict.CEILING_EXCEEDED,
                reason=f"{query.dimension} 요청 scope가 사람 ceiling({ceiling})을 넘는다",
                dimension=query.dimension,
                resource_scope=query.resource_scope,
                human_decision_required=True,
                profile_revision=self.revision,
                evidence={"ceiling": ceiling},
            )

        # dimension은 same_enum으로 비교한다. 같은 이름의 enum이 프로세스 안에 두 번 로드되면 `is`는
        # 유효한 grant를 NOT_GRANTED→DEFER로 잘못 떨어뜨리고, `==`는 값이 같은 다른 enum까지 같다고 본다.
        candidates = [
            grant
            for grant in self.grants
            if grant.subject == query.subject and same_enum(grant.dimension, query.dimension)
        ]
        if not candidates:
            return AuthorityDecision(
                allowed=False,
                verdict=AuthorityVerdict.NOT_GRANTED,
                reason=f"{query.subject}에게 {query.dimension} grant가 없다",
                dimension=query.dimension,
                resource_scope=query.resource_scope,
                profile_revision=self.revision,
            )

        live = [grant for grant in candidates if grant.revoked_at is None]
        if not live:
            return AuthorityDecision(
                allowed=False,
                verdict=AuthorityVerdict.REVOKED,
                reason=f"{query.subject}의 {query.dimension} grant가 명시적으로 회수됐다",
                dimension=query.dimension,
                resource_scope=query.resource_scope,
                profile_revision=self.revision,
            )

        in_scope = [grant for grant in live if scope_covers(grant.resource_scope, query.resource_scope)]
        if not in_scope:
            return AuthorityDecision(
                allowed=False,
                verdict=AuthorityVerdict.SCOPE_OUT_OF_RANGE,
                reason=f"유효한 grant의 scope가 요청 scope를 포함하지 않는다: {query.resource_scope}",
                dimension=query.dimension,
                resource_scope=query.resource_scope,
                profile_revision=self.revision,
            )

        operation_ok = [
            grant
            for grant in in_scope
            if ANY_SCOPE in grant.allowed_operations or query.operation in grant.allowed_operations
        ]
        if not operation_ok:
            return AuthorityDecision(
                allowed=False,
                verdict=AuthorityVerdict.OPERATION_NOT_ALLOWED,
                reason=f"grant가 operation을 허용하지 않는다: {query.operation}",
                dimension=query.dimension,
                resource_scope=query.resource_scope,
                profile_revision=self.revision,
            )

        usable = [grant for grant in operation_ok if not _expired(grant, reference)]
        if not usable:
            soonest = max((grant.expires_at for grant in operation_ok if grant.expires_at is not None), default=None)
            return AuthorityDecision(
                allowed=False,
                verdict=AuthorityVerdict.EXPIRED,
                reason=f"grant가 만료됐다: {soonest}",
                dimension=query.dimension,
                resource_scope=query.resource_scope,
                profile_revision=self.revision,
            )

        chain_ok: list[AuthorityGrant] = []
        chain_failures: list[AuthorityVerdict] = []
        for candidate in usable:
            failure = self._ancestor_failure(candidate, reference)
            if failure is None:
                chain_ok.append(candidate)
            else:
                chain_failures.append(failure)
        if not chain_ok:
            verdict = chain_failures[0] if chain_failures else AuthorityVerdict.NOT_GRANTED
            return AuthorityDecision(
                allowed=False,
                verdict=verdict,
                reason=f"조상 grant가 유효하지 않다: {verdict}",
                dimension=query.dimension,
                resource_scope=query.resource_scope,
                profile_revision=self.revision,
            )

        grant = chain_ok[0]
        missing_constraints = [constraint for constraint in query.constraints if constraint not in grant.constraints]
        if missing_constraints:
            return AuthorityDecision(
                allowed=False,
                verdict=AuthorityVerdict.CONSTRAINT_VIOLATED,
                reason=f"grant가 요구 constraint를 포함하지 않는다: {missing_constraints}",
                dimension=query.dimension,
                grant=grant,
                resource_scope=query.resource_scope,
                profile_revision=self.revision,
            )

        return AuthorityDecision(
            allowed=True,
            verdict=AuthorityVerdict.ALLOWED,
            reason=f"grant {grant.resource_scope} ({grant.granted_by})가 요청을 포함한다",
            dimension=query.dimension,
            grant=grant,
            limits=tuple(grant.constraints),
            resource_scope=query.resource_scope,
            profile_revision=self.revision,
        )

    def dimension_view(
        self,
        subject: str,
        *,
        resource_scope: str,
        operation: str,
        constraints: tuple[str, ...] = (),
        now: datetime | None = None,
    ) -> dict[AuthorityDimension, AuthorityVerdict]:
        """모든 dimension의 판정을 나열한다. 합산 score로 축약하지 않는다."""

        return {
            dimension: self.evaluate(
                AuthorityQuery(
                    subject=subject,
                    dimension=dimension,
                    resource_scope=resource_scope,
                    operation=operation,
                    constraints=constraints,
                ),
                now=now,
            ).verdict
            for dimension in AuthorityDimension
        }

    # ── delegation ──────────────────────────────────────
    def delegate(self, request: DelegationRequest, *, now: datetime | None = None) -> DelegationOutcome:
        """parent grant의 부분집합만 위임한다. 넓어지면 거부한다."""

        reference = now if now is not None else datetime.now(UTC)
        parents = [
            grant
            for grant in self.grants
            if grant.subject == request.parent_subject
            and same_enum(grant.dimension, request.dimension)
            and grant.revoked_at is None
            and not _expired(grant, reference)
            and self._ancestor_failure(grant, reference) is None
        ]
        if not parents:
            return DelegationOutcome(
                ok=False,
                verdict=AuthorityVerdict.DELEGATION_NOT_SUBSET,
                reason=f"{request.parent_subject}에게 활성 {request.dimension} parent grant가 없다",
            )
        covering = [
            parent
            for parent in parents
            if scope_covers(parent.resource_scope, request.resource_scope)
            and (
                ANY_SCOPE in parent.allowed_operations
                or set(request.allowed_operations).issubset(parent.allowed_operations)
            )
            and set(parent.constraints).issubset(request.constraints)
            and (request.expires_at is None or parent.expires_at is None or request.expires_at <= parent.expires_at)
        ]
        parent = max(covering or parents, key=lambda grant: (len(grant.resource_scope), grant.revision))
        if request.child_subject == request.parent_subject or request.child_subject == parent.granted_by:
            return DelegationOutcome(
                ok=False,
                verdict=AuthorityVerdict.DELEGATION_NOT_SUBSET,
                reason="위임 대상이 자기 자신 또는 직접 조상이라 cycle이다",
            )

        if not scope_covers(parent.resource_scope, request.resource_scope):
            return DelegationOutcome(
                ok=False,
                verdict=AuthorityVerdict.DELEGATION_NOT_SUBSET,
                reason=f"child scope가 parent scope 밖이다: {request.resource_scope}",
            )
        if ANY_SCOPE not in parent.allowed_operations:
            extra = tuple(
                operation for operation in request.allowed_operations if operation not in parent.allowed_operations
            )
            if extra:
                return DelegationOutcome(
                    ok=False,
                    verdict=AuthorityVerdict.DELEGATION_NOT_SUBSET,
                    reason=f"child operation이 parent 부분집합이 아니다: {extra}",
                    dropped_operations=extra,
                )
        if request.expires_at is not None and parent.expires_at is not None and request.expires_at > parent.expires_at:
            return DelegationOutcome(
                ok=False,
                verdict=AuthorityVerdict.DELEGATION_NOT_SUBSET,
                reason="child 만료가 parent 만료보다 늦다",
            )
        # 생략된 자식 만료는 부모 ceiling을 상속한다. 부모보다 긴 권한을 만들지 않는다.
        child_expires = request.expires_at if request.expires_at is not None else parent.expires_at
        dropped = tuple(constraint for constraint in parent.constraints if constraint not in request.constraints)
        if dropped:
            return DelegationOutcome(
                ok=False,
                verdict=AuthorityVerdict.DELEGATION_NOT_SUBSET,
                reason=f"child가 parent constraint를 제거했다: {dropped}",
                dropped_operations=dropped,
            )

        grant = AuthorityGrant(
            subject=request.child_subject,
            dimension=request.dimension,
            resource_scope=request.resource_scope,
            allowed_operations=request.allowed_operations,
            constraints=request.constraints,
            granted_by=parent.subject,
            issued_at=reference,
            expires_at=child_expires,
            revision=request.revision,
        )
        return DelegationOutcome(ok=True, verdict=AuthorityVerdict.ALLOWED, reason="parent 부분집합 위임", grant=grant)

    # ── 회수·발급 ───────────────────────────────────────
    def revoke(self, request: RevocationRequest) -> AuthorityProfile:
        """회수된 grant를 새 revision에 반영한다. 원래 profile은 변경하지 않는다.

        parent를 회수하면 그 parent가 발급한 child grant에 전파된다.
        """

        # 후손 전체: granted_by 체인을 고정점까지 닫는다 (손자·증손 누락 방지).
        revoked_subjects: set[str] = {request.subject}
        changed = True
        while changed:
            changed = False
            for grant in self.grants:
                if grant.granted_by in revoked_subjects and grant.subject not in revoked_subjects:
                    revoked_subjects.add(grant.subject)
                    changed = True

        updated: list[AuthorityGrant] = []
        for grant in self.grants:
            targets_revoked_grant = grant.subject == request.subject
            if (
                targets_revoked_grant
                and request.dimension is not None
                and not same_enum(grant.dimension, request.dimension)
            ):
                targets_revoked_grant = False
            if (
                targets_revoked_grant
                and request.resource_scope is not None
                and not scope_covers(request.resource_scope, grant.resource_scope)
            ):
                targets_revoked_grant = False
            propagate = grant.granted_by in revoked_subjects
            if (targets_revoked_grant or propagate) and grant.revoked_at is None:
                updated.append(grant.model_copy(update={"revoked_at": request.revoked_at}))
            else:
                updated.append(grant)
        return AuthorityProfile(
            revision=request.revision,
            grants=tuple(updated),
            human_ceiling=dict(self.human_ceiling),
            ceiling_constraints=self.ceiling_constraints,
        )

    def issue_grant(self, grant: AuthorityGrant, *, actor_kind: ProducerKind) -> AuthorityProfile:
        """grant 발급은 사람만 한다. learned policy/Brain/Body는 새 권한을 만들 수 없다."""

        if not same_enum(actor_kind, ProducerKind.HUMAN):
            raise AuthorityViolation(f"{actor_kind}는 authority grant를 발급할 수 없다 (human only)")
        return AuthorityProfile(
            revision=self.revision + 1,
            grants=(*self.grants, grant),
            human_ceiling=dict(self.human_ceiling),
            ceiling_constraints=self.ceiling_constraints,
        )

    def propose_ceiling_change(
        self, *, subject: str, dimension: AuthorityDimension, requested_scope: str, reason: str
    ) -> AuthorityDecision:
        """ceiling 상향은 제안만 한다. 적용은 사람 결정이다."""

        return AuthorityDecision(
            allowed=False,
            verdict=AuthorityVerdict.CEILING_EXCEEDED,
            reason=f"ceiling 상향은 사람 결정이다: {reason}",
            dimension=dimension,
            resource_scope=requested_scope,
            human_decision_required=True,
            profile_revision=self.revision,
            evidence={"proposed_subject": subject, "proposed_scope": requested_scope},
        )

    # ── 승인 재사용 ─────────────────────────────────────
    def reuse_approval(
        self,
        approval: ApprovalUse,
        query: AuthorityQuery,
        *,
        now: datetime | None = None,
        action_digest: str = "",
    ) -> ApprovalReuse:
        """같은 principal·scope·operation·유효기간·action digest의 승인만 재사용한다."""

        reference = now if now is not None else datetime.now(UTC)
        if approval.principal != query.subject:
            return ApprovalReuse(
                reusable=False,
                verdict=ApprovalReuseVerdict.PRINCIPAL_MISMATCH,
                reason="승인 principal과 요청 subject가 다르다",
                approval_id=approval.approval_id,
            )
        if not scope_covers(approval.resource_scope, query.resource_scope):
            return ApprovalReuse(
                reusable=False,
                verdict=ApprovalReuseVerdict.SCOPE_MISMATCH,
                reason="승인 scope가 요청 scope를 포함하지 않는다",
                approval_id=approval.approval_id,
            )
        if approval.operation != query.operation:
            return ApprovalReuse(
                reusable=False,
                verdict=ApprovalReuseVerdict.OPERATION_MISMATCH,
                reason="승인 operation과 요청 operation이 다르다",
                approval_id=approval.approval_id,
            )
        if approval.expires_at is not None and approval.expires_at <= reference:
            return ApprovalReuse(
                reusable=False,
                verdict=ApprovalReuseVerdict.EXPIRED,
                reason=f"승인이 {approval.expires_at}에 만료됐다",
                approval_id=approval.approval_id,
            )
        # 모든 재사용 경로는 현재 canonical action digest에 결박한다 (생략/빈 값 불가).
        if not action_digest or not approval.action_digest or approval.action_digest != action_digest:
            return ApprovalReuse(
                reusable=False,
                verdict=ApprovalReuseVerdict.DIGEST_MISMATCH,
                reason="승인 action digest가 현재 요청 digest와 다르다",
                approval_id=approval.approval_id,
            )
        return ApprovalReuse(
            reusable=True,
            verdict=ApprovalReuseVerdict.REUSED,
            reason="같은 principal·scope·operation·유효기간·digest 안의 승인이다",
            approval_id=approval.approval_id,
        )


__all__ = [
    "ANY_SCOPE",
    "HUMAN_ONLY_DIMENSIONS",
    "HUMAN_ONLY_OPERATIONS",
    "ApprovalReuse",
    "ApprovalReuseVerdict",
    "ApprovalUse",
    "AuthorityDecision",
    "AuthorityProfile",
    "AuthorityQuery",
    "AuthorityVerdict",
    "AuthorityViolation",
    "DelegationOutcome",
    "DelegationRequest",
    "RevocationRequest",
    "scope_covers",
]
