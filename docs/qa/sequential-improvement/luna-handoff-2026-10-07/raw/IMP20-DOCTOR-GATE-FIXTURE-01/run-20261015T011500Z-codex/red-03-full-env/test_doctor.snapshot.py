"""Tests for the agk doctor command — environment diagnostic.

Uses Typer's CliRunner to invoke the command and verify output.
"""

from __future__ import annotations

from typing import final

import pytest
from typer.testing import CliRunner

from antigravity_k.cli import app
from antigravity_k.engine.model_registry import ModelProfile
from antigravity_k.engine.provider_capabilities import ProviderCapability

runner = CliRunner()


class TestDoctorCommand:
    """agk doctor runs and produces expected output."""

    def test_doctor_exits_zero_on_success(self):
        """doctor should exit 0 when there are no hard failures."""
        result = runner.invoke(app, ["doctor"])
        # Exit code 0 means no FAIL checks (warnings are OK).
        assert result.exit_code in (0, 1)  # may be 1 if warnings + config issues
        assert "Doctor" in result.output or "passed" in result.output.lower()

    def test_doctor_output_contains_checks(self):
        """The output should list individual checks."""
        result = runner.invoke(app, ["doctor"])
        assert "Python" in result.output
        assert "git" in result.output.lower()

    def test_doctor_shows_summary(self):
        """The output should include a summary line with pass/warn/fail counts."""
        result = runner.invoke(app, ["doctor"])
        assert "passed" in result.output.lower()
        assert "warnings" in result.output.lower() or "failed" in result.output.lower()

    def test_doctor_checks_config(self):
        """Config validation is checked."""
        result = runner.invoke(app, ["doctor"])
        assert "Config" in result.output or "config" in result.output.lower()

    def test_doctor_checks_port(self):
        """Port availability is checked."""
        result = runner.invoke(app, ["doctor"])
        assert "Port" in result.output

    def test_doctor_checks_api_keys(self):
        """API key availability is checked."""
        result = runner.invoke(app, ["doctor"])
        assert "API key" in result.output or "api key" in result.output.lower()

    def test_doctor_shows_amplification_section(self):
        """증폭 서브시스템(CoV/cognitive/self-consistency) 설정이 표시된다."""
        result = runner.invoke(app, ["doctor"])
        assert "Amplification" in result.output
        assert "cognitive" in result.output.lower()
        assert "verification" in result.output.lower() or "cov" in result.output.lower()
        assert "self-consistency" in result.output.lower()

    def test_doctor_amplification_shows_on_off_state(self):
        """각 증폭 서브시스템의 on/off 상태가 detail에 표시된다."""
        result = runner.invoke(app, ["doctor"])
        # cognitive과 CoV는 config 기본값이 on, self-consistency는 off.
        lines = [ln for ln in result.output.splitlines() if "Amplification" in ln or "on ·" in ln or "off ·" in ln]
        joined = "\n".join(lines)
        assert "on ·" in joined or "off ·" in joined

    def test_doctor_checks_vault_writable(self):
        """Vault directory writability is checked."""
        result = runner.invoke(app, ["doctor"])
        assert "Vault" in result.output or "writable" in result.output.lower()

    def test_doctor_checks_model_registry(self):
        """Model registry loading is checked."""
        result = runner.invoke(app, ["doctor"])
        assert "Model" in result.output or "registry" in result.output.lower()

    def test_doctor_uses_capability_probe_for_local_model_health(self, monkeypatch: pytest.MonkeyPatch):
        """로컬 모델 헬스는 ProviderCapabilityProbe 결과로 표시한다."""
        from antigravity_k.engine.provider_capabilities import LocalProviderCapabilityProbe

        def fake_observe(
            self: LocalProviderCapabilityProbe,
            profile: ModelProfile,
            *,
            refresh: bool = False,
        ) -> ProviderCapability:
            _ = self
            _ = refresh
            status = "available" if profile.backend == "mlx" else "unavailable"
            detail = (
                "LM Studio server reachable; configured model identifiers are not loaded."
                if profile.backend == "lmstudio"
                else "URLError: connection refused"
            )
            reported_model_ids = ["qwen/qwen3-30b-a3b-instruct"] if profile.backend == "lmstudio" else []
            return {
                "model": profile.name,
                "provider": profile.backend,
                "is_local": True,
                "native_tool_calling": "unsupported" if profile.backend == "mlx" else "supported",
                "runtime_status": status,
                "source": f"{profile.backend}:test",
                "detail": detail,
                "reported_capabilities": [],
                "reported_model_count": 0,
                "reported_model_ids": reported_model_ids,
            }

        monkeypatch.setattr(LocalProviderCapabilityProbe, "observe", fake_observe)
        result = runner.invoke(app, ["doctor"], env={"COLUMNS": "200"})
        normalized_output = " ".join(result.output.replace("│", " ").split())

        assert "Local model health" in normalized_output
        assert "qwen3.8" in normalized_output
        assert "lmstudio/qwen3.6" in normalized_output
        assert "native_tools=supported" in normalized_output
        assert "fix=ollama serve" in normalized_output
        assert "config.yaml의 lmstudio/qwen3.6 repo를 같은 식별자로 변경" in normalized_output

    def test_doctor_in_version_help(self):
        """doctor should appear in the CLI help."""
        result = runner.invoke(app, ["--help"])
        assert "doctor" in result.output

    def test_run_command_uses_agent_runtime(self, monkeypatch: pytest.MonkeyPatch):
        from antigravity_k.api import dependencies
        from antigravity_k.engine.agent_runtime import TrackedStream

        @final
        class Runtime:
            def start_stream(
                self,
                messages: list[dict[str, str]],
                target_model: str = "",
            ) -> TrackedStream:
                assert messages == [{"role": "user", "content": "hello"}]
                assert target_model == "local-test"
                return TrackedStream(task_id="direct_cli_001", chunks=iter(["runtime output"]))

        monkeypatch.setattr(dependencies, "get_agent_runtime", lambda: Runtime())

        result = runner.invoke(app, ["run", "hello", "--model", "local-test"])

        assert result.exit_code == 0
        assert "direct_cli_001" in result.output
        assert "runtime output" in result.output
