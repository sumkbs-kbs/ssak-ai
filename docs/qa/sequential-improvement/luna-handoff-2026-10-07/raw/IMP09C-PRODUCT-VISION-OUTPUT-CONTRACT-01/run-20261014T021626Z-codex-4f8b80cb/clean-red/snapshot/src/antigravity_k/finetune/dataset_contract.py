from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Final, Literal, override

from pydantic import BaseModel, ConfigDict, Field

EMAIL_PATTERN: Final = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
KOREAN_PHONE_PATTERN: Final = re.compile(r"\b(?:0\d{1,2}-?\d{3,4}-?\d{4})\b")
MANIFEST_VERSION: Final = 1


class DatasetConsent(StrEnum):
    EXPLICIT = "explicit"
    PUBLICLY_AVAILABLE = "publicly_available"
    UNKNOWN = "unknown"


class DatasetSubjectRights(StrEnum):
    HONORED = "honored"
    UNKNOWN = "unknown"


class DatasetLicense(StrEnum):
    MIT = "MIT"
    APACHE_2_0 = "Apache-2.0"
    CC_BY_4_0 = "CC-BY-4.0"


@dataclass(frozen=True, slots=True)
class DatasetContractError(ValueError):
    reason: str

    @override
    def __str__(self) -> str:
        return self.reason


class DatasetSplitPolicy(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    seed: int = Field(ge=0, le=2_147_483_647)
    train_ratio: Literal["90/10", "80/20"]
    manifest_path: Path


class FinetuneDatasetContract(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    path: Path
    consent: DatasetConsent
    subject_rights: DatasetSubjectRights
    license_id: DatasetLicense
    split_policy: DatasetSplitPolicy


class DatasetInspectionReport(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    sha256: str
    record_count: int = Field(ge=1)
    train_record_count: int = Field(ge=1)
    valid_record_count: int = Field(ge=1)
    pii_findings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DatasetSplitPaths:
    train_path: Path
    valid_path: Path


class DatasetSplitManifest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    manifest_version: Literal[1]
    sha256: str
    record_count: int = Field(ge=1)
    seed: int
    train_ratio: str
    train_indices: tuple[int, ...]
    valid_indices: tuple[int, ...]


def inspect_dataset(contract: FinetuneDatasetContract) -> DatasetInspectionReport:
    if contract.consent is not DatasetConsent.EXPLICIT:
        raise DatasetContractError("Fine-tuning input requires documented explicit consent.")
    if contract.subject_rights is not DatasetSubjectRights.HONORED:
        raise DatasetContractError("Dataset subject rights must be honored before training.")

    payload = contract.path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    records = _records(payload)
    findings = _pii_findings(records)
    if findings:
        raise DatasetContractError(f"PII detected in fine-tuning input: {', '.join(findings)}")

    train_indices, valid_indices = _split_indices(
        record_count=len(records),
        seed=contract.split_policy.seed,
        train_ratio=contract.split_policy.train_ratio,
    )
    manifest = DatasetSplitManifest(
        manifest_version=MANIFEST_VERSION,
        sha256=digest,
        record_count=len(records),
        seed=contract.split_policy.seed,
        train_ratio=contract.split_policy.train_ratio,
        train_indices=train_indices,
        valid_indices=valid_indices,
    )
    _freeze_manifest(contract.split_policy.manifest_path, manifest)

    return DatasetInspectionReport(
        sha256=digest,
        record_count=len(records),
        train_record_count=len(train_indices),
        valid_record_count=len(valid_indices),
        pii_findings=(),
    )


def split_frozen_dataset(contract: FinetuneDatasetContract) -> DatasetSplitPaths:
    _ = inspect_dataset(contract)
    manifest = DatasetSplitManifest.model_validate_json(
        contract.split_policy.manifest_path.read_text(encoding="utf-8"),
    )
    records = _records(contract.path.read_bytes())
    train_path = contract.path.with_name(f"{contract.path.stem}_train{contract.path.suffix}")
    valid_path = contract.path.with_name(f"{contract.path.stem}_valid{contract.path.suffix}")
    _write_indices(train_path, records, manifest.train_indices)
    _write_indices(valid_path, records, manifest.valid_indices)
    return DatasetSplitPaths(train_path=train_path, valid_path=valid_path)


def _records(payload: bytes) -> tuple[str, ...]:
    records = tuple(record for record in payload.decode("utf-8").splitlines() if record)
    if not records:
        raise DatasetContractError("Dataset must contain at least one JSONL record.")
    return records


def _pii_findings(records: tuple[str, ...]) -> tuple[str, ...]:
    findings: list[str] = []
    for index, record in enumerate(records):
        if EMAIL_PATTERN.search(record) is not None:
            findings.append(f"record {index}: email")
        if KOREAN_PHONE_PATTERN.search(record) is not None:
            findings.append(f"record {index}: phone")
    return tuple(findings)


def _split_indices(
    *,
    record_count: int,
    seed: int,
    train_ratio: Literal["90/10", "80/20"],
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    ratio = 0.9 if train_ratio == "90/10" else 0.8
    indices = list(range(record_count))
    random.Random(seed).shuffle(indices)
    split_at = int(record_count * ratio)
    train_indices = tuple(sorted(indices[:split_at]))
    valid_indices = tuple(sorted(indices[split_at:]))
    if not train_indices or not valid_indices:
        raise DatasetContractError("Dataset split must produce train and validation records.")
    return train_indices, valid_indices


def _freeze_manifest(path: Path, manifest: DatasetSplitManifest) -> None:
    if path.exists():
        existing = DatasetSplitManifest.model_validate_json(path.read_text(encoding="utf-8"))
        if existing != manifest:
            raise DatasetContractError("Frozen dataset manifest must remain unchanged.")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")


def _write_indices(path: Path, records: tuple[str, ...], indices: tuple[int, ...]) -> None:
    payload = "".join(f"{records[index]}\n" for index in indices)
    _ = path.write_text(payload, encoding="utf-8")
