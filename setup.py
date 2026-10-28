from __future__ import annotations

import shutil
from pathlib import Path
from typing import override

from setuptools import setup
from setuptools.command.build_py import build_py


class _CleanPackageDataBuild(build_py):
    build_lib: str

    @override
    def run(self) -> None:
        if not self.build_lib:
            raise RuntimeError("Package-data build root must not be empty")
        build_root = Path(self.build_lib).resolve()
        if build_root == Path(build_root.anchor) or build_root == Path.cwd().resolve():
            raise RuntimeError(f"Unsafe package-data build root: {build_root}")
        project_root = Path(__file__).resolve().parent
        source_package = Path(self.get_package_dir("antigravity_k"))
        if not source_package.is_absolute():
            source_package = project_root / source_package
        source_package = source_package.resolve()
        if build_root.is_relative_to(source_package) or source_package.is_relative_to(build_root):
            raise RuntimeError(f"Package-data build root overlaps package source: {build_root}")
        package_root = build_root / "antigravity_k"
        if package_root.is_symlink() or (package_root.exists() and not package_root.is_dir()):
            raise RuntimeError(f"Unsafe package build root: {package_root}")
        for relative_path in (
            ("dashboard_dist",),
            ("prompts",),
            ("data", "benchmarks"),
        ):
            target = package_root.joinpath(*relative_path)
            if any(parent.is_symlink() for parent in target.parents if parent != build_root.parent):
                raise RuntimeError(f"Unsafe package-data build parent: {target}")
            if target.is_symlink() or (target.exists() and not target.is_dir()):
                raise RuntimeError(f"Unsafe package-data build target: {target}")
            if target.is_dir():
                shutil.rmtree(target)
        super().run()


_ = setup(cmdclass={"build_py": _CleanPackageDataBuild})
