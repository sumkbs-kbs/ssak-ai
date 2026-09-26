"""Static import reach measurement for cognitive surfaces."""

from __future__ import annotations

import ast
import json
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .cognitive_surface_types import CORE_MODULE, DEFAULT_SURFACE_ENTRYPOINTS, LEGACY_MODULE


@dataclass(frozen=True, slots=True)
class SurfaceReach:
    """정적 도달성. 실행 trace가 아니라 import 그래프 기준이다."""

    label: str
    module: str
    module_path: str
    exists: bool
    reaches_legacy: bool
    reaches_core: bool
    legacy_via: tuple[str, ...] = ()
    core_via: tuple[str, ...] = ()

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "label": self.label,
            "module": self.module,
            "module_path": self.module_path,
            "exists": self.exists,
            "reaches_legacy": self.reaches_legacy,
            "reaches_core": self.reaches_core,
            "legacy_via": list(self.legacy_via),
            "core_via": list(self.core_via),
        }


@dataclass(frozen=True, slots=True)
class SurfaceMeasurement:
    source_root: str
    legacy_module: str
    core_module: str
    reached_at: str
    entrypoints: tuple[SurfaceReach, ...]

    @property
    def legacy_count(self) -> int:
        return sum(1 for item in self.entrypoints if item.reaches_legacy)

    @property
    def core_count(self) -> int:
        return sum(1 for item in self.entrypoints if item.reaches_core)

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "source_root": self.source_root,
            "legacy_module": self.legacy_module,
            "core_module": self.core_module,
            "reached_at": self.reached_at,
            "legacy_count": self.legacy_count,
            "core_count": self.core_count,
            "entrypoints": [item.as_mapping() for item in self.entrypoints],
        }

    def to_json(self) -> str:
        return json.dumps(self.as_mapping(), ensure_ascii=False, indent=2, sort_keys=True)


def _module_file(module: str, source_root: Path) -> Path | None:
    parts = module.split(".")
    base = source_root.joinpath(*parts)
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _package_of(module: str, path: Path) -> tuple[str, ...]:
    """파일 경로에서 package 구성요소를 구한다(상대 import 해석용)."""

    if path.name == "__init__.py":
        return tuple(module.split("."))
    return tuple(module.split(".")[:-1])


def _first_party_imports(module: str, path: Path) -> tuple[str, ...]:
    """모듈의 first-party import를 절대 모듈명으로 돌려준다(상대 import 포함)."""

    tree = ast.parse(path.read_text(encoding="utf-8"))
    package = _package_of(module, path)
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names if alias.name.startswith("antigravity_k"))
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level == 0:
            base: tuple[str, ...] = ()
        else:
            # level 1은 현재 package, level 2는 한 단계 위를 가리킨다.
            base = package[: len(package) - (node.level - 1)] if node.level > 1 else package
        candidates: list[str] = []
        if node.module:
            candidates.append(".".join((*base, node.module)))
        else:
            candidates.append(".".join(base))
        # `from . import sub` 처럼 이름으로 하위 모듈을 가져오는 형태도 도달로 센다.
        for alias in node.names:
            if alias.name == "*":
                continue
            candidates.append(".".join((*base, node.module, alias.name) if node.module else (*base, alias.name)))
        modules.extend(item for item in candidates if item.startswith("antigravity_k"))
    return tuple(dict.fromkeys(modules))


def _reach_path(entry_module: str, target: str, source_root: Path, *, limit: int = 4000) -> tuple[str, ...]:
    """entry에서 target까지 import 그래프 최단 경로. 도달하지 않으면 빈 tuple."""

    entry_file = _module_file(entry_module, source_root)
    if entry_file is None:
        return ()
    if entry_module == target:
        return (entry_module,)
    seen = {entry_module}
    queue: list[tuple[str, tuple[str, ...]]] = [(entry_module, (entry_module,))]
    while queue and len(seen) < limit:
        module, trail = queue.pop(0)
        path = _module_file(module, source_root)
        if path is None:
            continue
        for imported in _first_party_imports(module, path):
            if imported == target:
                return (*trail, imported)
            if imported in seen:
                continue
            seen.add(imported)
            queue.append((imported, (*trail, imported)))
    return ()


def measure_surface_reach(
    *,
    source_root: str | Path | None = None,
    entrypoints: Sequence[tuple[str, str]] = DEFAULT_SURFACE_ENTRYPOINTS,
    now: datetime | None = None,
) -> SurfaceMeasurement:
    """entrypoint별로 legacy loop와 신규 core에 도달하는지 측정한다(정적 import 그래프)."""

    root = Path(source_root) if source_root is not None else Path(__file__).resolve().parents[2]
    reaches: list[SurfaceReach] = []
    for label, module in entrypoints:
        path = _module_file(module, root)
        legacy_via = _reach_path(module, LEGACY_MODULE, root)
        core_via = _reach_path(module, CORE_MODULE, root)
        reaches.append(
            SurfaceReach(
                label=label,
                module=module,
                module_path=str(path) if path is not None else "",
                exists=path is not None,
                reaches_legacy=bool(legacy_via),
                reaches_core=bool(core_via),
                legacy_via=legacy_via,
                core_via=core_via,
            )
        )
    return SurfaceMeasurement(
        source_root=str(root),
        legacy_module=LEGACY_MODULE,
        core_module=CORE_MODULE,
        reached_at=(now or datetime.now(tz=UTC)).isoformat(),
        entrypoints=tuple(reaches),
    )


@dataclass(frozen=True, slots=True)
class DurableSurfaceHistory:
    """Project-scoped runtime history projected from durable storage (not a fresh adapter)."""

    project_id: str
    last_episode_id: str | None
    last_termination: str | None
    dispatched_actions: int
    refused_actions: int
    observed_at: str | None
    source: str  # durable | unavailable | empty
    projection_revision: int = 0

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "project_id": self.project_id,
            "last_episode_id": self.last_episode_id,
            "last_termination": self.last_termination,
            "dispatched_actions": self.dispatched_actions,
            "refused_actions": self.refused_actions,
            "observed_at": self.observed_at,
            "source": self.source,
            "projection_revision": self.projection_revision,
        }


class DurableSurfaceHistoryStore:
    """SQLite projection of surface episode runs. Read paths never invent counters."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure()

    def _connect(self) -> "sqlite3.Connection":
        import sqlite3

        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _ensure(self) -> None:

        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS surface_runs ("
                "project_id TEXT NOT NULL, "
                "episode_id TEXT NOT NULL, "
                "termination TEXT, "
                "dispatched_actions INTEGER NOT NULL DEFAULT 0, "
                "refused_actions INTEGER NOT NULL DEFAULT 0, "
                "observed_at TEXT NOT NULL, "
                "projection_revision INTEGER NOT NULL DEFAULT 0, "
                "PRIMARY KEY(project_id, episode_id))"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS surface_project_meta ("
                "project_id TEXT PRIMARY KEY, "
                "last_episode_id TEXT, "
                "projection_revision INTEGER NOT NULL DEFAULT 0)"
            )

    def record_run(
        self,
        *,
        project_id: str,
        episode_id: str,
        termination: str | None,
        dispatched_actions: int,
        refused_actions: int,
        observed_at: str | None = None,
    ) -> DurableSurfaceHistory:
        from datetime import UTC, datetime

        when = observed_at or datetime.now(tz=UTC).isoformat()
        with self._connect() as connection:
            meta = connection.execute(
                "SELECT projection_revision FROM surface_project_meta WHERE project_id=?",
                (project_id,),
            ).fetchone()
            revision = int(meta[0]) + 1 if meta else 1
            connection.execute(
                "INSERT INTO surface_runs("
                "project_id, episode_id, termination, dispatched_actions, refused_actions, "
                "observed_at, projection_revision) VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(project_id, episode_id) DO UPDATE SET "
                "termination=excluded.termination, "
                "dispatched_actions=excluded.dispatched_actions, "
                "refused_actions=excluded.refused_actions, "
                "observed_at=excluded.observed_at, "
                "projection_revision=excluded.projection_revision",
                (
                    project_id,
                    episode_id,
                    termination or "",
                    int(dispatched_actions),
                    int(refused_actions),
                    when,
                    revision,
                ),
            )
            connection.execute(
                "INSERT INTO surface_project_meta(project_id, last_episode_id, projection_revision) "
                "VALUES (?,?,?) ON CONFLICT(project_id) DO UPDATE SET "
                "last_episode_id=excluded.last_episode_id, "
                "projection_revision=excluded.projection_revision",
                (project_id, episode_id, revision),
            )
        return self.latest(project_id) or DurableSurfaceHistory(
            project_id=project_id,
            last_episode_id=episode_id,
            last_termination=termination,
            dispatched_actions=dispatched_actions,
            refused_actions=refused_actions,
            observed_at=when,
            source="durable",
            projection_revision=revision,
        )

    def latest(self, project_id: str) -> DurableSurfaceHistory | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT r.episode_id, r.termination, r.dispatched_actions, r.refused_actions, "
                "r.observed_at, r.projection_revision "
                "FROM surface_project_meta m "
                "JOIN surface_runs r ON r.project_id=m.project_id AND r.episode_id=m.last_episode_id "
                "WHERE m.project_id=?",
                (project_id,),
            ).fetchone()
        if row is None:
            return DurableSurfaceHistory(
                project_id=project_id,
                last_episode_id=None,
                last_termination=None,
                dispatched_actions=0,
                refused_actions=0,
                observed_at=None,
                source="empty",
                projection_revision=0,
            )
        return DurableSurfaceHistory(
            project_id=project_id,
            last_episode_id=str(row[0]) or None,
            last_termination=str(row[1]) or None,
            dispatched_actions=int(row[2]),
            refused_actions=int(row[3]),
            observed_at=str(row[4]) or None,
            source="durable",
            projection_revision=int(row[5]),
        )

    def totals(self, project_id: str) -> tuple[int, int]:
        """Sum dispatched/refused across recorded runs for the project."""

        with self._connect() as connection:
            row = connection.execute(
                "SELECT COALESCE(SUM(dispatched_actions),0), COALESCE(SUM(refused_actions),0) "
                "FROM surface_runs WHERE project_id=?",
                (project_id,),
            ).fetchone()
        return int(row[0]), int(row[1])
