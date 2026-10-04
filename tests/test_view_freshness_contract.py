from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal, assert_never

import pytest

from antigravity_k.engine.conversation_store import ConversationRecord, ConversationStore


@pytest.fixture
def deferred_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ConversationStore:
    monkeypatch.setenv("AGK_CONVERSATION_VIEW_REFRESH", "coalesced")
    monkeypatch.setenv("AGK_CONVERSATION_VIEW_REFRESH_MAX_LAG", "8")
    return ConversationStore(storage_dir=tmp_path / "conversations")


def _append(store: ConversationStore, revision: int) -> int:
    return store.append(
        project_id="project",
        conversation_id="conversation",
        expected_revision=revision,
        role="user",
        content=f"turn-{revision + 1}",
    ).revision


def _view_sequence(store: ConversationStore) -> int:
    path = store._path_for("project", "conversation")
    if not path.exists():
        return 0
    return int(json.loads(path.read_text(encoding="utf-8"))["journal_seq"])


ReadSurface = Literal["get", "get_revision", "snapshot", "get_or_create", "export"]


@pytest.mark.parametrize("surface", ["get", "get_revision", "snapshot", "get_or_create", "export"])
def test_public_read_observes_and_converges_deferred_turns(
    deferred_store: ConversationStore,
    surface: ReadSurface,
) -> None:
    # Given two committed turns and a lagging view.
    revision = _append(deferred_store, 0)
    revision = _append(deferred_store, revision)
    assert _view_sequence(deferred_store) < 2
    # When a public read is made.
    match surface:
        case "get":
            record = deferred_store.get(project_id="project", conversation_id="conversation")
            assert record is not None and record.revision == revision
        case "get_revision":
            assert deferred_store.get_revision(project_id="project", conversation_id="conversation") == revision
        case "snapshot":
            assert deferred_store.snapshot(project_id="project", conversation_id="conversation").revision == revision
        case "get_or_create":
            assert (
                deferred_store.get_or_create(
                    project_id="project",
                    conversation_id="conversation",
                    expected_revision=revision,
                ).revision
                == revision
            )
        case "export":
            assert (
                deferred_store.export_original_history(
                    project_id="project",
                    conversation_id="conversation",
                )["message_count"]
                == 2
            )
        case unreachable:
            assert_never(unreachable)
    # Then the derived file converges too.
    assert _view_sequence(deferred_store) == 2


def test_restored_old_view_with_new_timestamp_observes_committed_turns(tmp_path: Path) -> None:
    store = ConversationStore(storage_dir=tmp_path)
    revision = _append(store, 0)
    view = store._path_for("project", "conversation")
    old = view.read_bytes()
    _append(store, revision)
    view.write_bytes(old)
    os.utime(view, None)
    reader = ConversationStore(storage_dir=tmp_path)
    assert reader.get_revision(project_id="project", conversation_id="conversation") == 2


def test_deferred_flush_does_not_resurrect_a_peer_deleted_conversation(deferred_store: ConversationStore) -> None:
    _append(deferred_store, 0)
    peer = ConversationStore(storage_dir=deferred_store._storage_dir)
    assert peer.delete_conversation(project_id="project", conversation_id="conversation")
    deferred_store.flush_views()
    assert not deferred_store._path_for("project", "conversation").exists()
    assert peer.get(project_id="project", conversation_id="conversation") is None


def test_deferred_flush_does_not_overwrite_a_peer_newer_turn(deferred_store: ConversationStore) -> None:
    revision = _append(deferred_store, 0)
    peer = ConversationStore(storage_dir=deferred_store._storage_dir)
    _append(peer, revision)
    deferred_store.flush_views()
    assert _view_sequence(deferred_store) == 2
    record = peer.get(project_id="project", conversation_id="conversation")
    assert record is not None and len(record.messages) == 2


def test_failed_flush_retains_pending_work_for_retry(
    deferred_store: ConversationStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _append(deferred_store, 0)
    persist = deferred_store._persist

    def fail_write(_record: ConversationRecord) -> None:
        raise OSError("injected view failure")

    monkeypatch.setattr(deferred_store, "_persist", fail_write)
    with pytest.raises(OSError, match="injected view failure"):
        deferred_store.flush_views()
    monkeypatch.setattr(deferred_store, "_persist", persist)
    deferred_store.flush_views()
    assert _view_sequence(deferred_store) == 1


def test_default_writes_view_once_for_every_append(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGK_CONVERSATION_VIEW_REFRESH", raising=False)
    store = ConversationStore(storage_dir=tmp_path)
    revision = 0
    for _ in range(12):
        revision = _append(store, revision)
        assert _view_sequence(store) == revision


def test_failed_read_flush_can_be_retried_by_explicit_flush(
    deferred_store: ConversationStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given an existing view followed by a deferred committed turn.
    revision = _append(deferred_store, 0)
    deferred_store.flush_views()
    _append(deferred_store, revision)
    persist = deferred_store._persist

    def fail_write(_record: ConversationRecord) -> None:
        raise OSError("injected read flush failure")

    monkeypatch.setattr(deferred_store, "_persist", fail_write)
    with pytest.raises(OSError, match="injected read flush failure"):
        deferred_store.get(project_id="project", conversation_id="conversation")
    monkeypatch.setattr(deferred_store, "_persist", persist)
    # When a shutdown flush retries the pending projection.
    deferred_store.flush_views()
    # Then the view includes the committed turn without another read.
    assert _view_sequence(deferred_store) == 2


def test_failed_bounded_flush_can_be_retried_without_another_append(
    deferred_store: ConversationStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a full deferral window whose projection write fails.
    revision = 0
    for _ in range(7):
        revision = _append(deferred_store, revision)
    persist = deferred_store._persist

    def fail_write(_record: ConversationRecord) -> None:
        raise OSError("injected bounded flush failure")

    monkeypatch.setattr(deferred_store, "_persist", fail_write)
    with pytest.raises(OSError, match="injected bounded flush failure"):
        _append(deferred_store, revision)
    monkeypatch.setattr(deferred_store, "_persist", persist)
    # When the writer retries only the pending projection.
    deferred_store.flush_views()
    # Then all committed events, including the failed append's event, are visible.
    assert _view_sequence(deferred_store) == 8


def test_coalescing_has_a_finite_window_without_replaying_each_turn(deferred_store: ConversationStore) -> None:
    revision = 0
    for _ in range(24):
        revision = _append(deferred_store, revision)
        assert 0 <= revision - _view_sequence(deferred_store) < 8
    assert _view_sequence(deferred_store) == revision
