"""flush 배치의 계약을 고정한다 — **결정적 예산**과 **바뀌지 않은 내구성 계약**.

계약(이 시험이 지키는 문장):
  1. append 1회는 저널 꼬리를 **한 번만** 읽는다(종전 3회 · 약 113 KiB 재읽기 — 실측).
  2. append 1회의 `os.fsync` 는 **정확히 1회**다(ADR-DAT-02 §2 “커밋 = 줄 + fsync”). 배치는 이걸 못 바꾼다.
  3. `revision`/`seq` 는 append 1회에 정확히 1씩 오르고, 미결 꼬리는 커밋 **전에** 옮겨진다.
  4. 꼬리 기억은 **임계 구역 밖으로 새지 않는다** — 구역이 바뀌면 버린다(낡은 seq 판정 금지).
  5. view 쓰기가 실패해도 저널 커밋은 살아남는다(종전 계약 그대로).

실행:
  기본은 저장소 루트의 `src/` 를 검사한다. 미러 리허설은 `NX10_FLUSH_TREE=<트리>` 로 대상을 바꾼다:
  `NX10_FLUSH_TREE=/tmp/mirror .venv/bin/python -m pytest docs/qa/2026-09-16-followup/nx10/fsync/test_flush_budget_contract.py -q`
검사 대상 트리를 **명시적으로** 고르는 이유: 이 시험은 “적용 전에는 빨갛고 적용 뒤에는 초록”이어야
계약이지, 초록으로 고정된 문장이 아니다(nx10/PROMOTION_PLAN §1h 의 P1/P2 시나리오).

namespace 규율:
  `sys.modules` 에서 `antigravity_k.*` 를 비우는 것은 **미러 리허설(`NX10_FLUSH_TREE` 지정)에서만** 한다.
  승격된 이 파일은 `tests/` 에서 일반 suite 와 함께 수집되므로, 조건 없이 비우면 나중에 import 되는
  module 이 같은 이름으로 다시 만들어져 **class identity 가 갈라진다**(실측 · ARCHITECTURE_REVIEW §1.1 ④).

"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
TREE_ENV = "NX10_FLUSH_TREE"


def _tree_root() -> Path:
    """검사 대상 트리: `NX10_FLUSH_TREE` 가 있으면 그곳, 없으면 `pyproject.toml` 을 위로 찾아 올라간다."""
    override = os.environ.get(TREE_ENV)
    if override:
        return Path(override).resolve()
    for candidate in (HERE, *HERE.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise AssertionError("검사 대상 트리를 찾지 못했다")


TREE = _tree_root()
SRC = TREE / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
# 다른 트리를 검사할 때 이전 임포트가 남아 있으면 조용히 옛 바이트를 검사한다(승격 때 실제로 겪은 부류).
# 그래서 비우는 것은 **미러 리허설에서만** 한다 — 이 파일은 승격 뒤 `tests/` 에서 일반 suite 와 함께 수집되므로,
# 조건 없이 비우면 아직 import 되지 않은 module 이 나중에 같은 이름으로 다시 만들어져 class identity 가 갈라진다
# (실측: 전량 회귀에서 `authority.AuthorityProfile` 이 두 객체가 됐다 · ARCHITECTURE_REVIEW §1.1 ④).
if os.environ.get(TREE_ENV):
    for name in [key for key in list(sys.modules) if key.startswith("antigravity_k")]:
        del sys.modules[name]


def _imports() -> tuple[Any, Any, Any]:
    from antigravity_k.engine import conversation_journal as journal_module
    from antigravity_k.engine import conversation_store as store_module
    from antigravity_k.engine.conversation_store import ConversationStore

    return journal_module, store_module, ConversationStore


class _Budget:
    """append N회의 syscall·바이트·호출 수를 **결정적으로** 센다(디스크 상태와 무관)."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.bytes_read = 0
        self._original: dict[str, Any] = {}

    def __enter__(self) -> _Budget:
        for name in ("open", "pread", "fsync", "replace", "write", "fstat", "stat"):
            original = getattr(os, name, None)
            if original is None:
                continue
            self._original[name] = original

            def make(fn: Any, key: str) -> Any:
                def wrapper(*args: Any, **kwargs: Any) -> Any:
                    self.counts[key] = self.counts.get(key, 0) + 1
                    result = fn(*args, **kwargs)
                    if key == "pread" and isinstance(result, (bytes, bytearray)):
                        self.bytes_read += len(result)
                    return result

                return wrapper

            setattr(os, name, make(original, name))
        return self

    def __exit__(self, *exc: object) -> None:
        for name, original in self._original.items():
            setattr(os, name, original)


def _measure_appends(appends: int = 120) -> tuple[dict[str, float], int]:
    """정상 상태 append N회를 재고 `(1회당 예산, tail() 호출 수)` 를 돌려준다."""
    journal_module, _store_module, ConversationStore = _imports()
    import tempfile

    workdir = Path(tempfile.mkdtemp(prefix="nx10-flush-contract-"))
    store = ConversationStore(storage_dir=workdir / "conversations")
    project, conversation = "flush", "conv"
    revision = store.append(
        project_id=project, conversation_id=conversation, expected_revision=0, role="user", content="seed"
    ).revision
    for index in range(5):  # 워밍업(디렉터리 생성·첫 줄)은 예산에서 뺀다
        revision = store.append(
            project_id=project,
            conversation_id=conversation,
            expected_revision=revision,
            role="user",
            content=f"w{index}",
        ).revision

    tail_calls = [0]
    original_tail = journal_module.ConversationJournal.tail

    def counting_tail(self: Any) -> Any:
        tail_calls[0] += 1
        return original_tail(self)

    journal_module.ConversationJournal.tail = counting_tail  # type: ignore[method-assign]
    try:
        with _Budget() as budget:
            for index in range(appends):
                revision = store.append(
                    project_id=project,
                    conversation_id=conversation,
                    expected_revision=revision,
                    role="user",
                    content=f"turn {index}",
                ).revision
    finally:
        journal_module.ConversationJournal.tail = original_tail  # type: ignore[method-assign]

    per = {name: value / appends for name, value in budget.counts.items()}
    per["bytes_read"] = budget.bytes_read / appends
    return per, tail_calls[0] / appends


def test_append_reads_the_journal_tail_at_most_once() -> None:
    """계약 ①: 한 커밋은 꼬리를 **한 번만** 읽는다 — 이 배치의 핵심 산출이다.

    실측 근거: 종전 append 1회는 `tail()` 을 **3.00회** 불렀고 그때마다 꼬리 창을 다시 읽어
    **116,025 B(≈113 KiB)/회** 를 재읽기했다(nx10/fsync/probe-flush-output.json).
    """
    per, tail_per_append = _measure_appends()
    assert tail_per_append <= 1.0, f"꼬리를 append 1회당 {tail_per_append:.2f}회 읽는다(계약: ≤ 1회)"
    assert per["bytes_read"] <= 70_000, f"꼬리 재읽기가 남아 있다: {per['bytes_read']:.0f} B/append(계약: ≤ 70,000)"


def test_append_still_fsyncs_exactly_once() -> None:
    """계약 ②: **내구성을 바꾸지 않았다** — append 1회당 fsync 는 정확히 1회다(F1 은 예산만 줄인다)."""
    per, _ = _measure_appends()
    assert per.get("fsync") == 1.0, f"fsync 가 append 1회당 {per.get('fsync')}회다(계약: 정확히 1회)"


def test_append_open_budget_does_not_regress() -> None:
    """계약 ①-보조: 한 커밋의 open 수가 늘지 않는다(측정 기준선 5/append)."""
    per, _ = _measure_appends()
    assert per.get("open", 0) <= 4.5, f"open 이 append 1회당 {per.get('open')}회다(기준선 5 · 계약 ≤ 4)"


def test_revision_and_seq_advance_exactly_once_per_append() -> None:
    """계약 ③: 꼬리를 나눠 써도 `seq`/`revision` 은 append 1회에 1씩만 오른다."""
    journal_module, _store_module, ConversationStore = _imports()
    import tempfile

    workdir = Path(tempfile.mkdtemp(prefix="nx10-flush-seq-"))
    store = ConversationStore(storage_dir=workdir / "conversations")
    project, conversation = "flush", "conv"
    revision = 0
    for index in range(1, 9):
        snapshot = store.append(
            project_id=project,
            conversation_id=conversation,
            expected_revision=revision,
            role="user",
            content=f"turn {index}",
        )
        revision = snapshot.revision
        assert revision == index, (revision, index)
    tail = journal_module.ConversationJournal(
        store.journal_path(project_id=project, conversation_id=conversation)
    ).tail()
    assert (tail.seq, tail.revision) == (8, 8), (tail.seq, tail.revision)


def test_a_new_critical_section_never_reuses_a_stale_tail() -> None:
    """계약 ④: 꼬리 기억은 **임계 구역 밖으로 새지 않는다**.

    실패한 CAS 뒤(꼬리를 읽고 커밋하지 않은 상태) 다른 writer 가 저널을 전진시킨 상황을 만든다 —
    기억이 새면 다음 append 가 **낡은 seq** 로 커밋해 revision 이 겹친다(조용한 손상).
    """
    _journal_module, _store_module, ConversationStore = _imports()
    import tempfile

    from antigravity_k.engine.conversation_store import StaleConversationRevisionError

    workdir = Path(tempfile.mkdtemp(prefix="nx10-flush-memo-"))
    storage = workdir / "conversations"
    store_a = ConversationStore(storage_dir=storage)
    store_b = ConversationStore(storage_dir=storage)
    project, conversation = "flush", "conv"
    revision = store_a.append(
        project_id=project, conversation_id=conversation, expected_revision=0, role="user", content="seed"
    ).revision

    # ① 꼬리를 읽고 커밋하지 않는 경로(CAS 실패) → 이 인스턴스의 기억이 남는다.
    try:
        store_a.append(
            project_id=project,
            conversation_id=conversation,
            expected_revision=revision + 5,
            role="user",
            content="loser",
        )
        raise AssertionError("CAS 실패를 기대했다")
    except StaleConversationRevisionError:
        pass

    # ② 다른 writer 가 저널을 두 번 전진시킨다(다른 인스턴스 = 다른 기억).
    revision = store_b.append(
        project_id=project, conversation_id=conversation, expected_revision=revision, role="user", content="foreign-1"
    ).revision
    revision = store_b.append(
        project_id=project, conversation_id=conversation, expected_revision=revision, role="user", content="foreign-2"
    ).revision

    # ③ 첫 인스턴스가 다시 커밋한다 — 낡은 꼬리를 썼다면 revision 이 겹친다.
    snapshot = store_a.append(
        project_id=project, conversation_id=conversation, expected_revision=revision, role="user", content="after"
    )
    assert snapshot.revision == revision + 1, (snapshot.revision, revision)
    assert store_a.get_revision(project_id=project, conversation_id=conversation) == revision + 1


def test_truncated_tail_is_still_rewritten_before_the_commit(monkeypatch: Any) -> None:
    """계약 ③-보조: 미결 꼬리(torn tail)는 종전과 똑같이 **커밋 전에** 옮겨진다."""
    journal_module, _store_module, ConversationStore = _imports()
    import tempfile

    workdir = Path(tempfile.mkdtemp(prefix="nx10-flush-torn-"))
    store = ConversationStore(storage_dir=workdir / "conversations")
    project, conversation = "flush", "conv"
    revision = store.append(
        project_id=project, conversation_id=conversation, expected_revision=0, role="user", content="seed"
    ).revision
    journal_path = store.journal_path(project_id=project, conversation_id=conversation)

    calls: list[int] = []
    original = journal_module.ConversationJournal.rewrite_without_truncated_tail

    def counting_rewrite(self: Any) -> Any:
        calls.append(1)
        return original(self)

    monkeypatch.setattr(journal_module.ConversationJournal, "rewrite_without_truncated_tail", counting_rewrite)
    with open(journal_path, "ab") as handle:  # 커밋되지 않은 반쪽 줄을 심는다
        handle.write(b'{"schema": "agk.conv-journal.v1", "seq": 99')

    snapshot = store.append(
        project_id=project, conversation_id=conversation, expected_revision=revision, role="user", content="after torn"
    )
    assert calls, "미결 꼬리를 커밋 전에 옮기지 않았다"
    assert snapshot.revision == revision + 1, (snapshot.revision, revision)
    assert journal_module.ConversationJournal(journal_path).tail().truncated_tail is False


def test_the_journal_line_is_fsynced_before_the_view_is_replaced(monkeypatch: Any) -> None:
    """계약 ②-보조: 커밋 순서가 그대로다 — 줄 + fsync 가 **먼저**, view 재작성이 그 다음(ADR §2)."""
    journal_module, _store_module, ConversationStore = _imports()
    import tempfile

    workdir = Path(tempfile.mkdtemp(prefix="nx10-flush-order-"))
    store = ConversationStore(storage_dir=workdir / "conversations")
    project, conversation = "flush", "conv"
    order: list[str] = []

    original_fsync = journal_module._fsync_fd
    original_replace = os.replace

    def recording_fsync(fd: int) -> None:
        order.append("fsync")
        original_fsync(fd)

    def recording_replace(src: Any, dst: Any) -> None:
        order.append("view-replace")
        original_replace(src, dst)

    monkeypatch.setattr(journal_module, "_fsync_fd", recording_fsync)
    monkeypatch.setattr(os, "replace", recording_replace)
    revision = store.append(
        project_id=project, conversation_id=conversation, expected_revision=0, role="user", content="seed"
    ).revision
    order.clear()
    store.append(
        project_id=project, conversation_id=conversation, expected_revision=revision, role="user", content="turn"
    )
    assert "fsync" in order and "view-replace" in order, order
    assert order.index("fsync") < order.index("view-replace"), f"커밋 순서가 뒤집혔다: {order}"


def test_view_write_failure_keeps_the_journal_commit(monkeypatch: Any) -> None:
    """계약 ⑤: view 쓰기가 실패해도 저널 커밋은 살아남는다(종전 계약 그대로 · 배치가 건드리지 않는다)."""
    _journal_module, store_module, ConversationStore = _imports()
    import tempfile

    workdir = Path(tempfile.mkdtemp(prefix="nx10-flush-viewfail-"))
    storage = workdir / "conversations"
    store = ConversationStore(storage_dir=storage)
    project, conversation = "flush", "conv"
    revision = store.append(
        project_id=project, conversation_id=conversation, expected_revision=0, role="user", content="seed"
    ).revision

    journal_path = store.journal_path(project_id=project, conversation_id=conversation)

    def boom(self: Any, record: Any) -> None:
        raise OSError("view write failed")

    monkeypatch.setattr(ConversationStore, "_persist", boom)
    try:
        store.append(
            project_id=project,
            conversation_id=conversation,
            expected_revision=revision,
            role="user",
            content="committed even though the view failed",
        )
    except OSError:
        pass
    else:
        raise AssertionError("view 실패가 조용히 통과했다")

    # 저널은 두 줄(seed + turn)이고, 원본 이력이 그대로 복구된다.
    import antigravity_k.engine.conversation_journal as journal_module

    events, truncated = journal_module.ConversationJournal(journal_path).read()
    assert truncated is False
    assert [event.seq for event in events] == [1, 2], [event.seq for event in events]
    fresh = ConversationStore(storage_dir=storage)
    history = fresh.original_history(project_id=project, conversation_id=conversation)
    assert [str(message["content"]) for message in history] == [
        "seed",
        "committed even though the view failed",
    ], history


def test_the_tail_memo_is_cleared_when_the_critical_section_is_entered() -> None:
    """계약 ④-보조(소스 이빨): 기억을 비우는 지점이 **임계 구역 진입**에 있다."""
    store_source = (SRC / "antigravity_k" / "engine" / "conversation_store.py").read_text(encoding="utf-8")
    journal_source = (SRC / "antigravity_k" / "engine" / "conversation_journal.py").read_text(encoding="utf-8")
    assert "_journal_tail" in store_source, "꼬리 기억 도우미가 없다"
    assert "self._tail_memo = None" in store_source, "기억을 비우는 지점이 없다"
    lock_start = store_source.index("def _cross_process_lock")
    lock_end = store_source.index("def _journal_errors")
    assert "self._tail_memo = None" in store_source[lock_start:lock_end], (
        "임계 구역 진입에서 기억을 비우지 않는다 — 낡은 seq 위험"
    )
    assert "tail: JournalTail | None = None" in journal_source, "append 가 호출자의 꼬리를 받지 않는다"
