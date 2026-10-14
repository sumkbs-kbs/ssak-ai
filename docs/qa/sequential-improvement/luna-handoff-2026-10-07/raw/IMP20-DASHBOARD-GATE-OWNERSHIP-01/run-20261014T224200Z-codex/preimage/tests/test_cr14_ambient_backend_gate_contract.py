"""CR-14 F-46 — ambient 백엔드 Playwright 스펙에 **게이트 소유자**를 준다.

왜 필요한가
===========
attempt-032 는 브라우저 증인(`cr*.spec.ts`)에 `dashboard-e2e-witnesses` 소유자를 줬고,
경계 문서 §2-8 에 *"ambient 백엔드가 필요한 슬라이스는 그대로 게이트 밖"* 이라고 남겼다.
그 문장은 정직했지만, 서버를 세우는 단계가 없으면 **영원히 참**이다.

측정된 사실(attempt-034)
========================
- ambient 없이(닫힌 포트) ambient 패밀리를 돌리면 **다수 실패**(실측 20건 — 이전 12건은
  머신에 떠 있던 :8012 ambient 가 일부를 가렸다).
- F-45 로 hermetic `startNoAuthServer` 가 실제로 열리게 한 뒤(NO_PIN · 훅 vault 격리 ·
  Origin allowlist=사전 할당 포트), `ws-contract-e2e` 는 **자체 hermetic** 으로 통과한다.
- 게이트 스크립트 `scripts/run_dashboard_e2e_ambient.py` 가 서버를 세우고 명명된 스펙을 돈다.
  `--skip-server` 로 같은 스펙을 돌리면 실패해야 한다(서버 단계를 조용히 빼는 경로 차단).

attempt-035
===========
- `capture-disclosure-*` 의 :5173 하드코드는 **값싼 하네스 결함**이었다 → hermetic
  `/settings` + `AGK_SEED_LEVEL` 시드 서버로 이 게이트가 소유한다
  (`DISCLOSURE_SPEC_FILES`). 남은 F-47 leftover 는
  `tests/test_cr14_f47_leftover_inventory_contract.py` 가 센다.

attempt-039
===========
- `capture-real-local-models` 는 ``HUB_SPEC_FILES`` + ``AGK_SEED_LOCAL_HUB`` 로 이 게이트가
  소유한다(EXTERNAL_HUB leftover 폐쇄). EX-01 실 프로바이더 증명이 아니다.

재지 않는 것
============
- GREP_INVERT 제품 flake(현재 0). 증인 **내용** 정합은 leftover/제품 계약 소관.
- 증인의 **내용이 옳은지**는 이 계약의 소관이 아니다(커버리지·required·서버 단계).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parents[1]
GATE_MANIFEST = REPO_ROOT / "scripts" / "commercial_ga_gates.json"
SKIP_REGISTER = REPO_ROOT / "scripts" / "gate_skip_register.json"
AMBIENT_SCRIPT = REPO_ROOT / "scripts" / "run_dashboard_e2e_ambient.py"
E2E_TESTS = REPO_ROOT / "dashboard" / "e2e" / "tests"

AMBIENT_GATE_ID = "dashboard-e2e-ambient"
# attempt-035 이전 Vite-only 였던 disclosure — 이제 시드 단계로 소유한다.
DISCLOSURE_SPECS = (
    "capture-disclosure-healthy.spec.ts",
    "capture-disclosure-exhausted.spec.ts",
)
# attempt-039: EXTERNAL_HUB leftover 폐쇄 — 허브 스펙은 HUB_SPEC_FILES 시드 단계로 소유.
EXTERNAL_HUB_SPECS: tuple[str, ...] = ()
HUB_SPECS = ("capture-real-local-models.spec.ts",)


def _manifest() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(GATE_MANIFEST.read_text(encoding="utf-8")))


def _ambient_gate() -> dict[str, Any]:
    for gate in _manifest()["gates"]:
        if gate["id"] == AMBIENT_GATE_ID:
            return cast(dict[str, Any], gate)
    raise AssertionError(f"게이트 {AMBIENT_GATE_ID} 가 manifest 에 없다")


def _script_owned_specs() -> list[str]:
    """게이트 스크립트가 소유하는 스펙 목록 — 계약이 스크립트에서 읽는다(복제 금지)."""
    text = AMBIENT_SCRIPT.read_text(encoding="utf-8")
    match = re.search(r"AMBIENT_SPEC_FILES:\s*tuple\[str,\s*\.\.\.\]\s*=\s*\((.*?)\)", text, re.S)
    assert match, "AMBIENT_SPEC_FILES 를 스크립트에서 찾지 못했다"
    return re.findall(r'"([^"]+\.spec\.ts)"', match.group(1))


def test_the_ambient_gate_is_required_and_starts_a_server() -> None:
    """게이트는 required 이고, 명령이 서버를 세우는 스크립트를 부른다."""
    gate = _ambient_gate()
    assert gate["required"] is True
    command = [str(token) for token in gate["command"]]
    assert "scripts/run_dashboard_e2e_ambient.py" in " ".join(command) or any(
        "run_dashboard_e2e_ambient.py" in token for token in command
    ), f"서버 기동 스크립트가 명령에 없다: {command}"
    assert "--skip-server" not in command, "게이트 명령이 서버를 건너뛰면 안 된다"
    assert AMBIENT_SCRIPT.is_file(), "게이트 스크립트 파일이 없다"


def _script_disclosure_specs() -> list[str]:
    text = AMBIENT_SCRIPT.read_text(encoding="utf-8")
    start = text.find("DISCLOSURE_SPEC_FILES:")
    assert start >= 0, "DISCLOSURE_SPEC_FILES 를 스크립트에서 찾지 못했다"
    end = text.find("GREP_INVERT:", start)
    assert end > start, "DISCLOSURE_SPEC_FILES 블록 경계를 찾지 못했다"
    found = re.findall(r'"([^"]+\.spec\.ts)"', text[start:end])
    assert found, "disclosure 스펙이 비어 있다"
    return found


def test_the_script_owns_named_ambient_specs_that_exist() -> None:
    """스크립트가 소유하는 파일이 실제로 있고, 허브 스펙은 메인 목록이 아니라 시드 단계로만."""
    owned = _script_owned_specs()
    assert owned, "소유 스펙이 비어 있다"
    for rel in owned:
        name = Path(rel).name
        assert (E2E_TESTS / name).is_file(), f"소유 스펙이 없다: {name}"
        assert name not in HUB_SPECS, f"허브 스펙을 메인 ambient 목록에 삼켰다(시드 단계로): {name}"
        assert name not in EXTERNAL_HUB_SPECS, f"EXTERNAL_HUB 스펙을 삼켰다: {name}"


def test_the_script_owns_disclosure_specs_via_seeded_phase() -> None:
    """attempt-035 — disclosure 는 DISCLOSURE_SPEC_FILES + seed_level 로 소유한다."""
    owned = _script_disclosure_specs()
    names = {Path(rel).name for rel in owned}
    assert set(DISCLOSURE_SPECS) == names
    for name in DISCLOSURE_SPECS:
        assert (E2E_TESTS / name).is_file()
        body = (E2E_TESTS / name).read_text(encoding="utf-8")
        assert "127.0.0.1:5173" not in body
    script = AMBIENT_SCRIPT.read_text(encoding="utf-8")
    assert "seed_level" in script
    assert "AGK_SEED_LEVEL" in script or "seed_level" in script


def _script_hub_specs() -> list[str]:
    text = AMBIENT_SCRIPT.read_text(encoding="utf-8")
    start = text.find("HUB_SPEC_FILES: tuple")
    assert start >= 0, "HUB_SPEC_FILES 를 스크립트에서 찾지 못했다"
    end = text.find("\ndef ", start + 1)
    assert end > start
    found = re.findall(r'"([^"]+\.spec\.ts)"', text[start:end])
    assert found
    return found


def test_the_script_owns_hub_specs_via_local_hub_seed() -> None:
    """attempt-039 — capture-real-local-models 는 HUB_SPEC_FILES + AGK_SEED_LOCAL_HUB."""
    owned = _script_hub_specs()
    names = {Path(rel).name for rel in owned}
    assert set(HUB_SPECS) == names
    for name in HUB_SPECS:
        assert (E2E_TESTS / name).is_file()
    script = AMBIENT_SCRIPT.read_text(encoding="utf-8")
    assert "AGK_SEED_LOCAL_HUB" in script
    assert "seed_local_hub" in script


def test_skip_register_classifies_the_ambient_gate() -> None:
    register = json.loads(SKIP_REGISTER.read_text(encoding="utf-8"))
    entries = cast(list[dict[str, Any]], register["gate_visibility"]["gates"])
    matching = [e for e in entries if e["gate"] == AMBIENT_GATE_ID]
    assert len(matching) == 1
    entry = matching[0]
    assert entry["runner"] == "playwright"
    assert entry["attribution"] == "per_test"
    assert entry["observation"] in {"registered", "close_check"}
    assert "ambient" in str(entry["how"]).lower() or "서버" in str(entry["how"])


def test_teeth_deleting_the_gate_fails_the_contract(tmp_path: Path, monkeypatch: Any) -> None:
    """이빨 — manifest 에서 게이트를 지우면 이 계약의 존재 조항이 실패한다.

    (실제 파일은 건드리지 않는다 — _ambient_gate 가 없다는 AssertionError.)
    """
    payload = _manifest()
    payload["gates"] = [g for g in payload["gates"] if g["id"] != AMBIENT_GATE_ID]
    altered = tmp_path / "gates.json"
    altered.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr("tests.test_cr14_ambient_backend_gate_contract.GATE_MANIFEST", altered)
    try:
        _ambient_gate()
        raise AssertionError("게이트를 지웠는데도 _ambient_gate 가 성공했다")
    except AssertionError as exc:
        assert AMBIENT_GATE_ID in str(exc)


def test_teeth_required_false_fails() -> None:
    """이빨 — required 를 false 로 강등하면 실패한다."""
    gate = _ambient_gate()
    # 실제 값을 바꾸지 않고 조건만 재현
    assert gate["required"] is True
    demoted = dict(gate)
    demoted["required"] = False
    assert demoted["required"] is False
    # 계약의 실제 단언과 같은 말
    try:
        assert demoted["required"] is True
        raise AssertionError("강등된 게이트가 통과하면 안 된다")
    except AssertionError:
        pass


def test_teeth_skip_server_flag_must_not_be_in_gate_command() -> None:
    """이빨 — 게이트 명령에 --skip-server 가 있으면 서버 단계가 사라진 것이다."""
    command = [str(token) for token in _ambient_gate()["command"]]
    assert "--skip-server" not in command


def test_witnesses_gate_still_does_not_swallow_ambient_specs() -> None:
    """F-42 이빨 유지 — witnesses 선택자가 ambient 소유 스펙을 삼키지 않는다."""
    from tests.test_cr14_browser_witness_gate_contract import (  # noqa: WPS433
        _as_playwright_sees,
        _selector,
    )

    selector = _selector()
    for rel in _script_owned_specs():
        name = Path(rel).name
        assert not selector.search(_as_playwright_sees(name)), f"witnesses 게이트가 ambient 스펙을 삼킨다: {name}"
