from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Literal, override
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from antigravity_k.engine.provider_adapters.unsloth_resource_contracts import (
    UnslothAdmissionCode,
    UnslothAdmissionRequest,
    UnslothArtifactProvenance,
    UnslothResourceOperation,
)

type UnslothGradientCheckpointing = Literal[False, True, "unsloth"]


@dataclass(frozen=True, slots=True)
class UnslothTrainingContractError(ValueError):
    reason: str

    @override
    def __str__(self) -> str:
        return self.reason


class UnslothTrainingRecipe(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    model_name: str = Field(min_length=3, max_length=256, pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    model_snapshot_path: str = Field(min_length=1, max_length=4_096)
    hf_dataset: str = Field(min_length=3, max_length=256, pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    dataset_snapshot_path: str = Field(min_length=1, max_length=4_096)
    format_type: str = Field(min_length=1, max_length=64)
    training_type: Literal["LoRA/QLoRA"] = "LoRA/QLoRA"
    load_in_4bit: bool = True
    max_seq_length: int = Field(ge=256, le=131_072)
    num_epochs: int = Field(ge=1, le=100)
    learning_rate: Decimal = Field(gt=0, lt=1)
    batch_size: int = Field(ge=1, le=128)
    gradient_accumulation_steps: int = Field(ge=1, le=4_096)
    lora_r: int = Field(ge=1, le=1_024)
    lora_alpha: int = Field(ge=1, le=2_048)
    packing: bool = False
    use_gradient_checkpointing: UnslothGradientCheckpointing = "unsloth"
    trust_remote_code: Literal[False] = False
    enable_wandb: Literal[False] = False

    @model_validator(mode="after")
    def validate_snapshot_paths(self) -> UnslothTrainingRecipe:
        for snapshot_path in (self.model_snapshot_path, self.dataset_snapshot_path):
            path = Path(snapshot_path)
            if not path.is_absolute() or ".." in path.parts:
                raise UnslothTrainingContractError(
                    "Training snapshot paths must be absolute and normalized.",
                )
        return self


class UnslothTrainingMCPConfig(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    model_name: str
    start_request_id: str
    training_type: Literal["LoRA/QLoRA"]
    load_in_4bit: bool
    max_seq_length: int
    trust_remote_code: Literal[False]
    model_snapshot_path: str
    hf_dataset: str
    dataset_snapshot_path: str
    format_type: str
    num_epochs: int
    learning_rate: Decimal
    batch_size: int
    gradient_accumulation_steps: int
    lora_r: int
    lora_alpha: int
    packing: bool
    use_gradient_checkpointing: UnslothGradientCheckpointing
    use_lora: Literal[True] = True
    enable_wandb: Literal[False]


class UnslothRemoteTrainingJob(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    job_id: str = Field(min_length=1, max_length=256)
    status: Literal["pending", "queued", "error"]
    message: str = Field(max_length=4_096)
    error: str | None = Field(default=None, max_length=4_096)
    error_code: str | None = Field(default=None, max_length=256)


class UnslothTrainingStartRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    admission: UnslothAdmissionRequest
    dataset_artifact: UnslothArtifactProvenance
    recipe: UnslothTrainingRecipe
    approval_id: str | None = Field(default=None, min_length=8, max_length=128)

    @model_validator(mode="after")
    def validate_provenance_links(self) -> UnslothTrainingStartRequest:
        if self.admission.operation is not UnslothResourceOperation.TRAINING:
            raise UnslothTrainingContractError("Training launch admission must use the training operation.")
        if _hf_repo_id(self.admission.artifact.source_uri) != self.recipe.model_name:
            raise UnslothTrainingContractError("Model provenance must match the training recipe model.")
        if _hf_repo_id(self.dataset_artifact.source_uri) != self.recipe.hf_dataset:
            raise UnslothTrainingContractError("Dataset provenance must match the training recipe dataset.")
        return self

    def request_fingerprint(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json", exclude={"approval_id"}),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    def mcp_config(self) -> UnslothTrainingMCPConfig:
        return UnslothTrainingMCPConfig(
            model_name=self.recipe.model_name,
            start_request_id=self.admission.idempotency_key,
            training_type=self.recipe.training_type,
            load_in_4bit=self.recipe.load_in_4bit,
            max_seq_length=self.recipe.max_seq_length,
            trust_remote_code=self.recipe.trust_remote_code,
            model_snapshot_path=self.recipe.model_snapshot_path,
            hf_dataset=self.recipe.hf_dataset,
            dataset_snapshot_path=self.recipe.dataset_snapshot_path,
            format_type=self.recipe.format_type,
            num_epochs=self.recipe.num_epochs,
            learning_rate=self.recipe.learning_rate,
            batch_size=self.recipe.batch_size,
            gradient_accumulation_steps=self.recipe.gradient_accumulation_steps,
            lora_r=self.recipe.lora_r,
            lora_alpha=self.recipe.lora_alpha,
            packing=self.recipe.packing,
            use_gradient_checkpointing=self.recipe.use_gradient_checkpointing,
            enable_wandb=self.recipe.enable_wandb,
        )


class UnslothTrainingLaunchState(StrEnum):
    WRITE_DISABLED = "write_disabled"
    POLICY_DENIED = "policy_denied"
    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_DENIED = "approval_denied"
    RESOURCE_DENIED = "resource_denied"
    STARTED = "started"
    IDEMPOTENT_REPLAY = "idempotent_replay"
    REMOTE_REJECTED = "remote_rejected"
    UNCERTAIN = "uncertain"


class UnslothTrainingStartOutcome(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    state: UnslothTrainingLaunchState
    write_tools_enabled: bool
    approval_id: str | None = None
    reservation_id: str | None = None
    resource_code: UnslothAdmissionCode | None = None
    resource_job_id: str | None = None
    remote_status: str | None = None


def _hf_repo_id(source_uri: str) -> str | None:
    parsed = urlsplit(source_uri)
    if parsed.scheme != "hf" or not parsed.netloc:
        return None
    return f"{parsed.netloc}{parsed.path}".strip("/")
