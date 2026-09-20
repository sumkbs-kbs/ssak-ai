"""출처 있는 브라우저 작업 기억(task 21) — 무엇을, 얼마나 오래, 누가 물어볼 수 있는가.

task 19 는 "성공은 측정이다" 를, task 20 은 "행동의 운명은 디스크에 남는다" 를 계약으로 만들었다.
이 모듈은 그 다음 질문에 답한다: **그 작업에서 무엇을 기억해도 되는가.**

지키는 것(전부 시험으로 고정돼 있다):

1. **opt-in 이다.** 정책이 꺼져 있으면(`TaskMemoryPolicy.enabled=False`, 기본값) `record` 는
   `MEMORY_DISABLED` 로 거절한다. 사용자가 켜지 않은 브라우징 이력을 수집하지 않는다.
2. **동의 없는 기억은 없다.** 항목은 `MemoryConsent`(누가·언제·어느 범위)를 **필수**로 갖고,
   동의 범위가 그 사이트와 맞지 않으면 `CONSENT_SCOPE_MISMATCH` 다.
3. **본문을 호출자가 쓰지 않는다.** 본문은 이 모듈이 `kind`·`goal`·`evidence`·`steps` 로 **조립**한다.
   그래서 페이지 전문(whole browsing history)이나 폼 입력값이 들어올 통로가 없다 —
   조립에 쓰이는 재료는 전부 한 줄로 잘리고(`clip`), URL 은 조회 문자열을 지운다(`scrub_url`).
4. **저장 전 비밀 검사.** 조립된 본문은 `secret_scanner` 로 스캔하고, 민감 **키 이름**
   (`password`/`token`/`cookie`/`authorization` …)이 재료에 있으면 `SECRET_IN_RECORD` /
   `SECRET_IN_BODY` 로 **거절**한다(가리지 않고 거절한다 — 가린 본문은 나중에 진짜 값인지 알 수 없다).
5. **결말이 상태를 정한다.** `succeeded` → 검증된 절차. `failed`/`partial`/`blocked` → 실패 패턴.
   `cancelled` → 아무것도 측정되지 않았으므로 `NOT_LEARNABLE`. **`unknown_outcome` → 거절**
   (`UNKNOWN_OUTCOME_NOT_LEARNABLE`): 되돌릴 수 없는 효과의 운명을 모르는 상태는 사람이 확인할
   사실이지, "아는 것" 으로 저장할 지식이 아니다.
6. **출처가 없으면 기억이 아니다.** 항목은 `source_task`·저널 확인·`evidence`·기록 시각·
   사이트 범위·만료·동의를 갖는다. 저널을 주면 **그 작업이 저널에 실제로 있는지** 확인한다
   (`SOURCE_TASK_NOT_RECORDED`).
7. **격리는 소유자 단위다.** `recall` 은 호출한 `owner` 의 항목만 본다(다른 사용자·다른 사이트의
   기억은 후보에 들어오지 않는다). 남의 항목을 철회하려 하면 `CROSS_USER_REFUSED` 다.
8. **수정·삭제는 색인과 캐시를 같이 무효화한다.** 색인은 항목 하나만 지운다
   (`VectorStore.delete_embedding` — `clear()` 는 vault 청크까지 지운다). 캐시를 비우지 않으면
   지운 기억이 계속 답변된다.
9. **Git 이력은 소거가 아니다.** 이 기억은 git 밖(data 디렉터리의 SQLite)에만 남기고, vault 에는
   쓰지 않는다. 기존 Git-first vault 의 과거 기록은 파일 삭제·철회로 **소거되지 않는다**(이력에 남는다) —
   그래서 전략은 "나중에 지우는 것" 이 아니라 **애초 민감한 것을 저장하지 않는 것**이다(위 1–7).
   운영자의 마지막 안전망으로 `redact` 경로(값 소거)가 있으나, 그것은 이미 디스크에 있던 값을
   가리는 처방이지 이력을 지우는 처방이 아니다.

기억은 **2차 사용**이다: 같은 사이트에서 확인된 절차를 다음 계획의 참고로 올릴 뿐, 성공 판정은
여전히 페이지 측정(task 19)이 한다. 그래서 힌트는 프롬프트에서 **우리 기억**과 **페이지 데이터**가
다른 블록으로 나뉜다.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
from typing import TYPE_CHECKING, Final, cast, final
from urllib.parse import urlsplit

from antigravity_k.engine.secret_scanner import is_credential_field, scan_for_secrets
from antigravity_k.tools.browser_task_memory_store import (
    CREATE_TABLE_SQL,
    TABLE,
    VECTOR_TABLE,
    integration_purge,
    parse_epoch,
)

if TYPE_CHECKING:
    from antigravity_k.agents.browser_task_loop import TaskOutcome

logger = logging.getLogger(__name__)

#: 기억 항목 하나의 스키마 이름(저장된 JSON 이 어떤 계약으로 쓰였는지 남긴다).
MEMORY_SCHEMA: Final = "ssak.browser.task_memory.v1"

#: SQLite 표·색인 표 이름은 잎 모듈(`browser_task_memory_store`)이 갖는다 — `memory_service` 의
#: 운영 삭제 경로도 같은 상수를 쓰고, 스키마를 아는 곳이 두 곳이면 갈라진다.
_ = TABLE, VECTOR_TABLE, CREATE_TABLE_SQL, integration_purge

#: 거절 코드. 전부 문자열 상수다(호출자가 문자열 추측으로 분기하지 않게).
MEMORY_DISABLED: Final = "MEMORY_DISABLED"
CONSENT_REQUIRED: Final = "CONSENT_REQUIRED"
CONSENT_SCOPE_MISMATCH: Final = "CONSENT_SCOPE_MISMATCH"
CONSENT_WITHDRAWN: Final = "CONSENT_WITHDRAWN"
OWNER_REQUIRED: Final = "OWNER_REQUIRED"
SITE_NOT_ALLOWED: Final = "SITE_NOT_ALLOWED"
SITE_UNKNOWN: Final = "SITE_UNKNOWN"
GOAL_REQUIRED: Final = "GOAL_REQUIRED"
NO_EVIDENCE: Final = "NO_EVIDENCE"
BODY_NOT_MINIMIZED: Final = "BODY_NOT_MINIMIZED"
SECRET_IN_BODY: Final = "SECRET_IN_BODY"
SECRET_IN_RECORD: Final = "SECRET_IN_RECORD"
NOT_LEARNABLE: Final = "NOT_LEARNABLE"
UNKNOWN_OUTCOME_NOT_LEARNABLE: Final = "UNKNOWN_OUTCOME_NOT_LEARNABLE"
SOURCE_TASK_NOT_RECORDED: Final = "SOURCE_TASK_NOT_RECORDED"
NOT_FOUND: Final = "NOT_FOUND"
CROSS_USER_REFUSED: Final = "CROSS_USER_REFUSED"
UNKNOWN_KIND: Final = "UNKNOWN_KIND"

#: 한 줄의 최대 길이(재료는 전부 여기서 잘린다 — 긴 본문이 기억이 되는 것을 막는 첫 관문).
LINE_LIMIT: Final = 200

_WHITESPACE = re.compile(r"\s+")


class MemoryRefusal(RuntimeError):
    """기억에 넣지 않기로 한 이유. `code` 가 판정이고 `reason` 이 사람이 읽는 문장이다."""

    def __init__(self, code: str, reason: str, *, details: Mapping[str, object] | None = None) -> None:
        super().__init__(f"{code}: {reason}")
        self.code = code
        self.reason = reason
        self.details: dict[str, object] = dict(details or {})

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code, "reason": self.reason, **self.details}


class MemoryKind(StrEnum):
    """기억해도 되는 것 세 가지. 이 밖의 종류는 없다 — 브라우징 이력은 종류가 아니다."""

    #: 검증된 절차: 측정으로 확인된 성공 작업의 행동 순서와 사후조건.
    VERIFIED_PROCEDURE = "verified_procedure"
    #: 실패 패턴: 왜 실패했는가(코드·이유·충족되지 않은 조건).
    FAILURE_PATTERN = "failure_pattern"
    #: 검증된 공개 출처 요약: 성공이 확인된 페이지의 출처(주소·사후조건 근거).
    SOURCE_SUMMARY = "source_summary"

    @classmethod
    def parse(cls, value: object) -> MemoryKind:
        try:
            return cls(str(value))
        except ValueError as exc:
            raise MemoryRefusal(UNKNOWN_KIND, f"알 수 없는 기억 종류다: {value!r}") from exc


class ConsentScope(StrEnum):
    """동의 범위. 사이트 하나에 대한 동의와 전체 동의를 구분한다."""

    SITE = "site"
    ALL = "all"


@dataclass(frozen=True)
class MemoryConsent:
    """누가 언제 어느 범위로 기억을 허락했는가. 철회는 `withdrawn_at` 이다."""

    granted_by: str
    granted_at: str
    scope: str = ConsentScope.ALL.value
    scope_value: str = ""
    withdrawn_at: str = ""

    @property
    def withdrawn(self) -> bool:
        return bool(self.withdrawn_at)

    @classmethod
    def for_site(cls, granted_by: str, site: str, *, granted_at: str = "", now: float | None = None) -> MemoryConsent:
        return cls(
            granted_by=granted_by,
            granted_at=granted_at or utc_stamp(now),
            scope=ConsentScope.SITE.value,
            scope_value=site,
        )

    def covers(self, site: str) -> bool:
        if self.withdrawn:
            return False
        if self.scope == ConsentScope.ALL.value:
            return True
        return self.scope == ConsentScope.SITE.value and self.scope_value == site

    def withdraw(self, *, now: float | None = None) -> MemoryConsent:
        return replace(self, withdrawn_at=self.withdrawn_at or utc_stamp(now))

    def to_dict(self) -> dict[str, object]:
        return {
            "granted_by": self.granted_by,
            "granted_at": self.granted_at,
            "scope": self.scope,
            "scope_value": self.scope_value,
            "withdrawn_at": self.withdrawn_at,
            "withdrawn": self.withdrawn,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> MemoryConsent:
        return cls(
            granted_by=str(payload.get("granted_by") or ""),
            granted_at=str(payload.get("granted_at") or ""),
            scope=str(payload.get("scope") or ConsentScope.ALL.value),
            scope_value=str(payload.get("scope_value") or ""),
            withdrawn_at=str(payload.get("withdrawn_at") or ""),
        )


@dataclass(frozen=True)
class TaskMemoryPolicy:
    """기억 정책. 기본은 **꺼짐**이다(opt-in).

    - ``enabled``: 켜야 기억이 남는다. 꺼진 상태에서도 **삭제·만료는 동작한다**
      (지우는 일이 설정에 막히면 그건 망각을 막는 것이다).
    - ``retention_days``: 기록 시각 기준 보관 기간. 만료 뒤에는 `recall` 이 보지 않고 회수가 지운다.
    - ``allow_sites``: 비어 있으면 \"동의한 사이트는 어디든\", 값이 있으면 그 사이트만.
    - ``max_body_chars``: 조립된 본문 상한. 넘으면 잘라내지 않고 **거절**한다(조용한 손실 금지).
    - ``require_consent``: 끄면 동의 없이도 저장한다 — 기본은 참이고, 시험이 이 기본을 지킨다.
    """

    enabled: bool = False
    retention_days: int = 30
    allow_sites: tuple[str, ...] = ()
    max_body_chars: int = 1200
    require_consent: bool = True

    def site_allowed(self, site: str) -> bool:
        return not self.allow_sites or site in self.allow_sites

    def to_dict(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "retention_days": self.retention_days,
            "allow_sites": list(self.allow_sites),
            "max_body_chars": self.max_body_chars,
            "require_consent": self.require_consent,
        }

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> TaskMemoryPolicy:
        """환경 변수만 읽는다 — **없으면 기본값(꺼짐)**이다."""
        source: Mapping[str, str] = os.environ if env is None else env
        if not source.get("AGK_BROWSER_TASK_MEMORY"):
            return cls()
        return cls(
            enabled=_truthy(source.get("AGK_BROWSER_TASK_MEMORY")),
            retention_days=_int_or(source.get("AGK_BROWSER_TASK_MEMORY_DAYS"), 30),
            allow_sites=_sites(source.get("AGK_BROWSER_TASK_MEMORY_SITES")),
            max_body_chars=_int_or(source.get("AGK_BROWSER_TASK_MEMORY_MAX_BODY_CHARS"), 1200),
            require_consent=not _falsey(source.get("AGK_BROWSER_TASK_MEMORY_REQUIRE_CONSENT")),
        )

    @classmethod
    def load(cls, env: Mapping[str, str] | None = None) -> TaskMemoryPolicy:
        """설정 파일(yaml) → 환경 변수 순서로 덮어쓴다(기존 관례: env > yaml)."""
        source: Mapping[str, str] = os.environ if env is None else env
        base = cls()
        try:
            from antigravity_k.config import config as app_config

            section = getattr(app_config, "browser_task_memory", None)
            if section is not None:
                base = cls(
                    enabled=bool(getattr(section, "enabled", False)),
                    retention_days=int(getattr(section, "retention_days", 30)),
                    allow_sites=tuple(str(item) for item in getattr(section, "allow_sites", ()) or ()),
                    max_body_chars=int(getattr(section, "max_body_chars", 1200)),
                    require_consent=bool(getattr(section, "require_consent", True)),
                )
        except Exception:  # 설정이 없거나 못 읽으면 기본값으로 간다(기억은 조용히 꺼진 채 돈다)
            logger.debug("browser task memory policy fell back to defaults", exc_info=True)
        if "AGK_BROWSER_TASK_MEMORY" in source:
            return cls.from_env(source)
        return base


@dataclass(frozen=True)
class TaskMemoryEntry:
    """기억 항목 하나. 출처·범위·만료·동의가 **본문과 같은 무게**로 저장된다."""

    entry_id: str
    kind: MemoryKind
    owner: str
    origin: str
    origin_url: str
    goal: str
    body: str
    source_task: str
    evidence: tuple[str, ...]
    steps: tuple[str, ...]
    consent: MemoryConsent
    minimized: tuple[str, ...]
    created_at: str
    updated_at: str
    expires_at: str
    revoked_at: str = ""
    revoke_reason: str = ""
    schema: str = MEMORY_SCHEMA

    @property
    def revoked(self) -> bool:
        return bool(self.revoked_at)

    def is_expired(self, now: float) -> bool:
        return parse_epoch(self.expires_at) <= now

    def expired_or_revoked(self, now: float) -> bool:
        return self.revoked or self.is_expired(now)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "entry_id": self.entry_id,
            "kind": self.kind.value,
            "owner": self.owner,
            "origin": self.origin,
            "origin_url": self.origin_url,
            "goal": self.goal,
            "body": self.body,
            "source_task": self.source_task,
            "evidence": list(self.evidence),
            "steps": list(self.steps),
            "consent": self.consent.to_dict(),
            "minimized": list(self.minimized),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "expires_at": self.expires_at,
            "revoked_at": self.revoked_at,
            "revoke_reason": self.revoke_reason,
        }

    def to_hint(self) -> str:
        """계획 프롬프트에 넣는 한 줄. 출처와 종류를 **항상** 앞에 붙인다(기억은 주장이 아니다)."""
        proof = self.evidence[0] if self.evidence else ""
        tail = f" — {proof}" if proof else ""
        return clip(f"[{self.kind.value}·{self.origin}] {self.goal}{tail}", LINE_LIMIT)


# ── 재료 다듬기(최소화) ──────────────────────────────────────────────────────


def clip(value: object, limit: int = LINE_LIMIT) -> str:
    """한 줄로 눌러 자른다 — 기억에 들어가는 모든 문자열이 지나는 관문이다."""
    text = _WHITESPACE.sub(" ", str(value or "")).strip()
    return text if len(text) <= limit else text[: max(0, limit - 1)] + "…"


def scrub_url(url: str, limit: int = 300) -> str:
    """조회 문자열·조각을 지운 주소. 조회 문자열은 토큰을 나르는 자리다."""
    raw = str(url or "").strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
    except ValueError:
        return ""
    if not parts.scheme or not parts.netloc:
        return clip(raw, limit)
    path = parts.path or "/"
    return clip(f"{parts.scheme}://{parts.netloc}{path}", limit)


def site_of(url: str) -> str:
    """사이트 범위 = 출처(스킴+호스트+포트). 경로·조회 문자열은 범위가 아니다."""
    raw = str(url or "").strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
    except ValueError:
        return ""
    if not parts.scheme or not parts.netloc:
        return ""
    return f"{parts.scheme}://{parts.netloc}".lower()


def utc_stamp(now: float | None = None) -> str:
    seconds = time.time() if now is None else now
    return datetime.fromtimestamp(seconds, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _falsey(value: object) -> bool:
    return str(value or "").strip().lower() in {"0", "false", "no", "off"}


def _int_or(value: object, default: int) -> int:
    text = str(value or "").strip()
    if not text:
        return default
    try:
        return int(text)
    except ValueError:
        return default


def _sites(value: object) -> tuple[str, ...]:
    return tuple(item.strip() for item in str(value or "").split(",") if item.strip())


def reject_secret_keys(payload: Mapping[str, object], *, where: str) -> None:
    """민감 **키 이름**이 기록에 있으면 거절한다(값은 보지 않는다).

    task 20 의 저널과 같은 규칙이다: 값이 비밀이면 키 이름만으로도 충분히 위험하고, 중첩된
    metadata 안에 숨어 있는 경우가 실제로 있었다.
    """
    for key, value in payload.items():
        if is_credential_field(key):
            raise MemoryRefusal(SECRET_IN_RECORD, f"{where} 에 민감 키가 있다: {key}")
        if isinstance(value, Mapping):
            reject_secret_keys(cast(Mapping[str, object], value), where=f"{where}.{key}")
        elif isinstance(value, (list, tuple)):
            for index, item in enumerate(cast(Sequence[object], value)):
                if isinstance(item, Mapping):
                    reject_secret_keys(cast(Mapping[str, object], item), where=f"{where}.{key}[{index}]")


def assert_no_secrets(text: str, *, where: str) -> None:
    """조립된 본문을 저장 **전에** 스캔한다. 하나라도 걸리면 거절이다(가리지 않는다)."""
    matches = scan_for_secrets(text)
    if matches:
        names = sorted({match.pattern for match in matches})
        raise MemoryRefusal(SECRET_IN_BODY, f"{where} 에 비밀로 보이는 값이 있다", details={"patterns": names})


# ── 저장소 ──────────────────────────────────────────────────────────────────


@final
class BrowserTaskMemory:
    """출처 있는 브라우저 작업 기억의 **한 곳**(저장·검색·철회·만료).

    메모리 서비스와 **같은 DB**를 쓰고, 색인은 그 서비스의 VectorStore 를 빌려 쓴다(표 이름으로 구분).
    색인이 없으면(chromadb 미설치) 키워드 검색으로 물러선다 — 기억이 사라지지는 않는다.
    """

    def __init__(
        self,
        service: object | None = None,
        *,
        policy: TaskMemoryPolicy | None = None,
        db_path: str | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._service = service if service is not None else _default_service()
        self.policy = policy if policy is not None else TaskMemoryPolicy.load()
        resolved = db_path or str(getattr(self._service, "db_path", "") or "")
        if not resolved:
            raise MemoryRefusal(SITE_UNKNOWN, "기억 저장소 경로를 알 수 없다")
        self.db_path = resolved
        self._clock = clock or time.time
        self._cache: dict[tuple[object, ...], tuple[TaskMemoryEntry, ...]] = {}
        self._init_db()

    # ── 내부 ──
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        _ = conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            _ = conn.execute(CREATE_TABLE_SQL)
            _ = conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_owner ON {TABLE} (owner, origin)")
            conn.commit()

    @property
    def _vector_store(self) -> object | None:
        store = getattr(self._service, "vector_store", None)
        return store

    def _embed(self, row_id: int, entry: TaskMemoryEntry) -> bool:
        store = self._vector_store
        embed = getattr(store, "store_embedding", None)
        if not callable(embed):
            return False
        try:
            _ = embed(VECTOR_TABLE, row_id, f"{entry.kind.value} {entry.origin} {entry.goal} {entry.body}")
            return True
        except Exception:  # 색인 실패가 기억 저장을 막지는 않는다(키워드로도 찾을 수 있다)
            logger.exception("browser task memory embedding failed")
            return False

    def _unembed(self, row_id: int) -> bool:
        store = self._vector_store
        drop = getattr(store, "delete_embedding", None)
        if not callable(drop):
            return False
        try:
            return bool(drop(VECTOR_TABLE, row_id))
        except Exception:
            logger.exception("browser task memory embedding removal failed")
            return False

    def _invalidate_cache(self) -> None:
        self._cache.clear()

    def _now(self, now: float | None) -> float:
        return self._clock() if now is None else now

    # ── 쓰기 ──
    def record(
        self,
        kind: MemoryKind | str,
        *,
        owner: str,
        goal: str,
        evidence: Sequence[str],
        source_task: str,
        consent: MemoryConsent | None,
        origin_url: str = "",
        origin: str = "",
        steps: Sequence[str] = (),
        now: float | None = None,
    ) -> TaskMemoryEntry:
        """기억 하나를 남긴다. 거절 조건은 전부 `MemoryRefusal` 로 나온다(부분 저장 없음).

        본문은 여기서 조립한다 — 호출자가 자유 문자열을 넣는 자리가 없다:
        `kind` · `goal` · `evidence` 한 줄들 · `steps` 한 줄들.
        """
        policy = self.policy
        if not policy.enabled:
            raise MemoryRefusal(MEMORY_DISABLED, "브라우저 작업 기억이 꺼져 있다(opt-in)")
        moment = self._now(now)
        owner_value = str(owner or "").strip()
        if not owner_value:
            raise MemoryRefusal(OWNER_REQUIRED, "기억에는 소유자가 있어야 한다(격리 단위다)")
        kind_value = MemoryKind.parse(kind)
        goal_value = clip(goal)
        if not goal_value:
            raise MemoryRefusal(GOAL_REQUIRED, "목표 없는 기억은 재사용할 수 없다")
        site = (origin or site_of(origin_url)).strip().lower()
        if not site:
            raise MemoryRefusal(SITE_UNKNOWN, "어느 사이트의 기억인지 알 수 없다")
        if policy.require_consent:
            if consent is None:
                raise MemoryRefusal(CONSENT_REQUIRED, "동의 없는 기억은 저장하지 않는다")
            if consent.withdrawn:
                raise MemoryRefusal(CONSENT_WITHDRAWN, "철회된 동의로는 기억을 남기지 않는다")
            if not consent.covers(site):
                raise MemoryRefusal(CONSENT_SCOPE_MISMATCH, f"동의 범위가 이 사이트가 아니다: {site}")
        if not policy.site_allowed(site):
            raise MemoryRefusal(SITE_NOT_ALLOWED, f"정책이 이 사이트를 허용하지 않는다: {site}")

        evidence_lines = _record_lines(evidence, where="evidence")
        step_lines = _record_lines(steps, where="steps")
        if kind_value is not MemoryKind.FAILURE_PATTERN and not evidence_lines:
            raise MemoryRefusal(NO_EVIDENCE, "검증된 기억에는 근거가 있어야 한다(성공 주장 금지)")

        body = _assemble_body(kind_value, goal_value, evidence_lines, step_lines)
        if len(body) > policy.max_body_chars:
            raise MemoryRefusal(
                BODY_NOT_MINIMIZED,
                "조립된 본문이 상한을 넘는다 — 근거를 줄여 최소화하라(잘라내지 않는다)",
                details={"chars": len(body), "limit": policy.max_body_chars},
            )
        assert_no_secrets(body, where="기억 본문")
        source = clip(source_task, 120) or f"adhoc:{utc_stamp(now)}"
        minimized = _minimization_notes(origin_url, len(evidence_lines), len(step_lines))
        reject_secret_keys(
            {
                "kind": kind_value.value,
                "goal": goal_value,
                "origin": site,
                "origin_url": scrub_url(origin_url),
                "source_task": source,
                "body": body,
                "steps": list(step_lines),
                "evidence": list(evidence_lines),
                "consent": (consent.to_dict() if consent is not None else {}),
                "minimized": list(minimized),
            },
            where="기억 항목",
        )

        stamp = utc_stamp(moment)
        expires = utc_stamp(moment + policy.retention_days * 86400)
        dedupe_key = _dedupe_key(owner_value, site, kind_value, goal_value)
        with self._connect() as conn:
            existing = conn.execute(
                f"SELECT id, created_at, entry_id FROM {TABLE} WHERE dedupe_key = ?", (dedupe_key,)
            ).fetchone()
            if existing is None:
                # id 는 중복 키의 앞부분이다. 같은 사이트·같은 목표를 **다시** 확인해도 앞선 철회 기록과
                # 충돌하지 않게, 이미 쓰인 접두사면 번호를 붙인다(첫 기억은 번호 없는 id 를 갖는다).
                base_id = f"btm_{dedupe_key[:16]}"
                taken = conn.execute(f"SELECT COUNT(*) FROM {TABLE} WHERE entry_id GLOB ?", (base_id + "*",)).fetchone()
                seen = int(taken[0]) if taken is not None else 0
                entry_id = base_id if seen == 0 else f"{base_id}_{seen + 1}"
                cursor = conn.execute(
                    f"INSERT INTO {TABLE} (entry_id, dedupe_key, kind, owner, origin, origin_url, goal, body, steps,"
                    f" evidence, consent, minimized, source_task, created_at, updated_at, expires_at, revoked_at,"
                    f" revoke_reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', '')",
                    (
                        entry_id,
                        dedupe_key,
                        kind_value.value,
                        owner_value,
                        site,
                        scrub_url(origin_url),
                        goal_value,
                        body,
                        json.dumps(list(step_lines), ensure_ascii=False),
                        json.dumps(list(evidence_lines), ensure_ascii=False),
                        json.dumps(consent.to_dict() if consent is not None else {}, ensure_ascii=False),
                        json.dumps(list(minimized), ensure_ascii=False),
                        source,
                        stamp,
                        stamp,
                        expires,
                    ),
                )
                row_id = int(cursor.lastrowid or 0)
                created = stamp
            else:
                row_id = int(existing["id"])
                created = str(existing["created_at"])
                entry_id = str(existing["entry_id"])  # 덮어쓰기는 **같은 기억**이다(id 를 바꾸지 않는다)
                # 같은 절차를 다시 확인했다 = **덮어쓰기**다(무한히 쌓지 않는다). 색인도 같은 id 로 덮어쓴다.
                _ = conn.execute(
                    f"UPDATE {TABLE} SET origin_url = ?, body = ?, steps = ?, evidence = ?, consent = ?, minimized = ?,"
                    f" source_task = ?, updated_at = ?, expires_at = ? WHERE dedupe_key = ?",
                    (
                        scrub_url(origin_url),
                        body,
                        json.dumps(list(step_lines), ensure_ascii=False),
                        json.dumps(list(evidence_lines), ensure_ascii=False),
                        json.dumps(consent.to_dict() if consent is not None else {}, ensure_ascii=False),
                        json.dumps(list(minimized), ensure_ascii=False),
                        source,
                        stamp,
                        expires,
                        dedupe_key,
                    ),
                )
            conn.commit()
        entry = TaskMemoryEntry(
            entry_id=entry_id,
            kind=kind_value,
            owner=owner_value,
            origin=site,
            origin_url=scrub_url(origin_url),
            goal=goal_value,
            body=body,
            source_task=source,
            evidence=evidence_lines,
            steps=step_lines,
            consent=consent or MemoryConsent(granted_by="", granted_at=stamp, scope=ConsentScope.ALL.value),
            minimized=minimized,
            created_at=created,
            updated_at=stamp,
            expires_at=expires,
        )
        _ = self._embed(row_id, entry)
        self._invalidate_cache()
        return entry

    def record_from_outcome(
        self,
        outcome: TaskOutcome,
        *,
        owner: str,
        source_task: str,
        consent: MemoryConsent | None = None,
        journal: object | None = None,
        now: float | None = None,
    ) -> TaskMemoryEntry:
        """작업 결말에서 기억을 만든다 — **결말이 기억의 종류를 정한다**.

        - `succeeded` → 검증된 절차 + (같은 페이지의) 출처 요약
        - `failed`/`partial`/`blocked` → 실패 패턴
        - `cancelled` → 거절(`NOT_LEARNABLE`): 측정된 것이 없다
        - `unknown_outcome` → 거절(`UNKNOWN_OUTCOME_NOT_LEARNABLE`): 사람이 확인할 사실이다

        페이지 전문(`final_text`)과 폼 입력값은 **쓰지 않는다**. 근거로 쓰는 것은 사후조건 판정의
        관측 조각이고, 그것도 한 줄로 잘린다.
        """
        from antigravity_k.agents.browser_task_loop import TaskStatus

        status = outcome.status
        site = site_of(outcome.final_url)
        if not site:
            raise MemoryRefusal(SITE_UNKNOWN, "결말에 사이트가 없다 — 어디서 배운 것인지 말할 수 없다")
        if journal is not None:
            _require_journal_task(journal, source_task)
        code_line = f"code={clip(outcome.code, 60)}"
        if status is TaskStatus.UNKNOWN_OUTCOME:
            raise MemoryRefusal(
                UNKNOWN_OUTCOME_NOT_LEARNABLE,
                "결과를 모르는 작업은 지식이 아니다 — 사람이 확인하기 전까지는 아는 것으로 저장하지 않는다",
                details={"code": outcome.code},
            )
        if status is TaskStatus.CANCELLED:
            raise MemoryRefusal(NOT_LEARNABLE, "취소된 작업에서 배울 것은 없다(측정된 것이 없다)")
        if status is TaskStatus.SUCCEEDED:
            verified = tuple(
                f"✓ {clip(item.description, 80)} — 관측 {clip(item.observed, 80)}"
                for item in outcome.postconditions
                if item.verified
            )
            if not verified:
                raise MemoryRefusal(NO_EVIDENCE, "성공으로 끝났지만 검증된 사후조건이 없다")
            return self.record(
                MemoryKind.VERIFIED_PROCEDURE,
                owner=owner,
                goal=outcome.goal,
                evidence=(code_line, *verified),
                steps=_steps_from_outcome(outcome),
                source_task=source_task,
                consent=consent,
                origin_url=outcome.final_url,
                origin=site,
                now=now,
            )
        missing = tuple(
            f"✗ {clip(item.description, 80)} — 기대 {clip(item.expected, 60)} / 관측 {clip(item.observed, 80)}"
            for item in outcome.postconditions
            if not item.verified
        )
        reason = f"reason={clip(outcome.reason, 160)}" if outcome.reason else ""
        blocked = f"blocked={clip(outcome.blocked_kind, 40)}" if outcome.blocked_kind else ""
        return self.record(
            MemoryKind.FAILURE_PATTERN,
            owner=owner,
            goal=outcome.goal,
            evidence=tuple(line for line in (code_line, blocked, reason, *missing) if line),
            steps=_steps_from_outcome(outcome),
            source_task=source_task,
            consent=consent,
            origin_url=outcome.final_url,
            origin=site,
            now=now,
        )

    # ── 읽기 ──
    def recall(
        self,
        query: str,
        *,
        owner: str,
        origin: str = "",
        kind: MemoryKind | str | None = None,
        limit: int = 5,
        now: float | None = None,
    ) -> list[TaskMemoryEntry]:
        """이 소유자·이 사이트의 기억을 찾는다. 만료·철회된 항목은 **후보가 아니다**.

        검색은 색인이 있으면 벡터 유사도로, 없으면 키워드 일치로 한다(둘 다 같은 표를 본다).
        결과는 캐시되지만, 쓰기·철회·수정이 있으면 캐시가 즉시 비워진다.
        """
        owner_value = str(owner or "").strip()
        if not owner_value:
            raise MemoryRefusal(OWNER_REQUIRED, "기억을 물어볼 소유자를 지정해야 한다")
        site = str(origin or "").strip().lower()
        kind_value = MemoryKind.parse(kind) if kind is not None else None
        moment = self._now(now)
        key = (owner_value, site, kind_value.value if kind_value else "", clip(query, 200), int(limit))
        cached = self._cache.get(key)
        if cached is not None:
            # 캐시는 **시간을 얼리지 않는다**: 담아 둔 사이에 만료된 항목은 돌려주지 않고,
            # 하나라도 걸리면 캐시를 버리고 다시 계산한다(회수 = 지금 살아 있는 것만).
            live = [entry for entry in cached if not entry.expired_or_revoked(moment)]
            if len(live) == len(cached):
                return live
            self._cache.pop(key, None)
        candidates = [
            (row_id, entry)
            for row_id, entry in self._load_rows(owner=owner_value, origin=site, kind=kind_value)
            if not entry.expired_or_revoked(moment)
        ]
        ranked = self._rank(candidates, query, limit=limit)
        self._cache[key] = tuple(ranked)
        return ranked

    def hints(
        self, query: str, *, owner: str, origin: str, limit: int = 3, now: float | None = None
    ) -> tuple[str, ...]:
        """계획 프롬프트에 넣을 힌트 줄. 기억이 꺼져 있으면 **빈 튜플**이다(조용히 아무 일도 안 한다)."""
        if not self.policy.enabled:
            return ()
        try:
            entries = self.recall(
                query, owner=owner, origin=origin, kind=MemoryKind.VERIFIED_PROCEDURE, limit=limit, now=now
            )
        except MemoryRefusal:
            logger.debug("browser task memory recall refused", exc_info=True)
            return ()
        return tuple(entry.to_hint() for entry in entries)

    def export(self, *, owner: str, include_revoked: bool = False) -> list[dict[str, object]]:
        """사람이 감사할 수 있는 형태(출처·동의·만료 포함)."""
        entries = self._load(owner=owner, origin="", kind=None)
        if not include_revoked:
            moment = self._now(None)
            entries = [entry for entry in entries if not entry.expired_or_revoked(moment)]
        return [entry.to_dict() for entry in entries]

    def stats(self, *, owner: str = "", now: float | None = None) -> dict[str, object]:
        entries = self._load(owner=owner, origin="", kind=None)
        moment = self._now(now)
        live = [entry for entry in entries if not entry.expired_or_revoked(moment)]
        by_kind: dict[str, int] = {}
        for entry in live:
            by_kind[entry.kind.value] = by_kind.get(entry.kind.value, 0) + 1
        return {
            "enabled": self.policy.enabled,
            "retention_days": self.policy.retention_days,
            "total": len(entries),
            "live": len(live),
            "expired": sum(1 for entry in entries if entry.is_expired(moment) and not entry.revoked),
            "revoked": sum(1 for entry in entries if entry.revoked),
            "by_kind": by_kind,
            "sites": sorted({entry.origin for entry in live}),
        }

    def _load_rows(self, *, owner: str, origin: str, kind: MemoryKind | None) -> list[tuple[int, TaskMemoryEntry]]:
        """행 id 와 항목을 함께 준다(색인에서 빼려면 숫자 id 가 필요하다)."""
        clauses = []
        params: list[object] = []
        if owner:
            clauses.append("owner = ?")
            params.append(owner)
        if origin:
            clauses.append("origin = ?")
            params.append(origin)
        if kind is not None:
            clauses.append("kind = ?")
            params.append(kind.value)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(f"SELECT * FROM {TABLE}{where} ORDER BY updated_at DESC", params).fetchall()
        return [(int(row["id"]), _entry_from_row(row)) for row in rows]

    def _load(self, *, owner: str, origin: str, kind: MemoryKind | None) -> list[TaskMemoryEntry]:
        return [entry for _, entry in self._load_rows(owner=owner, origin=origin, kind=kind)]

    def _row_id(self, entry_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(f"SELECT id FROM {TABLE} WHERE entry_id = ?", (entry_id,)).fetchone()
        return int(row["id"]) if row is not None else 0

    def _rank(
        self, candidates: Sequence[tuple[int, TaskMemoryEntry]], query: str, *, limit: int
    ) -> list[TaskMemoryEntry]:
        if not candidates:
            return []
        if not clip(query):
            return [entry for _, entry in candidates[:limit]]
        by_id = {row_id: entry for row_id, entry in candidates}
        store = self._vector_store
        search = getattr(store, "search_similar", None)
        if callable(search):
            try:
                hits = search(query, VECTOR_TABLE, top_k=max(limit * 4, 8))
            except Exception:
                hits = []
            ordered: list[TaskMemoryEntry] = []
            for hit in cast(Iterable[Mapping[str, object]], hits or []):
                entry = by_id.get(_as_int(hit.get("source_id")))
                if entry is not None and entry not in ordered:
                    ordered.append(entry)
            if ordered:
                return ordered[:limit]
        tokens = [token for token in clip(query, 200).lower().split(" ") if len(token) >= 2]
        scored: list[tuple[int, TaskMemoryEntry]] = []
        for _, entry in candidates:
            haystack = f"{entry.goal} {entry.body}".lower()
            score = sum(1 for token in tokens if token in haystack)
            if score:
                scored.append((score, entry))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        # 맞는 것이 없으면 **빈손으로 돌아간다** — 무관한 기억을 힌트로 올리면 다음 계획이 그쪽으로 샌다.
        return [entry for _, entry in scored[:limit]]

    # ── 고치고 지우기 ──
    def revoke(self, entry_id: str, *, owner: str, reason: str = "", now: float | None = None) -> TaskMemoryEntry:
        """기억 하나를 지운다. 행은 남기고 **철회로 표시**한다(감사 가능한 삭제).

        색인에서 그 항목만 빼고 캐시를 비운다 — 둘 중 하나만 하면 지운 기억이 계속 답변된다.
        철회된 항목의 중복 키는 바꿔 둔다: 다음 실행이 **같은 목표를 다시 확인하면** 그것은 새 기억이고,
        한번 지운 기억을 조용히 되살리는 것과는 다른 일이다.
        """
        row_id = self._require_entry(entry_id, owner=owner)
        current = self._entry_by_id(entry_id)
        if current.revoked:
            return current
        stamp = utc_stamp(self._now(now))
        with self._connect() as conn:
            _ = conn.execute(
                f"UPDATE {TABLE} SET revoked_at = ?, revoke_reason = ?, dedupe_key = dedupe_key || '#revoked'"
                f" WHERE entry_id = ?",
                (stamp, clip(reason, 200), entry_id),
            )
            conn.commit()
        _ = self._unembed(row_id)
        self._invalidate_cache()
        return replace(current, revoked_at=stamp, revoke_reason=clip(reason, 200))

    def update(
        self,
        entry_id: str,
        *,
        owner: str,
        evidence: Sequence[str] | None = None,
        steps: Sequence[str] | None = None,
        now: float | None = None,
    ) -> TaskMemoryEntry:
        """근거·절차를 고친다. 고친 본문은 **다시 검사**하고(비밀·최소화) 색인을 다시 쓴다."""
        _ = self._require_entry(entry_id, owner=owner)
        current = self._entry_by_id(entry_id)
        if current.revoked:
            raise MemoryRefusal(CONSENT_WITHDRAWN, "철회된 기억은 고칠 수 없다")
        evidence_lines = _record_lines(tuple(evidence) if evidence is not None else current.evidence, where="evidence")
        step_lines = _record_lines(tuple(steps) if steps is not None else current.steps, where="steps")
        body = _assemble_body(current.kind, current.goal, evidence_lines, step_lines)
        if len(body) > self.policy.max_body_chars:
            raise MemoryRefusal(
                BODY_NOT_MINIMIZED,
                "고친 본문이 상한을 넘는다",
                details={"chars": len(body), "limit": self.policy.max_body_chars},
            )
        assert_no_secrets(body, where="기억 본문")
        stamp = utc_stamp(self._now(now))
        with self._connect() as conn:
            _ = conn.execute(
                f"UPDATE {TABLE} SET body = ?, evidence = ?, steps = ?, updated_at = ? WHERE entry_id = ?",
                (
                    body,
                    json.dumps(list(evidence_lines), ensure_ascii=False),
                    json.dumps(list(step_lines), ensure_ascii=False),
                    stamp,
                    entry_id,
                ),
            )
            conn.commit()
        refreshed = self._entry_by_id(entry_id)
        row_id = self._row_id(entry_id)
        if row_id:
            _ = self._embed(row_id, refreshed)  # 임베딩은 upsert 라 같은 id 를 덮어쓴다
        self._invalidate_cache()
        return refreshed

    def withdraw_consent(self, *, owner: str, origin: str = "", reason: str = "", now: float | None = None) -> int:
        """동의를 철회한다: 그 범위의 기억을 **전부** 철회한다(동의 없이 남는 기억은 없다)."""
        moment = self._now(now)
        entries = [
            entry for entry in self._load(owner=owner, origin=origin, kind=None) if not entry.expired_or_revoked(moment)
        ]
        for entry in entries:
            _ = self.revoke(entry.entry_id, owner=owner, reason=reason or "consent withdrawn", now=moment)
        return len(entries)

    def forget_owner(self, owner: str, *, reason: str = "", now: float | None = None) -> int:
        """소유자 단위 삭제(사용자 요청·계정 정리)."""
        return self.withdraw_consent(owner=owner, reason=reason or "forgotten", now=now)

    def apply_retention(self, *, now: float | None = None) -> int:
        """만료됐거나 철회된 기억을 지운다(행 + 색인). 정책이 꺼져 있어도 동작한다 — 망각은 설정에 막히지 않는다."""
        moment = self._now(now)
        removed = 0
        for row_id, entry in self._load_rows(owner="", origin="", kind=None):
            if entry.expired_or_revoked(moment):
                with self._connect() as conn:
                    _ = conn.execute(f"DELETE FROM {TABLE} WHERE entry_id = ?", (entry.entry_id,))
                    conn.commit()
                _ = self._unembed(row_id)
                removed += 1
        if removed:
            self._invalidate_cache()
        return removed

    def _entry_by_id(self, entry_id: str) -> TaskMemoryEntry:
        with self._connect() as conn:
            row = conn.execute(f"SELECT * FROM {TABLE} WHERE entry_id = ?", (entry_id,)).fetchone()
        if row is None:
            raise MemoryRefusal(NOT_FOUND, f"그런 기억이 없다: {entry_id}")
        return _entry_from_row(row)

    def _require_entry(self, entry_id: str, *, owner: str) -> int:
        with self._connect() as conn:
            row = conn.execute(f"SELECT id, owner FROM {TABLE} WHERE entry_id = ?", (entry_id,)).fetchone()
        if row is None:
            raise MemoryRefusal(NOT_FOUND, f"그런 기억이 없다: {entry_id}")
        if str(row["owner"]) != str(owner or ""):
            raise MemoryRefusal(CROSS_USER_REFUSED, "다른 소유자의 기억은 고치거나 지울 수 없다")
        return int(row["id"])


def _require_journal_task(journal: object, task_id: str) -> None:
    """출처는 **저널에 실제로 있어야** 한다 — 없는 실행을 가리키는 기억은 검증할 수 없다."""
    probe = getattr(journal, "resume_plan", None)
    if not callable(probe):
        return
    try:
        plan = probe(task_id)
    except Exception as exc:
        raise MemoryRefusal(SOURCE_TASK_NOT_RECORDED, f"저널을 읽을 수 없다: {exc}") from exc
    if plan is None:
        raise MemoryRefusal(SOURCE_TASK_NOT_RECORDED, f"저널에 그 작업이 없다: {task_id}")


def _steps_from_outcome(outcome: TaskOutcome) -> tuple[str, ...]:
    """절차 요약. **입력값은 담지 않는다**(무엇을 눌렀는가·어디로 갔는가까지만)."""
    lines = []
    for step in outcome.steps:
        if step.rejected:
            lines.append(f"{step.index}. {step.action} {clip(step.target, 60)} → 거절({clip(step.rejected, 40)})")
            continue
        mark = "효과확인" if step.effect_verified else ("수행" if step.performed else "미수행")
        lines.append(f"{step.index}. {step.action} {clip(step.target, 60)} → {mark}")
    return tuple(lines)


def _record_lines(values: Sequence[str], *, where: str) -> tuple[str, ...]:
    """재료 한 줄을 기억에 넣을 수 있게 다듬는다: 한 줄로 누르고, 비밀이 있으면 거절한다."""
    lines: list[str] = []
    for value in values:
        line = clip(value)
        if not line:
            continue
        assert_no_secrets(line, where=where)
        lines.append(line)
    return tuple(lines)


def _assemble_body(kind: MemoryKind, goal: str, evidence: Sequence[str], steps: Sequence[str]) -> str:
    """본문 조립은 여기 한 곳이다 — 이 함수 밖에서 기억 본문이 만들어지지 않는다."""
    parts = [f"[{kind.value}] {goal}"]
    if evidence:
        parts.append("근거:")
        parts.extend(f"  - {line}" for line in evidence)
    if steps:
        parts.append("절차:")
        parts.extend(f"  - {line}" for line in steps)
    return "\n".join(parts)


def _minimization_notes(origin_url: str, evidence_count: int, step_count: int) -> tuple[str, ...]:
    notes = [
        "페이지 본문·전체 이력은 저장하지 않는다",
        "폼 입력값·쿠키·비밀은 저장하지 않는다",
        "주소에서 조회 문자열을 지운다",
    ]
    if origin_url and scrub_url(origin_url) != str(origin_url).strip():
        notes.append("조회 문자열이 실제로 제거됐다")
    notes.append(f"근거 {evidence_count}줄 · 절차 {step_count}줄")
    return tuple(notes)


def _dedupe_key(owner: str, site: str, kind: MemoryKind, goal: str) -> str:
    raw = f"{owner}|{site}|{kind.value}|{goal.lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _as_int(value: object, default: int = 0) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _entry_from_row(row: sqlite3.Row) -> TaskMemoryEntry:
    return TaskMemoryEntry(
        entry_id=str(row["entry_id"]),
        kind=MemoryKind.parse(str(row["kind"])),
        owner=str(row["owner"]),
        origin=str(row["origin"]),
        origin_url=str(row["origin_url"]),
        goal=str(row["goal"]),
        body=str(row["body"]),
        source_task=str(row["source_task"]),
        evidence=tuple(_json_list(row["evidence"])),
        steps=tuple(_json_list(row["steps"])),
        consent=MemoryConsent.from_dict(_json_map(row["consent"])),
        minimized=tuple(_json_list(row["minimized"])),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        expires_at=str(row["expires_at"]),
        revoked_at=str(row["revoked_at"] or ""),
        revoke_reason=str(row["revoke_reason"] or ""),
    )


def _json_list(value: object) -> list[str]:
    try:
        decoded = json.loads(str(value or "[]"))
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(decoded, list):
        return []
    return [str(item) for item in cast(list[object], decoded)]


def _json_map(value: object) -> dict[str, object]:
    try:
        decoded = json.loads(str(value or "{}"))
    except (json.JSONDecodeError, ValueError):
        return {}
    return cast("dict[str, object]", decoded) if isinstance(decoded, dict) else {}


def _default_service() -> object:
    from antigravity_k.knowledge.memory_service import MemoryService

    return MemoryService()


def memory_db_path(env: Mapping[str, str] | None = None) -> str:
    """이 모듈이 쓰는 DB 파일 경로(메모리 서비스와 같은 파일)."""
    source: Mapping[str, str] = os.environ if env is None else env
    configured = str(source.get("AGK_MEMORY_DB_PATH", "") or "").strip()
    if configured:
        return configured
    return str(getattr(_default_service(), "db_path", ""))


__all__ = [
    "BODY_NOT_MINIMIZED",
    "CONSENT_REQUIRED",
    "CONSENT_SCOPE_MISMATCH",
    "CONSENT_WITHDRAWN",
    "CROSS_USER_REFUSED",
    "MEMORY_DISABLED",
    "MEMORY_SCHEMA",
    "NOT_FOUND",
    "NOT_LEARNABLE",
    "OWNER_REQUIRED",
    "SECRET_IN_BODY",
    "SECRET_IN_RECORD",
    "SITE_NOT_ALLOWED",
    "SITE_UNKNOWN",
    "SOURCE_TASK_NOT_RECORDED",
    "TABLE",
    "UNKNOWN_KIND",
    "UNKNOWN_OUTCOME_NOT_LEARNABLE",
    "VECTOR_TABLE",
    "BrowserTaskMemory",
    "ConsentScope",
    "MemoryConsent",
    "MemoryKind",
    "MemoryRefusal",
    "TaskMemoryEntry",
    "TaskMemoryPolicy",
    "clip",
    "integration_purge",
    "memory_db_path",
    "reject_secret_keys",
    "scrub_url",
    "site_of",
    "utc_stamp",
]
