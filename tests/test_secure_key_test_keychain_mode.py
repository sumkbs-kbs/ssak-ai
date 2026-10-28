"""Test-only Keychain-disabled mode must never invoke the real macOS Keychain."""

from __future__ import annotations

import subprocess
from typing import Any

import pytest

from antigravity_k.engine import secure_key


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str], *a: Any, **k: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(args))
        if args and args[0] == "security":
            return subprocess.CompletedProcess(args, 0, stdout="keychain-seed-123456\n", stderr="")
        return subprocess.CompletedProcess(args, 0, stdout='"IOPlatformUUID" = "SYNTH-UUID-0001"\n', stderr="")


@pytest.fixture
def darwin(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    import platform

    rec = _Recorder()
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    monkeypatch.setattr(subprocess, "run", rec)
    return rec


def test_disabled_mode_never_calls_security(darwin: _Recorder, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGK_TEST_KEYCHAIN_BACKEND", "disabled")
    assert secure_key._get_keychain_seed() is None
    assert secure_key._set_keychain_seed("seed-abcdefgh") is False
    seed = secure_key._get_machine_seed()
    assert seed == "SYNTH-UUID-0001"
    assert not any(c and c[0] == "security" for c in darwin.calls)


@pytest.mark.parametrize("value", ["", "0", "Disabled", "off", "true"])
def test_default_and_other_values_keep_keychain_policy(
    darwin: _Recorder, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    if value:
        monkeypatch.setenv("AGK_TEST_KEYCHAIN_BACKEND", value)
    else:
        monkeypatch.delenv("AGK_TEST_KEYCHAIN_BACKEND", raising=False)
    assert secure_key._get_keychain_seed() == "keychain-seed-123456"
    assert secure_key._set_keychain_seed("seed-abcdefgh") is True
    assert [c[1] for c in darwin.calls if c[0] == "security"] == ["find-generic-password", "add-generic-password"]
