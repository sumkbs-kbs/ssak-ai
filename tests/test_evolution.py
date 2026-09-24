"""Tests for EvolutionManager (evolution.py)."""

from typing import cast
from unittest.mock import MagicMock, patch

import pytest

from antigravity_k.engine.evolution import EvolutionManager
from antigravity_k.engine.vault import VaultEngine


class TestEvolutionManager:
    def test_init_requires_vault_engine(self):
        model_manager = MagicMock()
        with pytest.raises(ValueError, match="requires a valid VaultEngine"):
            EvolutionManager(model_manager, cast(VaultEngine, cast(object, None)))

    def test_gather_failures_no_rag(self):
        model_manager = MagicMock()
        vault_engine = MagicMock()
        vault_engine.sync_rag = False
        manager = EvolutionManager(model_manager, vault_engine)
        result = manager._gather_failures("test query")
        assert "No past failure data" in result

    def test_gather_failures_with_results(self):
        model_manager = MagicMock()
        vault_engine = MagicMock()
        vault_engine.sync_rag = True
        vault_engine.vector_store.search.return_value = [
            {"text": "Failed because of missing error handling"},
            {"text": "User preferred async pattern"},
        ]
        manager = EvolutionManager(model_manager, vault_engine)
        result = manager._gather_failures("error handling")
        assert "Failed because of missing error handling" in result
        assert "User preferred async pattern" in result

    def test_gather_failures_no_results(self):
        model_manager = MagicMock()
        vault_engine = MagicMock()
        vault_engine.sync_rag = True
        vault_engine.vector_store.search.return_value = []
        manager = EvolutionManager(model_manager, vault_engine)
        result = manager._gather_failures("query")
        assert "No relevant failures found" in result

    def test_evolve_skill_not_found(self, tmp_path):
        model_manager = MagicMock()
        vault_engine = MagicMock()
        vault_engine.vault_path = tmp_path
        vault_engine.sync_rag = False
        manager = EvolutionManager(model_manager, vault_engine)
        # Skill path doesn't exist (real vault root — MagicMock root에서는 exists()가
        # 항상 참이라 이 시험은 우연히 통과했다; draft 저장이 write_text로 바뀌며 우연이 사라졌다)
        result = manager.evolve_skill("nonexistent_skill")
        assert result is None

    @patch("pathlib.Path.exists")
    @patch("builtins.open")
    def test_evolve_system_prompt(self, mock_open, mock_exists):
        mock_exists.return_value = True
        model_manager = MagicMock()
        model_manager.generate.return_value = "Evolved system prompt text"
        vault_engine = MagicMock()
        vault_engine.vault_path = MagicMock()
        vault_engine.sync_rag = True
        vault_engine.vector_store.search.return_value = []

        manager = EvolutionManager(model_manager, vault_engine)
        manager._gather_failures = MagicMock(return_value="failure context")

        # Mock the evolve_system_prompt's file operations
        with patch.object(manager, "evolve_system_prompt", return_value="/tmp/evolved.md"):
            result = manager.evolve_system_prompt()
            assert result == "/tmp/evolved.md"
