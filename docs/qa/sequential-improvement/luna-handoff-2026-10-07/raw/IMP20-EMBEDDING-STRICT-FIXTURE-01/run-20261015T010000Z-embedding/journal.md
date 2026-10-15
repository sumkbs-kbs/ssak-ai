# Embedding strict fixture repair

Scope: owned copies of candidate 302337877766a540a21dd42c61605dc590e4026b tests/test_api_server.py only. No candidate or ROOT source/test modification. No commit.

Hypothesis: the legacy API test expects successful hash fallback, whereas the real route intentionally passes allow_fallback=False and maps model unavailability to typed 503. Competing explanations: early authentication denial; real provider failure. Capture response and isolated boundary counts to distinguish them.

Artifacts: preimage/postimage test copies, candidate conftest and adjacent contract copies, guarded pytest launcher, per-attempt logs/JUnit/receipts, source binding, task patch, replay and final manifest. All remain here as requested evidence. Private test runtime is excluded from public manifest.

Validation scope: in-process TestClient route, disabled application lifespan, fake model factory, no sockets/listener/provider inference. Existing normal encoder contract is run alongside negative cases. Product lifespan and live embeddings are not evaluated.

Graph lookup returned project unindexed; parent already attempted indexing for 300 seconds without success. Known exact source paths were read directly.
