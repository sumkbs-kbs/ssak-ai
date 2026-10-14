"""Project Registry & Persistence Engine.
=========================================
Manages real local project workspaces, persists them to data/projects.json,
and coordinates active workspace switching.

DAT-03 (BR-03) 내구성 계약:
- 모든 변경은 process 공유 lock(flock) 아래 reload-modify-save로 수행된다.
- 저장은 temp file + fsync + atomic replace(os.replace)로 이루어진다.
- 저장 실패는 절대 조용히 성공으로 반환되지 않고 ``RegistrySaveError``를 던진다.
- 정상 저장마다 직전 정상 상태가 ``<storage>.bak``에 미러된다.
- 로드 시 primary가 손상/절단되면 ``<storage>.bak``에서 복구하고 손상본은
  ``<storage>.corrupt-<ts>``로 격리 보존한다.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("antigravity_k.engine.project_registry")

_DEFAULT_STORAGE_PATH = Path("data/projects.json")
_LOCK_ACQUIRE_TIMEOUT_SEC = 30.0
_FSYNC_PARENT_DIR = True


class RegistrySaveError(RuntimeError):
    """프로젝트 레지스트리 저장 실패 (disk-full, permission, interrupted 등)."""

    def __init__(self, message: str, *, cause: BaseException | None = None) -> None:
        super().__init__(message)
        self.__cause__ = cause


class RegistryLockTimeout(RuntimeError):
    """flock 획득 시간 초과."""


class ProjectRecord(BaseModel):
    """Represents a registered local workspace project.

    구버전 dataclass 시그니처 호환: 위치 인자 (id, name, path, is_active,
    last_accessed_at, tasks)와 ``to_dict``/``from_dict``를 그대로 제공한다.
    """

    model_config = {"populate_by_name": True}

    id: str = Field(default_factory=lambda: f"proj_{uuid.uuid4().hex[:8]}")
    name: str = "Project"
    path: str = "."
    is_active: bool = False
    last_accessed_at: str | None = None
    tasks: list[str] = Field(default_factory=list)

    def __init__(
        self,
        id: str | None = None,  # noqa: A002 — 구버전 필드명 호환
        name: str | None = None,
        path: str | None = None,
        is_active: bool = False,
        last_accessed_at: str | None = None,
        tasks: list[str] | None = None,
        **data: Any,
    ) -> None:
        if id is not None:
            data["id"] = id
        if name is not None:
            data["name"] = name
        if path is not None:
            data["path"] = os.path.abspath(str(path))
        data.setdefault("is_active", is_active)
        if last_accessed_at is not None:
            data["last_accessed_at"] = last_accessed_at
        if tasks is not None:
            data["tasks"] = tasks
        super().__init__(**data)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectRecord":
        return cls(**data)

    @property
    def tasks_list(self) -> list[str]:
        return list(self.tasks)


class ProjectRegistry:
    """Process-safe persistent registry for workspace projects.

    모든 변경 연산은 공유 lock 파일(flock) 아래에서 디스크의 최신 상태를
    reload한 뒤 적용하고 저장한다 — multi-process last-writer-wins 손실 방지.
    """

    def __init__(self, storage_path: Path | None = None) -> None:
        self.storage_path = Path(storage_path or _DEFAULT_STORAGE_PATH)
        self._lock_path = self.storage_path.with_suffix(self.storage_path.suffix + ".lock")
        self._projects: dict[str, ProjectRecord] = {}
        self._load()

    # ── locking ──────────────────────────────────────────────────────────

    def _locked(self) -> "_RegistryFileLock":
        return _RegistryFileLock(self._lock_path)

    # ── persistence ──────────────────────────────────────────────────────

    def _ensure_default_project(self) -> None:
        """Ensure the current working directory / root is registered as default."""
        if not self._projects:
            cwd = os.getcwd()
            name = os.path.basename(cwd) or "Ssak-Ai"
            default_proj = ProjectRecord(
                id="default",
                name=name,
                path=cwd,
                is_active=True,
                tasks=[],
            )
            self._projects[default_proj.id] = default_proj
            self._save_locked()

    def _load(self) -> None:
        if not self.storage_path.exists():
            # 최초 생성 경로도 **공유 lock 아래에서** 수행한다.
            #
            # 왜인가 (2026-09-17, SC-3 5-worker 경합 실측): 종전에는 이 경로만 lock 밖이었고,
            # 백업 회전의 임시 파일 이름이 고정("projects.json.bak.tmp")이었다. 여러 프로세스가
            # **같은 빈 저장소**에서 동시에 시작하면 둘 다 그 이름으로 쓰고, 한 쪽이 먼저
            # `os.replace` 로 옮긴 뒤 다른 쪽이 자기 이름을 찾지 못해
            # `RegistrySaveError: … projects.json.bak.tmp -> projects.json.bak` 로 **죽었다**
            # (하네스 worker 가 그대로 죽고, 부모는 결과 큐를 기다리다 멈췄다).
            # 같은 종류의 결함이 대화 저장소에서는 이미 고쳐졌다(결정론적 `<conv>.tmp` 이름이
            # 동시 writer 를 깨뜨린 F1) — registry 의 백업 회전에 같은 규칙이 남아 있었다.
            with self._locked():
                if self.storage_path.exists():
                    # 경합에서 진 쪽: 이긴 프로세스가 쓴 파일을 읽는다(재귀하지 않는다 —
                    # 같은 lock 을 다시 잡으면 flock 은 같은 프로세스라도 막힌다).
                    self._load_existing()
                else:
                    self._ensure_default_project()
            return

        self._load_existing()

    def _load_existing(self) -> None:
        """저장소가 이미 있을 때의 로드(손상 시 backup 복구 포함)."""
        try:
            raw = self._read_json(self.storage_path)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            recovered = self._try_recover_from_backup()
            if not recovered:
                logger.warning(
                    "Failed to load projects from %s and no usable backup; resetting",
                    self.storage_path,
                    exc_info=True,
                )
                self._projects = {}
                self._ensure_default_project()
            return

        self._apply_raw(raw)
        self._ensure_default_project()

    @staticmethod
    def _read_json(path: Path) -> Any:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _apply_raw(self, raw: Any) -> None:
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    try:
                        rec = ProjectRecord(**item)
                    except Exception:  # noqa: BLE001 — 개별 레코드 손상은 전체를 죽이지 않는다
                        logger.warning("Skipping malformed registry record: %r", item)
                        continue
                    self._projects[rec.id] = rec

    def _try_recover_from_backup(self) -> bool:
        """primary 손상 시 backup 복구 + 손상본 격리 보존."""
        backup = self._backup_path
        corrupt_copy = self.storage_path.with_name(f"{self.storage_path.name}.corrupt-{int(time.time())}")
        try:
            if corrupt_copy != backup:
                # 손상본 보존 (같은 파일이면 생략)
                corrupt_copy.write_bytes(self.storage_path.read_bytes())
                logger.warning("Corrupted registry preserved at %s", corrupt_copy)
        except OSError:
            logger.warning("Could not preserve corrupted registry copy", exc_info=True)

        if not backup.exists():
            return False
        try:
            raw = self._read_json(backup)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            logger.warning("Backup %s is also unreadable; starting clean", backup)
            return False

        self._projects = {}
        self._apply_raw(raw)
        self._ensure_default_project()
        # 복구 상태를 primary에 재구축
        try:
            self._save_locked()
            logger.warning("Registry recovered from backup %s", backup)
        except RegistrySaveError:
            logger.warning("Recovered in memory but failed to persist", exc_info=True)
        return True

    @property
    def _backup_path(self) -> Path:
        return self.storage_path.with_name(self.storage_path.name + ".bak")

    def _backup_tmp_path(self) -> Path:
        """백업 회전용 임시 파일 경로 — **프로세스별 고유 이름**(primary tmp 와 같은 규칙).

        고정 이름이면 두 writer 가 같은 파일을 쓰고, 한 쪽이 먼저 `os.replace` 로 옮긴 뒤
        다른 쪽이 `FileNotFoundError` 로 죽는다(2026-09-17 SC-3 경합 실측 — 임시 파일이 아니라
        **예외**가 관측된 이유다). lock 이 지켜지면 동시 진입이 없지만, 그 보장이 깨지는 경로가
        하나라도 있으면 여기서 죽므로 이름을 고유하게 두는 편이 싸다.
        """
        return self._backup_path.with_name(f".{self._backup_path.name}.tmp-{os.getpid()}")

    def _save_locked(self) -> None:
        """lock 보유 전제. temp+fsync+atomic replace로 저장, 실패는 typed error."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = [p.model_dump() for p in self._projects.values()]
        tmp = self.storage_path.with_name(f".{self.storage_path.name}.tmp-{os.getpid()}")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            if _FSYNC_PARENT_DIR:
                dir_fd = os.open(self.storage_path.parent, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            # backup 회전: 이전 primary(정상 상태 가정)를 bak으로
            if self.storage_path.exists():
                backup_tmp = self._backup_tmp_path()
                backup_tmp.write_bytes(self.storage_path.read_bytes())
                os.replace(backup_tmp, self._backup_path)
            os.replace(tmp, self.storage_path)  # atomic
        except OSError as e:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            # OBS-01: 레지스트리 저장 실패를 운영 metric에 기록
            from antigravity_k.engine.operational_metrics import record_registry_write

            record_registry_write("save_error")
            raise RegistrySaveError(
                f"Failed to save project registry to {self.storage_path}: {e}",
                cause=e,
            ) from e

    # ── public API (모든 변경은 lock + reload-modify-save) ───────────────

    def _reload_under_lock(self) -> None:
        """lock 보유 전제. 디스크의 최신 상태를 in-memory로 병합 적용."""
        if not self.storage_path.exists():
            return
        try:
            raw = self._read_json(self.storage_path)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            logger.warning("Registry unreadable during reload; keeping memory", exc_info=True)
            return
        disk_records: dict[str, ProjectRecord] = {}
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    try:
                        rec = ProjectRecord(**item)
                    except Exception:  # noqa: BLE001
                        continue
                    disk_records[rec.id] = rec
        # 디스크를 진실로 하되, 메모리에만 있는 신규 추가분은 보존(add_project의
        # 경우 lock 안에서 이미 반영 예정) — 여기선 디스크 우선 병합.
        self._projects.update(disk_records)

    def list_projects(self) -> list[dict[str, Any]]:
        self._ensure_default_project()
        return [
            p.model_dump()
            for p in sorted(
                self._projects.values(),
                key=lambda x: x.last_accessed_at or "",
                reverse=True,
            )
        ]

    def get_project(self, project_id: str) -> ProjectRecord | None:
        """Return a registered project by id without activating it."""
        if not project_id:
            return None
        return self._projects.get(project_id)

    def resolve_canonical_root(self, project_id: str) -> str | None:
        """Return the absolute path for a project id, or None if unknown.

        Does not mutate active project state. Callers that need allowlist /
        existence checks must use ``resolve_canonical_project_root`` in
        ``request_execution_context`` (ARC-01).
        """
        record = self.get_project(project_id)
        if record is None:
            return None
        return os.path.abspath(record.path)

    def get_active_project(self) -> ProjectRecord:
        self._ensure_default_project()
        for p in self._projects.values():
            if p.is_active:
                return p
        first = next(iter(self._projects.values()))
        first.is_active = True
        self._save_under_lock()
        return first

    def add_project(self, name: str, path: str, tasks: list[str] | None = None) -> ProjectRecord:
        abs_path = os.path.abspath(path)
        with self._locked():
            self._reload_under_lock()
            for p in self._projects.values():
                if os.path.abspath(p.path) == abs_path:
                    p.name = name or p.name
                    p.last_accessed_at = datetime.now().isoformat()
                    self._activate_single_locked(p.id)
                    self._save_locked()
                    return p

            project = ProjectRecord(
                id=f"proj_{uuid.uuid4().hex[:8]}",
                name=name.strip() or os.path.basename(abs_path) or "Project",
                path=abs_path,
                is_active=True,
                tasks=tasks or [],
            )
            self._projects[project.id] = project
            self._activate_single_locked(project.id)
            self._save_locked()
            return project

    def _activate_single_locked(self, active_id: str) -> None:
        for pid, p in self._projects.items():
            p.is_active = pid == active_id
            if p.is_active:
                p.last_accessed_at = datetime.now().isoformat()

    def switch_project(self, project_id_or_path: str) -> ProjectRecord | None:
        with self._locked():
            self._reload_under_lock()
            target: ProjectRecord | None = None
            if project_id_or_path in self._projects:
                target = self._projects[project_id_or_path]
            else:
                abs_path = os.path.abspath(project_id_or_path)
                for p in self._projects.values():
                    if os.path.abspath(p.path) == abs_path:
                        target = p
                        break
            if target is None:
                return None
            self._activate_single_locked(target.id)
            self._save_locked()
            return target

    def remove_project(self, project_id: str) -> bool:
        with self._locked():
            self._reload_under_lock()
            if project_id not in self._projects:
                return False
            # Do not delete the only project
            if len(self._projects) <= 1:
                return False
            was_active = self._projects[project_id].is_active
            del self._projects[project_id]
            if was_active:
                first = next(iter(self._projects.values()))
                first.is_active = True
            self._save_locked()
            return True

    def _save_under_lock(self) -> None:
        """get_active_project 등의 편의 저장 — lock 획득 후 저장."""
        with self._locked():
            self._save_locked()


class _RegistryFileLock:
    """storage 바로 옆 lock 파일에 flock을 잡는다 (process 공유)."""

    def __init__(self, lock_path: Path, timeout: float = _LOCK_ACQUIRE_TIMEOUT_SEC) -> None:
        self._lock_path = lock_path
        self._timeout = timeout
        self._fd: int | None = None

    def __enter__(self) -> "_RegistryFileLock":
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self._lock_path, os.O_CREAT | os.O_RDWR, 0o644)
        deadline = time.monotonic() + self._timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
                self._fd = fd  # pragma: no cover — unreachable; kept for clarity
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    os.close(fd)
                    # OBS-01: lock 획득 타임아웃을 운영 metric에 기록
                    from antigravity_k.engine.operational_metrics import record_registry_write

                    record_registry_write("lock_timeout")
                    raise RegistryLockTimeout(
                        f"Could not acquire registry lock {self._lock_path} within {self._timeout}s"
                    ) from None
                time.sleep(0.05)
        self._fd = fd
        return self

    def __exit__(self, *exc: object) -> None:
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            finally:
                os.close(self._fd)
                self._fd = None


_global_registry: ProjectRegistry | None = None


def get_project_registry() -> ProjectRegistry:
    global _global_registry
    if _global_registry is None:
        _global_registry = ProjectRegistry()
    return _global_registry
