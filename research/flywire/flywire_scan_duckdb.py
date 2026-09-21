"""duckdb 스캐너 — `flywire_contract` 의 사실 자료형을 **같은 모양**으로 채운다.

stdlib 스캐너와 결과가 같아야 한다(계약 시험이 작은 fixture 로 두 경로를 비교한다).
원자료(약 17.5 GB gz)에서 stdlib streaming 은 분 단위가 걸리지만 duckdb 는 초 단위라,
실행 경로는 이 스캐너를 쓰고 fixture·시험 경로는 stdlib 를 쓴다.

ID 집합은 **임시 표**로 만든다. 139,255개 ID 를 VALUES 리스트로 펼치면 SQL 문자열이
수 MB 가 되므로, 원자료 크기에서도 안전한 경로는 표다.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any, Mapping, Sequence

import duckdb

_THREADS = 4
_MEMORY_LIMIT = "3GB"
_ID_TABLE = "neuron_ids"
_ROOT_ID_MIN = 720575940000000000
_ROOT_ID_MAX = 2**63

INTEGRAL_TYPES = ("BIGINT", "INTEGER", "HUGEINT", "UBIGINT", "SMALLINT", "TINYINT")


def connect(memory_limit: str = _MEMORY_LIMIT) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(f"SET threads={_THREADS};")
    con.execute(f"SET memory_limit='{memory_limit}';")
    return con


def csv_sql(path: Path) -> str:
    return f"read_csv_auto('{path.as_posix()}')"


def load_id_table(con: duckdb.DuckDBPyConnection, ids: Sequence[int], name: str = _ID_TABLE) -> str:
    con.execute(f"CREATE OR REPLACE TEMP TABLE {name} (id BIGINT)")
    if ids:
        con.executemany(f"INSERT INTO {name} VALUES (?)", [(int(value),) for value in ids])
    return name


def column_types(con: duckdb.DuckDBPyConnection, path: Path, columns: Sequence[str]) -> dict[str, str]:
    described = con.execute(f"DESCRIBE SELECT * FROM {csv_sql(path)}").fetchall()
    found = {row[0]: row[1] for row in described}
    return {name: found.get(name, "MISSING") for name in columns}


def id_column_facts(con: duckdb.DuckDBPyConnection, path: Path, column: str) -> dict[str, Any]:
    declared = column_types(con, path, [column])[column]
    result: dict[str, Any] = {
        "column": column,
        "declared_type": declared,
        "non_integral": 0,
        "out_of_range": 0,
        "sample_non_integral": [],
    }
    if not declared.startswith(INTEGRAL_TYPES):
        result["non_integral"] = con.execute(
            f"SELECT count(*) FROM {csv_sql(path)} WHERE {column} IS NOT NULL"
        ).fetchone()[0]
        sample = con.execute(f"SELECT {column} FROM {csv_sql(path)} LIMIT 3").fetchall()
        result["sample_non_integral"] = [str(row[0]) for row in sample]
        return result
    result["out_of_range"] = con.execute(
        f"SELECT count(*) FROM {csv_sql(path)} WHERE {column} < {_ROOT_ID_MIN} OR {column} >= {_ROOT_ID_MAX}"
    ).fetchone()[0]
    return result


def neurons_facts(con: duckdb.DuckDBPyConnection, path: Path, with_ids: bool = True) -> dict[str, Any]:
    row = con.execute(
        f"""SELECT count(*), count(DISTINCT root_id),
                   count(*) FILTER (WHERE nt_type IS NULL),
                   count(*) FILTER (WHERE nt_type_score < 0.5)
            FROM {csv_sql(path)}"""
    ).fetchone()
    nt_counts = {
        str(nt_type): count
        for nt_type, count in con.execute(
            f"SELECT coalesce(nt_type, '(null)'), count(*) FROM {csv_sql(path)} GROUP BY 1"
        ).fetchall()
    }
    ids: list[int] = []
    if with_ids:
        ids = [int(row[0]) for row in con.execute(f"SELECT root_id FROM {csv_sql(path)}").fetchall()]
    return {
        "row_count": row[0],
        "distinct_ids": row[1],
        "nt_unknown": row[2],
        "nt_low_confidence": row[3],
        "nt_type_counts": nt_counts,
        "ids": ids,
    }


def classification_facts(
    con: duckdb.DuckDBPyConnection, path: Path, wanted: Sequence[str], id_table: str | None
) -> dict[str, Any]:
    row = con.execute(
        f"""SELECT count(*), count(DISTINCT root_id), count(*) FILTER (WHERE class IS NULL)
            FROM {csv_sql(path)}"""
    ).fetchone()
    super_counts = {
        str(super_class): count
        for super_class, count in con.execute(
            f"SELECT coalesce(super_class, '(null)'), count(*) FROM {csv_sql(path)} GROUP BY 1"
        ).fetchall()
    }
    outside = 0
    if id_table is not None:
        outside = con.execute(
            f"""SELECT count(*) FROM {csv_sql(path)} c
                WHERE NOT EXISTS (SELECT 1 FROM {id_table} v WHERE v.id = c.root_id)"""
        ).fetchone()[0]
    members = {
        label: [
            int(value[0])
            for value in con.execute(f"SELECT root_id FROM {csv_sql(path)} WHERE class = ?", [label]).fetchall()
        ]
        for label in wanted
    }
    return {
        "row_count": row[0],
        "distinct_ids": row[1],
        "class_null": row[2],
        "super_class_counts": super_counts,
        "ids_outside_neurons": outside,
        "members": members,
    }


def edges_facts(con: duckdb.DuckDBPyConnection, path: Path, threshold: int, id_table: str | None) -> dict[str, Any]:
    row = con.execute(
        f"""SELECT count(*), count(DISTINCT (pre_root_id, post_root_id)), sum(syn_count),
                   min(syn_count), max(syn_count),
                   count(*) FILTER (WHERE pre_root_id = post_root_id), count(DISTINCT neuropil)
            FROM {csv_sql(path)}"""
    ).fetchone()
    duplicate_rows = con.execute(
        f"""SELECT count(*) FROM (
                SELECT pre_root_id, post_root_id, neuropil FROM {csv_sql(path)}
                GROUP BY 1,2,3 HAVING count(*) > 1)"""
    ).fetchone()[0]
    pair = con.execute(
        f"""SELECT min(s), count(*) FILTER (WHERE s < {threshold}) FROM (
                SELECT sum(syn_count) s FROM {csv_sql(path)} GROUP BY pre_root_id, post_root_id)"""
    ).fetchone()
    facts: dict[str, Any] = {
        "row_count": row[0],
        "distinct_pairs": row[1],
        "synapses": int(row[2] or 0),
        "min_row_syn": row[3],
        "max_row_syn": row[4],
        "self_pairs": row[5],
        "neuropils": row[6],
        "duplicate_rows": duplicate_rows,
        "min_pair_syn": pair[0],
        "pairs_below_threshold": pair[1],
        "fk_missing_pre": 0,
        "fk_missing_post": 0,
        "unreadable_rows": 0,
    }
    if id_table is not None:
        facts["fk_missing_pre"] = con.execute(
            f"""SELECT count(*) FROM {csv_sql(path)} e
                WHERE NOT EXISTS (SELECT 1 FROM {id_table} v WHERE v.id = e.pre_root_id)"""
        ).fetchone()[0]
        facts["fk_missing_post"] = con.execute(
            f"""SELECT count(*) FROM {csv_sql(path)} e
                WHERE NOT EXISTS (SELECT 1 FROM {id_table} v WHERE v.id = e.post_root_id)"""
        ).fetchone()[0]
    return facts


def cross_source_facts(
    con: duckdb.DuckDBPyConnection,
    path: Path,
    members: Mapping[str, Sequence[int]],
    table_name: str,
    column: str,
) -> dict[str, dict[str, Any]]:
    """집단별 label 별 건수 — '해소/패턴 일치'의 판정은 계약이 한다."""

    result: dict[str, dict[str, Any]] = {}
    for label, ids in members.items():
        bucket: dict[str, Any] = {"table": table_name, "column": column, "covered": 0, "member_labels": {}}
        if ids:
            table = load_id_table(con, list(ids))
            bucket["covered"] = con.execute(
                f"SELECT count(*) FROM {csv_sql(path)} ct JOIN {table} v ON v.id = ct.root_id"
            ).fetchone()[0]
            bucket["member_labels"] = {
                int(root_id): ("(empty)" if name is None or not str(name).strip() else str(name))
                for root_id, name in con.execute(
                    f"SELECT ct.root_id, ct.{column} FROM {csv_sql(path)} ct JOIN {table} v ON v.id = ct.root_id"
                ).fetchall()
            }
        result[label] = bucket
    return result


def circuit_masks(
    con: duckdb.DuckDBPyConnection,
    path: Path,
    circuits: Mapping[str, Mapping[str, str]],
    members: Mapping[str, Sequence[int]],
    unresolved: Mapping[str, set[int]],
) -> tuple[dict[str, list[tuple[int, int, int]]], dict[str, int]]:
    """mask 를 SQL 로 만든다(원자료 5.3M 행에서 stdlib streaming 은 분 단위).

    `rows` 를 함께 세는 이유: pair 와 row 를 혼동하지 않기 위해서다(계약 §filtering_rule).
    """

    masks: dict[str, list[tuple[int, int, int]]] = {}
    row_counts: dict[str, int] = {}
    for name, rule in circuits.items():
        pre_ids = list(members.get(str(rule["pre_group"]), []))
        post_ids = list(members.get(str(rule["post_group"]), []))
        if not pre_ids or not post_ids:
            masks[name] = []
            row_counts[name] = 0
            continue
        pre_table = load_id_table(con, pre_ids, "pre_ids")
        post_table = load_id_table(con, post_ids, "post_ids")
        rows = con.execute(
            f"""SELECT e.pre_root_id, e.post_root_id, sum(e.syn_count) AS syn_count, count(*) AS row_count
                FROM {csv_sql(path)} e
                JOIN {pre_table} a ON a.id = e.pre_root_id
                JOIN {post_table} b ON b.id = e.post_root_id
                GROUP BY 1, 2 ORDER BY 1, 2"""
        ).fetchall()
        masks[name] = [(int(pre), int(post), int(syn)) for pre, post, syn, _ in rows]
        row_counts[name] = sum(int(count) for _, _, _, count in rows)
    return masks, row_counts


def unresolved_endpoint_edges(
    masks: Mapping[str, Sequence[tuple[int, int, int]]],
    circuits: Mapping[str, Mapping[str, str]],
    unresolved: Mapping[str, set[int]],
) -> dict[str, int]:
    return {
        name: sum(
            1
            for pre, post, _ in rows
            if pre in unresolved.get(str(rule["pre_group"]), set())
            or post in unresolved.get(str(rule["post_group"]), set())
        )
        for name, rows in masks.items()
        for rule in [circuits[name]]
    }


def swc_names(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        return [name for name in archive.namelist() if name.endswith(".swc")]


def skeleton_facts(path: Path, neuron_ids: Sequence[int]) -> dict[str, Any]:
    known = {str(root_id) for root_id in neuron_ids}
    extra_ids: list[str] = []
    entries = 0
    swc_entries = 0
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            entries += 1
            if name.endswith(".swc"):
                swc_entries += 1
                stem = Path(name).stem
                if stem not in known and stem.isdigit():
                    extra_ids.append(stem)
    extra_ids.sort()
    missing = sorted(known - {Path(name).stem for name in swc_names(path)})
    return {
        "path": path.name,
        "entries": entries,
        "swc_entries": swc_entries,
        "extra_ids": extra_ids,
        "missing_ids": missing,
    }
