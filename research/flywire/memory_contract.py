"""task 26 (B03·B04·B08) — 희소 검색·작업 기억 대조 실험의 **판정이 사는 단 한 곳**.

측정은 `benchmark_sparse_memory.py`·`benchmark_working_memory.py` 가 하고, 결정은 여기가 한다.
이 분리가 요점이다: 임계값을 스크립트 CLI 로 완화할 수 없고(플래그가 없다), 시험은 이 상수와
판정 함수를 직접 잰다.

## 두 실험

  - **A (B03)** 희소 검색: 같은 embedding·같은 메모리 예산에서 정확 cosine 베이스라인과
    SimHash · 무작위 희소 확장 · **구조(연결망) 유래 희소 확장**을 비교한다.
  - **B (B04)** 목표 중심 작업 기억: 최근 창(FIFO)·고정 핀·같은 토큰 예산 요약 베이스라인과
    결정적 선택기(목표 관련성+최근성+검증된 진전−중복)를 비교한다.

## 정직성 규칙 (문서에 그대로 옮긴다)

  1. 여기서 쓰는 embedding 은 **fixture 해시 임베딩**이다 — 실제 모델 임베딩이 아니다.
     그래서 결과의 `embedding.kind == "fixture_hash"` 이고 모델 임베딩 축은 NOT_RUN 이다.
  2. 기본 mask 는 **합성**이다. 실제 회로 마스크(`--mask-source`)를 주지 않으면
     생물학적 주장을 하지 않는다(`mask.kind == "synthetic"` 이면 구조 고유 효과 주장 금지).
  3. 두 arm 의 차이는 **투영 하나뿐**이다(같은 차원·같은 활성 좌표 수·같은 가중치 원천).
     그래야 "희소성 이득"과 "구조 이득"을 분리할 수 있다.
  4. 승격하지 않는 것도 정상 완료다(`Decision.REJECTED`).
"""

from __future__ import annotations

import hashlib
import math
import random
import statistics
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Final

# ── 종료 코드 ────────────────────────────────────────────────────────────────
# task 25 와 같은 규율: "주장할 근거가 없다"와 "실패했다"와 "위험을 발견했다"를 다른 코드로 둔다.
EXIT_OK: Final = 0
EXIT_USAGE: Final = 1
EXIT_INPUT_MISSING: Final = 2
EXIT_FIXTURE_REJECTED: Final = 3
EXIT_SAFETY_VIOLATION: Final = 4
EXIT_OUTPUT_ERROR: Final = 5
EXIT_REJECTED_EXPERIMENT: Final = 10

EXIT_MEANINGS: Final[Mapping[int, str]] = {
    EXIT_OK: "PASS — 승격 후보가 있다(기준을 만족한 조건이 하나 이상)",
    EXIT_USAGE: "인자 오류",
    EXIT_INPUT_MISSING: "필수 입력(fixture·corpus·mask) 부재",
    EXIT_FIXTURE_REJECTED: "fixture 거절 — leakage·빈 corpus 등 실험 자격 미달",
    EXIT_SAFETY_VIOLATION: "안전 위반 — scope 밖·철회·만료·삭제된 기억이 반환됐다(절대 완화 금지)",
    EXIT_OUTPUT_ERROR: "산출물 쓰기 실패",
    EXIT_REJECTED_EXPERIMENT: "기각/불충분 — 유의한 개선이 없다(정상 완료)",
}


class Decision(StrEnum):
    """실험 하나의 결말. `NOT_RUN` 을 `REJECTED` 로 위장하지 않는다."""

    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    NOT_RUN = "NOT_RUN"


class SafetyViolation(StrEnum):
    """회수 결과가 지켜야 하는 것 — 위반은 하나라도 있으면 실행 자체가 실패다."""

    FOREIGN_OWNER = "foreign_owner"
    CONSENT_WITHDRAWN = "consent_withdrawn"
    EXPIRED = "expired"
    REVOKED = "revoked"
    SESSION_LEAK = "session_leak"


# ── 판정 임계값 (CLI 로 완화 불가) ───────────────────────────────────────────
K: Final = 10
SPARSE_RECALL_DROP_MAX: Final = 0.01  # recall@10 절대 하락 허용
SPARSE_NDCG_DROP_MAX: Final = 0.02  # nDCG@10 절대 하락 허용
SPARSE_RESOURCE_GAIN_MIN: Final = 0.10  # p95 또는 peak RSS 10% 이상 개선
SPARSE_CI_LEVEL: Final = 0.95
BOOTSTRAP_RESAMPLES: Final = 2000

WM_TOKEN_REDUCTION_MIN: Final = 0.10
WM_SUCCESS_DROP_MAX_PP: Final = 0.01
WM_CONSTRAINT_OMISSION_MAX: Final = 0
WM_CROSS_SESSION_LEAK_MAX: Final = 0
WM_OVERFLOW_SILENT_MAX: Final = 0

# grid — "공학적 탐색값이며 실제 뉴런 수를 재현하는 수치가 아니다"(상세안 §4.3)
SPARSE_EXPANSIONS: Final[tuple[int, ...]] = (2048, 4096)
SPARSE_ACTIVE_RATIOS: Final[tuple[float, ...]] = (0.01, 0.05, 0.10)
DENSE_DIM: Final = 512


# ── 공통 ─────────────────────────────────────────────────────────────────────
def stable_hash(*parts: object) -> str:
    digest = hashlib.blake2b(digest_size=16)
    for part in parts:
        digest.update(repr(part).encode("utf-8"))
        digest.update(b"\x1f")
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def percentile(values: Sequence[float], fraction: float) -> float:
    """task 24 와 같은 정의(작은 표본에서 최대값을 p95 로 올린다)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(len(ordered) * fraction + 0.999999) - 1))
    return ordered[index]


def median(values: Sequence[float]) -> float:
    return statistics.median(values) if values else 0.0


def paired_bootstrap_ci(
    deltas: Sequence[float],
    *,
    level: float = SPARSE_CI_LEVEL,
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = 20260926,
) -> tuple[float, float, float]:
    """짝지은 델타의 부트스트랩 신뢰구간. 반환 = (평균, 하한, 상한).

    표본 단위는 **seed 가 아니라 질의**다(상세안 §9: "seed만 표본으로 부풀리지 않는다").
    """
    if not deltas:
        return 0.0, 0.0, 0.0
    observed = mean(deltas)
    rng = random.Random(seed)
    count = len(deltas)
    estimates: list[float] = []
    for _ in range(max(1, resamples)):
        estimates.append(mean([deltas[rng.randrange(count)] for _ in range(count)]))
    estimates.sort()
    tail = (1.0 - level) / 2.0
    low = estimates[min(len(estimates) - 1, max(0, int(tail * len(estimates))))]
    high = estimates[min(len(estimates) - 1, max(0, int((1.0 - tail) * len(estimates)) - 1))]
    return observed, low, high


# ── fixture 해시 임베딩 (모델 아님) ──────────────────────────────────────────
EMBEDDING_KIND: Final = "fixture_hash"  # 실제 모델 임베딩이 아니다 — 결과에 그대로 실린다


def embed(text: str, *, dim: int = DENSE_DIM) -> list[float]:
    """문자 3-gram + 토큰의 부호 있는 해시 임베딩(L2 정규화).

    목적은 품질이 아니라 **재현성**이다: 같은 텍스트 → 언제나 같은 벡터, 의존성 0.
    """
    vector = [0.0] * dim
    normalized = " ".join(str(text or "").lower().split())
    features: list[str] = []
    if normalized:
        features.extend(normalized.split(" "))
        padded = f"  {normalized}  "
        features.extend(padded[index : index + 3] for index in range(len(padded) - 2))
    for feature in features:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[bucket] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm:
        vector = [value / norm for value in vector]
    return vector


def cosine(a: Mapping[int, float], b: Mapping[int, float]) -> float:
    if not a or not b:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    return sum(value * b.get(key, 0.0) for key, value in a.items())


def to_sparse(vector: Sequence[float]) -> dict[int, float]:
    return {index: value for index, value in enumerate(vector) if value}


# ── 희소 투영 ────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class MaskEdge:
    """연결망에서 온 edge 하나. `syn_count` 는 log1p 후 정규화해 가중치로 쓴다."""

    pre: int
    post: int
    syn_count: int


@dataclass(frozen=True)
class Projection:
    """dense feature → 확장 좌표 사상. 조건 간 **차이는 이 객체 하나뿐**이다.

    - `kind`: `random` | `mask` | `mask_shuffled`
    - `coords[d]`: dense feature d 가 활성화하는 좌표(dense feature 당 **하나**)
    - `weights[d]`: 그 좌표의 가중치(양수)

    확장 뒤에는 **k-승자독식(sparsify)** 이 붙는다: `expansion` 좌표 중 활성 비율만큼만 남긴다.
    그래서 "희소성"은 `ratio × expansion` 이 정하고, 여기서 정하는 것은 **어느 좌표로 사상하는가**다.
    """

    kind: str
    expansion: int
    coords: tuple[tuple[int, ...], ...]
    weights: tuple[tuple[float, ...], ...]
    mask_sha256: str = ""
    mask_kind: str = "none"
    seed: int = 0

    @property
    def coordinate_count(self) -> int:
        return sum(len(row) for row in self.coords)

    def digest(self) -> str:
        return stable_hash(
            self.kind,
            self.expansion,
            tuple(self.coords),
            tuple(round(value, 8) for row in self.weights for value in row),
            self.mask_sha256,
            self.mask_kind,
            self.seed,
        )


def keep_count(expansion: int, active_ratio: float) -> int:
    """활성 비율 → 실제로 남기는 좌표 수(kWTA 의 k)."""
    return max(1, int(round(expansion * active_ratio)))


def random_projection(
    *,
    dim: int = DENSE_DIM,
    expansion: int,
    seed: int,
) -> Projection:
    """무작위 확장 — 구조 정보가 전혀 없는 대조군."""
    rng = random.Random(stable_hash("random-projection", dim, expansion, seed))
    coords = tuple((rng.randrange(expansion),) for _ in range(dim))
    weights = tuple((1.0,) for _ in range(dim))
    return Projection(
        kind="random",
        expansion=expansion,
        coords=coords,
        weights=weights,
        seed=seed,
    )


def _edge_coord(root_id: int, expansion: int) -> int:
    return int.from_bytes(hashlib.blake2b(str(root_id).encode("utf-8"), digest_size=8).digest()[:4], "big") % expansion


def _edge_feature(root_id: int, dim: int) -> int:
    return int.from_bytes(hashlib.blake2b(f"f{root_id}".encode("utf-8"), digest_size=8).digest()[:4], "big") % dim


def mask_projection(
    edges: Iterable[MaskEdge],
    *,
    dim: int = DENSE_DIM,
    expansion: int,
    seed: int,
    shuffle: bool,
    mask_sha256: str = "",
    mask_kind: str = "synthetic",
) -> Projection:
    """연결망에서 온 확장.

    dense feature f 는 **그것에 사상된 pre 뉴런의 가장 강한 post 파트너** 좌표로 간다
    (가중치는 그 연결의 log1p syn_count). 좌표 수(합쳐서 dense feature 당 하나)는 `random`
    조건과 동일하다 — 그래야 차이가 "어느 좌표로 가는가" 하나로 좁혀진다.

    `shuffle=True` 는 **degree 보존 대조군**이다: edge 의 post 대응을 고정 seed 로 다시 이어
    붙여 같은 edge 수·같은 차수 분포를 유지하고 구조만 파괴한다(상세안 §8.6).
    """
    buckets: dict[int, dict[int, float]] = {}
    rng = random.Random(stable_hash("mask-shuffle", mask_sha256, seed))
    edge_list = list(edges)
    if shuffle:
        posts = [edge.post for edge in edge_list]
        rng.shuffle(posts)
        edge_list = [
            MaskEdge(pre=edge.pre, post=post, syn_count=edge.syn_count) for edge, post in zip(edge_list, posts)
        ]
    for edge in edge_list:
        feature = _edge_feature(edge.pre, dim)
        coord = _edge_coord(edge.post, expansion)
        buckets.setdefault(feature, {}).setdefault(coord, 0.0)
        buckets[feature][coord] += math.log1p(max(0, edge.syn_count))
    coords: list[tuple[int, ...]] = []
    weights: list[tuple[float, ...]] = []
    filler_rng = random.Random(stable_hash("mask-filler", dim, expansion, seed, mask_sha256))
    for feature in range(dim):
        merged = buckets.get(feature, {})
        if merged:
            coord, weight = sorted(merged.items(), key=lambda pair: (-pair[1], pair[0]))[0]
        else:  # 이 feature 를 쓰는 edge 가 없다 — 무작위 좌표로 채운다(예산·비교 공정성 유지)
            coord, weight = filler_rng.randrange(expansion), 1.0
        coords.append((coord,))
        weights.append((weight,))
    return Projection(
        kind="mask_shuffled" if shuffle else "mask",
        expansion=expansion,
        coords=tuple(coords),
        weights=tuple(weights),
        mask_sha256=mask_sha256,
        mask_kind=mask_kind,
        seed=seed,
    )


def sparsify(code: Mapping[int, float], *, keep: int) -> dict[int, float]:
    """k-승자독식 — 확장 코드에서 **값이 큰 k 개**만 남긴다(동률은 좌표 오름차순).

    FlyHash 계열의 실제 기제이고, 여기서 `keep = round(expansion × 활성 비율)` 이다.
    비밀을 캐시 키로 삼는 문제를 피하려고 **입력값이 아니라 좌표와 크기**만 본다.
    """
    if keep <= 0 or len(code) <= keep:
        return dict(code)
    ranked = sorted(code.items(), key=lambda pair: (-abs(pair[1]), pair[0]))[:keep]
    return dict(sorted(ranked))


def simhash_signature(text: str, *, bits: int, seed: int = 0) -> int:
    """SimHash — 부호 있는 해시 가중합의 부호만 남긴다(bit encoding 고정).

    `seed` 는 채택하지 않는다: 임베딩 자체가 결정적이라 섞을 것이 없고, 시드를 받는 척하면
    "시드를 바꿔도 결과가 같다"는 사실이 가려진다.
    """
    vector = embed(text, dim=bits)
    signature = 0
    for index, value in enumerate(vector):
        if value > 0:
            signature |= 1 << index
    return signature


def hamming_distance(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def project(text: str, projection: Projection, *, dim: int = DENSE_DIM) -> dict[int, float]:
    """텍스트 → 희소 좌표 벡터(사전). 0 이 아닌 좌표만 담는다."""
    vector = embed(text, dim=dim)
    out: dict[int, float] = {}
    for feature, value in enumerate(vector):
        if not value:
            continue
        for coord, weight in zip(projection.coords[feature], projection.weights[feature]):
            out[coord] = out.get(coord, 0.0) + value * weight
    return out


# ── split (누출 방지) ────────────────────────────────────────────────────────
@dataclass(frozen=True)
class SplitRule:
    """사이트/과제군 기준 분리 — 같은 사이트가 calibration 과 holdout 에 동시에 있으면 거절."""

    holdout_sites: tuple[str, ...]
    calibration_sites: tuple[str, ...]
    train_sites: tuple[str, ...]
    rule_version: str = "site-disjoint/2026-09-22"

    def split_of(self, site: str) -> str:
        if site in self.holdout_sites:
            return "holdout"
        if site in self.calibration_sites:
            return "calibration"
        if site in self.train_sites:
            return "train"
        return "unassigned"

    def leakage_reasons(self) -> tuple[str, ...]:
        reasons: list[str] = []
        holdout = set(self.holdout_sites)
        calibration = set(self.calibration_sites)
        train = set(self.train_sites)
        if holdout & calibration:
            reasons.append(f"holdout ∩ calibration = {sorted(holdout & calibration)}")
        if holdout & train:
            reasons.append(f"holdout ∩ train = {sorted(holdout & train)}")
        if calibration & train:
            reasons.append(f"calibration ∩ train = {sorted(calibration & train)}")
        if not holdout:
            reasons.append("holdout 이 비어 있다(누출 이전에 실험이 성립하지 않는다)")
        if not calibration:
            # holdout 만 있는 분리는 누출은 없지만 **빈 껍데기**다: grid/가중치를 어디서 정했는지 말할 수 없다.
            reasons.append("calibration 이 비어 있다(고정했다고 말할 grid 의 근거가 없다)")
        return tuple(reasons)


def assign_sites_to_splits(
    sites: Iterable[str], *, holdout_ratio: float = 0.4, calibration_ratio: float = 0.3
) -> SplitRule:
    """사이트 문자열의 **고정 해시**로 나눈다 — 실행마다 달라지지 않는다.

    비율은 근사치다(난수 없음). 작은 사이트 집합에서도 결정적이며, 그래서 split hash 가 곧 계약이다.
    """
    ordered = sorted({site for site in sites if site})
    if not ordered:
        return SplitRule((), (), ())
    holdout_count = max(1, int(round(len(ordered) * holdout_ratio)))
    calibration_count = max(1, int(round(len(ordered) * calibration_ratio)))
    if holdout_count + calibration_count >= len(ordered):
        calibration_count = max(0, len(ordered) - holdout_count - 1)
    ranked = sorted(ordered, key=lambda site: stable_hash("split", site))
    holdout = tuple(sorted(ranked[:holdout_count]))
    calibration = tuple(sorted(ranked[holdout_count : holdout_count + calibration_count]))
    train = tuple(sorted(ranked[holdout_count + calibration_count :]))
    return SplitRule(holdout, calibration, train)


def leakage_from_queries(
    *,
    calibration_queries: Iterable[str],
    holdout_queries: Iterable[str],
    split: SplitRule,
) -> tuple[str, ...]:
    """질의 수준 누출 검사 — 사이트 분리와 **별개로** 둘 다 잰다."""
    reasons = list(split.leakage_reasons())
    overlap = set(calibration_queries) & set(holdout_queries)
    if overlap:
        reasons.append(f"calibration ∩ holdout 질의 {len(overlap)}건: {sorted(overlap)[:5]}")
    return tuple(reasons)


def cache_key(
    *,
    owner: str,
    scope: str,
    corpus_revision: str,
    embedding_version: str,
    mask_hash: str,
    query: str,
    limit: int,
) -> str:
    """캐시 키 계약 — 이 다섯 축 중 하나라도 빠지면 캐시가 권한을 우회한다."""
    return stable_hash(owner, scope, corpus_revision, embedding_version, mask_hash, query, limit)


# ── 판정 ─────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class SparseMetrics:
    recall_at_k: float
    ndcg_at_k: float
    p95_cold_ms: float
    p95_warm_ms: float
    build_ms: float
    index_nonzeros: int
    peak_rss_bytes: int
    query_count: int


@dataclass(frozen=True)
class SparseVerdict:
    decision: Decision
    reasons: tuple[str, ...]
    recall_delta: float
    ndcg_delta: float
    resource_gain: float
    resource_axis: str
    recall_ci: tuple[float, float, float]
    resource_ci: tuple[float, float, float]
    baseline: str
    condition: str


def decide_sparse_condition(
    *,
    baseline_name: str,
    condition_name: str,
    baseline: SparseMetrics,
    condition: SparseMetrics,
    recall_deltas: Sequence[float],
    p95_deltas: Sequence[float],
    rss_seed_gains: Sequence[float],
    safety_violations: Sequence[str],
) -> SparseVerdict:
    """조건 하나의 승격 판정.

    자원 축을 **두 개로 나눠 각각 증거를 요구**한다:

      - p95: 질의별 짝 델타의 부트스트랩 CI 상한 > 0 이어야 한다.
      - RSS: 질의별 표본이 없으므로(팔 단위 측정이다) **모든 seed 에서 10% 이상**이어야 한다.
        CI 를 흉내내지 않고 대신 전 seed 일치를 요구한다.

    안전 위반은 판정 이전에 실패다(호출자가 exit 4 로 끝낸다).
    """
    if safety_violations:
        return SparseVerdict(
            Decision.REJECTED,
            tuple(f"안전 위반: {name}" for name in safety_violations),
            0.0,
            0.0,
            0.0,
            "none",
            (0.0, 0.0, 0.0),
            (0.0, 0.0, 0.0),
            baseline_name,
            condition_name,
        )
    reasons: list[str] = []
    recall_delta = condition.recall_at_k - baseline.recall_at_k
    ndcg_delta = condition.ndcg_at_k - baseline.ndcg_at_k
    p95_gain = (baseline.p95_warm_ms - condition.p95_warm_ms) / baseline.p95_warm_ms if baseline.p95_warm_ms else 0.0
    rss_gain = (
        (baseline.peak_rss_bytes - condition.peak_rss_bytes) / baseline.peak_rss_bytes
        if baseline.peak_rss_bytes
        else 0.0
    )
    recall_ci = paired_bootstrap_ci(list(recall_deltas))
    p95_ci = paired_bootstrap_ci(list(p95_deltas))
    rss_stable = bool(rss_seed_gains) and all(gain >= SPARSE_RESOURCE_GAIN_MIN for gain in rss_seed_gains)
    p95_axis = p95_gain >= SPARSE_RESOURCE_GAIN_MIN and p95_ci[2] > 0.0
    rss_axis = rss_gain >= SPARSE_RESOURCE_GAIN_MIN and rss_stable
    resource_axis = "p95" if p95_axis else ("rss" if rss_axis else "none")
    resource_gain = max(p95_gain, rss_gain)

    def _verdict(decision: Decision) -> SparseVerdict:
        return SparseVerdict(
            decision,
            tuple(reasons),
            recall_delta,
            ndcg_delta,
            resource_gain,
            resource_axis,
            recall_ci,
            p95_ci,
            baseline_name,
            condition_name,
        )

    if recall_delta < -SPARSE_RECALL_DROP_MAX:
        reasons.append(f"recall@{K} 하락 {recall_delta:+.4f} > 허용 {SPARSE_RECALL_DROP_MAX}")
        return _verdict(Decision.REJECTED)
    if ndcg_delta < -SPARSE_NDCG_DROP_MAX:
        reasons.append(f"nDCG@{K} 하락 {ndcg_delta:+.4f} > 허용 {SPARSE_NDCG_DROP_MAX}")
        return _verdict(Decision.REJECTED)
    if recall_ci[1] < -SPARSE_RECALL_DROP_MAX:
        reasons.append(f"recall CI 하한 {recall_ci[1]:+.4f} 이 허용 하락을 넘는다 — 실질 하락을 배제할 수 없다")
        return _verdict(Decision.INCONCLUSIVE)
    if resource_axis == "none":
        if resource_gain < SPARSE_RESOURCE_GAIN_MIN:
            reasons.append(
                f"자원 개선 최대 {resource_gain:.4f} < 요구 {SPARSE_RESOURCE_GAIN_MIN}(품질은 지켰지만 얻은 것이 없다)"
            )
            return _verdict(Decision.REJECTED)
        reasons.append(
            f"p95 이득 {p95_gain:+.4f}(CI 상한 {p95_ci[2]:+.4f}) · RSS 이득 {rss_gain:+.4f}"
            f"(전 seed 일치 {rss_stable}) — 어느 축도 요구를 증거와 함께 넘지 못한다"
        )
        return _verdict(Decision.INCONCLUSIVE)
    reasons.append(
        f"recall {recall_delta:+.4f}(허용 −{SPARSE_RECALL_DROP_MAX}) · nDCG {ndcg_delta:+.4f}(허용 −{SPARSE_NDCG_DROP_MAX}) "
        f"· 자원 축 {resource_axis}(p95 {p95_gain:+.4f}/CI 상한 {p95_ci[2]:+.4f} · RSS {rss_gain:+.4f}/전 seed 일치 {rss_stable})"
    )
    return _verdict(Decision.ACCEPTED)


# ── 작업 기억(B04) ───────────────────────────────────────────────────────────
class ItemKind(StrEnum):
    CONSTRAINT = "constraint"  # 사용자 목표·승인 범위·금지 정책 — 강제 제약(삭제 불가)
    EVIDENCE = "evidence"  # 측정으로 확인된 증거
    OBSERVATION = "observation"  # 페이지 텍스트 등 낮은 신뢰 관찰
    STALE = "stale"  # 오래된 오답(정정으로 superseded)
    MALICIOUS = "malicious"  # 악성 페이지가 심으려 한 문장


@dataclass(frozen=True)
class MemoryItem:
    item_id: str
    kind: ItemKind
    text: str
    session: str
    goal_relevance: float
    recency: float
    verified: bool
    has_evidence: bool
    observed_at: float
    pinned: bool = False
    required: bool = False  # 이 항목이 사라지면 그 케이스는 실패다
    superseded_by: str = ""
    duplicate_of: str = ""
    externalizable: bool = False  # 비핵심 증거 참조 — 문맥 밖으로 밀어낼 수 있다

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.text)


def estimate_tokens(text: str) -> int:
    """프로젝트 `TokenEstimator` 와 같은 규칙(문자 기반 추정) — 값이 아니라 축을 재기 위한 것."""
    stripped = str(text or "").strip()
    return max(1, (len(stripped) + 3) // 4) if stripped else 0


@dataclass(frozen=True)
class WMCase:
    case_id: str
    kind: str  # mid_goal_change | interrupt_resume | stale_answer | malicious_page | concurrent_sessions
    goal: str
    token_budget: int
    items: tuple[MemoryItem, ...]
    required_ids: tuple[str, ...]
    constraint_ids: tuple[str, ...]
    session: str

    def by_id(self) -> dict[str, MemoryItem]:
        return {item.item_id: item for item in self.items}


@dataclass(frozen=True)
class WMSelection:
    condition: str
    case_id: str
    kept: tuple[str, ...]
    dropped: tuple[str, ...]
    externalized: tuple[str, ...]
    tokens: int
    overflow_reported: bool
    silent_drop: tuple[str, ...]
    cross_session: tuple[str, ...]
    constraint_omissions: tuple[str, ...]
    evidence_loss_without_source: tuple[str, ...]
    malicious_verbatim: tuple[str, ...] = ()  # 악성 페이지 지시문이 **그대로** 문맥에 실린 항목
    payload: tuple[tuple[str, str], ...] = ()  # (item_id, text) — 요약 조건은 본문을 바꾼다


@dataclass(frozen=True)
class WMVerdict:
    decision: Decision
    reasons: tuple[str, ...]
    token_reduction: float
    success: float
    baseline_success: float
    constraint_omissions: int
    cross_session_leaks: int
    silent_drops: int


def decide_working_memory(
    *,
    condition: str,
    baseline_success: float,
    condition_success: float,
    baseline_tokens: float,
    condition_tokens: float,
    constraint_omissions: int,
    cross_session_leaks: int,
    silent_drops: int,
    failure_cost: float = 0.0,
) -> WMVerdict:
    """작업 기억 조건의 승격 판정 — 네 축을 **모두** 만족해야 한다."""
    reasons: list[str] = []
    token_reduction = (baseline_tokens - condition_tokens) / baseline_tokens if baseline_tokens else 0.0
    success_drop = baseline_success - condition_success
    if constraint_omissions > WM_CONSTRAINT_OMISSION_MAX:
        reasons.append(f"제약 누락 {constraint_omissions}건 > 0 — 권한을 넓히는 손실은 어떤 이득으로도 상쇄되지 않는다")
    if cross_session_leaks > WM_CROSS_SESSION_LEAK_MAX:
        reasons.append(f"교차 세션 누출 {cross_session_leaks}건 > 0")
    if silent_drops > WM_OVERFLOW_SILENT_MAX:
        reasons.append(f"조용한 폐기 {silent_drops}건 > 0 — 초과는 보고하거나 외부화해야 한다")
    if success_drop > WM_SUCCESS_DROP_MAX_PP:
        reasons.append(f"성공 하락 {success_drop * 100:.2f}%p > 허용 {WM_SUCCESS_DROP_MAX_PP * 100:.2f}%p")
    if token_reduction < WM_TOKEN_REDUCTION_MIN:
        reasons.append(f"토큰 감소 {token_reduction:.4f} < 요구 {WM_TOKEN_REDUCTION_MIN}")
    if reasons:
        # 실패 사유가 하나라도 있으면 승격하지 않는다 — 네 축은 **모두** 만족해야 하는 조건이다.
        # `failure_cost` 는 기록용(케이스당 실패 비용)이며 판정을 완화하지 않는다.
        _ = failure_cost
        return WMVerdict(
            Decision.REJECTED,
            tuple(reasons),
            token_reduction,
            condition_success,
            baseline_success,
            constraint_omissions,
            cross_session_leaks,
            silent_drops,
        )
    reasons.append(
        f"제약 누락 0 · 교차 세션 0 · 조용한 폐기 0 · 성공 하락 {success_drop * 100:+.2f}%p(허용 "
        f"{WM_SUCCESS_DROP_MAX_PP * 100:.2f}%p) · 토큰 감소 {token_reduction:.4f} ≥ {WM_TOKEN_REDUCTION_MIN}"
    )
    return WMVerdict(
        Decision.ACCEPTED,
        tuple(reasons),
        token_reduction,
        condition_success,
        baseline_success,
        constraint_omissions,
        cross_session_leaks,
        silent_drops,
    )


# ── 결과 보고 양식(B08·상세안 §11) ───────────────────────────────────────────
@dataclass
class ExperimentRecord:
    """조건 하나의 보고 레코드 — 필드가 비면 그 사실이 리포트에 드러난다."""

    hypothesis: str
    baseline: str
    dataset: str
    split_hash: str
    code_hash: str
    config_hash: str
    budget: dict[str, object] = field(default_factory=dict)
    n_tasks: int = 0
    seeds: tuple[int, ...] = ()
    metrics: dict[str, object] = field(default_factory=dict)
    ci: dict[str, object] = field(default_factory=dict)
    failures: tuple[str, ...] = ()
    safety: dict[str, object] = field(default_factory=dict)
    resources: dict[str, object] = field(default_factory=dict)
    decision: str = str(Decision.NOT_RUN)
    limitations: tuple[str, ...] = ()
    reproduction_command: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "hypothesis": self.hypothesis,
            "baseline": self.baseline,
            "dataset": self.dataset,
            "split_hash": self.split_hash,
            "code_hash": self.code_hash,
            "config_hash": self.config_hash,
            "budget": dict(self.budget),
            "n_tasks": self.n_tasks,
            "seeds": list(self.seeds),
            "metrics": dict(self.metrics),
            "ci": dict(self.ci),
            "failures": list(self.failures),
            "safety": dict(self.safety),
            "resources": dict(self.resources),
            "decision": self.decision,
            "limitations": list(self.limitations),
            "reproduction_command": self.reproduction_command,
        }
