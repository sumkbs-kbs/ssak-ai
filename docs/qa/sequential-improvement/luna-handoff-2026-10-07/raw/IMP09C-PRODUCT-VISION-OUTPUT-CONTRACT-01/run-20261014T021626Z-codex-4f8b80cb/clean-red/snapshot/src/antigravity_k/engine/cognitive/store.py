"""Canonical cognitive store (P02) — create-only record, transaction manifest, Git persistence.

계약(COGNITIVE_DATA_MODEL.md 저장과 transaction 경계):
- record는 append-only다. 같은 ID를 다른 내용으로 다시 쓰지 않는다.
- writer는 staging manifest → 파일 flush → atomic rename → Git commit → committed manifest 공개 순서를 지킨다.
- reader는 committed manifest에 열거된 record만 읽는다. 미완료 transaction은 노출되지 않는다.
- 여러 파일 rename은 atomic transaction이 아니다. 공개 시점(committed manifest)이 유일한 공개 경계다.
- 손상/변조는 digest 재계산으로 검출한다. 원본 digest는 조용히 갱신하지 않는다.

Git과 lock은 기존 VaultEngine과 같은 규칙(`.git/.agk_vault.lock`)을 재사용한다.
별도 lock 순서를 만들지 않기 위해 store root를 Git repo로 두고 같은 lock file을 쓴다.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast, final

import yaml
from filelock import SoftFileLock

from antigravity_k.engine.cognitive.models import Record, from_wire, to_wire
from antigravity_k.engine.cognitive.protected_targets import (
    ActorKind,
    HumanApproval,
    ProtectedWriteGuard,
    ProtectedWriteRequest,
    ProtectionViolation,
    WriteChannel,
    WriteOperation,
)
from antigravity_k.engine.cognitive.references import (
    REL_SUPERSEDES,
    EntityType,
    Reference,
    ReferenceValidationError,
    ResolvedTarget,
    assert_no_supersedes_cycle,
    entity_type_for_id,
    namespace_for,
    validate_references,
)

RECORDS_DIR: Final[str] = "records"
CONTROL_DIR: Final[str] = ".cognitive"
STAGING_DIR: Final[str] = f"{CONTROL_DIR}/staging"
COMMITTED_DIR: Final[str] = f"{CONTROL_DIR}/committed"
INDEX_FILE: Final[str] = f"{CONTROL_DIR}/index/records.json"
LOCK_FILE: Final[str] = ".git/.agk_vault.lock"

STAGED: Final[str] = "STAGED"
COMMITTED: Final[str] = "COMMITTED"

GitCommitter = Callable[[Path, str], str | None]


class CanonicalStoreError(ValueError):
    """store 계약 위반의 공통 상위 타입."""


class DuplicateRecordError(CanonicalStoreError):
    """이미 공개된 ID를 다른 내용으로 다시 쓰려 할 때 발생한다(create-only)."""


class TransactionConflictError(CanonicalStoreError):
    """같은 transaction ID에 다른 content identity를 stage하려 할 때 발생한다."""


class TransactionNotFoundError(CanonicalStoreError):
    """알 수 없는 transaction ID."""


class CanonicalDigestError(CanonicalStoreError):
    """저장된 record가 기록된 digest와 일치하지 않는다(변조/손상)."""


class GitCommitError(CanonicalStoreError):
    """Git commit 실패. record는 아직 공개되지 않았으며 recover로 재시도한다."""


def canonical_digest(wire: Mapping[str, object]) -> str:
    """wire dict의 정규 직렬화 digest. 정렬·구분자 고정으로 재현 가능하게 만든다."""

    encoded = json.dumps(wire, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    record_id: str
    entity_type: str
    project_id: str
    relative_path: str
    digest: str
    wire: Mapping[str, object]

    def to_json(self) -> dict[str, object]:
        return {
            "id": self.record_id,
            "entity_type": self.entity_type,
            "project_id": self.project_id,
            "path": self.relative_path,
            "digest": self.digest,
            "wire": dict(self.wire),
        }

    @staticmethod
    def from_json(value: Mapping[str, object]) -> ManifestEntry:
        return ManifestEntry(
            record_id=str(value["id"]),
            entity_type=str(value["entity_type"]),
            project_id=str(value["project_id"]),
            relative_path=str(value["path"]),
            digest=str(value["digest"]),
            wire=cast(Mapping[str, object], value["wire"]),
        )


@dataclass(frozen=True, slots=True)
class TransactionManifest:
    transaction_id: str
    created_at: str
    status: str
    episode_id: str | None
    entries: tuple[ManifestEntry, ...]

    def content_identity(self) -> tuple[str | None, tuple[str, ...]]:
        """episode와 entry digest 순서로 transaction content를 식별한다."""

        return self.episode_id, tuple(entry.digest for entry in self.entries)

    def to_json(self) -> dict[str, object]:
        return {
            "transaction_id": self.transaction_id,
            "created_at": self.created_at,
            "status": self.status,
            "episode_id": self.episode_id,
            "entries": [entry.to_json() for entry in self.entries],
        }

    @staticmethod
    def from_json(value: Mapping[str, object]) -> TransactionManifest:
        raw_entries = value.get("entries")
        entries: tuple[ManifestEntry, ...] = ()
        if isinstance(raw_entries, list):
            entries = tuple(
                ManifestEntry.from_json(cast(Mapping[str, object], entry)) for entry in cast(list[object], raw_entries)
            )
        return TransactionManifest(
            transaction_id=str(value["transaction_id"]),
            created_at=str(value["created_at"]),
            status=str(value["status"]),
            episode_id=str(value["episode_id"]) if value.get("episode_id") is not None else None,
            entries=entries,
        )


@dataclass(frozen=True, slots=True)
class CommitReceipt:
    transaction_id: str
    committed_ids: tuple[str, ...]
    git_commit: str | None
    reused_commit: bool


def _run_git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _is_valid_repo(root: Path) -> bool:
    """`.git` 경로 존재가 아니라 실제 repo 여부를 확인한다.

    lock 파일이 `.git` 아래에 생기면서 빈 디렉터리만 존재하는 경우를 repo로 오인하지 않기 위한 검사다.
    """

    if not (root / ".git").is_dir():
        return False
    return _run_git(root, "rev-parse", "--git-dir").returncode == 0


def ensure_git_repo(root: Path) -> None:
    """store root를 Git repo로 만든다(이미 유효한 repo면 아무 것도 하지 않는다)."""

    if _is_valid_repo(root):
        return
    result = _run_git(root, "init")
    if result.returncode != 0:
        raise GitCommitError(f"git init failed: {result.stderr.strip()}")


def _git_commit_default(root: Path, message: str) -> str | None:
    """Git-first 저장. 실패 시 GitCommitError로 올려 publish를 막는다."""

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return _run_git(root, *args)

    ensure_git_repo(root)
    paths = [path for path in (RECORDS_DIR, CONTROL_DIR) if (root / path).exists()]
    if not paths:
        return None
    add = run("add", "--", *paths)
    if add.returncode != 0:
        raise GitCommitError(f"git add failed: {add.stderr.strip()}")
    staged = run("diff", "--cached", "--name-only")
    if staged.returncode != 0:
        raise GitCommitError(f"git diff failed: {staged.stderr.strip()}")
    if not staged.stdout.strip():
        return None
    commit = run("commit", "-m", message)
    if commit.returncode != 0:
        raise GitCommitError(f"git commit failed: {commit.stderr.strip()}")
    head = run("rev-parse", "HEAD")
    return head.stdout.strip() or None


def _actor_kind_for(record: Record) -> ActorKind:
    producer_kind = str(record.producer.kind)
    if producer_kind == "human":
        return ActorKind.HUMAN
    if producer_kind == "brain":
        return ActorKind.BRAIN
    if producer_kind == "tool":
        return ActorKind.TOOL
    return ActorKind.BODY


def _fsync_path(path: Path) -> None:
    if not path.exists():
        return
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def render_record_markdown(record: Record) -> str:
    """canonical record의 Markdown + YAML frontmatter 표현(원본)."""

    wire = to_wire(record)
    frontmatter: dict[str, object] = {
        "schema_version": wire["schema_version"],
        "id": wire["id"],
        "entity_type": wire["entity_type"],
        "project_id": wire["project_id"],
        "created_at": wire["created_at"],
        "record_digest": canonical_digest(wire),
        "record": wire,
    }
    body = (
        f"# {record.entity_type} · {record.id}\n\n"
        "```json\n"
        f"{json.dumps(wire, ensure_ascii=False, indent=2, sort_keys=True)}\n"
        "```\n"
    )
    return f"---\n{yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False)}---\n\n{body}"


def parse_record_markdown(text: str) -> tuple[dict[str, object], str]:
    """frontmatter에서 wire record와 기록된 digest를 꺼낸다."""

    if not text.startswith("---"):
        raise CanonicalStoreError("record file has no frontmatter")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise CanonicalStoreError("record file frontmatter is not terminated")
    loaded = yaml.safe_load(parts[1])
    if not isinstance(loaded, dict):
        raise CanonicalStoreError("record file frontmatter is not a mapping")
    frontmatter = cast(dict[str, object], loaded)
    wire = frontmatter.get("record")
    if not isinstance(wire, dict):
        raise CanonicalStoreError("record file frontmatter has no record payload")
    digest = frontmatter.get("record_digest")
    if not isinstance(digest, str):
        raise CanonicalStoreError("record file frontmatter has no record_digest")
    return cast(dict[str, object], wire), digest


def record_relative_path(record_id: str) -> str:
    namespace, raw_uuid = record_id.split(":", 1)
    return f"{RECORDS_DIR}/{namespace}/{raw_uuid}.md"


@final
class CanonicalStore:
    """create-only canonical record store.

    reader는 committed manifest만 신뢰한다. 따라서 write·commit·publish 각 단계 crash 뒤에도
    미완료 transaction은 조회되지 않는다.
    """

    def __init__(
        self,
        root: str | Path,
        *,
        git_committer: GitCommitter | None = None,
        git_enabled: bool = True,
        lock_timeout: float = 30.0,
        write_guard: ProtectedWriteGuard | None = None,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.write_guard = write_guard
        self._git_enabled = git_enabled
        self._git_committer: GitCommitter = git_committer if git_committer is not None else _git_commit_default
        if git_enabled:
            # Git repo를 lock 생성 전에 확보한다. SoftFileLock이 `.git` 디렉터리를 먼저 만들면
            # git init이 건너뛰어져 이후 git add가 실패한다.
            ensure_git_repo(self.root)
        lock_relative = LOCK_FILE if git_enabled else f"{CONTROL_DIR}/agk_vault.lock"
        self._file_lock = SoftFileLock(str(self.root / lock_relative), timeout=lock_timeout)

    # ── 경로 ─────────────────────────────────────────────
    @property
    def lock_path(self) -> Path:
        """store가 쓰는 lock file. adapter도 같은 파일을 써서 lock 순서를 하나로 유지한다."""

        return Path(self._file_lock.lock_file)

    @property
    def staging_dir(self) -> Path:
        return self.root / STAGING_DIR

    @property
    def committed_dir(self) -> Path:
        return self.root / COMMITTED_DIR

    @property
    def index_path(self) -> Path:
        return self.root / INDEX_FILE

    def staged_manifest_path(self, transaction_id: str) -> Path:
        return self.staging_dir / transaction_id / "manifest.json"

    def committed_manifest_path(self, transaction_id: str) -> Path:
        return self.committed_dir / f"{transaction_id}.json"

    def record_path(self, record_id: str) -> Path:
        return self.root / record_relative_path(record_id)

    # ── 공개 상태 ────────────────────────────────────────
    def committed_manifests(self) -> tuple[TransactionManifest, ...]:
        if not self.committed_dir.exists():
            return ()
        manifests: list[TransactionManifest] = []
        for path in sorted(self.committed_dir.glob("*.json")):
            manifest = self._load_manifest(path)
            if manifest is not None:
                manifests.append(manifest)
        return tuple(manifests)

    def is_committed(self, record_id: str) -> bool:
        return record_id in self._committed_entries()

    def _committed_entries(self) -> dict[str, ManifestEntry]:
        entries: dict[str, ManifestEntry] = {}
        for manifest in self.committed_manifests():
            for entry in manifest.entries:
                entries.setdefault(entry.record_id, entry)
        return entries

    def _load_manifest(self, path: Path) -> TransactionManifest | None:
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(loaded, dict):
            return None
        return TransactionManifest.from_json(cast(dict[str, object], loaded))

    # ── 읽기 ────────────────────────────────────────────
    def _read_entry(self, record_id: str, entry: ManifestEntry) -> Record:
        path = self.root / entry.relative_path
        if not path.exists():
            raise CanonicalDigestError(f"committed record file missing: {entry.relative_path}")
        wire, digest = parse_record_markdown(path.read_text(encoding="utf-8"))
        if digest != entry.digest:
            raise CanonicalDigestError(f"manifest digest mismatch for {record_id}")
        if canonical_digest(wire) != digest:
            raise CanonicalDigestError(f"record digest mismatch for {record_id}")
        return from_wire(wire)

    def read(self, record_id: str) -> Record | None:
        """공개된 record만 반환한다. 미완료 transaction의 파일은 무시한다."""

        entry = self._committed_entries().get(record_id)
        return self._read_entry(record_id, entry) if entry is not None else None

    def read_many(
        self,
        record_ids: Iterable[str],
        *,
        committed_snapshot: Mapping[str, ManifestEntry] | None = None,
    ) -> Mapping[str, Record]:
        """committed manifest를 한 번만 읽어 여러 record를 검증·조회한다."""

        entries = self._committed_entries() if committed_snapshot is None else committed_snapshot
        records: dict[str, Record] = {}
        for record_id in dict.fromkeys(record_ids):
            entry = entries.get(record_id)
            if entry is not None:
                records[record_id] = self._read_entry(record_id, entry)
        return records

    def list_committed(self, project_id: str | None = None) -> tuple[Record, ...]:
        """manifest snapshot당 한 번만 탐색해 committed records를 읽는다."""

        entries = self._committed_entries()
        return tuple(
            self._read_entry(record_id, entry)
            for record_id, entry in sorted(entries.items())
            if project_id is None or entry.project_id == project_id
        )

    def count_committed(self) -> int:
        """record 본문을 deserialize하지 않고 committed ID 수를 반환한다."""

        return len(self._committed_entries())

    def resolve(self, target_id: str) -> ResolvedTarget | None:
        """ReferenceResolver 구현. 공개된 record만 해석한다."""

        entry = self._committed_entries().get(target_id)
        if entry is None:
            return None
        return ResolvedTarget(entity_type=EntityType(entry.entity_type), project_id=entry.project_id)

    def resolve_many(
        self,
        target_ids: Iterable[str],
        *,
        committed_snapshot: Mapping[str, ManifestEntry] | None = None,
    ) -> Mapping[str, ResolvedTarget]:
        """committed manifest를 한 번 읽어 여러 reference target을 해석한다."""

        entries = self._committed_entries() if committed_snapshot is None else committed_snapshot
        return {
            target_id: ResolvedTarget(entity_type=EntityType(entry.entity_type), project_id=entry.project_id)
            for target_id in dict.fromkeys(target_ids)
            if (entry := entries.get(target_id)) is not None
        }

    def verify_digests(self) -> int:
        """공개된 모든 record의 digest를 재계산해 변조/손상을 검출한다."""

        checked = 0
        for entry in self._committed_entries().values():
            path = self.root / entry.relative_path
            if not path.exists():
                raise CanonicalDigestError(f"committed record file missing: {entry.relative_path}")
            wire, digest = parse_record_markdown(path.read_text(encoding="utf-8"))
            if digest != entry.digest or canonical_digest(wire) != entry.digest:
                raise CanonicalDigestError(f"record digest mismatch for {entry.record_id}")
            checked += 1
        return checked

    def rebuild_index(self) -> int:
        """검색/조회용 projection을 committed manifest에서 재생성한다(원본 아님)."""

        index: dict[str, dict[str, object]] = {}
        for manifest in self.committed_manifests():
            for entry in manifest.entries:
                index[entry.record_id] = {
                    "entity_type": entry.entity_type,
                    "project_id": entry.project_id,
                    "path": entry.relative_path,
                    "digest": entry.digest,
                    "transaction_id": manifest.transaction_id,
                }
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_atomic(self.index_path, json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True))
        return len(index)

    # ── 쓰기 ────────────────────────────────────────────
    def stage(
        self,
        records: Sequence[Record],
        *,
        transaction_id: str | None = None,
        episode_id: str | None = None,
    ) -> TransactionManifest:
        """staging manifest를 만든다. 이 시점에는 어떤 record도 공개되지 않는다."""

        if not records:
            raise CanonicalStoreError("transaction without records is not allowed")
        txn_id = transaction_id if transaction_id is not None else uuid.uuid4().hex
        with self._file_lock:
            return self._stage_locked(
                records,
                transaction_id=txn_id,
                episode_id=episode_id,
                committed=self._committed_entries(),
            )

    def _stage_locked(
        self,
        records: Sequence[Record],
        *,
        transaction_id: str,
        episode_id: str | None,
        committed: Mapping[str, ManifestEntry],
    ) -> TransactionManifest:
        """caller가 lock을 잡은 상태에서 동일한 committed snapshot으로 transaction을 stage한다."""

        existing = self.committed_manifest_path(transaction_id)
        if existing.exists():
            raise DuplicateRecordError(f"transaction already committed: {transaction_id}")
        self._assert_creatable(records, committed=committed)
        proposed = TransactionManifest(
            transaction_id=transaction_id,
            created_at=datetime.now(UTC).isoformat(),
            status=STAGED,
            episode_id=episode_id,
            entries=tuple(self._entry_for(record) for record in records),
        )
        path = self.staged_manifest_path(transaction_id)
        if path.exists():
            prior = self._load_manifest(path)
            if prior is None:
                raise CanonicalStoreError(f"unreadable staged manifest: {transaction_id}")
            if prior.content_identity() == proposed.content_identity():
                # 동일 content의 idempotent replay — manifest byte를 덮어쓰지 않는다.
                return prior
            raise TransactionConflictError(
                f"transaction {transaction_id} already staged with different content identity"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        self._write_atomic(path, json.dumps(proposed.to_json(), ensure_ascii=False, indent=2, sort_keys=True))
        _fsync_path(path)
        return proposed

    def commit(self, transaction_id: str, *, message: str | None = None) -> CommitReceipt:
        """staged transaction을 공개한다. Git commit 뒤에만 committed manifest를 쓴다."""

        with self._file_lock:
            return self._commit_locked(transaction_id, message=message)

    def commit_records(
        self,
        records: Sequence[Record],
        *,
        episode_id: str | None = None,
        transaction_id: str | None = None,
        message: str | None = None,
        approvals: Sequence[HumanApproval] = (),
    ) -> CommitReceipt:
        self._enforce_protection(records, approvals=approvals)
        manifest = self.stage(records, transaction_id=transaction_id, episode_id=episode_id)
        return self.commit(manifest.transaction_id, message=message)

    def _commit_records_batch(
        self,
        records: Sequence[Record],
        *,
        committed_snapshot: dict[str, ManifestEntry],
        transaction_id: str | None = None,
        episode_id: str | None = None,
        message: str | None = None,
        approvals: Sequence[HumanApproval] = (),
        rebuild_index: bool = False,
    ) -> CommitReceipt:
        """migration 전용 batch publish; 임시 단일 writer store에서 snapshot을 재사용한다.

        호출자는 별도 dry-run root의 유일한 writer여야 하며, index를 생략한 경우 최종 index를 rebuild한다.
        이 private 경로는 일반 writer의 최신 committed manifest 검사 계약을 대체하지 않는다.
        """

        if not records:
            raise CanonicalStoreError("transaction without records is not allowed")
        self._enforce_protection(records, approvals=approvals)
        txn_id = transaction_id if transaction_id is not None else uuid.uuid4().hex
        with self._file_lock:
            fresh_committed = self._committed_entries()
            if dict(committed_snapshot) != fresh_committed:
                raise CanonicalStoreError("batch commit snapshot is stale; refresh it before publishing")
            manifest = self._stage_locked(
                records,
                transaction_id=txn_id,
                episode_id=episode_id,
                committed=fresh_committed,
            )
            receipt = self._commit_locked(
                manifest.transaction_id,
                message=message,
                update_index=rebuild_index,
                committed=fresh_committed,
            )
            committed_snapshot.update((entry.record_id, entry) for entry in manifest.entries)
            return receipt

    def _enforce_protection(self, records: Sequence[Record], *, approvals: Sequence[HumanApproval] = ()) -> None:
        """canonical store도 같은 protected write allowlist를 지난다.

        헌법/authority/premise record는 사람 승인 없이는 공개되지 않는다.
        brain·learned policy가 만든 record는 승인이 있어도 거부된다.
        """

        if self.write_guard is None:
            return
        for record in records:
            request = ProtectedWriteRequest(
                channel=WriteChannel.CANONICAL_STORE,
                actor_kind=_actor_kind_for(record),
                actor_id=record.producer.actor_id,
                targets=(str(self.record_path(record.id)),),
                operation=WriteOperation.CREATE,
                action_digest=canonical_digest(to_wire(record)),
                project_root=str(self.root),
                approvals=tuple(approvals),
            )
            decision = self.write_guard.evaluate(request)
            if not decision.allowed:
                raise ProtectionViolation(decision)

    def recover(self) -> tuple[str, ...]:
        """crash 뒤 재시도. 같은 transaction ID로 대조해 중복 publish를 막는다.

        이미 공개된 transaction은 건너뛰므로 반복 호출이 부작용을 만들지 않는다.
        """

        recovered: list[str] = []
        with self._file_lock:
            if not self.staging_dir.exists():
                return ()
            for manifest_path in sorted(self.staging_dir.glob("*/manifest.json")):
                manifest = self._load_manifest(manifest_path)
                if manifest is None or manifest.status != STAGED:
                    continue
                if self.committed_manifest_path(manifest.transaction_id).exists():
                    continue
                self._publish_locked(manifest, message=f"recover cognitive transaction {manifest.transaction_id}")
                recovered.append(manifest.transaction_id)
        return tuple(recovered)

    # ── 내부 ────────────────────────────────────────────
    def _entry_for(self, record: Record) -> ManifestEntry:
        wire = to_wire(record)
        return ManifestEntry(
            record_id=record.id,
            entity_type=str(record.entity_type),
            project_id=record.project_id,
            relative_path=record_relative_path(record.id),
            digest=canonical_digest(wire),
            wire=wire,
        )

    def _assert_creatable(self, records: Sequence[Record], *, committed: Mapping[str, ManifestEntry]) -> None:
        """ID uniqueness는 내용과 무관하게 강제한다(create-only)."""

        seen: set[str] = set()
        for record in records:
            if record.id in seen:
                raise DuplicateRecordError(f"duplicate id inside transaction: {record.id}")
            if record.id in committed:
                raise DuplicateRecordError(f"record already committed: {record.id}")
            seen.add(record.id)

    def _validate_references(
        self,
        records: Sequence[Record],
        *,
        committed: Mapping[str, ManifestEntry] | None = None,
    ) -> None:
        """존재·타입·project 범위와 supersedes 순환을 공개 전에 검사한다."""

        pending: dict[str, ResolvedTarget] = {
            record.id: ResolvedTarget(entity_type=record.entity_type, project_id=record.project_id)
            for record in records
        }
        committed_entries = self._committed_entries() if committed is None else committed

        class _Resolver:
            def resolve(self, target_id: str) -> ResolvedTarget | None:
                if target_id in pending:
                    return pending[target_id]
                entry = committed_entries.get(target_id)
                if entry is None:
                    return None
                return ResolvedTarget(entity_type=EntityType(entry.entity_type), project_id=entry.project_id)

        supersedes: dict[str, tuple[Reference, ...]] = {
            record.id: tuple(reference for reference in record.references if reference.relation == REL_SUPERSEDES)
            for record in records
        }

        resolver = _Resolver()
        for record in records:
            validate_references(record, resolver)

        def load(record_id: str) -> Sequence[Reference]:
            if record_id not in supersedes:
                entry = committed_entries.get(record_id)
                if entry is None:
                    return ()
                supersedes[record_id] = tuple(
                    Reference.model_validate(reference)
                    for reference in cast(list[object], entry.wire.get("references", []))
                    if isinstance(reference, dict) and reference.get("relation") == REL_SUPERSEDES
                )
            return supersedes[record_id]

        for record in records:
            if any(reference.relation == REL_SUPERSEDES for reference in record.references):
                assert_no_supersedes_cycle(record.id, load)

    def _write_staged_files(self, manifest: TransactionManifest) -> None:
        staged_root = self.staging_dir / manifest.transaction_id / "records"
        staged_root.mkdir(parents=True, exist_ok=True)
        for entry in manifest.entries:
            wire = from_wire(entry.wire)
            staged_path = staged_root / Path(entry.relative_path).name
            self._write_atomic(staged_path, render_record_markdown(wire))
            _fsync_path(staged_path)

    def _materialize(self, manifest: TransactionManifest) -> None:
        """staged 내용을 records/로 옮긴다. rename은 여러 파일에 걸쳐 atomic하지 않다."""

        staged_root = self.staging_dir / manifest.transaction_id / "records"
        for entry in manifest.entries:
            final_path = self.root / entry.relative_path
            final_path.parent.mkdir(parents=True, exist_ok=True)
            staged_path = staged_root / Path(entry.relative_path).name
            if not staged_path.exists():
                self._write_atomic(staged_path, render_record_markdown(from_wire(entry.wire)))
            os.replace(staged_path, final_path)
            _fsync_path(final_path)

    def _publish_locked(
        self,
        manifest: TransactionManifest,
        *,
        message: str,
        update_index: bool = True,
        committed: Mapping[str, ManifestEntry] | None = None,
    ) -> CommitReceipt:
        committed_path = self.committed_manifest_path(manifest.transaction_id)
        if committed_path.exists():
            return CommitReceipt(
                transaction_id=manifest.transaction_id,
                committed_ids=tuple(entry.record_id for entry in manifest.entries),
                git_commit=None,
                reused_commit=True,
            )

        records = [from_wire(entry.wire) for entry in manifest.entries]
        if committed is None:
            self._assert_creatable(records, committed=self._committed_entries())
            self._validate_references(records)
        else:
            self._assert_creatable(records, committed=committed)
            self._validate_references(records, committed=committed)

        self._write_staged_files(manifest)
        self._materialize(manifest)
        committed_path = self.committed_manifest_path(manifest.transaction_id)
        committed_path.parent.mkdir(parents=True, exist_ok=True)

        git_commit: str | None = None
        if self._git_enabled:
            git_commit = self._git_committer(self.root, message)

        committed_manifest = TransactionManifest(
            transaction_id=manifest.transaction_id,
            created_at=manifest.created_at,
            status=COMMITTED,
            episode_id=manifest.episode_id,
            entries=manifest.entries,
        )
        self._write_atomic(
            committed_path,
            json.dumps(committed_manifest.to_json(), ensure_ascii=False, indent=2, sort_keys=True),
        )
        _fsync_path(committed_path)
        if update_index:
            self.rebuild_index()
        return CommitReceipt(
            transaction_id=manifest.transaction_id,
            committed_ids=tuple(entry.record_id for entry in manifest.entries),
            git_commit=git_commit,
            reused_commit=False,
        )

    def _commit_locked(
        self,
        transaction_id: str,
        *,
        message: str | None,
        update_index: bool = True,
        committed: Mapping[str, ManifestEntry] | None = None,
    ) -> CommitReceipt:
        committed_path = self.committed_manifest_path(transaction_id)
        staged_path = self.staged_manifest_path(transaction_id)
        if committed_path.exists():
            manifest = self._load_manifest(committed_path)
            if manifest is None:
                raise CanonicalStoreError(f"committed manifest unreadable: {transaction_id}")
            return CommitReceipt(
                transaction_id=transaction_id,
                committed_ids=tuple(entry.record_id for entry in manifest.entries),
                git_commit=None,
                reused_commit=True,
            )
        if not staged_path.exists():
            raise TransactionNotFoundError(f"unknown transaction: {transaction_id}")
        manifest = self._load_manifest(staged_path)
        if manifest is None:
            raise CanonicalStoreError(f"staged manifest unreadable: {transaction_id}")
        return self._publish_locked(
            manifest,
            message=message or f"cognitive transaction {transaction_id}",
            update_index=update_index,
            committed=committed,
        )

    def _write_atomic(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f".{path.name}.tmp-{os.getpid()}")
        temp_path.write_text(content, encoding="utf-8")
        _fsync_path(temp_path)
        os.replace(temp_path, path)


def namespace_of_record_id(record_id: str) -> str:
    """entity type 역추적 helper — store 밖에서 ID를 다룰 때 사용한다."""

    return namespace_for(entity_type_for_id(record_id))


__all__ = [
    "CanonicalDigestError",
    "CanonicalStore",
    "CanonicalStoreError",
    "CommitReceipt",
    "DuplicateRecordError",
    "TransactionConflictError",
    "GitCommitError",
    "ManifestEntry",
    "ReferenceValidationError",
    "TransactionManifest",
    "TransactionNotFoundError",
    "canonical_digest",
    "ensure_git_repo",
    "namespace_of_record_id",
    "parse_record_markdown",
    "record_relative_path",
    "render_record_markdown",
]
