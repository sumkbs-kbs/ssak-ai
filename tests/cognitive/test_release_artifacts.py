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
        roundtrip_exit=0,
        compared=664,
        missing=(),
        extra=(),
        rehearsal_exit=0,
        rehearsal_missing=(release.TAMPER_TARGET,),
        rehearsal_compared=664,
        tamper_exit=1,
        tamper_removed=release.TAMPER_TARGET,
        inputs_line=True,
        crashed=False,
        seconds=55.0,
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
        ("roundtrip_exit", None, "sdist 왕복을 돌리지 않았다"),
        ("roundtrip_exit", 1, "sdist 로 다시 빌드되지 않는다"),
        ("missing", ("antigravity_k/dashboard_dist/index.html",), "파일 1개가 빠졌다"),
        ("rehearsal_exit", None, "왕복의 red 재현(sdist 에서 파일 빼기)을 돌리지 않았다"),
        ("rehearsal_exit", 1, "왕복 red 재현에서 재빌드가 실패했다"),
        ("rehearsal_missing", (), "빼도 왕복이 ‘차이 없음’ 이라고 말했다"),
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
    """하한은 값과 근거를 함께 내고, 얇은 실행(산출물 하나·비교 0)에서는 실제로 문다."""

    floors = release.coverage_floors(_healthy(release))

    assert [floor.label for floor in floors] == ["배포 산출물", "저장소 밖 PASS", "비교한 파일"]
    assert all(floor.why.strip() for floor in floors)
    assert release.floor_problems(floors) == []

    thin = replace(_healthy(release), artifacts=(release.Artifact("wheel", "w.whl", 1, "a"),), passed=())
    assert release.floor_problems(release.coverage_floors(thin)) != []
    assert release.floor_problems(release.coverage_floors(replace(_healthy(release), compared=0))) != []


# ------------------------------------------------------------------ sdist 왕복


def test_wheel_compare_reports_missing_and_extra(tmp_path: Path, release: Any) -> None:  # noqa: ANN401
    """두 wheel 을 파일 목록으로 견준다 — **빠진 것**이 실패이고 더 있는 것은 보고 대상이다."""

    direct = tmp_path / "direct.whl"
    rebuilt = tmp_path / "rebuilt.whl"
    with zipfile.ZipFile(direct, "w") as archive:
        archive.writestr("antigravity_k/a.py", "a")
        archive.writestr("antigravity_k/dashboard_dist/index.html", "bundle")
    with zipfile.ZipFile(rebuilt, "w") as archive:
        archive.writestr("antigravity_k/a.py", "a")
        archive.writestr("antigravity_k/extra.py", "new")

    missing, extra, compared = release.compare_wheels(direct, rebuilt)

    assert missing == ("antigravity_k/dashboard_dist/index.html",)
    assert extra == ("antigravity_k/extra.py",)
    assert compared == 3


def test_wheel_names_are_sorted_and_unique(tmp_path: Path, release: Any) -> None:  # noqa: ANN401
    """목록 읽기는 정렬·중복 제거를 해야 두 목록 비교가 흔들리지 않는다."""

    wheel = tmp_path / "w.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("b.py", "b")
        archive.writestr("a.py", "a")

    assert release.wheel_names(wheel) == ("a.py", "b.py")


def test_unpack_sdist_finds_the_project_root(tmp_path: Path, release: Any) -> None:  # noqa: ANN401
    """sdist 를 풀 때 **그 안의** 프로젝트 뿌리를 찾는다(트리에서 빌드하면 왕복이 아니다)."""

    import tarfile

    sdist = tmp_path / "antigravity_k-0.1.0.tar.gz"
    source = tmp_path / "build" / "antigravity_k-0.1.0"
    source.mkdir(parents=True)
    (source / "pyproject.toml").write_text("[build-system]\nrequires = []\n", encoding="utf-8")
    (source / "README.md").write_text("x", encoding="utf-8")
    with tarfile.open(sdist, "w:gz") as archive:
        archive.add(source, arcname="antigravity_k-0.1.0")

    root = release.unpack_sdist(sdist, tmp_path / "work")

    assert root.name == "antigravity_k-0.1.0"
    assert (root / "pyproject.toml").is_file()
    assert not (root / "tests").exists()  # 트리가 아니라 sdist 안이다


def test_drop_member_removes_exactly_one_file(tmp_path: Path, release: Any) -> None:  # noqa: ANN401
    """sdist 사본에서 한 파일만 빠지고 나머지 메우리가 그대로 남는다(경로 모양도 유지)."""

    import tarfile

    good = tmp_path / "good"
    good.mkdir()
    (good / "antigravity_k").mkdir()
    (good / "antigravity_k" / "kept.py").write_text("kept", encoding="utf-8")
    (good / "antigravity_k" / "dropped.py").write_text("dropped", encoding="utf-8")
    source = tmp_path / "antigravity_k-0.1.0.tar.gz"
    with tarfile.open(source, "w:gz") as archive:
        archive.add(good, arcname="antigravity_k-0.1.0")

    target = release.drop_member(source, tmp_path / "dropped.tar.gz", remove="antigravity_k/dropped.py")

    with tarfile.open(target) as archive:
        members = [(member.name, member.size) for member in archive.getmembers()]
    assert all(not name.endswith("dropped.py") for name, _ in members)
    assert ("antigravity_k-0.1.0/antigravity_k/kept.py", 4) in members  # 내용까지 그대로 옮겼다


def test_drop_member_refuses_a_file_that_is_not_there(tmp_path: Path, release: Any) -> None:  # noqa: ANN401
    """뺄 파일이 그 압축본에 없으면 조용히 원본을 돌려주지 않고 거부한다(재현인 줄 알고 통과하는 순간을 막는다)."""

    import tarfile

    source = tmp_path / "small.tar.gz"
    (tmp_path / "only.py").write_text("x", encoding="utf-8")
    with tarfile.open(source, "w:gz") as archive:
        archive.add(tmp_path / "only.py", arcname="only.py")

    with pytest.raises(ValueError, match="없다"):
        release.drop_member(source, tmp_path / "out.tar.gz", remove="antigravity_k/engine/release_sbom.py")


def test_rehearse_dropped_sdist_is_unrun_without_inputs(tmp_path: Path, release: Any) -> None:  # noqa: ANN401
    """심을 재료가 없으면 None(못 돌렸다)으로 남는다 — ‘조용한 통과’ 도 ‘사고’ 도 아니다."""

    assert release.rehearse_dropped_sdist(tmp_path / "none.tar.gz", tmp_path / "none.whl", tmp_path) == (None, (), 0)


def test_unpack_sdist_refuses_a_tarball_without_a_project(tmp_path: Path, release: Any) -> None:  # noqa: ANN401
    """빌드할 트리가 없는 압축본은 조용히 넘어가지 않고 거부한다."""

    import tarfile

    sdist = tmp_path / "empty.tar.gz"
    empty = tmp_path / "empty"
    empty.mkdir()
    (empty / "note.txt").write_text("x", encoding="utf-8")
    with tarfile.open(sdist, "w:gz") as archive:
        archive.add(empty / "note.txt", arcname="note.txt")

    with pytest.raises(ValueError, match="pyproject.toml"):
        release.unpack_sdist(sdist, tmp_path / "work")


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
    assert payload["counts"]["compared"] == 664
    assert payload["counts"]["missing"] == 0
    assert payload["counts"]["tamper_detected"] == 1
    assert payload["coverage"] == {"artifacts": 2, "verified": 2, "compared": 664}
    assert payload["roundtrip"]["missing"] == []
    assert payload["roundtrip"]["compared"] == 664
    assert payload["counts"]["roundtrip_bites"] == 1
    assert payload["roundtrip"]["rehearsal_missing"] == [release.TAMPER_TARGET]
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
    assert record.roundtrip_exit == 0
    assert record.missing == ()  # sdist 에서 다시 빌드한 wheel 이 같은 파일을 담는다
    assert record.compared >= 100
    assert record.rehearsal_exit == 0
    assert record.rehearsal_missing == (release.TAMPER_TARGET,)  # sdist 에서 뺀 파일을 왕복이 지목했다
    assert record.detected is True


def test_the_report_json_is_readable_by_the_gate(release: Any) -> None:  # noqa: ANN401
    """리포트 형태가 게이트의 수치 추출 규약(지목한 키의 dict)과 맞는지 — 키 이름이 바뀌면 추이가 조용히 빈다."""

    payload = release.as_mapping(_healthy(release), release.self_probe())

    assert set(payload["counts"]) >= {"artifacts", "verified", "compared", "missing", "tamper_detected"}
    assert set(payload["coverage"]) == {"artifacts", "verified", "compared"}
    assert set(payload["roundtrip"]) == {"exit", "compared", "missing", "extra", "rehearsal_exit", "rehearsal_missing"}
    assert isinstance(payload["floors"], list) and payload["floors"]
    assert io.StringIO(json.dumps(payload)).read()  # 직렬화 가능해야 게이트가 읽는다


def test_the_baseline_watches_the_compared_floor(release: Any) -> None:  # noqa: ANN401
    """왕복 비교 수가 게이트의 수치 추출 키에 실린다 — 빠지면 감소가 추이에 안 보인다."""

    payload = release.as_mapping(_healthy(release), release.self_probe())

    assert payload["counts"]["compared"] == _healthy(release).compared
    assert "비교한 파일" in {floor["label"] for floor in payload["floors"]}  # type: ignore[index, union-attr]
