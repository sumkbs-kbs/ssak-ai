"""CR-11 — clean CI/release 부트스트랩과 실제 의존성 감사.

수용 기준(docs/17 C11-01 ~ C11-05)을 설정 문자열 복사가 아니라 **실행**으로 고정한다:

  C11-01 신규 venv에서 내부 모듈 실행  → 워크플로가 editable/PYTHONPATH에 기대지 않는다.
  C11-02 cache 없는 frozen dashboard 설치/build → Node/pnpm 조합 계약.
  C11-03 base/출하 extras 감사 입력 기록·음성 입력 거부 → 감사 스크립트를 실제 실행.
  C11-04 wheel/sdist 저장소 밖 CLI/API/auth 실행 → 검증 스크립트가 워크플로에 배선됐는지.
  C11-05 번들 출처·Node 조합·dry-run 원문 → 번들 대조기가 낡은 번들을 잡아내는지.

무거운 실행(신규 venv 설치·wheel 빌드)은 `verify_*` 스크립트가 담당하고,
여기서는 그 스크립트가 **실패를 잡아내는지**와 배선을 검증한다.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = (".github/workflows/ci.yml", ".github/workflows/release.yml")
NODE_PIN_PATTERNS = (
    re.compile(r"node-version:\s*['\"]?([0-9][0-9.]*)"),
    re.compile(r"FROM\s+node:([0-9][0-9.]*)"),
)
PNPM_ACTION_PIN = re.compile(r"pnpm/action-setup@v\d+\s*\n\s*with:\s*\n\s*version:\s*([0-9][0-9.]*)")


def _read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def _without_comments(text: str) -> str:
    """YAML 주석 줄을 제거한다 — 주석에 적힌 문구를 계약으로 오인하지 않게."""
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def _flatten(text: str) -> str:
    """셸 줄바꿈 연속(`\\` + 개행)을 공백으로 합친다."""
    return re.sub(r"\\\s*\n\s*", " ", text)


def _major_minor(version: str) -> tuple[int, int]:
    parts = re.findall(r"\d+", version)
    return (int(parts[0]) if parts else 0, int(parts[1]) if len(parts) > 1 else 0)


# ─── C11-03: 감사 스크립트가 출하 의존성을 실제로 본다 ─────────────────────


@pytest.fixture
def audit_script() -> Path:
    return REPO_ROOT / "scripts" / "audit_python_dependencies.sh"


def _stub_audit(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / f"{name}.sh"
    path.write_text(f"#!/usr/bin/env bash\n{body}\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def _run_audit(
    audit_script: Path,
    *,
    args: list[str],
    audit_cmd: Path | None = None,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    if audit_cmd is not None:
        env["AGK_PIP_AUDIT_CMD"] = str(audit_cmd)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", str(audit_script), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
        timeout=600,
    )


def test_audit_rejects_undeclared_extra(audit_script: Path) -> None:
    """pyproject에 없는 extra를 감사 대상으로 받아들이지 않는다(음성 입력 거부)."""
    result = _run_audit(audit_script, args=["--extras", "definitely-not-an-extra"])

    assert result.returncode == 2, result.stdout + result.stderr
    assert "INFRA_ERROR" in result.stderr
    assert "definitely-not-an-extra" in result.stderr


def test_audit_discovers_shipped_extras_and_records_inputs(audit_script: Path, tmp_path: Path) -> None:
    """감사 대상은 Dockerfile이 설치하는 extras에서 파생되고, 감사 전에 기록된다."""
    dockerfile = _flatten(_read("Dockerfile"))
    shipped = sorted(
        {
            extra.strip()
            for group in re.findall(r'"\.\[([^\]]+)\]"', dockerfile)
            for extra in group.split(",")
            if extra.strip()
        }
    )
    assert shipped, "Dockerfile에서 출하 extras를 찾지 못했습니다"

    record = tmp_path / "python-audit-inputs.json"
    result = _run_audit(audit_script, args=["--print-targets"], extra_env={"AGK_AUDIT_RECORD": str(record)})

    assert result.returncode == 0, result.stdout + result.stderr
    payload = next(
        json.loads(line.split(":", 1)[1].strip())
        for line in result.stdout.splitlines()
        if line.startswith("AUDIT-INPUTS:")
    )
    assert payload["shipped_extras"] == shipped
    assert sorted(payload["targets"]["extras"]) == shipped
    # 감사 전에 입력 규모를 기록한다(무엇을 감사했는지 사후에 알 수 있어야 한다).
    assert payload["targets"]["base"]["packages"] > 0
    assert len(payload["targets"]["base"]["sha256_16"]) == 16
    assert payload["targets"]["union"]["packages"] >= payload["targets"]["base"]["packages"]
    assert "TARGETS_ONLY" in result.stdout

    written = json.loads(record.read_text(encoding="utf-8"))
    assert written["shipped_extras"] == shipped
    assert written["schema"] == "agk-python-audit-inputs/1"

    # 과거 이름(AUDIT_RECORD)으로 설정해도 기록이 남아야 한다 — 문서/코드 불일치 회귀.
    legacy = tmp_path / "legacy-inputs.json"
    legacy_run = _run_audit(audit_script, args=["--print-targets"], extra_env={"AUDIT_RECORD": str(legacy)})
    assert legacy_run.returncode == 0, legacy_run.stdout + legacy_run.stderr
    assert json.loads(legacy.read_text(encoding="utf-8"))["shipped_extras"] == shipped


def test_audit_separates_vulnerabilities_from_infrastructure_errors(audit_script: Path, tmp_path: Path) -> None:
    """취약점(1)과 감사 인프라 오류(2)를 모두 비성공으로 다루되 이유는 구분한다."""
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("requests==2.31.0\n", encoding="utf-8")

    passthrough = _stub_audit(tmp_path, "pass", "printf '%s' '{\"dependencies\": []}'")
    vulnerabilities = _stub_audit(
        tmp_path,
        "vuln",
        'printf \'%s\' \'{"dependencies": [{"name": "x", "version": "1",'
        ' "vulns": [{"id": "CVE-2026-0001", "fix_versions": ["2"]}]}]}\'\nexit 1',
    )
    broken = _stub_audit(tmp_path, "broken", "echo 'tool exploded' >&2\nexit 1")

    passed = _run_audit(audit_script, args=["--requirement-file", str(requirements)], audit_cmd=passthrough)
    assert passed.returncode == 0, passed.stdout + passed.stderr
    assert "AUDIT-STATUS: PASS" in passed.stdout

    found = _run_audit(audit_script, args=["--requirement-file", str(requirements)], audit_cmd=vulnerabilities)
    assert found.returncode == 1, found.stdout + found.stderr
    assert "VULNERABILITIES_FOUND" in found.stderr
    assert "CVE-2026-0001" in found.stdout

    infra = _run_audit(audit_script, args=["--requirement-file", str(requirements)], audit_cmd=broken)
    assert infra.returncode == 2, infra.stdout + infra.stderr
    assert "INFRA_ERROR" in infra.stderr


# 실제 pip-audit이 출하 extras([rag])를 감사하면서 보고한 chromadb 1.5.9 권고.
# (감사 대상이 base 뿐이던 시절에는 이 4건이 gate까지 도달하지 못했다.)
_CHROMADB_ADVISORIES = (
    "PYSEC-2026-311",
    "PYSEC-2026-3813",
    "PYSEC-2026-3814",
    "PYSEC-2026-3815",
)


def _pip_audit_payload(advisories: tuple[tuple[str, str, str], ...]) -> str:
    """(name, version, id) 목록을 pip-audit JSON으로 만든다."""
    by_package: dict[tuple[str, str], list[dict[str, object]]] = {}
    for name, version, vuln_id in advisories:
        by_package.setdefault((name, version), []).append({"id": vuln_id, "fix_versions": []})
    payload = {
        "dependencies": [
            {"name": name, "version": version, "vulns": vulns} for (name, version), vulns in by_package.items()
        ]
    }
    return json.dumps(payload, ensure_ascii=False)


def _requirements_file(tmp_path: Path) -> Path:
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("chromadb==1.5.9\n", encoding="utf-8")
    return requirements


def test_audit_applies_registry_and_reports_excepted_findings(audit_script: Path, tmp_path: Path) -> None:
    """등록된 예외는 gate를 통과시키되, 목록과 owner/만료일을 그대로 드러낸다."""
    advisories = tuple(("chromadb", "1.5.9", vuln_id) for vuln_id in _CHROMADB_ADVISORIES)
    stub = _stub_audit(tmp_path, "chromadb", f"printf '%s' {json.dumps(_pip_audit_payload(advisories))}\nexit 1")

    result = _run_audit(
        audit_script,
        args=["--requirement-file", str(_requirements_file(tmp_path))],
        audit_cmd=stub,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    verdict = next(
        json.loads(line.split(":", 1)[1].strip())
        for line in result.stdout.splitlines()
        if line.startswith("AUDIT-VERDICT:")
    )
    assert verdict["unresolved"] == []
    assert sorted({item["id"] for item in verdict["excepted"]}) == list(_CHROMADB_ADVISORIES)
    assert all(item["owner"] == "rel-03-maintainer" for item in verdict["excepted"])
    assert all(item["expires"] == "2026-12-08" for item in verdict["excepted"])
    for vuln_id in _CHROMADB_ADVISORIES:
        assert vuln_id in result.stdout


def test_audit_closes_fail_closed_without_registry(audit_script: Path, tmp_path: Path) -> None:
    """예외를 평가할 수 없으면(레지스트리 부재) 취약점이 있을 때 실패로 닫는다."""
    advisories = (("chromadb", "1.5.9", "PYSEC-2026-311"),)
    stub = _stub_audit(tmp_path, "chromadb", f"printf '%s' {json.dumps(_pip_audit_payload(advisories))}\nexit 1")

    result = _run_audit(
        audit_script,
        args=["--requirement-file", str(_requirements_file(tmp_path)), "--exceptions", str(tmp_path / "nope.json")],
        audit_cmd=stub,
    )

    assert result.returncode == 2, result.stdout + result.stderr
    assert "INFRA_ERROR" in result.stderr


def test_audit_fails_on_expired_exception(audit_script: Path, tmp_path: Path) -> None:
    """만료된 예외는 gate 실패다(deny-by-default) — 예외가 자동 연장되지 않는다."""
    registry = tmp_path / "expired.json"
    registry.write_text(
        json.dumps(
            {
                "exceptions": [
                    {
                        "id": "PYSEC-2026-311",
                        "package": "chromadb",
                        "ecosystem": "pypi",
                        "installed_version": "1.5.9",
                        "owner": "rel-03-maintainer",
                        "justification": "만료 재현용 픽스처",
                        "expires": "2020-01-01",
                        "compensating_controls": ["픽스처"],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    advisories = (("chromadb", "1.5.9", "PYSEC-2026-311"),)
    stub = _stub_audit(tmp_path, "chromadb", f"printf '%s' {json.dumps(_pip_audit_payload(advisories))}\nexit 1")

    result = _run_audit(
        audit_script,
        args=["--requirement-file", str(_requirements_file(tmp_path)), "--exceptions", str(registry)],
        audit_cmd=stub,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    assert "EXPIRED_EXCEPTION" in result.stderr


def test_audit_verdict_matches_the_engine_verdict(audit_script: Path, tmp_path: Path) -> None:
    """셸 스크립트의 판정이 엔진(REL-03)의 판정과 일치한다 — 게이트 간 진실 분기 방지."""
    from antigravity_k.engine.audit_exceptions import audit_verdict_with_exceptions, load_exceptions

    exceptions = load_exceptions(REPO_ROOT / "config" / "audit-exceptions.json")
    findings = tuple(
        {
            "id": vuln_id,
            "package": "chromadb",
            "ecosystem": "pypi",
            "installed_version": "1.5.9",
            "severity": "high",
        }
        for vuln_id in _CHROMADB_ADVISORIES
    )
    engine = audit_verdict_with_exceptions(findings=findings, exceptions=exceptions)

    advisories = tuple(("chromadb", "1.5.9", vuln_id) for vuln_id in _CHROMADB_ADVISORIES)
    stub = _stub_audit(tmp_path, "chromadb", f"printf '%s' {json.dumps(_pip_audit_payload(advisories))}\nexit 1")
    result = _run_audit(
        audit_script,
        args=["--requirement-file", str(_requirements_file(tmp_path))],
        audit_cmd=stub,
    )
    verdict = next(
        json.loads(line.split(":", 1)[1].strip())
        for line in result.stdout.splitlines()
        if line.startswith("AUDIT-VERDICT:")
    )

    assert engine["ok"] is True
    assert engine["unresolved"] == ()
    assert len(engine["excepted"]) == len(verdict["excepted"])
    assert result.returncode == 0


def test_registry_entries_are_valid_and_not_expired() -> None:
    """등록된 예외가 4요소 계약을 지키고 만료되지 않았는지 저장소에서 직접 확인한다."""
    from datetime import UTC, datetime

    from antigravity_k.engine.audit_exceptions import expired_exceptions, load_exceptions

    registry = REPO_ROOT / "config" / "audit-exceptions.json"
    exceptions = load_exceptions(registry)
    assert exceptions, "예외 레지스트리가 비어 있습니다"
    assert expired_exceptions(exceptions, today=datetime.now(UTC).date()) == ()
    for exception in exceptions:
        assert exception.owner
        assert exception.compensating_controls


# ─── C11-01: editable/PYTHONPATH 우연 제거 ────────────────────────────────


def test_workflows_do_not_depend_on_editable_install_or_pythonpath() -> None:
    """editable 설치나 PYTHONPATH=src로 src-layout 모듈을 돌리지 않는다."""
    for workflow in WORKFLOWS:
        flattened = _flatten(_without_comments(_read(workflow)))
        assert not re.search(r"pip install\s+(-e|--editable)\b", flattened), f"{workflow}: editable 설치"
        assert "PYTHONPATH=src" not in flattened, f"{workflow}: PYTHONPATH=src 사용"


def test_workflows_install_project_before_running_internal_modules() -> None:
    """`python -m antigravity_k...`는 프로젝트 설치 이후에만 나온다(R01)."""
    for workflow in WORKFLOWS:
        flattened = _flatten(_without_comments(_read(workflow)))
        first_module = flattened.find("python -m antigravity_k.")
        if first_module < 0:
            continue
        prefix = flattened[:first_module]
        assert re.search(r"uv sync --locked", prefix), f"{workflow}: 모듈 실행 전 설치 없음"


def test_release_workflow_installs_before_running_sbom_module() -> None:
    """R01의 직접 회귀: 릴리스 SBOM 생성 모듈 실행 앞에 잠금 설치가 있다."""
    flattened = _flatten(_without_comments(_read(".github/workflows/release.yml")))
    sync_index = flattened.find("uv sync --locked")
    sbom_index = flattened.find("python -m antigravity_k.engine.release_sbom generate")

    assert sync_index >= 0, "release.yml에 잠금 설치가 없다"
    assert sbom_index >= 0, "release.yml에 SBOM 생성 모듈 실행이 없다"
    assert sync_index < sbom_index, "SBOM 모듈이 잠금 설치보다 먼저 실행된다"


# ─── C11-02 / C11-05: Node/pnpm 조합과 번들 출처 ──────────────────────────


def test_node_pins_satisfy_declared_engines() -> None:
    """CI·release·Docker의 Node 고정값이 package.json engines를 만족한다."""
    package = json.loads(_read("dashboard/package.json"))
    engines = package.get("engines", {})
    assert engines.get("node"), "dashboard/package.json에 engines.node 선언이 없다"

    requirement = re.match(r">=\s*([0-9.]+)", engines["node"])
    assert requirement is not None, f"지원하지 않는 engines.node 형식: {engines['node']}"
    required = _major_minor(requirement.group(1))

    pins: list[tuple[str, str]] = []
    for relative in (*WORKFLOWS, "Dockerfile"):
        text = _read(relative)
        for pattern in NODE_PIN_PATTERNS:
            pins.extend((relative, match) for match in pattern.findall(text))
    assert pins, "Node 버전 고정을 찾지 못했습니다"

    unsatisfied = [pin for pin in pins if _major_minor(pin[1]) < required]
    assert not unsatisfied, f"engines.node({engines['node']}) 미만 고정: {unsatisfied}"


def test_pnpm_pins_match_package_manager_declaration() -> None:
    """packageManager(pnpm@x.y.z)와 CI/Docker의 pnpm 설치 버전이 같다."""
    package = json.loads(_read("dashboard/package.json"))
    declared = package["packageManager"].removeprefix("pnpm@")

    pinned: list[tuple[str, str]] = []
    for relative in (*WORKFLOWS, "Dockerfile"):
        text = _read(relative)
        pinned.extend((relative, match) for match in PNPM_ACTION_PIN.findall(text))
        pinned.extend((relative, match) for match in re.findall(r"npm install -g pnpm@([0-9][0-9.]*)", text))
    assert pinned, "pnpm 버전 고정을 찾지 못했습니다"
    assert {version for _, version in pinned} == {declared}, f"packageManager={declared}, pins={pinned}"


def test_dashboard_provenance_uses_vite_out_dir() -> None:
    """provenance는 실제 번들 산출 디렉터리(vite outDir)를 기록한다."""
    vite = _read("dashboard/vite.config.ts")
    match = re.search(r"outDir:\s*path\.resolve\(__dirname,\s*'([^']+)'\)", vite)
    assert match is not None, "vite outDir을 찾지 못했습니다"
    expected = (REPO_ROOT / "dashboard" / match.group(1)).resolve().relative_to(REPO_ROOT).as_posix()

    recorded = re.findall(
        r"artifact_provenance\.py\s+create\s+(\S+)",
        _flatten(_without_comments(_read(".github/workflows/ci.yml"))),
    )
    assert expected in recorded, f"provenance 기록 {recorded}에 {expected}가 없다"


def test_workflows_run_bundle_and_artifact_verifiers() -> None:
    """새 번들 대조기와 배포 아티팩트 검증기가 CI·릴리스에 배선됐다."""
    for workflow in WORKFLOWS:
        text = _read(workflow)
        assert "scripts/verify_dashboard_bundle.sh" in text, f"{workflow}: 번들 대조기 미배선"
        assert "scripts/verify_release_artifacts.sh" in text, f"{workflow}: 배포 검증기 미배선"


@pytest.mark.parametrize("script", ["scripts/verify_dashboard_bundle.sh", "scripts/verify_release_artifacts.sh"])
def test_verifier_scripts_document_their_contract(script: str) -> None:
    """검증 스크립트는 사용법과 종료코드를 자기 안에 문서화한다."""
    text = _read(script)
    assert "--help" in text
    assert "종료코드" in text


def test_bundle_verifier_detects_stale_bundle(tmp_path: Path) -> None:
    """빌드한 번들과 wheel 내부 번들이 다르면 성공처럼 포장하지 않는다."""
    if shutil.which("uv") is None:
        pytest.skip("uv 가 없어 wheel 비교를 실행할 수 없습니다")

    script = REPO_ROOT / "scripts" / "verify_dashboard_bundle.sh"
    ok = subprocess.run(
        ["bash", str(script), "--skip-build"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "BUNDLE-STATUS: PASS" in ok.stdout

    mutated = tmp_path / "dashboard_dist"
    shutil.copytree(REPO_ROOT / "src" / "antigravity_k" / "dashboard_dist", mutated)
    (mutated / "assets" / "CR11-STALE.js").write_text("// stale bundle that must not be packaged\n", encoding="utf-8")
    bad = subprocess.run(
        ["bash", str(script), "--skip-build", "--dist-root", str(mutated)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )
    assert bad.returncode == 1, bad.stdout + bad.stderr
    assert "BUNDLE-STATUS: MISMATCH" in bad.stderr
    assert "assets/CR11-STALE.js" in bad.stdout


# ─── C11-05: dry-run만 검증한다 ──────────────────────────────────────────


def test_release_workflow_is_dry_run_first() -> None:
    """릴리스 워크플로는 dry-run이 기본이고, publish는 별도 조건에서만 열린다."""
    text = _read(".github/workflows/release.yml")

    assert re.search(r"dry_run:\s*(?:\n\s+.*)*?\n\s+default:\s*\"?true\"?", text), "dry_run 입력 기본값이 true가 아니다"
    assert "dry-run-report" in text, "dry-run 결과를 보고하는 job이 없다"
    assert text.count("inputs.dry_run != 'true'") >= 2, "publish 단계가 dry_run을 소비하지 않는다"

    for job in ("publish-pypi", "github-release"):
        assert f"\n  {job}:" in text, f"{job} job 이 없다"
        section = text.split(f"\n  {job}:", 1)[1].split("\n    steps:", 1)[0]
        assert "inputs.dry_run != 'true'" in section, f"{job}이 dry_run을 무시한다"
        assert "github.event_name == 'push'" in section, f"{job}이 수동 실행에서도 열린다"
