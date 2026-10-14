from __future__ import annotations

import fcntl
import os
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Literal, final, override

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from antigravity_k.finetune.artifact_lifecycle import FusedArtifactResult, FusedArtifactStatus
from antigravity_k.finetune.evaluation import EvaluationError
from antigravity_k.finetune.evaluation_gate import (
    PromotionDecision,
    load_promotion_decision_artifact,
    promotion_decision_sha256,
)
from antigravity_k.finetune.promotion_probe import (
    PromotionProbeTarget,
    RuntimeProbe,
    RuntimeProbeResult,
    RuntimeProbeStatus,
)


@final
class ActiveArtifactError(ValueError):
    __slots__: ClassVar[tuple[str, ...]] = ("reason",)
    reason: str

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason

    @override
    def __str__(self) -> str:
        return self.reason


class ActiveArtifactStatus(StrEnum):
    ACTIVE = "active"
    ROLLED_BACK = "rolled_back"


class ArtifactPromotionContract(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    recipe_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ActiveArtifactState(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    status: ActiveArtifactStatus
    base_model: str = Field(min_length=1)
    base_revision: str = Field(min_length=1)
    output_path: Path
    recipe_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    promotion_decision_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    promotion_revision: int = Field(ge=1)
    previous_output_path: Path | None = None


class FailedArtifactPromotion(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    status: Literal[ActiveArtifactStatus.ROLLED_BACK] = ActiveArtifactStatus.ROLLED_BACK
    candidate: ActiveArtifactState
    active: ActiveArtifactState | None
    probe: RuntimeProbeResult


_artifact_adapter: TypeAdapter[FusedArtifactResult] = TypeAdapter(FusedArtifactResult)
_state_adapter: TypeAdapter[ActiveArtifactState] = TypeAdapter(ActiveArtifactState)


def read_active_artifact(state_path: Path) -> ActiveArtifactState:
    try:
        state_path_is_file = state_path.is_file()
        state_path_is_symlink = state_path.is_symlink()
    except OSError as error:
        raise ActiveArtifactError("Active artifact state is unavailable.") from error
    if state_path_is_symlink or not state_path_is_file:
        raise ActiveArtifactError("Active artifact state is unavailable.")
    try:
        state = _state_adapter.validate_json(state_path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ActiveArtifactError("Active artifact state is unavailable.") from error
    except ValueError as error:
        raise ActiveArtifactError("Invalid active artifact state.") from error
    if state.status is not ActiveArtifactStatus.ACTIVE:
        raise ActiveArtifactError("Active artifact state must be active.")
    return state


def validate_active_artifact_output(state: ActiveArtifactState) -> FusedArtifactResult:
    artifact = _load_artifact(state.output_path)
    try:
        _validate_artifact(
            artifact,
            artifact_path=state.output_path,
            contract=ArtifactPromotionContract(
                recipe_sha256=state.recipe_sha256,
                evaluation_sha256=state.evaluation_sha256,
            ),
        )
        if artifact.base_model != state.base_model or artifact.base_revision != state.base_revision:
            raise ActiveArtifactError("Active artifact provenance does not match the fused manifest.")
    except OSError as error:
        raise ActiveArtifactError("Active artifact output is unavailable.") from error
    return artifact


def promote_artifact(
    artifact_path: Path,
    *,
    state_path: Path,
    contract: ArtifactPromotionContract,
    decision_path: Path,
    probe: RuntimeProbe,
) -> ActiveArtifactState | FailedArtifactPromotion:
    with _state_lock(state_path):
        previous = _read_optional_state(state_path)
        artifact = _load_artifact(artifact_path)
        _validate_artifact(artifact, artifact_path=artifact_path, contract=contract)
        try:
            decision = load_promotion_decision_artifact(decision_path)
        except EvaluationError as error:
            raise ActiveArtifactError(str(error)) from error
        _validate_decision(decision, artifact=artifact, contract=contract)
        state = ActiveArtifactState(
            status=ActiveArtifactStatus.ACTIVE,
            base_model=artifact.base_model,
            base_revision=artifact.base_revision,
            output_path=artifact_path,
            recipe_sha256=artifact.recipe_sha256,
            evaluation_sha256=artifact.evaluation_sha256,
            promotion_decision_sha256=promotion_decision_sha256(decision),
            promotion_revision=1 if previous is None else previous.promotion_revision + 1,
            previous_output_path=None if previous is None else previous.output_path,
        )
        _write_state_atomic(state_path, state)
        probe_result = probe(
            PromotionProbeTarget(
                output_path=artifact_path,
                model_name=decision.model,
            ),
        )
        if probe_result.status is RuntimeProbeStatus.PASSED:
            return state
        _restore_state(state_path, previous)
        return FailedArtifactPromotion(
            candidate=state,
            active=previous,
            probe=probe_result,
        )


def rollback_active_artifact(state_path: Path) -> ActiveArtifactState:
    with _state_lock(state_path):
        current = read_active_artifact(state_path)
        if current.previous_output_path is None:
            raise ActiveArtifactError("No previous artifact is available for rollback.")
        previous_path = current.previous_output_path
        artifact = _load_artifact(previous_path)
        _validate_artifact(
            artifact,
            artifact_path=previous_path,
            contract=ArtifactPromotionContract(
                recipe_sha256=artifact.recipe_sha256,
                evaluation_sha256=artifact.evaluation_sha256,
            ),
        )
        state = ActiveArtifactState(
            status=ActiveArtifactStatus.ACTIVE,
            base_model=artifact.base_model,
            base_revision=artifact.base_revision,
            output_path=previous_path,
            recipe_sha256=artifact.recipe_sha256,
            evaluation_sha256=artifact.evaluation_sha256,
            promotion_revision=current.promotion_revision + 1,
        )
        _write_state_atomic(state_path, state)
        return state


def _read_optional_state(state_path: Path) -> ActiveArtifactState | None:
    if not state_path.exists():
        return None
    return read_active_artifact(state_path)


def _load_artifact(artifact_path: Path) -> FusedArtifactResult:
    manifest_path = artifact_path / "artifact_manifest.json"
    try:
        artifact_path_is_directory = artifact_path.is_dir()
        artifact_path_is_symlink = artifact_path.is_symlink()
        manifest_path_is_file = manifest_path.is_file()
        manifest_path_is_symlink = manifest_path.is_symlink()
    except OSError as error:
        raise ActiveArtifactError("Active artifact output is unavailable.") from error
    if artifact_path_is_symlink:
        raise ActiveArtifactError("Active artifact output is unavailable.")
    if not artifact_path_is_directory:
        raise ActiveArtifactError("Artifact manifest is required.")
    if manifest_path_is_symlink or not manifest_path_is_file:
        raise ActiveArtifactError("Artifact manifest is required.")
    try:
        return _artifact_adapter.validate_json(manifest_path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ActiveArtifactError("Artifact manifest is unavailable.") from error
    except ValueError as error:
        raise ActiveArtifactError("Invalid artifact manifest.") from error


def _validate_artifact(
    artifact: FusedArtifactResult,
    *,
    artifact_path: Path,
    contract: ArtifactPromotionContract,
) -> None:
    if artifact.status is not FusedArtifactStatus.SUCCESS:
        raise ActiveArtifactError("Successful artifact is required for promotion.")
    if artifact.output_path.resolve() != artifact_path.resolve():
        raise ActiveArtifactError("Artifact manifest output path does not match the promoted directory.")
    if artifact.recipe_sha256 != contract.recipe_sha256:
        raise ActiveArtifactError("Artifact recipe provenance does not match the promotion contract.")
    if artifact.evaluation_sha256 != contract.evaluation_sha256:
        raise ActiveArtifactError("Artifact evaluation provenance does not match the promotion contract.")


def _validate_decision(
    decision: PromotionDecision,
    *,
    artifact: FusedArtifactResult,
    contract: ArtifactPromotionContract,
) -> None:
    if not decision.eligible:
        raise ActiveArtifactError("Promotion decision is not eligible.")
    if decision.evaluated_model != artifact.base_model or decision.model_revision != artifact.base_revision:
        raise ActiveArtifactError("Promotion decision model provenance does not match the artifact.")
    if decision.recipe_sha256 != contract.recipe_sha256:
        raise ActiveArtifactError("Promotion decision recipe provenance does not match the contract.")
    if decision.evaluation_pair_sha256 != contract.evaluation_sha256:
        raise ActiveArtifactError("Promotion decision evaluation provenance does not match the contract.")


def _restore_state(state_path: Path, previous: ActiveArtifactState | None) -> None:
    if previous is not None:
        _write_state_atomic(state_path, previous)
        return
    try:
        state_path.unlink()
    except FileNotFoundError:
        return


@contextmanager
def _state_lock(state_path: Path) -> Generator[None]:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = state_path.with_suffix(f"{state_path.suffix}.lock")
    with lock_path.open("a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _write_state_atomic(state_path: Path, state: ActiveArtifactState) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=state_path.parent,
        prefix=f".{state_path.name}.",
        delete=False,
    ) as temporary:
        temporary_name = temporary.name
        _ = temporary.write(state.model_dump_json(indent=2) + "\n")
        temporary.flush()
        os.fsync(temporary.fileno())
    try:
        os.replace(temporary_name, state_path)
    except OSError:
        os.unlink(temporary_name)
        raise
