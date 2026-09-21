"""FlyWire 원자료 계약 — **판정**만 갖고, 측정은 드라이버가 한다.

이 모듈은 표준 라이브러리만 쓴다(duckdb 불필요). 이유는 셋이다:

1. 같은 규칙을 duckdb 실행·stdlib 실행·계약 시험이 **재사용**한다. 판정이 드라이버에
   흩어져 있으면 이빨(변이)이 겨눌 대상도 흩어진다.
2. 원자료(약 17.5 GB)는 제품/Git 에 들어가지 않는다. 계약은 **수치와 규칙**만 갖고,
   데이터는 `--data-root`(D)에서 읽는다.
3. 원본이 바뀌면 hardcoded 정상값에 맞추지 않고 **새 dataset version** 으로 취급한다 —
   그래서 규칙은 release 별 expectations 파일에 있고, 해시는 **승인 실행**이 찍는다.

핵심 계약(요약):
  - root_id 는 문자열/64bit 정수다. 소수점·지수 표기는 **거절**한다(JS Number 금지).
  - neuropil 행은 pair 로 **합산**해 읽는다. 행 최소 syn 과 pair 최소 합을 혼동하지 않는다.
  - thresholded Princeton / no-threshold Princeton / Buhmann 은 **별도 데이터셋**이다.
    한 그래프로 합치지 않는다(표 혼합은 거절).
  - 세포군은 **주석 컬럼(class)** 으로만 정의한다. label 이름이나 root_id 크기로 추정하지
    않는다. 교차 출처(`consolidated_cell_types.primary_type`) 검증을 통과하지 못하면
    회로는 INCONCLUSIVE 다.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Iterable, Iterator, Mapping, Sequence

MANIFEST_VERSION: Final = 1
HASH_CHUNK: Final = 8 * 1024 * 1024

# ── exit code (계약 숫자: 시험이 이 표를 재므로 바꾸면 시험도 바꿔야 한다) ──
EXIT_OK: Final = 0
EXIT_USAGE: Final = 1
EXIT_INPUT_MISSING: Final = 2
EXIT_SCHEMA_VIOLATION: Final = 3
EXIT_DUPLICATE_EDGE: Final = 4
EXIT_FK_VIOLATION: Final = 5
EXIT_RELEASE_MISMATCH: Final = 6
EXIT_TABLE_MIXING: Final = 7
EXIT_COUNT_MISMATCH: Final = 8
EXIT_OUTPUT_ERROR: Final = 9
EXIT_INCONCLUSIVE: Final = 10

EXIT_MEANINGS: Final[Mapping[int, str]] = {
    EXIT_OK: "PASS — release 기대치와 입력 해시가 모두 일치",
    EXIT_USAGE: "인자 오류",
    EXIT_INPUT_MISSING: "필수 입력 파일 부재",
    EXIT_SCHEMA_VIOLATION: "스키마 위반(정수 아님 ID 등)",
    EXIT_DUPLICATE_EDGE: "중복 edge 행",
    EXIT_FK_VIOLATION: "연결이 참조하는 노드 누락",
    EXIT_RELEASE_MISMATCH: "다른 release 이거나 승인되지 않은 입력 변경",
    EXIT_TABLE_MIXING: "thresholded/no-threshold/Buhmann 표 혼합",
    EXIT_COUNT_MISMATCH: "수치가 release 기대치와 불일치",
    EXIT_OUTPUT_ERROR: "산출물 쓰기 실패",
    EXIT_INCONCLUSIVE: "회로 판정 INCONCLUSIVE(주석 근거 부족)",
}

# FlyWire root_id 는 2^59 이상의 64bit 정수다(관측: 720575940…). 하한은 "정수다"를
# 넘어 "이 release 의 ID 체계다"를 확인하는 값이고, 상한은 signed 64bit 다.
ROOT_ID_MIN: Final = 720575940000000000
ROOT_ID_MAX: Final = 2**63
PLACEHOLDER_PRIMARY_TYPE: Final = re.compile(r"^CB\d+$")

FAILURE_EXIT_ORDER: Final[Sequence[tuple[str, int]]] = (
    ("required_inputs", EXIT_INPUT_MISSING),
    ("release_marker", EXIT_RELEASE_MISMATCH),
    ("input_hashes", EXIT_RELEASE_MISMATCH),
    ("integer_ids", EXIT_SCHEMA_VIOLATION),
    ("unique_ids", EXIT_DUPLICATE_EDGE),
    ("fk_neurons", EXIT_FK_VIOLATION),
    ("no_duplicate_rows", EXIT_DUPLICATE_EDGE),
    ("table_not_mixed", EXIT_TABLE_MIXING),
    ("threshold_floor", EXIT_COUNT_MISMATCH),
    ("pair_aggregation", EXIT_COUNT_MISMATCH),
    ("counts_match_reference", EXIT_COUNT_MISMATCH),
    ("skeleton_consistency", EXIT_COUNT_MISMATCH),
    ("group_integrity", EXIT_COUNT_MISMATCH),
    ("manifest_schema", EXIT_SCHEMA_VIOLATION),
)


# ────────────────────────────── 측정값 자료형 ──────────────────────────────
@dataclass(slots=True)
class FileFacts:
    """파일 하나의 사실 — 해시/크기. 원본 변경 감지의 단위."""

    path: str
    bytes: int
    sha256: str
    hash_seconds: float | None = None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"path": self.path, "bytes": self.bytes, "sha256": self.sha256}
        if self.hash_seconds is not None:
            out["hash_seconds"] = round(self.hash_seconds, 3)
        return out


@dataclass(slots=True)
class IdColumnFacts:
    """ID 컬럼의 정수성 — duckdb 는 타입으로, stdlib 는 토큰으로 본다."""

    column: str
    declared_type: str
    non_integral: int = 0
    out_of_range: int = 0
    sample_non_integral: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "column": self.column,
            "declared_type": self.declared_type,
            "non_integral": self.non_integral,
            "out_of_range": self.out_of_range,
            "sample_non_integral": self.sample_non_integral[:5],
        }


@dataclass(slots=True)
class NeuronsFacts:
    row_count: int = 0
    distinct_ids: int = 0
    nt_unknown: int = 0
    nt_low_confidence: int = 0
    nt_type_counts: dict[str, int] = field(default_factory=dict)
    ids: list[int] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "row_count": self.row_count,
            "distinct_ids": self.distinct_ids,
            "nt_unknown": self.nt_unknown,
            "nt_low_confidence": self.nt_low_confidence,
            "nt_type_counts": dict(sorted(self.nt_type_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        }


@dataclass(slots=True)
class ClassificationFacts:
    row_count: int = 0
    distinct_ids: int = 0
    class_null: int = 0
    ids_outside_neurons: int = 0
    super_class_counts: dict[str, int] = field(default_factory=dict)
    class_counts: dict[str, int] = field(default_factory=dict)
    members: dict[str, list[int]] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "row_count": self.row_count,
            "distinct_ids": self.distinct_ids,
            "class_null": self.class_null,
            "ids_outside_neurons": self.ids_outside_neurons,
            "super_class_counts": dict(sorted(self.super_class_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        }


@dataclass(slots=True)
class EdgeFacts:
    row_count: int = 0
    distinct_pairs: int = 0
    synapses: int = 0
    min_row_syn: int | None = None
    max_row_syn: int | None = None
    self_pairs: int = 0
    neuropils: int = 0
    duplicate_rows: int = 0
    min_pair_syn: int | None = None
    pairs_below_threshold: int = 0
    fk_missing_pre: int = 0
    fk_missing_post: int = 0
    unreadable_rows: int = 0

    def to_json(self) -> dict[str, Any]:
        return {
            "row_count": self.row_count,
            "distinct_pairs": self.distinct_pairs,
            "synapses": self.synapses,
            "min_row_syn": self.min_row_syn,
            "max_row_syn": self.max_row_syn,
            "self_pairs": self.self_pairs,
            "neuropils": self.neuropils,
            "duplicate_rows": self.duplicate_rows,
            "min_pair_syn": self.min_pair_syn,
            "pairs_below_threshold": self.pairs_below_threshold,
            "fk_missing_pre": self.fk_missing_pre,
            "fk_missing_post": self.fk_missing_post,
            "unreadable_rows": self.unreadable_rows,
        }


@dataclass(slots=True)
class CrossSourceFacts:
    """교차 출처 검증 — 두 번째 주석이 집단을 지지하는가.

    스캐너는 **라벨별 건수**만 모은다. 무엇이 '해소된 이름'이고 무엇이 패턴 일치인지는
    계약이 정한다(마지막 두 글자가 판정 규칙을 갖는다).
    """

    table: str
    column: str
    covered: int = 0
    member_labels: dict[int, str] = field(default_factory=dict)

    def label_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for label in self.member_labels.values():
            counts[label] = counts.get(label, 0) + 1
        return counts

    def resolved_count(self) -> int:
        return sum(
            count
            for label, count in self.label_counts().items()
            if label and label != "(empty)" and not PLACEHOLDER_PRIMARY_TYPE.match(label)
        )

    def placeholder_labels(self) -> dict[str, int]:
        return {
            label: count
            for label, count in self.label_counts().items()
            if label == "(empty)" or PLACEHOLDER_PRIMARY_TYPE.match(label)
        }

    def matching_labels(self, patterns: Sequence[str]) -> int:
        compiled = [re.compile(pattern) for pattern in patterns]
        if not compiled:
            return 0
        return sum(
            count
            for label, count in self.label_counts().items()
            if label and label != "(empty)" and any(p.search(label) for p in compiled)
        )

    def unresolved_members(self, patterns: Sequence[str]) -> set[int]:
        """선언 패턴에 맞는 label 을 **갖지 못한** 구성원 ID.

        mask 에서 빠지지 않는다(그래프를 줄이지 않는다). 대신 그 endpoint 를 지나는 edge
        수를 세어 "무엇이 미해소 위에 서 있는가"를 보고한다.
        """

        compiled = [re.compile(pattern) for pattern in patterns]
        if not compiled:
            return set(self.member_labels)
        return {
            root_id
            for root_id, label in self.member_labels.items()
            if not label or label == "(empty)" or not any(p.search(label) for p in compiled)
        }

    def to_json(self) -> dict[str, Any]:
        counts = self.label_counts()
        return {
            "table": self.table,
            "column": self.column,
            "covered": self.covered,
            "resolved": self.resolved_count(),
            "label_counts": dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:10]),
            "unresolved_labels": dict(sorted(self.placeholder_labels().items(), key=lambda kv: (-kv[1], kv[0]))[:8]),
        }


@dataclass(slots=True)
class GroupFacts:
    label: str
    source_column: str
    source_values: list[str]
    count: int = 0
    joined_neurons: int = 0
    overlaps: dict[str, int] = field(default_factory=dict)
    cross: CrossSourceFacts | None = None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "label": self.label,
            "source_column": self.source_column,
            "source_values": list(self.source_values),
            "count": self.count,
            "joined_neurons": self.joined_neurons,
            "overlaps": dict(self.overlaps),
        }
        if self.cross is not None:
            out["cross_source"] = self.cross.to_json()
        return out


@dataclass(slots=True)
class SkeletonFacts:
    path: str
    entries: int = 0
    swc_entries: int = 0
    extra_ids: list[str] = field(default_factory=list)
    missing_ids: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "entries": self.entries,
            "swc_entries": self.swc_entries,
            "extra_count": len(self.extra_ids),
            "missing_count": len(self.missing_ids),
            "extra_ids_sha256": sha256_text("\n".join(self.extra_ids)),
            "extra_ids_sample": self.extra_ids[:5],
        }


@dataclass(slots=True)
class Measurement:
    """한 번의 검증 실행이 모은 **사실 전부** — 판정 입력은 이것 하나다."""

    data_root: str
    release: str
    files: dict[str, FileFacts] = field(default_factory=dict)
    id_columns: dict[str, IdColumnFacts] = field(default_factory=dict)
    neurons: NeuronsFacts | None = None
    classification: ClassificationFacts | None = None
    edges: EdgeFacts | None = None
    edge_table: str = ""
    groups: dict[str, GroupFacts] = field(default_factory=dict)
    skeleton: SkeletonFacts | None = None
    reader: str = "unknown"
    root_id_index_mapping_sha256: str = ""
    elapsed_seconds: float | None = None
    inventory: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Finding:
    """검사 결과. `blocking=False` 는 **판정에는 쓰이지만 run 을 실패시키지 않는** 사실이다.

    예: 세포군 `INCONCLUSIVE`. 데이터가 틀린 것이 아니라 그 집단을 주장할 근거가
    부족한 것이므로, dataset 검증은 통과해야 한다. 이 구분이 없으면 "주석 근거 부족"이
    "데이터 오류"로 둔갑한다.
    """

    check_id: str
    ok: bool
    detail: str
    measured: dict[str, Any] = field(default_factory=dict)
    blocking: bool = True

    def to_json(self) -> dict[str, Any]:
        return {
            "check": self.check_id,
            "ok": self.ok,
            "detail": self.detail,
            "measured": self.measured,
            "blocking": self.blocking,
        }


# ────────────────────────────── 해시·매핑 ──────────────────────────────
def sha256_file(path: Path) -> tuple[str, float]:
    """파일 하나의 sha256 과 걸린 시간(초). 거대 archive 도 일회성 I/O 로 잰다."""

    import time

    started = time.monotonic()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(HASH_CHUNK)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest(), time.monotonic() - started


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def data_root_inventory(root: Path) -> dict[str, Any]:
    """원자료 디렉터리의 파일 수·총 바이트 — **읽지 않고** 이름만 센다.

    해시 대상(release 고정 입력)과 별개로 두는 이유: 디렉터리에 새 표가 생기면 그 변화가
    보이게 하되, 그 표를 자동으로 그래프에 섞지는 않기 위해서다.
    """

    files = sorted(path for path in root.iterdir() if path.is_file())
    return {
        "files": len(files),
        "total_bytes": sum(path.stat().st_size for path in files),
        "names": [path.name for path in files],
    }


def root_id_index_mapping_sha256(ids: Iterable[int]) -> str:
    """정렬된 root_id → index 매핑의 해시.

    **행 순서가 달라도 같아야 한다**는 요구를 이 해시가 잡는다. 입력 순서를 그대로
    쓰면 같은 데이터의 두 덤프가 다른 해시를 내고, 그러면 회로 실험이 재현되지 않는다.
    """

    ordered = sorted(set(ids))
    digest = hashlib.sha256()
    for index, root_id in enumerate(ordered):
        digest.update(f"{root_id}:{index}\n".encode("utf-8"))
    return digest.hexdigest()


def _integer_token(token: str) -> bool:
    text = token.strip()
    if not text:
        return False
    if text[0] in "+-":
        text = text[1:]
    return text.isdigit() and text.isascii()


# ────────────────────────────── stdlib 스캐너 ──────────────────────────────
def _iter_csv_rows(path: Path) -> Iterator[list[str]]:
    with gzip.open(path, "rt", encoding="utf-8", errors="replace", newline="") as handle:
        for line in handle:
            line = line.rstrip("\r\n")
            if not line:
                continue
            yield line.split(",")


def scan_neurons_stdlib(path: Path, limit_ids: bool = True) -> tuple[NeuronsFacts, IdColumnFacts]:
    rows = _iter_csv_rows(path)
    header = next(rows)
    index = {name: position for position, name in enumerate(header)}
    id_at = index["root_id"]
    nt_at = index.get("nt_type")
    score_at = index.get("nt_type_score")

    facts = NeuronsFacts()
    column = IdColumnFacts(column="root_id", declared_type="VARCHAR(stdlib)")
    seen: set[int] = set()
    for row in rows:
        if len(row) <= id_at:
            continue
        facts.row_count += 1
        token = row[id_at]
        if not _integer_token(token):
            column.non_integral += 1
            if len(column.sample_non_integral) < 5:
                column.sample_non_integral.append(token)
            continue
        value = int(token)
        if not (ROOT_ID_MIN <= value < ROOT_ID_MAX):
            column.out_of_range += 1
        if value not in seen:
            seen.add(value)
            if limit_ids:
                facts.ids.append(value)
        nt_type = row[nt_at] if nt_at is not None and len(row) > nt_at else ""
        nt_type = nt_type.strip() or "(null)"
        facts.nt_type_counts[nt_type] = facts.nt_type_counts.get(nt_type, 0) + 1
        if nt_type == "(null)":
            facts.nt_unknown += 1
        if score_at is not None and len(row) > score_at and row[score_at].strip():
            try:
                if float(row[score_at]) < 0.5:
                    facts.nt_low_confidence += 1
            except ValueError:
                pass
    facts.distinct_ids = len(seen)
    return facts, column


def scan_classification_stdlib(
    path: Path, wanted_classes: Sequence[str], known_ids: set[int] | None = None
) -> tuple[ClassificationFacts, dict[str, list[int]]]:
    rows = _iter_csv_rows(path)
    header = next(rows)
    index = {name: position for position, name in enumerate(header)}
    id_at = index["root_id"]
    cls_at = index["class"]
    super_at = index.get("super_class")

    facts = ClassificationFacts()
    members: dict[str, list[int]] = {label: [] for label in wanted_classes}
    wanted = set(wanted_classes)
    for row in rows:
        if len(row) <= max(id_at, cls_at):
            continue
        facts.row_count += 1
        token = row[id_at]
        if not _integer_token(token):
            continue
        root_id = int(token)
        cls = row[cls_at].strip() or "(null)"
        if cls == "(null)":
            facts.class_null += 1
        else:
            facts.class_counts[cls] = facts.class_counts.get(cls, 0) + 1
        if super_at is not None and len(row) > super_at:
            super_class = row[super_at].strip() or "(null)"
            facts.super_class_counts[super_class] = facts.super_class_counts.get(super_class, 0) + 1
        if known_ids is not None and root_id not in known_ids:
            facts.ids_outside_neurons += 1
        if cls in wanted:
            members[cls].append(root_id)
    facts.distinct_ids = facts.row_count
    facts.members = members
    return facts, members


def scan_edges_stdlib(path: Path, neuropil_threshold: int, known_ids: set[int] | None) -> EdgeFacts:
    rows = _iter_csv_rows(path)
    header = next(rows)
    index = {name: position for position, name in enumerate(header)}
    pre_at = index["pre_root_id"]
    post_at = index["post_root_id"]
    neuro_at = index["neuropil"]
    syn_at = index["syn_count"]

    facts = EdgeFacts()
    pair_sums: dict[tuple[int, int], int] = {}
    row_signatures: set[tuple[int, int, str]] = set()
    neuropils: set[str] = set()
    for row in rows:
        width = max(pre_at, post_at, neuro_at, syn_at)
        if len(row) <= width:
            facts.unreadable_rows += 1
            continue
        try:
            pre = int(row[pre_at])
            post = int(row[post_at])
            syn = int(row[syn_at])
        except ValueError:
            facts.unreadable_rows += 1
            continue
        facts.row_count += 1
        neuropil = row[neuro_at].strip()
        neuropils.add(neuropil)
        facts.synapses += syn
        facts.min_row_syn = syn if facts.min_row_syn is None else min(facts.min_row_syn, syn)
        facts.max_row_syn = syn if facts.max_row_syn is None else max(facts.max_row_syn, syn)
        if pre == post:
            facts.self_pairs += 1
        signature = (pre, post, neuropil)
        if signature in row_signatures:
            facts.duplicate_rows += 1
        else:
            row_signatures.add(signature)
        pair = (pre, post)
        pair_sums[pair] = pair_sums.get(pair, 0) + syn
        if known_ids is not None:
            if pre not in known_ids:
                facts.fk_missing_pre += 1
            if post not in known_ids:
                facts.fk_missing_post += 1
    facts.distinct_pairs = len(pair_sums)
    facts.neuropils = len(neuropils)
    if pair_sums:
        facts.min_pair_syn = min(pair_sums.values())
        facts.pairs_below_threshold = sum(1 for value in pair_sums.values() if value < neuropil_threshold)
    return facts


def scan_cross_source_stdlib(
    path: Path, group_members: Mapping[str, Sequence[int]], table_name: str, column: str
) -> dict[str, CrossSourceFacts]:
    rows = _iter_csv_rows(path)
    header = next(rows)
    index = {name: position for position, name in enumerate(header)}
    id_at = index["root_id"]
    type_at = index.get(column, 1)

    wanted = {root_id: label for label, ids in group_members.items() for root_id in ids}
    facts = {label: CrossSourceFacts(table=table_name, column=column) for label in group_members}
    for row in rows:
        if len(row) <= max(id_at, type_at):
            continue
        try:
            root_id = int(row[id_at])
        except ValueError:
            continue
        label = wanted.get(root_id)
        if label is None:
            continue
        bucket = facts[label]
        bucket.covered += 1
        bucket.member_labels[root_id] = row[type_at].strip() or "(empty)"
    return facts


def scan_skeleton_zip(path: Path, neuron_ids: Iterable[int]) -> SkeletonFacts:
    known = {str(root_id) for root_id in neuron_ids}
    facts = SkeletonFacts(path=path.name)
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            facts.entries += 1
            stem = Path(name).stem
            if name.endswith(".swc"):
                facts.swc_entries += 1
                if stem not in known and re.fullmatch(r"\d+", stem):
                    facts.extra_ids.append(stem)
    facts.extra_ids.sort()
    facts.missing_ids = sorted(known - {Path(name).stem for name in zip_swc_names(path)})
    return facts


def zip_swc_names(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        return [name for name in archive.namelist() if name.endswith(".swc")]


# ─────────────────── duckdb 스캐너 결과 → 사실 자료형 ───────────────────
def neurons_from_facts(payload: Mapping[str, Any]) -> NeuronsFacts:
    return NeuronsFacts(
        row_count=int(payload["row_count"]),
        distinct_ids=int(payload["distinct_ids"]),
        nt_unknown=int(payload["nt_unknown"]),
        nt_low_confidence=int(payload["nt_low_confidence"]),
        nt_type_counts={str(k): int(v) for k, v in payload.get("nt_type_counts", {}).items()},
        ids=[int(value) for value in payload.get("ids", [])],
    )


def classification_from_facts(payload: Mapping[str, Any]) -> ClassificationFacts:
    return ClassificationFacts(
        row_count=int(payload["row_count"]),
        distinct_ids=int(payload["distinct_ids"]),
        class_null=int(payload["class_null"]),
        ids_outside_neurons=int(payload.get("ids_outside_neurons", 0)),
        super_class_counts={str(k): int(v) for k, v in payload.get("super_class_counts", {}).items()},
        class_counts={str(k): int(v) for k, v in payload.get("class_counts", {}).items()},
        members={str(k): [int(value) for value in v] for k, v in payload.get("members", {}).items()},
    )


def edges_from_facts(payload: Mapping[str, Any]) -> EdgeFacts:
    return EdgeFacts(
        row_count=int(payload["row_count"]),
        distinct_pairs=int(payload["distinct_pairs"]),
        synapses=int(payload["synapses"]),
        min_row_syn=payload.get("min_row_syn"),
        max_row_syn=payload.get("max_row_syn"),
        self_pairs=int(payload.get("self_pairs", 0)),
        neuropils=int(payload.get("neuropils", 0)),
        duplicate_rows=int(payload.get("duplicate_rows", 0)),
        min_pair_syn=payload.get("min_pair_syn"),
        pairs_below_threshold=int(payload.get("pairs_below_threshold", 0)),
        fk_missing_pre=int(payload.get("fk_missing_pre", 0)),
        fk_missing_post=int(payload.get("fk_missing_post", 0)),
        unreadable_rows=int(payload.get("unreadable_rows", 0)),
    )


def id_column_from_facts(payload: Mapping[str, Any]) -> IdColumnFacts:
    return IdColumnFacts(
        column=str(payload["column"]),
        declared_type=str(payload["declared_type"]),
        non_integral=int(payload.get("non_integral", 0)),
        out_of_range=int(payload.get("out_of_range", 0)),
        sample_non_integral=[str(value) for value in payload.get("sample_non_integral", [])],
    )


def cross_from_facts(payload: Mapping[str, Mapping[str, Any]]) -> dict[str, CrossSourceFacts]:
    return {
        str(label): CrossSourceFacts(
            table=str(bucket["table"]),
            column=str(bucket["column"]),
            covered=int(bucket.get("covered", 0)),
            member_labels={int(k): str(v) for k, v in bucket.get("member_labels", {}).items()},
        )
        for label, bucket in payload.items()
    }


def skeleton_from_facts(payload: Mapping[str, Any]) -> SkeletonFacts:
    return SkeletonFacts(
        path=str(payload["path"]),
        entries=int(payload.get("entries", 0)),
        swc_entries=int(payload.get("swc_entries", 0)),
        extra_ids=[str(value) for value in payload.get("extra_ids", [])],
        missing_ids=[str(value) for value in payload.get("missing_ids", [])],
    )


def build_group_facts(
    label: str,
    rule: Mapping[str, Any],
    members: Sequence[int],
    neuron_ids: set[int],
    cross: CrossSourceFacts | None,
    all_members: Mapping[str, Sequence[int]],
) -> GroupFacts:
    facts = GroupFacts(
        label=label,
        source_column=str(rule.get("source_column", "class")),
        source_values=[str(value) for value in rule.get("source_values", [])],
        count=len(members),
        joined_neurons=sum(1 for root_id in members if root_id in neuron_ids),
        cross=cross,
    )
    ids = set(members)
    for other, other_ids in all_members.items():
        if other == label:
            continue
        overlap = len(ids & set(other_ids))
        if overlap:
            facts.overlaps[other] = overlap
    return facts


# ────────────────────────────── 판정 ──────────────────────────────
@dataclass(slots=True)
class CircuitMask:
    """회로 mask — 근거(주석)와 결과(해시)를 함께 갖는다."""

    name: str
    file: str
    pairs: int = 0
    rows: int = 0
    synapses: int = 0
    pre_nodes: int = 0
    post_nodes: int = 0
    unresolved_endpoint_edges: int = 0
    output_sha256: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "pairs": self.pairs,
            "rows": self.rows,
            "synapses": self.synapses,
            "pre_nodes": self.pre_nodes,
            "post_nodes": self.post_nodes,
            "unresolved_endpoint_edges": self.unresolved_endpoint_edges,
            "output_sha256": self.output_sha256,
        }


def aggregate_masks(
    edge_path: Path,
    circuits: Mapping[str, Mapping[str, str]],
    group_ids: Mapping[str, Iterable[int]],
    unresolved_ids: Mapping[str, Iterable[int]],
) -> tuple[dict[str, list[tuple[int, int, int]]], dict[str, int]]:
    """한 번의 스트림으로 여러 회로 mask 의 pair 합산을 만든다.

    neuropil 행을 pair 로 합산하는 것은 dataset 계약과 **같은 규칙**이다. threshold 를
    넘지 않는 pair 도 mask 에는 그대로 담는다 — mask 는 `connections_princeton` 표
    자체이므로 거기서 다시 임계값을 추론하면 표를 섞는 셈이 된다.
    """

    rows = _iter_csv_rows(edge_path)
    header = next(rows)
    index = {name: position for position, name in enumerate(header)}
    pre_at = index["pre_root_id"]
    post_at = index["post_root_id"]
    syn_at = index["syn_count"]
    wanted = {
        name: (
            set(group_ids.get(str(rule["pre_group"]), ())),
            set(group_ids.get(str(rule["post_group"]), ())),
        )
        for name, rule in circuits.items()
    }
    unresolved = {
        name: (
            set(unresolved_ids.get(str(rule["pre_group"]), ())),
            set(unresolved_ids.get(str(rule["post_group"]), ())),
        )
        for name, rule in circuits.items()
    }
    sums: dict[str, dict[tuple[int, int], int]] = {name: {} for name in circuits}
    row_counts: dict[str, int] = {name: 0 for name in circuits}
    unresolved_edges: dict[str, int] = {name: 0 for name in circuits}
    for row in rows:
        if len(row) <= max(pre_at, post_at, syn_at):
            continue
        try:
            pre = int(row[pre_at])
            post = int(row[post_at])
            syn = int(row[syn_at])
        except ValueError:
            continue
        for name, (pres, posts) in wanted.items():
            if pre in pres and post in posts:
                pair = (pre, post)
                sums[name][pair] = sums[name].get(pair, 0) + syn
                row_counts[name] += 1
                pre_unresolved, post_unresolved = unresolved[name]
                if pre in pre_unresolved or post in post_unresolved:
                    unresolved_edges[name] += 1
    return (
        {name: sorted((pre, post, weight) for (pre, post), weight in sums[name].items()) for name in circuits},
        row_counts,
    )


def load_expectations(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = ("release", "dataset_id", "tables", "groups", "circuits", "license")
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError(f"expectations 파일에 필수 키가 없다: {missing}")
    return payload


def check_required_inputs(root: Path, expectations: Mapping[str, Any]) -> tuple[Finding, list[str]]:
    """필수 **표**만 본다. release marker 파일은 `check_release_marker` 의 책임이다.

    둘을 섞으면 marker 가 없을 때 "입력 부재(2)"로 끝나 버리고, 정작 알아야 하는
    "다른 release 다(6)"라는 사유가 가려진다.
    """

    names = list(expectations["required_inputs"])
    missing = [name for name in names if not (root / name).is_file()]
    detail = (
        "필수 입력 3표(neurons/classification/connections_princeton) 존재"
        if not missing
        else f"부재: {sorted(set(missing))}"
    )
    return Finding("required_inputs", not missing, detail, {"missing": sorted(set(missing))}), names


def check_release_marker(root: Path, expectations: Mapping[str, Any]) -> Finding:
    markers = expectations.get("release_markers", {})
    release = str(expectations["release"])
    observed: dict[str, str | None] = {}
    failures: list[str] = []
    for kind, marker in markers.items():
        if not isinstance(marker, str):
            continue
        hit = next((p.name for p in root.glob(f"*{Path(marker).suffix}*") if marker in p.name), None)
        observed[kind] = hit
        if hit is None:
            failures.append(f"{kind}: {marker} 를 {root} 에서 찾지 못함(다른 release 로 본다)")
    for token in expectations.get("release_must_contain", []):
        if token not in release:
            failures.append(f"release 문자열 '{release}' 에 '{token}' 없음")
    detail = f"release={release} · marker={markers}" if not failures else " · ".join(failures)
    return Finding("release_marker", not failures, detail, {"observed": observed, "release": release})


def check_input_hashes(expectations: Mapping[str, Any], files: Mapping[str, FileFacts], root: Path) -> Finding:
    approved = expectations.get("approved_hashes") or {}
    if not approved:
        return Finding(
            "input_hashes",
            False,
            "승인된 해시가 없다 — `--approve-hashes` 는 참조 수치가 모두 통과한 실행에서만 허용된다(사유 필수)",
            {"approved": 0},
        )
    mismatches: list[str] = []
    for name, record in approved.items():
        observed = files.get(name)
        if observed is None:
            mismatches.append(f"{name}: 측정 없음")
            continue
        if observed.sha256 != record.get("sha256"):
            mismatches.append(f"{name}: sha256 {observed.sha256[:16]}… ≠ 승인 {str(record.get('sha256'))[:16]}…")
        elif observed.bytes != record.get("bytes"):
            mismatches.append(f"{name}: bytes {observed.bytes} ≠ 승인 {record.get('bytes')}")
    detail = (
        f"승인 해시 {len(approved)}건 일치"
        if not mismatches
        else "입력이 승인 시점과 다르다 → 새 dataset version 으로 취급해야 한다: " + "; ".join(mismatches)
    )
    return Finding("input_hashes", not mismatches, detail, {"approved": len(approved), "mismatches": mismatches})


def check_integer_ids(measurement: Measurement) -> Finding:
    problems: list[str] = []
    for name, column in measurement.id_columns.items():
        if column.non_integral:
            problems.append(
                f"{name}.{column.column}: 정수 아님 {column.non_integral}건(예 {column.sample_non_integral[:2]})"
            )
        if column.out_of_range:
            problems.append(f"{name}.{column.column}: root_id 범위 밖 {column.out_of_range}건")
    declared = {name: column.declared_type for name, column in measurement.id_columns.items()}
    detail = "모든 root_id 컬럼이 64bit 정수" if not problems else " · ".join(problems)
    return Finding("integer_ids", not problems, detail, {"declared_types": declared})


def check_unique_ids(measurement: Measurement) -> Finding:
    neurons = measurement.neurons
    classification = measurement.classification
    problems: list[str] = []
    if neurons is None:
        problems.append("neurons 측정 없음")
    elif neurons.row_count != neurons.distinct_ids:
        problems.append(f"neurons root_id 중복: 행 {neurons.row_count} ≠ 고유 {neurons.distinct_ids}")
    if classification is None:
        problems.append("classification 측정 없음")
    elif classification.row_count != classification.distinct_ids:
        problems.append(
            f"classification root_id 중복: 행 {classification.row_count} ≠ 고유 {classification.distinct_ids}"
        )
    if classification is not None and classification.ids_outside_neurons:
        problems.append(f"classification 이 neurons 에 없는 ID 를 갖는다: {classification.ids_outside_neurons}건")
    detail = "두 표의 root_id 가 고유하고 서로 맞물린다" if not problems else " · ".join(problems)
    return Finding("unique_ids", not problems, detail)


def check_fk(measurement: Measurement) -> Finding:
    edges = measurement.edges
    if edges is None:
        return Finding("fk_neurons", False, "edges 측정 없음")
    missing = edges.fk_missing_pre + edges.fk_missing_post
    detail = (
        "연결 참조 누락 0"
        if missing == 0
        else f"연결이 참조하는 노드 누락: pre {edges.fk_missing_pre} · post {edges.fk_missing_post}"
    )
    return Finding("fk_neurons", missing == 0, detail, {"pre": edges.fk_missing_pre, "post": edges.fk_missing_post})


def check_duplicate_rows(measurement: Measurement) -> Finding:
    edges = measurement.edges
    if edges is None:
        return Finding("no_duplicate_rows", False, "edges 측정 없음")
    duplicate = edges.duplicate_rows
    detail = "중복 (pre,post,neuropil) 행 0" if duplicate == 0 else f"중복 edge 행 {duplicate}건 — 그래프가 부풀려진다"
    return Finding("no_duplicate_rows", duplicate == 0, detail, {"duplicate_rows": duplicate})


def check_table_mixing(
    expectations: Mapping[str, Any], measurement: Measurement, profiles: Mapping[str, Any]
) -> Finding:
    problems: list[str] = []
    allowed = set(expectations.get("allowed_edge_tables", []))
    if measurement.edge_table not in allowed:
        problems.append(f"허용되지 않은 edge 표: {measurement.edge_table}")
    forbidden = expectations.get("forbidden_edge_tables", {})
    if measurement.edge_table in forbidden:
        problems.append(f"{measurement.edge_table}: {forbidden[measurement.edge_table]}")
    edges = measurement.edges
    threshold = expectations["tables"]["edges"].get("pair_threshold")
    if edges is not None and threshold is not None:
        if edges.pairs_below_threshold:
            problems.append(f"pair 합 {threshold} 미만 {edges.pairs_below_threshold}건 — no-threshold 표를 섞었다")
        if edges.self_pairs:
            problems.append(f"자기 연결 {edges.self_pairs}건")
    observed = (
        None
        if edges is None
        else {
            "row_count": edges.row_count,
            "synapses": edges.synapses,
            "distinct_pairs": edges.distinct_pairs,
        }
    )
    if observed is not None:
        for name, profile in profiles.items():
            if name == measurement.edge_table:
                continue
            same = all(profile.get(key) == observed.get(key) for key in ("row_count", "synapses", "distinct_pairs"))
            if same:
                problems.append(f"{measurement.edge_table} 의 수치 프로필이 {name} 와 동일하다 — 표를 바꿔치기했다")
    detail = "thresholded Princeton 표만 쓴다" if not problems else " · ".join(problems)
    return Finding(
        "table_not_mixed", not problems, detail, {"edge_table": measurement.edge_table, "observed": observed}
    )


def _expected_problem(label: str, observed: Any, expected: Any) -> str:
    return f"{label}: 관측 {observed} ≠ 기대 {expected}"


def check_counts(expectations: Mapping[str, Any], measurement: Measurement) -> Finding:
    tables = expectations["tables"]
    problems: list[str] = []
    neurons = measurement.neurons
    classification = measurement.classification
    edges = measurement.edges
    if neurons is None or classification is None or edges is None:
        problems.append("측정 누락")
    else:
        for label, observed, expected in (
            ("neurons.row_count", neurons.row_count, tables["neurons"]["rows"]),
            ("neurons.distinct_ids", neurons.distinct_ids, tables["neurons"]["distinct_ids"]),
            ("neurons.nt_unknown", neurons.nt_unknown, tables["neurons"]["nt_unknown"]),
            ("neurons.nt_low_confidence", neurons.nt_low_confidence, tables["neurons"]["nt_low_confidence"]),
            ("classification.rows", classification.row_count, tables["classification"]["rows"]),
            ("classification.class_null", classification.class_null, tables["classification"]["class_null"]),
            ("edges.rows", edges.row_count, tables["edges"]["rows"]),
            ("edges.distinct_pairs", edges.distinct_pairs, tables["edges"]["distinct_pairs"]),
            ("edges.synapses", edges.synapses, tables["edges"]["synapses"]),
            ("edges.neuropils", edges.neuropils, tables["edges"]["neuropils"]),
            ("edges.min_row_syn", edges.min_row_syn, tables["edges"]["min_row_syn"]),
            ("edges.max_row_syn", edges.max_row_syn, tables["edges"]["max_row_syn"]),
            ("edges.min_pair_syn", edges.min_pair_syn, tables["edges"]["min_pair_syn"]),
            ("edges.self_pairs", edges.self_pairs, tables["edges"]["self_pairs"]),
        ):
            if observed != expected:
                problems.append(_expected_problem(label, observed, expected))
        expected_nt = tables["neurons"].get("nt_type_counts")
        if expected_nt:
            for nt_type, expected in expected_nt.items():
                observed = neurons.nt_type_counts.get(nt_type if nt_type != "(null)" else "(null)", 0)
                if observed != expected:
                    problems.append(_expected_problem(f"neurons.nt_type[{nt_type}]", observed, expected))
        expected_super = tables["classification"].get("super_class_counts")
        if expected_super:
            for super_class, expected in expected_super.items():
                observed = classification.super_class_counts.get(super_class, 0)
                if observed != expected:
                    problems.append(_expected_problem(f"classification.super_class[{super_class}]", observed, expected))
    detail = "release 기대 수치 재현" if not problems else "; ".join(problems)
    measured = {
        "neurons": None if neurons is None else neurons.to_json(),
        "classification": None if classification is None else classification.to_json(),
        "edges": None if edges is None else edges.to_json(),
    }
    return Finding("counts_match_reference", not problems, detail, measured)


def check_skeleton(expectations: Mapping[str, Any], measurement: Measurement) -> Finding:
    expected = expectations.get("skeleton") or {}
    facts = measurement.skeleton
    if facts is None:
        optional = bool(expected.get("optional", False))
        detail = (
            "skeleton archive 를 읽지 않았다(선택 입력)"
            if optional
            else "skeleton archive 를 읽지 않았다 — 이 release 는 필수다"
        )
        return Finding("skeleton_consistency", optional, detail, {"expected": expected.get("entries")})
    problems: list[str] = []
    for label, observed, wanted in (
        ("entries", facts.entries, expected.get("entries")),
        ("swc_entries", facts.swc_entries, expected.get("swc_entries")),
        ("extra", len(facts.extra_ids), expected.get("extra_count")),
        ("missing", len(facts.missing_ids), expected.get("missing_count")),
    ):
        if wanted is not None and observed != wanted:
            problems.append(_expected_problem(f"skeleton.{label}", observed, wanted))
    detail = "skeleton 추가/누락 수치 일치" if not problems else "; ".join(problems)
    return Finding("skeleton_consistency", not problems, detail, facts.to_json())


def group_decision(label: str, rule: Mapping[str, Any], facts: GroupFacts) -> tuple[Finding, Finding]:
    """세포군 판정을 **둘로 나눠** 낸다.

      (a) `group_integrity:<label>` — 데이터 무결성. 건수·join·중복은 계약 위반이므로
          실패하면 run 이 실패한다(exit 8).
      (b) `group_status:<label>` — 주장 가능성. 교차 출처 패턴/합의가 부족하면
          `INCONCLUSIVE` 가 될 뿐 **검증 실패가 아니다**. 회로 mask 의 근거로만 쓰인다.

    이 분리가 없으면 "주석 근거가 부족하다"가 "데이터가 틀렸다"로 둔갑한다.
    """

    integrity_problems: list[str] = []
    expected_count = rule.get("count")
    if expected_count is not None and facts.count != expected_count:
        integrity_problems.append(_expected_problem(f"{label}.count", facts.count, expected_count))
    if facts.joined_neurons != facts.count:
        integrity_problems.append(f"{label}: neurons 에 없는 ID {facts.count - facts.joined_neurons}건")
    if sum(facts.overlaps.values()):
        integrity_problems.append(f"{label}: 다른 집단과 ID 중복 {facts.overlaps}")

    status_problems: list[str] = []
    cross_rule = rule.get("cross_source") or {}
    patterns = [str(pattern) for pattern in (cross_rule.get("patterns") or [])]
    measured = facts.to_json()
    measured["patterns"] = patterns
    if not patterns:
        status_problems.append(f"{label}: 교차 출처 패턴이 선언되지 않았다 — 주장하지 않는다(INCONCLUSIVE)")
    elif facts.cross is None:
        status_problems.append(f"{label}: 교차 출처 측정 없음")
    else:
        cross = facts.cross
        resolved = cross.resolved_count()
        matches = cross.matching_labels(patterns)
        measured["unresolved_members"] = len(cross.unresolved_members(patterns))
        coverage = cross.covered / facts.count if facts.count else 0.0
        resolved_share = resolved / facts.count if facts.count else 0.0
        agreement = matches / resolved if resolved else 0.0
        if coverage < float(cross_rule.get("min_coverage", 0.95)):
            status_problems.append(
                f"{label}: 교차 출처 커버리지 {coverage:.3f} < {cross_rule.get('min_coverage', 0.95)}"
            )
        if resolved_share < float(cross_rule.get("min_resolved_share", 0.5)):
            status_problems.append(
                f"{label}: 해소된 이름 비율 {resolved_share:.3f} < {cross_rule.get('min_resolved_share', 0.5)}"
            )
        if agreement < float(cross_rule.get("min_agreement", 0.95)):
            status_problems.append(f"{label}: 패턴 일치율 {agreement:.3f} < {cross_rule.get('min_agreement', 0.95)}")
        measured["coverage"] = round(coverage, 4)
        measured["resolved_share"] = round(resolved_share, 4)
        measured["agreement"] = round(agreement, 4)
        measured["pattern_matches"] = matches

    integrity = Finding(
        f"group_integrity:{label}",
        not integrity_problems,
        f"{label}: 건수·join·중복 " + ("무결" if not integrity_problems else "; ".join(integrity_problems)),
        measured,
    )
    status = Finding(
        f"group_status:{label}",
        not status_problems,
        f"{label}: {'CONFIRMED' if not status_problems else 'INCONCLUSIVE'} · " + "; ".join(status_problems),
        measured,
        blocking=False,
    )
    return integrity, status


def circuit_decision(
    name: str, rule: Mapping[str, Any], groups: Mapping[str, Finding], mask: Mapping[str, Any]
) -> Finding:
    """회로 판정 — 두 세포군이 모두 CONFIRMED 이고 mask 에 근거가 있어야 한다.

    **pair 와 row 를 따로 잰다.** neuropil 행 수와 (pre,post) pair 수는 다르다(예: PN→KC
    행 22,569 vs pair 22,298). 둘을 한 숫자로 뭉개면 표 혼합이나 중복 계상을 놓친다.
    """

    problems: list[str] = []
    for role in ("pre_group", "post_group"):
        group = rule.get(role)
        finding = groups.get(str(group))
        if finding is None:
            problems.append(f"{name}: {role}={group} 판정 없음")
        elif not finding.ok:
            problems.append(f"{name}: {role}={group} 가 CONFIRMED 가 아니다")
    if not mask.get("pairs"):
        problems.append(f"{name}: mask pair 0건 — 근거가 없다")
    for label in ("pairs", "rows", "synapses"):
        expected = rule.get(f"expected_{label}")
        if expected is not None and mask.get(label) != expected:
            problems.append(_expected_problem(f"{name}.{label}", mask.get(label), expected))
    detail = f"{name}: {'CONFIRMED' if not problems else 'INCONCLUSIVE'} · " + "; ".join(problems)
    return Finding(f"circuit_annotation:{name}", not problems, detail, dict(mask))


def determine_exit(findings: Sequence[Finding]) -> int:
    """실패를 exit code 로 옮긴다. 순서는 FAILURE_EXIT_ORDER — 계약 숫자다.

    차단(blocking) 실패만 본다. `INCONCLUSIVE` 같은 비차단 사실은 exit 가 아니라
    manifest 의 status/checks 에 남는다(소비자가 그 값을 판단한다).
    """

    failing = [finding for finding in findings if not finding.ok and finding.blocking]
    if not failing:
        return EXIT_OK
    for check_id, code in FAILURE_EXIT_ORDER:
        if any(finding.check_id == check_id or finding.check_id.startswith(f"{check_id}:") for finding in failing):
            return code
    return EXIT_INCONCLUSIVE


# ────────────────────────────── manifest ──────────────────────────────
def assemble_manifest(
    expectations: Mapping[str, Any],
    measurement: Measurement,
    findings: Sequence[Finding],
    *,
    code_sha256: Mapping[str, str],
    generated_at: str,
    group_statuses: Mapping[str, str] | None = None,
    seed: Any = None,
) -> dict[str, Any]:
    status = "PASS" if all(finding.ok for finding in findings if finding.blocking) else "FAIL"
    statuses = dict(group_statuses or {})
    measures = {
        finding.check_id.split(":", 1)[1]: finding.measured
        for finding in findings
        if finding.check_id.startswith("group_status:")
    }
    groups = {
        label: {
            **facts.to_json(),
            **measures.get(label, {}),
            "status": statuses.get(label, "UNKNOWN"),
        }
        for label, facts in measurement.groups.items()
    }
    return {
        "manifest_version": MANIFEST_VERSION,
        "dataset_id": expectations["dataset_id"],
        "release": expectations["release"],
        "status": status,
        "generated_at": generated_at,
        "data_root": measurement.data_root,
        "reader": measurement.reader,
        "elapsed_seconds": measurement.elapsed_seconds,
        "inputs": {name: facts.to_json() for name, facts in sorted(measurement.files.items())},
        "annotation": {
            "version": expectations["release"],
            "source_table": "classification.csv.gz",
            "cross_source_table": "consolidated_cell_types.csv.gz",
            "groups": groups,
        },
        "filtering_rule": expectations["filtering_rule"],
        "unknown_nt_policy": expectations["unknown_nt_policy"],
        "root_id_index_mapping_sha256": measurement.root_id_index_mapping_sha256,
        "counts": {
            "nodes": None if measurement.neurons is None else measurement.neurons.distinct_ids,
            "directed_pairs": None if measurement.edges is None else measurement.edges.distinct_pairs,
            "synapses": None if measurement.edges is None else measurement.edges.synapses,
            "neuropil_rows": None if measurement.edges is None else measurement.edges.row_count,
            "edge_table": measurement.edge_table,
        },
        "skeleton": None if measurement.skeleton is None else measurement.skeleton.to_json(),
        "data_root_inventory": measurement.inventory,
        "license": expectations["license"],
        "code": dict(sorted(code_sha256.items())),
        "seed": seed,
        "seed_policy": "not_applicable: dataset 검증은 결정적이다(seed 없음)",
        "outputs": {},
        "checks": [finding.to_json() for finding in findings],
    }


SCHEMA_TYPES: Final[Mapping[str, tuple[type, ...]]] = {
    "object": (dict,),
    "array": (list,),
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "null": (type(None),),
}


def validate_against_schema(instance: Any, schema: Mapping[str, Any], path: str = "$") -> list[str]:
    """manifest.schema.json 을 재는 **최소** 검증기.

    jsonschema 패키지를 새 의존성으로 들이지 않기 위해, 스키마가 실제로 쓰는 키워드만
    지원한다(type·required·properties·items·enum·const·minItems·pattern·additionalProperties).
    스키마에 새 키워드를 쓰면 이 함수가 모르는 키로 남으므로, 지원 키 목록을 노출한다.
    """

    problems: list[str] = []
    if "const" in schema and instance != schema["const"]:
        problems.append(f"{path}: const {schema['const']!r} ≠ {instance!r}")
    if "enum" in schema and instance not in schema["enum"]:
        problems.append(f"{path}: {instance!r} 가 enum {schema['enum']} 에 없다")
    declared = schema.get("type")
    if declared is not None:
        names = [str(name) for name in declared] if isinstance(declared, list) else [str(declared)]
        unknown = [name for name in names if name not in SCHEMA_TYPES]
        if unknown:
            problems.append(f"{path}: 알 수 없는 type {unknown}")
        else:
            numeric = {"integer", "number"} & set(names)
            matched = any(isinstance(instance, SCHEMA_TYPES[name]) for name in names)
            if isinstance(instance, bool) and numeric and len(names) == 1:
                problems.append(f"{path}: boolean 은 {names[0]} 가 아니다")
                return problems
            if isinstance(instance, bool) and numeric and "boolean" not in names:
                problems.append(f"{path}: boolean 은 {names} 가 아니다")
                return problems
            if not matched:
                problems.append(f"{path}: {names} 기대, {type(instance).__name__} 관측")
                return problems
    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                problems.append(f"{path}.{key}: 필수 키 부재")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for key in instance:
                if key not in properties:
                    problems.append(f"{path}.{key}: 스키마에 없는 키")
        for key, subschema in properties.items():
            if key in instance:
                problems.extend(validate_against_schema(instance[key], subschema, f"{path}.{key}"))
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            problems.append(f"{path}: 항목 {len(instance)} < minItems {schema['minItems']}")
        items = schema.get("items")
        if isinstance(items, dict):
            for index, item in enumerate(instance):
                problems.extend(validate_against_schema(item, items, f"{path}[{index}]"))
    if isinstance(instance, str) and "pattern" in schema and not re.search(schema["pattern"], instance):
        problems.append(f"{path}: {instance!r} 가 pattern {schema['pattern']!r} 과 불일치")
    return problems


def supported_schema_keywords() -> set[str]:
    return {"type", "required", "properties", "items", "enum", "const", "minItems", "pattern", "additionalProperties"}


SCHEMA_MAP_KEYWORDS: Final = frozenset({"properties", "patternProperties", "$defs", "definitions", "dependentSchemas"})
SCHEMA_SINGLE_KEYWORDS: Final = frozenset(
    {"items", "additionalProperties", "not", "if", "then", "else", "contains", "propertyNames"}
)
SCHEMA_LIST_KEYWORDS: Final = frozenset({"allOf", "anyOf", "oneOf", "prefixItems"})


def collect_schema_keywords(schema: Any) -> set[str]:
    """스키마 **문맥**에서만 키워드를 모은다.

    단순히 모든 dict 키를 모으면 `properties` 아래의 속성 이름(`inputs`·`bytes` …)이
    키워드로 둔갑해 "검증기가 모르는 키워드"로 오판한다.
    """

    found: set[str] = set()
    if not isinstance(schema, dict):
        return found
    for key, value in schema.items():
        found.add(key)
        if key in SCHEMA_MAP_KEYWORDS and isinstance(value, dict):
            for sub in value.values():
                found |= collect_schema_keywords(sub)
        elif key in SCHEMA_SINGLE_KEYWORDS and isinstance(value, dict):
            found |= collect_schema_keywords(value)
        elif key in SCHEMA_LIST_KEYWORDS and isinstance(value, list):
            for sub in value:
                found |= collect_schema_keywords(sub)
    return found
