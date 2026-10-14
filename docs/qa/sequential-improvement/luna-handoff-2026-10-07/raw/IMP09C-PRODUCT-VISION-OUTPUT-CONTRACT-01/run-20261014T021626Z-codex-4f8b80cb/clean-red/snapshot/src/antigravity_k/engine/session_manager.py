"""SessionManager — 세션 영속성 관리.

==================================
Claw Code의 Session Persistence 아키텍처 이식.

3-Tier 메모리 모델:
- Turn Memory   : 현재 턴의 메시지 (즉시 사용)
- Session Memory: 세션 전체 히스토리 (압축 적용)
- Working Memory: 프로젝트별 장기 기억 (세션 간 유지)

세션은 .antigravity/sessions/ 디렉토리에 JSON 파일로 저장됩니다.
프로젝트 디렉토리 기반으로 세션을 자동 매칭합니다.
"""

import hashlib
import json
import logging
import os
import tempfile
import threading
import time
import uuid
from collections.abc import Generator, Mapping
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Final, TypedDict, cast, final

from antigravity_k.engine.memory_contracts import JsonValue

logger = logging.getLogger(__name__)

# CR-02: 세션 저장 무결성 계약
SESSION_REVISION_FIELD: Final[str] = "revision"
SESSION_LOCK_DIR_NAME: Final[str] = ".locks"
# NX-03: 세션 ID 세대와 삭제 표식(tombstone) 계약.
# 삭제는 같은 per-session 잠금 안에서 tombstone을 먼저 durable하게 남긴 뒤
# 가시 데이터를 제거한다. tombstone에는 세션 본문·PIN 등 민감 내용을 넣지 않는다.
SESSION_GENERATION_FIELD: Final[str] = "generation"
SESSION_TOMBSTONE_DIR_NAME: Final[str] = ".tombstones"
SESSION_TOMBSTONE_SCHEMA: Final[str] = "agk.session-tombstone.v1"


class SessionPersistenceError(RuntimeError):
    """CR-02: 세션 저장 실패. 마지막 정상 파일 바이트는 보존된다.

    호출자(API/CLI/UI)는 이 예외를 저장 성공으로 응답해서는 안 된다.
    ``public_detail``은 응답에 넣어도 안전한 문구다(내부 경로/스택 미포함).
    """

    error_code: str = "session_persistence_error"
    public_detail: str = "Session state could not be persisted; the last good file is preserved"


class SessionDurabilityUncertainError(SessionPersistenceError):
    """CR-02: replace는 성공했으나 디렉터리 fsync가 실패했다.

    새 완전한 JSON이 이미 관측될 수 있으므로 오래된 데이터로 되돌리지 않는다.
    """

    error_code: str = "session_durability_uncertain"
    public_detail: str = "Session bytes were written but durability could not be confirmed; reload before retrying"


class StaleSessionWriteError(SessionPersistenceError):
    """CR-02: 다른 writer가 먼저 저장해 메모리 스냅샷이 뒤처졌다.

    잠금만이 아니라 디스크 revision 비교로 판정한다. 전체 메모리 덮어쓰기를 거부한다.
    """

    error_code: str = "stale_session_write"
    public_detail: str = "Session was modified by another writer; reload before saving"


class SessionDeletedError(SessionPersistenceError):
    """NX-03: 삭제된 세션 ID를 오래된 writer가 다시 만들려 했다.

    삭제는 tombstone(세대 표식)을 durable하게 남긴다. tombstone 세대 이하의
    스냅샷(또는 파일이 사라진 것을 모르는 writer)은 같은 ID를 다시 만들 수 없다.
    호출자는 재로드 또는 새 세션 시작으로 안내받아야 한다.
    """

    error_code: str = "session_deleted"
    public_detail: str = "Session was deleted; reload or start a new session"


def default_session_base_dir() -> str:
    """기본 세션 저장 루트. 테스트는 이 함수를 패치해 사용자 홈을 보호한다."""
    return os.path.join(os.path.expanduser("~"), ".antigravity", "sessions")


def _serialize_session(payload: Mapping[str, object]) -> str:
    """세션 직렬화 (테스트에서 serialize 실패를 주입할 수 있게 분리)."""
    return json.dumps(dict(payload), ensure_ascii=False, indent=2)


def _fsync_fd(fd: int) -> None:
    """파일/디렉터리 fsync (테스트에서 실패 주입 지점)."""
    os.fsync(fd)


def _write_session_text(fd: int, text: str) -> None:
    """임시 파일 fd에 직렬화 결과를 쓰고 flush/fsync한다."""
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            _fsync_fd(handle.fileno())
    except BaseException:
        with suppress(OSError):
            os.close(fd)
        raise


def _replace_file(source: Path, destination: Path) -> None:
    """원자적 교체 (테스트에서 실패 주입 지점)."""
    os.replace(source, destination)


def _unlink_session_file(path: Path) -> None:
    """세션 파일 제거 (테스트에서 실패/중단 주입 지점)."""
    path.unlink()


def _fsync_directory(path: Path) -> None:
    """디렉터리 엔트리 내구성 확보. 미지원 플랫폼에서는 조용히 통과한다."""
    if os.name != "posix":
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        dir_fd = os.open(str(path), flags)
    except OSError:
        # 디렉터리 fsync를 지원하지 않는 파일시스템은 내구성 판정 대상이 아니다.
        return
    try:
        _fsync_fd(dir_fd)
    finally:
        os.close(dir_fd)


def _read_session_revision(path: Path) -> int | None:
    """디스크 세션의 revision. 구형 레코드(필드 없음)는 0, 손상은 None."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    raw = data.get(SESSION_REVISION_FIELD, 0)
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
        return 0
    return raw


def _read_session_payload(path: Path) -> dict[str, object] | None:
    """세션 JSON 전체를 읽는다(실패/손상은 None)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return cast(dict[str, object], data)


def _session_generation(payload: Mapping[str, object] | None) -> int:
    """레코드의 세대. 필드가 없는 구형 레코드는 0이다."""
    if not payload:
        return 0
    raw = payload.get(SESSION_GENERATION_FIELD, 0)
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
        return 0
    return raw


def _session_tombstone_path(base_dir: str, session_id: str) -> Path:
    return Path(base_dir) / SESSION_TOMBSTONE_DIR_NAME / f"{_session_lock_name(session_id)}.json"


def _read_tombstone(base_dir: str, session_id: str) -> dict[str, object] | None:
    """삭제 표식을 읽는다. 없거나 손상이면 None(가짜 표식을 만들지 않는다)."""
    try:
        data = json.loads(_session_tombstone_path(base_dir, session_id).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return cast(dict[str, object], data)


def _tombstone_generation(tombstone: Mapping[str, object] | None) -> int | None:
    """표식의 세대(표식이 없으면 None)."""
    if not tombstone:
        return None
    raw = tombstone.get(SESSION_GENERATION_FIELD, 0)
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
        return 0
    return raw


def _write_session_tombstone(base_dir: str, session_id: str, *, generation: int, revision: int) -> None:
    """삭제 사실을 durable하게 기록한다(본문 없음). 실패는 그대로 전파한다."""
    payload: dict[str, object] = {
        "schema": SESSION_TOMBSTONE_SCHEMA,
        "session_id": session_id,
        SESSION_GENERATION_FIELD: max(0, int(generation)),
        SESSION_REVISION_FIELD: max(0, int(revision)),
        "deleted_at": time.time(),
    }
    _write_session_file_atomically(_session_tombstone_path(base_dir, session_id), payload)


def _deleted_residue(base_dir: str, session_id: str, payload: Mapping[str, object] | None) -> bool:
    """표식 세대 >= 파일 세대이면 삭제가 중단된 잔재다(가시 세션으로 취급하지 않는다)."""
    generation = _tombstone_generation(_read_tombstone(base_dir, session_id))
    if generation is None:
        return False
    return generation >= _session_generation(payload)


def _quarantine_session_file(path: Path) -> Path:
    """손상된 세션 파일을 보존한 뒤 치운다(삭제하지 않는다)."""
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    target = path.with_name(f"{path.name}.corrupt-{stamp}")
    try:
        os.replace(path, target)
    except OSError as exc:
        raise SessionPersistenceError(f"Damaged session file cannot be quarantined: {path}") from exc
    return target


def _record_revision(session: "SessionData", revision: int) -> None:
    """메모리 세션 스냅샷에 revision을 반영한다(상수 키 → literal-required 회피)."""
    session["revision"] = revision


def _session_lock_name(session_id: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in session_id)[:96]


def _new_session_id(project_hash: str) -> str:
    """CR-02: 신규 세션 ID = 프로젝트 식별 정보 + UUID (시간 비의존).

    과거 ID(`{project_hash}_{epoch초}`)는 resume/list에서 계속 읽힌다.
    """
    return f"{project_hash}_{uuid.uuid4().hex}"


def _write_session_file_atomically(path: Path, payload: Mapping[str, object]) -> str:
    """CR-02: 직렬화 → 고유 임시파일 → flush/fsync → atomic replace → 디렉터리 fsync.

    replace 이전의 모든 실패는 원본 파일 바이트를 그대로 둔다. replace 이후
    디렉터리 fsync 실패는 되돌리지 않고 내구성 불확실 오류로 전달한다.
    """
    text = _serialize_session(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        os.chmod(tmp, 0o600)
        _write_session_text(fd, text)
        _replace_file(tmp, path)
    except OSError as exc:
        # 자신이 만든 임시 파일만 정리한다. replace 이전 실패는 마지막 정상
        # 파일 바이트를 그대로 둔다. 저수준 errno는 노출하지 않고 체인으로 보존한다.
        with suppress(OSError):
            tmp.unlink()
        raise SessionPersistenceError(f"Session bytes could not be persisted: {path}") from exc
    except BaseException:
        # 직렬화/프로그래밍 오류는 원형을 유지한다(임시 파일만 정리).
        with suppress(OSError):
            tmp.unlink()
        raise
    try:
        _fsync_directory(path.parent)
    except OSError as exc:
        raise SessionDurabilityUncertainError(
            f"Session bytes were replaced but the directory fsync failed: {path}"
        ) from exc
    return text


class SessionMetadata(TypedDict):
    total_tokens_used: int
    tools_used: list[str]
    files_modified: list[str]
    ended_at: float | None


class SessionData(TypedDict):
    id: str
    project_path: str
    project_hash: str
    created_at: float
    updated_at: float
    turn_count: int
    revision: int
    messages: list[dict[str, str]]
    working_memory: dict[str, object]
    metadata: SessionMetadata


class SessionInfo(TypedDict):
    id: str
    project_path: str
    turn_count: int
    created_at: float
    updated_at: float
    message_count: int
    memory_keys: list[str]
    metadata: dict[str, object]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in cast(list[object], value) if isinstance(item, str)]


def _message_list(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    messages: list[dict[str, str]] = []
    for item in cast(list[object], value):
        if not isinstance(item, dict):
            continue
        record = cast(dict[object, object], item)
        role = record.get("role")
        content = record.get("content")
        if isinstance(role, str) and isinstance(content, str):
            messages.append({"role": role, "content": content})
    return messages


@final
class SessionManager:
    """세션 영속성 관리자.

    Claw Code의 세션 패턴:
    - 프로젝트별 세션 자동 생성/복원
    - 세션 메타데이터 (시작 시간, 턴 수, 토큰 사용)
    - Working Memory (프로젝트별 장기 기억)
    """

    def __init__(self, base_dir: str | None = None):
        """Initialize the SessionManager.

        Args:
            base_dir (str | None): str | None base dir.

        """
        self.base_dir = base_dir or default_session_base_dir()
        os.makedirs(self.base_dir, exist_ok=True)

        self._current_session: SessionData | None = None
        self._session_id: str | None = None
        # CR-02: 메모리 스냅샷이 근거하는 디스크 revision과 저장 직렬화 락.
        self._base_revision: int = 0
        # NX-03: 스냅샷이 근거하는 세션 세대(삭제 판정용).
        self._base_generation: int = 0
        self._save_lock = threading.RLock()

    # ─────────── 세션 라이프사이클 ───────────

    def start_session(
        self,
        project_path: str | None = None,
        resume: bool = True,
    ) -> str:
        """새 세션을 시작하거나, 기존 세션을 이어갑니다.

        Args:
            project_path: 프로젝트 루트 경로 (세션 매칭용)
            resume: True이면 기존 세션을 이어갈 수 있음

        Returns:
            session_id

        """
        project_path = project_path or os.getcwd()

        # 프로젝트 기반 세션 ID 생성
        # P0 수정: MD5 → SHA256 (보안 감사 대응)
        project_hash = hashlib.sha256(os.path.abspath(project_path).encode()).hexdigest()[:8]

        if resume:
            # 최근 세션 찾기
            existing = self._find_latest_session(project_hash)
            if existing:
                self._load_session(existing)
                logger.info("Resumed session: %s", self._session_id)
                return self._session_id or ""

        # 새 세션 생성 — CR-02: 시간이 아니라 UUID로 유일성을 보장한다.
        self._session_id = _new_session_id(project_hash)
        self._base_revision = 0
        # NX-03: 신규 세션은 세대 0(첫 저장에서 1로 올라간다). 삭제된 ID의
        # 묵시적 재사용(부활)은 금지이며, 새 ID는 항상 새 UUID다.
        self._base_generation = 0
        self._current_session = {
            "id": self._session_id,
            "project_path": os.path.abspath(project_path),
            "project_hash": project_hash,
            "created_at": time.time(),
            "updated_at": time.time(),
            "turn_count": 0,
            "revision": 0,
            "messages": [],  # Session Memory
            "working_memory": {},  # Working Memory (장기)
            "metadata": {
                "total_tokens_used": 0,
                "tools_used": [],
                "files_modified": [],
                "ended_at": None,
            },
        }

        self._save_session()
        logger.info("Created new session: %s", self._session_id)
        return self._session_id

    def save(self) -> None:
        """현재 세션을 디스크에 저장합니다."""
        if self._current_session:
            self._current_session["updated_at"] = time.time()
            self._save_session()

    def end_session(self) -> None:
        """현재 세션을 종료하고 저장합니다."""
        if self._current_session:
            self._current_session["metadata"]["ended_at"] = time.time()
            self._save_session()
            logger.info("Session ended: %s", self._session_id)
            self._current_session = None
            self._session_id = None

    # ─────────── Turn Memory ───────────

    def add_turn(
        self,
        messages: list[dict[str, str]] | None = None,
        *,
        role: str | None = None,
        content: str | None = None,
    ) -> None:
        """턴(사용자 입력 + 어시스턴트 응답)을 세션에 추가합니다.

        두 가지 호출 패턴을 지원:
          1. add_turn([{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}])
          2. add_turn(role="user", content="...")  (단일 메시지, BuiltinMemoryProvider 호환)
        """
        if not self._current_session:
            _ = self.start_session()
            assert self._current_session is not None

        # role/content 키워드 인자로 단일 메시지 추가 (호환성)
        if role is not None and content is not None:
            messages = [{"role": role, "content": content}]
        elif messages is None:
            return

        self._current_session["messages"].extend(messages)
        self._current_session["turn_count"] += 1
        self._current_session["updated_at"] = time.time()

        # 자동 저장 (5턴마다). CR-02: 저장 실패는 숨기지 않고 호출자에게 전파한다
        # (UI/API가 저장 성공으로 응답하거나 세션을 비워 재생성하지 않도록).
        if self._current_session["turn_count"] % 5 == 0:
            self._save_session()

    def get_messages(self) -> list[dict[str, str]]:
        """현재 세션의 전체 메시지를 반환합니다."""
        if not self._current_session:
            return []
        return self._current_session.get("messages", [])

    def get_recent_messages(self, count: int = 10) -> list[dict[str, str]]:
        """최근 N개 메시지를 반환합니다."""
        messages = self.get_messages()
        return messages[-count:] if len(messages) > count else messages

    # ─────────── Working Memory (장기 기억) ───────────

    def set_memory(self, key: str, value: object) -> None:
        """Working Memory에 값을 저장합니다."""
        if not self._current_session:
            _ = self.start_session()
            assert self._current_session is not None
        self._current_session["working_memory"][key] = {
            "value": value,
            "last_accessed": time.time(),
            "access_count": 1,
        }

    def get_memory(self, key: str, default: object = None) -> object:
        """Working Memory에서 값을 조회합니다."""
        if not self._current_session:
            return default
        if key in self._current_session["working_memory"]:
            mem = self._current_session["working_memory"][key]
            # 만약 예전 포맷의 단순 값이면
            if isinstance(mem, dict) and "last_accessed" in mem:
                record = cast(dict[str, object], mem)
                record["last_accessed"] = time.time()
                access_count = record.get("access_count", 0)
                record["access_count"] = access_count + 1 if isinstance(access_count, int) else 1
                return record.get("value")
            new_record: dict[str, object] = {
                "value": mem,
                "last_accessed": time.time(),
                "access_count": 1,
            }
            self._current_session["working_memory"][key] = new_record
            return new_record["value"]
        return default

    def get_all_memory(self) -> dict[str, object]:
        """모든 Working Memory를 반환합니다."""
        if not self._current_session:
            return {}
        result: dict[str, object] = {}
        for k, v in self._current_session.get("working_memory", {}).items():
            if isinstance(v, dict) and "value" in v:
                result[k] = v["value"]
            else:
                result[k] = v
        return result

    def get_working_memory(self) -> dict[str, object]:
        """Working Memory를 반환합니다 (get_all_memory의 별칭 — BuiltinMemoryProvider 호환)."""
        return self.get_all_memory()

    def clear_memory(self, scope: str = "all") -> int:
        if scope not in {"session", "working", "project", "global", "all"}:
            raise ValueError(f"Unsupported memory scope: {scope}")
        if scope in {"project", "global"}:
            return 0
        if scope == "all":
            deleted = 0
            if self._current_session:
                deleted += len(self._current_session.get("messages", []))
                deleted += len(self._current_session.get("working_memory", {}))
            current_path = Path(self.base_dir) / f"{self._session_id}.json" if self._session_id else None
            for session_path in sorted(Path(self.base_dir).glob("*.json")):
                # NX-03: 삭제는 저장과 같은 per-session 잠금 안에서 tombstone을 먼저
                # durable하게 남긴 뒤 가시 파일을 제거한다. 표식 기록 실패는 삭제
                # 성공으로 보고하지 않고 파일도 남긴다.
                # 현재 세션은 메모리 스냅샷으로 이미 셌으므로 파일 집계는 건너뛴다.
                deleted += self._delete_session_file(session_path, count=session_path != current_path)
            self._current_session = None
            self._session_id = None
            self._base_revision = 0
            self._base_generation = 0
            return deleted

        if not self._current_session:
            return 0

        deleted = 0
        if scope == "session":
            messages = self._current_session.get("messages", [])
            deleted += len(messages)
            self._current_session["messages"] = []
            self._current_session["turn_count"] = 0
            self._current_session["metadata"] = {
                "total_tokens_used": 0,
                "tools_used": [],
                "files_modified": [],
                "ended_at": None,
            }
        if scope == "working":
            deleted += len(self._current_session.get("working_memory", {}))
            self._current_session["working_memory"] = {}

        self.save()
        return deleted

    def export_memory(self, scope: str = "all") -> list[dict[str, JsonValue]]:
        if scope not in {"session", "working", "project", "global", "all"}:
            raise ValueError(f"Unsupported memory scope: {scope}")
        if scope in {"project", "global"}:
            return []
        if scope == "all":
            records: list[dict[str, JsonValue]] = []
            current_path = Path(self.base_dir) / f"{self._session_id}.json"
            for session_path in Path(self.base_dir).glob("*.json"):
                if session_path == current_path and self._current_session is not None:
                    records.append(
                        {
                            "session_id": session_path.stem,
                            "data": cast(JsonValue, cast(object, self._current_session)),
                        },
                    )
                    continue
                try:
                    data = cast(object, json.loads(session_path.read_text(encoding="utf-8")))
                except (OSError, json.JSONDecodeError):
                    continue
                records.append({"session_id": session_path.stem, "data": cast(JsonValue, data)})
            return records
        if not self._current_session:
            return []
        key = "messages" if scope == "session" else "working_memory"
        return [
            {
                "session_id": self._session_id,
                "scope": scope,
                "data": cast(JsonValue, self._current_session.get(key, {})),
            },
        ]

    def redact_memory(self, scope: str = "all") -> int:
        records = self.export_memory(scope)
        if scope in {"project", "global"}:
            return 0
        from antigravity_k.engine.secret_scanner import redact_full

        def redact_value(value: object) -> tuple[object, int]:
            if isinstance(value, str):
                redacted = redact_full(value)
                return redacted, int(redacted != value)
            if isinstance(value, dict):
                changed = 0
                object_result: dict[str, object] = {}
                object_value = cast(dict[object, object], value)
                for key, item in object_value.items():
                    redacted_item, count = redact_value(item)
                    object_result[str(key)] = redacted_item
                    changed += count
                return object_result, changed
            if isinstance(value, list):
                changed = 0
                list_result: list[object] = []
                list_value = cast(list[object], value)
                for item in list_value:
                    redacted_item, count = redact_value(item)
                    list_result.append(redacted_item)
                    changed += count
                return list_result, changed
            return value, 0

        changed = 0
        if scope == "all":
            for record in records:
                data, count = redact_value(cast(object, record["data"]))
                changed += count
                path = Path(self.base_dir) / f"{record['session_id']}.json"
                if path == Path(self.base_dir) / f"{self._session_id}.json" and isinstance(data, dict):
                    self._current_session = cast(SessionData, cast(object, data))
                _ = path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        elif self._current_session:
            data = cast(SessionData, cast(object, dict(self._current_session)))
            if scope == "session":
                redacted, count = redact_value(data.get("messages", []))
                data["messages"] = cast(list[dict[str, str]], redacted)
            else:
                redacted, count = redact_value(data.get("working_memory", {}))
                data["working_memory"] = cast(dict[str, object], redacted)
            self._current_session = data
            changed += count
            self.save()
        return changed

    def apply_retention(self, max_age_days: int) -> int:
        if max_age_days < 0:
            raise ValueError("max_age_days must be non-negative")
        cutoff = time.time() - (max_age_days * 86400)
        current_path = Path(self.base_dir) / f"{self._session_id}.json"
        deleted = 0
        for session_path in sorted(Path(self.base_dir).glob("*.json")):
            if session_path == current_path:
                continue
            try:
                if session_path.stat().st_mtime >= cutoff:
                    continue
            except OSError:
                continue
            # NX-03: retention도 삭제 경로이므로 같은 잠금·tombstone 규칙을 따른다.
            _ = self._delete_session_file(session_path)
            deleted += 1
        return deleted

    # ─────────── 메타데이터 추적 ───────────

    def record_tool_use(self, tool_name: str) -> None:
        """도구 사용을 기록합니다."""
        if self._current_session:
            tools = self._current_session["metadata"]["tools_used"]
            if tool_name not in tools:
                tools.append(tool_name)

    def record_file_modified(self, file_path: str) -> None:
        """파일 수정을 기록합니다."""
        if self._current_session:
            files = self._current_session["metadata"]["files_modified"]
            if file_path not in files:
                files.append(file_path)

    def record_tokens(self, count: int) -> None:
        """토큰 사용량을 기록합니다."""
        if self._current_session:
            self._current_session["metadata"]["total_tokens_used"] += count

    # ─────────── 세션 조회 ───────────

    # ─────────── NX-03 후속: 삭제 표식(tombstone) 누적 관측과 회수 ───────────

    def tombstone_usage(self) -> dict[str, object]:
        """삭제 표식 누적 관측 — 개수·바이트·가장 오래된/최신 나이(초).

        표식은 삭제된 ID 당 1개씩 남고 자동 만료가 없다(NX-03). 자동 prune 대신 운영자가
        이 값으로 회수 시점을 결정한다.
        """
        directory = Path(self.base_dir) / SESSION_TOMBSTONE_DIR_NAME
        files = sorted(path for path in directory.glob("*.json") if path.is_file())
        now = time.time()
        total_bytes = 0
        ages: list[float] = []
        for path in files:
            with suppress(OSError):
                total_bytes += path.stat().st_size
                ages.append(max(0.0, now - path.stat().st_mtime))
        return {
            "directory": str(directory),
            "count": len(files),
            "total_bytes": total_bytes,
            "oldest_age_seconds": max(ages) if ages else None,
            "newest_age_seconds": min(ages) if ages else None,
            "automatic_expiry": False,
        }

    def collect_tombstones(self, *, older_than_seconds: float, dry_run: bool = True) -> dict[str, object]:
        """운영자가 명시적으로 호출하는 표식 회수(NX-03 후속: GC 정책).

        정책: **임의 TTL 로 자동 만료하지 않는다.** 표식을 지우면 그 세대의 stale writer 가
        다시 살아날 수 있으므로, 나이 기준은 위험을 감수하는 주체가 정한다 — 이 메서드는
        `older_than_seconds` 를 **필수**로 받고(>0), 기본은 dry_run 이며, 실제 회수도
        삭제가 아니라 `<tombstones>/gc/<UTC>/` 로 **이동**만 한다(되돌릴 수 있고 감사 기록이 남는다).

        반환: 옮긴(또는 옮길) 표식 목록과 개수·바이트·아카이브 경로.
        """
        if older_than_seconds <= 0:
            raise ValueError("older_than_seconds must be > 0 (no implicit 'expire everything')")
        directory = Path(self.base_dir) / SESSION_TOMBSTONE_DIR_NAME
        now = time.time()
        candidates: list[tuple[Path, int]] = []
        for path in sorted(directory.glob("*.json")):
            if not path.is_file():
                continue
            with suppress(OSError):
                if now - path.stat().st_mtime < older_than_seconds:
                    continue
                candidates.append((path, path.stat().st_size))

        report: dict[str, object] = {
            "dry_run": dry_run,
            "older_than_seconds": float(older_than_seconds),
            "candidates": [path.name for path, _ in candidates],
            "count": len(candidates),
            "bytes": sum(size for _, size in candidates),
            "archive_dir": None,
            "moved": [],
        }
        if dry_run or not candidates:
            return report

        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        archive = directory / "gc" / stamp
        archive.mkdir(parents=True, exist_ok=True)
        moved: list[str] = []
        for path, _size in candidates:
            target = archive / path.name
            try:
                _ = path.replace(target)
            except OSError:
                logger.warning("Could not archive tombstone %s", path, exc_info=True)
                continue
            moved.append(path.name)
        if moved:
            _write_session_file_atomically(
                archive / "gc-report.json",
                {
                    "schema": "agk.session-tombstone-gc.v1",
                    "moved": moved,
                    "older_than_seconds": float(older_than_seconds),
                    "collected_at": now,
                    "note": "tombstones were moved (not deleted) — restoring a file re-enables its protection",
                },
            )
        report["archive_dir"] = str(archive)
        report["moved"] = moved
        logger.info(
            "Session tombstone GC: moved %d marker(s) older than %.0fs to %s",
            len(moved),
            older_than_seconds,
            archive,
        )
        return report

    def list_sessions(self, limit: int = 10) -> list[dict[str, object]]:
        """최근 세션 목록을 반환합니다."""
        sessions: list[dict[str, object]] = []
        for fname in os.listdir(self.base_dir):
            if fname.endswith(".json"):
                fpath = os.path.join(self.base_dir, fname)
                try:
                    with open(fpath, encoding="utf-8") as f:
                        raw_data = cast(object, json.load(f))
                    if not isinstance(raw_data, dict):
                        continue
                    data = cast(dict[str, object], raw_data)
                    # NX-03: 삭제가 중단된 잔재는 목록에 노출하지 않는다.
                    record_id = str(data.get("id") or fname[: -len(".json")])
                    if _deleted_residue(self.base_dir, record_id, data):
                        continue
                    sessions.append(
                        {
                            "id": data.get("id", fname),
                            "project_path": data.get("project_path", "?"),
                            "created_at": data.get("created_at", 0),
                            "updated_at": data.get("updated_at", 0),
                            "turn_count": data.get("turn_count", 0),
                            # CR-02: 구형 레코드는 revision 0으로 노출한다.
                            "revision": data.get(SESSION_REVISION_FIELD, 0),
                        },
                    )
                except (json.JSONDecodeError, KeyError):
                    continue

        def updated_at(session: dict[str, object]) -> float:
            value = session.get("updated_at", 0)
            return float(value) if isinstance(value, (int, float)) else 0.0

        sessions.sort(key=updated_at, reverse=True)
        return sessions[:limit]

    def load_session(self, session_id: str) -> bool:
        """특정 세션을 로드합니다.

        NX-03: 삭제 표식이 남은 잔재(삭제 중 중단)는 가시 세션으로 취급하지 않는다.
        """
        fpath = os.path.join(self.base_dir, f"{session_id}.json")
        if os.path.exists(fpath):
            payload = _read_session_payload(Path(fpath))
            record_id = str(payload.get("id") or session_id) if payload else session_id
            if _deleted_residue(self.base_dir, record_id, payload) or _deleted_residue(
                self.base_dir, session_id, payload
            ):
                logger.warning("Refusing to load deleted session residue: %s", session_id)
                return False
            self._load_session(fpath)
            return True
        return False

    def get_session_info(self) -> SessionInfo | None:
        """현재 세션 정보를 반환합니다."""
        if not self._current_session:
            return None
        return {
            "id": self._session_id or "",
            "project_path": self._current_session.get("project_path", ""),
            "turn_count": self._current_session.get("turn_count", 0),
            "created_at": self._current_session.get("created_at", 0.0),
            "updated_at": self._current_session.get("updated_at", 0.0),
            "message_count": len(self._current_session.get("messages", [])),
            "memory_keys": list(self._current_session.get("working_memory", {}).keys()),
            "metadata": cast(dict[str, object], cast(object, self._current_session.get("metadata", {}))),
        }

    # ─────────── 내부 메서드 ───────────

    def _session_path(self, session_id: str) -> Path:
        return Path(self.base_dir) / f"{session_id}.json"

    @contextmanager
    def _session_process_lock(self, session_id: str) -> Generator[None, None, None]:
        """CR-02: 같은 세션을 쓰는 다른 프로세스와 배타적으로 직렬화한다.

        잠금 파일은 `.locks/` 하위에 두어 `list_sessions`/retention이 세션 JSON으로
        오인하지 않게 한다. `fcntl`이 없는 플랫폼은 스레드 락 + revision CAS만으로
        동작한다(지원 OS는 macOS/Linux).
        """
        try:
            import fcntl
        except ImportError:  # pragma: no cover - 지원 범위 밖(Windows)
            yield
            return
        lock_dir = Path(self.base_dir) / SESSION_LOCK_DIR_NAME
        lock_dir.mkdir(parents=True, exist_ok=True)
        lock_path = lock_dir / f"{_session_lock_name(session_id)}.lock"
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            with suppress(OSError):
                fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _delete_session_file(self, session_path: Path, *, count: bool = True) -> int:
        """NX-03: per-session 잠금 안에서 tombstone을 먼저 쓰고 파일을 제거한다.

        반환값은 제거한 메시지+working memory 개수다(`count=False`면 0).
        tombstone 기록이 실패하면 예외를 전파하고 가시 파일을 남긴다
        (삭제 성공으로 보고하지 않는다).
        """
        lock_id = session_path.stem
        first = _read_session_payload(session_path)
        known_id = str(first.get("id") or lock_id) if first else lock_id
        deleted = 0
        with self._save_lock, self._session_process_lock(known_id):
            payload = _read_session_payload(session_path)
            session_id = str(payload.get("id") or lock_id) if payload else lock_id
            # 파일명 기반 writer와 레코드 id 기반 writer를 모두 막는다.
            for target_id in sorted({known_id, lock_id, session_id}):
                existing = _read_tombstone(self.base_dir, target_id)
                generation = max(
                    _session_generation(payload),
                    _tombstone_generation(existing) or 0,
                )
                _write_session_tombstone(
                    self.base_dir,
                    target_id,
                    generation=generation,
                    revision=_read_session_revision(session_path) or 0,
                )
            if payload is not None and count:
                messages = payload.get("messages", [])
                working_memory = payload.get("working_memory", {})
                deleted += len(messages) if isinstance(messages, list) else 0
                deleted += len(working_memory) if isinstance(working_memory, dict) else 0
            try:
                _unlink_session_file(session_path)
            except FileNotFoundError:
                pass
            except OSError as exc:
                # 표식은 남았지만 가시 파일이 남았다(삭제 중단). 삭제 성공으로
                # 보고하지 않고 전파한다. 같은 표식 때문에 잔재는 가시 세션으로
                # 취급되지 않으며, 재시도가 이어서 제거한다.
                raise SessionPersistenceError(f"Session file could not be removed: {session_path}") from exc
        return deleted

    def _save_session(self) -> None:
        """CR-02: 원자 저장 + per-session 프로세스 잠금 + revision CAS.

        직렬화 → 고유 임시파일 → flush/fsync → atomic replace → 디렉터리 fsync.
        replace 이전 실패는 마지막 정상 파일을 보존하고, 실패를 그대로 전파한다.
        디스크 revision이 메모리 기준보다 앞서 있으면 stale write를 거부한다.

        NX-03: 같은 잠금 안에서 삭제 표식(tombstone)과 파일 존재를 먼저 확인한다.
        삭제된 ID는 다시 만들지 않고(``SessionDeletedError``), 삭제 표식 없는
        파일 소실은 stale writer가 되살리지 않는다(``StaleSessionWriteError``).
        """
        if not self._current_session or not self._session_id:
            return
        self._current_session["updated_at"] = time.time()
        session_id = self._session_id
        path = self._session_path(session_id)
        with self._save_lock, self._session_process_lock(session_id):
            tombstone = _read_tombstone(self.base_dir, session_id)
            deleted_generation = _tombstone_generation(tombstone)
            if deleted_generation is not None and self._base_generation <= deleted_generation:
                raise SessionDeletedError(
                    f"Session {session_id} was deleted "
                    f"(deleted generation {deleted_generation}, memory generation {self._base_generation})"
                )
            disk_revision: int | None = None
            quarantined_locally = False
            if path.is_file():
                disk_revision = _read_session_revision(path)
                if disk_revision is None:
                    # 손상 잔재(예: 과거 truncate-dump 중단)는 삭제하지 않고 격리한다.
                    quarantined = _quarantine_session_file(path)
                    quarantined_locally = True
                    logger.error("Damaged session file preserved as %s", quarantined)
            elif not quarantined_locally and (self._base_revision > 0 or self._base_generation > 0):
                # 한 번 저장했던 세션의 파일이 사라졌다 → 삭제된 세션을 되살리는
                # stale writer로 판정한다(신규 세션 생성과 구별).
                raise StaleSessionWriteError(
                    f"Session {session_id} file is gone; refusing to recreate it from a stale snapshot"
                )
            if disk_revision is not None and disk_revision != self._base_revision:
                raise StaleSessionWriteError(
                    f"Session {session_id} was modified by another writer "
                    f"(disk revision {disk_revision}, memory revision {self._base_revision})"
                )
            next_revision = (disk_revision if disk_revision is not None else 0) + 1
            next_generation = self._base_generation or 1
            payload = dict(self._current_session)
            payload[SESSION_REVISION_FIELD] = next_revision
            payload[SESSION_GENERATION_FIELD] = next_generation
            try:
                _write_session_file_atomically(path, payload)
            except SessionDurabilityUncertainError:
                # 새 완전한 JSON이 이미 보일 수 있다. 오래된 데이터로 되돌리지 않고
                # 재조회로 실제 저장 상태를 반영한 뒤 오류를 전달한다.
                observed = _read_session_revision(path) if path.is_file() else None
                if observed is not None:
                    self._base_revision = observed
                    _record_revision(self._current_session, observed)
                raise
            self._base_revision = next_revision
            self._base_generation = next_generation
            _record_revision(self._current_session, next_revision)

    def _load_session(self, fpath: str) -> None:
        """디스크에서 세션을 로드합니다."""
        try:
            with open(fpath, encoding="utf-8") as f:
                raw_data = cast(object, json.load(f))
            if not isinstance(raw_data, dict):
                raise TypeError("Session file must contain a JSON object")
            data = cast(dict[str, object], raw_data)
            self._current_session = cast(SessionData, cast(object, data))
            session_id = data.get("id")
            self._session_id = session_id if isinstance(session_id, str) else None
            # CR-02: 구형 레코드는 revision 기본값 0으로 읽는다(잠금 안에서 비교).
            raw_revision = data.get(SESSION_REVISION_FIELD, 0)
            self._base_revision = (
                raw_revision
                if isinstance(raw_revision, int) and not isinstance(raw_revision, bool) and raw_revision >= 0
                else 0
            )
            # NX-03: 구형 레코드(`generation` 없음)는 0으로 읽는다.
            self._base_generation = _session_generation(data)
        except Exception:
            logger.exception("Failed to load session")
            self._current_session = None
            self._session_id = None
            self._base_revision = 0
            self._base_generation = 0

    def _find_latest_session(self, project_hash: str) -> str | None:
        """프로젝트 해시로 최근 세션 파일을 찾습니다.

        CR-02: 파일명 prefix만으로 선택하지 않는다. 구형 `{hash}_{epoch}`과 신형
        `{hash}_{uuid}`의 suffix를 시간으로 해석하지 않고, 레코드의 ``project_hash``
        메타데이터를 실제 식별자로 확인한 뒤 ``updated_at`` 기준으로 고른다.
        손상/타 프로젝트 레코드는 후보에서 제외한다(빈 세션으로 대체하지 않는다).
        """
        candidates: list[tuple[float, str]] = []
        for fname in os.listdir(self.base_dir):
            if not fname.endswith(".json") or not fname.startswith(project_hash):
                continue
            fpath = os.path.join(self.base_dir, fname)
            try:
                with open(fpath, encoding="utf-8") as session_file:
                    raw = cast(object, json.load(session_file))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(raw, dict):
                continue
            record = cast(dict[str, object], raw)
            # NX-03: 삭제가 중단된 잔재는 resume 후보가 아니다(부활 금지).
            record_id = str(record.get("id") or fname[: -len(".json")])
            if _deleted_residue(self.base_dir, record_id, record):
                continue
            stored_hash = record.get("project_hash")
            if isinstance(stored_hash, str) and stored_hash != project_hash:
                continue
            updated_at = record.get("updated_at")
            stamp = (
                float(updated_at) if isinstance(updated_at, (int, float)) and not isinstance(updated_at, bool) else 0.0
            )
            if stamp <= 0:
                try:
                    stamp = os.path.getmtime(fpath)
                except OSError:
                    continue
            candidates.append((stamp, fpath))

        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    # ─────────── 자동 컨텍스트 복원 (P1-5) ───────────

    def auto_restore(self, project_path: str | None = None) -> str | None:
        """이전 세션의 핵심 컨텍스트를 자동 복원합니다.

        자동화 핵심:
        - 마지막 세션의 요약 생성 (수정 파일, 사용 도구, 핵심 대화)
        - 에이전트 시스템 프롬프트에 주입하여 연속성 보장
        - '빈 칸판' 문제 해결

        Returns:
            복원된 컨텍스트 문자열 (없으면 None)

        """
        project_path = project_path or os.getcwd()
        project_hash = hashlib.sha256(os.path.abspath(project_path).encode()).hexdigest()[:8]

        session_path = self._find_latest_session(project_hash)
        if not session_path:
            return None

        try:
            with open(session_path, encoding="utf-8") as f:
                raw_prev_session = cast(object, json.load(f))
        except Exception:
            logger.exception("Unhandled exception")
            return None

        if not isinstance(raw_prev_session, dict):
            return None
        prev_session = cast(dict[str, object], raw_prev_session)
        meta_value = prev_session.get("metadata", {})
        meta = cast(dict[str, object], meta_value) if isinstance(meta_value, dict) else {}
        files_value = meta.get("files_modified", [])
        files_modified = _string_list(files_value)
        tools_value = meta.get("tools_used", [])
        tools_used = _string_list(tools_value)
        working_value = prev_session.get("working_memory", {})
        working_mem = cast(dict[str, object], working_value) if isinstance(working_value, dict) else {}
        messages_value = prev_session.get("messages", [])
        messages = _message_list(messages_value)
        turn_value = prev_session.get("turn_count", 0)
        turn_count = turn_value if isinstance(turn_value, int) else 0

        if turn_count == 0:
            return None

        # 마지막 사용자 메시지 3개 요약
        recent_user_msgs = [m["content"][:200] for m in messages if m.get("role") == "user"][-3:]

        # 컨텍스트 문자열 생성
        parts = ["\n[SESSION CONTEXT RESTORE]"]
        parts.append(f"Previous session: {turn_count} turns")

        if recent_user_msgs:
            parts.append("Recent topics:")
            for msg in recent_user_msgs:
                parts.append(f"  - {msg}")

        # 작업 2: 실제 최근 대화 내용 복원 — 에이전트가 이전 대화를 "기억"하도록
        recent_msgs = messages[-10:] if len(messages) > 10 else messages
        if recent_msgs:
            parts.append("\nRecent conversation:")
            for recent_msg in recent_msgs:
                role = recent_msg.get("role", "?")
                content = str(recent_msg.get("content", ""))[:300]
                if role in ("user", "assistant") and content.strip():
                    parts.append(f"  {role}: {content}")

        if files_modified:
            parts.append(f"Modified files: {', '.join(files_modified[-10:])}")

        if tools_used:
            parts.append(f"Tools used: {', '.join(tools_used)}")

        # Staleness Tracker (P2-12)
        if working_mem:
            active_keys: list[str] = []
            now = time.time()
            for k, v in working_mem.items():
                last_accessed = now
                if isinstance(v, dict) and "last_accessed" in v:
                    memory_record = cast(dict[str, object], v)
                    candidate = memory_record["last_accessed"]
                    if isinstance(candidate, (int, float)):
                        last_accessed = float(candidate)
                # 7일 이상 경과된 메모리는 Staleness 처리 (배제)
                if (now - last_accessed) < 7 * 24 * 3600:
                    active_keys.append(k)

            if active_keys:
                parts.append("Working memory keys: " + ", ".join(active_keys[:10]))
                if len(active_keys) < len(working_mem):
                    parts.append(
                        f"  *(Note: {len(working_mem) - len(active_keys)} old items were purged due to staleness)*",
                    )

        # 자율 행동/수복 메모리 주입 (Hermes 차용)
        memory_dir = Path(project_path) / ".agent" / "memory"
        immune_dir = memory_dir / "immune_patches"
        if immune_dir.exists():
            patches = list(immune_dir.glob("*.json"))
            if patches:
                parts.append("\n[AUTONOMOUS LEARNINGS & PATCHES]")
                # 최근 3개의 패치 이력만 컨텍스트에 주입
                for p in sorted(patches, key=lambda x: x.stat().st_mtime, reverse=True)[:3]:
                    try:
                        with open(p, encoding="utf-8") as f:
                            raw_data = cast(object, json.load(f))
                        if not isinstance(raw_data, dict):
                            continue
                        data = cast(dict[str, object], raw_data)
                        parts.append(
                            f"  - Self-Patched {data.get('target_file')}: {data.get('explanation')}",
                        )
                    except Exception:
                        logger.exception("Unhandled exception")
                        continue

        parts.append("[END SESSION CONTEXT]\n")

        context = "\n".join(parts)
        logger.info("[AutoRestore] Restored context from session with %s turns", turn_count)
        return context
