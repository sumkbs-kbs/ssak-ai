from __future__ import annotations

import json
import re
import tarfile
import zipfile
from dataclasses import dataclass
from email import policy
from email.message import Message
from email.parser import BytesParser
from email.policy import Policy
from pathlib import Path
from typing import Annotated, Never, cast, override

import typer

from antigravity_k import __version__


@dataclass(frozen=True, slots=True)
class ReleaseMetadataError(ValueError):
    reason: str

    @override
    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class ReleaseMetadata:
    version: str
    source_version: str
    wheel: Path
    sdist: Path

    def as_json(self) -> str:
        return json.dumps(
            {
                "sdist": self.sdist.name,
                "source_version": self.source_version,
                "version": self.version,
                "wheel": self.wheel.name,
            },
            sort_keys=True,
            separators=(",", ":"),
        )


def verify_release_metadata(
    *,
    distribution_root: Path,
    source_version: str,
    git_ref: str,
) -> ReleaseMetadata:
    wheel = _single_archive(distribution_root, "*.whl", "wheel")
    sdist = _single_archive(distribution_root, "*.tar.gz", "sdist")
    wheel_name, wheel_filename_version = _parse_wheel_filename(wheel.name)
    sdist_name, sdist_filename_version = _parse_sdist_filename(sdist.name)
    _validate_project_name(wheel_name, "wheel filename")
    _validate_project_name(sdist_name, "sdist filename")

    wheel_metadata = _read_metadata(wheel)
    sdist_metadata = _read_metadata(sdist)
    _validate_project_name(wheel_metadata.name, "wheel metadata")
    _validate_project_name(sdist_metadata.name, "sdist metadata")
    _validate_version(
        actual=wheel_metadata.version,
        expected=wheel_filename_version,
        label=f"wheel version {wheel_metadata.version}",
        expected_label=f"wheel filename {wheel_filename_version}",
    )
    _validate_version(
        actual=sdist_metadata.version,
        expected=wheel_metadata.version,
        label=f"sdist version {sdist_metadata.version}",
        expected_label=f"wheel version {wheel_metadata.version}",
    )
    _validate_version(
        actual=sdist_filename_version,
        expected=wheel_metadata.version,
        label=f"sdist filename {sdist_filename_version}",
        expected_label=f"wheel version {wheel_metadata.version}",
    )
    _validate_version(
        actual=source_version,
        expected=wheel_metadata.version,
        label=f"source package version {source_version}",
        expected_label=f"wheel version {wheel_metadata.version}",
    )
    _validate_tag(git_ref=git_ref, version=wheel_metadata.version)
    return ReleaseMetadata(
        version=wheel_metadata.version,
        source_version=source_version,
        wheel=wheel,
        sdist=sdist,
    )


@dataclass(frozen=True, slots=True)
class _ArchiveMetadata:
    name: str
    version: str


def _single_archive(root: Path, pattern: str, kind: str) -> Path:
    matches = sorted(root.glob(pattern))
    if len(matches) != 1:
        raise ReleaseMetadataError(f"Distribution root must contain exactly one {kind}: {root}")
    archive = matches[0]
    if archive.is_symlink() or not archive.is_file():
        raise ReleaseMetadataError(f"Distribution {kind} is not a regular file: {archive}")
    return archive


def _parse_wheel_filename(filename: str) -> tuple[str, str]:
    match = re.fullmatch(r"antigravity[_-]k-(?P<version>[^-]+)-[^-]+-[^-]+-[^-]+\.whl", filename)
    if match is None:
        raise ReleaseMetadataError(f"Invalid wheel filename: {filename}")
    return "antigravity-k", match.group("version")


def _parse_sdist_filename(filename: str) -> tuple[str, str]:
    match = re.fullmatch(r"antigravity[_-]k-(?P<version>[^-]+)\.tar\.gz", filename)
    if match is None:
        raise ReleaseMetadataError(f"Invalid sdist filename: {filename}")
    return "antigravity-k", match.group("version")


def _read_metadata(archive: Path) -> _ArchiveMetadata:
    if archive.suffix == ".whl":
        metadata_bytes = _read_wheel_metadata(archive)
    else:
        metadata_bytes = _read_sdist_metadata(archive)
    # policy.default(EmailPolicy[EmailMessage])는 typeshed 기본 BytesParser
    # 오버로드(Policy[Message[str, str]])와 타입이 어긋난다 — 런타임 동작은
    # 동일하므로 cast로 오버로드만 정렬한다 (mypy 1.14+, 2026-09-06).
    headers = BytesParser(policy=cast("Policy[Message[str, str]]", policy.default)).parsebytes(metadata_bytes)
    names = tuple(headers.get_all("Name") or ())
    versions = tuple(headers.get_all("Version") or ())
    if len(names) != 1 or len(versions) != 1 or not names[0] or not versions[0]:
        raise ReleaseMetadataError(f"Distribution metadata must contain one Name and Version: {archive.name}")
    return _ArchiveMetadata(
        name=_canonical_name(_header_value(names)),
        version=_header_value(versions),
    )


def _header_value(values: tuple[str, ...]) -> str:
    if len(values) != 1 or not values[0]:
        raise ReleaseMetadataError("Distribution metadata must contain one Name and Version")
    return values[0]


def _read_wheel_metadata(wheel: Path) -> bytes:
    try:
        with zipfile.ZipFile(wheel) as archive:
            members = [name for name in archive.namelist() if name.endswith("/METADATA")]
            if len(members) != 1:
                raise ReleaseMetadataError(f"Wheel must contain exactly one METADATA entry: {wheel.name}")
            return archive.read(members[0])
    except (OSError, zipfile.BadZipFile) as error:
        raise ReleaseMetadataError(f"Could not read wheel metadata: {wheel}") from error


def _read_sdist_metadata(sdist: Path) -> bytes:
    try:
        with tarfile.open(sdist, "r:gz") as archive:
            prefix = sdist.name.removesuffix(".tar.gz")
            member = f"{prefix}/PKG-INFO"
            extracted = archive.extractfile(member)
            if extracted is None:
                raise ReleaseMetadataError(f"Could not read sdist PKG-INFO: {sdist.name}")
            return extracted.read()
    except (OSError, tarfile.TarError) as error:
        raise ReleaseMetadataError(f"Could not read sdist metadata: {sdist}") from error


def _canonical_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _validate_project_name(actual: str, origin: str) -> None:
    expected = "antigravity-k"
    if actual != expected:
        raise ReleaseMetadataError(f"Invalid project name in {origin}: expected {expected}, got {actual}")


def _validate_version(*, actual: str, expected: str, label: str, expected_label: str) -> None:
    if actual != expected:
        raise ReleaseMetadataError(f"{label} does not match {expected_label}")


def _validate_tag(*, git_ref: str, version: str) -> None:
    match = re.fullmatch(r"refs/tags/v(.+)", git_ref)
    if match is None:
        return
    tag_version = match.group(1)
    if not tag_version:
        raise ReleaseMetadataError(f"Release tag has no version: {git_ref}")
    _validate_version(
        actual=tag_version,
        expected=version,
        label=f"tag version {tag_version}",
        expected_label=f"wheel version {version}",
    )


app = typer.Typer(help="Verify versions in built Ssak-Ai release artifacts.")


@app.command()
def verify(
    distribution_root: Annotated[Path, typer.Option("--distribution-root")],
    git_ref: Annotated[str, typer.Option("--git-ref")],
) -> None:
    try:
        metadata = verify_release_metadata(
            distribution_root=distribution_root,
            source_version=__version__,
            git_ref=git_ref,
        )
    except ReleaseMetadataError as error:
        _exit_with_error(error)
    typer.echo(metadata.as_json())


def _exit_with_error(error: ReleaseMetadataError) -> Never:
    typer.echo(json.dumps({"error": str(error), "status": "error"}, sort_keys=True), err=True)
    raise typer.Exit(code=2)


if __name__ == "__main__":
    app()
