# Local metadata preflight — prepared, no inference

Exactly four authorized requests completed once: GET `/api/version`, GET `/api/tags`, POST `/api/show` for `nomic-embed-text:latest`, GET `/api/ps`, all HTTP 200 at `http://127.0.0.1:11434`. No retry, redirect, proxy, embedding/chat inference, pull or unload call. The subprocess exited 0 within the 45-second guard; no owned process remained. Raw response bytes, request receipts and timestamps are retained. Existing installed httpx 0.28.1 was used because httpx2 is absent; no package installation occurred.

Observed installed metadata:

- Ollama version: `0.40.3`.
- Model: `nomic-embed-text:latest`.
- Digest: `0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f`.
- Size: `274302450` bytes; GGUF, nomic-bert, 137M, F16.
- Capability: `embedding`.
- Advertised embedding length: `768`; advertised context length: `2048`.
- `/api/ps` returned no running models; no model was loaded or unloaded by these calls.

These are metadata observations, not inference results. The declared `nomic-ai/nomic-embed-text-v1.5` repository mapping is not proven by the tag alone. The feature's configured revision remains UNVERIFIED and configured dimension remains 0/UNKNOWN. Future reviewed quality execution must bind its actual tag/digest and observe the real response dimensions without changing defaults.

`invocation.json` records executable/argv/cwd, HTTP limits and before/after hashes for the helper and default config inputs. `requests.jsonl` contains the four exact safe requests and response statuses. `*.response.bin` are their original bodies. `summary.json` records metadata and explicit zero inference/mutation counts. `fixture-hash-check.log` verifies all 38 previously frozen fixture/spec files; the fixture manifest SHA remains `8a92bd375a38036107165f61f3d44677d4987b45eca87300e36aa2d1e40fd499`.

Stop state: PREPARED_METADATA_AVAILABLE_NOT_INFERRED. No retrieval-quality runner has been implemented or executed. Wait for identity review, any keyword-path correction, and the published candidate source freeze before quality calls.
