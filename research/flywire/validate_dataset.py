#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["duckdb>=1.1.0,<2.0"]
# ///
"""FlyWire 원자료 검증 — 측정만 하고, 판정은 `flywire_contract` 가 한다.

    uv run research/flywire/validate_dataset.py --data-root "$D" --output <E/task-25/manifest.json>

원자료(D)는 **읽기 전용**이다. 이 스크립트는 해시를 찍고 수치를 재고, 기대치와
다르면 nonzero 로 끝난다(`flywire_contract.EXIT_MEANINGS` 참조).

승인 흐름(입력 해시는 데이터가 아니라 **승인 시점**을 고정한다):

    1) 처음에는 `expected/<release>.json` 의 `approved_hashes` 가 비어 있다 → exit 6.
    2) 참조 수치가 전부 통과한 실행에서만 `--approve-hashes --reason "..."` 로 해시를 찍는다.
       (참조 수치가 틀린 실행은 승인할 수 없다 — 시험이 이 문을 잰다.)
    3) 이후 검증은 매번 해시를 다시 재서 비교한다. 한 바이트라도 다르면 exit 6 이고
       "새 dataset version 으로 취급하라"고 말한다.

거대 archive(skeleton zip, 약 13.8 GB)도 **일회성 I/O** 로 full hash 를 찍고 걸린 시간을
manifest 에 남긴다(`inputs[*].hash_seconds`).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:  # `python research/flywire/validate_dataset.py` 로도 돈다
    sys.path.insert(0, str(SCRIPT_DIR))

# `research/flywire` 는 패키지가 아니라 **스크립트 묶음**이다(PEP723). 그래서 형제 모듈을
# 스크립트 디렉터리 기준으로 import 한다 — `uv run research/flywire/validate_dataset.py`.
import flywire_contract as contract  # noqa: E402  # pyright: ignore[reportImplicitRelativeImport]
from flywire_contract import (  # noqa: E402  # pyright: ignore[reportImplicitRelativeImport]
    EXIT_RELEASE_MISMATCH,
    EXIT_USAGE,
    Measurement,
    build_group_facts,
    check_counts,
    check_duplicate_rows,
    check_fk,
    check_input_hashes,
    check_integer_ids,
    check_release_marker,
    check_required_inputs,
    check_skeleton,
    check_table_mixing,
    check_unique_ids,
    determine_exit,
    edges_from_facts,
    group_decision,
    neurons_from_facts,
    sha256_file,
    skeleton_from_facts,
    validate_against_schema,
)

TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FlyWire 원자료 검증(읽기 전용)")
    parser.add_argument("--data-root", required=True, type=Path, help="원자료 디렉터리(D)")
    parser.add_argument("--release", default="fafb_v783", help="release 식별자")
    parser.add_argument("--expectations", type=Path, default=None, help="expectations JSON 경로")
    parser.add_argument("--output", required=True, type=Path, help="manifest JSON 출력 경로")
    parser.add_argument("--reader", choices=("auto", "duckdb", "stdlib"), default="auto")
    parser.add_argument("--skip-hash", action="append", default=[], help="해시를 건너뛸 파일 이름")
    parser.add_argument(
        "--approve-hashes",
        action="store_true",
        help="참조 수치가 통과한 실행에서 입력 해시를 expectations 에 **승인**으로 찍는다",
    )
    parser.add_argument("--reason", default="", help="--approve-hashes 와 함께 쓰는 사유(필수)")
    parser.add_argument("--print-json", action="store_true", help="manifest 를 stdout 에도 낸다")
    return parser.parse_args(argv)


def resolve_expectations(args: argparse.Namespace) -> Path:
    if args.expectations is not None:
        return args.expectations
    return SCRIPT_DIR / "expected" / f"{args.release}.json"


def choose_reader(requested: str) -> str:
    if requested == "stdlib":
        return "stdlib"
    try:
        import flywire_scan_duckdb  # noqa: F401  # pyright: ignore[reportImplicitRelativeImport]
    except Exception:  # pragma: no cover - duckdb 미설치 환경
        if requested == "duckdb":
            raise SystemExit(f"{EXIT_USAGE}: --reader duckdb 를 쓸 수 없다(duckdb 미설치)")
        return "stdlib"
    return "duckdb"


def hash_inputs(
    root: Path, names: Sequence[str], skipped: Sequence[str]
) -> tuple[dict[str, contract.FileFacts], list[str]]:
    facts: dict[str, contract.FileFacts] = {}
    skipped_hits: list[str] = []
    for name in names:
        path = root / name
        if not path.is_file():
            continue
        if name in skipped:
            skipped_hits.append(name)
            continue
        digest, seconds = sha256_file(path)
        facts[name] = contract.FileFacts(path=name, bytes=path.stat().st_size, sha256=digest, hash_seconds=seconds)
    return facts, skipped_hits


def measure_duckdb(root: Path, expectations: dict[str, Any], edge_table: str) -> Measurement:
    import flywire_scan_duckdb as duck  # pyright: ignore[reportImplicitRelativeImport]

    tables = expectations["tables"]
    con = duck.connect()
    neurons_payload = duck.neurons_facts(con, root / tables["neurons"]["file"])
    id_facts = duck.id_column_facts(con, root / tables["neurons"]["file"], tables["neurons"]["id_column"])
    neuron_ids = set(neurons_payload["ids"])
    duck.load_id_table(con, sorted(neuron_ids))
    classification_payload = duck.classification_facts(
        con, root / tables["classification"]["file"], sorted(expectations["groups"]), duck._ID_TABLE
    )
    edges_payload = duck.edges_facts(con, root / edge_table, int(tables["edges"]["pair_threshold"]), duck._ID_TABLE)
    cross_rules = {label: rule.get("cross_source") or {} for label, rule in expectations["groups"].items()}
    cross_table = next((rule.get("table") for rule in cross_rules.values() if rule.get("table")), None)
    cross_column = next((rule.get("column") for rule in cross_rules.values() if rule.get("column")), None)
    cross_payload = {}
    if cross_table and cross_column:
        cross_payload = duck.cross_source_facts(
            con,
            root / cross_table,
            classification_payload["members"],
            cross_table,
            cross_column,
        )
    skeleton_payload = None
    skeleton_rule = expectations.get("skeleton") or {}
    if skeleton_rule.get("file") and (root / skeleton_rule["file"]).is_file():
        skeleton_payload = duck.skeleton_facts(root / skeleton_rule["file"], sorted(neuron_ids))
    return assemble_measurement(
        root,
        expectations,
        neurons_payload,
        id_facts,
        classification_payload,
        edges_payload,
        cross_payload,
        skeleton_payload,
        edge_table,
        reader="duckdb",
    )


def measure_stdlib(root: Path, expectations: dict[str, Any], edge_table: str) -> Measurement:
    tables = expectations["tables"]
    neurons_facts, id_facts = contract.scan_neurons_stdlib(root / tables["neurons"]["file"])
    neuron_ids = set(neurons_facts.ids)
    classification_facts, members = contract.scan_classification_stdlib(
        root / tables["classification"]["file"], sorted(expectations["groups"]), neuron_ids
    )
    edges_facts = contract.scan_edges_stdlib(root / edge_table, int(tables["edges"]["pair_threshold"]), neuron_ids)
    cross_payload: dict[str, contract.CrossSourceFacts] = {}
    cross_rule_pair: tuple[str, str] | None = next(
        (
            (str(rule["table"]), str(rule["column"]))
            for rule in (expectations["groups"][label].get("cross_source") or {} for label in expectations["groups"])
            if rule.get("table") and rule.get("column")
        ),
        None,
    )
    if cross_rule_pair:
        cross_table, cross_column = cross_rule_pair
        cross_payload = contract.scan_cross_source_stdlib(root / cross_table, members, cross_table, cross_column)
    skeleton_payload = None
    skeleton_rule = expectations.get("skeleton") or {}
    if skeleton_rule.get("file") and (root / skeleton_rule["file"]).is_file():
        skeleton_payload = contract.scan_skeleton_zip(root / skeleton_rule["file"], sorted(neuron_ids))
    measurement = Measurement(data_root=str(root), release=str(expectations["release"]), reader="stdlib")
    measurement.id_columns = {str(tables["neurons"]["file"]): id_facts}
    measurement.neurons = neurons_facts
    measurement.classification = classification_facts
    measurement.edges = edges_facts
    measurement.edge_table = edge_table
    measurement.skeleton = skeleton_payload
    measurement.groups = build_groups(expectations, members, neuron_ids, cross_payload)
    measurement.root_id_index_mapping_sha256 = contract.root_id_index_mapping_sha256(neurons_facts.ids)
    return measurement


def assemble_measurement(
    root: Path,
    expectations: dict[str, Any],
    neurons_payload: dict[str, Any],
    id_payload: dict[str, Any],
    classification_payload: dict[str, Any],
    edges_payload: dict[str, Any],
    cross_payload: dict[str, Any],
    skeleton_payload: dict[str, Any] | None,
    edge_table: str,
    *,
    reader: str,
) -> Measurement:
    measurement = Measurement(data_root=str(root), release=str(expectations["release"]), reader=reader)
    measurement.id_columns = {str(expectations["tables"]["neurons"]["file"]): contract.id_column_from_facts(id_payload)}
    measurement.neurons = neurons_from_facts(neurons_payload)
    measurement.classification = contract.classification_from_facts(classification_payload)
    measurement.edges = edges_from_facts(edges_payload)
    measurement.edge_table = edge_table
    if skeleton_payload is not None:
        measurement.skeleton = skeleton_from_facts(skeleton_payload)
    cross_facts = contract.cross_from_facts(cross_payload) if cross_payload else {}
    members = {
        str(label): [int(value) for value in values] for label, values in classification_payload["members"].items()
    }
    measurement.groups = build_groups(
        expectations, members, set(int(value) for value in neurons_payload["ids"]), cross_facts
    )
    measurement.root_id_index_mapping_sha256 = contract.root_id_index_mapping_sha256(
        (int(value) for value in neurons_payload["ids"])
    )
    return measurement


def build_groups(
    expectations: dict[str, Any],
    members: dict[str, list[int]],
    neuron_ids: set[int],
    cross_facts: dict[str, contract.CrossSourceFacts],
) -> dict[str, contract.GroupFacts]:
    groups: dict[str, contract.GroupFacts] = {}
    for label, rule in expectations["groups"].items():
        groups[label] = build_group_facts(
            label, rule, members.get(label, []), neuron_ids, cross_facts.get(label), members
        )
    return groups


def collect_findings(
    root: Path,
    expectations: dict[str, Any],
    measurement: Measurement,
    files: dict[str, contract.FileFacts],
) -> list[contract.Finding]:
    findings: list[contract.Finding] = []
    findings.append(check_required_inputs(root, expectations)[0])
    findings.append(check_release_marker(root, expectations))
    findings.append(check_input_hashes(expectations, files, root))
    findings.append(check_integer_ids(measurement))
    findings.append(check_unique_ids(measurement))
    findings.append(check_fk(measurement))
    findings.append(check_duplicate_rows(measurement))
    profiles = expectations["tables"].get("known_edge_profiles") or {}
    findings.append(check_table_mixing(expectations, measurement, profiles))
    findings.append(check_counts(expectations, measurement))
    findings.append(check_skeleton(expectations, measurement))
    for label, rule in expectations["groups"].items():
        facts = measurement.groups.get(label)
        if facts is None:
            findings.append(contract.Finding(f"group_integrity:{label}", False, f"{label}: 측정 없음"))
            findings.append(contract.Finding(f"group_status:{label}", False, f"{label}: 측정 없음(INCONCLUSIVE)"))
            continue
        integrity, status = group_decision(label, rule, facts)
        findings.append(integrity)
        findings.append(status)
    return findings


def code_hashes() -> dict[str, str]:
    hashes: dict[str, str] = {}
    for name in ("flywire_contract.py", "validate_dataset.py", "flywire_scan_duckdb.py", "manifest.schema.json"):
        path = SCRIPT_DIR / name
        if path.is_file():
            digest, _ = sha256_file(path)
            hashes[name] = digest
    return hashes


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    started = time.monotonic()
    root = args.data_root.resolve()
    expectations_path = resolve_expectations(args)
    if not expectations_path.is_file():
        print(f"{EXIT_USAGE}: expectations 파일이 없다: {expectations_path}", file=sys.stderr)
        return EXIT_USAGE
    expectations = contract.load_expectations(expectations_path)

    if args.approve_hashes and not args.reason.strip():
        print(f"{EXIT_USAGE}: --approve-hashes 에는 --reason 이 필요하다", file=sys.stderr)
        return EXIT_USAGE

    edge_table = str(expectations["tables"]["edges"]["file"])
    reader = choose_reader(args.reader)

    marker_files = [name for name in expectations.get("release_markers", {}).values() if isinstance(name, str)]
    hash_targets = list(dict.fromkeys([*expectations["required_inputs"], *marker_files, edge_table]))
    files, skipped = hash_inputs(root, hash_targets, args.skip_hash)

    if reader == "duckdb":
        measurement = measure_duckdb(root, expectations, edge_table)
    else:
        measurement = measure_stdlib(root, expectations, edge_table)
    measurement.files = files
    measurement.inventory = contract.data_root_inventory(root)
    measurement.elapsed_seconds = round(time.monotonic() - started, 3)

    findings = collect_findings(root, expectations, measurement, files)

    if args.approve_hashes:
        reference_ok = all(
            finding.ok
            for finding in findings
            if finding.blocking and finding.check_id not in {"input_hashes", "manifest_schema"}
        )
        if not reference_ok:
            print(
                f"{EXIT_RELEASE_MISMATCH}: 참조 수치가 통과하지 않아 해시를 승인할 수 없다 — 승인은 통과한 실행에서만",
                file=sys.stderr,
            )
            for finding in findings:
                if not finding.ok and finding.blocking:
                    print(f"  - {finding.check_id}: {finding.detail}", file=sys.stderr)
            return EXIT_RELEASE_MISMATCH
        updated = dict(expectations)
        updated["approved_hashes"] = {
            name: {"sha256": facts.sha256, "bytes": facts.bytes} for name, facts in sorted(files.items())
        }
        updated["approved_hashes_reason"] = args.reason.strip()
        updated["approved_hashes_at"] = datetime.now(UTC).strftime(TIMESTAMP_FORMAT)
        expectations_path.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"승인 해시 {len(files)}건을 {expectations_path} 에 기록했다(사유: {args.reason.strip()})")
        expectations = contract.load_expectations(expectations_path)
        findings = collect_findings(root, expectations, measurement, files)

    schema = json.loads((SCRIPT_DIR / "manifest.schema.json").read_text(encoding="utf-8"))
    unknown_keywords = (
        contract.collect_schema_keywords(schema)
        - contract.supported_schema_keywords()
        - {
            "$schema",
            "$id",
            "title",
            "description",
        }
    )
    manifest = contract.assemble_manifest(
        expectations,
        measurement,
        findings,
        code_sha256=code_hashes(),
        generated_at=datetime.now(UTC).strftime(TIMESTAMP_FORMAT),
        group_statuses={
            finding.check_id.split(":", 1)[1]: ("CONFIRMED" if finding.ok else "INCONCLUSIVE")
            for finding in findings
            if finding.check_id.startswith("group_status:")
        },
    )
    problems = validate_against_schema(manifest, schema)
    findings.append(
        contract.Finding(
            "manifest_schema",
            not problems,
            "; ".join(problems) or "schema 통과",
            {"unknown_keywords": sorted(unknown_keywords)},
        )
    )

    exit_code = determine_exit(findings)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for finding in findings:
        mark = "OK  " if finding.ok else "FAIL"
        print(f"{mark} {finding.check_id}: {finding.detail}")
    if skipped:
        print(f"SKIP 해시 건너뜀: {skipped}")
    print(
        f"reader={reader} · elapsed={measurement.elapsed_seconds}s · exit={exit_code} — {contract.EXIT_MEANINGS[exit_code]}"
    )
    if args.print_json:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
