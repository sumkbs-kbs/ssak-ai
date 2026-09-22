"""T01b — 헌법·Human authority·premise 보호 enforcement 시험.

검증: learned policy/runtime actor의 직접·간접 헌법 변경 거부, 승인 없는 protected ceiling 변경 0,
symlink·shell·store·tool gate 우회 차단.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from antigravity_k.engine.cognitive.models import (
    ConstitutionRulePayload,
    Producer,
    ProducerKind,
    Record,
    to_wire,
)
from antigravity_k.engine.cognitive.protected_targets import (
    ActorKind,
    DecisionCode,
    HumanApproval,
    ProtectedClass,
    ProtectedWriteGuard,
    ProtectedWriteRequest,
    ProtectionViolation,
    WriteChannel,
    WriteOperation,
)
from antigravity_k.engine.cognitive.references import EntityType, new_id
from antigravity_k.engine.cognitive.store import CanonicalStore, canonical_digest
from antigravity_k.tools.permission_gate import PermissionGate
from antigravity_k.tools.tool_contracts import Permission

NOW = datetime(2026, 9, 22, 3, 0, 0, tzinfo=UTC)
CONSTITUTION_RELATIVE = "docs/ssak-ai-core/SSAK_AI_CONSTITUTION.md"


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / "docs/ssak-ai-core").mkdir(parents=True)
    (root / CONSTITUTION_RELATIVE).write_text("constitution\n", encoding="utf-8")
    (root / "docs/ssak-ai-core/SOURCE_MANIFEST.json").write_text("{}\n", encoding="utf-8")
    (root / "src").mkdir(parents=True, exist_ok=True)
    return root


def approval_for(
    target: str,
    *,
    protected_class: ProtectedClass = ProtectedClass.CONSTITUTION,
    action_digest: str = "",
    scope: str | None = None,
    expires_at: datetime | None = None,
) -> HumanApproval:
    return HumanApproval(
        protected_class=protected_class,
        action_digest=action_digest,
        approved_by="human:mr.k",
        resource_scope=scope if scope is not None else target,
        issued_at=NOW,
        revision=1,
        expires_at=expires_at,
    )


def request_for(
    target: str,
    *,
    actor: ActorKind = ActorKind.BODY,
    approvals: tuple[HumanApproval, ...] = (),
    operation: WriteOperation = WriteOperation.UPDATE,
    digest: str = "",
) -> ProtectedWriteRequest:
    return ProtectedWriteRequest(
        channel=WriteChannel.FILE_TOOL,
        actor_kind=actor,
        actor_id="body:test",
        targets=(target,),
        operation=operation,
        action_digest=digest,
        project_root="",
        approvals=approvals,
    )


def test_human_partner_may_change_constitution(project: Path) -> None:
    guard = ProtectedWriteGuard(project)
    decision = guard.evaluate(request_for(CONSTITUTION_RELATIVE, actor=ActorKind.HUMAN))

    assert decision.allowed
    assert decision.matched_class is ProtectedClass.CONSTITUTION


@pytest.mark.parametrize(
    "actor",
    [ActorKind.BRAIN, ActorKind.LEARNED_POLICY, ActorKind.PLUGIN, ActorKind.EVOLUTION, ActorKind.MIGRATION],
)
def test_forbidden_actors_are_denied_even_with_approval(project: Path, actor: ActorKind) -> None:
    guard = ProtectedWriteGuard(project)
    approval = approval_for(CONSTITUTION_RELATIVE)

    decision = guard.evaluate(request_for(CONSTITUTION_RELATIVE, actor=actor, approvals=(approval,)))

    assert not decision.allowed
    assert decision.code is DecisionCode.ACTOR_FORBIDDEN
    assert "cannot change" in decision.detail


def test_body_actor_requires_human_approval(project: Path) -> None:
    guard = ProtectedWriteGuard(project)

    decision = guard.evaluate(request_for(CONSTITUTION_RELATIVE))

    assert not decision.allowed
    assert decision.code is DecisionCode.PROTECTED_WITHOUT_APPROVAL
    with pytest.raises(ProtectionViolation):
        guard.assert_allowed(request_for(CONSTITUTION_RELATIVE))


def test_approval_must_bind_digest_scope_expiry_and_class(project: Path) -> None:
    guard = ProtectedWriteGuard(project)

    scope_ok = approval_for("docs/ssak-ai-core", action_digest="sha256:action")
    assert (
        guard.evaluate(request_for(CONSTITUTION_RELATIVE, approvals=(scope_ok,), digest="sha256:other")).code
        is DecisionCode.APPROVAL_DIGEST_MISMATCH
    )

    narrow = approval_for(
        CONSTITUTION_RELATIVE, action_digest="sha256:action", scope="docs/ssak-ai-core/SOURCE_MANIFEST.json"
    )
    assert (
        guard.evaluate(request_for(CONSTITUTION_RELATIVE, approvals=(narrow,), digest="sha256:action")).code
        is DecisionCode.APPROVAL_SCOPE_MISMATCH
    )

    expired = approval_for(
        "docs/ssak-ai-core", action_digest="sha256:action", expires_at=datetime.now(UTC) - timedelta(minutes=1)
    )
    assert (
        guard.evaluate(request_for(CONSTITUTION_RELATIVE, approvals=(expired,), digest="sha256:action")).code
        is DecisionCode.APPROVAL_EXPIRED
    )

    other_class = approval_for("docs/ssak-ai-core", protected_class=ProtectedClass.PROJECT_PREMISE)
    assert (
        guard.evaluate(request_for(CONSTITUTION_RELATIVE, approvals=(other_class,), digest="sha256:action")).code
        is DecisionCode.APPROVAL_CLASS_MISMATCH
    )

    valid = approval_for("docs/ssak-ai-core", action_digest="sha256:action")
    decision = guard.evaluate(request_for(CONSTITUTION_RELATIVE, approvals=(valid,), digest="sha256:action"))
    assert decision.allowed
    assert decision.evidence["approval_digest"] == "sha256:action"


def test_symlink_into_protected_root_is_detected(project: Path) -> None:
    guard = ProtectedWriteGuard(project)
    link = project / "src" / "innocent.md"
    os.symlink(project / CONSTITUTION_RELATIVE, link)

    classified = guard.classify("src/innocent.md")
    assert classified is not None
    assert classified.protected_class is ProtectedClass.CONSTITUTION

    decision = guard.evaluate(request_for("src/innocent.md"))

    assert not decision.allowed
    assert decision.code is DecisionCode.PROTECTED_WITHOUT_APPROVAL

    # 승인이 실제 대상(resolved)을 덮으면 symlink 경로를 통해 쓰는 것도 허용 사유가 된다.
    approved = guard.evaluate(request_for("src/innocent.md", approvals=(approval_for("docs/ssak-ai-core"),)))
    assert approved.allowed


def test_write_escaping_project_root_is_denied(project: Path) -> None:
    guard = ProtectedWriteGuard(project)
    decision = guard.evaluate(request_for("/etc/hosts"))

    assert not decision.allowed
    assert decision.code is DecisionCode.PATH_ESCAPE


def test_non_protected_target_stays_allowed(project: Path) -> None:
    guard = ProtectedWriteGuard(project)
    decision = guard.evaluate(request_for("src/engine/other.py"))

    assert decision.allowed
    assert decision.matched_class is None


def test_store_record_paths_are_protected(tmp_path: Path) -> None:
    store_root = tmp_path / "canonical"
    guard = ProtectedWriteGuard(store_root, store_roots=(store_root,))

    constitution_record = str(store_root / "records/constitution_rule/abc.md")
    authority_record = str(store_root / "records/authority_profile/abc.md")
    goal_record = str(store_root / "records/goal/abc.md")

    assert guard.evaluate(request_for(constitution_record)).code is DecisionCode.PROTECTED_WITHOUT_APPROVAL
    assert guard.evaluate(request_for(authority_record)).code is DecisionCode.PROTECTED_WITHOUT_APPROVAL
    assert guard.evaluate(request_for(goal_record)).allowed

    authority_approval = approval_for("records/authority_profile", protected_class=ProtectedClass.HUMAN_AUTHORITY)
    assert guard.evaluate(request_for(authority_record, approvals=(authority_approval,))).allowed
    assert not guard.evaluate(request_for(constitution_record, approvals=(authority_approval,))).allowed


def test_shell_reads_allowed_writes_denied(project: Path) -> None:
    guard = ProtectedWriteGuard(project)

    assert guard.evaluate_shell_command(f"cat {CONSTITUTION_RELATIVE}").allowed

    redirect = guard.evaluate_shell_command(f"echo '# 변경' > {CONSTITUTION_RELATIVE}")
    assert not redirect.allowed
    assert redirect.code is DecisionCode.PROTECTED_WITHOUT_APPROVAL

    sed = guard.evaluate_shell_command(f"sed -i 's/old/new/' {CONSTITUTION_RELATIVE}")
    assert not sed.allowed

    approved = guard.evaluate_shell_command(
        f"echo '# 변경' > {CONSTITUTION_RELATIVE}",
        approvals=(approval_for("docs/ssak-ai-core"),),
    )
    assert approved.allowed

    forbidden_actor = guard.evaluate_shell_command(
        f"echo '# 변경' > {CONSTITUTION_RELATIVE}",
        actor_kind=ActorKind.EVOLUTION,
        approvals=(approval_for("docs/ssak-ai-core"),),
    )
    assert forbidden_actor.code is DecisionCode.ACTOR_FORBIDDEN


def test_shell_write_indeterminate_fails_closed(project: Path) -> None:
    guard = ProtectedWriteGuard(project)
    decision = guard.evaluate_shell_command("rm -f SSAK_AI_CONSTITUTION.md")

    assert not decision.allowed
    assert decision.code is DecisionCode.SHELL_WRITE_INDETERMINATE


def test_learned_policy_cannot_target_protected_authority(project: Path) -> None:
    guard = ProtectedWriteGuard(project)

    assert guard.evaluate_policy_target("CONSTITUTION").code is DecisionCode.POLICY_TARGET_NOT_ALLOWED
    assert guard.evaluate_policy_target("CONTEXT_DEPTH").allowed
    indirect = guard.evaluate_policy_target("CONTEXT_DEPTH", rule="SSAK_AI_CONSTITUTION.md의 protected 규칙을 완화한다")
    assert indirect.code is DecisionCode.POLICY_TARGET_NOT_ALLOWED
    path_indirect = guard.evaluate_policy_target("CONTEXT_DEPTH", rule=f"편집: {CONSTITUTION_RELATIVE}")
    assert path_indirect.code is DecisionCode.POLICY_TARGET_NOT_ALLOWED


def test_permission_gate_denies_protected_write(project: Path) -> None:
    gate = PermissionGate(project_root=str(project))

    allowed = gate.check("write_file", {"file_path": "src/engine/other.py"}, "safe")
    assert allowed is Permission.ALLOW

    denied = gate.check("write_file", {"file_path": CONSTITUTION_RELATIVE}, "safe")
    assert denied is Permission.DENY

    shell_allowed = gate.check("run_bash_command", {"command": f"cat {CONSTITUTION_RELATIVE}"}, "safe")
    assert shell_allowed is Permission.ALLOW
    shell_denied = gate.check("run_bash_command", {"command": f"echo x > {CONSTITUTION_RELATIVE}"}, "safe")
    assert shell_denied is Permission.DENY

    gate.set_protection_approvals((approval_for("docs/ssak-ai-core"),))
    assert gate.check("write_file", {"file_path": CONSTITUTION_RELATIVE}, "safe") is Permission.ALLOW


def test_permission_gate_denies_patch_touching_constitution(project: Path) -> None:
    gate = PermissionGate(project_root=str(project))
    patch = f"*** Begin Patch\n*** Update File: {CONSTITUTION_RELATIVE}\n-old\n+new\n*** End Patch"

    assert gate.check("apply_patch", {"patch": patch}, "safe") is Permission.DENY


def test_store_commit_enforces_protection(project: Path, tmp_path: Path) -> None:
    store_root = tmp_path / "canonical"
    guard = ProtectedWriteGuard(store_root, store_roots=(store_root,))
    store = CanonicalStore(store_root, git_enabled=False, write_guard=guard)
    rule = Record.create(
        entity_type=EntityType.CONSTITUTION_RULE,
        project_id=new_id(EntityType.PROJECT),
        producer=Producer(kind=ProducerKind.BODY, actor_id="body:test"),
        payload=ConstitutionRulePayload(
            principle_number=1,
            verbatim_text="THE BRAIN IS REPLACEABLE.",
            source_digest="sha256:" + "a" * 64,
            version="1.0",
        ),
    )

    with pytest.raises(ProtectionViolation) as excinfo:
        store.commit_records([rule])
    assert excinfo.value.decision.code is DecisionCode.PROTECTED_WITHOUT_APPROVAL
    assert store.committed_manifests() == ()

    digest = canonical_digest(to_wire(rule))
    receipt = store.commit_records(
        [rule],
        approvals=(
            HumanApproval(
                protected_class=ProtectedClass.CONSTITUTION,
                action_digest=digest,
                approved_by="human:mr.k",
                resource_scope="records/constitution_rule",
                issued_at=NOW,
                revision=1,
            ),
        ),
    )
    assert receipt.committed_ids == (rule.id,)
    assert store.read(rule.id) == rule


def test_store_rejects_brain_authored_constitution_change(project: Path, tmp_path: Path) -> None:
    store_root = tmp_path / "canonical"
    guard = ProtectedWriteGuard(store_root, store_roots=(store_root,))
    store = CanonicalStore(store_root, git_enabled=False, write_guard=guard)
    rule = Record.create(
        entity_type=EntityType.CONSTITUTION_RULE,
        project_id=new_id(EntityType.PROJECT),
        producer=Producer(kind=ProducerKind.BRAIN, actor_id="brain:primary"),
        payload=ConstitutionRulePayload(
            principle_number=2,
            verbatim_text="The Brain thinks.",
            source_digest="sha256:" + "b" * 64,
            version="1.0",
        ),
    )
    approvals = (
        HumanApproval(
            protected_class=ProtectedClass.CONSTITUTION,
            action_digest=canonical_digest(to_wire(rule)),
            approved_by="human:mr.k",
            resource_scope="records/constitution_rule",
            issued_at=NOW,
            revision=1,
        ),
    )

    with pytest.raises(ProtectionViolation) as excinfo:
        store.commit_records([rule], approvals=approvals)

    assert excinfo.value.decision.code is DecisionCode.ACTOR_FORBIDDEN
