from __future__ import annotations

import hashlib
import json
import tarfile
import zipfile
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Annotated, ClassVar, Never, override
from urllib.parse import quote

import typer
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from antigravity_k import __version__
from antigravity_k.engine.release_dependencies import (
    DashboardDependency,
    DashboardRuntimeDependencies,
    PythonDependency,
    PythonRuntimeDependencies,
    dashboard_runtime_dependencies,
    python_runtime_dependencies,
)


@dataclass(frozen=True, slots=True)
class ReleaseSbomError(ValueError):
    reason: str

    @override
    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class ReleaseDocuments:
    python_sbom: Path
    dashboard_sbom: Path
    notices: Path
    release_root: Path

    def __iter__(self) -> Iterator[Path]:
        return iter((self.python_sbom, self.dashboard_sbom, self.notices))


class _SbomComponent(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="allow")

    name: str


class _SbomDocument(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="allow")

    components: tuple[_SbomComponent, ...]


class _SupplyChainManifest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    artifacts: dict[str, str]
    documents: dict[str, str]


def generate_release_documents(project_root: Path) -> ReleaseDocuments:
    release_root = project_root / "src" / "antigravity_k" / "release"
    python = python_runtime_dependencies(project_root)
    dashboard = dashboard_runtime_dependencies(project_root)
    try:
        release_root.mkdir(parents=True, exist_ok=True)
        _write_json(release_root / "python.cdx.json", _python_sbom(python))
        _write_json(release_root / "dashboard.cdx.json", _dashboard_sbom(dashboard))
        _ = (release_root / "THIRD_PARTY_NOTICES.txt").write_text(
            _notices(python.dependencies, dashboard.dependencies),
            encoding="utf-8",
            newline="\n",
        )
    except OSError as error:
        raise ReleaseSbomError(f"Could not write release documents: {release_root}") from error
    return ReleaseDocuments(
        python_sbom=release_root / "python.cdx.json",
        dashboard_sbom=release_root / "dashboard.cdx.json",
        notices=release_root / "THIRD_PARTY_NOTICES.txt",
        release_root=release_root,
    )


def verify_release_bundle(*, distribution_root: Path, release_root: Path) -> Path:
    wheels = sorted(distribution_root.glob("*.whl"))
    sdists = sorted(distribution_root.glob("*.tar.gz"))
    if not wheels and not sdists:
        raise ReleaseSbomError(f"Distribution root has no wheel or sdist: {distribution_root}")
    documents = _release_documents(release_root)
    for document in documents:
        payload = document.read_bytes()
        for wheel in wheels:
            _verify_wheel_document(wheel, f"antigravity_k/release/{document.name}", payload, document.name)
        for sdist in sdists:
            prefix = sdist.name.removesuffix(".tar.gz")
            member = f"{prefix}/src/antigravity_k/release/{document.name}"
            _verify_sdist_document(sdist, member, payload, document.name)
    return _write_supply_chain_manifest(distribution_root, documents, (*wheels, *sdists))


def _python_sbom(python: PythonRuntimeDependencies) -> dict[str, object]:
    components: list[dict[str, object]] = [_application_component()]
    components.extend(_python_component(dependency) for dependency in python.dependencies)
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "component": _application_component(),
            "properties": [
                {"name": "agk:lockfile", "value": "uv.lock"},
                {"name": "agk:excluded-extras", "value": ",".join(python.excluded_extras)},
            ],
        },
        "components": components,
    }


def _dashboard_sbom(dashboard: DashboardRuntimeDependencies) -> dict[str, object]:
    root = {
        "bom-ref": "pkg:npm/antigravity-k-dashboard-react@0.1.0",
        "type": "application",
        "name": dashboard.root_name,
        "version": dashboard.root_version,
    }
    components = [root, *(_dashboard_component(dependency) for dependency in dashboard.dependencies)]
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {"component": root},
        "components": components,
    }


def _application_component() -> dict[str, object]:
    return {
        "bom-ref": f"pkg:pypi/antigravity-k@{quote(__version__)}",
        "type": "application",
        "name": "antigravity-k",
        "version": __version__,
        "licenses": [{"license": {"id": "MIT"}}],
    }


def _python_component(dependency: PythonDependency) -> dict[str, object]:
    component: dict[str, object] = {
        "bom-ref": f"pkg:pypi/{quote(dependency.name)}@{quote(dependency.version)}",
        "type": "library",
        "name": dependency.name,
        "version": dependency.version,
        "purl": f"pkg:pypi/{quote(dependency.name)}@{quote(dependency.version)}",
    }
    license_id = _python_license_id(dependency.name)
    if license_id is not None:
        component["licenses"] = [{"license": {"id": license_id}}]
    if dependency.source_url is not None:
        component["externalReferences"] = [{"type": "distribution", "url": dependency.source_url}]
    return component


def _dashboard_component(dependency: DashboardDependency) -> dict[str, object]:
    component: dict[str, object] = {
        "bom-ref": f"pkg:npm/{quote(dependency.name)}@{quote(dependency.version)}",
        "type": "library",
        "name": dependency.name,
        "version": dependency.version,
        "purl": f"pkg:npm/{quote(dependency.name)}@{quote(dependency.version)}",
    }
    if dependency.license_id is not None:
        component["licenses"] = [{"license": {"id": dependency.license_id}}]
    if dependency.license_source == "provenance-declared":
        # 출처를 숨기지 않는다: lock의 license 필드가 아니라 provenance 정책의
        # 명시 승인으로 채워진 값임을 SBOM 소비자(audit gate 포함)가 알 수 있게 한다.
        component["properties"] = [{"name": "agk:license-source", "value": "provenance-declared"}]
    if dependency.source_url is not None:
        component["externalReferences"] = [{"type": "distribution", "url": dependency.source_url}]
    return component


def _notices(
    python_dependencies: Iterable[PythonDependency],
    dashboard_dependencies: Iterable[DashboardDependency],
) -> str:
    lines = [
        "Ssak-Ai third-party notices",
        "",
        "Project license: MIT",
        "Dependency scope: runtime dependency closure; dev dependencies excluded",
        "",
        "Python dependencies (uv.lock):",
    ]
    for python_dep in python_dependencies:
        lines.append(f"- {python_dep.name} {python_dep.version} — {_python_license(python_dep.name)}")
    lines.extend(("", "Dashboard dependencies (dashboard/package-lock.json):"))
    for dashboard_dep in dashboard_dependencies:
        license_id = dashboard_dep.license_id or "license metadata unavailable"
        if dashboard_dep.license_source == "provenance-declared":
            license_id = f"{license_id} (provenance-declared — THIRD_PARTY_PROVENANCE.toml)"
        lines.append(f"- {dashboard_dep.name} {dashboard_dep.version} — {license_id}")
    lines.extend(("", "Missing license or notice metadata is reported explicitly and never synthesized."))
    return "\n".join(lines) + "\n"


def _sbom_component_count(sbom_path: Path) -> int:
    try:
        document = TypeAdapter(_SbomDocument).validate_json(sbom_path.read_bytes())
    except (OSError, ValidationError) as error:
        raise ReleaseSbomError(f"Could not count release SBOM components: {sbom_path}") from error
    return len(document.components)


# REL-03 — 설치된 패키지 메타데이터의 License 필드/분류기를 SPDX id로 정규화.
# 메타데이터를 합성하지 않는다: 정확 일치 별명만 SPDX id로 대응하고,
# 판독 불가면 None을 반환해 gate가 unknown으로 보고하게 둔다.
_PYTHON_LICENSE_ALIASES = {
    "MIT": "MIT",
    "MIT License": "MIT",
    "Apache-2.0": "Apache-2.0",
    "Apache License 2.0": "Apache-2.0",
    "Apache License, Version 2.0": "Apache-2.0",
    "Apache Software License": "Apache-2.0",
    "Apache 2.0": "Apache-2.0",
    "BSD-3-Clause": "BSD-3-Clause",
    "BSD 3-Clause License": "BSD-3-Clause",
    "BSD License": "BSD-3-Clause",
    "BSD-2-Clause": "BSD-2-Clause",
    "BSD 2-Clause License": "BSD-2-Clause",
    "ISC": "ISC",
    "ISC License (ISCL)": "ISC",
    "MPL-2.0": "MPL-2.0",
    "Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "The Unlicense (Unlicense)": "Unlicense",
    "Unlicense": "Unlicense",
    "Python Software Foundation License": "PSF-2.0",
    "PSF-2.0": "PSF-2.0",
    "Apache2.0": "Apache-2.0",
    "Zlib": "Zlib",
    "zlib": "Zlib",
    "PSF": "PSF-2.0",
}


def _python_license_id(name: str) -> str | None:
    """설치된 패키지 메타데이터에서 SPDX-compatible license id를 판독한다.

    PEP 639 License-Expression 우선, 다음으로 License 필드/License 분류기를
    별명표와 SPDX 형태 검사로 대조한다. 플랫폼 마커 패키지(colorama/pywin32,
    win32 전용)처럼 현재 플랫폼에 설치되지 않아 메타데이터가 없는 경우
    lock 자체가 provenance의 marker로 관리되므로 None을 반환한다 — gate는
    unknown으로 보고하되, 프로비넌스 정책이 marker 패키지를 허용 목록으로
    판정한다 (합성 금지 원칙 유지).
    """
    try:
        meta = metadata.metadata(name)
    except metadata.PackageNotFoundError:
        return None
    # PEP 639 License-Expression은 이미 SPDX 형식 — 정규화 없이 사용.
    expression = meta.get("License-Expression") or ""
    if expression.strip():
        return expression.strip().split(" OR ")[0].split(" AND ")[0].strip() or None
    candidates = [meta.get("License", "")]
    classifiers = meta.get_all("Classifier") or []
    candidates.extend(
        classifier.split("::")[-1].strip() for classifier in classifiers if classifier.startswith("License ::")
    )
    # 분류기 "OSI Approved :: BSD License" 등의 표기도 별명표에 넣기 전에
    # 마지막 세그먼트의 일반 축약형을 시도한다 (예: "BSD License").
    for candidate in candidates:
        alias = _PYTHON_LICENSE_ALIASES.get(candidate.strip())
        if alias is not None:
            return alias
        # License 필드가 이미 SPDX id 형태인 경우 그대로 수용 (판독 강화)
        if candidate.strip() and _looks_like_spdx(candidate.strip()):
            return candidate.strip()
    return None


def _looks_like_spdx(value: str) -> bool:
    """단일 SPDX id 형태 (알파벳+숫자+.-_)이고 알려진 접두어를 갖는다."""
    import re

    if not re.fullmatch(r"[A-Za-z0-9.+-]+", value):
        return False
    known_prefixes = (
        "MIT",
        "BSD",
        "Apache",
        "MPL",
        "GPL",
        "LGPL",
        "AGPL",
        "ISC",
        "PSF",
        "Zlib",
        "Unlicense",
        "CC",
        "Python-2",
        "OFL",
        "Ubuntu-font",
        "BlueOak",
        "Artistic",
        "CECILL",
        "EUPL",
        "MS-PL",
        "PostgreSQL",
        "Ruby",
        "WTFPL",
        "OpenSSL",
    )
    return value.startswith(known_prefixes)


def _python_license(name: str) -> str:
    """고지문에 쓸 파이썬 라이선스 표기 — SBOM 과 **같은 판독 체인**을 쓴다.

    이전에는 이 함수만 `License` 필드를 직접 읽었다. PEP 639 이후 대부분의 배포물은
    `License-Expression` 에 SPDX id를 쓰고 `License` 필드는 비워 두므로, 같은 실행의
    `python.cdx.json` 은 `MIT` 를 적는데 `THIRD_PARTY_NOTICES.txt` 는 "license metadata
    unavailable" 을 적었다(CR-14 F-03 — 실측 42건 불일치, 그중 35건은 메타데이터가
    있는데도 미상으로 적힌 판독 실패). 같은 질문에 두 산출물이 다른 답을 하면 어느 쪽도
    승인 근거가 될 수 없다.

    순서: SPDX id 판독(PEP 639 → License → 분류기 → 별명표) → 원문 `License` 필드 →
    미상 표기. 값을 합성하지 않는다 — 판독 불가는 계속 명시한다.
    """
    license_id = _python_license_id(name)
    if license_id is not None:
        return license_id
    try:
        raw = metadata.metadata(name).get("License", "") or ""
    except metadata.PackageNotFoundError:
        # 현재 플랫폼에 설치되지 않는 마커 패키지(colorama/pywin32)이 대표적인 경우다.
        # 그 집합은 저장소 정책(`marker_platform_packages`)이 관리하고
        # `tests/test_cr14_python_license_determinism.py` 가 고정한다.
        return "license metadata unavailable"
    # 원문은 여러 줄일 수 있다 — `- name version — license` 한 줄 형식을 깨지 않도록
    # 공백만 정규화한다. 자르거나 합성하지 않는다.
    return " ".join(raw.split()) or "license metadata unavailable"


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    content = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    _ = path.write_text(content, encoding="utf-8", newline="\n")


def _release_documents(release_root: Path) -> tuple[Path, ...]:
    names = ("python.cdx.json", "dashboard.cdx.json", "THIRD_PARTY_NOTICES.txt")
    documents = tuple(release_root / name for name in names)
    for document in documents:
        if not document.is_file():
            raise ReleaseSbomError(f"missing release document: {document}")
    return documents


def _verify_wheel_document(wheel: Path, member: str, expected: bytes, name: str) -> None:
    try:
        with zipfile.ZipFile(wheel) as archive:
            if member not in archive.namelist():
                raise ReleaseSbomError(f"wheel is missing release document: {name}")
            if archive.read(member) != expected:
                raise ReleaseSbomError(f"{name} does not match wheel release document")
    except (OSError, zipfile.BadZipFile) as error:
        raise ReleaseSbomError(f"Could not verify wheel: {wheel}") from error


def _verify_sdist_document(sdist: Path, member: str, expected: bytes, name: str) -> None:
    try:
        with tarfile.open(sdist, "r:gz") as archive:
            extracted = archive.extractfile(member)
            if extracted is None:
                raise ReleaseSbomError(f"sdist is missing release document: {name}")
            if extracted.read() != expected:
                raise ReleaseSbomError(f"{name} does not match sdist release document")
    except (OSError, tarfile.TarError) as error:
        raise ReleaseSbomError(f"Could not verify sdist: {sdist}") from error


def _write_supply_chain_manifest(
    distribution_root: Path,
    documents: tuple[Path, ...],
    archives: tuple[Path, ...],
) -> Path:
    payload = {
        "artifacts": {archive.name: _sha256_hex(archive) for archive in archives},
        "documents": {document.name: f"sha256-{_sha256_hex(document)}" for document in documents},
    }
    manifest = distribution_root / "release-supply-chain.json"
    _write_json(manifest, payload)
    return manifest


def _sha256_hex(path: Path) -> str:
    try:
        with path.open("rb") as handle:
            return hashlib.file_digest(handle, "sha256").hexdigest()
    except OSError as error:
        raise ReleaseSbomError(f"Could not hash release file: {path}") from error


app = typer.Typer(help="Generate and verify Ssak-Ai release SBOMs and notices.")


@app.command()
def generate(
    project_root: Annotated[Path, typer.Option("--project-root")],
    release_root: Annotated[Path, typer.Option("--release-root")],
) -> None:
    try:
        documents = generate_release_documents(project_root)
        if documents.release_root != release_root:
            raise ReleaseSbomError("The requested release root does not match the project src layout")
        python_count = _sbom_component_count(documents.python_sbom)
        dashboard_count = _sbom_component_count(documents.dashboard_sbom)
    except ReleaseSbomError as error:
        _exit_with_error(error)
    typer.echo(
        json.dumps(
            {
                "dashboard_components": dashboard_count,
                "python_components": python_count,
                "release_root": str(release_root),
                "status": "generated",
            }
        )
    )


@app.command()
def verify(
    distribution_root: Annotated[Path, typer.Option("--distribution-root")],
    release_root: Annotated[Path, typer.Option("--release-root")],
    output: Annotated[Path | None, typer.Option("--output")] = None,
) -> None:
    try:
        manifest = verify_release_bundle(distribution_root=distribution_root, release_root=release_root)
        if output is not None:
            supply_chain = TypeAdapter(_SupplyChainManifest).validate_json(manifest.read_bytes())
            _write_json(output, supply_chain.model_dump(mode="json"))
        python_count = _sbom_component_count(release_root / "python.cdx.json")
    except ReleaseSbomError as error:
        _exit_with_error(error)
    typer.echo(
        json.dumps({"manifest": str(output or manifest), "python_components": python_count, "status": "verified"})
    )


def _exit_with_error(error: ReleaseSbomError) -> Never:
    typer.echo(json.dumps({"error": str(error), "status": "error"}), err=True)
    raise typer.Exit(code=2)


if __name__ == "__main__":
    app()
