"""Cavemem Store module."""

import logging
import os
import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypedDict, final

logger = logging.getLogger(__name__)


@dataclass
class Observation:
    """A single episodic memory observation (caveman-style short-term store)."""

    id: int
    session_id: str
    content: str
    compressed_content: str
    timestamp: str


class ObservationRecord(TypedDict):
    id: int
    session_id: str
    content: str
    compressed_content: str
    timestamp: str


@final
class CavememStore:
    """Persistent memory store utilizing SQLite FTS5 for local-first,.

    cross-agent memory retrieval. Uses basic Caveman compression heuristics.
    """

    db_path: str

    def __init__(self, db_path: str = ".antigravity/cavemem.sqlite3") -> None:
        """Initialize the CavememStore.

        Args:
            db_path (str): str db path.

        """
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            _ = cursor.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS observations_fts USING fts5(

                    session_id,
                    content,
                    compressed_content,
                    timestamp UNINDEXED
                )
            """,
            )
            # Create a regular table to auto-increment IDs and keep original data
            _ = cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS observations (

                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    content TEXT,
                    compressed_content TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """,
            )
            # Trigger to auto-insert into FTS table
            _ = cursor.execute(
                """
                CREATE TRIGGER IF NOT EXISTS obs_ai AFTER INSERT ON observations BEGIN

                    INSERT INTO observations_fts(rowid, session_id, content, compressed_content, timestamp)
                    VALUES (new.id, new.session_id, new.content, new.compressed_content, new.timestamp);
                END;
            """,
            )
            conn.commit()

    def compress_to_caveman(self, text: str) -> str:
        """Compress text by removing filler words, articles, and pleasantries."""
        if not text:
            return ""
        # Remove common filler words (case insensitive)
        fillers = r"\b(the|a|an|is|are|was|were|will|would|could|should|can|please|thank you|hello|hi|here is|i will|let me|we should)\b"  # noqa: E501
        compressed = re.sub(fillers, "", text, flags=re.IGNORECASE)
        # Collapse multiple spaces
        compressed = re.sub(r"\s+", " ", compressed).strip()
        # Basic symbol replacement
        compressed = compressed.replace("because", "b/c").replace("with", "w/")
        return compressed

    def store_observation(self, session_id: str, content: str) -> int:
        """Store Observation.

        Args:
            session_id (str): str session id.
            content (str): str content.

        Returns:
            int: The int result.

        """
        compressed = self.compress_to_caveman(content)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            _ = cursor.execute(
                "INSERT INTO observations (session_id, content, compressed_content) VALUES (?, ?, ?)",
                (session_id, content, compressed),
            )
            obs_id = cursor.lastrowid
            conn.commit()
            return obs_id or 0

    def search_observations(self, query: str, limit: int = 5) -> list[ObservationRecord]:
        """Search for observations.

        Args:
            query (str): str query.
            limit (int): int limit.

        Returns:
            list[ObservationRecord]: Matching observation records.

        """
        # FTS5 match query
        # We need to sanitize the query to avoid FTS syntax errors
        sanitized_query = re.sub(r"[^\w\s]", "", query).strip()
        if not sanitized_query:
            return []

        fts_query = " OR ".join([f"{word}*" for word in sanitized_query.split()])

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                _ = cursor.execute(
                    """
                    SELECT rowid as id, session_id, content, compressed_content, timestamp

                    FROM observations_fts
                    WHERE observations_fts MATCH ?
                    ORDER BY rank LIMIT ?
                    """,
                    (fts_query, limit),
                )
                rows: list[sqlite3.Row] = cursor.fetchall()
                records: list[ObservationRecord] = []
                for row in rows:
                    records.append(
                        {
                            "id": row["id"] if isinstance(row["id"], int) else 0,
                            "session_id": row["session_id"] if isinstance(row["session_id"], str) else "",
                            "content": row["content"] if isinstance(row["content"], str) else "",
                            "compressed_content": row["compressed_content"]
                            if isinstance(row["compressed_content"], str)
                            else "",
                            "timestamp": row["timestamp"] if isinstance(row["timestamp"], str) else "",
                        }
                    )
                return records
        except sqlite3.OperationalError:
            # Fallback if FTS parsing fails
            return []

    # ─── LLM-Driven Memory Extraction (SurfSense 패턴) ────────

    _MEMORY_EXTRACT_PROMPT = """\

You are a memory extraction assistant for an AI coding agent. Analyze the user's \
message and decide if it contains any long-term information worth persisting.

Worth remembering: preferences, project context, tech stack, coding conventions, \
goals, decisions, expertise, architecture choices — durable facts that will matter \
in future sessions.

NOT worth remembering: greetings, one-off questions, session logistics, ephemeral \
requests, follow-up clarifications with no new personal info.

If the message contains memorizable information, output a structured entry like:
- (DATE) [fact|pref|instr] description

[fact] = durable facts, [pref] = preferences, [instr] = standing instructions.

If nothing is worth remembering, output exactly: NO_UPDATE

<current_memory>
{current_memory}
</current_memory>

<user_message>
{user_message}
</user_message>"""

    def extract_memory(
        self,
        user_message: str,
        session_id: str = "auto",
        model_fn: Callable[[str], str] | None = None,
    ) -> str | None:
        """대화 턴에서 장기 기억할 가치가 있는 정보를 자동 추출합니다.

        SurfSense의 memory_extraction.py 패턴을 적용:
        - 경량 LLM 호출로 메시지를 평가
        - 가치 있는 정보는 자동으로 store_observation()에 저장
        - NO_UPDATE 응답 시 아무것도 저장하지 않음

        Args:
            user_message: 사용자 메시지
            session_id: 세션 식별자
            model_fn: LLM 호출 함수 (str -> str). None이면 규칙 기반 폴백.

        Returns:
            저장된 기억 내용 또는 None

        """
        if not user_message or len(user_message.strip()) < 10:
            return None

        # 현재 기억 맥락 조회
        recent = self.search_observations(user_message[:50], limit=3)
        current_memory = "\n".join(obs.get("compressed_content", "") for obs in recent) if recent else "(empty)"

        if model_fn is not None:
            # LLM 기반 추출
            try:
                prompt = self._MEMORY_EXTRACT_PROMPT.format(
                    current_memory=current_memory,
                    user_message=user_message,
                )
                response = model_fn(prompt)
                text = response.strip()

                if text == "NO_UPDATE" or not text:
                    return None

                _ = self.store_observation(session_id, text)
                return text
            except Exception:
                logger.exception("Unhandled exception")
                pass  # LLM 실패 시 규칙 기반 폴백

        # 규칙 기반 폴백: 키워드 패턴으로 기억할 가치 판정
        memory_keywords = [
            "나는",
            "우리는",
            "이 프로젝트",
            "기술 스택",
            "사용해",
            "선호",
            "규칙",
            "컨벤션",
            "아키텍처",
            "항상",
            "Python",
            "FastAPI",
            "React",
            "TypeScript",
            "I use",
            "I prefer",
            "always",
            "convention",
            "stack",
        ]
        if any(kw in user_message for kw in memory_keywords):
            _ = self.store_observation(session_id, user_message)
            return user_message

        return None
