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
import subprocess
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


def _healthy_repro(release: Any) -> Any:  # noqa: ANN401
    """재현 계약을 통과하는 관찰 — wheel 동일 · sdist 는 생성 항목만 다름 · 민감도 셋 · CI pin 일치."""

    generated = "antigravity_k-0.1.0/src/antigravity_k.egg-info/PKG-INFO"
    return release.Reproducibility(
        identities=(
            release.Identity(
                kind="wheel",
                first="a" * 64,
                second="a" * 64,
                members=664,
                pinned_members=664,
                appeared=(),
                differs=(),
                allowed_differs=(),
                real_differs=(),
            ),
            release.Identity(
                kind="sdist",
                first="b" * 64,
                second="c" * 64,
                members=1205,
                pinned_members=0,
                appeared=(),
                differs=(generated,),
                allowed_differs=(generated,),
                real_differs=(),
            ),
        ),
        second_build_exit=0,
        sensitivity=release.Sensitivity(
            control_equal=True,
            pin_moves_bytes=True,
            sdist_differs=("repro-mini-0.1.0/PKG-INFO",),
            sdist_backend_only=True,
            exits=(0, 0, 0),
        ),
        ci_pinned=True,
        ci_pin_value=str(release.REPRO_PIN),
        seconds=9.3,
    )


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
        differing=(),
        extra=(),
        rehearsal_exit=0,
        rehearsal_missing=(release.TAMPER_TARGET,),
        rehearsal_differing=(release.REWRITE_TARGET,),
        rehearsal_compared=664,
        content=release.ContentCheck(
            compared=658,
            differ=(),
            absent=("antigravity_k-0.1.0.dist-info/METADATA",),
            rehearsal_control=(),
            rehearsal_defect=(release.TRANSFORM_TARGET,),
        ),
        tree=release.TreeCoverage(
            expected=tuple(f"antigravity_k/f{i}.py" for i in range(656)),
            missing=(),
            generated=("antigravity_k/vendor/ssak_search/bin/ssak-mcp",),
            local_only=("antigravity_k/data/memory.db",),
        ),
        tree_rehearsal_control=(),
        tree_rehearsal_defect=(release.MINI_DROPPED,),
        reproducibility=_healthy_repro(release),
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
        (
            "differing",
            ("antigravity_k/engine/release_sbom.py",),
            "내용이 다르다",
        ),
        ("rehearsal_differing", (), "이름은 같은데 바이트가 다르다"),
        (
            "content",
            lambda release: release.ContentCheck(658, ("antigravity_k/a.py",), (), (), (release.TRANSFORM_TARGET,)),
            "내용**이 빌드가 본 트리와 다르다",
        ),
        (
            "content",
            lambda release: release.ContentCheck(658, (), (), (), ()),
            "내용을 바꿔 싣는 실물 프로젝트에서 이 눈이 아무것도 지목하지 못했다",
        ),
        (
            "content",
            lambda release: release.ContentCheck(658, (), (), (), ("mini/other.py",)),
            "심은 것과 다른 것을 보면",
        ),
        (
            "content",
            lambda release: release.ContentCheck(658, (), (), ("mini/kept.py",), (release.TRANSFORM_TARGET,)),
            "대조군(변환 없는 같은 프로젝트)에서",
        ),
        (
            "content",
            lambda release: release.ContentCheck(658, (), (), (), (release.TRANSFORM_TARGET,), "uv 빌드가 실패했다"),
            "내용 재현 재료를 만들지 못했다",
        ),
        ("rehearsal_note", "release_sbom.py 가 그 압축본에 없다", "왕복 재현 재료를 만들지 못했다"),
        ("rehearsal_exit", None, "왕복의 red 재현(sdist 에서 파일 빼기)을 돌리지 않았다"),
        ("rehearsal_exit", 1, "왕복 red 재현에서 재빌드가 실패했다"),
        ("rehearsal_missing", (), "빼도 왕복이 ‘차이 없음’ 이라고 말했다"),
        (
            "tree",
            lambda release: release.TreeCoverage(
                expected=("antigravity_k/a.py",), missing=("antigravity_k/a.py",), generated=(), local_only=()
            ),
            "배포판에 없는 **추적 파일",
        ),
        ("tree_rehearsal_defect", (), "실물 재현에서 이 눈이 아무것도 지목하지 못했다"),
        ("tree_rehearsal_defect", ("minipkg/something_else.py",), "심은 것과 다른 것을 보면"),
        ("tree_rehearsal_control", ("minipkg/kept.py",), "대조군(정상 프로젝트)에서 빼짐을 지목했다"),
        ("tamper_exit", None, "red 재현(빠진 배포판)을 돌리지 않았다"),
        ("tamper_exit", 0, "빠진 배포판을 통과시켰다"),
        ("note", "하위 process 가 죽었다", "사고가 났다"),
        (
            "reproducibility",
            lambda release: replace(_healthy_repro(release), second_build_exit=None),
            "두 번째 빌드를 돌리지 않았다",
        ),
        (
            "reproducibility",
            lambda release: replace(_healthy_repro(release), second_build_exit=1),
            "두 번째 빌드가 exit 1",
        ),
        (
            "reproducibility",
            lambda release: _repro(  # wheel 이 같은 pin 으로도 다르다
                release,
                identities=(
                    release.Identity(
                        "wheel", "a" * 64, "d" * 64, 664, 664, (), ("antigravity_k/x.py",), (), ("antigravity_k/x.py",)
                    ),
                    _healthy_repro(release).identities[1],
                ),
            ),
            "wheel 이 같은 pin 으로도 다른 바이트다",
        ),
        (
            "reproducibility",
            lambda release: _repro(release, identities=(_healthy_repro(release).identities[0],)),
            "재현 비교가 산출물 ['wheel'] 에서만",
        ),
        (
            "reproducibility",
            lambda release: _repro(release, identities=()),
            "sdist 재현 관찰이 없다",
        ),
        (
            "reproducibility",
            lambda release: _repro(
                release,
                identities=(
                    _healthy_repro(release).identities[0],
                    replace(_healthy_repro(release).identities[1], second="b" * 64),
                ),
            ),
            "이제 sdist 도 재현된다",
        ),
        (
            "reproducibility",
            lambda release: _repro(
                release,
                identities=(
                    _healthy_repro(release).identities[0],
                    replace(_healthy_repro(release).identities[1], pinned_members=3),
                ),
            ),
            "근거 문장이 낡았다",
        ),
        (
            "reproducibility",
            lambda release: _repro(
                release,
                identities=(
                    _healthy_repro(release).identities[0],
                    replace(
                        _healthy_repro(release).identities[1],
                        appeared=("antigravity_k-0.1.0/src/extra.py",),
                    ),
                ),
            ),
            "파일 목록이 두 빌드에서 다르다",
        ),
        (
            "reproducibility",
            lambda release: _repro(
                release,
                sensitivity=release.Sensitivity(False, True, ("x",), True, (0, 0, 0)),
            ),
            "미니 wheel 이 서로 다르다",
        ),
        (
            "reproducibility",
            lambda release: _repro(
                release,
                sensitivity=release.Sensitivity(True, False, ("x",), True, (0, 0, 0)),
            ),
            "눈이 있다는 증거가 없다",
        ),
        (
            "reproducibility",
            lambda release: _repro(
                release,
                sensitivity=release.Sensitivity(True, True, (), False, (0, 0, 0)),
            ),
            "**우리 repo 탓**이다",
        ),
        (
            "reproducibility",
            lambda release: _repro(
                release,
                sensitivity=release.Sensitivity(True, True, ("mini/kept.py",), False, (0, 0, 0)),
            ),
            "차이가 생성 항목 밖",
        ),
        (
            "reproducibility",
            lambda release: _repro(
                release,
                sensitivity=release.Sensitivity(True, True, ("x",), True, (0, 1, 0)),
            ),
            "민감도 재현의 빌드가 셋이 아니거나 실패했다",
        ),
        (
            "reproducibility",
            lambda release: replace(_healthy_repro(release), ci_pinned=False, ci_pin_value="0"),
            "배포 경로가 같은 pin 을 걸지 않는다",
        ),
        (
            "reproducibility",
            lambda release: replace(_healthy_repro(release), tracked_readable=False),
            "git 추적 목록을 읽지 못했다",
        ),
    ],
)
def test_each_defect_is_a_failure(release: Any, field: str, value: object, fragment: str) -> None:  # noqa: ANN401
    """결함 하나씩을 재현해 각각이 실패 문장으로 남는지 본다 — 통과로 새는 자리가 없어야 한다."""

    bound = value(release) if callable(value) else value
    record = replace(_healthy(release), **{field: bound})

    assert record.ok is False, field
    assert any(fragment in problem for problem in record.problems), record.problems


def _repro(release: Any, **overrides: object) -> Any:  # noqa: ANN401
    """재현 관찰의 변형 — 기준 관찰을 필드별로 바꾼다."""

    return replace(_healthy_repro(release), **overrides)


def test_red_is_the_whole_point(release: Any) -> None:  # noqa: ANN401
    """빠진 배포판을 막지 못한 실행은 실패다 — 그 사실이 이 층의 존재 이유다."""

    record = replace(_healthy(release), tamper_exit=0)

    assert record.detected is False
    assert any("아무것도 막지 못한다" in problem for problem in record.problems)


# ------------------------------------------------------------------ 하한


def test_floors_carry_their_basis_and_bite_when_thin(release: Any) -> None:  # noqa: ANN401
    """하한은 값과 근거를 함께 내고, 얇은 실행(산출물 하나·비교 0)에서는 실제로 문다."""

    floors = release.coverage_floors(_healthy(release))

    assert [floor.label for floor in floors] == [
        "배포 산출물",
        "저장소 밖 PASS",
        "비교한 파일",
        "배포판에 실린 추적 파일",
        "재현 비교한 산출물",
        "내용을 견준 패키지 파일",
    ]
    assert all(floor.why.strip() for floor in floors)
    assert release.floor_problems(floors) == []

    thin = replace(_healthy(release), artifacts=(release.Artifact("wheel", "w.whl", 1, "a"),), passed=())
    assert release.floor_problems(release.coverage_floors(thin)) != []
    assert release.floor_problems(release.coverage_floors(replace(_healthy(release), compared=0))) != []
    empty_tree = replace(_healthy(release), tree=release.TreeCoverage((), (), (), ()))
    assert release.floor_problems(release.coverage_floors(empty_tree)) != []  # 추적 0개 = 본 것이 없다
    nothing = replace(_healthy(release), reproducibility=_repro(release, identities=()))
    assert release.floor_problems(release.coverage_floors(nothing)) != []  # 비교 0건 = ‘동일’ 이 아니라 안 본 것
    blind = replace(_healthy(release), content=release.ContentCheck(0, (), (), (), (release.TRANSFORM_TARGET,)))
    assert release.floor_problems(release.coverage_floors(blind)) != []  # 내용 0건 = ‘차이 없음’ 이 아니라 안 본 것


# ------------------------------------------------------------------ sdist 왕복


def test_wheel_compare_reports_missing_content_and_extra(tmp_path: Path, release: Any) -> None:  # noqa: ANN401
    """두 wheel 을 견준다 — **빠진 것**·**내용이 다른 것**은 실패이고 더 있는 것은 보고 대상이다."""

    direct = tmp_path / "direct.whl"
    rebuilt = tmp_path / "rebuilt.whl"
    with zipfile.ZipFile(direct, "w") as archive:
        archive.writestr("antigravity_k/a.py", "a")
        archive.writestr("antigravity_k/dashboard_dist/index.html", "bundle")
        archive.writestr("antigravity_k/trunc.py", "original body")
    with zipfile.ZipFile(rebuilt, "w") as archive:
        archive.writestr("antigravity_k/a.py", "a")
        archive.writestr("antigravity_k/extra.py", "new")
        archive.writestr("antigravity_k/trunc.py", "orig")  # 이름은 같은데 잘렸다

    diff = release.compare_wheels(direct, rebuilt)

    assert diff.missing == ("antigravity_k/dashboard_dist/index.html",)
    assert diff.differing == ("antigravity_k/trunc.py",)  # 이름만 보면 통과할 자리
    assert diff.extra == ("antigravity_k/extra.py",)
    assert diff.compared == 4


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
    """심을 재료가 없으면 **못 돌렸다** 로 남고 그 까닭을 말한다 — ‘조용한 통과’ 도 ‘사고’ 도 아니다."""

    result = release.rehearse_dropped_sdist(tmp_path / "none.tar.gz", tmp_path / "none.whl", tmp_path)

    assert result.exit_code is None and result.missing == () and result.compared == 0
    assert result.note  # 왜 못 돌렸는지


def test_rehearsal_material_disappearing_is_a_note_not_a_crash(tmp_path: Path, release: Any) -> None:  # noqa: ANN401
    """재현 대상 파일이 패키징에서 사라지면 **사고가 아니라 못 돌림** 이다(그 까닭을 남긴다)."""

    import tarfile

    source = tmp_path / "antigravity_k-0.1.0.tar.gz"
    body = tmp_path / "kept.py"
    body.write_text("kept", encoding="utf-8")
    with tarfile.open(source, "w:gz") as archive:
        archive.add(body, arcname="antigravity_k-0.1.0/antigravity_k/kept.py")
    wheel = _fake_wheel(tmp_path / "antigravity_k-0.1.0-py3-none-any.whl", ("antigravity_k/kept.py",))

    result = release.rehearse_dropped_sdist(source, wheel, tmp_path)

    assert result.exit_code is None
    assert release.REWRITE_TARGET in result.note or release.TAMPER_TARGET in result.note


# ------------------------------------------------------------------ 배포판 vs 추적 트리


def _mini_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    """임시 git 저장소를 만든다 — 추적 대조는 **실제 git** 을 읽으므로 합성 문자열로는 시험되지 않는다."""

    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    identity = ["-c", "user.email=t@t", "-c", "user.name=t"]
    for argv in (["git", "init", "-q", "."], ["git", "add", "-A"], ["git", *identity, "commit", "-qm", "x"]):
        subprocess.run(argv, cwd=repo, capture_output=True, text=True, check=True)
    return repo


def _fake_wheel(path: Path, names: tuple[str, ...]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name in names:
            archive.writestr(name, "x")
    return path


def test_tree_coverage_names_tracked_files_the_wheel_lost(tmp_path: Path, release: Any) -> None:  # noqa: ANN401
    """추적되는데 배포판에 없으면 **이름으로** 남고, 미추적 로컬 파일은 보고만 된다."""

    package = "minipkg"
    repo = _mini_repo(tmp_path, {f"{package}/kept.py": "kept", f"{package}/dropped.py": "dropped"})
    (repo / package / "scratch.py").write_text("scratch", encoding="utf-8")  # 추적되지 않는 로컬 파일
    wheel = _fake_wheel(tmp_path / "w.whl", (f"{package}/kept.py", f"{package}.dist-info/RECORD"))

    coverage = release.tree_coverage(wheel, package_dir=repo / package, package_name=package, repo=repo)

    assert coverage.expected == (f"{package}/dropped.py", f"{package}/kept.py")
    assert coverage.missing == (f"{package}/dropped.py",)
    assert coverage.local_only == (f"{package}/scratch.py",)
    assert coverage.generated == ()  # dist-info 는 패키지 뿌리가 아니므로 생성물로 세지 않는다


def test_tree_coverage_reports_generated_members(tmp_path: Path, release: Any) -> None:  # noqa: ANN401
    """배포판에만 있는 패키지 파일(빌드 생성물)은 보고 대상이다 — 실패가 아니다."""

    package = "minipkg"
    repo = _mini_repo(tmp_path, {f"{package}/kept.py": "kept"})
    wheel = _fake_wheel(tmp_path / "w.whl", (f"{package}/kept.py", f"{package}/vendor/built.bin"))

    coverage = release.tree_coverage(wheel, package_dir=repo / package, package_name=package, repo=repo)

    assert coverage.missing == ()
    assert coverage.generated == (f"{package}/vendor/built.bin",)


def test_tree_coverage_returns_nothing_without_a_wheel(tmp_path: Path, release: Any) -> None:  # noqa: ANN401
    """재료가 없으면 빈 보고다 — 0을 보고 ‘빠짐 없음’ 으로 판정하지 않는다(하한이 문다)."""

    repo = _mini_repo(tmp_path, {"minipkg/kept.py": "kept"})

    coverage = release.tree_coverage(
        tmp_path / "none.whl", package_dir=repo / "minipkg", package_name="minipkg", repo=repo
    )

    assert coverage.expected == () and coverage.missing == ()


def test_tree_coverage_skips_runtime_leftovers(tmp_path: Path, release: Any) -> None:  # noqa: ANN401
    """`__pycache__` 같은 실행 부산물은 목록을 더럽히지 않는다(진짜 결함이 그 사이에 묻힌다)."""

    package = "minipkg"
    repo = _mini_repo(tmp_path, {f"{package}/kept.py": "kept"})
    cache = repo / package / "__pycache__"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "kept.cpython-313.pyc").write_bytes(b"\x00")
    wheel = _fake_wheel(tmp_path / "w.whl", (f"{package}/kept.py",))

    coverage = release.tree_coverage(wheel, package_dir=repo / package, package_name=package, repo=repo)

    assert coverage.local_only == ()


def test_the_real_rehearsal_bites_and_the_control_stays_quiet(tmp_path: Path, release: Any) -> None:  # noqa: ANN401
    """실물 빌드 재현: sdist 에서 뺀 추적 파일을 이 눈이 지목하고, 대조군에서는 아무것도 지목하지 않는다."""

    control, defect = release.rehearse_tree_loss(tmp_path)

    assert control == ()
    assert defect == (release.MINI_DROPPED,)


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


# ------------------------------------------------------------------ 내용 대조(이름이 같아도 바이트가 다를 수 있다)


def test_content_check_matches_the_tree_bytes(tmp_path: Path, release: Any) -> None:  # noqa: ANN401
    """배포판 파일의 **바이트** 를 트리와 견준다 — 같으면 조용하고, 생성물·`dist-info` 는 ‘견줄 수 없다’ 로 남는다."""

    package = tmp_path / "tree" / "minipkg"
    package.mkdir(parents=True)
    (package / "kept.py").write_text("kept = 1\n", encoding="utf-8")
    wheel = tmp_path / "w.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("minipkg/kept.py", "kept = 1\n")
        archive.writestr("minipkg-0.1.0.dist-info/METADATA", "Name: minipkg\n")

    check = release.content_check(wheel, tree_root=package, package_name="minipkg")

    assert check.compared == 1
    assert check.differ == ()
    assert check.absent == ("minipkg-0.1.0.dist-info/METADATA",)


def test_content_check_names_a_changed_file(tmp_path: Path, release: Any) -> None:  # noqa: ANN401
    """내용이 바뀌어 실린 파일은 **이름으로** 남는다 — 목록 대조로는 보이지 않는 결함이다."""

    package = tmp_path / "tree" / "minipkg"
    package.mkdir(parents=True)
    (package / "kept.py").write_text("kept = 1\n", encoding="utf-8")
    wheel = tmp_path / "w.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("minipkg/kept.py", "kept = 9  # build transform\n")

    check = release.content_check(wheel, tree_root=package, package_name="minipkg")

    assert check.differ == ("minipkg/kept.py",)
    assert check.compared == 1


def test_content_check_gives_up_quietly_without_material(tmp_path: Path, release: Any) -> None:  # noqa: ANN401
    """재료가 없으면 0건을 보고한다 — 0을 ‘차이 없음’ 으로 주장하지 않는다(하한이 문다)."""

    check = release.content_check(tmp_path / "none.whl", tree_root=tmp_path / "none", package_name="minipkg")

    assert check.compared == 0 and check.differ == ()


def test_wheel_payloads_fingerprints_content(tmp_path: Path, release: Any) -> None:  # noqa: ANN401
    """항목별 **내용** 지문을 낸다(디렉터리 항목은 세지 않는다)."""

    wheel = tmp_path / "w.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("pkg/a.py", "a")
        archive.writestr("pkg/b.py", "b")

    payloads = release.wheel_payloads(wheel)

    assert set(payloads) == {"pkg/a.py", "pkg/b.py"}
    assert payloads["pkg/a.py"] != payloads["pkg/b.py"]


def test_damage_sdist_drops_one_file_and_rewrites_another(tmp_path: Path, release: Any) -> None:  # noqa: ANN401
    """한 번의 사본으로 빠짐과 내용 변환을 함께 심는다(왕복 빌드를 두 번 돌리지 않기 위해서다)."""

    import tarfile

    source = tmp_path / "antigravity_k-0.1.0.tar.gz"
    tree = tmp_path / "tree"
    (tree / "antigravity_k").mkdir(parents=True)
    (tree / "antigravity_k" / "dropped.py").write_text("dropped", encoding="utf-8")
    (tree / "antigravity_k" / "kept.py").write_text("kept", encoding="utf-8")
    with tarfile.open(source, "w:gz") as archive:
        archive.add(tree / "antigravity_k", arcname="antigravity_k-0.1.0/antigravity_k")

    target = release.damage_sdist(
        source,
        tmp_path / "damaged.tar.gz",
        remove="antigravity_k/dropped.py",
        rewrite="antigravity_k/kept.py",
        appendix="\n# rewritten\n",
    )

    with tarfile.open(target) as archive:
        names = [member.name for member in archive.getmembers()]
        kept = archive.extractfile("antigravity_k-0.1.0/antigravity_k/kept.py").read().decode("utf-8")

    assert all(not name.endswith("dropped.py") for name in names)
    assert kept == "kept\n# rewritten\n"


def test_damage_sdist_refuses_a_file_that_is_not_there(tmp_path: Path, release: Any) -> None:  # noqa: ANN401
    """바꿀 파일이 그 압축본에 없으면 조용히 넘어가지 않고 거부한다(재현인 줄 알고 통과하는 순간을 막는다)."""

    import tarfile

    source = tmp_path / "small.tar.gz"
    (tmp_path / "only.py").write_text("x", encoding="utf-8")
    with tarfile.open(source, "w:gz") as archive:
        archive.add(tmp_path / "only.py", arcname="only.py")

    with pytest.raises(ValueError, match="내용을 바꿀 파일이"):
        release.damage_sdist(source, tmp_path / "out.tar.gz", remove="only.py", rewrite="missing.py")


def test_the_content_rehearsal_bites_and_the_control_stays_quiet(tmp_path: Path, release: Any) -> None:  # noqa: ANN401
    """실물 빌드 재현: 빌드가 내용을 바꿔 싣는 프로젝트를 이 눈이 지목하고, 변환만 뺀 대조군은 조용하다."""

    control, defect, note = release.rehearse_content_transform(tmp_path)

    assert note == ""
    assert control == ()
    assert defect == (release.TRANSFORM_TARGET,)


# ------------------------------------------------------------------ 재현 빌드(같은 입력 → 같은 바이트)


def _tar(
    path: Path,
    members: dict[str, tuple[str, float]],
    directories: tuple[str, ...] = (),
    *,
    compressed: bool = True,
    dir_mtime: float = 1_790_000_000.0,
) -> Path:
    """합성 sdist — member 별 내용과 mtime 을 직접 정한다(무엇이 다른지 우리가 아는 상황을 만든다).

    `compressed=False` 는 gzip 헤더의 벽시계 시각을 피하기 위해서다(그것 때문에 같은 항목의 두 압축본도 바이트가 다르다).
    """

    import tarfile

    with tarfile.open(path, "w:gz" if compressed else "w") as archive:
        for name, (body, mtime) in members.items():
            payload = body.encode("utf-8")
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            info.mtime = mtime
            info.mode = 0o644
            info.uid, info.gid = 501, 20
            archive.addfile(info, io.BytesIO(payload))
        for name in directories:
            directory = tarfile.TarInfo(name)
            directory.type = tarfile.DIRTYPE
            directory.mtime = dir_mtime
            directory.mode = 0o755
            archive.addfile(directory)
    return path


def test_identical_archives_are_identical(tmp_path: Path, release: Any) -> None:  # noqa: ANN401
    """같은 재료로 만든 두 압축본은 `identical` 이고 차이 목록이 비어 있다(baseline 오탐 방지)."""

    members = {"pkg-0.1.0/pkg/kept.py": ("kept", 1_790_000_000.0), "pkg-0.1.0/PKG-INFO": ("meta", 1_790_000_000.0)}
    first = _tar(tmp_path / "a.tar", members, compressed=False)
    second = _tar(tmp_path / "b.tar", members, compressed=False)

    identity = release.compare_artifacts("sdist", first, second, is_tree_file=lambda _name: False)

    assert identity.identical is True
    assert identity.differs == () and identity.appeared == () and identity.members == 2
    assert identity.bytes_only is False


def _regzip(source: Path, target: Path, *, header_mtime: int) -> Path:
    """평범한 tar 를 **지정한 gzip 헤더 시각** 으로 다시 압축한다.

    실제로 두 번째 빌드가 이렇게 다르다(gzip 헤더의 벽시계). 시간에 기대면 시험이 흔들리므로 시각을 직접 쓴다.
    """

    import gzip

    with source.open("rb") as handle:
        raw = handle.read()
    with target.open("wb") as out, gzip.GzipFile(fileobj=out, mode="wb", mtime=header_mtime) as gz:
        gz.write(raw)
    return target


def test_same_members_but_different_bytes_are_named(tmp_path: Path, release: Any) -> None:  # noqa: ANN401
    """항목이 모두 같은데 바이트가 다를 수 있다(gzip 헤더의 벽시계) — 그때 “왜” 를 이름으로 말해야 한다.

    이 구분이 없으면 “다르다” 가 “무엇이 다른지 모른다” 로 읽히고, 사람은 그 문장을 무시하게 된다.
    """

    members = {"pkg-0.1.0/pkg/kept.py": ("kept", 1_790_000_000.0)}
    plain = _tar(tmp_path / "plain.tar", members, compressed=False)
    first = _regzip(plain, tmp_path / "a.tar.gz", header_mtime=0)
    second = _regzip(plain, tmp_path / "b.tar.gz", header_mtime=1)

    identity = release.compare_artifacts("sdist", first, second, is_tree_file=lambda _name: False)

    assert identity.identical is False  # gzip 헤더의 시각이 다르다
    assert identity.differs == () and identity.appeared == ()
    assert identity.bytes_only is True  # 실린 파일이 바뀐 것은 아니다


def test_appeared_members_are_named(tmp_path: Path, release: Any) -> None:  # noqa: ANN401
    """한쪽에만 있는 파일은 목록 차이로 **이름을 남긴다**(무엇이 실릴지가 빌드 순간에 달렸다)."""

    first = _tar(tmp_path / "a.tar.gz", {"pkg-0.1.0/a.py": ("a", 1.0)})
    second = _tar(tmp_path / "b.tar.gz", {"pkg-0.1.0/a.py": ("a", 1.0), "pkg-0.1.0/b.py": ("b", 1.0)})

    identity = release.compare_artifacts("sdist", first, second, is_tree_file=lambda _name: False)

    assert identity.identical is False
    assert identity.appeared == ("pkg-0.1.0/b.py",)
    assert identity.differs == ()
    assert identity.bytes_only is False  # 목록이 흔들렸다 — 압축·헤더 문제가 아니다


def test_only_generated_and_directories_may_differ(tmp_path: Path, release: Any) -> None:  # noqa: ANN401
    """허용되는 차이는 좁다 — 디렉터리·**커밋되지 않은** 생성물은 허용, 커밋된 파일은 결함으로 남는다.

    이 구분이 이 층의 핵심이다: 빌드 자신이 트리에 남기는 `*.egg-info` 를 ‘실제 파일’ 로 세면 이 층은 자기 찌거기마다
    빨개지고, 반대로 실제 파일의 차이를 예외로 삼키면 다음 결함이 조용히 섞인다.
    """

    first = _tar(
        tmp_path / "a.tar.gz",
        {
            "pkg-0.1.0/pkg/kept.py": ("kept", 100.0),
            "pkg-0.1.0/src/pkg.egg-info/PKG-INFO": ("gen", 100.0),
        },
        directories=("pkg-0.1.0/pkg",),
    )
    second = _tar(
        tmp_path / "b.tar.gz",
        {
            "pkg-0.1.0/pkg/kept.py": ("kept", 200.0),
            "pkg-0.1.0/src/pkg.egg-info/PKG-INFO": ("gen", 300.0),
        },
        directories=("pkg-0.1.0/pkg",),
    )
    tracked = frozenset({"pkg/kept.py"})

    identity = release.compare_artifacts(
        "sdist", first, second, is_tree_file=release._tree_oracle("sdist", tracked=tracked)
    )

    assert identity.real_differs == ("pkg-0.1.0/pkg/kept.py",)  # 커밋된 파일이 달라졌다 → 결함
    assert identity.allowed_differs == ("pkg-0.1.0/src/pkg.egg-info/PKG-INFO",)  # 생성물은 허용
    assert identity.identical is False


def test_directories_may_differ(tmp_path: Path, release: Any) -> None:  # noqa: ANN401
    """디렉터리 항목은 빌드가 새로 만들므로 시각이 다르다 — 그 자체는 결함이 아니다(파일 행은 두 빌드가 같다)."""

    members = {"pkg-0.1.0/pkg/x.py": ("x", 100.0)}
    first = _tar(tmp_path / "a.tar.gz", members, directories=("pkg-0.1.0/pkg",), dir_mtime=1.0)
    second = _tar(tmp_path / "b.tar.gz", members, directories=("pkg-0.1.0/pkg",), dir_mtime=2.0)
    tracked = frozenset({"pkg/x.py"})

    identity = release.compare_artifacts(
        "sdist", first, second, is_tree_file=release._tree_oracle("sdist", tracked=tracked)
    )

    assert identity.real_differs == ()
    assert identity.allowed_differs == ("pkg-0.1.0/pkg",)


def test_pinned_members_count_the_pin(tmp_path: Path, release: Any) -> None:  # noqa: ANN401
    """pin 시각을 쓰는 항목 수를 센다 — 근거 문장(`sdist 는 0`)이 관측과 어긋나면 낡은 근거다."""

    pinned = _tar(tmp_path / "pinned.tar.gz", {"pkg-0.1.0/a.py": ("a", float(release.REPRO_PIN))})
    other = _tar(tmp_path / "other.tar.gz", {"pkg-0.1.0/a.py": ("a", 1.0)})
    stamped = tmp_path / "stamped.whl"
    with zipfile.ZipFile(stamped, "w") as archive:
        info = zipfile.ZipInfo("pkg/a.py", date_time=(2025, 9, 23, 4, 0, 0))
        archive.writestr(info, "a")

    assert release._pinned_members("sdist", pinned) == 1
    assert release._pinned_members("sdist", other) == 0
    assert release._pinned_members("wheel", stamped) == 1


def test_member_name_maps_archive_paths_to_the_tree(release: Any) -> None:  # noqa: ANN401
    """아카이브 이름을 트리 경로로 되돌린다 — sdist 는 최상위 한 칸을 벗고 wheel 은 패키지 접두사를 벗긴다."""

    assert release._member_name("antigravity_k-0.1.0/src/antigravity_k/a.py", kind="sdist") == "src/antigravity_k/a.py"
    assert release._member_name("antigravity_k/engine/a.py", kind="wheel") == "engine/a.py"
    assert release._member_name("antigravity_k", kind="wheel") == ""


def test_tree_oracle_is_strict_without_a_tracked_list(release: Any) -> None:  # noqa: ANN401
    """추적 목록을 못 읽으면 **엄격한 쪽** 으로 판정한다 — 못 읽은 목록을 예외로 삼키지 않는다."""

    blind = release._tree_oracle("sdist", tracked=None)
    seeing = release._tree_oracle("sdist", tracked=frozenset({"src/a.py"}))
    wheel_eye = release._tree_oracle("wheel", tracked=frozenset({"src/antigravity_k/a.py"}))

    assert blind("src/a.py") is True and blind("anything.py") is True
    assert seeing("src/a.py") is True and seeing("src/b.py") is False
    assert wheel_eye("a.py") is True and wheel_eye("b.py") is False


def test_tracked_paths_reads_git_and_gives_up_quietly(tmp_path: Path, release: Any) -> None:  # noqa: ANN401
    """git 이 아는 파일을 읽는다 — 저장소가 아니면 `None`(그 사실이 따로 문제로 보고된다)."""

    repo = _mini_repo(tmp_path, {"pkg/kept.py": "kept"})
    plain = tmp_path / "not-a-repo"
    plain.mkdir()

    assert release.tracked_paths(repo) == frozenset({"pkg/kept.py"})
    assert release.tracked_paths(plain) is None


def _workflow(path: Path, body: str) -> Path:
    workflows = path / ".github" / "workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    target = workflows / "ci.yml"
    target.write_text(body, encoding="utf-8")
    return target


@pytest.mark.parametrize(
    ("body", "pinned", "fragment"),
    [
        ("jobs:\n  test:\n    steps: []\n", False, "`build` job 이 없다"),
        (
            "jobs:\n  build:\n    steps:\n      - name: Build\n        run: uv build --no-sources\n  next:\n    steps: []\n",
            False,
            "SOURCE_DATE_EPOCH` 를 걸지 않는다",
        ),
        (
            'jobs:\n  build:\n    steps:\n      - name: Build\n        env:\n          SOURCE_DATE_EPOCH: "1"\n        run: uv build --no-sources\n',
            False,
            "",
        ),
        (
            "jobs:\n  build:\n    steps:\n      - name: Verify\n        run: echo hi\n",
            False,
            "`uv build` 단계가 없다",
        ),
    ],
)
def test_ci_pin_check_reports_why_it_cannot_see(
    tmp_path: Path,
    release: Any,
    monkeypatch: pytest.MonkeyPatch,
    body: str,
    pinned: bool,
    fragment: str,  # noqa: ANN401, E501
) -> None:
    """배포 경로를 못 보면 **이유를 말한다** — job 이 사라지거나 이름이 바뀌어도 조용히 통과하지 않는다."""

    monkeypatch.setattr(release, "CI_WORKFLOW", _workflow(tmp_path, body))

    result, value, note = release.ci_pin_check()

    assert result is pinned
    assert (fragment in note) if fragment else (value == "1" and note == "")


def test_ci_pin_check_accepts_the_contract_value(tmp_path: Path, release: Any, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN401, E501
    """같은 값을 걸면 통과한다 — 이 층이 검증한 물건과 배포되는 물건이 같아지는 자리다."""

    body = (
        "jobs:\n  build:\n    steps:\n      - name: Build\n        env:\n"
        f'          SOURCE_DATE_EPOCH: "{release.REPRO_PIN}"\n        run: uv build --no-sources\n'
    )
    monkeypatch.setattr(release, "CI_WORKFLOW", _workflow(tmp_path, body))

    assert release.ci_pin_check() == (True, str(release.REPRO_PIN), "")


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
    assert payload["counts"]["tracked_shipped"] == 656
    assert payload["counts"]["tracked_missing"] == 0
    assert payload["counts"]["tree_rehearsal_bites"] == 1
    assert payload["counts"]["content_compared"] == 658
    assert payload["counts"]["content_differ"] == 0
    assert payload["counts"]["content_rehearsal_bites"] == 1
    assert payload["counts"]["roundtrip_content_bites"] == 1
    assert payload["counts"]["differing"] == 0
    assert payload["tree"]["expected"] == 656
    assert payload["tree"]["rehearsal_defect"] == [release.MINI_DROPPED]
    assert payload["tamper"]["detected"] is True
    assert payload["reproducibility"]["pin"] == release.REPRO_PIN
    assert payload["reproducibility"]["ci_pinned"] is True
    assert payload["reproducibility"]["sensitivity"]["pin_moves_bytes"] is True
    assert payload["counts"]["identity_compared"] == 2
    assert payload["counts"]["identity_identical"] == 1  # wheel 만 동일(예외는 sdist)
    assert payload["counts"]["identity_real_differs"] == 0
    assert payload["counts"]["sensitivity_bites"] == 1
    assert payload["counts"]["ci_pinned"] == 1
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


@pytest.fixture(scope="module")
def real_measure(release: Any) -> Any:  # noqa: ANN401
    """실물 측정 **한 번** — 실물 시험들이 같은 관찰을 나눠 쓴다(두 번 빌드하면 시간이 두 배가 된다)."""

    return release.measure()


@pytest.mark.slow
def test_the_real_artifacts_are_built_consumed_and_tampered(real_measure: Any, release: Any) -> None:  # noqa: ANN401
    """실물: wheel/sdist 를 만들고 저장소 밖에서 써 보고, 빠진 배포판이 막히는지까지 본다(수십 초)."""

    record = real_measure

    assert record.ok, record.problems
    assert {item.kind for item in record.artifacts} == {"wheel", "sdist"}
    assert all(item.bytes > 0 and len(item.sha256) == 64 for item in record.artifacts)
    assert record.passed == ("wheel", "sdist")
    assert record.roundtrip_exit == 0
    assert record.missing == ()  # sdist 에서 다시 빌드한 wheel 이 같은 파일을 담는다
    assert record.compared >= 100
    assert record.tree.missing == ()  # 배포판이 커밋된 코드를 모두 담는다
    assert len(record.tree.expected) >= 600
    assert record.tree_rehearsal_defect == (release.MINI_DROPPED,)
    assert record.tree_rehearsal_control == ()
    assert record.rehearsal_exit == 0
    assert record.rehearsal_missing == (release.TAMPER_TARGET,)  # sdist 에서 뺀 파일을 왕복이 지목했다
    assert record.detected is True


@pytest.mark.slow
def test_the_real_bytes_are_reproducible_under_the_pin(real_measure: Any, release: Any) -> None:  # noqa: ANN401
    """실물 재현 계약: 같은 pin 두 번에서 **wheel 은 같은 바이트**, sdist 는 생성 항목만 다르고, CI 도 같은 pin 을 건다."""

    record = real_measure
    repro = record.reproducibility
    wheel = next(item for item in repro.identities if item.kind == "wheel")
    sdist = next(item for item in repro.identities if item.kind == "sdist")

    assert wheel.identical is True, (wheel.first[:12], wheel.second[:12])
    assert wheel.pinned_members == wheel.members  # 항목 전부가 pin 시각을 쓴다
    assert sdist.identical is False  # backend 는 sdist 에서 이 값을 읽지 않는다(기록된 한계)
    assert sdist.pinned_members == 0  # 그 관측이 근거 문장과 같다
    assert sdist.real_differs == () and sdist.appeared == ()  # 커밋된 파일·목록은 흔들리지 않는다
    assert sdist.allowed_differs  # 차이는 있지만 전부 생성 항목이다
    assert repro.sensitivity.control_equal is True
    assert repro.sensitivity.pin_moves_bytes is True
    assert repro.sensitivity.sdist_backend_only is True
    assert repro.ci_pinned is True
    assert repro.tracked_readable is True


@pytest.mark.slow
def test_the_real_content_matches_the_tree_byte_for_byte(real_measure: Any, release: Any) -> None:  # noqa: ANN401
    """실물 내용 계약: 배포판에 실린 바이트가 디스크 트리와 같고, 그 눈이 실물 변환 프로젝트에서 문다."""

    content = real_measure.content

    assert content.differ == ()  # 이름이 같고 내용이 다른 파일이 없다
    assert content.compared >= 600  # 실제로 견준 것이 하한 위에 있다
    assert content.rehearsal_defect == (release.TRANSFORM_TARGET,)
    assert content.rehearsal_control == ()
    assert content.rehearsal_note == ""
    assert real_measure.differing == ()  # sdist 를 거쳐도 내용이 바뀌지 않는다
    assert release.REWRITE_TARGET in real_measure.rehearsal_differing
    assert release.TAMPER_TARGET in real_measure.rehearsal_missing


def test_the_report_json_is_readable_by_the_gate(release: Any) -> None:  # noqa: ANN401
    """리포트 형태가 게이트의 수치 추출 규약(지목한 키의 dict)과 맞는지 — 키 이름이 바뀌면 추이가 조용히 빈다."""

    payload = release.as_mapping(_healthy(release), release.self_probe())

    assert set(payload["counts"]) >= {"artifacts", "verified", "compared", "missing", "tamper_detected"}
    assert set(payload["coverage"]) == {"artifacts", "verified", "compared"}
    assert set(payload["reproducibility"]) == {
        "pin",
        "identities",
        "second_build_exit",
        "sensitivity",
        "ci_pinned",
        "ci_pin_value",
        "ci_note",
        "tracked_readable",
        "seconds",
    }
    assert set(payload["roundtrip"]) == {
        "exit",
        "compared",
        "missing",
        "differing",
        "extra",
        "rehearsal_exit",
        "rehearsal_missing",
        "rehearsal_differing",
    }
    assert set(payload["content"]) == {
        "compared",
        "differ",
        "absent",
        "rehearsal_control",
        "rehearsal_defect",
        "rehearsal_note",
    }
    assert isinstance(payload["floors"], list) and payload["floors"]
    assert io.StringIO(json.dumps(payload)).read()  # 직렬화 가능해야 게이트가 읽는다


def test_the_baseline_watches_the_compared_floor(release: Any) -> None:  # noqa: ANN401
    """왕복 비교 수가 게이트의 수치 추출 키에 실린다 — 빠지면 감소가 추이에 안 보인다."""

    payload = release.as_mapping(_healthy(release), release.self_probe())

    assert payload["counts"]["compared"] == _healthy(release).compared
    assert "비교한 파일" in {floor["label"] for floor in payload["floors"]}  # type: ignore[index, union-attr]
