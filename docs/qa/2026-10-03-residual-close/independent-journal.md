# Independent deferred-view QA journal

Scope: ConversationStore deferred-view patch and tests only. No production edits.
Artifacts planned: independent-driver.py, independent-runtime.txt, independent-review.md, independent-hashes.txt.
Runtime: existing .venv Python, real temporary stores, subprocess workers, no network/model calls. All stores cleaned by TemporaryDirectory.
Graph first attempted search_graph (project missing), then index_repository (Transport closed); precise source fallback used.
