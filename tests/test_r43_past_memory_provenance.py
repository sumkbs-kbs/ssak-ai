"""Vault source identifiers must not become project-root file references."""

from dataclasses import dataclass
from pathlib import Path

import pytest

from antigravity_k.engine.past_memory import build_past_memory_block
from antigravity_k.tools.tool_path import resolve_tool_path


@dataclass(frozen=True, slots=True)
class SavedNoteSearch:
    source: str

    def search(self, query: str, n_results: int = 5) -> list[dict[str, str | dict[str, str]]]:
        return [{"text": "Synthetic badge identifier is HERON-CALDERA-7342.", "metadata": {"source": self.source}}]


@dataclass(frozen=True, slots=True)
class SavedNoteVault:
    vault_path: Path
    vector_store: SavedNoteSearch
    sync_rag: bool = True


def test_recalled_note_exposes_real_project_relative_read_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given a real vault note whose logical source does not exist at the project root.
    project = tmp_path / "project"
    vault_root = project / ".antigravity" / "vault_data"
    note = vault_root / "r42" / "synthetic-decision.md"
    note.parent.mkdir(parents=True)
    note.write_text("Synthetic badge identifier is HERON-CALDERA-7342.", encoding="utf-8")
    monkeypatch.chdir(project)
    vault = SavedNoteVault(vault_root, SavedNoteSearch("r42/synthetic-decision.md"))

    # When the shared memory block is assembled for either chat execution path.
    block, status, count = build_past_memory_block(
        vault, "What badge identifier did we agree on?", project_root=str(project)
    )

    # Then provenance identifies its namespace and the offered read path reaches the real note.
    assert (status, count) == ("hit", 1)
    assert "Source (vault-relative): r42/synthetic-decision.md" in block
    read_path = block.split("read_file path: ", 1)[1].splitlines()[0]
    assert read_path == ".antigravity/vault_data/r42/synthetic-decision.md"
    assert Path(resolve_tool_path(read_path, str(project))) == note
    assert "already supplied" in block
    assert "do not need another read_file" in block


@pytest.mark.parametrize("source", ["../outside.md", "r42/../note.md", "missing.md", "absolute-note", "..\\outside.md"])
def test_unresolvable_vault_sources_do_not_advertise_read_file_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    # Given source identifiers that cannot safely name a real contained vault note.
    project = tmp_path / "project"
    vault_root = project / ".antigravity" / "vault_data"
    vault_root.mkdir(parents=True)
    (vault_root / "note.md").write_text("synthetic note", encoding="utf-8")
    (vault_root.parent / "outside.md").write_text("outside vault", encoding="utf-8")
    if source == "absolute-note":
        source = str(vault_root / "note.md")
    monkeypatch.chdir(project)
    vault = SavedNoteVault(vault_root, SavedNoteSearch(source))

    # When retrieved memory is rendered.
    block, status, count = build_past_memory_block(vault, "What did we agree on?", project_root=str(project))

    # Then evidence remains usable without inventing a project read path.
    assert (status, count) == ("hit", 1)
    assert f"Source (vault-relative): {source}" in block
    assert "read_file path:" not in block


def test_external_vault_does_not_extend_project_file_access(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given a vault outside the request's project boundary.
    project = tmp_path / "project"
    project.mkdir()
    vault_root = tmp_path / "external-vault"
    vault_root.mkdir()
    (vault_root / "note.md").write_text("synthetic note", encoding="utf-8")
    monkeypatch.chdir(project)
    vault = SavedNoteVault(vault_root, SavedNoteSearch("note.md"))

    # When memory from that vault is rendered.
    block, _, _ = build_past_memory_block(vault, "What did we agree on?", project_root=str(project))

    # Then no absolute or escaping path is advertised as a permitted file read.
    assert "read_file path:" not in block
    assert str(vault_root) not in block


def test_vault_symlink_cannot_advertise_a_note_outside_vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given an in-project file outside the vault reached through a vault symlink.
    project = tmp_path / "project"
    vault_root = project / ".antigravity" / "vault_data"
    vault_root.mkdir(parents=True)
    outside_note = project / "outside.md"
    outside_note.write_text("outside vault", encoding="utf-8")
    (vault_root / "linked.md").symlink_to(outside_note)
    monkeypatch.chdir(project)
    vault = SavedNoteVault(vault_root, SavedNoteSearch("linked.md"))

    # When retrieved memory names the link.
    block, _, _ = build_past_memory_block(vault, "What did we agree on?", project_root=str(project))

    # Then project containment alone cannot turn it into a valid vault reference.
    assert "read_file path:" not in block


def test_omitted_project_root_does_not_authorize_a_file_from_process_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given a contained existing note and a process cwd that is not request authority.
    vault_root = tmp_path / ".antigravity" / "vault_data"
    vault_root.mkdir(parents=True)
    (vault_root / "note.md").write_text("synthetic note", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    vault = SavedNoteVault(vault_root, SavedNoteSearch("note.md"))

    # When the caller has not supplied the request's canonical project root.
    block, _, _ = build_past_memory_block(vault, "What did we agree on?")

    # Then the current working directory cannot implicitly authorize a file reference.
    assert "read_file path:" not in block
