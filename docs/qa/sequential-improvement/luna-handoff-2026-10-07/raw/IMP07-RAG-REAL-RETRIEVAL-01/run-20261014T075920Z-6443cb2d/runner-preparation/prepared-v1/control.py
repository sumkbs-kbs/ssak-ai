from __future__ import annotations

import hashlib
import json
import math
import socket
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Literal, TypedDict, final, override

import httpx
from pydantic import BaseModel, ConfigDict, StringConstraints


class Query(TypedDict):
    id: str
    group: Literal["controlled", "exploratory"]
    language: Literal["en", "ko"]
    text: str


class Oracle(TypedDict):
    query_id: str
    source_path: str
    answer_fact: str


class QueryFile(BaseModel):
    model_config = ConfigDict(strict=True)
    queries: list[Query]


class OracleFile(BaseModel):
    model_config = ConfigDict(strict=True)
    oracles: list[Oracle]


class EmbeddingRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    model: Literal["nomic-embed-text:latest"]
    input: list[str]
    truncate: Literal[False]


class SourceFreeze(BaseModel):
    model_config = ConfigDict(strict=True)
    authorization: Literal["ROOT_GO"]
    retrieval_mode: Literal["semantic"]
    source_root: Path
    sources: dict[str, Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]]


class Phase(BaseModel):
    model_config = ConfigDict(strict=True)
    name: Literal["semantic", "peer"]
    started_monotonic: float


def load_freeze(path: Path, fixture: Path) -> SourceFreeze:
    freeze = SourceFreeze.model_validate_json(path.read_bytes())
    required = {
        str(fixture / "runner-preparation" / name)
        for name in ("control.py", "runner.py", "supervisor.py", "test_control.py")
    }
    required.add(str(fixture / "fixture-manifest.sha256"))
    required.add(str(fixture / "profile-clarification.json"))
    if not required.issubset(freeze.sources):
        raise ValueError("Freeze omits governing runner/fixture sources")
    if not freeze.source_root.is_absolute():
        raise ValueError("Source root must be absolute")
    for source, digest in freeze.sources.items():
        file = Path(source)
        if not file.is_absolute() or not (
            file.resolve().is_relative_to(freeze.source_root.resolve())
            or file.resolve().is_relative_to(fixture.resolve())
        ):
            raise ValueError("Frozen source outside owned fixture and candidate roots")
        if sha(file) != digest:
            raise ValueError(f"Frozen source changed: {source}")
    return freeze


MODEL = "nomic-embed-text:latest"
DIGEST = "0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f"
BASE = "http://127.0.0.1:11434"
PHASE_LIMITS = {
    "index-a": 2,
    "index-b": 1,
    "queries-a": 20,
    "queries-b": 2,
    "mutation": 1,
    "queries-mutated": 2,
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)


def verify_manifest(root: Path, name: str) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for line in (root / name).read_text().splitlines():
        digest, relative = line.split(maxsplit=1)
        relative = relative.lstrip("*")
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()) or sha(path) != digest:
            raise ValueError(f"Source preimage changed: {relative}")
        hashes[relative] = digest
    return hashes


def score(paths: list[str], expected: str) -> dict[str, float | int | None]:
    rank = next(
        (index for index, source in enumerate(paths[:5], 1) if source == expected), None
    )
    return {
        "rank": rank,
        "recall_at_5": int(rank is not None),
        "mrr_at_5": 1 / rank if rank else 0.0,
        "ndcg_at_5": 1 / math.log2(rank + 1) if rank else 0.0,
    }


def validate_oracles(fixture: Path) -> tuple[list[Query], dict[str, Oracle]]:
    queries = QueryFile.model_validate_json(
        (fixture / "queries.json").read_bytes()
    ).queries
    rows = OracleFile.model_validate_json(
        (fixture / "oracles.json").read_bytes()
    ).oracles
    oracles = {row["query_id"]: row for row in rows}
    if (
        len(queries) != 20
        or len(oracles) != 20
        or len({q["id"] for q in queries}) != 20
    ):
        raise ValueError("Twenty unique queries and source oracles required")
    if Counter(q["group"] for q in queries) != {"controlled": 10, "exploratory": 10}:
        raise ValueError("Frozen group balance changed")
    if Counter(q["language"] for q in queries) != {"en": 10, "ko": 10}:
        raise ValueError("Frozen language balance changed")
    for query in queries:
        oracle = oracles[query["id"]]
        path = (fixture / "corpus-a" / oracle["source_path"]).resolve()
        if (
            not path.is_relative_to((fixture / "corpus-a").resolve())
            or not path.is_file()
        ):
            raise ValueError("Missing or escaping oracle source")
        if oracle["answer_fact"] in query["text"]:
            raise ValueError("Answer leaked into query")
    return queries, oracles


@final
class Budget:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self.clock = clock
        self.deadline = clock() + 180
        self.phase = "not-started"
        self.counts: Counter[str] = Counter()
        self.metadata = 0

    def reserve(self, request: httpx.Request) -> float:
        if (
            str(request.url).split("?")[0] != str(request.url)
            or request.url.scheme != "http"
            or request.url.host != "127.0.0.1"
            or request.url.port != 11434
        ):
            raise ValueError("HTTP destination outside exact allowlist")
        remaining = self.deadline - self.clock()
        if remaining <= 0:
            raise TimeoutError("Semantic deadline exhausted")
        if request.method == "GET" and request.url.path in ("/api/tags", "/api/ps"):
            if self.metadata >= 3:
                raise ValueError("Metadata budget exhausted")
            self.metadata += 1
            return min(10.0, remaining)
        if request.method != "POST" or request.url.path != "/api/embed":
            raise ValueError("Only embedding and three metadata requests authorized")
        if (
            self.phase not in PHASE_LIMITS
            or self.counts[self.phase] >= PHASE_LIMITS[self.phase]
        ):
            raise ValueError("Phase inference budget exhausted")
        if sum(self.counts.values()) >= 28 or sum(self.counts.values()) >= 30:
            raise ValueError("Inference budget exhausted")
        body = EmbeddingRequest.model_validate_json(request.content)
        prefix = (
            "search_query: "
            if self.phase.startswith("queries")
            else "search_document: "
        )
        if not body.input:
            raise ValueError("Empty embedding input")
        if self.phase.startswith("queries") and len(body.input) != 1:
            raise ValueError("Queries must be one inference per query")
        if not all(
            text.startswith(prefix)
            and not text[len(prefix) :].startswith(
                ("search_query: ", "search_document: ")
            )
            for text in body.input
        ):
            raise ValueError("Required embedding prefix missing or duplicated")
        self.counts[self.phase] += 1
        return min(55.0, remaining)


@final
class WireTransport(httpx.BaseTransport):
    def __init__(
        self,
        out: Path,
        budget: Budget,
        factory: Callable[[], httpx.BaseTransport] | None = None,
    ):
        self.out, self.budget = out, budget
        self.factory = factory or (
            lambda: httpx.HTTPTransport(retries=0, trust_env=False)
        )
        self.sequence = 0
        self.client_close_calls = 0

    @override
    def close(self) -> None:
        self.client_close_calls += 1

    @override
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        timeout = self.budget.reserve(request)
        request.extensions["timeout"] = dict.fromkeys(
            ("connect", "read", "write", "pool"), timeout
        )
        self.sequence += 1
        stem = f"{self.sequence:03d}"
        request_body = request.read()
        (self.out / f"{stem}.request.bin").write_bytes(request_body)
        receipt = {
            "sequence": self.sequence,
            "phase": self.budget.phase,
            "method": request.method,
            "url": str(request.url),
            "headers": list(request.headers.multi_items()),
            "request_sha256": hashlib.sha256(request_body).hexdigest(),
            "timeout": timeout,
            "input_sha256": [
                hashlib.sha256(text.encode()).hexdigest()
                for text in EmbeddingRequest.model_validate_json(request_body).input
            ]
            if request_body
            else [],
            "status": None,
            "error": None,
        }
        save(self.out / f"{stem}.receipt.json", receipt)
        started = time.monotonic()
        try:
            with self.factory() as transport:
                response = transport.handle_request(request)
                body = response.read()
                (self.out / f"{stem}.response.bin").write_bytes(body)
                receipt.update(
                    status=response.status_code,
                    response_headers=list(response.headers.multi_items()),
                    response_sha256=hashlib.sha256(body).hexdigest(),
                )
                return httpx.Response(
                    response.status_code,
                    headers=response.headers,
                    content=body,
                    request=request,
                )
        except Exception as exc:
            receipt["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            receipt["elapsed_seconds"] = time.monotonic() - started
            save(self.out / f"{stem}.receipt.json", receipt)


def install_socket_guard(journal: Path) -> Counter[str]:
    counts: Counter[str] = Counter()
    original = socket.socket

    class GuardedSocket(original):
        def _check(self, address: object, operation: str) -> None:
            if self.family not in (socket.AF_INET, socket.AF_INET6):
                counts["ipc"] += 1
                return
            allowed = operation in ("connect", "connect_ex") and address == (
                "127.0.0.1",
                11434,
            )
            counts["allowed" if allowed else "denied"] += 1
            with journal.open("a") as stream:
                stream.write(
                    json.dumps(
                        {"operation": operation, "address": address, "allowed": allowed}
                    )
                    + "\n"
                )
            if not allowed:
                raise PermissionError("Physical network outside loopback Ollama denied")

        def connect(self, address):
            self._check(address, "connect")
            return super().connect(address)

        def connect_ex(self, address):
            self._check(address, "connect_ex")
            return super().connect_ex(address)

        def bind(self, address):
            self._check(address, "bind")
            return super().bind(address)

        def sendto(self, data, *args):
            self._check(args[-1], "sendto")
            return super().sendto(data, *args)

    socket.socket = GuardedSocket
    return counts
