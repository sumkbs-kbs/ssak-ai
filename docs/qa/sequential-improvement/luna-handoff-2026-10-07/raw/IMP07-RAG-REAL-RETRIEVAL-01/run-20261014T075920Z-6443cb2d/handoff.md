# Priority 5 independent QA preparation

Prepared, not executed: 30 original synthetic A documents, 20 queries, fixed source oracles, two conflicting B documents with reused filenames, one outside-root sentinel, a predetermined replacement document and `acceptance-plan.md`.

`corpus-a/` is exactly 20 targets plus 10 related distractors, 15 English and 15 Korean. Queries are ten controlled and ten exploratory, each five English/five Korean. Oracles are separate evaluation data and must never become retrieval input. All operational facts are invented for this fixture; none asserts Ssak-Ai behavior.

The plan preserves original IMP-07 gates: controlled top-5 **10/10**, namespace leak/purge residual/peer harm **0**, and **8** concurrent same-path clients. Exploratory Recall@5/MRR@5/nDCG@5 have no invented pass threshold. The frozen API is production `RAGIndexer.search(query, n_results=5, mode='semantic')`, one actual query embedding per input; no default-hybrid quality claim is made. Real semantic execution waits for frozen, reviewed identity code; precomputed peer-contract vectors are explicitly separate from semantic quality.

Declared model is local `nomic-embed-text:latest`, repository `nomic-ai/nomic-embed-text-v1.5`, configured dimension **0/UNKNOWN**, prefixes `search_document: ` and `search_query: `. The supplied official-card reference is documented without a new web fetch. Future metadata evidence belongs under `metadata-preflight/`; it may resolve an installed tag digest but cannot verify configured feature revision or successful embedding.

Semantic proposal: at most 28 inference requests, hard cap 30, overall 180 seconds and each request at most 55 seconds; no retries, redirects, fallback embeddings, downloads or LLM chat. The separately authorized preparation preflight permits only four local metadata requests, each at most 10 seconds within 45 seconds overall. No quality/model inference or lifecycle tests have been run during preparation.

`fixture-manifest.sha256` freezes all corpus/query/oracle/spec files before metadata calls. Future runners must verify it, copy corpus bytes into new owned runtime project roots, and preserve the frozen originals. `acceptance-plan.md` defines mutation, delete/reindex/reopen, B/sentinel isolation, purge, peer concurrency, call accounting and coverage limitations. This fixture cannot support general quality improvement or GA claims without additional evidence and a paired baseline.
