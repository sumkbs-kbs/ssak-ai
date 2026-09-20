"""Ssak-Ai: 자율 학습 파이프라인 (Autonomous Learner).

=======================================================
사용자 명령 수행 시 에이전트가 자동으로 지식 갭을 감지하고,
웹 검색/스크래핑을 통해 학습하여 Vault(KI)에 영속적으로 저장합니다.

워크플로우:
  1. should_learn(task) → 학습 필요 여부 판단
  2. analyze_knowledge_gap(task) → 필요한 지식 목록 추출
  3. auto_learn(gaps) → 웹 검색 → 스크래핑 → 요약 → KI 저장
"""

import hashlib
import json
import logging
import os
import re
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol, TypeAlias, cast
from urllib.parse import urlsplit

from antigravity_k.config import config
from antigravity_k.engine.hook_event_bus import HookEventBus, HookEventEmit, get_hook_event_bus
from antigravity_k.tools.egress_policy import safe_urlopen
from antigravity_k.tools.web_search_models import SearchResponse

if TYPE_CHECKING:  # pragma: no cover - 순환 import 방지(계약 타입만 참조)
    from antigravity_k.agents.browser_task_loop import TaskGoal

logger = logging.getLogger(__name__)

JsonValue: TypeAlias = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]


class _ModelManagerLike(Protocol):
    def get_target_for_role(self, role_name: str, *, default_role: str = "reasoning") -> str: ...

    def generate(
        self,
        prompt: str,
        target: str,
        *,
        max_tokens: int,
        temperature: float,
    ) -> object: ...


class _BrowserModelManagerLike(Protocol):
    def get_target_for_role(self, role: str, *, default_role: str) -> str: ...

    def generate(self, **kwargs: object) -> object: ...


class _KIEngineLike(Protocol):
    def save_ki(self, ki_id: str, data: dict[str, object]) -> None: ...


def _verified_page_goal(topic: str, url: str) -> "TaskGoal":
    """주제와 검색 결과 URL 로 **측정 가능한** 목표를 만든다(task 19).

    성공 판정을 모델의 말에 맡기지 않기 위해 페이지에서 확인할 문장이 필요하다. 주제의 의미
    있는 단어가 페이지에 있는지(`text_contains`)를 먼저 보고, 쓸 단어가 없으면 "결과 페이지에
    실제로 머물렀는가"(`url_contains <host>`)만 확인한다 — 빈손으로 성공을 주장하지 않는다.
    """
    from antigravity_k.agents.browser_task_loop import Postcondition, TaskGoal

    keyword = next((token.strip(".,?!'\"()[]") for token in topic.split() if len(token.strip()) >= 4), "")
    conditions: tuple[Postcondition, ...]
    if keyword:
        conditions = (
            Postcondition("text_contains", keyword, description=f"페이지가 '{keyword}' 를 언급한다"),
            Postcondition("url_contains", urlsplit(url).hostname or "", description="결과 페이지에 머물렀다"),
        )
    else:
        conditions = (
            Postcondition("url_contains", urlsplit(url).hostname or "", description="결과 페이지에 머물렀다"),
        )
    return TaskGoal(goal=f"'{topic}' 에 대해 이 페이지에서 읽는다", postconditions=conditions)


def _knowledge_from_outcome(outcome: object, snippet: str, url: str, *, min_chars: int = 50) -> str:
    """작업 결과를 지식 문자열로 바꾸는 **판정 한 곳**(task 19).

    측정으로 확인된(`succeeded`) 작업의 **측정 본문**만 페이지 내용으로 쓴다. 확인되지 않았으면
    (partial/failed/blocked/cancelled) 페이지 대신 검색 스니펫으로 물러선다 — 예전에는 모델의
    주장(혹은 모델이 없는 상태의 `[Mock Data]`)이 50자만 넘으면 "학습한 내용" 으로 소비됐다.
    """
    from antigravity_k.agents.browser_task_loop import TaskOutcome, TaskStatus

    if isinstance(outcome, TaskOutcome) and outcome.status is TaskStatus.SUCCEEDED:
        text = outcome.final_text
        if len(text) > min_chars:
            return f"Source: {url}\nContent: {text}"
    return f"Source: {url}\nSnippet: {snippet}"


def _as_json_map(value: object) -> dict[str, object]:
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def _as_text(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _as_text_list(value: object, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    items = cast(list[object], value)
    return [item for item in items if isinstance(item, str)][:limit]


# ─── 데이터 모델 ─────────────────────────────────────────────────


@dataclass
class KnowledgeGap:
    """에이전트가 모르는 지식 항목."""

    topic: str
    reason: str  # 왜 이 지식이 필요한지
    search_queries: list[str] = field(default_factory=list)  # 검색 쿼리 후보


@dataclass
class LearnedKnowledge:
    """학습 완료된 지식."""

    topic: str
    summary: str
    sources: list[str] = field(default_factory=list)
    learned_at: str = ""
    ki_id: str = ""


# ─── 학습 필요 여부 판단 ─────────────────────────────────────────

# 학습이 필요할 가능성이 높은 키워드 패턴
_LEARN_TRIGGERS_KO = [
    "최신",
    "새로운",
    "업데이트",
    "방법",
    "어떻게",
    "설치",
    "라이브러리",
    "프레임워크",
    "패키지",
    "API",
    "문서",
    "트렌드",
    "비교",
    "추천",
    "2025",
    "2026",
]
_LEARN_TRIGGERS_EN = [
    "latest",
    "new",
    "update",
    "how to",
    "install",
    "library",
    "framework",
    "package",
    "tutorial",
    "documentation",
    "best practice",
    "compare",
]


class AutonomousLearner:
    """자율 학습 엔진.

    CEO 분석 후, 에이전트가 태스크를 실행하기 전에 호출되어
    필요한 지식을 자동으로 웹에서 수집하고 Vault에 저장합니다.
    """

    def __init__(
        self,
        model_manager: object | None = None,
        ki_engine: _KIEngineLike | None = None,
        project_root: str = ".",
    ):
        """Initialize the AutonomousLearner.

        Args:
            model_manager: model manager.
            ki_engine: ki engine.
            project_root (str): str project root.

        """
        self.manager: _ModelManagerLike | None = (
            cast(_ModelManagerLike, model_manager) if model_manager is not None else None
        )
        self.ki_engine: _KIEngineLike | None = ki_engine
        self.project_root: str = project_root
        self._max_gaps: int = 3
        self._max_sources_per_gap: int = 3
        self._last_manager_generation_failed: bool = False

    def _generation_target(self, role_name: str, default_role: str = "reasoning") -> str:
        configured = os.environ.get("AGK_KNOWLEDGE_MODEL", "").strip()
        if configured:
            return configured
        if self.manager is not None:
            resolver = getattr(self.manager, "get_target_for_role", None)
            if callable(resolver):
                try:
                    target = resolver(role_name, default_role=default_role)
                    if isinstance(target, str) and target.strip():
                        return target.strip()
                except (AttributeError, TypeError, ValueError, RuntimeError):
                    logger.warning("[AutoLearn] Failed to resolve managed knowledge model", exc_info=True)
        return config.model.main_model

    def _generate_with_manager(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        role_name: str,
        default_role: str = "reasoning",
    ) -> str | None:
        if self.manager is None:
            return None
        generate = getattr(self.manager, "generate", None)
        if not callable(generate):
            return None
        self._last_manager_generation_failed = False
        try:
            response = generate(
                prompt,
                self._generation_target(role_name, default_role),
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
            self._last_manager_generation_failed = True
            logger.warning("[AutoLearn] Managed knowledge generation failed; using keyword fallback", exc_info=True)
            return None
        if response is None:
            self._last_manager_generation_failed = True
        return response if isinstance(response, str) else None

    def should_learn(self, task_description: str) -> bool:
        """태스크 수행에 새로운 외부 지식이 필요한지 빠르게 판단합니다."""
        lower = task_description.lower()

        # ─── 단순 대화 질문 빠른 거부 (False Positive 방지) ───
        # 짧은 질문(80자 미만)이면서 기술 용어가 없으면 학습 불필요
        if len(task_description) < 80:
            tech_terms_found = sum(
                1
                for kw in [
                    "api",
                    "라이브러리",
                    "프레임워크",
                    "패키지",
                    "설치",
                    "library",
                    "framework",
                    "install",
                    "package",
                    "deploy",
                    "docker",
                    "kubernetes",
                    "database",
                ]
                if kw in lower
            )
            if tech_terms_found == 0:
                logger.debug("[AutoLearn] Short conversational question, skipping")
                return False

        # 키워드 기반 빠른 감지
        all_triggers = _LEARN_TRIGGERS_KO + _LEARN_TRIGGERS_EN
        matches = sum(1 for kw in all_triggers if kw in lower)

        # 3개 이상 트리거 매칭 시 학습 필요 (임계값 상향)
        if matches >= 3:
            logger.info("[AutoLearn] Triggered by keywords (%s matches)", matches)
            return True

        # URL이나 패키지 이름이 포함된 경우
        if re.search(r"https?://|pip install|npm install|brew install", lower):
            return True

        # 물음표 + 기술 키워드 2개 이상일 때만 학습 (조건 강화)
        return ("?" in task_description or "어떻게" in lower or "how" in lower) and matches >= 2

    def analyze_knowledge_gap(self, task_description: str) -> list[KnowledgeGap]:
        """LLM을 사용하여 태스크에 필요한 지식 갭을 분석합니다.

        LLM이 없으면 키워드 기반 폴백으로 검색 쿼리를 생성합니다.
        """
        # LLM 기반 분석 시도
        if self.manager is not None:
            try:
                return self._analyze_with_llm(task_description)
            except Exception:
                logger.exception("[AutoLearn] LLM analysis failed, falling back")

        # 키워드 기반 폴백
        return self._analyze_with_keywords(task_description)

    def _analyze_with_llm(self, task_description: str) -> list[KnowledgeGap]:
        """LLM에게 지식 갭 분석을 요청합니다."""
        prompt = (
            "You are a knowledge gap analyzer. Given the following user task, "
            "identify what specific knowledge or information would be needed from the internet "
            "to complete it successfully.\n\n"
            f"Task: {task_description}\n\n"
            "Return a JSON array of objects with fields:\n"
            "- topic: what knowledge is needed\n"
            "- reason: why it's needed\n"
            "- search_queries: list of 2-3 web search queries to find this info\n\n"
            "Return ONLY the JSON array, no markdown or explanation.\n"
            "If no external knowledge is needed, return an empty array []."
        )

        try:
            response_text = self._generate_with_manager(
                prompt,
                max_tokens=512,
                temperature=0.3,
                role_name="knowledge_gap_analyzer",
            )
            if response_text is None:
                if self._last_manager_generation_failed:
                    return self._analyze_with_keywords(task_description)
                data = {
                    "model": self._generation_target("knowledge_gap_analyzer"),
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": 512, "temperature": 0.3},
                }
                req = urllib.request.Request(
                    f"{config.model.api_base.replace('/v1', '').rstrip('/')}/api/generate",
                    data=json.dumps(data).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
                with safe_urlopen(req, timeout=30) as resp:
                    result = _as_json_map(cast(object, json.loads(resp.read().decode("utf-8"))))
                    response_text = _as_text(result.get("response"))

            # JSON 추출
            # <think> 태그 제거
            clean = re.sub(r"<think>.*?</think>", "", response_text, flags=re.DOTALL)

            # JSON 배열 추출
            match = re.search(r"\[.*\]", clean, re.DOTALL)
            if match:
                parsed = cast(object, json.loads(match.group()))
                gaps_data = cast(list[object], parsed) if isinstance(parsed, list) else []
                gaps: list[KnowledgeGap] = []
                for item in gaps_data[: self._max_gaps]:
                    item_map = _as_json_map(item)
                    gaps.append(
                        KnowledgeGap(
                            topic=_as_text(item_map.get("topic")),
                            reason=_as_text(item_map.get("reason")),
                            search_queries=_as_text_list(item_map.get("search_queries"), 3),
                        ),
                    )
                return gaps

        except Exception:
            logger.exception("[AutoLearn] LLM gap analysis error")

        return self._analyze_with_keywords(task_description)

    def _analyze_with_keywords(self, task_description: str) -> list[KnowledgeGap]:
        """키워드 기반 폴백 — LLM 없이 검색 쿼리를 생성합니다."""
        gaps: list[KnowledgeGap] = []

        # URL 제거 (오탐 방지)
        text_without_urls = re.sub(r"https?://\S+", "", task_description)

        # 핵심 명사구 추출 (간단한 휴리스틱)
        # 따옴표 안의 내용, 영문 고유명사, 기술 용어 추출
        quoted: list[str] = re.findall(r'["\']([^"\']+)["\']', text_without_urls)
        tech_terms: list[str] = re.findall(r"\b[A-Z][a-zA-Z]+(?:\.[a-zA-Z]+)*\b", text_without_urls)

        # 쿼리 후보 생성
        if quoted:
            for q in quoted[:2]:
                gaps.append(
                    KnowledgeGap(
                        topic=q,
                        reason="사용자가 명시적으로 언급한 주제",
                        search_queries=[q, f"{q} tutorial", f"{q} 사용법"],
                    ),
                )

        if tech_terms:
            combined = " ".join(tech_terms[:3])
            gaps.append(
                KnowledgeGap(
                    topic=combined,
                    reason="기술 용어 감지",
                    search_queries=[combined, f"{combined} documentation"],
                ),
            )

        # 기본 폴백
        if not gaps:
            gaps.append(
                KnowledgeGap(
                    topic=task_description[:100],
                    reason="일반 태스크 학습",
                    search_queries=[task_description[:80]],
                ),
            )

        return gaps[: self._max_gaps]

    def auto_learn(self, gaps: list[KnowledgeGap]) -> list[LearnedKnowledge]:
        """다중 에이전트 협업 파이프라인 (Vibe Coding Style):

        1. Query Generator: 이미 분석된 gaps.search_queries 사용
        2. Search Infra: SearxNG/Tavily를 통해 검색 후 URL 확보
        3. Web Surfer: BrowserSurfingAgent가 해당 URL에 접속해 시각적 탐색 후 데이터 추출
        4. Synthesizer: DeepSeek-V4가 수집된 정보를 교차 검증 및 최종 요약
        """
        from antigravity_k.agents.browser_surfing_agent import BrowserSurfingAgent
        from antigravity_k.agents.browser_task_loop import TaskBudget, TaskStatus
        from antigravity_k.tools.web_search import WebSearchEngine

        bus: HookEventBus | None = get_hook_event_bus()

        search_engine = WebSearchEngine()
        browser_manager = (
            cast(_BrowserModelManagerLike, cast(object, self.manager)) if self.manager is not None else None
        )
        surfer = BrowserSurfingAgent(model_manager=browser_manager, vision_model_name="qwen3.6:latest")

        learned: list[LearnedKnowledge] = []

        # asyncio.run is not safe inside an async context, but auto_learn seems synchronous right now?
        # Actually auto_learn is called synchronously in orchestrator_handlers.py!
        # But WebSearchEngine and BrowserSurfingAgent are async.
        # Let's wrap async execution
        import asyncio

        async def _run_vibe_coding_pipeline():
            if bus:
                # role/task_type는 kanban_api의 AgentTurnStarted 구독자가 사용
                bus.emit(
                    HookEventEmit(
                        kind="agent-turn-start",
                        payload={
                            "panel_id": "auto_learner",
                            "role": "AutoLearner",
                            "task_type": "Vibe Coding Pipeline",
                        },
                    ),
                )
            for gap in gaps:
                try:
                    all_results: list[str] = []
                    for query in gap.search_queries[:2]:
                        # 검색 인프라 (SearxNG/Tavily)
                        response: SearchResponse = await search_engine.search(query=query)
                        if response and response.results:
                            # 상위 2개 URL에 대해 Browser-Use 서핑 수행
                            for r in response.results[:2]:
                                logger.info("[AutoLearn] Surfing %s for '%s'...", r.url, gap.topic)
                                if bus:
                                    bus.emit(
                                        HookEventEmit(
                                            kind="pretool",
                                            payload={
                                                "panel_id": "auto_learner",
                                                "tool_name": "WebSurfer",
                                                "tool_input": {"command": f"Surfing: {r.url}"},
                                            },
                                        ),
                                    )
                                # task 19: `surf` 의 결과는 **모델의 주장**이었다(모델이 없으면 `[Mock Data]`
                                # 였고, 그것도 50자만 넘으면 "학습한 내용" 으로 소비됐다). 이제 **측정으로
                                # 확인된** 작업만 지식으로 쓴다 — 확인되지 않으면 검색 스니펫으로 물러선다.
                                outcome = await surfer.run_task(
                                    r.url,
                                    _verified_page_goal(gap.topic, r.url),
                                    budget=TaskBudget(action_budget=3, deadline_seconds=120),
                                )
                                if outcome.status is not TaskStatus.SUCCEEDED:
                                    logger.info(
                                        "[AutoLearn] unverified page for '%s': %s(%s) %s",
                                        gap.topic,
                                        outcome.status.value,
                                        outcome.code,
                                        outcome.reason,
                                    )
                                all_results.append(_knowledge_from_outcome(outcome, r.snippet, r.url))

                    if not all_results:
                        logger.info("[AutoLearn] No valid surfing results for: %s", gap.topic)
                        continue

                    # 검색 결과 합산
                    combined = "\n\n".join(all_results)

                    if bus:
                        bus.emit(
                            HookEventEmit(
                                kind="pretool",
                                payload={
                                    "panel_id": "auto_learner",
                                    "tool_name": "Synthesizer",
                                    "tool_input": {"command": f"Summarizing: {gap.topic}"},
                                },
                            ),
                        )

                    # Synthesizer (DeepSeek-V4)를 통한 요약 및 교차 검증
                    summary = self._summarize_results(gap.topic, combined)

                    # KI에 저장
                    ki_id = self._save_to_ki(gap.topic, summary, gap.search_queries)

                    learned.append(
                        LearnedKnowledge(
                            topic=gap.topic,
                            summary=summary,
                            sources=gap.search_queries,
                            learned_at=datetime.now(UTC).isoformat(),
                            ki_id=ki_id,
                        ),
                    )

                    logger.info("[AutoLearn] Synthesized: %s (%s chars)", gap.topic, len(summary))

                except Exception:
                    logger.exception("[AutoLearn] Failed to learn about '%s'", gap.topic)
            await search_engine.close()
            if bus:
                # role/task_type는 kanban_api의 AgentTurnEnded 구독자가 사용
                bus.emit(
                    HookEventEmit(
                        kind="agent-turn-end",
                        payload={
                            "panel_id": "auto_learner",
                            "role": "AutoLearner",
                            "task_type": "Vibe Coding Pipeline",
                        },
                    ),
                )

        # Execute async pipeline
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Already inside an event loop (e.g. uvicorn) — run in a separate thread
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, _run_vibe_coding_pipeline())
                try:
                    future.result(timeout=120)
                except Exception:
                    logger.exception("[AutoLearn] Pipeline failed in thread")
        else:
            asyncio.run(_run_vibe_coding_pipeline())

        return learned

    def _summarize_results(self, topic: str, search_results: str) -> str:
        """검색 결과를 LLM으로 요약합니다. LLM 없으면 원문 반환."""
        if not self.manager:
            # LLM 없으면 원문 잘라서 반환
            return search_results[:2000]

        try:
            prompt = (
                f"Summarize the following web search results about '{topic}' "
                f"into a concise, actionable knowledge note (max 500 words).\n\n"
                f"Search Results:\n{search_results[:4000]}\n\n"
                f"Write a clear, structured summary in the language that matches the topic."
            )
            summary = self._generate_with_manager(
                prompt,
                max_tokens=800,
                temperature=0.3,
                role_name="knowledge_synthesizer",
            )
            if summary is None:
                return search_results[:2000]
            summary = re.sub(r"<think>.*?</think>", "", summary, flags=re.DOTALL).strip()
            return summary if summary else search_results[:2000]
        except Exception:
            logger.exception("[AutoLearn] Summarization failed")
            return search_results[:2000]

    def _save_to_ki(self, topic: str, summary: str, sources: list[str]) -> str:
        """학습된 지식을 KIEngine에 저장합니다."""
        ki_id = f"autolearn_{hashlib.sha256(topic.encode()).hexdigest()[:12]}"

        if self.ki_engine:
            self.ki_engine.save_ki(
                ki_id,
                {
                    "title": f"[AutoLearn] {topic}",
                    "summary": summary,
                    "sources": sources,
                    "learned_at": datetime.now(UTC).isoformat(),
                    "type": "auto_learned",
                    "artifacts": [],
                },
            )

        return ki_id

    def format_context(self, learned: list[LearnedKnowledge]) -> str:
        """학습된 지식을 LLM 컨텍스트 주입용 텍스트로 포맷합니다."""
        if not learned:
            return ""

        lines = ["\n<auto_learned_context>"]
        lines.append("# 자동 학습된 최신 정보 (웹 검색 기반)")
        lines.append("")

        for item in learned:
            lines.append(f"## {item.topic}")
            lines.append(f"*학습 시각: {item.learned_at}*")
            lines.append(f"*출처: {', '.join(item.sources[:3])}*")
            lines.append("")
            lines.append(item.summary[:1500])
            lines.append("")

        lines.append("</auto_learned_context>")
        return "\n".join(lines)
