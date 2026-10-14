"""Transactional reward accounting and read-only validation for the wiki graph."""

from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Literal, TypeAlias, TypedDict

REWARD_DECAY = 0.95
REWARD_CAP = 10.0
GraphRewardEvent: TypeAlias = (
    tuple[Literal["node"], int] | tuple[Literal["link"], tuple[int, int]] | tuple[Literal["decay"], None]
)


class KGValidationResult(TypedDict):
    OK: bool
    errors: tuple[str, ...]
    integrity_check: str
    foreign_key_violations: int
    entry_count: int
    link_count: int
    reward_tick: int


def advance_reward_ticks(connection: sqlite3.Connection, events: Iterable[GraphRewardEvent]) -> None:
    """Apply ordered graph reward ticks with one bulk decay pass.

    Each event decays all existing KG scores by 0.95, then optionally rewards
    one node or directed edge, capped at 10. The caller includes this operation
    in the same transaction as the corresponding graph mutation.
    """
    normalized_events = tuple(events)
    if not normalized_events:
        return
    if not connection.in_transaction:
        _ = connection.execute("BEGIN")

    node_positions: dict[int, list[int]] = defaultdict(list)
    link_positions: dict[tuple[int, int], list[int]] = defaultdict(list)
    for index, event in enumerate(normalized_events):
        if event[0] == "node":
            node_positions[event[1]].append(index)
        elif event[0] == "link":
            link_positions[event[1]].append(index)

    total_ticks = len(normalized_events)
    decay_factor = REWARD_DECAY**total_ticks
    old_node_scores: dict[int, float] = {}
    node_ids = tuple(sorted(node_positions))
    for offset in range(0, len(node_ids), 400):
        node_chunk = node_ids[offset : offset + 400]
        rows = connection.execute(
            "SELECT entry_id, score FROM wiki_node_rewards WHERE entry_id IN (SELECT value FROM json_each(?))",
            (json.dumps(node_chunk),),
        ).fetchall()
        old_node_scores.update({int(row[0]): float(row[1]) for row in rows})

    old_link_scores: dict[tuple[int, int], float] = {}
    link_pairs = tuple(sorted(link_positions))
    for offset in range(0, len(link_pairs), 300):
        link_chunk = link_pairs[offset : offset + 300]
        rows = connection.execute(
            "SELECT from_id, to_id, score FROM wiki_link_rewards WHERE (from_id, to_id) IN"
            " (SELECT json_extract(value, '$[0]'), json_extract(value, '$[1]') FROM json_each(?))",
            (json.dumps(link_chunk),),
        ).fetchall()
        old_link_scores.update({(int(row[0]), int(row[1])): float(row[2]) for row in rows})

    for clear_query, decay_query, prune_query in (
        (
            "DELETE FROM wiki_node_rewards",
            "UPDATE wiki_node_rewards SET score = score * ?",
            "DELETE FROM wiki_node_rewards WHERE score <= 0",
        ),
        (
            "DELETE FROM wiki_link_rewards",
            "UPDATE wiki_link_rewards SET score = score * ?",
            "DELETE FROM wiki_link_rewards WHERE score <= 0",
        ),
    ):
        if decay_factor == 0:
            _ = connection.execute(clear_query)
        else:
            _ = connection.execute(decay_query, (decay_factor,))
            _ = connection.execute(prune_query)

    for node_id in node_ids:
        score = _reward_score_after_events(old_node_scores.get(node_id, 0.0), node_positions[node_id], total_ticks)
        if score > 0:
            _ = connection.execute(
                """INSERT INTO wiki_node_rewards (entry_id, score) VALUES (?, ?)
                   ON CONFLICT(entry_id) DO UPDATE SET score = excluded.score""",
                (node_id, score),
            )
    for link_pair in link_pairs:
        score = _reward_score_after_events(old_link_scores.get(link_pair, 0.0), link_positions[link_pair], total_ticks)
        if score > 0:
            _ = connection.execute(
                """INSERT INTO wiki_link_rewards (from_id, to_id, score) VALUES (?, ?, ?)
                   ON CONFLICT(from_id, to_id) DO UPDATE SET score = excluded.score""",
                (link_pair[0], link_pair[1], score),
            )

    cursor = connection.execute("UPDATE wiki_graph_state SET tick = tick + ? WHERE id = 1", (total_ticks,))
    if cursor.rowcount != 1:
        raise RuntimeError("Wiki graph state row is missing")


def _reward_score_after_events(score: float, positions: Sequence[int], tick_count: int) -> float:
    last_tick = 0
    for event_index in positions:
        score *= REWARD_DECAY ** (event_index + 1 - last_tick)
        score = min(REWARD_CAP, score + 1.0)
        last_tick = event_index + 1
    return score * REWARD_DECAY ** (tick_count - last_tick)


def advance_reward_tick(
    connection: sqlite3.Connection,
    *,
    node_id: int | None = None,
    link_pair: tuple[int, int] | None = None,
) -> None:
    """Apply one decay tick and optionally reward one node or directed pair."""
    if node_id is not None and link_pair is not None:
        raise ValueError("A wiki graph tick can reward only one pair")
    if node_id is not None:
        event: GraphRewardEvent = ("node", node_id)
    elif link_pair is not None:
        event = ("link", link_pair)
    else:
        event = ("decay", None)
    advance_reward_ticks(connection, (event,))


def graph_deletion_events(
    connection: sqlite3.Connection,
    entry_ids: tuple[int, ...],
) -> tuple[GraphRewardEvent, ...]:
    """Build one decay event per distinct incident edge and deleted node."""
    unique_ids = tuple(sorted(set(entry_ids)))
    if not unique_ids:
        return ()

    incident_pairs: set[tuple[int, int]] = set()
    for offset in range(0, len(unique_ids), 400):
        chunk = unique_ids[offset : offset + 400]
        parameters = (json.dumps(chunk), json.dumps(chunk))
        rows = connection.execute(
            "SELECT from_id, to_id FROM wiki_links WHERE from_id IN (SELECT value FROM json_each(?)) "
            "OR to_id IN (SELECT value FROM json_each(?)) ORDER BY from_id, to_id",
            parameters,
        ).fetchall()
        incident_pairs.update((int(row[0]), int(row[1])) for row in rows)

    events: list[GraphRewardEvent] = [("decay", None) for _pair in sorted(incident_pairs)]
    events.extend(("decay", None) for _entry_id in unique_ids)
    return tuple(events)


def prepare_graph_deletion(connection: sqlite3.Connection, entry_ids: tuple[int, ...]) -> None:
    """Apply reward-decay events before the caller deletes graph endpoints."""
    advance_reward_ticks(connection, graph_deletion_events(connection, entry_ids))


def delete_graph_rows(connection: sqlite3.Connection, entry_ids: tuple[int, ...]) -> None:
    """Explicitly remove incident graph rows even when legacy FK enforcement is off."""
    unique_ids = tuple(sorted(set(entry_ids)))
    chunks = tuple(unique_ids[offset : offset + 400] for offset in range(0, len(unique_ids), 400))
    for chunk in chunks:
        parameters = (json.dumps(chunk),)
        _ = connection.execute(
            "DELETE FROM wiki_link_rewards WHERE from_id IN (SELECT value FROM json_each(?))",
            parameters,
        )
        _ = connection.execute(
            "DELETE FROM wiki_links WHERE from_id IN (SELECT value FROM json_each(?))",
            parameters,
        )
    for chunk in chunks:
        parameters = (json.dumps(chunk),)
        _ = connection.execute(
            "DELETE FROM wiki_link_rewards WHERE to_id IN (SELECT value FROM json_each(?))",
            parameters,
        )
        _ = connection.execute(
            "DELETE FROM wiki_links WHERE to_id IN (SELECT value FROM json_each(?))",
            parameters,
        )
        _ = connection.execute(
            "DELETE FROM wiki_node_rewards WHERE entry_id IN (SELECT value FROM json_each(?))",
            parameters,
        )


def validate_reward_rows(connection: sqlite3.Connection) -> bool:
    """Reject non-finite, zero, negative, or over-cap reward scores."""
    for query in (
        "SELECT entry_id, score FROM wiki_node_rewards",
        "SELECT from_id, to_id, score FROM wiki_link_rewards",
    ):
        for row in connection.execute(query).fetchall():
            score = float(row[-1])
            if not math.isfinite(score) or score <= 0 or score > REWARD_CAP:
                return False
    return True


class KGBinaryValidator:
    """Validate one SQLite wiki graph using a read-only connection."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def validate(self) -> KGValidationResult:
        """Return ``OK=True`` only when graph schema/data/integrity checks pass.

        Validation is scoped to one DB and does not certify installation-wide
        DB inventory or runtime access behavior.
        """
        errors: list[str] = []
        integrity_check = "unavailable"
        foreign_key_violations = 0
        entry_count = 0
        link_count = 0
        reward_tick = -1
        connection: sqlite3.Connection | None = None

        try:
            uri = f"{self.db_path.expanduser().resolve().as_uri()}?mode=ro"
            connection = sqlite3.connect(uri, uri=True)
            _ = connection.execute("PRAGMA query_only=ON")
            _ = connection.execute("BEGIN")
            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'",
                ).fetchall()
            }
            required = {
                "wiki_entries",
                "wiki_links",
                "wiki_graph_state",
                "wiki_node_rewards",
                "wiki_link_rewards",
            }
            missing = sorted(required - tables)
            if missing:
                errors.append(f"missing_tables:{','.join(missing)}")
            else:
                integrity_rows = connection.execute("PRAGMA integrity_check").fetchall()
                integrity_values = tuple(str(row[0]) for row in integrity_rows)
                integrity_check = ";".join(integrity_values) if integrity_values else "empty_result"
                if integrity_values != ("ok",):
                    errors.append("integrity_check_failed")

                foreign_key_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
                foreign_key_violations = len(foreign_key_rows)
                if foreign_key_rows:
                    errors.append("foreign_key_check_failed")

                entry_count = int(connection.execute("SELECT COUNT(*) FROM wiki_entries").fetchone()[0])
                link_count = int(connection.execute("SELECT COUNT(*) FROM wiki_links").fetchone()[0])
                orphan_count = int(
                    connection.execute(
                        """SELECT COUNT(*) FROM wiki_links l
                           LEFT JOIN wiki_entries f ON f.id = l.from_id
                           LEFT JOIN wiki_entries t ON t.id = l.to_id
                           WHERE f.id IS NULL OR t.id IS NULL""",
                    ).fetchone()[0],
                )
                if orphan_count:
                    errors.append("orphan_link_endpoints")

                invalid_relations = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM wiki_links WHERE relation IS NULL OR trim(relation) = ''",
                    ).fetchone()[0],
                )
                if invalid_relations:
                    errors.append("invalid_relation_values")

                states = connection.execute("SELECT id, tick FROM wiki_graph_state ORDER BY id").fetchall()
                if len(states) != 1 or int(states[0][0]) != 1 or int(states[0][1]) < 0:
                    errors.append("invalid_graph_state")
                else:
                    reward_tick = int(states[0][1])

                if not validate_reward_rows(connection):
                    errors.append("invalid_reward_scores")

                node_reward_orphans = int(
                    connection.execute(
                        """SELECT COUNT(*) FROM wiki_node_rewards r
                           LEFT JOIN wiki_entries e ON e.id = r.entry_id WHERE e.id IS NULL""",
                    ).fetchone()[0],
                )
                link_reward_orphans = int(
                    connection.execute(
                        """SELECT COUNT(*) FROM wiki_link_rewards r
                           LEFT JOIN wiki_links l ON l.from_id = r.from_id AND l.to_id = r.to_id
                           WHERE l.from_id IS NULL""",
                    ).fetchone()[0],
                )
                if node_reward_orphans or link_reward_orphans:
                    errors.append("orphan_reward_rows")
        except (OSError, sqlite3.Error, ValueError, TypeError) as exc:
            errors.append(f"validation_error:{type(exc).__name__}")
        finally:
            if connection is not None:
                try:
                    connection.rollback()
                finally:
                    connection.close()

        return {
            "OK": not errors,
            "errors": tuple(errors),
            "integrity_check": integrity_check,
            "foreign_key_violations": foreign_key_violations,
            "entry_count": entry_count,
            "link_count": link_count,
            "reward_tick": reward_tick,
        }
