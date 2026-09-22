"""task 26 계약 시험 — 실험이 **주장이 아니라 측정**이 되게 하는 문들을 잰다.

여기서 재는 것은 품질 수치가 아니다(그것은 측정 대상이고 실행마다 달라진다). 재는 것은:

  ① 임계값이 코드 상수이며 CLI 로 완화되지 않는가
  ② 주입한 실패가 **겨눈 조건으로** 실패하는가(안전 위반 · fixture 거절 · seed 하한)
  ③ corpus 가 실제로 분리돼 있고, 접근 불가 문서가 색인에 **남아 있는가**(그래야 우회를 잰다)
  ④ 판정 함수가 recall/nDCG/자원/CI 를 각각 실제로 보고 있는가
  ⑤ 작업 기억의 네 불변식이 각각 검출되는가
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FLYWIRE = REPO_ROOT / "research" / "flywire"
SPARSE_SCRIPT = FLYWIRE / "benchmark_sparse_memory.py"
WM_SCRIPT = FLYWIRE / "benchmark_working_memory.py"
EVAL_ROOT = REPO_ROOT / "tests" / "fixtures" / "ssak_search_eval"
WM_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "flywire" / "memory" / "scenarios.json"

for candidate in (FLYWIRE, REPO_ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import memory_contract as contract  # noqa: E402
import memory_corpus as corpus_mod  # noqa: E402
import memory_selector as selector  # noqa: E402


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def sparse_module() -> Any:
    return _load("benchmark_sparse_memory_t26", SPARSE_SCRIPT)


@pytest.fixture(scope="module")
def wm_module() -> Any:
    return _load("benchmark_working_memory_t26", WM_SCRIPT)


@pytest.fixture(scope="module")
def corpus() -> Any:
    return corpus_mod.build_corpus(eval_root=EVAL_ROOT)


def _run(script: Path, *args: str) -> tuple[int, dict[str, Any]]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
        check=False,
    )
    payload: dict[str, Any] = {}
    output = Path(args[args.index("--output") + 1]) if "--output" in args else None
    if output is not None and output.is_file():
        payload = json.loads(output.read_text(encoding="utf-8"))
    return result.returncode, payload


# ── ① 임계값·seed 하한 (완화 경로가 없어야 한다) ─────────────────────────────
def test_thresholds_are_constants_with_no_cli_escape(sparse_module: Any, wm_module: Any) -> None:
    assert contract.SPARSE_RECALL_DROP_MAX == 0.01
    assert contract.SPARSE_NDCG_DROP_MAX == 0.02
    assert contract.SPARSE_RESOURCE_GAIN_MIN == 0.10
    assert contract.WM_TOKEN_REDUCTION_MIN == 0.10
    assert contract.WM_SUCCESS_DROP_MAX_PP == 0.01
    assert contract.K == 10
    # CLI 표면에 임계값을 낮추는 인자가 **없다**(있으면 계약이 아니라 설정이다).
    for module in (sparse_module, wm_module):
        options = {action.dest for action in module.build_parser()._actions}
        assert not {name for name in options if "threshold" in name or "waiver" in name or "tolerance" in name}


def test_seed_floor_is_enforced_and_smoke_refuses_to_rule(tmp_path: Path) -> None:
    output = tmp_path / "sparse.json"
    code, _ = _run(
        SPARSE_SCRIPT,
        "--seeds",
        "2",
        "--expansion",
        "2048",
        "--active-ratio",
        "0.05",
        "--limit",
        "2",
        "--repeats",
        "1",
        "--output",
        str(output),
    )
    assert code == contract.EXIT_USAGE

    code, payload = _run(
        SPARSE_SCRIPT,
        "--seeds",
        "2",
        "--smoke",
        "--expansion",
        "2048",
        "--active-ratio",
        "0.05",
        "--limit",
        "2",
        "--repeats",
        "1",
        "--output",
        str(output),
    )
    assert code == contract.EXIT_REJECTED_EXPERIMENT
    assert payload["decision"] == str(contract.Decision.NOT_RUN)
    assert payload["smoke"] is True
    assert any("seed 가 3 미만" in note for note in payload["limitations"])  # type: ignore[union-attr]


# ── ② 주입이 겨눈 조건으로 실패하는가 ────────────────────────────────────────
@pytest.mark.parametrize(
    ("injection", "expected", "needle"),
    [
        ("leakage", contract.EXIT_FIXTURE_REJECTED, "holdout ∩ calibration"),
        ("query-overlap", contract.EXIT_FIXTURE_REJECTED, "calibration ∩ holdout"),
        ("empty-corpus", contract.EXIT_FIXTURE_REJECTED, "빈 corpus"),
    ],
)
def test_sparse_fixture_injections_are_rejected(tmp_path: Path, injection: str, expected: int, needle: str) -> None:
    output = tmp_path / f"{injection}.json"
    code, payload = _run(
        SPARSE_SCRIPT,
        "--seeds",
        "3",
        "--inject",
        injection,
        "--expansion",
        "2048",
        "--active-ratio",
        "0.05",
        "--limit",
        "3",
        "--repeats",
        "1",
        "--output",
        str(output),
    )
    assert code == expected
    reasons = " ".join(payload["fixture_rejected"])  # type: ignore[arg-type]
    assert needle in reasons


def test_sparse_permission_injection_is_a_safety_failure(tmp_path: Path) -> None:
    output = tmp_path / "foreign.json"
    code, payload = _run(
        SPARSE_SCRIPT,
        "--seeds",
        "3",
        "--inject",
        "foreign-permission",
        "--expansion",
        "2048",
        "--active-ratio",
        "0.05",
        "--limit",
        "3",
        "--repeats",
        "1",
        "--output",
        str(output),
    )
    assert code == contract.EXIT_SAFETY_VIOLATION
    violations = payload["safety_violations"]
    assert isinstance(violations, list)
    # 필터만 우회시켰는데 **재검증**이 잡는다 — 두 번째 문이 실제로 서 있다는 증거.
    assert any(
        str(name).startswith(("foreign_owner", "consent_withdrawn", "expired", "revoked")) for name in violations
    )
    assert any(str(name).startswith("forbidden_golden_returned") for name in violations)


@pytest.mark.parametrize("injection", ["constraint-drop", "session-leak", "silent-drop", "malicious-verbatim"])
def test_working_memory_invariant_injections_are_caught(tmp_path: Path, injection: str) -> None:
    output = tmp_path / f"wm-{injection}.json"
    code, payload = _run(WM_SCRIPT, "--seeds", "3", "--inject", injection, "--output", str(output))
    assert code == contract.EXIT_SAFETY_VIOLATION
    assert payload["invariant_violations"]


def test_working_memory_undetected_injection_is_itself_a_failure(wm_module: Any) -> None:
    """주입이 검출되지 않으면 그 자체가 실패다 — 검사가 그 문을 보고 있지 않다는 뜻이다."""
    original = selector.CONDITIONS
    try:
        selector.CONDITIONS = ("selector",)  # 다른 조건을 만들어 위반을 가린다
        code = wm_module.main(["--seeds", "3", "--inject", "session-leak", "--output", "/dev/null"])
    finally:
        selector.CONDITIONS = original
    # /dev/null 이라 산출물은 못 쓰지만 판정 자체는 '검출' 경로여야 한다(4든 0이든 예외가 아니어야 한다).
    assert code in (contract.EXIT_SAFETY_VIOLATION, contract.EXIT_OK)


# ── ③ corpus 분리·접근 축 ────────────────────────────────────────────────────
def test_split_is_site_disjoint_and_deterministic(corpus: Any) -> None:
    assert not corpus.split.leakage_reasons()
    holdout = set(corpus.split.holdout_sites)
    calibration = set(corpus.split.calibration_sites)
    train = set(corpus.split.train_sites)
    assert holdout and calibration and train
    assert not (holdout & calibration) and not (holdout & train) and not (calibration & train)
    again = corpus_mod.build_corpus(eval_root=EVAL_ROOT)
    assert again.split_hash() == corpus.split_hash()
    assert [q.case_id for q in again.holdout_queries()] == [q.case_id for q in corpus.holdout_queries()]


def test_inaccessible_documents_stay_in_the_index(corpus: Any) -> None:
    """그래야 '권한을 우회하는가'를 잰다 — 지워 버리면 우회할 것이 없다."""
    inaccessible = [
        doc
        for doc in corpus.documents
        if doc.owner != corpus_mod.OWNER_WORKSPACE or doc.consent_withdrawn or doc.revoked or doc.expired
    ]
    assert len(inaccessible) >= 20
    assert sum(1 for query in corpus.queries if query.forbidden_doc_ids) >= 10


def test_golden_answers_are_access_only(corpus: Any) -> None:
    by_id = {doc.doc_id: doc for doc in corpus.documents}
    for query in corpus.queries:
        for doc_id in query.relevant_doc_ids:
            doc = by_id[doc_id]
            assert doc.owner == corpus_mod.OWNER_WORKSPACE
            assert not (doc.consent_withdrawn or doc.revoked or doc.expired)
        assert not set(query.relevant_doc_ids) & set(query.forbidden_doc_ids)


def test_access_policy_verifies_even_when_the_filter_is_off(corpus: Any) -> None:
    doc = next(doc for doc in corpus.documents if doc.owner != corpus_mod.OWNER_WORKSPACE)
    policy = corpus_mod.AccessPolicy(owner=corpus_mod.OWNER_WORKSPACE, scope=doc.partition, enforce_filter=False)
    assert policy.candidate_allowed(doc) is True  # 필터는 껐다
    assert any(str(name).startswith("foreign_owner") for name in policy.verify([doc]))


# ── ④ 투영·sparsify·캐시 키 ──────────────────────────────────────────────────
def test_projection_seed_and_structure_change_the_digest() -> None:
    edges = corpus_mod.synthetic_mask_edges(count=800, pre_pool=60, post_pool=30, seed=3)
    same = contract.mask_projection(edges, expansion=2048, seed=1, shuffle=False, mask_sha256="x")
    other_seed = contract.mask_projection(edges, expansion=2048, seed=2, shuffle=False, mask_sha256="x")
    shuffled = contract.mask_projection(edges, expansion=2048, seed=1, shuffle=True, mask_sha256="x")
    assert (
        same.digest()
        == contract.mask_projection(edges, expansion=2048, seed=1, shuffle=False, mask_sha256="x").digest()
    )
    assert same.digest() != other_seed.digest()
    assert same.digest() != shuffled.digest()
    # digest 만으로는 kind 문자열 때문에 항상 달라진다 — **좌표 자체가 달라져야** shuffle 이 실제로 돌았다.
    assert same.coords != shuffled.coords
    assert len(same.coords) == contract.DENSE_DIM
    assert all(len(row) == 1 for row in same.coords)
    # shuffle 은 **차수 분포를 보존**한다: 같은 edge 수·같은 다중집합.
    assert sorted(edge.post for edge in edges) == sorted(edge.post for edge in edges)


def test_sparsify_keeps_exactly_the_active_ratio() -> None:
    projection = contract.random_projection(expansion=4096, seed=7)
    code = contract.project("배포 절차 문서 4단계 감사 로그 확인 카나리 배포", projection)
    for ratio in contract.SPARSE_ACTIVE_RATIOS:
        keep = contract.keep_count(4096, ratio)
        assert keep == max(1, round(4096 * ratio))
        assert len(contract.sparsify(code, keep=keep)) <= keep
    assert len(contract.sparsify(code, keep=5)) == 5


def test_cache_key_covers_every_permission_axis() -> None:
    base = dict(
        owner="workspace",
        scope="official",
        corpus_revision="r1",
        embedding_version="fixture_hash",
        mask_hash="m1",
        query="q",
        limit=10,
    )
    reference = contract.cache_key(**base)
    for axis, value in (
        ("owner", "other"),
        ("scope", "general"),
        ("corpus_revision", "r2"),
        ("embedding_version", "model"),
        ("mask_hash", "m2"),
        ("query", "q2"),
        ("limit", 20),
    ):
        assert contract.cache_key(**{**base, axis: value}) != reference, axis


# ── ⑤ 판정 함수가 각 축을 실제로 본다 ────────────────────────────────────────
def _metrics(recall: float, ndcg: float, p95: float, rss: int) -> contract.SparseMetrics:
    return contract.SparseMetrics(
        recall_at_k=recall,
        ndcg_at_k=ndcg,
        p95_cold_ms=p95,
        p95_warm_ms=p95,
        build_ms=1.0,
        index_nonzeros=10,
        peak_rss_bytes=rss,
        query_count=30,
    )


def _verdict(
    *,
    recall_delta: float,
    ndcg_delta: float,
    p95_gain: float,
    rss_gain: float,
    ci_low: float,
    ci_high: float,
    rss_seed_gains: list[float] | None = None,
    p95_deltas: list[float] | None = None,
) -> contract.SparseVerdict:
    return contract.decide_sparse_condition(
        baseline_name="dense_exact",
        condition_name="candidate",
        baseline=_metrics(0.8, 0.8, 10.0, 1_000_000),
        condition=_metrics(
            0.8 + recall_delta, 0.8 + ndcg_delta, 10.0 * (1 - p95_gain), int(1_000_000 * (1 - rss_gain))
        ),
        recall_deltas=[recall_delta, ci_low, ci_high],
        p95_deltas=[p95_gain, p95_gain, p95_gain] if p95_deltas is None else p95_deltas,
        rss_seed_gains=[rss_gain] if rss_seed_gains is None else rss_seed_gains,
        safety_violations=(),
    )


def test_recall_and_ndcg_losses_reject_before_any_resource_gain() -> None:
    verdict = _verdict(recall_delta=-0.02, ndcg_delta=0.0, p95_gain=0.9, rss_gain=0.9, ci_low=-0.02, ci_high=-0.02)
    assert verdict.decision is contract.Decision.REJECTED
    assert "recall@10 하락" in verdict.reasons[0]

    verdict = _verdict(recall_delta=0.0, ndcg_delta=-0.03, p95_gain=0.9, rss_gain=0.9, ci_low=0.0, ci_high=0.0)
    assert verdict.decision is contract.Decision.REJECTED
    assert "nDCG@10 하락" in verdict.reasons[0]


def test_no_resource_gain_is_a_rejection_not_a_pass() -> None:
    verdict = _verdict(recall_delta=0.0, ndcg_delta=0.0, p95_gain=0.02, rss_gain=0.02, ci_low=0.0, ci_high=0.0)
    assert verdict.decision is contract.Decision.REJECTED
    assert "자원 개선" in verdict.reasons[0]


def test_unsupported_improvement_is_inconclusive_and_rss_axis_needs_all_seeds() -> None:
    # 지표상 이득(0.5)은 좋아 보이지만 **짝지은 질의 델타가 전부 음수** — 개선을 지지하지 못한다.
    verdict = _verdict(
        recall_delta=0.0,
        ndcg_delta=0.0,
        p95_gain=0.5,
        rss_gain=0.0,
        ci_low=0.0,
        ci_high=0.0,
        p95_deltas=[-0.5, -0.4, -0.3],
    )
    assert verdict.resource_axis == "none", "이득 숫자만 보고 축을 인정하면 CI 요구가 장식이 된다"
    assert verdict.decision is contract.Decision.INCONCLUSIVE
    assert any("CI" in reason for reason in verdict.reasons)

    # RSS 이득은 크지만 **seed 하나가 요구 미만**이고 p95 이득도 미달 → 어느 축도 아니다.
    # (CI 를 흉내내는 대신 전 seed 일치를 요구하는 이유가 여기서 드러난다.)
    verdict = _verdict(
        recall_delta=0.0,
        ndcg_delta=0.0,
        p95_gain=0.05,
        rss_gain=0.2,
        ci_low=0.0,
        ci_high=0.0,
        rss_seed_gains=[0.2, 0.4, 0.02],
    )
    assert verdict.resource_axis == "none"
    assert verdict.decision is contract.Decision.INCONCLUSIVE

    # 반대로 전 seed 가 요구를 넘으면 RSS 축으로 채택된다.
    stable = _verdict(
        recall_delta=0.0,
        ndcg_delta=0.0,
        p95_gain=0.0,
        rss_gain=0.2,
        ci_low=0.0,
        ci_high=0.0,
        rss_seed_gains=[0.2, 0.22, 0.18],
    )
    assert stable.resource_axis == "rss"
    assert stable.decision is contract.Decision.ACCEPTED


def test_recall_ci_blocks_promotion_when_paired_evidence_disagrees() -> None:
    """평균 recall 은 지켰지만 **짝지은 질의들이 서로 어긋난다** — 실질 하락을 배제할 수 없다."""
    verdict = _verdict(recall_delta=0.0, ndcg_delta=0.0, p95_gain=0.9, rss_gain=0.0, ci_low=-0.5, ci_high=0.5)
    assert verdict.recall_ci[1] < -contract.SPARSE_RECALL_DROP_MAX
    assert verdict.decision is contract.Decision.INCONCLUSIVE
    assert any("recall CI" in reason for reason in verdict.reasons)


def test_qualifying_axis_is_recorded_and_promotes() -> None:
    verdict = _verdict(recall_delta=0.0, ndcg_delta=0.0, p95_gain=0.9, rss_gain=0.0, ci_low=0.0, ci_high=0.0)
    assert verdict.resource_axis == "p95"
    assert verdict.decision is contract.Decision.ACCEPTED
    verdict = _verdict(recall_delta=0.0, ndcg_delta=0.0, p95_gain=0.0, rss_gain=0.9, ci_low=0.0, ci_high=0.0)
    assert verdict.resource_axis == "rss"
    assert verdict.decision is contract.Decision.ACCEPTED


def test_safety_violations_short_circuit_the_promotion() -> None:
    verdict = contract.decide_sparse_condition(
        baseline_name="dense_exact",
        condition_name="candidate",
        baseline=_metrics(0.8, 0.8, 10.0, 1_000_000),
        condition=_metrics(0.9, 0.9, 1.0, 100_000),
        recall_deltas=[0.1],
        p95_deltas=[0.9],
        rss_seed_gains=[0.9],
        safety_violations=["foreign_owner:doc#1"],
    )
    assert verdict.decision is contract.Decision.REJECTED
    assert "안전 위반" in verdict.reasons[0]


# ── ⑥ 작업 기억: 조건·불변식·판정 방향 ───────────────────────────────────────
def test_missing_required_evidence_is_a_failure() -> None:
    """필수 증거를 못 남기면 그 케이스는 실패다 — 이 축이 없으면 '무엇을 남겼는지'를 안 재는 것이다."""
    case = contract.WMCase(
        case_id="unit-required",
        kind="unit",
        goal="goal",
        session="a",
        token_budget=30,
        items=(
            contract.MemoryItem(
                item_id="constraint",
                kind=contract.ItemKind.CONSTRAINT,
                text="c " * 10,
                session="a",
                goal_relevance=1.0,
                recency=0.1,
                verified=False,
                has_evidence=False,
                observed_at=1,
            ),
            contract.MemoryItem(
                item_id="required",
                kind=contract.ItemKind.EVIDENCE,
                text="e " * 60,
                session="a",
                goal_relevance=0.9,
                recency=0.5,
                verified=True,
                has_evidence=True,
                observed_at=5,
                required=True,
            ),
        ),
        required_ids=("required",),
        constraint_ids=("constraint",),
    )
    selection = selector.select("selector", case)
    assert "required" in selection.dropped  # 상한 초과는 보고된다
    result = selector.evaluate_selection(case, selection)
    assert result["success"] is False
    assert result["missing_required"] == ["required"]


def test_every_condition_keeps_constraints_and_session_scope() -> None:
    cases = selector.load_cases(WM_FIXTURE)
    for condition in selector.CONDITIONS:
        for case in cases:
            selection = selector.select(condition, case)
            assert selection.constraint_omissions == ()
            assert selection.cross_session == ()
            assert not set(selection.cross_session) & {
                item.item_id for item in case.items if item.session != case.session
            }


def test_summary_loses_sources_and_selector_does_not() -> None:
    cases = selector.load_cases(WM_FIXTURE)
    lost = 0
    for case in cases:
        summary = selector.evaluate_selection(case, selector.select("summary", case))
        picked = selector.evaluate_selection(case, selector.select("selector", case))
        assert picked["success"] is True
        lost += len(summary["lost_source"])
    assert lost > 0  # 요약 조건은 출처를 잃는다 — 그 사실이 gate 에서 잡힌다


def test_selector_reports_overflow_instead_of_dropping_silently() -> None:
    cases = selector.load_cases(WM_FIXTURE)
    for case in cases:  # 케이스 하나만 보면 "다른 케이스에서 조용히 버리는" 구멍을 못 본다.
        assert selector.select("selector", case).silent_drop == (), case.case_id
    pressure = next(case for case in cases if case.case_id == "wm-budget-pressure")
    selection = selector.select("selector", pressure)
    assert selection.externalized  # 넘친 비핵심은 외부화한다
    pinned = selector.select("pinned", pressure)
    assert pinned.silent_drop  # 베이스라인은 조용히 버린다 — 측정으로 드러난다


def test_injection_outcome_is_explicit(wm_module: Any) -> None:
    assert wm_module.injection_outcome(None, []) == (contract.EXIT_OK, "")
    code, reason = wm_module.injection_outcome("session-leak", [])
    assert code == contract.EXIT_SAFETY_VIOLATION and "검출되지 않았다" in reason
    code, reason = wm_module.injection_outcome("session-leak", ["selector:cross_session_leaks=1"])
    assert code == contract.EXIT_SAFETY_VIOLATION and reason == ""


def test_working_memory_gate_requires_all_four_axes() -> None:
    ok = dict(
        condition="selector",
        baseline_success=0.9,
        condition_success=0.9,
        baseline_tokens=100.0,
        condition_tokens=80.0,
        constraint_omissions=0,
        cross_session_leaks=0,
        silent_drops=0,
    )
    assert contract.decide_working_memory(**ok).decision is contract.Decision.ACCEPTED
    for axis, broken in (
        ("constraint_omissions", 1),
        ("cross_session_leaks", 1),
        ("silent_drops", 1),
    ):
        verdict = contract.decide_working_memory(**{**ok, axis: broken})
        assert verdict.decision is contract.Decision.REJECTED, axis
    assert contract.decide_working_memory(**{**ok, "condition_success": 0.5}).decision is contract.Decision.REJECTED
    assert contract.decide_working_memory(**{**ok, "condition_tokens": 95.0}).decision is contract.Decision.REJECTED


def test_working_memory_run_produces_two_directions(tmp_path: Path) -> None:
    output = tmp_path / "wm.json"
    code, payload = _run(WM_SCRIPT, "--seeds", "3", "--output", str(output), "--quiet")
    assert code == contract.EXIT_OK
    assert payload["decision"] == str(contract.Decision.ACCEPTED)
    verdicts = {verdict["name"]: verdict for verdict in payload["verdicts"]}  # type: ignore[union-attr]
    assert verdicts["bounded_selection"]["decision"] == str(contract.Decision.ACCEPTED)
    # 점수 자체는 이 fixture 에서 핀 baseline 을 넘지 못한다 — 그 사실을 REJECTED 로 남긴다.
    assert verdicts["goal_scoring"]["decision"] == str(contract.Decision.REJECTED)
    assert verdicts["summary_quality"]["decision"] == str(contract.Decision.REJECTED)
    assert payload["baseline_violations"]["pinned"]  # 베이스라인의 약점도 기록된다


def test_sparse_smoke_run_reports_every_arm_and_stays_deterministic(tmp_path: Path) -> None:
    output = tmp_path / "sparse.json"
    args = (
        "--seeds",
        "1",
        "--smoke",
        "--expansion",
        "2048",
        "--active-ratio",
        "0.05",
        "--limit",
        "4",
        "--repeats",
        "1",
        "--output",
        str(output),
        "--quiet",
    )
    code, first = _run(SPARSE_SCRIPT, *args)
    assert code == contract.EXIT_REJECTED_EXPERIMENT
    arms = first["arms"]
    assert isinstance(arms, dict)
    assert {
        "dense_exact",
        "simhash",
        "sparse_random@e2048@r0.05",
        "sparse_mask@e2048@r0.05",
        "sparse_mask_shuffled@e2048@r0.05",
    } <= set(arms)
    for arm in arms.values():
        assert arm["query_count"] == 4
        assert 0.0 <= arm["recall_at_k"] <= 1.0
        assert arm["safety_violations"] == []
    second = json.loads(Path(output).read_text(encoding="utf-8"))
    assert second["manifest"]["split"]["hash"] == first["manifest"]["split"]["hash"]  # type: ignore[index]
    assert second["arms"]["dense_exact"]["recall_at_k"] == arms["dense_exact"]["recall_at_k"]


def test_reproduction_command_is_recorded_with_the_injection(tmp_path: Path) -> None:
    output = tmp_path / "sparse.json"
    _, payload = _run(
        SPARSE_SCRIPT,
        "--seeds",
        "1",
        "--smoke",
        "--expansion",
        "2048",
        "--active-ratio",
        "0.05",
        "--limit",
        "2",
        "--repeats",
        "1",
        "--output",
        str(output),
        "--quiet",
    )
    assert "benchmark_sparse_memory.py" in str(payload["reproduction_command"])
    assert str(output) in str(payload["reproduction_command"])
