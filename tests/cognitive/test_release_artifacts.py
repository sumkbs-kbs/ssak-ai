"""배포 산출물 계약(`scripts/release_artifacts.py`)의 계약 — **`build` 가 NOT_RUN 으로 남지 않게**.

T14 는 `test / lint / type / build` 를 요구하는데 `build` 만 “릴리스 CI 소관” 이라는 이유로 이 체크아웃에서 실행되지
않았다. 이 계약 시험이 고정하는 것은 그 도구의 판정 규칙이다:

  * 빌드 실패 · 산출물이 하나뿐 · 저장소 밖 검증 실패 · PASS 문장 부재 · `ARTIFACT-INPUTS` 부재는 통과가 아니다.
  * **‘빠진 배포판’ 을 통과시키면 실패다** — 그 red 재현이 이 층의 핵심이다(검증기가 무는지 확인하지 않은 실행은
    통과가 아니다).
  * tamper 는 **유효하되 불완전한** wheel 을 만든다: 파일을 빼고 `RECORD` 를 다시 쓴다(설치 거부와 “설치되지만 못 씀”
    은 다른 결함이다).
  * 하한(산출물 2 · 저장소 밖 PASS 2)은 값과 근거를 함께 내고, 얇은 실행에서는 실제로 문다.

실물 빌드·설치·검증은 `slow` 표시로 분리했다(로컬 회차에서만 돈다 — CI 는 `not slow` 로 돌린다).
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import zipfile
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("release_artifacts_under_test", SCRIPTS / "release_artifacts.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def release() -> Any:  # noqa: ANN401 - 스크립트 module
    return load_script()


def _healthy(release: Any) -> Any:  # noqa: ANN401
    """빌드·소비·red 재현을 모두 본 관찰 — 결함별 변형의 기준이 된다."""

    return release.Observation(
        build_exit=0,
        artifacts=(
            release.Artifact("wheel", "antigravity_k-0.1.0-py3-none-any.whl", 100, "a"),
            release.Artifact("sdist", "antigravity_k-0.1.0.tar.gz", 120, "b"),
        ),
        verify_exit=0,
        passed=("wheel", "sdist"),
        tamper_exit=1,
        tamper_removed=release.TAMPER_TARGET,
        inputs_line=True,
        crashed=False,
        seconds=44.0,
    )


# ------------------------------------------------------------------ 판정 규칙


def test_a_healthy_observation_passes(release: Any) -> None:  # noqa: ANN401
    """빌드 0 · 산출물 둘 · PASS 둘 · `ARTIFACT-INPUTS` 있음 · 빠진 배포판 차단 — 이것이 통과다."""

    record = _healthy(release)

    assert record.ok is True
    assert record.detected is True


@pytest.mark.parametrize(
    ("field", "value", "fragment"),
    [
        ("build_exit", 1, "빌드가 exit 1"),
        ("artifacts", (), "산출물이 계약과 다르다"),
        ("verify_exit", 1, "저장소 밖 설치·소비 검증이 exit 1"),
        ("passed", ("wheel",), "PASS 문장이 1개뿐이다"),
        ("inputs_line", False, "ARTIFACT-INPUTS"),
        ("tamper_exit", None, "red 재현(빠진 배포판)을 돌리지 않았다"),
        ("tamper_exit", 0, "빠진 배포판을 통과시켰다"),
        ("note", "하위 process 가 죽었다", "사고가 났다"),
    ],
)
def test_each_defect_is_a_failure(release: Any, field: str, value: object, fragment: str) -> None:  # noqa: ANN401
    """결함 하나씩을 재현해 각각이 실패 문장으로 남는지 본다 — 통과로 새는 자리가 없어야 한다."""

    record = replace(_healthy(release), **{field: value})

    assert record.ok is False, field
    assert any(fragment in problem for problem in record.problems), record.problems


def test_red_is_the_whole_point(release: Any) -> None:  # noqa: ANN401
    """빠진 배포판을 막지 못한 실행은 실패다 — 그 사실이 이 층의 존재 이유다."""

    record = replace(_healthy(release), tamper_exit=0)

    assert record.detected is False
    assert any("아무것도 막지 못한다" in problem for problem in record.problems)


# ------------------------------------------------------------------ 하한


def test_floors_carry_their_basis_and_bite_when_thin(release: Any) -> None:  # noqa: ANN401
    """하한은 값과 근거를 함께 내고, 산출물이 하나뿐인 얇은 실행에서는 실제로 문다."""

    floors = release.coverage_floors(_healthy(release))

    assert [floor.label for floor in floors] == ["배포 산출물", "저장소 밖 PASS"]
    assert all(floor.why.strip() for floor in floors)
    assert release.floor_problems(floors) == []

    thin = replace(_healthy(release), artifacts=(release.Artifact("wheel", "w.whl", 1, "a"),), passed=())
    assert release.floor_problems(release.coverage_floors(thin)) != []


# ------------------------------------------------------------------ tamper = ‘빠진 배포판’


def _synthetic_wheel(path: Path) -> Path:
    """RECORD 를 갖춘 최소 wheel — 실물 빌드 없이 tamper 규칙을 시험한다."""

    files = {
        "antigravity_k/__init__.py": "__version__ = '0.1.0'\n",
        "antigravity_k/engine/release_sbom.py": "def main() -> int:\n    return 0\n",
        "antigravity_k-0.1.0.dist-info/METADATA": "Metadata-Version: 2.3\nName: antigravity-k\n",
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, text in files.items():
            archive.writestr(name, text)
        archive.writestr("antigravity_k-0.1.0.dist-info/RECORD", "placeholder,,\n")
    return path


def test_tamper_drops_the_module_and_rewrites_record(tmp_path: Path, release: Any) -> None:  # noqa: ANN401
    """tamper 는 파일을 빼고 `RECORD` 를 남은 파일 기준으로 다시 쓴다(유효하되 불완전한 배포판)."""

    original = _synthetic_wheel(tmp_path / "antigravity_k-0.1.0-py3-none-any.whl")
    target = tmp_path / "tampered" / original.name
    target.parent.mkdir(parents=True, exist_ok=True)

    release.tamper_wheel(original, target, remove=release.TAMPER_TARGET)

    with zipfile.ZipFile(target) as archive:
        names = archive.namelist()
        record = archive.read("antigravity_k-0.1.0.dist-info/RECORD").decode("utf-8")

    assert release.TAMPER_TARGET not in names
    assert "antigravity_k/__init__.py" in names
    listed = {line.split(",")[0] for line in record.strip().splitlines()}
    assert listed == set(names)  # RECORD 가 남은 파일과 정확히 일치한다
    assert "antigravity_k-0.1.0.dist-info/RECORD,," in record  # 자기 자신은 해시 없이


def test_tamper_refuses_a_wheel_without_the_target(tmp_path: Path, release: Any) -> None:  # noqa: ANN401
    """재현 대상이 없는 wheel 은 조용히 통과시키지 않고 거부한다(무엇을 재현했는지 모르는 채로 넘어가지 않는다)."""

    original = _synthetic_wheel(tmp_path / "antigravity_k-0.1.0-py3-none-any.whl")

    with pytest.raises(ValueError, match="없다"):
        release.tamper_wheel(original, tmp_path / "out.whl", remove="antigravity_k/engine/not_there.py")


def test_passed_kinds_reads_structure_not_prose(release: Any) -> None:  # noqa: ANN401
    """검증기의 PASS 판정은 **구조화된 줄**에서 읽는다(산문에서 ‘PASS’ 를 줍지 않는다)."""

    output = "\n".join(
        [
            'ARTIFACT-INPUTS: {"wheel":"a.whl"}',
            'ARTIFACT-RESULT: {"kind":"wheel","status":"PASS","artifact":"a.whl"}',
            'ARTIFACT-RESULT: {"kind":"sdist","status":"FAIL","step":"install"}',
            "ARTIFACT-STATUS: FAIL — sdist 가 실패했다(PASS 라는 단어가 산문에 있어도 세지 않는다)",
        ]
    )

    assert release.passed_kinds(output) == ("wheel",)


# ------------------------------------------------------------------ CLI 계약


def test_emit_json_reports_the_contract(release: Any, monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:  # noqa: ANN401
    """`--emit-json` 은 게이트가 읽는 형태(판정·수치·하한)를 낸다."""

    monkeypatch.setattr(release, "measure", lambda **kwargs: _healthy(release))
    assert release.main(["--emit-json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["verdict"] == "PASS"
    assert payload["counts"]["artifacts"] == 2
    assert payload["counts"]["verified"] == 2
    assert payload["counts"]["tamper_detected"] == 1
    assert payload["coverage"] == {"artifacts": 2, "verified": 2}
    assert payload["tamper"]["detected"] is True
    assert all(record["why"].strip() for record in payload["floors"])
    assert payload["probe"]["cases"] >= 15


def test_gate_and_json_fail_when_red_is_not_reproduced(
    release: Any, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:  # noqa: ANN401, E501
    """빠진 배포판을 통과시킨 실행은 `--gate` 도 `--emit-json` 도 exit 1 이다(진단은 JSON 에 남는다)."""

    monkeypatch.setattr(release, "measure", lambda **kwargs: replace(_healthy(release), tamper_exit=0))
    assert release.main(["--gate"]) == 1
    assert "[FAIL]" in capsys.readouterr().err

    assert release.main(["--emit-json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["counts"]["tamper_detected"] == 0
    assert any("아무것도 막지 못한다" in problem for problem in payload["problems"])


def test_self_probe_rejudges_the_rules(release: Any) -> None:  # noqa: ANN401
    """자기시험이 매 실행 판정 규칙을 다시 묻는다(빌드하지 않는다)."""

    probe = release.self_probe()

    assert probe.ok is True
    assert probe.cases >= 15
    assert release.main(["--self-test"]) == 0


# ------------------------------------------------------------------ 실물 계약(로컬 회차)


@pytest.mark.slow
def test_the_real_artifacts_are_built_consumed_and_tampered(release: Any) -> None:  # noqa: ANN401
    """실물: wheel/sdist 를 만들고 저장소 밖에서 써 보고, 빠진 배포판이 막히는지까지 본다(수십 초)."""

    record = release.measure()

    assert record.ok, record.problems
    assert {item.kind for item in record.artifacts} == {"wheel", "sdist"}
    assert all(item.bytes > 0 and len(item.sha256) == 64 for item in record.artifacts)
    assert record.passed == ("wheel", "sdist")
    assert record.detected is True


def test_the_report_json_is_readable_by_the_gate(release: Any) -> None:  # noqa: ANN401
    """리포트 형태가 게이트의 수치 추출 규약(지목한 키의 dict)과 맞는지 — 키 이름이 바뀌면 추이가 조용히 빈다."""

    payload = release.as_mapping(_healthy(release), release.self_probe())

    assert set(payload["counts"]) >= {"artifacts", "verified", "tamper_detected"}
    assert set(payload["coverage"]) == {"artifacts", "verified"}
    assert isinstance(payload["floors"], list) and payload["floors"]
    assert io.StringIO(json.dumps(payload)).read()  # 직렬화 가능해야 게이트가 읽는다
