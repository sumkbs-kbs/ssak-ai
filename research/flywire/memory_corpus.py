"""task 26 corpus — **이미 봉인된 task 24 검색셋**에서 기억 문서를 유도하고, 권한 축을 얹는다.

여기서 새로 만드는 것은 문서가 아니라 **접근 축**이다. 문서·질의·관련도(graded)는 task 24 가
동결한 `tests/fixtures/ssak_search_eval/` 에서 그대로 가져온다(그 파일은 해시로 봉인돼 있다).
그 위에 task 21 의 기억 계약(owner · scope · 동의 · 만료 · 철회)을 얹어, 검색 채널이
**권한을 우회하지 않는지**를 잴 수 있게 한다.

정직성: 원문 payload 의 관련도는 "그 케이스의 질의에 대한" 라벨이다. 다른 질의에 대해서는
라벨이 없으므로 0 으로 센다(`unlabeled_treated_as_zero`). 표준적인 pooled 평가의 한계이며
리포트의 limitations 에 그대로 실린다.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

# `research/flywire` 는 패키지가 아니라 **스크립트 묶음**이다 — 형제 모듈을 스크립트 디렉터리 기준으로 import 한다
# (task 25 와 같은 규칙: `uv run research/flywire/<script>.py`).
import memory_contract as contract  # pyright: ignore[reportImplicitRelativeImport]
from memory_contract import MaskEdge  # pyright: ignore[reportImplicitRelativeImport]

SPLIT_VERSION = "site-disjoint/2026-09-22"
UNLABELED_TREATED_AS = 0
OWNER_WORKSPACE = "workspace"
OWNER_FOREIGN = "external-team"


@dataclass(frozen=True)
class CorpusDocument:
    """기억 문서 하나 — 본문은 검색셋 payload 에서, 접근 축은 여기서 온다."""

    doc_id: str
    url: str
    site: str
    partition: str  # scope 축(카테고리)
    title: str
    snippet: str
    owner: str
    consent_withdrawn: bool
    revoked: bool
    expired: bool

    @property
    def text(self) -> str:
        return f"{self.title} {self.snippet} {self.url}"

    @property
    def accessible_for(self) -> str:
        return OWNER_WORKSPACE

    def to_dict(self) -> dict[str, object]:
        return {
            "doc_id": self.doc_id,
            "url": self.url,
            "site": self.site,
            "partition": self.partition,
            "title": self.title,
            "owner": self.owner,
            "consent_withdrawn": self.consent_withdrawn,
            "revoked": self.revoked,
            "expired": self.expired,
        }


@dataclass(frozen=True)
class CorpusQuery:
    case_id: str
    query: str
    partition: str
    site: str
    split: str
    relevant_doc_ids: tuple[str, ...]  # 접근 가능한 정답(라벨 > 0)
    relevant_grades: Mapping[str, int]
    forbidden_doc_ids: tuple[str, ...]  # 접근 불가지만 라벨은 있는 문서 — 반환되면 위반
    authority_expectation: str


@dataclass(frozen=True)
class Corpus:
    documents: tuple[CorpusDocument, ...]
    queries: tuple[CorpusQuery, ...]
    split: contract.SplitRule
    eval_fixture_sha256: str
    corpus_revision: str
    unlabeled_treated_as: int = UNLABELED_TREATED_AS
    notes: tuple[str, ...] = field(default_factory=tuple)

    def partition_of(self, name: str) -> tuple[CorpusDocument, ...]:
        return tuple(doc for doc in self.documents if doc.partition == name)

    def holdout_queries(self) -> tuple[CorpusQuery, ...]:
        return tuple(query for query in self.queries if query.split == "holdout")

    def calibration_queries(self) -> tuple[CorpusQuery, ...]:
        return tuple(query for query in self.queries if query.split == "calibration")

    def split_hash(self) -> str:
        return contract.stable_hash(
            SPLIT_VERSION,
            self.split.holdout_sites,
            self.split.calibration_sites,
            self.split.train_sites,
            tuple(sorted(query.case_id for query in self.queries)),
        )


class FixtureRejected(RuntimeError):
    """실험 자격 미달(누출·빈 corpus) — exit 3 으로 끝난다."""

    def __init__(self, reasons: Sequence[str]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = tuple(reasons)


def _dominant_site(payload: Sequence[object]) -> str:
    """케이스가 **어느 사이트에서 수행된 과제인가** — payload 에서 가장 많이 나온 사이트.

    첫 히트의 사이트를 쓰면 상위 결과가 남의 사이트일 때 split 이 흔들린다(그러면 누출 검사가
    실제와 다른 것을 잰다). 동수면 사전순으로 고정한다.
    """
    counts: dict[str, int] = {}
    for hit in payload:
        if isinstance(hit, (list, tuple)) and hit:
            counts[_site_of(str(hit[0]))] = counts.get(_site_of(str(hit[0])), 0) + 1
    if not counts:
        return ""
    return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[0][0]


def _site_of(url: str) -> str:
    body = str(url or "").split("://", 1)[-1]
    host = body.split("/", 1)[0].split("?", 1)[0].lower()
    parts = [part for part in host.split(".") if part]
    if len(parts) >= 3 and parts[-2] in {"co", "or", "ne", "go", "ac"}:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def load_eval_payloads(eval_root: Path) -> list[dict[str, object]]:
    """동결된 검색셋의 케이스 전부를 파일 순서대로 읽는다(순서가 곧 계약)."""
    manifest_path = eval_root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"검색셋 manifest 가 없다: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    categories = manifest.get("categories")
    if not isinstance(categories, list):
        raise ValueError("manifest.categories 가 리스트가 아니다")
    cases: list[dict[str, object]] = []
    for entry in categories:
        if not isinstance(entry, Mapping):
            continue
        relative = entry.get("file")
        if not isinstance(relative, str):
            continue
        payload = json.loads((eval_root / relative).read_text(encoding="utf-8"))
        category = str(payload.get("category", ""))
        raw_cases = payload.get("cases")
        if not isinstance(raw_cases, list):
            continue
        for case in raw_cases:
            if isinstance(case, Mapping):
                cases.append({**case, "category": category})
    return cases


def _access_axes(doc_id: str, site: str) -> tuple[str, bool, bool, bool]:
    """접근 축을 **문서 해시로** 정한다(난수 없음 → 실행마다 같다).

    문서의 17% 정도가 접근 불가 축을 하나씩 갖는다. 이 문서들은 색인에 **남아 있고**,
    그래서 "권한을 우회하지 않는가"가 실제로 재어진다.
    """
    bucket = int(contract.stable_hash("access", doc_id)[:4], 16) % 100
    foreign = bucket < 6
    withdrawn = 6 <= bucket < 10
    revoked = 10 <= bucket < 13
    expired = 13 <= bucket < 17
    return (OWNER_FOREIGN if foreign else OWNER_WORKSPACE, withdrawn, revoked, expired)


def build_corpus(
    *,
    eval_root: Path,
    holdout_ratio: float = 0.4,
    calibration_ratio: float = 0.3,
    inject_leakage: bool = False,
    inject_query_overlap: bool = False,
    inject_empty_corpus: bool = False,
) -> Corpus:
    """검색셋 → 기억 corpus. 주입은 **실패 fixture 를 실제로 만든다**(시험이 그 문을 잰다).

    누출 검사는 두 층이다(하나로 합치지 않는다):
      1. **사이트 분리** — 같은 사이트가 calibration 과 holdout 에 동시에 있으면 거절
      2. **질의 중복** — 같은 질의가 양쪽에 있으면 거절
    `inject_leakage` 는 1을, `inject_query_overlap` 은 2를 깨뜨려 각 층의 문을 따로 연다.
    """
    cases = load_eval_payloads(eval_root)
    if not cases:
        raise FixtureRejected(["검색셋에 케이스가 없다"])

    documents: dict[str, CorpusDocument] = {}  # canonical id = url
    for case in cases:
        partition = str(case.get("category", ""))
        payload = case.get("payload")
        if not isinstance(payload, list):
            continue
        for index, hit in enumerate(payload):
            if not isinstance(hit, (list, tuple)) or len(hit) < 3:
                continue
            url = str(hit[0])
            if url in documents:
                continue
            doc_id = f"{partition}::{index}::{contract.sha256_text(url)[:12]}"
            owner, withdrawn, revoked, expired = _access_axes(doc_id, _site_of(url))
            documents[url] = CorpusDocument(
                doc_id=doc_id,
                url=url,
                site=_site_of(url),
                partition=partition,
                title=str(hit[1]),
                snippet=str(hit[2]),
                owner=owner,
                consent_withdrawn=withdrawn,
                revoked=revoked,
                expired=expired,
            )

    if inject_empty_corpus:
        documents.clear()

    by_url = documents
    queries: list[CorpusQuery] = []
    for case in cases:
        payload = case.get("payload")
        if not isinstance(payload, list):
            continue
        grades: dict[str, int] = {}
        for hit in payload:
            if not isinstance(hit, (list, tuple)) or len(hit) < 4:
                continue
            try:
                grade = int(hit[3])
            except (TypeError, ValueError):
                continue
            url = str(hit[0])
            if grade > 0:
                grades[url] = grade
        if not grades:
            continue
        accessible: list[str] = []
        forbidden: list[str] = []
        for url in grades:
            doc = by_url.get(url)
            if doc is None:
                continue
            if doc.owner != OWNER_WORKSPACE or doc.consent_withdrawn or doc.revoked or doc.expired:
                forbidden.append(doc.doc_id)
            else:
                accessible.append(doc.doc_id)
        partition = str(case.get("category", ""))
        queries.append(
            CorpusQuery(
                case_id=str(case.get("case_id", "")),
                query=str(case.get("query", "")),
                partition=partition,
                site=_dominant_site(payload),
                split="",
                relevant_doc_ids=tuple(sorted(accessible)),
                relevant_grades={
                    by_url[url].doc_id: grade
                    for url, grade in grades.items()
                    if url in by_url and by_url[url].doc_id in set(accessible)
                },
                forbidden_doc_ids=tuple(sorted(forbidden)),
                authority_expectation=str(case.get("authority_expectation", "n/a")),
            )
        )

    if not documents:
        raise FixtureRejected(["빈 corpus — 색인할 문서가 없다"])
    split = contract.assign_sites_to_splits(
        (doc.site for doc in documents.values()), holdout_ratio=holdout_ratio, calibration_ratio=calibration_ratio
    )
    if inject_leakage and split.holdout_sites:
        # 주입 1: holdout 사이트를 calibration 에도 넣는다 — 사이트 분리 검사가 잡아야 한다.
        leaked_site = split.holdout_sites[0]
        split = contract.SplitRule(
            holdout_sites=split.holdout_sites,
            calibration_sites=tuple(sorted(set(split.calibration_sites) | {leaked_site})),
            train_sites=split.train_sites,
            rule_version=split.rule_version,
        )
    assigned: list[CorpusQuery] = [
        CorpusQuery(
            case_id=query.case_id,
            query=query.query,
            partition=query.partition,
            site=query.site,
            split=split.split_of(query.site),
            relevant_doc_ids=query.relevant_doc_ids,
            relevant_grades=query.relevant_grades,
            forbidden_doc_ids=query.forbidden_doc_ids,
            authority_expectation=query.authority_expectation,
        )
        for query in queries
    ]
    if inject_query_overlap:
        # 주입 2: holdout 질의를 calibration 에 **복제**한다 — 질의 중복 검사가 잡아야 한다.
        duplicated = next((q for q in assigned if q.split == "holdout"), None)
        if duplicated is not None:
            assigned.append(
                CorpusQuery(
                    case_id=f"{duplicated.case_id}::leak",
                    query=duplicated.query,
                    partition=duplicated.partition,
                    site=duplicated.site,
                    split="calibration",
                    relevant_doc_ids=duplicated.relevant_doc_ids,
                    relevant_grades=duplicated.relevant_grades,
                    forbidden_doc_ids=duplicated.forbidden_doc_ids,
                    authority_expectation=duplicated.authority_expectation,
                )
            )

    leakage = contract.leakage_from_queries(
        calibration_queries=[q.query for q in assigned if q.split == "calibration"],
        holdout_queries=[q.query for q in assigned if q.split == "holdout"],
        split=split,
    )
    if leakage:
        raise FixtureRejected(leakage)
    holdout = [q for q in assigned if q.split == "holdout"]
    if not holdout:
        raise FixtureRejected(["holdout 질의가 없다 — holdout 없이 승격을 주장할 수 없다"])

    fixture_hash = contract.stable_hash(
        SPLIT_VERSION,
        tuple(sorted(by_url)),
        tuple((case.get("case_id"), case.get("query")) for case in cases),
    )
    return Corpus(
        documents=tuple(by_url.values()),
        queries=tuple(assigned),
        split=split,
        eval_fixture_sha256=fixture_hash,
        corpus_revision=contract.stable_hash("corpus", fixture_hash, len(by_url)),
        notes=(
            "관련도 라벨은 task 24 동결 검색셋의 graded payload 에서 왔고, 그 라벨은 각 케이스의 질의에 대한 것이다.",
            f"다른 질의에 대해서는 라벨이 없으므로 {UNLABELED_TREATED_AS} 으로 센다(pooled 평가의 한계).",
            "접근 불가(다른 owner·동의 철회·철회·만료) 문서는 색인에 남겨 둔다 — 우회 여부를 재기 위해서다.",
            "정답 집합은 **접근 가능한** 라벨>0 문서로만 구성한다(정당한 배제가 recall 을 깎지 않게).",
        ),
    )


# ── 권한 계층 ────────────────────────────────────────────────────────────────
class AccessPolicy:
    """후보 필터와 **반환 재검증**을 분리하지 않는다 — 둘 다 여기를 지난다.

    두 단계를 따로 끌 수 있게 둔 이유는 **이빨(주입) 때문**이다: 필터만 우회시켜도 재검증이
    잡아야 하고, 그 문을 시험이 실제로 열어 본다(우회 불가를 주장이 아니라 측정으로 둔다).
    """

    def __init__(self, *, owner: str, scope: str, enforce_filter: bool = True, enforce_verify: bool = True) -> None:
        self.owner = owner
        self.scope = scope
        self.enforce_filter = enforce_filter
        self.enforce_verify = enforce_verify

    @property
    def enforce(self) -> bool:
        return self.enforce_filter and self.enforce_verify

    def candidate_allowed(self, doc: CorpusDocument) -> bool:
        if not self.enforce_filter:
            return True
        if doc.owner != self.owner:
            return False
        if doc.consent_withdrawn or doc.revoked or doc.expired:
            return False
        return doc.partition == self.scope

    def verify(self, docs: Sequence[CorpusDocument]) -> tuple[str, ...]:
        """반환 직전 재검증 — 위반 이름을 돌려준다(빈 튜플이면 통과)."""
        if not self.enforce_verify:
            return ()
        violations: list[str] = []
        for doc in docs:
            if doc.owner != self.owner:
                violations.append(f"{contract.SafetyViolation.FOREIGN_OWNER}:{doc.doc_id}")
            if doc.consent_withdrawn:
                violations.append(f"{contract.SafetyViolation.CONSENT_WITHDRAWN}:{doc.doc_id}")
            if doc.revoked:
                violations.append(f"{contract.SafetyViolation.REVOKED}:{doc.doc_id}")
            if doc.expired:
                violations.append(f"{contract.SafetyViolation.EXPIRED}:{doc.doc_id}")
            if doc.partition != self.scope:
                violations.append(f"scope:{doc.doc_id}")
        return tuple(violations)


# ── mask ─────────────────────────────────────────────────────────────────────
def load_mask_edges_csv(path: Path) -> list[MaskEdge]:
    """task 25 `extract_circuits.py` 가 낸 `pre_root_id,post_root_id,syn_count` CSV."""
    edges: list[MaskEdge] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
        if header is None or header[:3] != ["pre_root_id", "post_root_id", "syn_count"]:
            raise ValueError(f"mask CSV 의 헤더가 예상과 다르다: {header}")
        for row in reader:
            if len(row) < 3:
                continue
            edges.append(MaskEdge(pre=int(row[0]), post=int(row[1]), syn_count=int(row[2])))
    if not edges:
        raise ValueError("mask CSV 에 edge 가 없다")
    return edges


def synthetic_mask_edges(*, count: int, pre_pool: int, post_pool: int, seed: int) -> list[MaskEdge]:
    """합성 mask — 시험·기본 실행용. **생물학적 주장의 근거가 아니다**(mask_kind=synthetic)."""
    import random

    rng = random.Random(contract.stable_hash("synthetic-mask", count, pre_pool, post_pool, seed))
    pre_ids = sorted(rng.sample(range(72_057_594_060_000_000, 72_057_594_060_000_000 + pre_pool * 37), pre_pool))
    post_ids = sorted(rng.sample(range(72_057_594_070_000_000, 72_057_594_070_000_000 + post_pool * 41), post_pool))
    edges: list[MaskEdge] = []
    for _ in range(count):
        edges.append(
            MaskEdge(
                pre=pre_ids[rng.randrange(pre_pool)],
                post=post_ids[rng.randrange(post_pool)],
                syn_count=rng.randint(1, 120),
            )
        )
    return edges


def mask_provenance(circuits_json: Path | None) -> dict[str, object]:
    """task 25 의 `circuits.json` 에서 **판정·해시**를 그대로 인용한다(주장을 스스로 하지 않는다)."""
    if circuits_json is None or not circuits_json.is_file():
        return {"available": False, "reason": "circuits.json 이 없다"}
    payload = json.loads(circuits_json.read_text(encoding="utf-8"))
    circuits = payload.get("circuits")
    if not isinstance(circuits, Mapping):
        return {"available": False, "reason": "circuits 블록이 없다"}
    record = circuits.get("KC_to_MBON")
    if not isinstance(record, Mapping):
        return {"available": False, "reason": "KC_to_MBON 기록이 없다"}
    return {
        "available": True,
        "release": payload.get("release"),
        "status": record.get("status"),
        "output_sha256": record.get("output_sha256"),
        "mapping_sha256": payload.get("root_id_index_mapping_sha256"),
        "pre_group": record.get("pre_group"),
        "post_group": record.get("post_group"),
        "pairs": record.get("pairs"),
    }
