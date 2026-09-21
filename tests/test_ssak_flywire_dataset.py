"""task 25 계약 시험 — FlyWire 재현 dataset 의 **문**을 잰다.

원자료(17.5 GB)는 시험에 쓸 수 없다. 그래서 시험은 실제 수치가 아니라 계약을 잰다:

  1. 정상 fixture 는 통과하고 manifest 가 schema·수치·매핑 해시를 갖춘다.
     (세포군 INCONCLUSIVE 는 **검증 실패가 아니다** — 데이터 무결성과 주장 가능성은 다르다.)
  2. float ID · 중복 edge · 누락 node · 다른 release · 표 혼합은 **각각 다른 exit code** 로
     거절되고, 그 실행에서 **겨눈 검사만** 실패한다(사유가 하나로 좁혀진다).
  3. 입력이 승인 이후 한 바이트라도 바뀌면 exit 6 이고 "새 dataset version" 이라 말한다.
  4. 승인(`--approve-hashes`)은 **참조 수치가 통과한 실행에서만** 가능하다.
  5. 행 순서가 달라도 root_id→index 매핑 해시가 같다(재현성).
  6. duckdb 경로와 stdlib 경로가 **같은 사실**을 낸다(두 스캐너의 계약).
  7. manifest.schema.json 의 모든 키워드를 stdlib 검증기가 지원한다(검증기와 스키마의 계약).
"""

from __future__ import annotations

import gzip
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parents[1]
FLYWIRE_DIR = ROOT / "research" / "flywire"
FIXTURE_BUILDER = ROOT / "tests" / "fixtures" / "flywire" / "build_fixture.py"
VALIDATOR = FLYWIRE_DIR / "validate_dataset.py"

sys.path.insert(0, str(FLYWIRE_DIR))
sys.path.insert(0, str(FIXTURE_BUILDER.parent))

import build_fixture  # noqa: E402
import flywire_contract as contract  # noqa: E402


def run_validator(fixture: Path, output: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--data-root",
            str(fixture),
            "--expectations",
            str(fixture / "expected.json"),
            "--output",
            str(output),
            "--reader",
            "stdlib",
            *extra,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture(scope="session")
def fixtures(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("flywire-fixtures")
    return build_fixture.build_all(root)


def manifest_of(output: Path) -> dict[str, object]:
    return cast("dict[str, object]", json.loads(output.read_text(encoding="utf-8")))


def as_dict(value: object) -> dict[str, Any]:
    assert isinstance(value, dict), f"dict 기대: {type(value).__name__}"
    return cast("dict[str, Any]", value)


def failing_checks(manifest: dict[str, object]) -> list[str]:
    """run 을 실패시킨 검사만 — 비차단 `INCONCLUSIVE` 사실은 빼고 본다."""

    checks = manifest["checks"]
    assert isinstance(checks, list)
    return [str(check["check"]) for check in checks if not check["ok"] and bool(check.get("blocking", True))]


def primary_failure(manifest: dict[str, object]) -> str:
    """exit code 를 결정한 검사 — FAILURE_EXIT_ORDER 의 첫 번째 실패.

    스키마 위반은 **연쇄**한다: float ID 하나가 노드를 못 읽게 만들어 FK·집단·수치 검사까지
    실패시킨다. 그래서 거절 fixture 에서 물어야 하는 것은 "실패가 몇 개인가"가 아니라
    "**주된 사유**가 겨눈 검사인가"다(exit code 가 그 증거다).
    """

    failures = set(failing_checks(manifest))
    for check_id, _ in contract.FAILURE_EXIT_ORDER:
        hits = [name for name in failures if name == check_id or name.startswith(f"{check_id}:")]
        if hits:
            return sorted(hits)[0]
    return ""


def test_normal_fixture_passes_and_manifest_matches_schema(fixtures: dict[str, Path], tmp_path: Path) -> None:
    output = tmp_path / "manifest.json"
    result = run_validator(fixtures["normal"], output)
    assert result.returncode == contract.EXIT_OK, result.stdout + result.stderr
    manifest = manifest_of(output)

    schema = json.loads((FLYWIRE_DIR / "manifest.schema.json").read_text(encoding="utf-8"))
    assert contract.validate_against_schema(manifest, schema) == []

    assert manifest["status"] == "PASS"
    assert manifest["counts"] == {
        "nodes": 6,
        "directed_pairs": 8,
        "synapses": 52,
        "neuropil_rows": 9,
        "edge_table": "connections_princeton.csv.gz",
    }
    assert manifest["root_id_index_mapping_sha256"] == contract.root_id_index_mapping_sha256(
        [720575940600000000 + index for index in range(1, 7)]
    )
    assert manifest["license"]["license"] == "CC BY-NC 4.0"
    assert manifest["seed"] is None
    annotation = as_dict(manifest["annotation"])
    groups = as_dict(annotation["groups"])
    assert as_dict(groups["Kenyon_Cell"])["status"] == "CONFIRMED"
    assert as_dict(groups["MBIN"])["status"] == "INCONCLUSIVE", "패턴이 선언되지 않은 집단은 주장할 수 없다"
    mbin = next(
        check for check in cast("list[dict[str, Any]]", manifest["checks"]) if check["check"] == "group_status:MBIN"
    )
    assert mbin["ok"] is False, "INCONCLUSIVE 는 체크 결과로도 보인다"
    skeleton = as_dict(manifest["skeleton"])
    assert skeleton["extra_count"] == 1 and skeleton["missing_count"] == 0


def test_row_order_does_not_change_the_mapping_hash(fixtures: dict[str, Path], tmp_path: Path) -> None:
    first = tmp_path / "ordered.json"
    second = tmp_path / "shuffled.json"
    assert run_validator(fixtures["normal"], first).returncode == contract.EXIT_OK
    assert run_validator(fixtures["shuffled"], second).returncode == contract.EXIT_OK
    ordered = manifest_of(first)
    shuffled = manifest_of(second)
    assert ordered["root_id_index_mapping_sha256"] == shuffled["root_id_index_mapping_sha256"]
    assert ordered["counts"] == shuffled["counts"]


CASCADING = {"float-id", "out-of-range-id"}


@pytest.mark.parametrize(
    ("fixture", "expected_exit", "target_check"),
    [
        ("float-id", contract.EXIT_SCHEMA_VIOLATION, "integer_ids"),
        ("out-of-range-id", contract.EXIT_SCHEMA_VIOLATION, "integer_ids"),
        ("dup-edge", contract.EXIT_DUPLICATE_EDGE, "no_duplicate_rows"),
        ("missing-node", contract.EXIT_FK_VIOLATION, "fk_neurons"),
        ("foreign-release", contract.EXIT_RELEASE_MISMATCH, "release_marker"),
        ("mixed-table", contract.EXIT_TABLE_MIXING, "table_not_mixed"),
        ("self-loop", contract.EXIT_TABLE_MIXING, "table_not_mixed"),
        ("skeleton-mismatch", contract.EXIT_COUNT_MISMATCH, "skeleton_consistency"),
        ("table-swap", contract.EXIT_TABLE_MIXING, "table_not_mixed"),
    ],
)
def test_rejections_are_targeted(
    fixtures: dict[str, Path], tmp_path: Path, fixture: str, expected_exit: int, target_check: str
) -> None:
    output = tmp_path / f"{fixture}.json"
    result = run_validator(fixtures[fixture], output)
    assert result.returncode == expected_exit, result.stdout + result.stderr
    manifest = manifest_of(output)
    assert manifest["status"] == "FAIL"
    failures = failing_checks(manifest)
    assert target_check in failures, failures
    assert primary_failure(manifest) == target_check, f"주된 사유가 겨눈 검사여야 한다: {failures}"
    if fixture not in CASCADING:
        assert set(failures) == {target_check}, f"사유가 하나로 좁혀져야 한다: {failures}"


@pytest.mark.parametrize(
    ("fixture", "group", "expect_in_detail"),
    [
        ("cross-coverage", "Kenyon_Cell", "커버리지"),
        ("cross-vocabulary", "MBON", "패턴 일치율"),
    ],
)
def test_vocabulary_or_coverage_gaps_make_a_group_inconclusive(
    fixtures: dict[str, Path], tmp_path: Path, fixture: str, group: str, expect_in_detail: str
) -> None:
    """주석 근거가 부족한 집단은 CONFIRMED 가 아니다 — 데이터는 무결하므로 run 은 통과한다."""

    output = tmp_path / f"{fixture}.json"
    result = run_validator(fixtures[fixture], output)
    assert result.returncode == contract.EXIT_OK, result.stdout + result.stderr
    manifest = manifest_of(output)
    assert failing_checks(manifest) == [], "근거 부족은 검증 실패가 아니다"
    status = next(
        check for check in cast("list[dict[str, Any]]", manifest["checks"]) if check["check"] == f"group_status:{group}"
    )
    assert status["ok"] is False
    assert expect_in_detail in status["detail"]
    annotation = as_dict(manifest["annotation"])
    group_entry = as_dict(as_dict(annotation["groups"]).get(group, {}))
    assert group_entry["status"] == "INCONCLUSIVE"


def test_unapproved_input_drift_is_refused_as_a_new_dataset_version(fixtures: dict[str, Path], tmp_path: Path) -> None:
    tampered = tmp_path / "tampered"
    shutil.copytree(fixtures["normal"], tampered)
    raw = gzip.decompress((tampered / "neurons.csv.gz").read_bytes())
    changed = raw.replace(b"720575940600000006,MB_ML,,0.00", b"720575940600000006,MB_ML,,0.01")
    assert changed != raw
    (tampered / "neurons.csv.gz").write_bytes(gzip.compress(changed))

    output = tmp_path / "drift.json"
    result = run_validator(tampered, output)
    assert result.returncode == contract.EXIT_RELEASE_MISMATCH
    manifest = manifest_of(output)
    assert failing_checks(manifest) == ["input_hashes"]
    detail = next(
        check["detail"]
        for check in cast("list[dict[str, Any]]", manifest["checks"])
        if check["check"] == "input_hashes"
    )
    assert "새 dataset version" in detail


def test_unstamped_expectations_are_refused(fixtures: dict[str, Path], tmp_path: Path) -> None:
    unstamped = tmp_path / "unstamped"
    shutil.copytree(fixtures["normal"], unstamped)
    payload = json.loads((unstamped / "expected.json").read_text(encoding="utf-8"))
    payload["approved_hashes"] = {}
    (unstamped / "expected.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    output = tmp_path / "unstamped.json"
    result = run_validator(unstamped, output)
    assert result.returncode == contract.EXIT_RELEASE_MISMATCH
    assert failing_checks(manifest_of(output)) == ["input_hashes"]


def test_approval_requires_reason_and_a_passing_measurement(fixtures: dict[str, Path], tmp_path: Path) -> None:
    target = tmp_path / "approve"
    shutil.copytree(fixtures["normal"], target)
    payload = json.loads((target / "expected.json").read_text(encoding="utf-8"))

    payload["approved_hashes"] = {}
    (target / "expected.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    no_reason = run_validator(target, tmp_path / "no-reason.json", "--approve-hashes")
    assert no_reason.returncode == contract.EXIT_USAGE
    assert "reason" in no_reason.stderr

    approved = run_validator(
        target, tmp_path / "approved.json", "--approve-hashes", "--reason", "계약 시험: 정상 fixture"
    )
    assert approved.returncode == contract.EXIT_OK, approved.stdout + approved.stderr
    stamped = json.loads((target / "expected.json").read_text(encoding="utf-8"))
    assert stamped["approved_hashes"], "승인 실행은 해시를 남긴다"
    assert stamped["approved_hashes_reason"] == "계약 시험: 정상 fixture"
    assert run_validator(target, tmp_path / "after.json").returncode == contract.EXIT_OK

    broken = tmp_path / "brokendata"
    shutil.copytree(fixtures["normal"], broken)
    broken_expectations = broken / "expected.json"
    broken_payload = json.loads(broken_expectations.read_text(encoding="utf-8"))
    broken_payload["approved_hashes"] = {}
    broken_payload["tables"]["edges"]["synapses"] = 1
    broken_expectations.write_text(json.dumps(broken_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    refused = run_validator(broken, tmp_path / "broken.json", "--approve-hashes", "--reason", "수치가 틀린 실행")
    assert refused.returncode == contract.EXIT_RELEASE_MISMATCH
    assert "승인할 수 없다" in refused.stderr
    assert json.loads(broken_expectations.read_text(encoding="utf-8"))["approved_hashes"] == {}


def test_duckdb_and_stdlib_scanners_agree(fixtures: dict[str, Path], tmp_path: Path) -> None:
    pytest.importorskip("duckdb", reason="duckdb 는 연구 PEP723 환경에만 있다")
    duck = pytest.importorskip("flywire_scan_duckdb")
    fixture = fixtures["normal"]
    con = duck.connect()

    neurons_duck = duck.neurons_facts(con, fixture / "neurons.csv.gz")
    id_duck = duck.id_column_facts(con, fixture / "neurons.csv.gz", "root_id")
    duck.load_id_table(con, neurons_duck["ids"])
    classification_duck = duck.classification_facts(
        con, fixture / "classification.csv.gz", ["ALPN", "Kenyon_Cell"], duck._ID_TABLE
    )
    edges_duck = duck.edges_facts(con, fixture / "connections_princeton.csv.gz", 5, duck._ID_TABLE)
    cross_duck = duck.cross_source_facts(
        con,
        fixture / "consolidated_cell_types.csv.gz",
        classification_duck["members"],
        "consolidated_cell_types.csv.gz",
        "primary_type",
    )

    neurons_stdlib, id_stdlib = contract.scan_neurons_stdlib(fixture / "neurons.csv.gz")
    classification_stdlib, members_stdlib = contract.scan_classification_stdlib(
        fixture / "classification.csv.gz",
        ["ALPN", "Kenyon_Cell"],
        set(neurons_stdlib.ids),
    )
    edges_stdlib = contract.scan_edges_stdlib(fixture / "connections_princeton.csv.gz", 5, set(neurons_stdlib.ids))
    cross_stdlib = contract.scan_cross_source_stdlib(
        fixture / "consolidated_cell_types.csv.gz",
        members_stdlib,
        "consolidated_cell_types.csv.gz",
        "primary_type",
    )

    assert neurons_duck["row_count"] == neurons_stdlib.row_count
    assert neurons_duck["nt_type_counts"] == neurons_stdlib.nt_type_counts
    assert sorted(neurons_duck["ids"]) == sorted(neurons_stdlib.ids)
    assert id_duck["non_integral"] == id_stdlib.non_integral
    assert classification_duck["class_null"] == classification_stdlib.class_null
    assert classification_duck["super_class_counts"] == classification_stdlib.super_class_counts

    duck_edges = contract.edges_from_facts(edges_duck)
    for field in ("row_count", "distinct_pairs", "synapses", "min_row_syn", "max_row_syn", "self_pairs", "neuropils"):
        assert getattr(duck_edges, field) == getattr(edges_stdlib, field), field
    assert duck_edges.duplicate_rows == edges_stdlib.duplicate_rows
    assert duck_edges.min_pair_syn == edges_stdlib.min_pair_syn
    assert duck_edges.pairs_below_threshold == edges_stdlib.pairs_below_threshold

    circuits = {
        "PN_to_KC": {"pre_group": "ALPN", "post_group": "Kenyon_Cell"},
        "KC_to_MBON": {"pre_group": "Kenyon_Cell", "post_group": "MBON"},
    }
    duck_masks, duck_rows = duck.circuit_masks(
        con, fixture / "connections_princeton.csv.gz", circuits, classification_duck["members"], {}
    )
    stdlib_masks, stdlib_rows = contract.aggregate_masks(
        fixture / "connections_princeton.csv.gz", circuits, members_stdlib, {}
    )
    assert duck_masks == stdlib_masks, "mask 는 두 경로에서 같아야 한다"
    assert duck_rows == stdlib_rows
    assert stdlib_masks["PN_to_KC"] == [
        (720575940600000001, 720575940600000003, 7),
        (720575940600000001, 720575940600000004, 5),
        (720575940600000002, 720575940600000003, 5),
        (720575940600000002, 720575940600000004, 6),
    ]

    for label in ("ALPN", "Kenyon_Cell"):
        duck_bucket = cross_duck[label]
        stdlib_bucket = cross_stdlib[label]
        assert duck_bucket["covered"] == stdlib_bucket.covered
        assert duck_bucket["member_labels"] == stdlib_bucket.member_labels
        assert contract.cross_from_facts(cross_duck)[label].matching_labels(["PN"]) == stdlib_bucket.matching_labels(
            ["PN"]
        )
        assert contract.cross_from_facts(cross_duck)[label].unresolved_members(
            ["PN"]
        ) == stdlib_bucket.unresolved_members(["PN"])


def test_manifest_schema_pins_the_documented_required_keys() -> None:
    """스키마 약화를 잡는다 — 카드가 약속한 키가 `required` 에서 빠지면 실패."""

    schema = json.loads((FLYWIRE_DIR / "manifest.schema.json").read_text(encoding="utf-8"))
    for key in (
        "manifest_version",
        "dataset_id",
        "release",
        "status",
        "inputs",
        "annotation",
        "counts",
        "license",
        "code",
        "checks",
    ):
        assert key in schema["required"], f"manifest schema 가 {key} 를 요구하지 않는다"
    checks_item = schema["properties"]["checks"]["items"]
    assert set(checks_item["required"]) == {"check", "ok", "detail"}
    assert schema["properties"]["status"]["enum"] == ["PASS", "FAIL"]
    assert schema["properties"]["manifest_version"]["const"] == 1


def test_schema_keywords_are_all_supported() -> None:
    schema = json.loads((FLYWIRE_DIR / "manifest.schema.json").read_text(encoding="utf-8"))
    keywords = contract.collect_schema_keywords(schema)
    unsupported = keywords - contract.supported_schema_keywords() - {"$schema", "$id", "title", "description"}
    assert unsupported == set(), f"검증기가 모르는 키워드가 스키마에 있다: {unsupported}"


def test_manifest_schema_rejects_a_missing_required_key() -> None:
    schema = json.loads((FLYWIRE_DIR / "manifest.schema.json").read_text(encoding="utf-8"))
    problems = contract.validate_against_schema({"release": "fafb_v783"}, schema)
    assert any("manifest_version" in problem for problem in problems)
    assert any("checks" in problem for problem in problems)


def test_group_and_circuit_decisions_bite() -> None:
    facts = contract.GroupFacts(
        label="MBON",
        source_column="class",
        source_values=["MBON"],
        count=96,
        joined_neurons=96,
        cross=contract.CrossSourceFacts(
            table="consolidated_cell_types.csv.gz",
            column="primary_type",
            covered=96,
            member_labels={
                **{720575940600100000 + index: "MBON10" for index in range(9)},
                **{720575940600200000 + index: "MBON25" for index in range(6)},
                **{720575940600300000 + index: "APL" for index in range(81)},
            },
        ),
    )
    integrity, same_vocabulary = contract.group_decision(
        "MBON",
        {"count": 96, "cross_source": {"patterns": ["^MBON"], "min_agreement": 0.95}},
        facts,
    )
    assert integrity.ok and integrity.check_id == "group_integrity:MBON"
    assert not same_vocabulary.ok, "다른 어휘가 섞이면 CONFIRMED 가 아니다"
    _, mixed_vocabulary = contract.group_decision(
        "MBON",
        {"count": 96, "cross_source": {"patterns": ["^MBON", "^APL"], "min_agreement": 0.95}},
        facts,
    )
    assert mixed_vocabulary.ok

    groups = {
        "ALPN": contract.Finding("group_status:ALPN", True, "ALPN: CONFIRMED"),
        "Kenyon_Cell": contract.Finding("group_status:Kenyon_Cell", False, "Kenyon_Cell: INCONCLUSIVE"),
    }
    circuit = contract.circuit_decision(
        "PN_to_KC",
        {"pre_group": "ALPN", "post_group": "Kenyon_Cell", "expected_pairs": 22298},
        groups,
        {"pairs": 22298, "rows": 22569, "synapses": 366946},
    )
    assert not circuit.ok, "post_group 이 CONFIRMED 가 아니면 단정할 수 없다"
    assert circuit.check_id == "circuit_annotation:PN_to_KC"

    row_pair_confusion = contract.circuit_decision(
        "PN_to_KC",
        {"pre_group": "ALPN", "post_group": "Kenyon_Cell", "expected_pairs": 22298, "expected_rows": 22569},
        {
            "ALPN": contract.Finding("group_status:ALPN", True, "ok"),
            "Kenyon_Cell": contract.Finding("group_status:Kenyon_Cell", True, "ok"),
        },
        {"pairs": 22569, "rows": 22298, "synapses": 366946},
    )
    assert not row_pair_confusion.ok, "pair 와 row 를 뒤바꾸면 잡아야 한다"
    assert "pairs" in row_pair_confusion.detail and "rows" in row_pair_confusion.detail

    confirmed = {
        "ALPN": contract.Finding("group_status:ALPN", True, "ok"),
        "Kenyon_Cell": contract.Finding("group_status:Kenyon_Cell", True, "ok"),
    }
    assert contract.circuit_decision(
        "PN_to_KC",
        {"pre_group": "ALPN", "post_group": "Kenyon_Cell"},
        confirmed,
        {"pairs": 1, "rows": 1, "synapses": 5},
    ).ok
    empty = contract.circuit_decision(
        "PN_to_KC",
        {"pre_group": "ALPN", "post_group": "Kenyon_Cell"},
        confirmed,
        {"pairs": 0, "rows": 0, "synapses": 0},
    )
    assert not empty.ok, "pair 0건은 근거가 아니다"


def test_exit_codes_are_contract_numbers() -> None:
    assert contract.EXIT_OK == 0
    assert contract.EXIT_INPUT_MISSING == 2
    assert contract.EXIT_SCHEMA_VIOLATION == 3
    assert contract.EXIT_DUPLICATE_EDGE == 4
    assert contract.EXIT_FK_VIOLATION == 5
    assert contract.EXIT_RELEASE_MISMATCH == 6
    assert contract.EXIT_TABLE_MIXING == 7
    assert contract.EXIT_COUNT_MISMATCH == 8
    assert contract.EXIT_INCONCLUSIVE == 10

    finding = contract.Finding("circuit_annotation:PN_to_KC", False, "INCONCLUSIVE")
    assert contract.determine_exit([finding]) == contract.EXIT_INCONCLUSIVE
    assert contract.determine_exit([contract.Finding("integer_ids", False, "float")]) == 3
    assert contract.determine_exit([contract.Finding("integer_ids", True, "ok")]) == 0


def test_missing_required_input_is_reported_as_absent(tmp_path: Path) -> None:
    empty = tmp_path / "empty-root"
    empty.mkdir()
    expectations = json.loads(
        (ROOT / "research" / "flywire" / "expected" / "fafb_v783.json").read_text(encoding="utf-8")
    )
    finding, names = contract.check_required_inputs(empty, expectations)
    assert not finding.ok
    assert finding.check_id == "required_inputs"
    assert "connections_princeton.csv.gz" in finding.measured["missing"]
    assert set(names) == {"neurons.csv.gz", "classification.csv.gz", "connections_princeton.csv.gz"}
