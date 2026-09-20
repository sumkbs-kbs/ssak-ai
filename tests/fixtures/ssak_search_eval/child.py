"""검색 벤치마크(task 24)용 stdio MCP child — **기록된 payload 를 그대로 돌려준다**.

벤치마크가 재려는 것은 네트워크가 아니라 **통합 경로**다: MCP 프로토콜 경계(SDK → CallToolResult →
문자열/구조)를 지나 provider adapter 가 결과를 보존하는가. 그래서 여기서는 표준 라이브러리만으로
JSON-RPC(줄 단위) stdio 서버를 띄우고, 결과는 전부 `SSAK_SEARCH_EVAL_PAYLOAD` 파일에서 읽는다.

payload 파일 모양::

    {"queries": {"<query>": {"hits": [[url, title, snippet], ...], "took_ms": 120}}}

노브(전부 env, 전부 주입용):

  - ``SSAK_SEARCH_EVAL_PAYLOAD``     : payload JSON 경로(필수)
  - ``SSAK_SEARCH_EVAL_DELAY_MS``    : 호출마다 추가 대기(느린 provider 주입)
  - ``SSAK_SEARCH_EVAL_SHUFFLE``     : ``1`` 이면 호출마다 hits 순서를 바꾼다(비결정 주입)
  - ``SSAK_SEARCH_EVAL_DROP_HITS``   : ``1`` 이면 hits 를 빈 배열로 돌려준다(빈 결과 주입)
  - ``SSAK_SEARCH_EVAL_CALLS_FILE``  : 호출 기록(``<file>`` = 시작 표시, ``<file>.calls`` = 호출마다 한 줄)

콜드/웜: 같은 질의의 **두 번째 호출부터** ``cached: true`` 와 ``cache_age_ms`` 를 싣는다 — 실제 번들이
내부 캐시를 보고하는 방식이며, provider 가 그 필드를 보존하는지가 task 14 의 계약이다.

기록되지 않은 질의(예: 엔진이 만든 대체 질의)는 **토큰 겹침이 가장 큰** 질의의 payload 를 돌려준다
(동점이면 파일 순서 — 결정적).
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import sys
import time

TOOLS: list[dict[str, object]] = [
    {
        "name": "ssak_search",
        "description": "기록된 검색 payload 를 돌려준다(벤치마크 fixture)",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "max_results": {"type": "integer"}},
            "required": ["query"],
        },
    },
]

_CALL_COUNTS: dict[str, int] = {}
_PAYLOADS: dict[str, dict[str, object]] = {}
_ORDER: list[str] = []


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip() in {"1", "true", "yes", "on"}


def _load_payloads() -> None:
    path = os.environ.get("SSAK_SEARCH_EVAL_PAYLOAD", "").strip()
    if not path:
        raise SystemExit("SSAK_SEARCH_EVAL_PAYLOAD is required")
    with open(path, encoding="utf-8") as handle:
        raw = json.load(handle)
    queries = raw.get("queries") if isinstance(raw, dict) else None
    if not isinstance(queries, dict) or not queries:
        raise SystemExit("payload file must contain a non-empty 'queries' object")
    for query, entry in queries.items():
        if not isinstance(entry, dict):
            raise SystemExit(f"payload entry for {query!r} must be an object")
        _PAYLOADS[str(query)] = entry
        _ORDER.append(str(query))


def _tokens(text: str) -> set[str]:
    return {token for token in "".join(ch if ch.isalnum() else " " for ch in text.casefold()).split() if token}


def _entry_for(query: str) -> tuple[str, dict[str, object]] | None:
    if query in _PAYLOADS:
        return query, _PAYLOADS[query]
    wanted = _tokens(query)
    if not wanted:
        return (_ORDER[0], _PAYLOADS[_ORDER[0]]) if _ORDER else None
    best_key = ""
    best_score = -1.0
    for key in _ORDER:
        shared = len(wanted & _tokens(key))
        score = shared / len(wanted)
        if score > best_score:
            best_key = key
            best_score = score
    if not best_key:
        return None
    return best_key, _PAYLOADS[best_key]


def _hits(entry: dict[str, object]) -> list[dict[str, object]]:
    raw_hits = entry.get("hits")
    if _env_flag("SSAK_SEARCH_EVAL_DROP_HITS"):
        return []
    if not isinstance(raw_hits, list):
        return []
    hits: list[dict[str, object]] = []
    for index, item in enumerate(raw_hits):
        if not isinstance(item, list) or len(item) < 3:
            continue
        url, title, snippet = (str(value) for value in item[:3])
        hits.append(
            {
                "title": title,
                "url": url,
                "snippet": snippet,
                "score": round(max(0.05, 0.95 - index * 0.1), 3),
                "source": "fixture-search",
            }
        )
    return hits


def _record_call(query: str) -> None:
    path = os.environ.get("SSAK_SEARCH_EVAL_CALLS_FILE", "").strip()
    if not path:
        return
    with open(f"{path}.calls", "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"query": query, "at": time.time()}, ensure_ascii=False) + "\n")


def _write_start_marker() -> None:
    path = os.environ.get("SSAK_SEARCH_EVAL_CALLS_FILE", "").strip()
    if not path:
        return
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"pid": os.getpid(), "argv": sys.argv, "started_at": time.time()}, handle)


def _search_payload(raw_query: str) -> dict[str, object]:
    _record_call(raw_query)
    found = _entry_for(raw_query)
    if found is None:  # pragma: no cover — payload 파일이 비어 있으면 로딩에서 죽는다
        return {"query": raw_query, "took_ms": 1, "hits": [], "aborted_backends": [], "signal_confidence": "LOW"}
    key, entry = found
    repeat = _CALL_COUNTS.get(key, 0) > 0
    _CALL_COUNTS[key] = _CALL_COUNTS.get(key, 0) + 1
    hits = _hits(entry)
    if _env_flag("SSAK_SEARCH_EVAL_SHUFFLE") and hits:
        # 호출마다 다른 순서 — 통합 경로가 결정적이지 않다는 사실을 계약이 잡아야 한다(비결정 주입).
        random.Random(hashlib.sha256(f"{key}:{_CALL_COUNTS[key]}".encode()).hexdigest()).shuffle(hits)
    delay_ms = float(os.environ.get("SSAK_SEARCH_EVAL_DELAY_MS", "0") or 0)
    if delay_ms > 0:
        time.sleep(delay_ms / 1000.0)
    took_ms = entry.get("took_ms")
    payload: dict[str, object] = {
        "query": key,
        "took_ms": int(took_ms) if isinstance(took_ms, int) else 120,
        "hits": hits,
        "aborted_backends": [],
        "signal_confidence": "HIGH",
    }
    if repeat:
        payload["cached"] = True
        payload["cache_age_ms"] = 120_000
    return payload


def _result_for(name: str, arguments: dict[str, object]) -> dict[str, object]:
    if name != "ssak_search":
        return {
            "content": [{"type": "text", "text": json.dumps({"error": {"code": "UNKNOWN_TOOL"}})}],
            "isError": True,
        }
    payload = _search_payload(str(arguments.get("query", "")))
    text = json.dumps(payload, ensure_ascii=False)
    return {"content": [{"type": "text", "text": text}], "structuredContent": payload}


def _respond(payload: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _serve() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = message.get("method")
        request_id = message.get("id")

        if method == "initialize":
            params = message.get("params") or {}
            _respond(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": params.get("protocolVersion", "2025-06-18"),
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "ssak-search-eval-fixture", "version": "1.0.0"},
                    },
                }
            )
        elif method == "notifications/initialized":
            continue
        elif method == "ping":
            _respond({"jsonrpc": "2.0", "id": request_id, "result": {}})
        elif method == "tools/list":
            _respond({"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            params = message.get("params") or {}
            name = str(params.get("name"))
            result = _result_for(name, dict(params.get("arguments") or {}))
            _respond({"jsonrpc": "2.0", "id": request_id, "result": result})
        elif request_id is not None:
            _respond(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }
            )


def main() -> None:
    _load_payloads()
    _write_start_marker()
    _serve()


if __name__ == "__main__":
    main()
