"""R02 residual: cross-process grant-cache freshness on shared CanonicalStore SoftFileLock.

Process A caches an AuthorityProfile; process B revokes and commits a newer
AuthorityProfile on the same store root. Stale in-memory cache still allows;
re-read from durable store must deny. Single-host SoftFileLock only —
multi-host / replicated grant cache remains OPEN (ATTACK_NOTES §7).
Independent R02-V still OPEN.
"""

from __future__ import annotations

import multiprocessing
from datetime import UTC, datetime, timedelta
from pathlib import Path

from antigravity_k.engine.cognitive.authority import (
    AuthorityDimension,
    AuthorityProfile,
    AuthorityQuery,
    AuthorityVerdict,
    RevocationRequest,
)
from antigravity_k.engine.cognitive.models import (
    AuthorityGrant,
    Producer,
    ProducerKind,
    Record,
    same_enum,
)
from antigravity_k.engine.cognitive.references import EntityType, new_id
from antigravity_k.engine.cognitive.store import CanonicalStore

NOW = datetime(2026, 9, 26, 12, 0, 0, tzinfo=UTC)
HOLDER = "agent:holder"


def _grant() -> AuthorityGrant:
    return AuthorityGrant(
        subject=HOLDER,
        dimension=AuthorityDimension.TOOL_WRITE,
        resource_scope="src",
        allowed_operations=("execute_tool", "read_only"),
        constraints=("no_network",),
        granted_by="human:mr.k",
        issued_at=NOW,
        expires_at=NOW + timedelta(hours=2),
        revision=1,
    )


def _profile_record(project: str, profile: AuthorityProfile) -> Record:
    return Record.create(
        entity_type=EntityType.AUTHORITY_PROFILE,
        project_id=project,
        producer=Producer(kind=ProducerKind.HUMAN, actor_id="human:mr.k"),
        payload=profile.publishable_payload(),
        created_at=NOW,
    )


def _latest_profile(store: CanonicalStore, project: str) -> AuthorityProfile:
    records = [
        record
        for record in store.list_committed(project)
        if same_enum(record.entity_type, EntityType.AUTHORITY_PROFILE)
    ]
    assert records, "expected at least one committed AuthorityProfile"
    return max((AuthorityProfile.from_record(record) for record in records), key=lambda item: item.revision)


def _query() -> AuthorityQuery:
    return AuthorityQuery(
        subject=HOLDER,
        dimension=AuthorityDimension.TOOL_WRITE,
        resource_scope="src/a.py",
        operation="read_only",
    )


def _r02_a6_grant_cache_worker(
    store_root: str,
    project: str,
    barrier,
    results,
    role: str,
) -> None:
    """spawn worker: holder caches profile; revoker commits revoke on shared CanonicalStore."""

    store = CanonicalStore(Path(store_root), git_enabled=False, lock_timeout=30.0)
    if role == "holder":
        cached = _latest_profile(store, project)
        before = cached.evaluate(_query(), now=NOW)
        assert before.allowed is True
        barrier.wait(timeout=30)
        barrier.wait(timeout=30)
        stale = cached.evaluate(_query(), now=NOW)
        fresh_profile = _latest_profile(store, project)
        fresh = fresh_profile.evaluate(_query(), now=NOW)
        results.put(
            {
                "role": role,
                "stale_allowed": bool(stale.allowed),
                "stale_verdict": stale.verdict.name,
                "fresh_allowed": bool(fresh.allowed),
                "fresh_verdict": fresh.verdict.name,
                "cached_revision": cached.revision,
                "fresh_revision": fresh_profile.revision,
            }
        )
        return

    barrier.wait(timeout=30)
    current = _latest_profile(store, project)
    revoked = current.revoke(
        RevocationRequest(
            subject=HOLDER,
            revoked_at=NOW + timedelta(minutes=1),
            revision=current.revision + 1,
            reason="cross-process revoke",
        )
    )
    store.commit_records([_profile_record(project, revoked)])
    barrier.wait(timeout=30)
    results.put({"role": role, "committed_revision": revoked.revision})


def test_r02_a6_cross_process_grant_cache_requires_reread(tmp_path: Path) -> None:
    """R02 Attack 6 residual: stale cache allows; store re-read sees revoke across processes.

    Uses real CanonicalStore SoftFileLock path for AuthorityProfile records
    (``records/authority_profile``). Single-host only; not Independent R02-V.
    """

    root = tmp_path / "store"
    project = new_id(EntityType.PROJECT)
    bootstrap = CanonicalStore(root, git_enabled=False, lock_timeout=30.0)
    initial = AuthorityProfile(revision=1, grants=(_grant(),))
    bootstrap.commit_records([_profile_record(project, initial)])
    assert _latest_profile(bootstrap, project).evaluate(_query(), now=NOW).allowed is True

    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    results = context.Queue()
    workers = [
        context.Process(
            target=_r02_a6_grant_cache_worker,
            args=(str(root), project, barrier, results, role),
        )
        for role in ("holder", "revoker")
    ]
    for worker in workers:
        worker.start()
    try:
        outcomes = [results.get(timeout=60) for _ in workers]
        for worker in workers:
            worker.join(timeout=30)
            assert worker.exitcode == 0, (worker.exitcode, outcomes)
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.terminate()
                worker.join(timeout=5)
        results.close()

    by_role = {item["role"]: item for item in outcomes}
    assert set(by_role) == {"holder", "revoker"}
    assert by_role["revoker"]["committed_revision"] == 2
    holder = by_role["holder"]
    # Stale in-memory cache still authorizes — proves re-read is mandatory.
    assert holder["stale_allowed"] is True
    assert holder["cached_revision"] == 1
    # Re-read from shared durable store sees revoke across processes.
    assert holder["fresh_allowed"] is False
    assert holder["fresh_verdict"] == AuthorityVerdict.REVOKED.name
    assert holder["fresh_revision"] == 2
