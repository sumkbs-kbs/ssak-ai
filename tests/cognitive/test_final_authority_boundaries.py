"""Regression scenarios for relocation and delegated authority attenuation."""

import hashlib
import shlex
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, assert_never

import pytest

from antigravity_k.engine.cognitive.authority import AuthorityProfile, AuthorityQuery, DelegationRequest
from antigravity_k.engine.cognitive.models import AuthorityDimension, AuthorityGrant
from antigravity_k.engine.cognitive.protected_targets import CONSTITUTION_DOC
from antigravity_k.engine.sandbox import SandboxRunner

NOW = datetime(2026, 9, 27, tzinfo=UTC)


@pytest.mark.skipif(sys.platform != "darwin", reason="Requires real Seatbelt")
@pytest.mark.parametrize("ancestor", ["project", "docs", "container"])
@pytest.mark.parametrize("restrict_reads", [False, True])
def test_protected_bytes_survive_ancestor_relocation(tmp_path: Path, ancestor: str, restrict_reads: bool) -> None:
    # Given protected bytes in a disposable project under writable temporary storage.
    container = tmp_path / "container"
    root = container / "project"
    protected = root / CONSTITUTION_DOC
    protected.parent.mkdir(parents=True)
    _ = protected.write_bytes(b"ORIGINAL\n")
    before = hashlib.sha256(protected.read_bytes()).hexdigest()
    source = {"project": root, "docs": root / "docs", "container": container}[ancestor]
    moved = tmp_path / "relocated"
    moved_protected = moved / protected.relative_to(source)
    runner = SandboxRunner(project_root=str(root), enabled=True, require_sandbox=True, restrict_reads=restrict_reads)
    # When the real subprocess tries to move an ancestor, then mutate relocated bytes.
    result = runner.execute(
        f"/bin/mv {shlex.quote(str(source))} {shlex.quote(str(moved))} && "
        + f"/bin/echo CHANGED > {shlex.quote(str(moved_protected))}",
        cwd=str(tmp_path),
    )
    # Then the boundary blocks relocation and retains exactly the original bytes.
    assert result.sandboxed and not result.success
    assert protected.exists()
    assert hashlib.sha256(protected.read_bytes()).hexdigest() == before


@pytest.mark.skipif(sys.platform != "darwin", reason="Requires real Seatbelt")
def test_ordinary_sibling_rename_remains_allowed(tmp_path: Path) -> None:
    # Given an ordinary file beside a protected document.
    protected = tmp_path / CONSTITUTION_DOC
    protected.parent.mkdir(parents=True)
    _ = protected.write_bytes(b"ORIGINAL")
    ordinary = protected.parent / "notes.txt"
    _ = ordinary.write_text("notes")
    renamed = protected.parent / "renamed.txt"
    runner = SandboxRunner(project_root=str(tmp_path), enabled=True, require_sandbox=True)
    # When an ordinary sibling is renamed and updated.
    result = runner.execute(
        f"/bin/mv {shlex.quote(str(ordinary))} {shlex.quote(str(renamed))} && /bin/echo ok >> {shlex.quote(str(renamed))}"
    )
    # Then ordinary development remains permitted.
    assert result.success, result.stderr
    assert renamed.read_text() == "notesok\n"


def _grant(
    subject: str,
    issuer: str,
    operations: tuple[str, ...] = ("write",),
    constraints: tuple[str, ...] = (),
    issued_at: datetime = NOW,
    expires_at: datetime | None = None,
    scope: str = "workspace",
) -> AuthorityGrant:
    return AuthorityGrant(
        subject=subject,
        granted_by=issuer,
        dimension=AuthorityDimension.TOOL_WRITE,
        resource_scope=scope,
        allowed_operations=operations,
        constraints=constraints,
        issued_at=issued_at,
        expires_at=expires_at,
        revision=2,
    )


@pytest.mark.parametrize(
    "case", ["operations", "constraints", "future_parent", "future_child", "expiry", "grandparent"]
)
def test_child_cannot_exceed_current_ancestor_authority(
    case: Literal["operations", "constraints", "future_parent", "future_child", "expiry", "grandparent"],
) -> None:
    # Given a child whose stored grant no longer fits its current ancestor chain.
    parent = _grant("body:p", "human:owner")
    child = _grant("body:c", "body:p", scope="workspace/x")
    grants: list[AuthorityGrant] = []
    match case:
        case "operations":
            parent = _grant("body:p", "human:owner", operations=("read",))
        case "constraints":
            parent = _grant("body:p", "human:owner", constraints=("no_network",))
        case "future_parent":
            parent = _grant("body:p", "human:owner", issued_at=NOW + timedelta(hours=1))
        case "future_child":
            child = _grant("body:c", "body:p", issued_at=NOW + timedelta(hours=1))
        case "expiry":
            parent = _grant("body:p", "human:owner", expires_at=NOW + timedelta(hours=1))
        case "grandparent":
            parent = _grant("body:p", "body:g")
            grants.append(_grant("body:g", "human:owner", operations=("read",)))
        case unreachable:
            assert_never(unreachable)
    profile = AuthorityProfile.from_grants((*grants, parent, child), revision=2)
    # When the child requests a write based on its stale stored grant.
    decision = profile.evaluate(
        AuthorityQuery(
            subject="body:c", dimension=AuthorityDimension.TOOL_WRITE, resource_scope="workspace/x", operation="write"
        ),
        now=NOW,
    )
    # Then the whole chain must still authorize the child.
    assert not decision.allowed


def test_covering_parent_is_selected_among_multiple_grants() -> None:
    # Given unrelated narrow and applicable broad grants for the parent.
    profile = AuthorityProfile.from_grants(
        (
            _grant("body:p", "human:owner", scope="workspace/unrelated"),
            _grant("body:p", "human:owner", operations=("*",)),
            _grant("body:c", "body:p", scope="workspace/x"),
        )
    )
    # When the child requests the covered operation.
    decision = profile.evaluate(
        AuthorityQuery(
            subject="body:c", dimension=AuthorityDimension.TOOL_WRITE, resource_scope="workspace/x", operation="write"
        ),
        now=NOW,
    )
    # Then an actual covering chain authorizes it.
    assert decision.allowed


def test_delegate_rejects_parent_with_invalid_ancestry() -> None:
    # Given a parent whose own ancestor no longer permits writes.
    profile = AuthorityProfile.from_grants(
        (_grant("body:g", "human:owner", operations=("read",)), _grant("body:p", "body:g"))
    )
    # When it attempts to issue another write grant.
    result = profile.delegate(
        DelegationRequest(
            parent_subject="body:p",
            child_subject="body:c",
            dimension=AuthorityDimension.TOOL_WRITE,
            resource_scope="workspace/x",
            allowed_operations=("write",),
        ),
        now=NOW,
    )
    # Then issuance fails as well as later evaluation.
    assert not result.ok


@pytest.mark.skipif(sys.platform != "darwin", reason="Requires real Seatbelt")
def test_explicit_protected_target_prevents_root_relocation(tmp_path: Path) -> None:
    # Given a custom protected target supplied by a canonical store caller.
    root = tmp_path / "project"
    root.mkdir()
    protected = root / "authority.json"
    _ = protected.write_bytes(b"ORIGINAL")
    runner = SandboxRunner(
        project_root=str(root), enabled=True, require_sandbox=True, protected_write_deny_paths=(str(protected),)
    )
    # When the subprocess tries to relocate its containing workspace.
    result = runner.execute(
        f"/bin/mv {shlex.quote(str(root))} {shlex.quote(str(tmp_path / 'moved'))}", cwd=str(tmp_path)
    )
    # Then custom protection keeps the same relocation guarantee.
    assert not result.success
    assert protected.read_bytes() == b"ORIGINAL"


def test_missing_protection_policy_refuses_runner_creation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given unavailable protected policy construction.
    def unavailable(_root: str) -> tuple[str, ...]:
        raise RuntimeError("policy unavailable")

    monkeypatch.setattr("antigravity_k.engine.cognitive.protected_targets.sandbox_protected_write_denies", unavailable)
    # When mandatory sandbox initialization attempts to load the policy.
    # Then it cannot silently construct an unprotected runner.
    with pytest.raises(RuntimeError, match="policy unavailable"):
        _ = SandboxRunner(project_root=str(tmp_path), enabled=True, require_sandbox=True)
