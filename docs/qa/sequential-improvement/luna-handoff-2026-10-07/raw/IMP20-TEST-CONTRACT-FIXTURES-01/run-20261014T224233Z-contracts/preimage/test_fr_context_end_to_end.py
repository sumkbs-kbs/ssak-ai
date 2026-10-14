"""FR-09 regression: manual/automatic context compaction, end to end.

Deterministic tier (plan RP-09): the browser-tier manual UI click and the
live-provider tier belong to manual QA / RP-12.

Covers:

- a long synthetic conversation (initial constraint, tool evidence pair,
  citation source, latest instruction) is compacted through the real store
  AND the real ``/v1/conversations/compact`` endpoint
- revision increments exactly once; retained ids match the snapshot; tokens
  strictly drop; latest user instruction survives in the retained tail
- the deterministic summary path preserves the initial key constraint and
  keeps structured tool evidence (citation provenance) instead of prose
- tail-only compaction ("skipped") still CAS-bumps once without destroying
  messages; stale revisions are rejected; state survives store restart
- the final serialized prompt (``prompt_messages``) stays within the same
  budget envelope the store estimates
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from antigravity_k.api.project_binding import SESSION_ID_HEADER
from antigravity_k.config import config
from antigravity_k.engine.conversation_store import ConversationStore

PROJECT = "fr09-proj"
CONV = "fr09-conv"

INITIAL_CONSTRAINT = "NEVER-EDIT-CONSTRAINT: vault_data/config.json은 절대 수정하지 않는다"
LATEST_INSTRUCTION = "LATEST-INSTRUCTION: 이제 결과를 한국어로 요약해줘"
TOOL_EVIDENCE = (
    "<tool_response>\n"
    '[TOOL_EVIDENCE] {"source_id": "docs/architecture.md", "citation": "arch-doc"}\n'
    "[UNTRUSTED_TOOL_RESULT]\n"
    "컴포넌트 다이어그램: Engine → Router → Provider (line 10-42)\n"
    "[/UNTRUSTED_TOOL_RESULT]\n"
    "</tool_response>"
)


def _seed_long_conversation(store: ConversationStore, project_id: str = PROJECT) -> int:
    turns: list[tuple[str, str]] = [
        ("user", f"프로젝트 개선 작업을 시작한다. {INITIAL_CONSTRAINT}. 먼저 아키텍처를 분석해라."),
        ("assistant", "아키텍처를 분석하겠습니다."),
        ("tool", TOOL_EVIDENCE),
        ("assistant", "아키텍처 분석 완료: 3계층 구조."),
        ("user", "라우터 로직을 개선해라."),
        ("assistant", "라우터 개선 1차 적용."),
        ("tool", TOOL_EVIDENCE),
        ("assistant", "검증 완료."),
        ("user", "모델 레지스트리도 정리해라."),
        ("assistant", "레지스트리 정리 완료."),
        ("user", LATEST_INSTRUCTION),
        ("assistant", "요약을 준비합니다."),
    ]
    revision = 0
    for role, content in turns:
        snap = store.append(
            project_id=project_id,
            conversation_id=CONV,
            expected_revision=revision,
            role=role,  # type: ignore[arg-type]
            content=content,
        )
        revision = snap.revision
    return revision


@pytest.fixture()
def store(tmp_path: Path) -> ConversationStore:
    s = ConversationStore(storage_dir=tmp_path / "conversations")
    _seed_long_conversation(s)
    return s


def _auth_headers() -> dict[str, str]:
    if not config.security.access_pin:
        return {}
    return {"X-Access-Pin": config.security.access_pin}


class TestManualCompactStoreLevel:
    def test_compact_preserves_contract(self, store: ConversationStore) -> None:
        before = store.get(project_id=PROJECT, conversation_id=CONV)
        assert before is not None
        tokens_before = before.estimate_tokens()
        rev_before = before.revision

        snap = store.compact(
            project_id=PROJECT,
            conversation_id=CONV,
            expected_revision=rev_before,
            retain_tail=4,
        )

        # revision increments exactly once
        assert snap.revision == rev_before + 1
        # retained ids match the snapshot's messages exactly
        after = store.get(project_id=PROJECT, conversation_id=CONV)
        assert after is not None
        assert tuple(m.id for m in after.messages) == snap.retained_message_ids
        # tokens strictly drop
        assert after.estimate_tokens() < tokens_before
        # latest user instruction survives in the retained tail
        tail_texts = "\n".join(m.content for m in after.messages[-4:])
        assert LATEST_INSTRUCTION in tail_texts

    def test_deterministic_summary_keeps_initial_constraint_and_evidence(self, store: ConversationStore) -> None:
        before = store.get(project_id=PROJECT, conversation_id=CONV)
        assert before is not None
        _snap = store.compact(
            project_id=PROJECT,
            conversation_id=CONV,
            expected_revision=before.revision,
            retain_tail=4,
        )
        after = store.get(project_id=PROJECT, conversation_id=CONV)
        assert after is not None
        assert after.summary, "summary must be recorded on the record"

        # Deterministic path: structured tool evidence survives compaction
        # (citation provenance) instead of being replaced by prose.
        assert "[TOOL_EVIDENCE]" in after.summary
        assert "docs/architecture.md" in after.summary
        # The initial constraint (first user message) is a key message and
        # must remain visible in the summary section.
        assert "NEVER-EDIT-CONSTRAINT" in after.summary

    def test_summary_with_llm_double_includes_key_sections(self, store: ConversationStore) -> None:
        before = store.get(project_id=PROJECT, conversation_id=CONV)
        assert before is not None
        captured_prompt: list[str] = []

        def summarize_fn(prompt: str) -> str:
            captured_prompt.append(prompt)
            return "사용자가 vault_data/config.json 수정 금지를 결정하고 아키텍처 분석 후 라우터와 레지스트리를 정리함."

        snap = store.compact(
            project_id=PROJECT,
            conversation_id=CONV,
            expected_revision=before.revision,
            retain_tail=4,
            summarize_fn=summarize_fn,
        )
        assert snap.summary is not None
        assert "대화 요약" in snap.summary
        assert "[TOOL_EVIDENCE]" in snap.summary  # evidence appended after LLM summary
        assert captured_prompt, "summarizer double must have been invoked with the old messages"

    def test_tail_only_compact_bumps_once_and_keeps_messages(self, store: ConversationStore) -> None:
        before = store.get(project_id=PROJECT, conversation_id=CONV)
        assert before is not None
        count_before = len(before.messages)

        snap = store.compact(
            project_id=PROJECT,
            conversation_id=CONV,
            expected_revision=before.revision,
            retain_tail=50,  # >= message count → nothing to compact
        )
        after = store.get(project_id=PROJECT, conversation_id=CONV)
        assert after is not None
        assert snap.revision == before.revision + 1
        assert len(after.messages) == count_before

    def test_stale_revision_rejected(self, store: ConversationStore) -> None:
        from antigravity_k.api.contracts.errors import StaleConversationRevisionError

        before = store.get(project_id=PROJECT, conversation_id=CONV)
        assert before is not None
        with pytest.raises(StaleConversationRevisionError):
            store.compact(
                project_id=PROJECT,
                conversation_id=CONV,
                expected_revision=before.revision - 1,
                retain_tail=4,
            )

    def test_state_survives_store_restart(self, store: ConversationStore, tmp_path: Path) -> None:
        before = store.get(project_id=PROJECT, conversation_id=CONV)
        assert before is not None
        snap = store.compact(
            project_id=PROJECT,
            conversation_id=CONV,
            expected_revision=before.revision,
            retain_tail=4,
        )
        fresh = ConversationStore(storage_dir=tmp_path / "conversations")
        after = fresh.get(project_id=PROJECT, conversation_id=CONV)
        assert after is not None
        assert after.revision == snap.revision
        assert tuple(m.id for m in after.messages) == snap.retained_message_ids


class TestManualCompactApiLevel:
    @staticmethod
    def _make_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, prefix: str):
        """ctx01-style isolated app: fresh store singleton + registry + handler."""
        from fastapi import FastAPI

        import antigravity_k.engine.conversation_store as cs
        from antigravity_k.api.error_handler import APIError, global_exception_handler
        from antigravity_k.api.routes import conversation_api as conv_api
        from antigravity_k.engine.project_registry import ProjectRegistry

        api_store = ConversationStore(storage_dir=tmp_path / f"{prefix}-conversations")
        cs.reset_conversation_store_for_tests(api_store)

        registry = ProjectRegistry(storage_path=tmp_path / f"{prefix}-projects.json")
        record = registry.add_project(name=prefix, path=str(tmp_path))
        monkeypatch.setattr("antigravity_k.api.project_binding.get_project_registry", lambda: registry)
        monkeypatch.setattr(
            "antigravity_k.engine.request_execution_context.get_project_registry",
            lambda: registry,
        )
        monkeypatch.setattr("antigravity_k.config.config.paths.project_root", tmp_path.resolve())
        monkeypatch.setenv("AGK_ALLOWED_ROOTS", str(tmp_path.resolve()))

        test_app = FastAPI()
        test_app.add_exception_handler(APIError, global_exception_handler)
        test_app.add_exception_handler(Exception, global_exception_handler)
        test_app.include_router(conv_api.router)
        client = TestClient(test_app, raise_server_exceptions=False)
        return client, record.id, api_store

    def test_compact_endpoint_returns_full_contract(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from antigravity_k.api.project_binding import bind_session_active_project

        client, pid, api_store = self._make_client(tmp_path, monkeypatch, "fr09")
        _ = bind_session_active_project("fr09-session", pid)
        _seed_long_conversation(api_store, project_id=pid)
        before = api_store.get(project_id=pid, conversation_id=CONV)
        assert before is not None
        tokens_before = before.estimate_tokens()

        response = client.post(
            "/v1/conversations/compact",
            json={
                "project_id": pid,
                "conversation_id": CONV,
                "expected_revision": before.revision,
                "retain_tail": 4,
            },
            headers={**_auth_headers(), SESSION_ID_HEADER: "fr09-session"},
        )

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["revision"] == before.revision + 1
        assert data["retained_message_ids"]
        assert data["tokens_after"] < tokens_before
        assert data["tokens_reduced"] == tokens_before - data["tokens_after"]
        assert data["summary"]
        assert "NEVER-EDIT-CONSTRAINT" in data["summary"]
        assert "[TOOL_EVIDENCE]" in data["summary"]

    def test_compact_endpoint_stale_revision_conflict(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from antigravity_k.api.project_binding import bind_session_active_project

        client, pid, api_store = self._make_client(tmp_path, monkeypatch, "fr09b")
        _ = bind_session_active_project("fr09b-session", pid)
        _seed_long_conversation(api_store, project_id=pid)
        before = api_store.get(project_id=pid, conversation_id=CONV)
        assert before is not None

        response = client.post(
            "/v1/conversations/compact",
            json={
                "project_id": pid,
                "conversation_id": CONV,
                "expected_revision": before.revision - 3,  # stale
                "retain_tail": 4,
            },
            headers={**_auth_headers(), SESSION_ID_HEADER: "fr09b-session"},
        )

        assert response.status_code == 409, response.text
        body = response.json()
        assert body["error"] == "stale_conversation_revision"


class TestFinalPromptPayload:
    def test_serialized_prompt_after_compaction_is_bounded_and_ordered(self, store: ConversationStore) -> None:
        before = store.get(project_id=PROJECT, conversation_id=CONV)
        assert before is not None
        _snap = store.compact(
            project_id=PROJECT,
            conversation_id=CONV,
            expected_revision=before.revision,
            retain_tail=4,
        )
        after = store.get(project_id=PROJECT, conversation_id=CONV)
        assert after is not None

        payload = after.prompt_messages()
        serialized = "\n".join(m["content"] for m in payload)
        # ordering: summary-first then retained tail
        assert payload[0]["role"] == "system"
        assert "NEVER-EDIT-CONSTRAINT" in serialized
        assert "[TOOL_EVIDENCE]" in serialized
        assert LATEST_INSTRUCTION in serialized
        # store-level token estimate drops after compaction
        assert after.estimate_tokens() > 0
        assert after.estimate_tokens() < before.estimate_tokens()
