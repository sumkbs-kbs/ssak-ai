import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import final

from pydantic import JsonValue

_TOKEN_RE: re.Pattern[str] = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)|\d+|[가-힣]+")
_FEATURE_BUCKETS = 64


@dataclass(frozen=True, slots=True)
class LongContextConfig:
    candidate_pool: int = 128
    max_per_source: int = 2
    manifold_floor: float = 0.02
    sinkhorn_iterations: int = 12


def project_doubly_stochastic(
    matrix: Sequence[Sequence[float]],
    floor: float = 0.02,
    iterations: int = 12,
) -> tuple[tuple[float, ...], ...]:
    size = len(matrix)
    if size == 0 or any(len(row) != size for row in matrix):
        raise ValueError("matrix must be non-empty and square")
    if floor < 0 or floor * size > 1:
        raise ValueError("floor must fit inside a stochastic row")
    values = [[max(float(cell), floor) for cell in row] for row in matrix]
    for _ in range(max(iterations, 1)):
        for row in values:
            total = sum(row)
            for index, cell in enumerate(row):
                row[index] = cell / total
        for column_index in range(size):
            total = sum(values[row_index][column_index] for row_index in range(size))
            for row_index in range(size):
                values[row_index][column_index] /= total
    return tuple(tuple(row) for row in values)


@final
class LongContextFusion:
    def __init__(self, config: LongContextConfig | None = None):
        self.config: LongContextConfig = config or LongContextConfig()
        self._mixing_matrix: tuple[tuple[float, ...], ...] = project_doubly_stochastic(
            ((0.72, 0.18, 0.10), (0.14, 0.76, 0.10), (0.14, 0.16, 0.70)),
            floor=self.config.manifold_floor,
            iterations=self.config.sinkhorn_iterations,
        )

    def rank(
        self,
        query: str,
        sparse_results: Sequence[Mapping[str, JsonValue]],
        dense_results: Sequence[Mapping[str, JsonValue]],
        n_results: int = 5,
        candidate_pool: int | None = None,
    ) -> list[dict[str, JsonValue]]:
        if n_results <= 0:
            return []
        requested_pool = self.config.candidate_pool if candidate_pool is None else candidate_pool
        pool = min(requested_pool, self.config.candidate_pool)
        result_limit = min(n_results, pool)
        if result_limit <= 0:
            return []
        candidates: dict[str, Mapping[str, JsonValue]] = {}
        sparse_scores: dict[str, float] = {}
        dense_scores: dict[str, float] = {}
        for rank, result in enumerate(sparse_results[:pool]):
            candidate_id = self._candidate_id(result)
            if candidate_id not in candidates:
                candidates[candidate_id] = result
            sparse_scores[candidate_id] = max(sparse_scores.get(candidate_id, 0.0), 1.0 / (rank + 1))
        for rank, result in enumerate(dense_results[:pool]):
            candidate_id = self._candidate_id(result)
            if candidate_id not in candidates:
                candidates[candidate_id] = result
            dense_scores[candidate_id] = max(dense_scores.get(candidate_id, 0.0), 1.0 / (rank + 1))

        query_features = self._features(query)
        scored: list[tuple[float, str, dict[str, JsonValue]]] = []
        for candidate_id, result in candidates.items():
            text = " ".join(
                (
                    str(result.get("text", "")),
                    str(self._metadata(result).get("node_name", "")),
                    str(self._metadata(result).get("source", "")),
                ),
            )
            channels = (
                sparse_scores.get(candidate_id, 0.0),
                dense_scores.get(candidate_id, 0.0),
                self._cosine(query_features, self._features(text)),
            )
            fused = sum(weight * channel for weight, channel in zip(self._mixing_matrix[0], channels, strict=True))
            enriched: dict[str, JsonValue] = dict(result)
            metadata = dict(self._metadata(result))
            metadata.update(
                {
                    "retrieval_architecture": "sparse_linear_mhc",
                    "sparse_score": channels[0],
                    "dense_score": channels[1],
                    "linear_score": channels[2],
                    "fusion_score": fused,
                },
            )
            enriched["metadata"] = metadata
            scored.append((fused, candidate_id, enriched))

        scored.sort(key=lambda item: (-item[0], item[1]))
        selected: list[dict[str, JsonValue]] = []
        source_counts: dict[str, int] = {}
        for _, candidate_id, result in scored:
            source = str(self._metadata(result).get("source") or candidate_id)
            if source_counts.get(source, 0) >= self.config.max_per_source:
                continue
            selected.append(result)
            source_counts[source] = source_counts.get(source, 0) + 1
            if len(selected) >= result_limit:
                break
        return selected

    @staticmethod
    def _candidate_id(result: Mapping[str, JsonValue]) -> str:
        value = result.get("id")
        if isinstance(value, str) and value:
            return value
        metadata = result.get("metadata")
        identity = json.dumps(
            {
                "text": result.get("text", ""),
                "metadata": dict(metadata) if isinstance(metadata, dict) else {},
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(identity.encode()).hexdigest()[:24]
        return f"chunk:{digest}"

    @staticmethod
    def _metadata(result: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
        metadata = result.get("metadata")
        return dict(metadata) if isinstance(metadata, dict) else {}

    @staticmethod
    def _features(text: str) -> tuple[float, ...]:
        features = [0.0] * _FEATURE_BUCKETS
        tokens: list[str] = _TOKEN_RE.findall(text)
        for token in tokens:
            bucket = int.from_bytes(hashlib.blake2b(token.lower().encode(), digest_size=2).digest(), "big")
            features[bucket % _FEATURE_BUCKETS] += 1.0
        return tuple(features)

    @staticmethod
    def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
        numerator = sum(a * b for a, b in zip(left, right, strict=True))
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm == 0.0 or right_norm == 0.0:
            return 0.0
        return numerator / (left_norm * right_norm)
