from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Final

from typer.testing import CliRunner

from antigravity_k.cli import app
from tests._cli_subprocess import python_invocation

PROJECT_ROOT: Final = Path(__file__).resolve().parents[1]


def _run_cli(*arguments: str, cwd: Path = PROJECT_ROOT) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["COLUMNS"] = "80"
    # pytest가 venv 밖 인터프리터로 실행돼도 antigravity_k가 임포트 가능한
    # python으로 서브프로세스를 띄운다 (Phase 12 트리아지 → Phase 25 수정).
    # uv run은 프로젝트 루트에서만 프로젝트 환경을 적용하므로, tmp_path cwd 테스트는
    # cwd를 잠시 프로젝트 루트로 고정하고 uv에게 --project를 명시한다.
    argv = [*python_invocation(project=True), "-m", "antigravity_k.cli", *arguments]
    return subprocess.run(
        argv,
        check=False,
        cwd=cwd,
        capture_output=True,
        env=environment,
        text=True,
    )


def test_module_cli_help_exposes_documented_commands() -> None:
    result = _run_cli("--help")

    assert result.returncode == 0, result.stderr
    assert "serve" in result.stdout
    assert "models" in result.stdout
    assert "doctor" in result.stdout
    assert "task" in result.stdout


def test_module_cli_models_includes_default_local_qwen_profile() -> None:
    result = _run_cli("model", "list")

    assert result.returncode == 0, result.stderr
    assert "qwen3.6:latest" in result.stdout
    assert "Ollama" in result.stdout


def test_model_list_includes_models_discovered_from_local_backends() -> None:
    result = _run_cli("model", "list")

    assert result.returncode == 0, result.stderr
    assert "llava:latest" in result.stdout


def test_model_list_min_quality_filters_to_balanced_or_better() -> None:
    """Phase 45: LEVEL_ORDER 랭킹 필터 — balanced 이상만 표시 (대시보드 '균형 이상' 파리티)."""
    unfiltered = _run_cli("model", "list")
    assert unfiltered.returncode == 0, unfiltered.stderr

    filtered = _run_cli("model", "list", "--min-quality", "balanced")

    assert filtered.returncode == 0, filtered.stderr
    # 필터 안내가 출력에 표시된다.
    assert "balanced' 이상" in filtered.stdout
    # unknown(—) 행은 어떤 하한에서도 제외된다.
    assert "필터: 'balanced' 이상 표시 중" in filtered.stdout


def test_model_list_min_quality_premium_is_stricter_than_balanced() -> None:
    """등급 서열(LEVEL_ORDER) 실측 — premium 하한이 balanced 하한보다 같거나 적게 표시."""

    def _count(stdout: str) -> int:
        for line in stdout.splitlines():
            if "이상 표시 중" in line:
                return int(line.split("(")[1].split("개")[0])
        return -1

    balanced = _run_cli("model", "list", "--min-quality", "balanced")
    premium = _run_cli("model", "list", "--min-quality", "premium")

    assert balanced.returncode == 0, balanced.stderr
    assert premium.returncode == 0, premium.stderr
    assert _count(premium.stdout) <= _count(balanced.stdout)


def test_model_list_min_quality_rejects_unknown_level_with_exit_2() -> None:
    result = _run_cli("model", "list", "--min-quality", "ultra")

    assert result.returncode == 2
    assert "알 수 없는 품질 등급 'ultra'" in result.stdout
    assert "compact < balanced < high < premium" in result.stdout


def test_memory_alias_cli_creates_and_lists_project_schema(tmp_path: Path) -> None:
    # Given: an empty project workspace.
    project_root = tmp_path / "project"
    project_root.mkdir()

    # When: the operator creates and lists a project memory alias.
    created = _run_cli("memory", "alias-set", "database", "primary_db", cwd=project_root)
    listed = _run_cli("memory", "aliases", cwd=project_root)

    # Then: both commands succeed and the typed schema is persisted locally.
    assert created.returncode == 0, created.stderr
    assert listed.returncode == 0, listed.stderr
    assert "database" in listed.stdout
    assert "primary_db" in listed.stdout
    schema = (project_root / ".antigravity" / "memory" / "project_aliases.json").read_text(
        encoding="utf-8",
    )
    assert '"database"' in schema
    assert '"primary_db"' in schema


def test_memory_alias_cli_removes_alias_without_deleting_group_peers(tmp_path: Path) -> None:
    # Given: one canonical key has two aliases.
    project_root = tmp_path / "project"
    project_root.mkdir()
    _ = _run_cli("memory", "alias-set", "database", "primary_db", cwd=project_root)
    _ = _run_cli("memory", "alias-set", "database", "storage_backend", cwd=project_root)

    # When: one alias is removed.
    removed = _run_cli("memory", "alias-remove", "primary_db", cwd=project_root)
    listed = _run_cli("memory", "aliases", cwd=project_root)

    # Then: only the selected alias disappears.
    assert removed.returncode == 0, removed.stderr
    assert "primary_db" not in listed.stdout
    assert "storage_backend" in listed.stdout


def test_memory_alias_cli_rejects_builtin_redefinition_without_writing(tmp_path: Path) -> None:
    # Given: an empty project workspace.
    project_root = tmp_path / "project"
    project_root.mkdir()

    # When: the operator attempts to map a built-in key to a conflicting meaning.
    result = _run_cli("memory", "alias-set", "cache_backend", "database", cwd=project_root)

    # Then: validation fails and no schema is written.
    assert result.returncode != 0
    assert "alias" in (result.stdout + result.stderr).lower()
    assert not (project_root / ".antigravity" / "memory" / "project_aliases.json").exists()


def test_memory_alias_cli_rejects_unknown_removal_without_rewriting(tmp_path: Path) -> None:
    # Given: one valid alias schema already exists.
    project_root = tmp_path / "project"
    project_root.mkdir()
    created = _run_cli("memory", "alias-set", "database", "primary_db", cwd=project_root)
    path = project_root / ".antigravity" / "memory" / "project_aliases.json"
    original = path.read_bytes()

    # When: the operator removes an alias that is not configured.
    result = _run_cli("memory", "alias-remove", "missing_alias", cwd=project_root)

    # Then: the command fails and preserves the original schema bytes.
    assert created.returncode == 0, created.stderr
    assert result.returncode != 0
    assert path.read_bytes() == original


def test_task_resume_cli_waits_and_prints_accumulated_output(monkeypatch) -> None:
    from antigravity_k.api import dependencies

    class Runtime:
        def resume_task(self, task_id: str, target_model: str = "") -> bool:
            assert task_id == "direct_cli_001"
            assert target_model == "qwen3.6:latest"
            return True

        def wait_task(self, task_id: str, timeout: float | None = None) -> dict[str, object] | None:
            assert task_id == "direct_cli_001"
            assert timeout == 12
            return {"task_id": task_id, "status": "done"}

        def get_task_output(self, task_id: str) -> str | None:
            assert task_id == "direct_cli_001"
            return "partial-output\nDIRECT_RESUME_OK"

    monkeypatch.setattr(dependencies, "get_agent_runtime", lambda: Runtime())

    result = CliRunner().invoke(
        app,
        ["task", "resume", "direct_cli_001", "--model", "qwen3.6:latest", "--timeout", "12"],
    )

    assert result.exit_code == 0, result.output
    assert "DIRECT_RESUME_OK" in result.output
    assert "done" in result.output
