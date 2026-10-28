"""성능 회귀 테스트 — Freebuff-Style Proactive Pipeline latency 검증.

각 파이프라인 단계의 latency가 허용 임계값 이하인지 측정합니다.
벤치마크 스크립트(scripts/benchmark_proactive_pipeline.py)와 동일한
측정 함수를 사용하지만, pytest에 통합하여 CI에서 성능 회귀를 감지합니다.

환경 변수로 임계값 오버라이드:
  BENCHMARK_THRESHOLD_CONTEXT_ENRICH  (기본: 500ms)
  BENCHMARK_THRESHOLD_CODE_REVIEW     (기본: 1000ms)
  BENCHMARK_THRESHOLD_MAX_ENGINE      (기본: 50ms)

실행 (CR-14 F-21 이후):
  이 모듈의 모든 테스트는 `benchmark` 마커를 가진다. 그 이유는 임계값이 **wall-clock** 이라
  조용한 프로세스에서만 의미가 있기 때문이다 — 실측: 같은 환경에서 이 모듈만 돌리면
  `test_context_enrich_total_latency` 가 2209/2209/2212ms 였지만, 6000여 개 테스트를 도는
  프로세스 안에서는 6084ms 로 임계값(6000ms)을 넘겼다.

  그래서 기능 게이트는 `-m "not benchmark"` 로 이 모듈을 제외하고, 전용 게이트가 선별한다:

      python -m pytest tests/ -m "not benchmark" -v --tb=short   # python-tests
      python -m pytest tests/ -m benchmark -v --tb=short         # python-benchmark

  특정 스테이지만:

      python -m pytest tests/test_benchmark_performance.py -v -k "context_enrich"

  주의: 예전 이 자리에는 "기본: slow 마커로 skip" 이라고 적혀 있었지만 실제로 그들을
  deselect 하는 설정은 없었다(`addopts`·collection hook 없음) — 문서와 동작이 달랐다.
"""

import os
import tempfile
import time
from collections.abc import Callable
from types import TracebackType
from typing import Self, cast

import pytest

from tests._legacy_fake_embedding import legacy_fake_binding  # noqa: F401  # r29 explicit fake binding

pytestmark = pytest.mark.usefixtures("legacy_fake_binding")

# ─── 프로젝트 루트 탐색 ──────────────────────────────────────────

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
# sys.path는 conftest.py에서 src/를 이미 추가합니다.


class _GeneratorDouble:
    def generate(self, prompt: str, target: str, **kwargs: object) -> str:
        _ = (prompt, target, kwargs)
        return "BUGS: None\nTYPES: None\nQUALITY: None"


class _ManagerDouble:
    _loaded_models: dict[str, object]

    def __init__(self, loaded_models: dict[str, object] | None = None) -> None:
        self._loaded_models = loaded_models or {}

    def generate(self, prompt: str, target: str, **kwargs: object) -> str:
        _ = (prompt, target, kwargs)
        return "SELECTED: 1\nREASON: Best"


class _ContextDouble:
    cost_guard: None = None


class _OrchestratorDouble:
    manager: _ManagerDouble
    ctx: _ContextDouble

    def __init__(self, manager: _ManagerDouble) -> None:
        self.manager = manager
        self.ctx = _ContextDouble()

    def _get_model_for_role(self, role: str) -> str:
        _ = role
        return "qa-model"


# ─── 임계값 설정 (환경 변수로 오버라이드 가능) ─────────────────


def _threshold(name: str, default: float) -> float:
    """환경 변수에서 임계값을 읽거나 기본값을 반환합니다."""
    env_key = f"BENCHMARK_THRESHOLD_{name.upper()}"
    raw = os.environ.get(env_key)
    if raw is not None:
        try:
            return float(raw)
        except ValueError:
            pass
    return default


# ─── RAG 테스트용 가상 프로젝트 생성 헬퍼 ──────────────────────


def _create_rag_test_project(tmpdir: str) -> dict[str, str]:
    """RAG 벤치마크용 가상 프로젝트 (Python + Markdown 파일)를 생성합니다."""
    import os

    files: dict[str, str] = {}
    for i in range(8):
        files[f"src/mod{i}.py"] = (
            f"import os\nfrom typing import Optional\n\n"
            f"def process_{i}(data: str) -> str:\n"
            f'    """Process data for module {i}."""\n'
            f"    result = data.upper()\n"
            f"    return result.strip()\n\n"
            f"class Handler{i}:\n"
            f'    """Handler for module {i}."""\n'
            f'    def __init__(self, name: str = "default"):\n'
            f"        self.name = name\n"
            f"    def handle(self, payload: dict) -> dict:\n"
            f'        return {{"status": "ok", "module": {i}}}\n'
        )

    for i in range(6):
        files[f"doc/chapter_{i}.md"] = (
            f"# Chapter {i}\n\n"
            f"Introduction to chapter {i}.\n\n"
            f"## Section {i}.1\n\n"
            f"Content for section {i}.1.\n\n"
            f"| Key | Value |\n"
            f"|-----|-------|\n"
            f"| param_{i} | value_{i} |\n"
        )

    for rel_path, content in files.items():
        full_path = os.path.join(tmpdir, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            _ = f.write(content)

    return files


# ─── 타이머 헬퍼 ─────────────────────────────────────────────────


class _Timer:
    """간단한 밀리초 단위 타이머."""

    _start: float
    _elapsed: float

    def __init__(self) -> None:
        self._start = 0.0
        self._elapsed = 0.0

    def __enter__(self) -> Self:
        self._start = time.perf_counter()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._elapsed = (time.perf_counter() - self._start) * 1000

    @property
    def ms(self) -> float:
        return self._elapsed


# ═══════════════════════════════════════════════════════════════════
# context_enrich — CodeTreeIndexer + FileSummarizer
# ═══════════════════════════════════════════════════════════════════

_NAME_CTX = "context_enrich"
_THRESHOLD_CTX = _threshold(_NAME_CTX, 6000.0)  # 6000ms — 솔로 실측 ~2s, 전체 suite 동시 실행 시 디스크 경합 헤드룸


@pytest.mark.benchmark
@pytest.mark.slow
def test_context_enrich_total_latency():
    """context_enrich 전체 latency가 임계값 이하인지 검증."""
    from antigravity_k.engine.code_tree_indexer import CodeTreeIndexer
    from antigravity_k.engine.file_summarizer import FileSummarizer

    t_total = _Timer()
    with t_total:
        indexer = CodeTreeIndexer(PROJECT_ROOT)
        _ = indexer.build_tree()
        related = indexer.search("benchmark performance test", max_files=8)
        summarizer = FileSummarizer()
        _ = summarizer.summarize_files(related, PROJECT_ROOT, query="benchmark")

    total_ms = t_total.ms
    assert total_ms < _THRESHOLD_CTX, (
        f"context_enrich latency {total_ms:.1f}ms exceeds threshold {_THRESHOLD_CTX:.0f}ms"
    )


@pytest.mark.benchmark
def test_context_enrich_search_latency():
    """CodeTreeIndexer.search() latency가 허용 범위 내인지 검증."""
    from antigravity_k.engine.code_tree_indexer import CodeTreeIndexer

    indexer = CodeTreeIndexer(PROJECT_ROOT)
    _ = indexer.build_tree()

    queries = [
        "benchmark performance test",
        "code tree indexer",
        "file summarizer",
        "user authentication",
    ]

    times_ms: list[float] = []
    for q in queries:
        t = _Timer()
        with t:
            _ = indexer.search(q, max_files=8)
        times_ms.append(t.ms)

    avg_search_ms = sum(times_ms) / len(times_ms)

    # search는 가볍게 동작해야 함 (랭킹 연산만)
    assert avg_search_ms < 200.0, f"search avg latency {avg_search_ms:.2f}ms exceeds 200ms"


@pytest.mark.benchmark
def test_context_enrich_build_tree_latency():
    """CodeTreeIndexer.build_tree() 첫 빌드 latency 검증."""
    import tempfile

    from antigravity_k.engine.code_tree_indexer import CodeTreeIndexer

    # 작은 프로젝트로 측정 (안정적인 latency)
    with tempfile.TemporaryDirectory() as tmpdir:
        # 10개 Python 파일 생성
        for i in range(10):
            p = os.path.join(tmpdir, f"mod{i}.py")
            with open(p, "w") as f:
                _ = f.write(f"def func_{i}():\n    return {i}\n\n")
                _ = f.write(f"class Class{i}:\n    pass\n")

        # 깨끗한 인덱서로 첫 빌드
        indexer = CodeTreeIndexer(tmpdir)

        t = _Timer()
        with t:
            _ = indexer.build_tree()

        assert t.ms < 300.0, f"first build_tree latency {t.ms:.1f}ms exceeds 300ms"

        # 캐시 히트 검증
        t_cache = _Timer()
        with t_cache:
            _ = indexer.build_tree()

        assert t_cache.ms < 10.0, f"cached build_tree latency {t_cache.ms:.2f}ms exceeds 10ms"


# ═══════════════════════════════════════════════════════════════════
# code_review — Git diff + Mock LLM
# ═══════════════════════════════════════════════════════════════════

_NAME_CR = "code_review"
_THRESHOLD_CR = _threshold(_NAME_CR, 1000.0)  # 1000ms generously (git diff 포함)


@pytest.mark.benchmark
@pytest.mark.slow
def test_code_review_total_latency():
    """code_review 전체 latency가 임계값 이하인지 검증."""
    import subprocess

    mock_manager = _GeneratorDouble()

    t_total = _Timer()
    with t_total:
        # Git diff --stat
        _ = subprocess.run(
            ["git", "diff", "--stat"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )

        # Git diff 상세
        detail_result = subprocess.run(
            ["git", "diff"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        diff_content = detail_result.stdout

        # 모의 LLM 리뷰
        review_prompt = f"""Review the following code changes for bugs or issues.

Respond in EXACTLY this format (one line per category, 'None' if none):
BUGS: <brief description or None>
TYPES: <type error description or None>
QUALITY: <quality concern or None>

```diff
{diff_content[:2000]}
```"""
    _ = mock_manager.generate(
        prompt=review_prompt,
        target="qa-model",
        max_tokens=256,
    )

    total_ms = t_total.ms
    assert total_ms < _THRESHOLD_CR, f"code_review latency {total_ms:.1f}ms exceeds threshold {_THRESHOLD_CR:.0f}ms"


@pytest.mark.benchmark
def test_code_review_git_diff_latency():
    """Git diff 명령어 latency 검증."""
    import subprocess

    t_stat = _Timer()
    with t_stat:
        _ = subprocess.run(
            ["git", "diff", "--stat"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
    assert t_stat.ms < 500.0, f"git diff --stat latency {t_stat.ms:.1f}ms exceeds 500ms"

    t_detail = _Timer()
    with t_detail:
        _ = subprocess.run(
            ["git", "diff"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
    assert t_detail.ms < 500.0, f"git diff detail latency {t_detail.ms:.1f}ms exceeds 500ms"


@pytest.mark.benchmark
def test_code_review_mock_llm_latency():
    """모의 LLM 리뷰 호출 latency 검증 (서브 밀리초여야 함)."""
    mock_manager = _GeneratorDouble()

    t = _Timer()
    with t:
        _ = mock_manager.generate(
            prompt="Review: some code",
            target="qa-model",
            max_tokens=256,
        )

    # MagicMock 호출은 서브 밀리초
    assert t.ms < 10.0, f"mock LLM call latency {t.ms:.3f}ms exceeds 10ms"


# ═══════════════════════════════════════════════════════════════════
# max_engine — Worker config + mock run + Selector
# ═══════════════════════════════════════════════════════════════════

_NAME_MAX = "max_engine"
_THRESHOLD_MAX = _threshold(
    _NAME_MAX, 300.0
)  # 300ms — mock 위주(솔로 수 ms), 전체 suite 동시 실행 시 엔진 초기화 경합 헤드룸


@pytest.mark.benchmark
def test_max_engine_total_latency():
    """max_engine run() 전체 latency가 임계값 이하인지 검증."""
    from antigravity_k.engine.max_engine import MaxModeEngine, WorkerResult

    mgr = _ManagerDouble({"model-a": {}, "model-b": {}})

    engine = MaxModeEngine(mgr, project_root=PROJECT_ROOT)
    setattr(engine, "_get_available_models", lambda: ["model-a", "model-b"])

    def mock_run_worker(*_args: object, **_kwargs: object) -> WorkerResult:
        return WorkerResult(0, "model-a", "default", "output result", 0.3)

    setattr(engine, "_run_worker", mock_run_worker)

    mock_orch = _OrchestratorDouble(mgr)

    t = _Timer()
    with t:
        result = engine.run(
            {
                "prompt": "Create a test function",
                "messages": [{"role": "user", "content": "Create a test function"}],
                "task_type": "coding",
                "delegate_to": "WORKER",
                "max_steps": 5,
                "target_model": "model-a",
            },
            orchestrator=mock_orch,
        )

    total_ms = t.ms
    assert total_ms < _THRESHOLD_MAX, (
        f"max_engine run() latency {total_ms:.2f}ms exceeds threshold {_THRESHOLD_MAX:.0f}ms"
    )
    assert result.total_workers == 2


@pytest.mark.benchmark
def test_max_engine_worker_config_latency():
    """_build_worker_configs() latency 검증."""
    from antigravity_k.engine.max_engine import MaxModeEngine, WorkerConfig

    mgr = _ManagerDouble({"a": {}, "b": {}, "c": {}})
    engine = MaxModeEngine(mgr)
    build_worker_configs = cast(Callable[[str, str], list[WorkerConfig]], getattr(engine, "_build_worker_configs"))

    # 1개 모델
    setattr(engine, "_get_available_models", lambda: ["a"])
    t1 = _Timer()
    with t1:
        _ = build_worker_configs("WORKER", "a")
    assert t1.ms < 10.0, f"1 model config latency {t1.ms:.3f}ms"

    # 3개 모델
    setattr(engine, "_get_available_models", lambda: ["a", "b", "c"])
    t3 = _Timer()
    with t3:
        _ = build_worker_configs("WORKER", "a")
    assert t3.ms < 10.0, f"3 model config latency {t3.ms:.3f}ms"


@pytest.mark.benchmark
def test_max_engine_prompt_building_latency():
    """_build_worker_prompt() latency 검증 (4개 전략)."""
    from antigravity_k.engine.max_engine import MaxModeEngine

    engine = MaxModeEngine(None)
    build_worker_prompt = cast(Callable[[str, str, str, float], str], getattr(engine, "_build_worker_prompt"))

    for strategy in ("default", "creative", "safe", "balanced"):
        t = _Timer()
        with t:
            _ = build_worker_prompt(
                "Create a test function",
                "model-a",
                strategy,
                0.4,
            )
        assert t.ms < 10.0, f"prompt building ({strategy}) latency {t.ms:.3f}ms exceeds 10ms"


@pytest.mark.benchmark
def test_max_engine_selector_latency():
    """_select_best() latency 검증 (2개, 3개 후보)."""
    from antigravity_k.engine.max_engine import (
        MaxModeEngine,
        WorkerResult,
    )

    mgr = _ManagerDouble()
    engine = MaxModeEngine(mgr)

    qa_orch = _OrchestratorDouble(mgr)
    select_best = cast(Callable[..., int], getattr(engine, "_select_best"))

    # 2개 후보
    t2 = _Timer()
    with t2:
        _ = select_best(
            "task",
            [
                WorkerResult(0, "a", "default", "short", 0.5),
                WorkerResult(1, "b", "creative", "longer complete", 1.2),
            ],
            "WORKER",
            qa_orch,
        )
    assert t2.ms < 20.0, f"2-candidate selector latency {t2.ms:.3f}ms exceeds 20ms"

    # 3개 후보
    t3 = _Timer()
    with t3:
        _ = select_best(
            "task",
            [
                WorkerResult(0, "a", "default", "first", 0.5),
                WorkerResult(1, "b", "creative", "second", 1.0),
                WorkerResult(2, "c", "safe", "third", 1.5),
            ],
            "WORKER",
            qa_orch,
        )
    assert t3.ms < 30.0, f"3-candidate selector latency {t3.ms:.3f}ms exceeds 30ms"


@pytest.mark.benchmark
def test_max_engine_format_trace_latency():
    """_format_trace() latency 검증."""
    from antigravity_k.engine.max_engine import (
        MaxModeEngine,
        WorkerResult,
    )

    engine = MaxModeEngine(None)
    format_trace = cast(Callable[..., str], getattr(engine, "_format_trace"))
    results = [
        WorkerResult(0, "a", "default", "out1", 1.0),
        WorkerResult(1, "b", "creative", "out2", 2.0),
    ]
    configs = [{"model": "a", "strategy": "default"}, {"model": "b", "strategy": "creative"}]

    t = _Timer()
    with t:
        trace = format_trace(results, 1, configs)

    assert t.ms < 5.0, f"format_trace latency {t.ms:.3f}ms exceeds 5ms"
    assert "SELECTED" in trace


# ═══════════════════════════════════════════════════════════════════
# rag_indexing — RAGIndexer + VectorStore (Vector Search + Context Retrieval)
# ═══════════════════════════════════════════════════════════════════

_NAME_RAG = "rag_indexing"
_THRESHOLD_RAG = _threshold(_NAME_RAG, 3000.0)  # 3000ms (includes ChromaDB index + search)


@pytest.mark.benchmark
@pytest.mark.slow
def test_rag_total_latency():
    """RAG pipeline 전체 latency (index_project + search + format_context) 검증."""
    pytest.importorskip("chromadb", reason="chromadb not installed (install the rag extra)")
    from antigravity_k.engine.rag_indexer import RAGIndexer
    from antigravity_k.engine.vector_store import VectorStore

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        _ = _create_rag_test_project(tmpdir)

        store = VectorStore(persist_directory=os.path.join(tmpdir, ".chroma"), collection_name="test_rag")
        indexer = RAGIndexer(tmpdir, vector_store=store)

        t_total = _Timer()
        with t_total:
            _ = indexer.index_project()
            _ = store.search("process data", n_results=5)
            _ = indexer.format_context("Handler processing", n_results=3, max_chars=3000)

        _ = store.close()

    total_ms = t_total.ms
    assert total_ms < _THRESHOLD_RAG, (
        f"rag_indexing total latency {total_ms:.1f}ms exceeds threshold {_THRESHOLD_RAG:.0f}ms"
    )


@pytest.mark.benchmark
def test_rag_chunk_python_latency():
    """RAGIndexer._chunk_python() — 단일 Python 파일 청킹 latency 검증."""
    from antigravity_k.engine.rag_indexer import CodeChunk, RAGIndexer

    indexer = RAGIndexer("/tmp", vector_store=None)

    content = (
        "import os\n"
        "from typing import Optional\n\n"
        "def process(data: str) -> str:\n"
        "    return data.strip()\n\n"
        "class Handler:\n"
        "    def __init__(self):\n"
        "        self.name = 'test'\n"
        "    def handle(self, payload: dict) -> dict:\n"
        "        return {'status': 'ok'}\n"
    )

    chunk_python = cast(Callable[[str, str], list[CodeChunk]], getattr(indexer, "_chunk_python"))
    t = _Timer()
    with t:
        chunks = chunk_python("test.py", content)

    assert t.ms < 50.0, f"chunk_python latency {t.ms:.3f}ms exceeds 50ms"
    assert len(chunks) >= 2  # header + function + class


@pytest.mark.benchmark
def test_rag_chunk_markdown_latency():
    """RAGIndexer._chunk_markdown() — 단일 Markdown 파일 청킹 latency 검증."""
    from antigravity_k.engine.rag_indexer import CodeChunk, RAGIndexer

    indexer = RAGIndexer("/tmp", vector_store=None)

    content = (
        "# Chapter 1\n\n"
        "Introduction text.\n\n"
        "## Section 1.1\n\n"
        "Detailed content here.\n\n"
        "| Key | Value |\n"
        "|-----|-------|\n"
        "| param | value |\n"
        "| timeout | 30s |\n"
        "## Section 1.2\n\n"
        "More content.\n"
    )

    chunk_markdown = cast(Callable[[str, str], list[CodeChunk]], getattr(indexer, "_chunk_markdown"))
    t = _Timer()
    with t:
        chunks = chunk_markdown("doc.md", content)

    assert t.ms < 20.0, f"chunk_markdown latency {t.ms:.3f}ms exceeds 20ms"
    assert len(chunks) >= 1


@pytest.mark.benchmark
def test_rag_search_semantic_latency():
    """VectorStore.search() — 시맨틱 검색 latency 검증."""
    pytest.importorskip("chromadb", reason="chromadb not installed (install the rag extra)")
    from antigravity_k.engine.rag_indexer import RAGIndexer
    from antigravity_k.engine.vector_store import VectorStore

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        _ = _create_rag_test_project(tmpdir)

        store = VectorStore(persist_directory=os.path.join(tmpdir, ".chroma"), collection_name="test_semantic")
        indexer = RAGIndexer(tmpdir, vector_store=store)
        _ = indexer.index_project()

        queries = ["process data", "handler method", "module implementation", "data processing"]

        times_ms: list[float] = []
        for q in queries:
            t = _Timer()
            with t:
                _ = store.search(q, n_results=5)
            times_ms.append(t.ms)

        _ = store.close()

    avg_search_ms = sum(times_ms) / len(times_ms) if times_ms else 0
    assert avg_search_ms < 200.0, f"semantic search avg latency {avg_search_ms:.2f}ms exceeds 200ms"


@pytest.mark.benchmark
def test_rag_hybrid_search_latency():
    """RAGIndexer._hybrid_search_rrf() — 하이브리드 검색 latency 검증."""
    pytest.importorskip("chromadb", reason="chromadb not installed (install the rag extra)")
    from antigravity_k.engine.rag_indexer import RAGIndexer
    from antigravity_k.engine.vector_store import VectorStore

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        _ = _create_rag_test_project(tmpdir)

        store = VectorStore(persist_directory=os.path.join(tmpdir, ".chroma"), collection_name="test_hybrid")
        indexer = RAGIndexer(tmpdir, vector_store=store)
        _ = indexer.index_project()

        t = _Timer()
        hybrid_search = cast(Callable[[str, int], list[dict[str, object]]], getattr(indexer, "_hybrid_search_rrf"))
        with t:
            _hybrid_results = hybrid_search("Handler validate process", 5)

        _ = store.close()

    assert t.ms < 500.0, f"hybrid search latency {t.ms:.3f}ms exceeds 500ms"
