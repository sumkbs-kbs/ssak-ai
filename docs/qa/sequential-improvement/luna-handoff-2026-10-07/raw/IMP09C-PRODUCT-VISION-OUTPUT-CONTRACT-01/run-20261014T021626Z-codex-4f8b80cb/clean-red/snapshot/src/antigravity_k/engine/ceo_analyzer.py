"""Ssak-Ai: CEO 분석 엔진 (CEOAnalyzer).

==========================================
I-1 리팩터링: Orchestrator에서 분리된 CEO 태스크 분류 로직.
LLM 스트리밍으로 사용자 의도를 분석하고, JSON/키워드 폴백으로 task_type/delegate_to를 결정합니다.
"""

import json
import logging
import re
from collections.abc import Generator, Iterable
from typing import Protocol, cast

logger = logging.getLogger(__name__)

JsonObject = dict[str, object]


class _ModelManagerLike(Protocol):
    def stream_generate(
        self,
        *,
        prompt: str,
        target: str,
        max_tokens: int,
        response_format: str | None = None,
    ) -> Iterable[str]: ...


def ceo_analyze(
    user_message: str,
    target_model: str,
    ceo_prompt_template: str,
    model_manager: object | None,
) -> Generator[str | JsonObject, None, None]:
    """CEO가 사용자 메시지를 분석하여 태스크 유형과 위임 대상을 결정합니다.

    스트리밍으로 분석 과정을 출력하며, 마지막에 결과를 dict로 yield합니다.

    Args:
        user_message: 사용자 입력 메시지
        target_model: 지정된 모델 (없으면 기본 모델 사용)
        ceo_prompt_template: CEO 역할 프롬프트 템플릿
        model_manager: ModelManager 인스턴스

    """
    # orchestrator-swarm 또는 target_model 사용
    ceo_model = target_model if target_model and target_model != "default" else "orchestrator-swarm"

    ceo_prompt = f"{ceo_prompt_template}\n\nUser request: {user_message}"

    # 1. Pre-routing (Short-circuit): 단순 인사나 명확한 키워드는 LLM 호출 없이 즉시 우회
    # (질문어 "어떻게"/"뭐야"는 코딩 등 실작업 문장에도 쓰이므로 단축 회로에서
    # 제외하고, 충분히 짧은 문장일 때만 우회한다)
    pre_routing_result = _keyword_fallback(user_message, user_message) if len(user_message) < 40 else None
    if pre_routing_result and pre_routing_result.get("task_type") == "simple_chat":
        logger.info("CEO Pre-routing: Short-circuited to simple_chat based on keywords.")
        yield pre_routing_result
        return

    try:
        response_text = ""
        if model_manager is None:
            raise RuntimeError("Model manager unavailable")
        manager = cast(_ModelManagerLike, model_manager)
        # ModelManager의 stream_generate를 사용하여 콤보/단일 모델 라우팅을 자동 처리
        # max_tokens=512는 thinking 모델이 <think>에 예산을 모두 쓰면 JSON이
        # 끊긴다 — 추론 여유를 포함해 상향한다.
        # response_format="json": Ollama 네이티브 문법 제약 디코딩으로 라우팅
        # JSON을 강제한다 (제어 평면은 항상 no-think이므로 thinking 충돌 없음).
        for chunk in manager.stream_generate(
            prompt=ceo_prompt,
            target=ceo_model,
            max_tokens=2048,
            response_format="json",
        ):
            response_text += chunk
            yield chunk

        # thinking 모델의 <think> 블록은 분류 대상이 아니다 — 제거 후 파싱
        raw_text = re.sub(r"<think>.*?</think>", "", response_text, flags=re.DOTALL).strip()

        # JSON 추출 — 3단계 전략
        parsed = _extract_task_json(raw_text)

        if parsed:
            yield parsed
            return

        # 3차: 키워드 기반 폴백 — 모델 출력이 아니라 "사용자 요청"을 분류한다
        keyword_result = _keyword_fallback(user_message, user_message)
        if keyword_result:
            yield keyword_result
            return

        logger.warning("CEO analysis: no JSON found in response")
    except Exception as e:
        logger.error("CEO analysis failed: %s", e, exc_info=True)

    # 최종 폴백: 단순 대화로 처리
    yield {
        "task_type": "simple_chat",
        "delegate_to": "SELF",
        "reasoning": "CEO analysis failed, fallback to direct response",
        "refined_prompt": user_message,
    }


def _extract_task_json(raw_text: str) -> JsonObject | None:
    """Raw 텍스트에서 task_type이 포함된 JSON 객체를 추출합니다."""
    # 1차: JSONDecoder.raw_decode — 중첩 {} 처리 가능
    decoder = json.JSONDecoder()
    for i, ch in enumerate(raw_text):
        if ch == "{":
            try:
                decoded, _end_idx = cast(tuple[object, int], decoder.raw_decode(raw_text, i))
                obj = _as_json_object(decoded)
                if obj is not None and "task_type" in obj:
                    logger.info(
                        "CEO Analysis (raw_decode): type=%s, delegate=%s",
                        obj.get("task_type"),
                        obj.get("delegate_to"),
                    )
                    return obj
            except json.JSONDecodeError:
                continue

    # 2차: 정규식 폴백
    json_match = re.search(r'\{[^{}]*"task_type"\s*:\s*"[^"]*"[^{}]*\}', raw_text, re.DOTALL)
    if json_match:
        try:
            return _as_json_object(cast(object, json.loads(json_match.group())))
        except json.JSONDecodeError as je:
            logger.warning("CEO JSON decode error: %s", je)

    return None


_KEYWORD_MAP = [
    (
        ["안녕", "소개", "누구", "인사", "대화", "얘기"],
        "simple_chat",
        "SELF",
    ),
    (
        ["coding", "code", "function", "함수", "코드", "작성", "파일", "구현"],
        "coding",
        "WORKER",
    ),
    (["review", "리뷰", "검토", "점검"], "review", "QA"),
    (["design", "디자인", "ui", "ux", "레이아웃"], "design", "DESIGNER"),
    (
        ["분석", "analyze", "추론", "reason", "설명", "explain"],
        "reasoning",
        "ENG_MANAGER",
    ),
]


def _as_json_object(value: object) -> JsonObject | None:
    if not isinstance(value, dict):
        return None
    raw_mapping = cast(dict[object, object], value)
    result: JsonObject = {}
    for key, item in raw_mapping.items():
        if not isinstance(key, str):
            return None
        result[key] = item
    return result


def _keyword_fallback(raw_text: str, user_message: str) -> JsonObject | None:
    """키워드 기반 의도 감지 — JSON 파싱 실패 시 사용."""
    lower = raw_text.lower()
    for keywords, task_type, delegate in _KEYWORD_MAP:
        if any(kw in lower for kw in keywords):
            logger.info("CEO fallback: detected %s from keywords", task_type)
            return {
                "task_type": task_type,
                "delegate_to": delegate,
                "reasoning": "keyword-based detection",
                "refined_prompt": user_message,
            }
    return None
