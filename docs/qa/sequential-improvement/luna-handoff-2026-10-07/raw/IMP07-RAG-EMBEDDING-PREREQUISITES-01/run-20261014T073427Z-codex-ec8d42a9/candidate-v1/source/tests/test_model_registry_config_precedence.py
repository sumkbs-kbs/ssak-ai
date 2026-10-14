from pathlib import Path

import pytest

from antigravity_k.engine import model_registry


def write_registry(path: Path, name: str) -> Path:
    path.write_text(f"models:\n  embedding:\n    - name: {name}\n      provider: ollama\n      repo: {name}\n")
    return path


def test_explicit_config_path_precedes_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    explicit = write_registry(tmp_path / "explicit.yaml", "explicit-model")
    environment = write_registry(tmp_path / "environment.yaml", "environment-model")
    monkeypatch.setenv("AGK_CONFIG_FILE", str(environment))
    registry = model_registry.ModelRegistry(str(explicit))
    assert registry.get_model("explicit-model") is not None
    assert registry.get_model("environment-model") is None


def test_environment_config_is_used_when_path_omitted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    environment = write_registry(tmp_path / "environment.yaml", "environment-model")
    default = write_registry(tmp_path / "default.yaml", "default-model")
    monkeypatch.setenv("AGK_CONFIG_FILE", str(environment))
    monkeypatch.setattr(model_registry, "_default_config_path", lambda: default)
    registry = model_registry.ModelRegistry()
    assert registry.get_model("environment-model") is not None
    assert registry.get_model("default-model") is None


@pytest.mark.parametrize("empty_environment", [False, True])
def test_missing_or_empty_environment_preserves_default_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, empty_environment: bool
) -> None:
    default = write_registry(tmp_path / "default.yaml", "default-model")
    monkeypatch.delenv("AGK_CONFIG_FILE", raising=False)
    if empty_environment:
        monkeypatch.setenv("AGK_CONFIG_FILE", "")
    monkeypatch.setattr(model_registry, "_default_config_path", lambda: default)
    registry = model_registry.ModelRegistry()
    assert registry.get_model("default-model") is not None
