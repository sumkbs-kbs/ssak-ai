# Frozen acceptance proposal — NOT RUN

Authority: `docs/ssak-ai-core/SEQUENTIAL_AUDIT_IMPROVEMENT_PLAN_2026-10-04.md`, IMP-07, lines 356–373. This plan and the corpus/query/oracle bytes are fixed before retrieval. Current preparation does not authorize execution of quality calls: wait for the reviewed, published strict identity candidate to be frozen and bound by source SHA. No quality runner has been implemented or run.

## Fixture and input boundaries

Every fact here is original invented fixture data about Alder Community Hub/느티 허브 and Birch Annex/자작 별관. These documents are not descriptions of Ssak-Ai behavior or real operational advice. Project A is exactly the 30 Markdown files in `corpus-a/`: files 01–20 are answer-bearing targets, 21–30 are plausible related distractors. There are 15 English and 15 Korean documents. `queries.json` contains 20 inputs: controlled Q01–Q10 and exploratory Q11–Q20, each group with five English and five Korean queries. No input query contains its expected answer or an artificial unique matching token. `oracles.json` is evaluation authority, never indexed, embedded, or passed to retrieval.

Project B is the two files in `corpus-b/`, with the same basenames as A sources 01 and 06 but conflicting invented facts. `outside-projects/key-register.md` is outside both project roots. It must never be indexed, returned, or removed by either project's purge. `mutation/` is also outside the initial project roots and must not be indexed initially. The future runner copies only each corpus directory's contents into a fresh owned project; it must not index this run's parent directory, plans, query files, or oracle files. Frozen corpus bytes remain unchanged throughout; only owned runtime copies may be mutated.

Source identity is the pair `(project_id, canonical root-relative source path)` resolved against the declared project's canonical root. A basename alone cannot distinguish A from B. Record actual returned metadata, resolve its path without basename-only remapping, and reject an out-of-root source. The original source document determines relevance; neither a generated answer nor an embedding score can rewrite the oracle.

## Model profile and future metadata gate

Declared profile: registered local Ollama `nomic-embed-text:latest`; declared model repository `nomic-ai/nomic-embed-text-v1.5`. Configured dimension is **0 / UNKNOWN**, not a claim about the real output dimension. The tag's installed digest, capabilities, size and any advertised embedding dimension remain pending until metadata is captured. The moving `:latest` tag must be bound to that observed installed digest for the future run; a declared repository name is not proof that the tag contains those exact bytes. Feature/configured revision identity remains UNVERIFIED until the reviewed candidate supplies and records it.

The caller supplied the verified official model card reference: <https://huggingface.co/nomic-ai/nomic-embed-text-v1.5>. Required protocol fields are document prefix `search_document: ` and query prefix `search_query: `. Apply each exactly once to provider input at the embedding boundary. Preserve stored canonical source/chunk/query text without the prefixes. Capture canonical input hash, actual wire input hash, prefix field, model tag/digest, output dimension and candidate identity for each batch. Do not silently normalize text, change dimensions, use fallback embeddings, generate fake semantic vectors, or accept a missing identity field.

A separately authorized preparation preflight may make exactly four metadata requests to `http://127.0.0.1:11434`: GET `/api/version`, GET `/api/tags`, POST `/api/show` with `{"model":"nomic-embed-text:latest"}`, and GET `/api/ps`. Record request bodies, raw responses, durations and status independently of inference counts. Proxies disabled (`trust_env=false`), redirects disabled, retries zero, request timeout 10 seconds, overall deadline 45 seconds. No embed/chat/pull/unload or other requests. An absent model or unavailable metadata yields UNAVAILABLE without retry or pull. Do not unload other users' models. Metadata alone never proves successful embedding or retrieval.

## Semantic retrieval scenario and call budget — future only

Use the real registered Ollama embedding endpoint and the frozen candidate's strict bound VectorStore plus RAGIndexer. The frozen retrieval mode is **semantic**, invoked through production `RAGIndexer.search(query, n_results=5, mode='semantic')`, with one actual query embedding call per query. The current default hybrid path can repeat vector inference through its keyword fallback; this diagnostic neither executes that path nor claims default-hybrid quality. Capture candidate SHA/file hashes and actual imported module paths before/after. Verify no source drift. Index exactly 30 A documents and two B documents in distinct namespaces, without an implicit default embedding callback. Chunking must be the candidate's real behavior; record its chunk/source mapping and counts. No fixture-specific retrieval bypass or oracle-aware ranking is permitted.

| Operation | Maximum provider inference requests | Semantic inputs |
| --- | ---: | --- |
| A indexing | 2 | All actual chunks from the 30 A documents, in one or two bounded batches |
| B indexing | 1 | Actual chunks from the two B documents |
| Initial A retrieval | 20 | Q01–Q20, one query inference each, once only |
| B isolation retrieval | 2 | Q01 and Q06 against B, one query inference each |
| Edited A source reindex | 1 | Actual chunks of the predetermined source replacement |
| A post-mutation/reopen checks | 2 | Q01 and Q06, once each after edit/delete/reindex/reopen |
| **Planned maximum** | **28** | No automatic retries or hidden re-embedding |

Metadata requests are four separate non-inference calls, not part of the 28 count. Reopen/purge/peer checks must not trigger provider inference. Overall semantic deadline is 180 seconds; each request is bounded by `min(55 seconds, remaining overall budget)`. Connection retries and redirects are zero. Hard inference ceiling is 30; the two remaining slots are not permission for tuning, replay, or retries. If the candidate cannot batch within this budget, stop before execution with INTERFACE_NOT_READY and resolve the plan explicitly; do not silently call once per chunk or expand the budget. Track attempted/completed/failed provider requests and document/query input counts separately. A failure, timeout, missing model, rejected identity, or budget exhaustion is not a pass. Preserve evidence and do not automatically repeat.

Allow network only to the explicit loopback Ollama endpoint. No chat, vision, external provider, model download, pull, force unload, or cache/config default changes. Owned runtime state, databases, model/cache directories and temporary files stay under a unique future attempt directory within this QA run. HOME and CODEX_HOME remain unchanged.

## Frozen scoring

Request the real top-5 result surface. Use the first occurrence of the oracle's project/source in those five returned results; a repeated chunk does not count as another relevant source. Do not fetch a larger candidate pool solely to improve this measurement or change ranks through post hoc deduplication. If the public API inherently returns document-deduplicated results, record that behavior and its input/output mapping before scoring. Preserve raw order, scores and metadata.

For oracle rank `r` in 1–5: Recall@5=1, reciprocal rank=1/r, and nDCG@5=1/log2(r+1), with a single relevant source and ideal DCG=1. If absent, all three values are 0. Report per-query values, exact group sums/denominators, language splits, latency and RSS with their measurement boundaries. Source attribution failures and namespace leaks are reported separately from relevance scores.

**Original required quality gate: controlled Q01–Q10 must all contain the correct source in top-5, 10/10.** Exploratory Q11–Q20 have no invented acceptance percentage: report Recall@5, MRR@5 and nDCG@5 separately as observations. Do not replace the original gate with an aggregate over all 20, an arbitrary 80% threshold, or an average that hides a controlled failure. Empty, failed or unobserved calls remain failed/inconclusive inputs; never drop them from the denominator.

## Predetermined mutation, namespace and purge checks

After the initial 20-query results are sealed, replace the working A `01-room-cancellations.md` with the exact `mutation/01-room-cancellations.md` bytes and remove working A `06-lost-keys.md`. Reindex through the real candidate API and reopen. Re-run Q01: correct A source must remain in top-5 with the new source/content hash and the 24-hour fact; no stale 48-hour chunk from the replaced file may remain in store rows. Re-run Q06: the removed A source must be absent from all current rows and top-5 results, so it cannot serve as new answer evidence. This checks retrieval evidence, not LLM answer generation. Never mutate B or the immutable original corpus/oracles.

Seal B's logical vector IDs, canonical document/metadata hashes, graph snapshot if present, and file SHA manifest after a clean close. Record the out-of-root sentinel hash. Purge A through the candidate's own namespace-scoped operation, close and reopen A, then require A vector residual=0. Compare B's pre/post purge hashes before reopening B so its own reopen cannot confound the no-write comparison; then reopen B and verify its two sources and original facts remain. The sentinel must be byte-identical and absent from A/B results and indexed source inventories. Namespace leaks, purge residuals and peer damage must each be **0**.

If the selected API cannot exercise the original B graph-preservation requirement, record that coverage gap explicitly; vector-only success cannot close the complete original IMP-07 lifecycle criterion. Do not fabricate an empty graph fixture as proof. Model/dimension incompatibility must fail before modifying an existing store, preserving its preflight bytes; use the candidate's existing contract checks rather than changing defaults.

## Eight-client contract scenario — distinct from semantic quality

Use a separate owned peer-store path shared by eight real clients, one frozen precomputed-vector identity, and one collection. No Ollama calls or semantic-quality scores belong to this scenario. Supply deterministic 3D vectors directly for eight stable IDs, one per client; never label them model embeddings. Two barrier-coordinated cycles cover concurrent initialize → eight writes → eight reads/counts → peer close → remaining-peer reads → all close → concurrent reopen. On the second cycle upsert the same IDs to check duplicate prevention. Count must be eight for every live peer after all writes, including after one sibling closes. All eight client constructions/reopens must finish; errors, closed-peer damage and registry/cache damage must be zero. Record exact client identities, root/collection/identity bindings, close order, results and OS cleanup. Bound this separate local-only scenario to 30 seconds; no retries or deliberate count on a closed client.

Planned fixed vectors for IDs peer-1 through peer-8: `[1,0,0]`, `[0,1,0]`, `[0,0,1]`, `[1,1,0]`, `[1,0,1]`, `[0,1,1]`, `[1,1,1]`, `[-1,1,0]`. A precomputed fixture identity must not impersonate the real Nomic profile or overwrite a model-bound store.

## Methodology limits and release boundary

This is a small authored bilingual fixture, with related decoys and ten intentionally clear cases. The single-source relevance model does not measure every partially useful source. English/Korean coverage is balanced by case count, not by broad linguistic representativeness. No cross-language query/document transfer is assumed by these mostly same-language cases. Preparation is NOT_RUN for model inference, retrieval, mutations, purge and peer execution. A future pass establishes only this frozen fixture and candidate. Normal retrieval quality, general improvement and GA readiness require separate evidence; any improvement claim needs a paired baseline using the same corpus, queries and budget. There is no baseline or improvement claim here.
