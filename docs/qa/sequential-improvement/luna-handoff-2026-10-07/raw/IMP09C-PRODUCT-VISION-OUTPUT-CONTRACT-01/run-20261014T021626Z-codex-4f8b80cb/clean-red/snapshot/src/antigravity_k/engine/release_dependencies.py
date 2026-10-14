from __future__ import annotations

import json
import re
import tomllib
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Literal, override

from pydantic import BaseModel, ConfigDict, Field, ValidationError


@dataclass(frozen=True, slots=True)
class ReleaseDependencyError(ValueError):
    reason: str

    @override
    def __str__(self) -> str:
        return self.reason


class _LockSource(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="allow")

    registry: str | None = None
    url: str | None = None


class _LockDependency(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="allow")

    name: str = Field(min_length=1)
    extra: str | tuple[str, ...] | None = None


class _LockMetadata(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, populate_by_name=True, extra="allow")

    provides_extras: tuple[str, ...] = Field(default_factory=tuple, alias="provides-extras")


class _LockPackage(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="allow")

    name: str = Field(min_length=1)
    version: str | None = None
    source: _LockSource | None = None
    dependencies: tuple[_LockDependency, ...] = ()
    optional_dependencies: dict[str, tuple[_LockDependency, ...]] = Field(default_factory=dict)
    metadata: _LockMetadata = Field(default_factory=_LockMetadata)


class _UvLock(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="allow")

    version: Literal[1] = 1
    package: tuple[_LockPackage, ...]


class _NpmPackage(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="allow")

    name: str | None = None
    version: str | None = None
    resolved: str | None = None
    integrity: str | None = None
    license: str | None = None
    dev: bool = False
    dependencies: dict[str, str] = Field(default_factory=dict)
    devDependencies: dict[str, str] = Field(default_factory=dict)


class _PackageLock(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="allow")

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    lockfileVersion: Literal[3]
    packages: dict[str, _NpmPackage]


@dataclass(frozen=True, slots=True)
class PythonDependency:
    name: str
    version: str
    source_url: str | None


@dataclass(frozen=True, slots=True)
class DashboardDependency:
    name: str
    version: str
    source_url: str | None
    license_id: str | None
    # "lock" = package-lock.json의 license 필드, "provenance-declared" =
    # THIRD_PARTY_PROVENANCE.toml의 declared_licenses, None = 미상(gate 실패).
    license_source: str | None = None


# 배포물에 라이선스 메타데이터가 없는 런타임 의존성을 사람이 승인해 **선언**한다.
# 정책 단일 진실원은 THIRD_PARTY_PROVENANCE.toml `[distribution].declared_licenses`이며
# 형식은 "<ecosystem>:<name>@<version>=<spdx>"이다. 선언이 없으면 라이선스는 미상으로
# 남고 license gate가 실패한다 — 메타데이터를 합성하지 않는다.
_DECLARED_LICENSE_PATTERN = re.compile(
    r"^(?P<ecosystem>[a-z]+):(?P<name>[^=@]+)@(?P<version>[^=]+)=(?P<spdx>[A-Za-z0-9.+-]+)$",
)


def declared_licenses(project_root: Path) -> dict[str, str]:
    """provenance 정책이 승인한 라이선스 선언을 `<ecosystem>:<name>@<version>` → SPDX 맵으로 읽는다.

    정책 파일이 없으면 빈 맵을 반환한다(선언 없음 = 미상 유지). 형식 오류는
    조용히 넘기지 않고 ReleaseDependencyError로 실패시킨다 — 잘못된 정책이
    gate를 통과시키는 것을 막는다.
    """
    provenance = project_root / "THIRD_PARTY_PROVENANCE.toml"
    if not provenance.is_file():
        return {}
    try:
        data = tomllib.loads(provenance.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ReleaseDependencyError(f"Could not read provenance policy: {provenance}") from error
    distribution = data.get("distribution")
    raw = distribution.get("declared_licenses", ()) if isinstance(distribution, dict) else ()
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        message = "THIRD_PARTY_PROVENANCE.toml declared_licenses must be a list of strings"
        raise ReleaseDependencyError(message)
    declared: dict[str, str] = {}
    for item in raw:
        match = _DECLARED_LICENSE_PATTERN.match(item)
        if match is None:
            raise ReleaseDependencyError(f"Malformed declared license entry: {item!r}")
        identifier = f"{match['ecosystem']}:{match['name']}@{match['version']}"
        declared[identifier] = match["spdx"]
    return declared


@dataclass(frozen=True, slots=True)
class PythonRuntimeDependencies:
    root_name: str
    excluded_extras: tuple[str, ...]
    dependencies: tuple[PythonDependency, ...]


@dataclass(frozen=True, slots=True)
class DashboardRuntimeDependencies:
    root_name: str
    root_version: str
    dependencies: tuple[DashboardDependency, ...]


def python_runtime_dependencies(project_root: Path) -> PythonRuntimeDependencies:
    lock_path = project_root / "uv.lock"
    try:
        raw_lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
        lock = _UvLock.model_validate(raw_lock)
    except (OSError, tomllib.TOMLDecodeError, ValidationError) as error:
        raise ReleaseDependencyError(f"Could not parse Python lockfile: {lock_path}") from error

    by_name: dict[str, tuple[_LockPackage, ...]] = defaultdict(tuple)
    root: _LockPackage | None = None
    for package in lock.package:
        normalized = _canonical_python_name(package.name)
        by_name[normalized] = (*by_name[normalized], package)
        if normalized == "antigravity-k":
            root = package
    if root is None or root.version is not None:
        raise ReleaseDependencyError("The Python lockfile must contain one editable antigravity-k root package.")

    selected: dict[str, _LockPackage] = {}
    pending = [root]
    while pending:
        package = pending.pop()
        normalized = _canonical_python_name(package.name)
        selected[normalized] = package
        for dependency in package.dependencies:
            _queue_python_dependency(dependency, by_name, selected, pending)
    dependencies = tuple(
        _python_dependency(package)
        for package in selected.values()
        if _canonical_python_name(package.name) != "antigravity-k"
    )
    return PythonRuntimeDependencies(
        root_name=root.name,
        excluded_extras=tuple(sorted(set(root.metadata.provides_extras))),
        dependencies=tuple(sorted(dependencies, key=lambda item: _canonical_python_name(item.name))),
    )


def dashboard_runtime_dependencies(project_root: Path) -> DashboardRuntimeDependencies:
    lock_path = project_root / "dashboard" / "package-lock.json"
    try:
        lock = _PackageLock.model_validate_json(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValidationError) as error:
        raise ReleaseDependencyError(f"Could not parse dashboard lockfile: {lock_path}") from error
    root = lock.packages.get("")
    if root is None or root.name is None or root.version is None:
        raise ReleaseDependencyError("The dashboard lockfile has no valid root package.")

    selected: dict[str, _NpmPackage] = {}
    pending = [("", root)]
    while pending:
        parent_path, package = pending.pop()
        for dependency_name in package.dependencies:
            dependency_path = _resolve_npm_path(parent_path, dependency_name, lock.packages)
            dependency = lock.packages[dependency_path]
            if dependency.dev:
                continue
            if dependency_path not in selected:
                selected[dependency_path] = dependency
                pending.append((dependency_path, dependency))
    declared = declared_licenses(project_root)
    dependencies = tuple(
        _dashboard_dependency(dependency_path, dependency, declared) for dependency_path, dependency in selected.items()
    )
    return DashboardRuntimeDependencies(
        root_name=root.name,
        root_version=root.version,
        dependencies=tuple(sorted(dependencies, key=lambda item: item.name)),
    )


def _queue_python_dependency(
    dependency: _LockDependency,
    by_name: Mapping[str, tuple[_LockPackage, ...]],
    selected: Mapping[str, _LockPackage],
    pending: list[_LockPackage],
) -> None:
    normalized = _canonical_python_name(dependency.name)
    if normalized not in selected:
        for package in by_name.get(normalized, ()):
            pending.append(package)
    extras = _dependency_extras(dependency)
    selected_package = selected.get(normalized)
    if selected_package is None:
        selected_package = next(iter(by_name[normalized]))
    for extra in extras:
        for optional in selected_package.optional_dependencies.get(extra, ()):
            optional_name = _canonical_python_name(optional.name)
            if optional_name not in selected:
                for package in by_name.get(optional_name, ()):
                    pending.append(package)


def _dependency_extras(dependency: _LockDependency) -> tuple[str, ...]:
    match dependency.extra:
        case None:
            return ()
        case str(extra):
            return (extra,)
        case extras:
            return extras


def _python_dependency(package: _LockPackage) -> PythonDependency:
    if package.version is None:
        raise ReleaseDependencyError(f"Locked runtime package has no version: {package.name}")
    return PythonDependency(
        name=package.name,
        version=package.version,
        source_url=_python_source_url(package),
    )


def _dashboard_dependency(
    package_path: str,
    package: _NpmPackage,
    declared: Mapping[str, str],
) -> DashboardDependency:
    if package.version is None:
        raise ReleaseDependencyError(f"Locked dashboard package has no version: {package_path}")
    name = _npm_package_name(package_path, package)
    declared_spdx = declared.get(f"npm:{name}@{package.version}")
    if package.license is not None:
        license_id: str | None = package.license
        license_source: str | None = "lock"
    elif declared_spdx is not None:
        license_id = declared_spdx
        license_source = "provenance-declared"
    else:
        license_id = None
        license_source = None
    return DashboardDependency(
        name=name,
        version=package.version,
        source_url=package.resolved,
        license_id=license_id,
        license_source=license_source,
    )


def _resolve_npm_path(parent_path: str, dependency_name: str, packages: Mapping[str, _NpmPackage]) -> str:
    candidates = _npm_dependency_candidates(parent_path, dependency_name)
    for candidate in candidates:
        if candidate in packages:
            return candidate
    message = (
        f"Dashboard lockfile has no package entry for runtime dependency {dependency_name!r} "
        f"required by {parent_path or '<root>'}; candidates: {', '.join(candidates)}"
    )
    raise ReleaseDependencyError(message)


def _npm_dependency_candidates(parent_path: str, dependency_name: str) -> tuple[str, ...]:
    relative_name = "/".join(("node_modules", *dependency_name.split("/")))
    if not parent_path:
        return (relative_name,)

    candidates = [f"{parent_path}/{relative_name}"]
    candidates.extend(
        f"{scope}/{relative_name}" if scope else relative_name for scope in _npm_package_scopes(parent_path)
    )
    return tuple(candidates)


def _npm_package_scopes(package_path: str) -> tuple[str, ...]:
    package_names = package_path.removeprefix("node_modules/").split("/node_modules/")
    scopes = [""]
    for index in range(1, len(package_names)):
        scopes.append("node_modules/" + "/node_modules/".join(package_names[:index]))
    return tuple(reversed(scopes))


def _npm_package_name(package_path: str, package: _NpmPackage) -> str:
    if package.name is not None:
        return package.name
    return package_path.removesuffix("/node_modules").split("node_modules/")[-1]


def _python_source_url(package: _LockPackage) -> str | None:
    if package.source is None:
        return None
    return package.source.url or package.source.registry


def _canonical_python_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()
