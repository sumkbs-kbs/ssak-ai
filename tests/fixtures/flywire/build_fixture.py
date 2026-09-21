"""FlyWire 계약 시험용 **작은** 원자료 fixture (표준 라이브러리만).

원자료(D, 약 17.5 GB)는 시험에 쓸 수 없다. 그래서 시험이 재는 것은 "실제 수치"가 아니라
**계약의 문**이다: float ID·중복 edge·누락 node·다른 release·표 혼합을 실제로 거절하는가,
정상 입력은 통과하는가, 행 순서가 달라도 같은 매핑 해시가 나오는가.

fixture 는 **생성물**이다(저장소에 gz 를 커밋하지 않는다). 각 fixture 디렉터리에는
`expected.json` 이 함께 생기고, 그 안의 `approved_hashes` 는 생성 직후의 파일 해시다 —
즉 이 fixture 에서는 "승인된 입력"이 성립한다.

ID 는 실제 root_id 범위(720575940…)를 쓴다. 계약이 ID 범위를 검사하므로, fixture 가
범위를 벗어나면 정상 fixture 가 거절돼 시험이 무의미해진다.
"""

from __future__ import annotations

import gzip
import json
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Any, cast

BASE_ID = 720575940600000000
THRESHOLD = 5

KINDS = [
    "normal",
    "shuffled",
    "float-id",
    "out-of-range-id",
    "dup-edge",
    "missing-node",
    "foreign-release",
    "mixed-table",
    "self-loop",
    "skeleton-mismatch",
    "cross-coverage",
    "cross-vocabulary",
    "table-swap",
]

NEURON_ROWS: list[tuple[int, str, str, float]] = [
    (BASE_ID + 1, "AL.LH", "ACH", 0.91),
    (BASE_ID + 2, "AL.LH", "ACH", 0.88),
    (BASE_ID + 3, "MB_CA", "ACH", 0.77),
    (BASE_ID + 4, "MB_CA", "GABA", 0.71),
    (BASE_ID + 5, "MB_CA", "ACH", 0.66),
    (BASE_ID + 6, "MB_ML", "", 0.0),
]

CLASS_ROWS = cast(
    "list[tuple[int, str, str, str | None, str]]",
    [
        (BASE_ID + 1, "intrinsic", "olfactory", "ALPN", "multiglomerular"),
        (BASE_ID + 2, "intrinsic", "olfactory", "ALPN", "uniglomerular"),
        (BASE_ID + 3, "intrinsic", "central", "Kenyon_Cell", "KCg"),
        (BASE_ID + 4, "intrinsic", "central", "Kenyon_Cell", None),
        (BASE_ID + 5, "intrinsic", "central", "MBON", None),
        (BASE_ID + 6, "intrinsic", "central", "MBIN", None),
    ],
)

CONSOLIDATED_ROWS: list[tuple[int, str]] = [
    (BASE_ID + 1, "DA1_lPN"),
    (BASE_ID + 2, "DL2d_adPN"),
    (BASE_ID + 3, "KCg-m"),
    (BASE_ID + 4, "KCab"),
    (BASE_ID + 5, "MBON10"),
    (BASE_ID + 6, "APL"),
]

# (pre, post, neuropil, syn) — pair 합 5 이상, 자기 연결 없음, 중복 행 없음.
EDGE_ROWS: list[tuple[int, int, str, int]] = [
    (BASE_ID + 1, BASE_ID + 3, "AL_L", 3),
    (BASE_ID + 1, BASE_ID + 3, "MB_CA", 4),
    (BASE_ID + 1, BASE_ID + 4, "AL_L", 5),
    (BASE_ID + 2, BASE_ID + 3, "AL_R", 5),
    (BASE_ID + 2, BASE_ID + 4, "AL_R", 6),
    (BASE_ID + 3, BASE_ID + 5, "MB_CA", 9),
    (BASE_ID + 4, BASE_ID + 5, "MB_ML", 5),
    (BASE_ID + 3, BASE_ID + 6, "MB_CA", 7),
    (BASE_ID + 4, BASE_ID + 6, "MB_ML", 8),
]

GROUP_RULES: dict[str, dict[str, object]] = {
    "ALPN": {
        "source_column": "class",
        "source_values": ["ALPN"],
        "count": 2,
        "cross_source": {
            "table": "consolidated_cell_types.csv.gz",
            "column": "primary_type",
            "patterns": ["PN"],
            "min_coverage": 0.95,
            "min_resolved_share": 0.5,
            "min_agreement": 0.95,
        },
    },
    "Kenyon_Cell": {
        "source_column": "class",
        "source_values": ["Kenyon_Cell"],
        "count": 2,
        "cross_source": {
            "table": "consolidated_cell_types.csv.gz",
            "column": "primary_type",
            "patterns": ["^KC"],
            "min_coverage": 0.95,
            "min_resolved_share": 0.95,
            "min_agreement": 0.95,
        },
    },
    "MBON": {
        "source_column": "class",
        "source_values": ["MBON"],
        "count": 1,
        "cross_source": {
            "table": "consolidated_cell_types.csv.gz",
            "column": "primary_type",
            "patterns": ["^MBON"],
            "min_coverage": 0.95,
            "min_resolved_share": 0.95,
            "min_agreement": 0.95,
        },
    },
    "MBIN": {
        "source_column": "class",
        "source_values": ["MBIN"],
        "count": 1,
        "cross_source": {
            "table": "consolidated_cell_types.csv.gz",
            "column": "primary_type",
            "patterns": [],
            "min_coverage": 0.95,
            "min_resolved_share": 0.5,
            "min_agreement": 0.95,
        },
    },
}


def as_dict(value: object) -> dict[str, Any]:
    """payload 는 dict[str, object] 라 중첩 접근에 좁히기가 필요하다(시험 코드의 형 검사용)."""

    assert isinstance(value, dict), f"dict 기대: {type(value).__name__}"
    return cast("dict[str, Any]", value)


def write_gz(path: Path, rows: list[list[str]]) -> None:
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        for row in rows:
            handle.write(",".join(row) + "\n")


def neurons_rows(*, float_id: bool = False, shuffle: bool = False, out_of_range: bool = False) -> list[list[str]]:
    rows = [["root_id", "group", "nt_type", "nt_type_score"]]
    data = list(NEURON_ROWS)
    if shuffle:
        data = [data[3], data[0], data[5], data[2], data[4], data[1]]
    for root_id, group, nt_type, score in data:
        token = str(root_id)
        if float_id and root_id == BASE_ID + 1:
            token = f"{root_id}.0"
        if out_of_range and root_id == BASE_ID + 6:
            token = "42"
        rows.append([token, group, nt_type, f"{score:.2f}"])
    return rows


def classification_rows() -> list[list[str]]:
    rows = [["root_id", "flow", "super_class", "class", "sub_class", "hemilineage", "side", "nerve"]]
    for root_id, flow, super_class, cls, sub_class in CLASS_ROWS:
        rows.append([str(root_id), flow, super_class, (cls or ""), (sub_class or ""), "", "left", ""])
    return rows


def consolidated_rows(*, missing_member: bool = False, wrong_vocabulary: bool = False) -> list[list[str]]:
    rows = [["root_id", "primary_type", "additional_type(s)"]]
    for root_id, primary in CONSOLIDATED_ROWS:
        if missing_member and root_id == BASE_ID + 4:
            continue
        if wrong_vocabulary and root_id == BASE_ID + 5:
            primary = "APL"
        rows.append([str(root_id), primary, ""])
    return rows


def edge_rows(
    *, duplicate: bool = False, missing_node: bool = False, mixed_table: bool = False, self_loop: bool = False
) -> list[list[str]]:
    rows = [["pre_root_id", "post_root_id", "neuropil", "syn_count", "nt_type"]]
    data = list(EDGE_ROWS)
    if duplicate:
        data.append(data[0])
    if missing_node:
        data.append((BASE_ID + 1, BASE_ID + 99, "AL_L", 5))
    if mixed_table:
        data.append((BASE_ID + 2, BASE_ID + 5, "AL_R", 1))
    if self_loop:
        data.append((BASE_ID + 1, BASE_ID + 1, "AL_L", 5))
    for pre, post, neuropil, syn in data:
        rows.append([str(pre), str(post), neuropil, str(syn), "ACH"])
    return rows


def write_expected(dest: Path, *, entries: int, extra: int, missing: int, allowed_edge_table: str) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "dataset_id": "flywire-fixture",
        "release": "fafb_v783",
        "release_markers": {
            "synapse_table": "fafb_v783_princeton_synapse_table.csv.gz",
            "skeleton_archive": "sk_lod1_783_healed.zip",
        },
        "release_must_contain": ["v783"],
        "required_inputs": ["neurons.csv.gz", "classification.csv.gz", "connections_princeton.csv.gz"],
        "allowed_edge_tables": [allowed_edge_table],
        "forbidden_edge_tables": {
            "connections_buhmann_no_threshold.csv.gz": "별도 데이터셋(Buhmann)",
        },
        "tables": {
            "neurons": {
                "file": "neurons.csv.gz",
                "rows": len(NEURON_ROWS),
                "distinct_ids": len(NEURON_ROWS),
                "id_column": "root_id",
                "nt_unknown": 1,
                "nt_low_confidence": 1,
                "nt_type_counts": {"ACH": 4, "GABA": 1, "(null)": 1},
            },
            "classification": {
                "file": "classification.csv.gz",
                "rows": len(CLASS_ROWS),
                "class_null": 0,
                "super_class_counts": {"central": 4, "olfactory": 2},
            },
            "edges": {
                "file": allowed_edge_table,
                "rows": None,
                "distinct_pairs": None,
                "synapses": None,
                "min_row_syn": 3,
                "max_row_syn": None,
                "min_pair_syn": 5,
                "pair_threshold": THRESHOLD,
                "neuropils": None,
                "self_pairs": 0,
                "duplicate_rows": 0,
                "fk_missing": 0,
            },
            "known_edge_profiles": {
                "connections_buhmann_no_threshold.csv.gz": {
                    "row_count": 16847997,
                    "synapses": 54492922,
                    "distinct_pairs": 15091983,
                }
            },
        },
        "filtering_rule": {
            "edge_table": allowed_edge_table,
            "pair_aggregation": "neuropil 행을 pair 로 합산",
            "threshold": THRESHOLD,
        },
        "unknown_nt_policy": "미상 유지(대체 금지)",
        "groups": GROUP_RULES,
        "circuits": {},
        "skeleton": {
            "file": "sk_lod1_783_healed.zip",
            "optional": False,
            "entries": entries,
            "swc_entries": entries,
            "extra_count": extra,
            "missing_count": missing,
        },
        "license": {
            "decision": "research_only_noncommercial_attribution",
            "license": "CC BY-NC 4.0",
            "evidence": ["fixture: 실제 배포 조건은 원문 확인"],
            "constraints": "fixture 는 제품/Git 에 들어가는 데이터가 아니다",
        },
        "approved_hashes": {},
    }
    (dest / "expected.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def write_skeleton(dest: Path, ids: list[int], extra_ids: list[str]) -> None:
    """skeleton zip — 남는 id(extra)를 넣어 'neuron 대비 추가'를 재현한다."""

    with zipfile.ZipFile(dest / "sk_lod1_783_healed.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for root_id in ids:
            archive.writestr(f"{root_id}.swc", "1 1 0 0 0 1 -1\n")
        for extra in extra_ids:
            archive.writestr(f"{extra}.swc", "1 1 0 0 0 1 -1\n")


def stamp_hashes(dest: Path, payload: dict[str, object]) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "research" / "flywire"))
    from flywire_contract import sha256_file  # noqa: PLC0415

    approved = {}
    required = cast("list[str]", payload["required_inputs"])
    markers = cast("dict[str, str]", payload["release_markers"])
    for name in sorted(set(required) | {str(value) for value in markers.values()}):
        path = dest / name
        if path.is_file():
            digest, _ = sha256_file(path)
            approved[name] = {"sha256": digest, "bytes": path.stat().st_size}
    payload["approved_hashes"] = approved
    payload["approved_hashes_reason"] = "fixture 생성 직후(빌더가 찍는다)"
    (dest / "expected.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build(kind: str, dest: Path) -> dict[str, object]:
    """fixture 하나를 만든다. kind: normal|shuffled|float-id|dup-edge|missing-node|foreign-release|mixed-table."""

    if kind not in KINDS:
        raise ValueError(f"알 수 없는 fixture: {kind}")
    dest.mkdir(parents=True, exist_ok=True)
    for stale in dest.iterdir():
        if stale.is_file():
            stale.unlink()

    edge_table = "connections_princeton.csv.gz"
    edge_data = edge_rows(
        duplicate=kind == "dup-edge",
        missing_node=kind == "missing-node",
        mixed_table=kind == "mixed-table",
        self_loop=kind == "self-loop",
    )
    write_gz(
        dest / "neurons.csv.gz",
        neurons_rows(
            float_id=kind == "float-id",
            shuffle=kind == "shuffled",
            out_of_range=kind == "out-of-range-id",
        ),
    )
    write_gz(dest / "classification.csv.gz", classification_rows())
    write_gz(dest / edge_table, edge_data)
    write_gz(
        dest / "consolidated_cell_types.csv.gz",
        consolidated_rows(
            missing_member=kind == "cross-coverage",
            wrong_vocabulary=kind == "cross-vocabulary",
        ),
    )
    extra_ids = ["720575940699999999"]
    if kind == "skeleton-mismatch":
        extra_ids.append("720575940699999998")
    write_skeleton(dest, [root_id for root_id, *_ in NEURON_ROWS], extra_ids)
    if kind != "foreign-release":
        (dest / "fafb_v783_princeton_synapse_table.csv.gz").write_bytes(b"fixture\n")

    payload = write_expected(
        dest,
        entries=len(NEURON_ROWS) + 1,
        extra=1,
        missing=0,
        allowed_edge_table=edge_table,
    )
    tables = payload["tables"]
    assert isinstance(tables, dict)
    edges = tables["edges"]
    assert isinstance(edges, dict)
    edges["rows"] = len(edge_data) - 1
    pairs = {(int(row[0]), int(row[1])) for row in edge_data[1:]}
    edges["distinct_pairs"] = len(pairs)
    edges["synapses"] = sum(int(row[3]) for row in edge_data[1:])
    edges["max_row_syn"] = max(int(row[3]) for row in edge_data[1:])
    edges["neuropils"] = len({row[2] for row in edge_data[1:]})
    if kind == "dup-edge":
        edges["duplicate_rows"] = edges_rows_duplicates(edge_data)
    if kind == "missing-node":
        edges["fk_missing"] = 1
    if kind == "skeleton-mismatch":
        # zip 에 남는 ID 가 2개인데 기대치는 1개로 둔다 — 이 시험의 사유를 skeleton 하나로 좁힌다.
        skeleton_rule = as_dict(payload["skeleton"])
        skeleton_rule["entries"] = len(NEURON_ROWS) + len(extra_ids)
        skeleton_rule["swc_entries"] = len(NEURON_ROWS) + len(extra_ids)
        skeleton_rule["extra_count"] = 1
    payload["approved_hashes"] = {}
    (dest / "expected.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    stamp_hashes(dest, payload)
    if kind in {"dup-edge", "missing-node", "mixed-table", "self-loop", "table-swap"}:
        rewrite_with_observed_counts(dest, payload)
    if kind == "table-swap":
        # 이름은 thresholded 인데 수치 프로필이 **다른 표**와 같다 — 바꿔치기 검출을 겨눈다.
        tables = payload["tables"]
        assert isinstance(tables, dict)
        profiles = tables["known_edge_profiles"]
        assert isinstance(profiles, dict)
        observed = tables["edges"]
        assert isinstance(observed, dict)
        profiles["connections_princeton_no_threshold.csv.gz"] = {
            "row_count": observed["rows"],
            "synapses": observed["synapses"],
            "distinct_pairs": observed["distinct_pairs"],
        }
        (dest / "expected.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        stamp_hashes(dest, payload)
    return payload


def edges_rows_duplicates(edge_data: list[list[str]]) -> int:
    seen: set[tuple[str, str, str]] = set()
    duplicates = 0
    for row in edge_data[1:]:
        signature = (row[0], row[1], row[2])
        if signature in seen:
            duplicates += 1
        seen.add(signature)
    return duplicates


def rewrite_with_observed_counts(dest: Path, payload: dict[str, object]) -> None:
    """거절 fixture 는 '정상 기대치'가 아니라 **관측치**를 기대치로 둔다.

    계약은 (a) 중복/누락/혼합을 먼저 거절하고, (b) 수치 불일치는 뒤에 본다. 거절
    fixture 에 정상 수치를 넣으면 두 사유가 섞여 어느 문이 실제로 잠갔는지 알 수 없다.
    그래서 관측 수치를 넣고, 거절 사유가 **하나로 좁혀지는지**를 시험이 확인한다.
    """

    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "research" / "flywire"))
    from flywire_contract import scan_edges_stdlib, scan_neurons_stdlib  # noqa: PLC0415

    tables = payload["tables"]
    assert isinstance(tables, dict)
    edges_rule = tables["edges"]
    assert isinstance(edges_rule, dict)
    neurons_rule = tables["neurons"]
    assert isinstance(neurons_rule, dict)

    neurons_facts, _ = scan_neurons_stdlib(dest / "neurons.csv.gz")
    known = set(neurons_facts.ids)
    facts = scan_edges_stdlib(dest / str(edges_rule["file"]), THRESHOLD, known)
    edges_rule["rows"] = facts.row_count
    edges_rule["distinct_pairs"] = facts.distinct_pairs
    edges_rule["synapses"] = facts.synapses
    edges_rule["max_row_syn"] = facts.max_row_syn
    edges_rule["min_row_syn"] = facts.min_row_syn
    edges_rule["neuropils"] = facts.neuropils
    edges_rule["self_pairs"] = facts.self_pairs
    edges_rule["duplicate_rows"] = facts.duplicate_rows
    edges_rule["min_pair_syn"] = facts.min_pair_syn
    neurons_rule["nt_type_counts"] = neurons_facts.nt_type_counts
    (dest / "expected.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    stamp_hashes(dest, payload)


def build_all(root: Path) -> dict[str, Path]:
    if root.exists():
        shutil.rmtree(root)
    return {kind: (build(kind, root / kind), root / kind)[1] for kind in KINDS}


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "tmp-flywire-fixtures")
    built = build_all(target)
    for kind, path in built.items():
        print(f"{kind}: {path}")
