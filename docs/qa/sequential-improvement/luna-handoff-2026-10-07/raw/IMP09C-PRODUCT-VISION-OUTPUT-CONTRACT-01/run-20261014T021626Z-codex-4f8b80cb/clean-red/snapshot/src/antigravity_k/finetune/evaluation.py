from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Literal, override

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


@dataclass(frozen=True, slots=True)
class EvaluationError(ValueError):
    reason: str

    @override
    def __str__(self) -> str:
        return self.reason


class CandidateKind(StrEnum):
    BASE = "base"
    TUNED = "tuned"


class EvaluationDataset(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    path: Path
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    case_ids: tuple[str, ...] = Field(min_length=1)


class FrozenEvaluationManifest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="allow")

    schema_version: Literal[1]
    dataset_path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    row_count: int = Field(ge=1)


class CandidateEvaluation(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    kind: CandidateKind
    model: str = Field(min_length=1)
    model_revision: str = Field(min_length=1)
    adapter_path: Path | None = None
    recipe_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    case_ids: tuple[str, ...] = Field(min_length=1)
    scores: tuple[float, ...] = Field(min_length=1)
    environment: dict[str, str]


class EvaluationPair(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    dataset: EvaluationDataset
    base: CandidateEvaluation
    tuned: CandidateEvaluation


_PAIR_CANONICAL_FIELDS = {
    "kind",
    "model",
    "model_revision",
    "adapter_path",
    "recipe_sha256",
    "case_ids",
    "environment",
}
_FROZEN_DATASET_NAMES = {"held_out_v1.jsonl", "held_out_v2.jsonl"}


def evaluation_pair_sha256(pair: EvaluationPair) -> str:
    _validate_pair(pair)
    canonical = {
        "dataset": pair.dataset.model_dump(mode="json"),
        "base": pair.base.model_dump(mode="json", include=_PAIR_CANONICAL_FIELDS),
        "tuned": pair.tuned.model_dump(mode="json", include=_PAIR_CANONICAL_FIELDS),
    }
    return hashlib.sha256(json_canonical(canonical).encode("utf-8")).hexdigest()


def load_evaluation_pair(path: Path, *, model: str, model_revision: str) -> EvaluationPair:
    try:
        pair = TypeAdapter(EvaluationPair).validate_json(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise EvaluationError(f"Invalid evaluation result at {path}: {error}") from error
    _validate_pair(pair)
    _validate_provenance(pair, model=model, model_revision=model_revision)
    return pair


def evaluate_candidates(
    *,
    dataset: EvaluationDataset,
    model: str,
    model_revision: str,
    adapter_path: Path,
    recipe_sha256: str,
    environment: dict[str, str],
    inference: Callable[[EvaluationCase, CandidateKind], str],
) -> EvaluationPair:
    cases = _load_cases(dataset)
    base_scores = tuple(_case_score(case, inference(case, CandidateKind.BASE)) for case in cases)
    tuned_scores = tuple(_case_score(case, inference(case, CandidateKind.TUNED)) for case in cases)
    return EvaluationPair(
        dataset=dataset,
        base=CandidateEvaluation(
            kind=CandidateKind.BASE,
            model=model,
            model_revision=model_revision,
            case_ids=dataset.case_ids,
            environment=environment,
            scores=base_scores,
        ),
        tuned=CandidateEvaluation(
            kind=CandidateKind.TUNED,
            model=model,
            model_revision=model_revision,
            adapter_path=adapter_path,
            recipe_sha256=recipe_sha256,
            case_ids=dataset.case_ids,
            environment=environment,
            scores=tuned_scores,
        ),
    )


def _load_cases(dataset: EvaluationDataset) -> tuple[EvaluationCase, ...]:
    cases = tuple(
        EvaluationCase.model_validate_json(line)
        for line in dataset.path.read_text(encoding="utf-8").splitlines()
        if line
    )
    if tuple(case.id for case in cases) != dataset.case_ids:
        raise EvaluationError("Evaluation case IDs must match the frozen dataset order.")
    return cases


def _case_score(case: EvaluationCase, output: str) -> float:
    if case.expected_output:
        return 1.0 if case.expected_output in output else 0.0
    keywords = case.expected_keywords
    return sum(keyword.lower() in output.lower() for keyword in keywords) / len(keywords)


def _validate_pair(pair: EvaluationPair) -> None:
    if pair.dataset.path.name not in _FROZEN_DATASET_NAMES:
        raise EvaluationError("Evaluation dataset must be a supported frozen held-out version.")
    if pair.dataset.sha256 != hashlib.sha256(pair.dataset.path.read_bytes()).hexdigest():
        raise EvaluationError("Evaluation dataset digest does not match the frozen file.")
    case_count = len(pair.dataset.case_ids)
    _validate_freeze_manifest(pair.dataset, case_count=case_count)
    if len(set(pair.dataset.case_ids)) != case_count:
        raise EvaluationError("Evaluation dataset must contain unique held-out case IDs.")
    if pair.base.case_ids != pair.dataset.case_ids or pair.tuned.case_ids != pair.dataset.case_ids:
        raise EvaluationError("Base and tuned evaluations must cover the same held-out cases.")
    if len(pair.base.scores) != case_count or len(pair.tuned.scores) != case_count:
        raise EvaluationError("Base and tuned evaluation scores must align to held-out case IDs.")
    if any(not _case_forbids_training(pair.dataset.path, case_id) for case_id in pair.dataset.case_ids):
        raise EvaluationError("Every evaluation case must be forbidden for training.")
    if pair.base.kind is not CandidateKind.BASE or pair.tuned.kind is not CandidateKind.TUNED:
        raise EvaluationError("Evaluation pair requires one base and one tuned candidate.")
    if pair.base.adapter_path is not None or pair.base.recipe_sha256 is not None:
        raise EvaluationError("Base evaluation must not carry tuned adapter provenance.")
    if pair.tuned.adapter_path is None or pair.tuned.recipe_sha256 is None:
        raise EvaluationError("Tuned evaluation requires adapter and recipe provenance.")


def _validate_freeze_manifest(dataset: EvaluationDataset, *, case_count: int) -> None:
    freeze_path = dataset.path.with_suffix(".freeze.json")
    try:
        manifest = FrozenEvaluationManifest.model_validate_json(freeze_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise EvaluationError("Evaluation freeze manifest is invalid or unavailable.") from error
    if Path(manifest.dataset_path).name != dataset.path.name:
        raise EvaluationError("Evaluation freeze manifest names a different dataset.")
    if manifest.sha256 != dataset.sha256:
        raise EvaluationError("Evaluation dataset digest does not match the freeze manifest.")
    if manifest.row_count != case_count:
        raise EvaluationError("Evaluation case count does not match the freeze manifest.")


def _case_forbids_training(dataset_path: Path, case_id: str) -> bool:
    for line in dataset_path.read_text(encoding="utf-8").splitlines():
        row = HeldOutCase.model_validate_json(line)
        if row.id == case_id:
            return row.forbidden_for_training
    return False


def _validate_provenance(pair: EvaluationPair, *, model: str, model_revision: str) -> None:
    if pair.base.model != model or pair.tuned.model != model:
        raise EvaluationError("Evaluation candidates must use the training base model.")
    if pair.base.model_revision != model_revision or pair.tuned.model_revision != model_revision:
        raise EvaluationError("Evaluation candidates must use the same base model revision.")


def json_canonical(value: dict[str, dict[str, str | Path | tuple[str, ...] | None]]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class HeldOutCase(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="allow")

    id: str
    forbidden_for_training: bool


class EvaluationCase(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="allow")

    id: str
    category: str
    prompt: str
    expected_keywords: tuple[str, ...]
    expected_output: str = ""
    forbidden_for_training: bool
