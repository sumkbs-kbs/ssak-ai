"""T02 — canonical store 불변 저장·복구 시험."""

from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path

import pytest

from antigravity_k.engine.cognitive.references import (
    EntityType,
    ReferenceValidationError,
    new_id,
)
from antigravity_k.engine.cognitive.store import (
    COMMITTED_DIR,
    CanonicalDigestError,
    CanonicalStore,
    CanonicalStoreError,
    DuplicateRecordError,
    GitCommitError,
    parse_record_markdown,
    record_relative_path,
    render_record_markdown,
)
from tests.cognitive._fixtures import (
    PRODUCER,
    build_decision,
    build_evidence,
    build_experience,
    build_goal,
    build_interpretation,
    build_judgment,
)


def make_store(tmp_path: Path, *, git_enabled: bool = False, commit_hook: object | None = None) -> CanonicalStore:
    return CanonicalStore(
        tmp_path / "store",
        git_enabled=git_enabled,
        git_committer=commit_hook,  # type: ignore[arg-type]
    )


def project_id() -> str:
    return new_id(EntityType.PROJECT)


def test_stage_does_not_publish(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    goal = build_goal(project_id())

    manifest = store.stage([goal], transaction_id="txn-1")

    assert manifest.status == "STAGED"
    assert store.read(goal.id) is None
    assert store.resolve(goal.id) is None
    assert store.list_committed() == ()
    assert not store.record_path(goal.id).exists()
    assert store.committed_manifests() == ()


def test_commit_publishes_and_reads_back(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    project = project_id()
    evidence = build_evidence(project)
    judgment = build_judgment(project, evidence.id)

    receipt = store.commit_records([evidence, judgment])

    assert receipt.committed_ids == (evidence.id, judgment.id)
    assert store.read(judgment.id) == judgment
    assert store.read(evidence.id) == evidence
    assert [record.id for record in store.list_committed(project)] == sorted([evidence.id, judgment.id])
    assert store.verify_digests() == 2
    assert store.rebuild_index() == 2


def test_record_files_are_markdown_with_frontmatter(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    goal = build_goal(project_id())
    store.commit_records([goal])

    path = store.record_path(goal.id)
    assert path.relative_to(store.root).as_posix() == record_relative_path(goal.id)
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    wire, digest = parse_record_markdown(text)
    assert wire["id"] == goal.id
    assert digest in text
    assert render_record_markdown(goal).startswith("---\n")


def test_duplicate_id_rejected(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    project = project_id()
    goal = build_goal(project)
    store.commit_records([goal])

    with pytest.raises(DuplicateRecordError):
        store.commit_records([goal], transaction_id="txn-same")

    other_payload = build_goal(project, statement="같은 ID, 다른 내용").payload
    tampered = goal.model_copy(update={"payload": other_payload})
    with pytest.raises(DuplicateRecordError):
        store.commit_records([tampered], transaction_id="txn-other")

    assert store.rebuild_index() == 1
    assert store.read(goal.id) == goal


def test_duplicate_id_inside_one_transaction_rejected(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    goal = build_goal(project_id())
    with pytest.raises(DuplicateRecordError):
        store.stage([goal, goal], transaction_id="txn-dup")


def test_failed_git_commit_is_invisible_then_recovered(tmp_path: Path) -> None:
    calls: list[str] = []

    def failing_committer(root: Path, message: str) -> str | None:
        calls.append(message)
        raise GitCommitError("simulated git failure")

    store = make_store(tmp_path, git_enabled=True, commit_hook=failing_committer)
    project = project_id()
    evidence = build_evidence(project)
    judgment = build_judgment(project, evidence.id)

    with pytest.raises(GitCommitError):
        store.commit_records([evidence, judgment], transaction_id="txn-crash")

    assert calls == ["cognitive transaction txn-crash"]
    assert store.read(judgment.id) is None
    assert store.committed_manifests() == ()
    assert store.record_path(judgment.id).exists(), "rename은 끝났지만 publish는 되지 않아야 한다"

    committed: list[str] = []

    def ok_committer(root: Path, message: str) -> str | None:
        committed.append(message)
        return "deadbeef"

    store._git_committer = ok_committer  # noqa: SLF001 - crash 주입 해제
    assert store.recover() == ("txn-crash",)

    assert store.read(judgment.id) == judgment
    assert store.read(evidence.id) == evidence
    assert store.verify_digests() == 2
    assert store.recover() == ()
    assert store.recover() == ()
    assert store.rebuild_index() == 2
    assert len(store.committed_manifests()) == 1


def test_unknown_transaction_rejected(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    with pytest.raises(CanonicalStoreError):
        store.commit("txn-missing")


def test_git_commit_is_recorded(tmp_path: Path) -> None:
    store = make_store(tmp_path, git_enabled=True)
    goal = build_goal(project_id())

    receipt = store.commit_records([goal], message="cognitive: goal")

    assert receipt.git_commit is not None
    log = subprocess.run(
        ["git", "-C", str(store.root), "log", "--oneline"], capture_output=True, text=True, check=False
    )
    assert "cognitive: goal" in log.stdout


def test_digest_tamper_detected(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    goal = build_goal(project_id())
    store.commit_records([goal])

    path = store.record_path(goal.id)
    tampered = path.read_text(encoding="utf-8").replace("canonical store 구현", "canonical store 변조")
    path.write_text(tampered, encoding="utf-8")

    with pytest.raises(CanonicalDigestError):
        store.read(goal.id)
    with pytest.raises(CanonicalDigestError):
        store.verify_digests()


def test_append_leaves_original_bytes_unchanged(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    project = project_id()
    experience = build_experience(project)
    store.commit_records([experience])
    original = store.record_path(experience.id).read_bytes()

    store.commit_records([build_interpretation(project, experience.id)])

    assert store.record_path(experience.id).read_bytes() == original
    assert store.verify_digests() == 2
    assert store.read(experience.id) == experience


def test_unresolved_reference_blocks_commit(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    project = project_id()
    judgment = build_judgment(project, new_id(EntityType.EVIDENCE))

    with pytest.raises(ReferenceValidationError, match="UNRESOLVED"):
        store.commit_records([judgment])

    assert store.committed_manifests() == ()


def test_cross_project_reference_blocked(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    project_a = project_id()
    project_b = project_id()
    evidence = build_evidence(project_a)
    store.commit_records([evidence])

    foreign_evidence = build_evidence(project_b)
    store.commit_records([foreign_evidence])
    cross = build_judgment(project_a, foreign_evidence.id)

    with pytest.raises(ReferenceValidationError, match="CROSS_PROJECT"):
        store.commit_records([cross])


def test_intra_transaction_reference_resolves(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    project = project_id()
    evidence = build_evidence(project)
    judgment = build_judgment(project, evidence.id)

    store.commit_records([judgment, evidence])

    assert store.read(judgment.id) is not None


def test_supersedes_cycle_rejected(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    project = project_id()
    first_id = new_id(EntityType.DECISION)
    second_id = new_id(EntityType.DECISION)
    first = build_decision(project, supersedes=(second_id,))
    second = build_decision(project, supersedes=(first_id,))
    first = first.model_copy(update={"id": first_id})
    second = second.model_copy(update={"id": second_id})

    with pytest.raises(ReferenceValidationError, match="SUPERSEDES_CYCLE"):
        store.commit_records([first, second])

    assert store.committed_manifests() == ()


def test_index_is_rebuildable_projection(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    project = project_id()
    store.commit_records([build_goal(project)])

    index_path = store.index_path
    assert index_path.exists()
    index_path.unlink()

    assert store.rebuild_index() == 1
    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert all(entry["project_id"] == project for entry in index.values())


def test_concurrent_same_id_commit_is_serialized(tmp_path: Path) -> None:
    root = tmp_path / "store"
    store_a = CanonicalStore(root, git_enabled=False, lock_timeout=10.0)
    store_b = CanonicalStore(root, git_enabled=False, lock_timeout=10.0)
    project = project_id()
    goal = build_goal(project)
    results: list[str] = []
    barrier = threading.Barrier(2)

    def commit(store: CanonicalStore, txn: str) -> None:
        barrier.wait()
        try:
            store.commit_records([goal], transaction_id=txn)
            results.append("committed")
        except DuplicateRecordError:
            results.append("duplicate")

    threads = [
        threading.Thread(target=commit, args=(store_a, "txn-a")),
        threading.Thread(target=commit, args=(store_b, "txn-b")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert sorted(results) == ["committed", "duplicate"]
    assert store_a.rebuild_index() == 1
    assert len(store_a.committed_manifests()) == 1


def test_references_survive_roundtrip_through_store(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    project = project_id()
    evidence = build_evidence(project)
    judgment = build_judgment(project, evidence.id)
    store.commit_records([evidence, judgment])

    restored = store.read(judgment.id)
    assert restored is not None
    assert restored.references == judgment.references
    assert restored.producer == PRODUCER
    assert str(restored.entity_type) == "BrainJudgment"
    assert (store.root / COMMITTED_DIR).exists()


# ── T02(실제 Vault 통합): VaultEngine write 경로와의 동시성 ────────────────


def test_real_vault_writer_shares_the_same_lock_and_serializes(tmp_path: Path) -> None:
    # 같은 repo root 배치에서 실제 VaultEngine의 write(git add/commit)와 CanonicalStore의
    # publish(git add/commit)가 **같은 lock 파일**(.git/.agk_vault.lock)로 직렬화된다 —
    # git index 경합(index.lock) 없이 모두 성공하고 원본은 그대로다.
    from antigravity_k.engine.vault import VaultEngine

    root = tmp_path / "shared-root"
    root.mkdir()
    vault = VaultEngine(str(root), sync_rag=False)  # .git 생성(같은 root 배치의 전제 순서)
    project = project_id()
    stores = [CanonicalStore(root, git_enabled=True, lock_timeout=30.0) for _ in range(2)]
    assert all(store.lock_path == root / ".git" / ".agk_vault.lock" for store in stores)

    errors: list[str] = []

    def vault_writes(tag: str) -> None:
        for i in range(3):
            try:
                vault.write_note(f"notes/{tag}-{i}.md", {"title": f"{tag}-{i}"}, f"body {tag} {i}")
            except Exception as exc:  # noqa: BLE001 — 폭풍에서 실패를 모아 보고한다
                errors.append(f"vault {tag}-{i}: {exc}")

    def store_commits(store: CanonicalStore, tag: str) -> None:
        for i in range(3):
            try:
                store.commit_records([build_experience(project)], transaction_id=f"cog-{tag}-{i}")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"store {tag}-{i}: {exc}")

    threads = [
        threading.Thread(target=vault_writes, args=("w1",)),
        threading.Thread(target=vault_writes, args=("w2",)),
        threading.Thread(target=store_commits, args=(stores[0], "s1")),
        threading.Thread(target=store_commits, args=(stores[1], "s2")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert errors == []
    assert len(stores[0].list_committed()) == 6
    assert stores[0].verify_digests() == 6
    for tag in ("w1", "w2"):
        for i in range(3):
            assert (root / "notes" / f"{tag}-{i}.md").exists()


def test_default_layout_coexists_with_vault_git_without_shared_lock(tmp_path: Path) -> None:
    # 기본 배치(default_store: .cognitive/canonical, git 비활성)는 vault와 lock 파일을 공유하지
    # 않는다 — store가 .git과 git index를 전혀 건드리지 않으므로 공유할 경합 자체가 없다.
    from antigravity_k.engine.cognitive.context import default_store
    from antigravity_k.engine.vault import VaultEngine

    root = tmp_path / "project"
    root.mkdir()
    vault = VaultEngine(str(root), sync_rag=False)
    store = default_store(root)

    assert store.lock_path != root / ".git" / ".agk_vault.lock"

    errors: list[str] = []
    for i in range(3):
        try:
            vault.write_note(f"notes/n-{i}.md", {"title": f"n-{i}"}, f"body {i}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"vault {i}: {exc}")
        try:
            store.commit_records([build_experience(project_id())], transaction_id=f"txn-{i}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"store {i}: {exc}")

    assert errors == []
    assert len(store.list_committed()) == 3
    assert store.verify_digests() == 3
    assert len(list((root / "notes").glob("n-*.md"))) == 3
