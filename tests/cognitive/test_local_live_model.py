"""The live provider is pinned and records actual wire responses."""

from pathlib import Path

import httpx
import pytest

from antigravity_k.engine.cognitive.growth import ArmRole
from antigravity_k.engine.cognitive.live_pilot import LiveTrialRequest, TrialOrder
from antigravity_k.engine.cognitive.live_trial_types import ModelTask
from antigravity_k.engine.local_live_model import LocalOllamaModelPort


def test_live_response_and_token_counts_come_from_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given an HTTP boundary serving an installed model and deliberately wrong bytes.
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "test", "digest": "pinned"}]})
        if request.url.path == "/api/ps":
            return httpx.Response(200, json={"models": [{"name": "test", "digest": "pinned", "context_length": 40960}]})
        return httpx.Response(
            200,
            json={
                "response": '{"append_content":"WRONG","expand_missing":false}',
                "prompt_eval_count": 17,
                "eval_count": 5,
            },
        )

    monkeypatch.setattr(
        LocalOllamaModelPort,
        "_client",
        lambda self: httpx.Client(base_url="http://127.0.0.1:11434", transport=httpx.MockTransport(respond)),
    )
    model = LocalOllamaModelPort("test", tmp_path / "trace.jsonl")
    request = LiveTrialRequest("PT-01", "FINAL", ArmRole.FRESH, 0, TrialOrder.FRESH_FIRST, None, ())
    # When the model is called.
    choice = model.choose(request, ModelTask("PT-01", (), None), missing_refs=(), workspace=tmp_path)
    # Then the adapter preserves the actual incorrect result and measured token count.
    assert choice.append_content == "WRONG"
    assert choice.tokens == 22
    assert model.attestation.model_snapshot == "pinned"
    assert (tmp_path / "trace.jsonl").is_file()
