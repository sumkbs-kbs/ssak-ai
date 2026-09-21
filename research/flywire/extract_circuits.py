#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["duckdb>=1.1.0,<2.0"]
# ///
"""회로 mask 추출 — 주석 근거가 있는 회로만 CONFIRMED, 아니면 INCONCLUSIVE.

    uv run research/flywire/extract_circuits.py \\
        --data-root "$D" --out-dir <E/task-25/artifacts/circuits> \\
        --output <E/task-25/circuits.json>

계약(상세안 §8-2):

  - 세포군은 **그 릴리스의 주석 컬럼(class)** 으로만 정의한다. label 이름이나 root_id
    크기로 추정하지 않는다.
  - 교차 출처(`consolidated_cell_types.primary_type`) 검증을 통과하지 못한 집단이 하나라도
    걸린 회로는 `INCONCLUSIVE` 다 — mask 를 만들어도 **주장하지 않는다**(파일은 남기고
    status 로 표시한다).
  - 검증 실패 보고와 그래프 수준 대조 실험은 별개다. 미실행 회로 실험을 성공으로 위장하지
    않는다: 그래서 이 스크립트는 **회로 실험 결과**가 아니라 **mask 와 그 근거**만 낸다.

exit: 0 = 요청 회로 전부 CONFIRMED · 10 = INCONCLUSIVE 있음 · 2/6/8 = 입력·release·무결성 실패.
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
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# `research/flywire` 는 패키지가 아니라 **스크립트 묶음**이다(PEP723) — 형제 모듈은
# 스크립트 디렉터리 기준으로 import 한다(`uv run research/flywire/extract_circuits.py`).
import flywire_contract as contract  # noqa: E402  # pyright: ignore[reportImplicitRelativeImport]
from flywire_contract import (  # noqa: E402  # pyright: ignore[reportImplicitRelativeImport]
    EXIT_USAGE,
    build_group_facts,
    circuit_decision,
    determine_exit,
    group_decision,
    sha256_file,
    validate_against_schema,
)

TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FlyWire 회로 mask 추출(읽기 전용)")
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--release", default="fafb_v783")
    parser.add_argument("--expectations", type=Path, default=None)
    parser.add_argument("--out-dir", required=True, type=Path, help="mask CSV 출력 디렉터리")
    parser.add_argument("--output", required=True, type=Path, help="작업 manifest JSON")
    parser.add_argument("--circuit", action="append", default=[], help="추출할 회로 이름(기본: 전부)")
    parser.add_argument("--reader", choices=("auto", "duckdb", "stdlib"), default="auto")
    return parser.parse_args(argv)


def choose_reader(requested: str) -> str:
    if requested == "stdlib":
        return "stdlib"
    try:
        import flywire_scan_duckdb  # noqa: F401  # pyright: ignore[reportImplicitRelativeImport]
    except Exception:
        if requested == "duckdb":
            raise SystemExit(f"{EXIT_USAGE}: --reader duckdb 를 쓸 수 없다(duckdb 미설치)")
        return "stdlib"
    return "duckdb"


def write_mask(
    out_dir: Path, name: str, rows: Sequence[tuple[int, int, int]], source_rows: int
) -> contract.CircuitMask:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.csv"
    lines = ["pre_root_id,post_root_id,syn_count"] + [f"{pre},{post},{syn}" for pre, post, syn in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    digest, _ = sha256_file(path)
    return contract.CircuitMask(
        name=name,
        file=path.name,
        pairs=len(rows),
        rows=source_rows,
        synapses=sum(syn for _, _, syn in rows),
        pre_nodes=len({pre for pre, _, _ in rows}),
        post_nodes=len({post for _, post, _ in rows}),
        output_sha256=digest,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    started = time.monotonic()
    root = args.data_root.resolve()
    expectations_path = args.expectations or SCRIPT_DIR / "expected" / f"{args.release}.json"
    if not expectations_path.is_file():
        print(f"{EXIT_USAGE}: expectations 파일이 없다: {expectations_path}", file=sys.stderr)
        return EXIT_USAGE
    expectations = contract.load_expectations(expectations_path)

    required = list(expectations["required_inputs"])
    missing = [name for name in required if not (root / name).is_file()]
    findings: list[contract.Finding] = [
        contract.Finding(
            "required_inputs",
            not missing,
            f"부재: {missing}" if missing else "필수 입력 3표 존재",
            {"missing": missing},
        )
    ]
    if missing:
        print(f"{contract.EXIT_INPUT_MISSING}: 부재 {missing}", file=sys.stderr)
        return contract.EXIT_INPUT_MISSING

    findings.append(contract.check_release_marker(root, expectations))
    reader = choose_reader(args.reader)

    files: dict[str, contract.FileFacts] = {}
    cross_table = next(
        (
            str(rule["cross_source"]["table"])
            for rule in expectations["groups"].values()
            if (rule.get("cross_source") or {}).get("table")
        ),
        None,
    )
    hash_targets = [*required, *([cross_table] if cross_table else [])]
    for name in dict.fromkeys(hash_targets):
        path = root / name
        if path.is_file():
            digest, seconds = sha256_file(path)
            files[name] = contract.FileFacts(path=name, bytes=path.stat().st_size, sha256=digest, hash_seconds=seconds)

    neurons_facts, id_facts = contract.scan_neurons_stdlib(root / expectations["tables"]["neurons"]["file"])
    neuron_ids = set(neurons_facts.ids)
    classification_facts, members = contract.scan_classification_stdlib(
        root / expectations["tables"]["classification"]["file"], sorted(expectations["groups"]), neuron_ids
    )
    cross_facts = (
        contract.scan_cross_source_stdlib(root / cross_table, members, cross_table, "primary_type")
        if cross_table
        else {}
    )

    measurement = contract.Measurement(data_root=str(root), release=str(expectations["release"]), reader=reader)
    measurement.id_columns = {str(expectations["tables"]["neurons"]["file"]): id_facts}
    measurement.neurons = neurons_facts
    measurement.classification = classification_facts
    measurement.files = files
    measurement.groups = {
        label: build_group_facts(label, rule, members.get(label, []), neuron_ids, cross_facts.get(label), members)
        for label, rule in expectations["groups"].items()
    }
    measurement.root_id_index_mapping_sha256 = contract.root_id_index_mapping_sha256(neurons_facts.ids)
    measurement.inventory = contract.data_root_inventory(root)

    findings.append(contract.check_integer_ids(measurement))
    findings.append(contract.check_unique_ids(measurement))

    group_findings: dict[str, contract.Finding] = {}
    for label, rule in expectations["groups"].items():
        integrity, status = group_decision(label, rule, measurement.groups[label])
        findings.append(integrity)
        findings.append(status)
        group_findings[label] = status

    recommended = args.circuit or sorted(name for name in expectations["circuits"] if not name.startswith("_"))
    for name in recommended:
        if name not in expectations["circuits"]:
            print(f"{EXIT_USAGE}: 알 수 없는 회로 {name}", file=sys.stderr)
            return EXIT_USAGE

    unresolved_ids = {
        label: (
            cross_facts[label].unresolved_members(
                [str(p) for p in ((rule.get("cross_source") or {}).get("patterns") or [])]
            )
            if label in cross_facts
            else set(members.get(label, []))
        )
        for label, rule in expectations["groups"].items()
    }

    selected_circuits = {name: expectations["circuits"][name] for name in recommended}
    if reader == "duckdb":
        import flywire_scan_duckdb as duck  # pyright: ignore[reportImplicitRelativeImport]

        masks, source_rows = duck.circuit_masks(
            duck.connect(),
            root / expectations["tables"]["edges"]["file"],
            selected_circuits,
            members,
            unresolved_ids,
        )
    else:
        masks, source_rows = contract.aggregate_masks(
            root / expectations["tables"]["edges"]["file"],
            selected_circuits,
            members,
            unresolved_ids,
        )
    circuit_facts: dict[str, dict[str, Any]] = {}
    for name in recommended:
        mask = write_mask(args.out_dir, name, masks[name], source_rows[name])
        mask.unresolved_endpoint_edges = sum(
            1
            for pre, post, _ in masks[name]
            if pre in unresolved_ids.get(str(selected_circuits[name]["pre_group"]), set())
            or post in unresolved_ids.get(str(selected_circuits[name]["post_group"]), set())
        )
        finding = circuit_decision(
            name,
            selected_circuits[name],
            group_findings,
            {"pairs": mask.pairs, "rows": mask.rows, "synapses": mask.synapses},
        )
        findings.append(finding)
        circuit_facts[name] = {
            **mask.to_json(),
            "status": "CONFIRMED" if finding.ok else "INCONCLUSIVE",
            "pre_group": selected_circuits[name]["pre_group"],
            "post_group": selected_circuits[name]["post_group"],
            "reason": finding.detail,
        }

    measurement.elapsed_seconds = round(time.monotonic() - started, 3)
    manifest = contract.assemble_manifest(
        expectations,
        measurement,
        findings,
        code_sha256={
            name: sha256_file(SCRIPT_DIR / name)[0]
            for name in ("flywire_contract.py", "extract_circuits.py")
            if (SCRIPT_DIR / name).is_file()
        },
        generated_at=datetime.now(UTC).strftime(TIMESTAMP_FORMAT),
        group_statuses={
            finding.check_id.split(":", 1)[1]: ("CONFIRMED" if finding.ok else "INCONCLUSIVE")
            for finding in findings
            if finding.check_id.startswith("group_status:")
        },
    )
    manifest["circuits"] = circuit_facts
    manifest["outputs"] = {name: facts["output_sha256"] for name, facts in circuit_facts.items()}
    manifest["limits"] = {
        "note": "파생물은 연구 산출물이다. 원자료는 Git·제품 패키지에 넣지 않는다.",
        "raw_data_included": False,
        "mask_bytes": sum((args.out_dir / facts["file"]).stat().st_size for facts in circuit_facts.values()),
    }
    schema = json.loads((SCRIPT_DIR / "manifest.schema.json").read_text(encoding="utf-8"))
    problems = validate_against_schema(manifest, schema)
    findings.append(contract.Finding("manifest_schema", not problems, "; ".join(problems) or "schema 통과", {}))
    exit_code = determine_exit(findings)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for finding in findings:
        print(f"{'OK  ' if finding.ok else 'FAIL'} {finding.check_id}: {finding.detail}")
    for name, facts in circuit_facts.items():
        print(
            f"     {name}: pairs={facts['pairs']} rows={facts['rows']} synapses={facts['synapses']} "
            f"pre={facts['pre_nodes']} post={facts['post_nodes']} unresolved_endpoint_edges={facts['unresolved_endpoint_edges']} "
            f"sha256={facts['output_sha256'][:16]}… status={facts['status']}"
        )
    print(
        f"reader={reader} · elapsed={measurement.elapsed_seconds}s · exit={exit_code} — {contract.EXIT_MEANINGS[exit_code]}"
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
