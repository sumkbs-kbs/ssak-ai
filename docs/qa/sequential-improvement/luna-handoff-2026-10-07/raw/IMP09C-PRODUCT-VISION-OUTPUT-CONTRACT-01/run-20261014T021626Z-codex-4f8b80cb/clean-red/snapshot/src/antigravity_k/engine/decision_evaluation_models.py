from __future__ import annotations

from typing import Annotated, ClassVar, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from pydantic_core import PydanticCustomError

type DecisionKey = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=128, pattern=r"\S")]
type Probability = Annotated[float, Field(strict=True, allow_inf_nan=False, ge=0, le=1)]


class _EvaluationModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class _TaggedCase(_EvaluationModel):
    tags: Annotated[tuple[DecisionKey, ...], Field(max_length=16)] = ()

    @model_validator(mode="after")
    def validate_tags(self) -> Self:
        if len(set(self.tags)) != len(self.tags):
            raise PydanticCustomError("duplicate_tags", "Case tags must be unique")
        return self


class DecisionPrediction(_TaggedCase):
    case_id: DecisionKey
    status: Literal["prediction"]
    options: Annotated[tuple[DecisionKey, ...], Field(min_length=2, max_length=64)]
    probabilities: Annotated[tuple[Probability, ...], Field(min_length=2, max_length=64)]
    expected_key: DecisionKey | None = None
    underdetermined: Annotated[bool, Field(strict=True)] = False

    @model_validator(mode="after")
    def validate_prediction(self) -> Self:
        if len(self.options) != len(self.probabilities):
            raise PydanticCustomError("probability_shape", "Option and probability counts must match")
        if len(set(self.options)) != len(self.options):
            raise PydanticCustomError("duplicate_options", "Option keys must be unique")
        if self.underdetermined and self.expected_key is not None:
            raise PydanticCustomError("ambiguous_truth", "Underdetermined cases cannot include a truth label")
        return self


class DecisionError(_TaggedCase):
    case_id: DecisionKey
    status: Literal["error"]
    error_code: Literal["provider_error", "timeout", "invalid_response"]


type DecisionCase = Annotated[DecisionPrediction | DecisionError, Field(discriminator="status")]


class DecisionEvaluationRequest(_EvaluationModel):
    model_id: DecisionKey | None = None
    dataset_id: DecisionKey | None = None
    risk_budget: Probability = 0.05
    cases: Annotated[tuple[DecisionCase, ...], Field(max_length=1000)] = ()

    @model_validator(mode="after")
    def validate_case_ids(self) -> Self:
        if len({case.case_id for case in self.cases}) != len(self.cases):
            raise PydanticCustomError("duplicate_cases", "Case identifiers must be unique")
        return self


class DecisionEvaluationCounts(_EvaluationModel):
    total: int
    predictions: int
    errors: int
    strict_valid: int
    lenient_valid: int
    invalid_sum: int
    scored: int
    unlabeled: int
    missing_expected_label: int
    underdetermined: int
    tied_predictions: int


class AccuracyInterval(_EvaluationModel):
    method: Literal["wilson"] = "wilson"
    confidence_level: Annotated[float, Field(strict=True, ge=0.95, le=0.95)] = 0.95
    z: Annotated[float, Field(strict=True, ge=1.96, le=1.96)] = 1.96
    n: Annotated[int, Field(ge=1)]
    successes: Annotated[int, Field(ge=0)]
    lower: Probability
    upper: Probability


class DecisionEvaluationMetrics(_EvaluationModel):
    accuracy: float | None
    accuracy_interval: AccuracyInterval | None = None
    ece: float | None
    brier: float | None
    nll: float | None
    strict_valid_rate: float | None
    lenient_valid_rate: float | None
    error_rate: float | None


class ReliabilityBin(_EvaluationModel):
    lower_bound: float
    upper_bound: float
    count: int
    mean_confidence: float | None
    accuracy: float | None


class SelectiveCoverage(_EvaluationModel):
    risk_budget: float
    selected_count: int
    confidence_threshold: float | None
    coverage: float | None
    empirical_risk: float | None


class UnderdeterminedDiagnostics(_EvaluationModel):
    count: int
    mean_max_probability: float | None
    high_confidence_rate: float | None
    uniform_deviation: float | None


class DecisionEvaluationSummary(_EvaluationModel):
    counts: DecisionEvaluationCounts
    metrics: DecisionEvaluationMetrics
    ece_bins: tuple[ReliabilityBin, ...]
    selective_coverage: SelectiveCoverage
    underdetermined: UnderdeterminedDiagnostics


class DecisionTagGroup(DecisionEvaluationSummary):
    tag: DecisionKey


class TagDiagnostics(_EvaluationModel):
    total_tags: Annotated[int, Field(ge=0)] = 0
    omitted_tags: Annotated[int, Field(ge=0)] = 0
    tag_limit: Literal[25] = 25
    groups: tuple[DecisionTagGroup, ...] = ()


class DecisionEvaluationReport(DecisionEvaluationSummary):
    schema_version: Literal[1] = 1
    model_id: DecisionKey | None
    dataset_id: DecisionKey | None
    input_sha256: str
    score_source: Literal["provided_probabilities"] = "provided_probabilities"
    calibration_status: Literal["unverified"] = "unverified"
    tag_diagnostics: TagDiagnostics = Field(default_factory=TagDiagnostics)
