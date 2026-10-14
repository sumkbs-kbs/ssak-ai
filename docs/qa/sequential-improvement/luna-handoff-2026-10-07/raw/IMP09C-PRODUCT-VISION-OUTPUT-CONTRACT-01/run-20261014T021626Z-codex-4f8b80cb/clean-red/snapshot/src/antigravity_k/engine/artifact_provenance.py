from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Annotated, ClassVar, Literal, Never, Protocol, override

import typer
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


def _validate_relative_path(value: str, *, allow_root: bool) -> str:
    path = PurePosixPath(value)
    if "\\" in value or path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise ArtifactProvenanceError("Artifact paths must be normalized relative POSIX paths.")
    if not allow_root and value == ".":
        raise ArtifactProvenanceError("Artifact file paths cannot name the root directory.")
    return value


class ArtifactRecord(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(min_length=1)
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return _validate_relative_path(value, allow_root=False)


class ArtifactManifest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    algorithm: Literal["sha256"] = "sha256"
    selection: tuple[str, ...] = Field(min_length=1)
    artifacts: tuple[ArtifactRecord, ...] = Field(min_length=1)

    @field_validator("selection")
    @classmethod
    def validate_selection(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(_validate_relative_path(path, allow_root=True) for path in value)
        if normalized != tuple(sorted(set(normalized))):
            raise ArtifactProvenanceError("Artifact selections must be sorted and unique.")
        return normalized

    @field_validator("artifacts")
    @classmethod
    def validate_artifacts(cls, value: tuple[ArtifactRecord, ...]) -> tuple[ArtifactRecord, ...]:
        paths = tuple(record.path for record in value)
        if paths != tuple(sorted(set(paths))):
            raise ArtifactProvenanceError("Artifact records must be sorted and unique.")
        return value


class VerificationIssue(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["missing", "unexpected", "size_mismatch", "sha256_mismatch"]
    path: str = Field(min_length=1)


class VerificationReport(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    valid: bool
    checked: int = Field(ge=0)
    issues: tuple[VerificationIssue, ...] = ()


@dataclass(frozen=True, slots=True)
class ArtifactProvenanceError(ValueError):
    reason: str

    @override
    def __str__(self) -> str:
        return self.reason


ArtifactSource = Literal["build", "ui_bundle", "sandbox_mount", "workspace"]


class ArtifactEventStore(Protocol):
    def append_execution_event(self, task_id: str, event_type: str, payload_json: str) -> int: ...


@dataclass(frozen=True, slots=True)
class ArtifactProvenanceEvent:
    task_id: str
    source: ArtifactSource
    digest: str
    sequence: int


def manifest_digest(manifest: ArtifactManifest) -> str:
    payload = manifest.model_dump_json(exclude_none=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def record_manifest_event(
    store: ArtifactEventStore,
    task_id: str,
    manifest: ArtifactManifest,
    *,
    source: ArtifactSource = "workspace",
) -> ArtifactProvenanceEvent:
    digest = manifest_digest(manifest)
    payload = json.dumps(
        {"digest": digest, "manifest": manifest.model_dump(mode="json"), "source": source},
        ensure_ascii=False,
        sort_keys=True,
    )
    sequence = store.append_execution_event(task_id, "artifact.provenance.recorded", payload)
    return ArtifactProvenanceEvent(task_id=task_id, source=source, digest=digest, sequence=sequence)


def create_manifest(
    root: Path,
    inputs: Sequence[Path],
    *,
    excluded_paths: Sequence[Path] = (),
) -> ArtifactManifest:
    resolved_root = _resolve_root(root)
    selections, files = _collect_files(resolved_root, inputs, excluded_paths, allow_missing=False)
    if not files:
        raise ArtifactProvenanceError("The artifact selection contains no regular files.")
    records = tuple(
        ArtifactRecord(path=relative, size_bytes=path.stat().st_size, sha256=_sha256(path))
        for relative, path in sorted(files.items())
    )
    return ArtifactManifest(selection=selections, artifacts=records)


def verify_manifest(
    root: Path,
    manifest: ArtifactManifest,
    *,
    excluded_paths: Sequence[Path] = (),
) -> VerificationReport:
    resolved_root = _resolve_root(root)
    _, current = _collect_files(
        resolved_root,
        tuple(Path(path) for path in manifest.selection),
        excluded_paths,
        allow_missing=True,
    )
    expected = {record.path: record for record in manifest.artifacts}
    issues: list[VerificationIssue] = []
    for path in current.keys() - expected.keys():
        issues.append(VerificationIssue(kind="unexpected", path=path))
    for path in expected.keys() - current.keys():
        issues.append(VerificationIssue(kind="missing", path=path))
    for path in current.keys() & expected.keys():
        actual = current[path]
        record = expected[path]
        if actual.stat().st_size != record.size_bytes:
            issues.append(VerificationIssue(kind="size_mismatch", path=path))
        elif _sha256(actual) != record.sha256:
            issues.append(VerificationIssue(kind="sha256_mismatch", path=path))
    ordered = tuple(sorted(issues, key=lambda issue: (issue.path, issue.kind)))
    return VerificationReport(valid=not ordered, checked=len(current.keys() & expected.keys()), issues=ordered)


def write_manifest(path: Path, manifest: ArtifactManifest) -> None:
    payload = manifest.model_dump_json(indent=2) + "\n"
    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            _ = handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        _ = temporary_path.replace(path)
    except OSError as error:
        raise ArtifactProvenanceError(f"Could not write artifact manifest: {path}") from error
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def load_manifest(path: Path) -> ArtifactManifest:
    try:
        return ArtifactManifest.model_validate_json(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ArtifactProvenanceError(f"Could not read artifact manifest: {path}") from error
    except ValidationError as error:
        raise ArtifactProvenanceError(f"Invalid artifact manifest: {path}") from error


def _resolve_root(root: Path) -> Path:
    try:
        resolved = root.resolve(strict=True)
    except OSError as error:
        raise ArtifactProvenanceError(f"Artifact root is unavailable: {root}") from error
    if not resolved.is_dir():
        raise ArtifactProvenanceError(f"Artifact root is not a directory: {root}")
    return resolved


def _collect_files(
    root: Path,
    inputs: Sequence[Path],
    excluded_paths: Sequence[Path],
    *,
    allow_missing: bool,
) -> tuple[tuple[str, ...], dict[str, Path]]:
    if not inputs:
        raise ArtifactProvenanceError("At least one artifact path is required.")
    excluded = frozenset(_resolve_candidate(root, path, strict=False) for path in excluded_paths)
    selections: set[str] = set()
    files: dict[str, Path] = {}
    for input_path in inputs:
        candidate = _resolve_candidate(root, input_path, strict=not allow_missing)
        selections.add(_relative_name(root, candidate, allow_root=True))
        if not candidate.exists() and allow_missing:
            continue
        if candidate.is_symlink():
            raise ArtifactProvenanceError(f"Symbolic links are not allowed in artifact selections: {input_path}")
        descendants = (candidate,) if candidate.is_file() else tuple(candidate.rglob("*"))
        for path in descendants:
            if path.is_symlink():
                raise ArtifactProvenanceError(f"Symbolic links are not allowed in artifact selections: {path}")
            if path.is_file() and path.resolve() not in excluded:
                files[_relative_name(root, path.resolve(), allow_root=False)] = path.resolve()
    return tuple(sorted(selections)), files


def _resolve_candidate(root: Path, candidate: Path, *, strict: bool) -> Path:
    unresolved = candidate if candidate.is_absolute() else root / candidate
    try:
        resolved = unresolved.resolve(strict=strict)
        _ = resolved.relative_to(root)
    except FileNotFoundError as error:
        raise ArtifactProvenanceError(f"Artifact path is unavailable: {candidate}") from error
    except ValueError as error:
        raise ArtifactProvenanceError(f"Artifact path is outside the artifact root: {candidate}") from error
    return resolved


def _relative_name(root: Path, path: Path, *, allow_root: bool) -> str:
    value = path.relative_to(root).as_posix() or "."
    return _validate_relative_path(value, allow_root=allow_root)


def _sha256(path: Path) -> str:
    try:
        with path.open("rb") as handle:
            return hashlib.file_digest(handle, "sha256").hexdigest()
    except OSError as error:
        raise ArtifactProvenanceError(f"Could not hash artifact file: {path}") from error


app = typer.Typer(no_args_is_help=True, help="Create and verify SHA-256 artifact provenance manifests.")


@app.command("create")
def create_command(
    paths: Annotated[list[Path], typer.Argument(help="Files or directories relative to the artifact root.")],
    root: Annotated[Path | None, typer.Option("--root", help="Artifact root directory.")] = None,
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Manifest output path.")] = None,
) -> None:
    root_path = root if root is not None else Path(".")
    requested_output = output if output is not None else Path("artifact-provenance.json")
    output_path = requested_output if requested_output.is_absolute() else root_path / requested_output
    try:
        manifest = create_manifest(root_path, paths, excluded_paths=(output_path,))
        write_manifest(output_path, manifest)
    except ArtifactProvenanceError as error:
        _exit_with_error(error)
    typer.echo(
        json.dumps({"artifact_count": len(manifest.artifacts), "manifest": str(output_path), "status": "created"})
    )


@app.command("verify")
def verify_command(
    manifest_path: Annotated[Path, typer.Argument(help="Manifest to verify.")],
    root: Annotated[Path | None, typer.Option("--root", help="Artifact root directory.")] = None,
) -> None:
    root_path = root if root is not None else Path(".")
    try:
        manifest = load_manifest(manifest_path)
        report = verify_manifest(root_path, manifest, excluded_paths=(manifest_path,))
    except ArtifactProvenanceError as error:
        _exit_with_error(error)
    typer.echo(report.model_dump_json(indent=2))
    if not report.valid:
        raise typer.Exit(code=1)


def _exit_with_error(error: ArtifactProvenanceError) -> Never:
    typer.echo(json.dumps({"error": str(error), "status": "error"}), err=True)
    raise typer.Exit(code=2)


if __name__ == "__main__":
    app()
