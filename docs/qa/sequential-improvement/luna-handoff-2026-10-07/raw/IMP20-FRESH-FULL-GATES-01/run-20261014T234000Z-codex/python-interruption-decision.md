# Superseded Python candidate

The source-bound owned-copy reproduction of `tests/test_api_server.py::test_embeddings_endpoint_uses_local_fallback` confirms HTTP503 versus legacy expected200 at the same API/test preimage as candidate30233787. The public API already requires `allow_fallback=False`; restoring silent hash fallback would violate the approved strict embedding contract.

The primary agent intentionally interrupts this candidate's still-running Python suite after the defect is confirmed, rather than waiting for an already-known unacceptable candidate. This gate is NOT_PASSED and its partial output is retained. The other unchanged gates may continue diagnostically. No partial result is promoted to a full-suite or full23 PASS. After the test contract repair is reviewed and committed, a fresh all23 run is required with no merge from this candidate.
