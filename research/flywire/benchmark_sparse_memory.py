#!/usr/bin/env python3
"""task 26 (B03) — 희소 검색 대조 실험.

    uv run research/flywire/benchmark_sparse_memory.py --seeds 3 \
        --output .omo/evidence/ssak-ai-web-integration/<run>/task-26/results.json

## 이 스크립트가 답하는 질문

*"같은 embedding·같은 예산에서, 확장(expansion)+승자독식(kWTA)으로 만든 희소 코드가
정확 cosine 베이스라인과 견줄 만한 품질을 유지하면서 메모리/지연을 줄이는가?"*

## 조건 (차이는 하나씩만 둔다)

  - `dense_exact`          : 512차원 fixture 임베딩의 정확 cosine — **품질 참조·실전 베이스라인**
  - `simhash`              : 부호 기반 4096-bit SimHash + Hamming 유사도
  - `sparse_random`        : 무작위 확장 → kWTA
  - `sparse_mask`          : **연결망 유래** 확장 → kWTA
  - `sparse_mask_shuffled` : 같은 mask 의 **degree 보존 shuffle** 대조군

`sparse_mask` ↔ `sparse_mask_shuffled` 의 차이는 **어느 좌표로 사상하는가** 하나다. 그래서
"구조 이득"과 "희소성 이득"을 분리할 수 있다 — 분리되지 않으면 구조 주장을 하지 않는다.

## 안전 축 (품질과 별개로 0 이어야 한다)

접근 불가 문서(다른 owner · 동의 철회 · 철회 · 만료 · 다른 scope)는 **색인에 남아 있다**.
모든 후보는 필터를 지나고 반환 직전에 다시 검증된다(`memory_corpus.AccessPolicy`).
하나라도 새면 exit 4 — 품질 이득이 안전 위반을 상쇄하지 않는다.

## 종료코드

`memory_contract.EXIT_MEANINGS` — 0 승격 후보 있음 · 3 fixture 거절 · 4 안전 위반 ·
5 산출물 실패 · 10 기각/불충분(정상 완료).
"""

from __future__ import annotations

import argparse
import json
import platform
import resource
import sys
import time
import tracemalloc
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
for candidate in (SCRIPT_DIR, REPO_ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import memory_contract as contract  # noqa: E402  # pyright: ignore[reportImplicitRelativeImport]
import memory_corpus as corpus_mod  # noqa: E402  # pyright: ignore[reportImplicitRelativeImport]

from antigravity_k.tools.search_quality_evaluator import (  # noqa: E402
    SearchGoldenCase,
    evaluate_golden_case,
)
from antigravity_k.tools.web_search_models import SearchResult  # noqa: E402

DEFAULT_EVAL_ROOT = REPO_ROOT / "tests" / "fixtures" / "ssak_search_eval"
SIMHASH_BITS = 4096
LATENCY_REPEATS = 5
PAIR_BASELINE = ("dense_exact", 0, 0.0)

ConditionKey = tuple[str, int, float]


def label_of(key: ConditionKey) -> str:
    kind, expansion, ratio = key
    if kind in {"dense_exact", "simhash"}:
        return kind
    return f"{kind}@e{expansion}@r{ratio:g}"


# ── 팔(arm) ──────────────────────────────────────────────────────────────────
class Arm:
    """검색 채널 하나. 색인은 문서별 상태를 담고, 질의별 상태는 `begin_query` 로 갈아 끼운다."""

    def __init__(self, key: ConditionKey, *, projection: contract.Projection | None = None, keep: int = 0) -> None:
        self.key = key
        self.projection = projection
        self.keep = keep
        self._index: dict[str, Any] = {}
        self._query: Any = None

    def build(self, docs: Sequence[corpus_mod.CorpusDocument]) -> None:
        raise NotImplementedError

    def begin_query(self, query: str) -> None:
        self._query = query

    def score(self, doc_id: str) -> float:
        raise NotImplementedError

    @property
    def nonzeros(self) -> int:
        raise NotImplementedError


class DenseArm(Arm):
    def build(self, docs: Sequence[corpus_mod.CorpusDocument]) -> None:
        self._index = {doc.doc_id: contract.embed(doc.text) for doc in docs}

    def begin_query(self, query: str) -> None:
        self._query = contract.to_sparse(contract.embed(query))

    def score(self, doc_id: str) -> float:
        vector = self._index.get(doc_id)
        if vector is None or not self._query:
            return 0.0
        return sum(value * self._query.get(index, 0.0) for index, value in enumerate(vector))

    @property
    def nonzeros(self) -> int:
        return len(self._index) * contract.DENSE_DIM


class SimHashArm(Arm):
    def build(self, docs: Sequence[corpus_mod.CorpusDocument]) -> None:
        self._index = {doc.doc_id: contract.simhash_signature(doc.text, bits=SIMHASH_BITS) for doc in docs}

    def begin_query(self, query: str) -> None:
        self._query = contract.simhash_signature(query, bits=SIMHASH_BITS)

    def score(self, doc_id: str) -> float:
        signature = self._index.get(doc_id)
        if signature is None:
            return 0.0
        return 1.0 - contract.hamming_distance(self._query, signature) / SIMHASH_BITS

    @property
    def nonzeros(self) -> int:
        return len(self._index) * (SIMHASH_BITS // 64)  # 64-bit word 로 담는다고 본 모델


class SparseArm(Arm):
    def build(self, docs: Sequence[corpus_mod.CorpusDocument]) -> None:
        assert self.projection is not None
        self._index = {
            doc.doc_id: contract.sparsify(contract.project(doc.text, self.projection), keep=self.keep) for doc in docs
        }

    def begin_query(self, query: str) -> None:
        assert self.projection is not None
        self._query = contract.sparsify(contract.project(query, self.projection), keep=self.keep)

    def score(self, doc_id: str) -> float:
        code = self._index.get(doc_id)
        if code is None or not self._query:
            return 0.0
        return contract.cosine(self._query, code)

    @property
    def nonzeros(self) -> int:
        return sum(len(code) for code in self._index.values())


def build_arm(
    key: ConditionKey,
    *,
    seed: int,
    edges: Sequence[contract.MaskEdge],
    mask_sha256: str,
    mask_kind: str,
) -> Arm:
    kind, expansion, active_ratio = key
    if kind == "dense_exact":
        return DenseArm(key)
    if kind == "simhash":
        return SimHashArm(key)
    keep = contract.keep_count(expansion, active_ratio)
    if kind == "sparse_random":
        return SparseArm(key, projection=contract.random_projection(expansion=expansion, seed=seed), keep=keep)
    if kind in {"sparse_mask", "sparse_mask_shuffled"}:
        projection = contract.mask_projection(
            edges,
            expansion=expansion,
            seed=seed,
            shuffle=kind == "sparse_mask_shuffled",
            mask_sha256=mask_sha256,
            mask_kind=mask_kind,
        )
        return SparseArm(key, projection=projection, keep=keep)
    raise ValueError(f"알 수 없는 조건: {kind}")


# ── 측정 ─────────────────────────────────────────────────────────────────────
def golden_case(query: corpus_mod.CorpusQuery, doc_by_id: Mapping[str, corpus_mod.CorpusDocument]) -> SearchGoldenCase:
    """정답은 **접근 가능한** 라벨>0 문서다 — 정당한 배제가 recall 을 깎지 않는다."""
    graded = tuple(
        (doc_by_id[doc_id].url, grade)
        for doc_id, grade in sorted(query.relevant_grades.items())
        if doc_id in doc_by_id and grade > 0
    )
    return SearchGoldenCase(
        case_id=query.case_id,
        query=query.query,
        relevant_urls=tuple(url for url, _ in graded),
        graded_relevance=graded,
    )


def retrieve(
    arm: Arm, *, pool: Sequence[corpus_mod.CorpusDocument], policy: corpus_mod.AccessPolicy, k: int
) -> tuple[list[str], tuple[str, ...]]:
    """후보 필터 → 점수 → 상위 k → **반환 재검증**. 반환 = (문서 id 순위, 안전 위반)."""
    candidates = [doc for doc in pool if policy.candidate_allowed(doc)]
    scored = sorted(
        ((arm.score(doc.doc_id), doc.doc_id) for doc in candidates),
        key=lambda pair: (-pair[0], pair[1]),
    )
    top_ids = [doc_id for _, doc_id in scored[:k]]
    by_id = {doc.doc_id: doc for doc in pool}
    return top_ids, policy.verify([by_id[doc_id] for doc_id in top_ids])


def run_arm(
    arm: Arm,
    *,
    queries: Sequence[corpus_mod.CorpusQuery],
    documents: Sequence[corpus_mod.CorpusDocument],
    owner: str,
    repeats: int,
    k: int,
    inject_foreign_permission: bool,
) -> dict[str, Any]:
    doc_by_id = {doc.doc_id: doc for doc in documents}
    by_partition: dict[str, list[corpus_mod.CorpusDocument]] = {}
    for doc in documents:
        by_partition.setdefault(doc.partition, []).append(doc)

    tracemalloc.start()
    build_start = time.perf_counter()
    arm.build(documents)
    build_ms = (time.perf_counter() - build_start) * 1000.0
    _, peak_alloc = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    recalls: list[float] = []
    ndcgs: list[float] = []
    cold_times: list[float] = []
    warm_medians: list[float] = []
    violations: list[str] = []
    forbidden_returned = 0
    empties = 0
    for query in queries:
        policy = corpus_mod.AccessPolicy(
            owner=owner,
            scope=query.partition,
            enforce_filter=not inject_foreign_permission,
            enforce_verify=True,
        )
        pool = by_partition.get(query.partition, [])
        arm.begin_query(query.query)
        start = time.perf_counter()
        top_ids, found = retrieve(arm, pool=pool, policy=policy, k=k)
        cold_times.append((time.perf_counter() - start) * 1000.0)
        violations.extend(found)
        forbidden_returned += sum(1 for doc_id in top_ids if doc_id in set(query.forbidden_doc_ids))
        if not top_ids:
            empties += 1
        warm: list[float] = []
        for _ in range(max(1, repeats)):
            tick = time.perf_counter()
            _ = retrieve(arm, pool=pool, policy=policy, k=k)
            warm.append((time.perf_counter() - tick) * 1000.0)
        warm_medians.append(contract.median(warm))
        hits = [
            SearchResult(title=doc_by_id[doc_id].title, url=doc_by_id[doc_id].url, snippet=doc_by_id[doc_id].snippet)
            for doc_id in top_ids
        ]
        report = evaluate_golden_case(golden_case(query, doc_by_id), hits, k=k)
        recalls.append(report.recall_at_k)
        ndcgs.append(report.ndcg_at_k)

    return {
        "arm": label_of(arm.key),
        "seed": arm.key,
        "query_count": len(queries),
        "recall_at_k": contract.mean(recalls),
        "ndcg_at_k": contract.mean(ndcgs),
        "p95_cold_ms": contract.percentile(cold_times, 0.95),
        "p95_warm_ms": contract.percentile(warm_medians, 0.95),
        "build_ms": build_ms,
        "keep": arm.keep,
        "index_nonzeros": arm.nonzeros,
        "index_peak_alloc_bytes": int(peak_alloc),
        "empty_rate": empties / len(queries) if queries else 0.0,
        "safety_violations": sorted(set(violations)),
        "forbidden_returned": forbidden_returned,
        "per_query_recall": recalls,
        "per_query_warm_ms": warm_medians,
    }


def _metrics(row: Mapping[str, Any]) -> contract.SparseMetrics:
    return contract.SparseMetrics(
        recall_at_k=float(row["recall_at_k"]),
        ndcg_at_k=float(row["ndcg_at_k"]),
        p95_cold_ms=float(row["p95_cold_ms"]),
        p95_warm_ms=float(row["p95_warm_ms"]),
        build_ms=float(row["build_ms"]),
        index_nonzeros=int(row["index_nonzeros"]),
        peak_rss_bytes=int(row["index_peak_alloc_bytes"]),
        query_count=int(row["query_count"]),
    )


def _average(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    def avg(key: str) -> float:
        return contract.mean([float(row[key]) for row in rows])

    return {
        "recall_at_k": avg("recall_at_k"),
        "ndcg_at_k": avg("ndcg_at_k"),
        "p95_cold_ms": avg("p95_cold_ms"),
        "p95_warm_ms": avg("p95_warm_ms"),
        "build_ms": avg("build_ms"),
        "keep": int(avg("keep")),
        "index_nonzeros": int(avg("index_nonzeros")),
        "index_peak_alloc_bytes": int(avg("index_peak_alloc_bytes")),
        "query_count": int(rows[0]["query_count"]),
        "empty_rate": avg("empty_rate"),
        "safety_violations": sorted({name for row in rows for name in row["safety_violations"]}),
        "forbidden_returned": sum(int(row["forbidden_returned"]) for row in rows),
        "recall_spread": max(row["recall_at_k"] for row in rows) - min(row["recall_at_k"] for row in rows),
        "seed_count": len(rows),
    }


def paired_deltas(
    baseline_rows: Sequence[Mapping[str, Any]],
    condition_rows: Sequence[Mapping[str, Any]],
    key: str,
    *,
    ratio: bool,
) -> list[float]:
    """같은 seed 의 같은 질의끼리 짝지어 델타를 만든다 — 표본 단위는 **질의**다."""
    deltas: list[float] = []
    for base, cond in zip(baseline_rows, condition_rows):
        for base_value, cond_value in zip(base[key], cond[key]):
            base_float, cond_float = float(base_value), float(cond_value)
            deltas.append(
                (base_float - cond_float) / base_float
                if ratio and base_float
                else (0.0 if ratio else cond_float - base_float)
            )
    return deltas


# ── CLI ──────────────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    _ = parser.add_argument("--seeds", type=int, default=3, help="최소 3 (계획 요구) — 낮으면 사용 오류")
    _ = parser.add_argument("--output", type=Path, default=Path("task-26-results.json"))
    _ = parser.add_argument("--eval-root", type=Path, default=DEFAULT_EVAL_ROOT)
    _ = parser.add_argument("--mask-source", type=Path, default=None, help="task 25 extract_circuits CSV(opt-in)")
    _ = parser.add_argument("--mask-provenance", type=Path, default=None, help="task 25 circuits.json(주장 인용)")
    _ = parser.add_argument("--expansion", type=int, default=None, help="지정 시 grid 대신 이 값만")
    _ = parser.add_argument("--active-ratio", type=float, default=None)
    _ = parser.add_argument("--repeats", type=int, default=LATENCY_REPEATS)
    _ = parser.add_argument("--limit", type=int, default=None, help="앞에서 N 개 holdout 질의만(스모크)")
    _ = parser.add_argument(
        "--inject",
        choices=("leakage", "query-overlap", "empty-corpus", "foreign-permission"),
        default=None,
        help="실패를 실제로 검출하는지 확인하는 장치 — 대응 조건이 무너져야 한다",
    )
    _ = parser.add_argument("--print-json", action="store_true")
    _ = parser.add_argument("--quiet", action="store_true")
    _ = parser.add_argument(
        "--smoke",
        action="store_true",
        help="빠른 배선 확인 — seed 1~2 를 허용하되 **승격 판정을 하지 않는다**(decision=NOT_RUN, exit 10)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.seeds < 3 and not args.smoke:
        print("--seeds 는 최소 3 이다(계획 요구) — seed 를 표본으로 부풀리지 않기 위한 하한이다.", file=sys.stderr)
        return contract.EXIT_USAGE

    try:
        corpus = corpus_mod.build_corpus(
            eval_root=args.eval_root,
            inject_leakage=args.inject == "leakage",
            inject_query_overlap=args.inject == "query-overlap",
            inject_empty_corpus=args.inject == "empty-corpus",
        )
    except corpus_mod.FixtureRejected as rejected:
        _write(
            args.output,
            {
                "task": "task-26",
                "experiment": "sparse_memory",
                "inject": args.inject,
                "decision": str(contract.Decision.NOT_RUN),
                "fixture_rejected": list(rejected.reasons),
            },
        )
        print("fixture 거절:\n  " + "\n  ".join(rejected.reasons), file=sys.stderr)
        return contract.EXIT_FIXTURE_REJECTED
    except FileNotFoundError as missing:
        print(f"입력 부재: {missing}", file=sys.stderr)
        return contract.EXIT_INPUT_MISSING

    mask_kind = "synthetic"
    mask_sha = contract.stable_hash("synthetic-mask-fixture/2026-09-22")
    if args.mask_source is not None:
        try:
            edges = corpus_mod.load_mask_edges_csv(args.mask_source)
        except (OSError, ValueError) as error:
            print(f"mask 입력 오류: {error}", file=sys.stderr)
            return contract.EXIT_INPUT_MISSING
        mask_sha = contract.sha256_file(args.mask_source)
        mask_kind = "flywire"
    else:
        edges = corpus_mod.synthetic_mask_edges(count=6000, pre_pool=320, post_pool=140, seed=26)

    provenance = corpus_mod.mask_provenance(args.mask_provenance)
    if mask_kind == "flywire" and provenance.get("available") and provenance.get("status") != "CONFIRMED":
        print(
            f"mask provenance 가 CONFIRMED 가 아니다({provenance.get('status')}) — 회로 주장의 근거가 될 수 없다.",
            file=sys.stderr,
        )
        return contract.EXIT_FIXTURE_REJECTED

    queries = list(corpus.holdout_queries())
    if args.limit:
        queries = queries[: args.limit]
    if not queries:
        print("holdout 질의가 없다", file=sys.stderr)
        return contract.EXIT_FIXTURE_REJECTED

    expansions = (args.expansion,) if args.expansion else contract.SPARSE_EXPANSIONS
    ratios = (args.active_ratio,) if args.active_ratio else contract.SPARSE_ACTIVE_RATIOS
    seeds = tuple(100 + index * 101 for index in range(args.seeds))

    configs: list[ConditionKey] = [("dense_exact", 0, 0.0), ("simhash", 0, 0.0)]
    for expansion in expansions:
        for ratio in ratios:
            configs.extend(
                (
                    ("sparse_random", expansion, ratio),
                    ("sparse_mask", expansion, ratio),
                    ("sparse_mask_shuffled", expansion, ratio),
                )
            )

    rows: dict[str, list[dict[str, Any]]] = {}
    for key in configs:
        for seed in seeds:
            arm = build_arm(key, seed=seed, edges=edges, mask_sha256=mask_sha, mask_kind=mask_kind)
            rows.setdefault(label_of(key), []).append(
                run_arm(
                    arm,
                    queries=queries,
                    documents=corpus.documents,
                    owner=corpus_mod.OWNER_WORKSPACE,
                    repeats=args.repeats,
                    k=contract.K,
                    inject_foreign_permission=args.inject == "foreign-permission",
                )
            )

    reported = []
    for label, group in rows.items():
        reported.extend(group)
    safety = sorted({name for row in reported for name in row["safety_violations"]})
    forbidden_returned = sum(int(row["forbidden_returned"]) for row in reported)
    if forbidden_returned:
        safety = [*safety, f"forbidden_golden_returned:{forbidden_returned}"]
    manifest = _manifest(corpus, mask_sha, mask_kind, provenance, args, seeds)
    if safety:
        _write(
            args.output,
            {
                "task": "task-26",
                "experiment": "sparse_memory",
                "inject": args.inject,
                "decision": str(contract.Decision.REJECTED),
                "safety_violations": safety,
                "manifest": manifest,
            },
        )
        print("안전 위반 — 실행 실패:\n  " + "\n  ".join(safety), file=sys.stderr)
        return contract.EXIT_SAFETY_VIOLATION

    summaries = {label: _average(group) for label, group in rows.items()}
    baseline_label = label_of(PAIR_BASELINE)
    baseline_rows = rows[baseline_label]
    baseline_metrics = _metrics(summaries[baseline_label])

    verdicts: list[dict[str, Any]] = []
    for label, group in sorted(rows.items()):
        if label == baseline_label:
            continue
        rss_seed_gains = [
            (float(base["index_peak_alloc_bytes"]) - float(cond["index_peak_alloc_bytes"]))
            / float(base["index_peak_alloc_bytes"])
            if float(base["index_peak_alloc_bytes"])
            else 0.0
            for base, cond in zip(baseline_rows, group)
        ]
        verdict = contract.decide_sparse_condition(
            baseline_name=baseline_label,
            condition_name=label,
            baseline=baseline_metrics,
            condition=_metrics(summaries[label]),
            recall_deltas=paired_deltas(baseline_rows, group, "per_query_recall", ratio=False),
            p95_deltas=paired_deltas(baseline_rows, group, "per_query_warm_ms", ratio=True),
            rss_seed_gains=rss_seed_gains,
            safety_violations=summaries[label]["safety_violations"],
        )
        verdicts.append(
            {
                "condition": label,
                "baseline": baseline_label,
                "decision": str(verdict.decision),
                "reasons": list(verdict.reasons),
                "recall_delta": verdict.recall_delta,
                "ndcg_delta": verdict.ndcg_delta,
                "resource_gain": verdict.resource_gain,
                "resource_axis": verdict.resource_axis,
                "recall_ci": list(verdict.recall_ci),
                "resource_ci": list(verdict.resource_ci),
                "rss_seed_gains": rss_seed_gains,
                "metrics": summaries[label],
            }
        )

    accepted = [v for v in verdicts if v["decision"] == str(contract.Decision.ACCEPTED)]
    inconclusive = [v for v in verdicts if v["decision"] == str(contract.Decision.INCONCLUSIVE)]
    decision = (
        contract.Decision.ACCEPTED
        if accepted
        else (contract.Decision.INCONCLUSIVE if inconclusive else contract.Decision.REJECTED)
    )
    if args.smoke:
        # 스모크는 **판정을 하지 않는다**: seed 가 3 미만이면 CI 를 주장할 수 없다.
        decision = contract.Decision.NOT_RUN

    report = {
        "task": "task-26",
        "experiment": "sparse_memory",
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "inject": args.inject,
        "decision": str(decision),
        "manifest": manifest,
        "smoke": bool(args.smoke),
        "grid": {
            "expansions": list(expansions),
            "active_ratios": list(ratios),
            "keep": {str(e): {str(r): contract.keep_count(e, r) for r in ratios} for e in expansions},
        },
        "arms": summaries,
        "verdicts": verdicts,
        "limitations": (["스모크 실행 — seed 가 3 미만이라 CI/승격을 주장하지 않는다."] if args.smoke else [])
        + [
            "embedding 은 fixture 해시 임베딩이다 — 실제 모델 임베딩 품질은 재지 않았다(model_embedding=NOT_RUN).",
            "관련도 라벨은 task 24 동결 검색셋의 graded payload 이며 각 케이스 질의에 대한 것이다; 다른 질의는 0 으로 센다.",
            "정확 cosine 을 품질 참조로 두었다 — 프로젝트 ANN(chromadb) 팔은 이 실행에 없다(임베딩 모델 다운로드 필요).",
            "index_peak_alloc_bytes 는 tracemalloc 할당 피크이며 프로세스 RSS 가 아니다.",
            "mask_kind=synthetic 이면 구조 고유 효과를 주장하지 않는다.",
        ],
        "reproduction_command": _reproduction(args, seeds),
    }
    _write(args.output, report)
    if not args.quiet:
        _print_summary(report)
    if args.print_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return contract.EXIT_OK if decision is contract.Decision.ACCEPTED else contract.EXIT_REJECTED_EXPERIMENT


def _manifest(
    corpus: corpus_mod.Corpus,
    mask_sha: str,
    mask_kind: str,
    provenance: Mapping[str, object],
    args: argparse.Namespace,
    seeds: Sequence[int],
) -> dict[str, Any]:
    return {
        "task": "task-26/B03",
        "corpus": {
            "documents": len(corpus.documents),
            "queries": len(corpus.queries),
            "holdout_queries": len(corpus.holdout_queries()),
            "calibration_queries": len(corpus.calibration_queries()),
            "eval_fixture_sha256": corpus.eval_fixture_sha256,
            "corpus_revision": corpus.corpus_revision,
            "unlabeled_treated_as": corpus.unlabeled_treated_as,
            "notes": list(corpus.notes),
        },
        "split": {
            "rule_version": corpus.split.rule_version,
            "hash": corpus.split_hash(),
            "holdout_sites": len(corpus.split.holdout_sites),
            "calibration_sites": len(corpus.split.calibration_sites),
            "train_sites": len(corpus.split.train_sites),
        },
        "embedding": {"kind": contract.EMBEDDING_KIND, "dim": contract.DENSE_DIM},
        "mask": {"kind": mask_kind, "sha256": mask_sha, "provenance": dict(provenance)},
        "code": {"path": str(Path(__file__).resolve()), "sha256": contract.sha256_file(Path(__file__).resolve())},
        "budget": {"k": contract.K, "repeats": args.repeats, "seeds": list(seeds)},
        "machine": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "process_max_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
        },
    }


def _reproduction(args: argparse.Namespace, seeds: Sequence[int]) -> str:
    parts = [
        "uv run research/flywire/benchmark_sparse_memory.py",
        f"--seeds {len(seeds)}",
        f"--output {args.output}",
    ]
    if args.mask_source:
        parts.append(f"--mask-source {args.mask_source}")
    if args.inject:
        parts.append(f"--inject {args.inject}")
    return " ".join(parts)


def _write(path: Path, payload: Mapping[str, object]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as error:
        print(f"산출물 쓰기 실패: {error}", file=sys.stderr)


def _print_summary(report: Mapping[str, Any]) -> None:
    print(f"task-26/B03 희소 검색 — 결정 {report['decision']}")
    for verdict in report["verdicts"]:
        metrics = verdict["metrics"]
        print(
            f"  {verdict['condition']:<34} {verdict['decision']:<12} "
            f"recall {metrics['recall_at_k']:.4f} nDCG {metrics['ndcg_at_k']:.4f} "
            f"warm p95 {metrics['p95_warm_ms']:.2f}ms nnz {metrics['index_nonzeros']} "
            f"gain {verdict['resource_gain']:+.4f}({verdict['resource_axis']})"
        )
    print("  ── 사유 ──")
    for verdict in report["verdicts"]:
        print(f"  {verdict['condition']}: {'; '.join(verdict['reasons'])}")


if __name__ == "__main__":
    raise SystemExit(main())
