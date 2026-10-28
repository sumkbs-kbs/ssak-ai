"""Exercise package-data cleanup without running setup, a backend or an install."""

from __future__ import annotations

import ast
import shutil
from pathlib import Path
from typing import cast, override

import pytest


_SETUP = Path(__file__).resolve().parents[1] / "setup.py"
_RESOURCES = (
    Path("dashboard_dist/index.html"),
    Path("prompts/roles/default.md"),
    Path("data/benchmarks/fixture.json"),
)
_CLEANED_DIRECTORIES = (Path("dashboard_dist"), Path("prompts"), Path("data/benchmarks"))


class _FakeBuild:
    """The src-layout source lookup is real fixture data; the parent only observes."""

    def __init__(self) -> None:
        self.build_lib = ""
        self.package_dir = {"": "src"}
        self.parent_views: list[tuple[bool, ...]] = []

    def get_package_dir(self, package: str) -> str:
        assert package == "antigravity_k"
        return "src/antigravity_k"

    def run(self) -> None:
        target = Path(self.build_lib) / "antigravity_k"
        self.parent_views.append(tuple((target / relative).exists() for relative in _CLEANED_DIRECTORIES))


def _load_owned_build_class(project: Path) -> type[_FakeBuild]:
    """Execute just the production class, with no setup() call or setuptools import."""
    source = _SETUP.read_text(encoding="utf-8")
    owned_setup = project / "setup.py"
    owned_setup.write_text(source, encoding="utf-8")
    parsed = ast.parse(source, filename=str(owned_setup))
    declarations = [node for node in parsed.body if isinstance(node, ast.ClassDef) and node.name == "_CleanPackageDataBuild"]
    assert len(declarations) == 1
    declaration = declarations[0]
    module = ast.Module(body=[declaration], type_ignores=[])
    namespace: dict[str, object] = {
        "__file__": str(owned_setup),
        "__name__": "r58_owned_package_build",
        "Path": Path,
        "shutil": shutil,
        "override": override,
        "build_py": _FakeBuild,
    }
    exec(compile(module, str(owned_setup), "exec"), namespace)  # noqa: S102 - only the reviewed class AST.
    loaded = namespace[declaration.name]
    assert isinstance(loaded, type) and issubclass(loaded, _FakeBuild)
    return cast(type[_FakeBuild], loaded)


def _source_project(root: Path) -> tuple[Path, Path]:
    project = root / "source-project"
    package = project / "src" / "antigravity_k"
    package.mkdir(parents=True)
    for relative in _RESOURCES:
        target = package / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("source:" + relative.as_posix(), encoding="utf-8")
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "new_module.py").write_text("value = 'new source'\n", encoding="utf-8")
    return project, package


def _bytes_below(package: Path) -> dict[str, bytes]:
    return {path.relative_to(package).as_posix(): path.read_bytes() for path in sorted(package.rglob("*")) if path.is_file()}


@pytest.mark.parametrize("destination", ["src", "project", "ancestor", "source-alias"])
def test_package_data_cleanup_rejects_source_overlap_before_any_deletion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, destination: str,
) -> None:
    # Given: real source resources and the actual build class, not the setup entrypoint.
    project, source_package = _source_project(tmp_path)
    build_class = _load_owned_build_class(project)
    monkeypatch.chdir(project)
    command = build_class()
    if destination == "src":
        command.build_lib = "src"
    elif destination == "project":
        command.build_lib = "."
    elif destination == "ancestor":
        command.build_lib = str(tmp_path)
    else:
        alias = tmp_path / "source-alias"
        alias.symlink_to(project / "src", target_is_directory=True)
        command.build_lib = str(alias)
    before = _bytes_below(source_package)

    # When: only the real cleanup method runs; the parent backend is an observer.
    error: RuntimeError | None = None
    try:
        command.run()
    except RuntimeError as caught:
        error = caught

    # Then: refusal precedes both source loss and delegation to a backend.
    assert _bytes_below(source_package) == before
    assert command.parent_views == []
    assert error is not None


@pytest.mark.parametrize("build_location", ["project-default", "external"])
def test_separate_build_root_cleans_only_stale_resources_before_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, build_location: str,
) -> None:
    # Given: an independent build destination, with stale resources and a kept module.
    project, source_package = _source_project(tmp_path)
    build_class = _load_owned_build_class(project)
    monkeypatch.chdir(project)
    build_root = (
        project / "build" / "lib"
        if build_location == "project-default"
        else tmp_path / "separate-output" / "lib"
    )
    target_package = build_root / "antigravity_k"
    for relative in _RESOURCES:
        target = target_package / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("stale:" + relative.as_posix(), encoding="utf-8")
    kept = target_package / "kept_module.py"
    kept.write_text("keep = True\n", encoding="utf-8")
    source_before = _bytes_below(source_package)
    command = build_class()
    command.build_lib = str(build_root)

    # When: cleanup is followed by the fake parent, with no build/install performed.
    command.run()

    # Then: only stale build data was removed and source data remains byte-identical.
    assert command.parent_views == [(False, False, False)]
    assert _bytes_below(source_package) == source_before
    assert kept.read_text(encoding="utf-8") == "keep = True\n"
    assert all(not (target_package / relative).exists() for relative in _CLEANED_DIRECTORIES)
