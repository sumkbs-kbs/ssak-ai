"""Response verification handlers for the orchestrator state graph."""

import logging
from collections.abc import Callable, Generator
from typing import Protocol, cast

from antigravity_k.engine import multimodal
from antigravity_k.engine.orchestrator_handler_config import OrchestratorConfigLike, cov_settings
from antigravity_k.engine.state_graph import AgentState, StateContext

logger = logging.getLogger("antigravity_k.engine.orchestrator_handlers")


class _OrchestratorLike(Protocol):
    manager: object | None


def cov_verify_handler(ctx: StateContext, orch: object) -> Generator[str, None, None]:
    """Chain-of-Verification: 에이전트 응답을 자기검증합니다.

    규칙 기반 검증 (구문 오류, 자기 모순, 반복)을 수행하고,
    문제 발견 시 응답에 경고를 추가합니다.
    """
    cov_enabled, verify_model, min_len, threshold, max_iter = cov_settings(cast(OrchestratorConfigLike, orch))
    if not cov_enabled:
        return  # amplification.cov.enabled=false 시 검증 스킵
    if not ctx.agent_output or len(ctx.agent_output.strip()) < min_len:
        return  # 짧은 응답은 검증 스킵

    try:
        from antigravity_k.engine.chain_of_verification import ChainOfVerification

        orchestrator = cast(_OrchestratorLike, orch)
        cov = cast(object | None, getattr(orchestrator, "_cov_engine", None))
        if cov is None:
            manager = orchestrator.manager
            generate_fn_impl: Callable[[str], str] | None
            if manager is not None and callable(getattr(manager, "generate", None)):
                generate_impl = cast(Callable[..., str], getattr(manager, "generate"))

                def manager_generate(prompt: str) -> str:
                    return generate_impl(
                        prompt,
                        target=verify_model,
                        max_tokens=4096,
                        temperature=0.2,
                    )

                generate_fn_impl = manager_generate
            else:
                generate_fn_impl = None

            cov = ChainOfVerification(
                generate_fn=generate_fn_impl,
                complexity_threshold=threshold,
                min_response_length=min_len,
                max_revise_iterations=max_iter,
            )
            setattr(orchestrator, "_cov_engine", cov)

        cov = cast(ChainOfVerification, cov)
        trace = cov.run(ctx.user_message, ctx.agent_output)

        if trace.skipped:
            return

        if trace.revised_response and trace.revised_response != ctx.agent_output:
            ctx.agent_output = trace.revised_response
            yield "✅ 자동 수정 적용 완료\n"

        if trace.verification_result and trace.verification_result.issues_found:
            severity = trace.verification_result.severity
            issues = trace.verification_result.issues_found
            yield f"\n\n🔍 **[자기검증]** {len(issues)}건 감지 (severity={severity}):\n"
            for issue in issues[:3]:
                yield f"  - {issue}\n"
            if not trace.verification_result.passed:
                ctx.validation_passed = False

            logger.info("[CoV] Verified: passes=%s, severity=%s, issues=%s", trace.total_passes, severity, len(issues))
        else:
            logger.debug("[CoV] Verification passed — no issues")
            ctx.validation_passed = True

        from antigravity_k.tools.search_quality_evaluator import (
            citation_sources_from_context,
            evaluate_citations,
        )

        # NX-09-F03: content 가 파트 배열일 수 있다(첨부) — join 전에 반드시 텍스트로 접는다.
        evidence_context = "\n".join(
            [
                ctx.rag_context,
                *(multimodal.flatten_content(message.get("content", "")) for message in ctx.messages),
                *(multimodal.flatten_content(message.get("content", "")) for message in ctx.custom_messages),
            ],
        )
        citation_sources = citation_sources_from_context(evidence_context)
        if citation_sources:
            import hashlib

            output_sha = hashlib.sha256(ctx.agent_output.encode("utf-8")).hexdigest()[:16]
            cached_eval = ctx.analysis.get("citation_evaluation")
            cached_sha = ctx.analysis.get("citation_evaluation_output_sha")
            if isinstance(cached_eval, dict) and cached_sha == output_sha:
                # 도구 루프가 동일 출력에 대해 이미 인용 평가를 수행했다 —
                # 재평가(동일 LLM 컨텍스트 재스캔) 없이 결과를 재사용한다.
                claim_count = int(cached_eval.get("claim_count", 0) or 0)
                citation_failed = claim_count and (
                    float(cached_eval.get("citation_coverage", 1.0) or 1.0) < 1.0
                    or int(cached_eval.get("unknown_citation_count", 0) or 0) > 0
                    or int(cached_eval.get("unacknowledged_conflict_count", 0) or 0) > 0
                )
                citation_failed = bool(citation_failed)
                unsupported = int(cached_eval.get("unsupported_claim_count", 0) or 0)
            else:
                citation_report = evaluate_citations(ctx.agent_output, citation_sources)
                ctx.analysis["citation_evaluation"] = citation_report.to_dict()
                ctx.analysis["citation_evaluation_output_sha"] = output_sha
                citation_failed = citation_report.claim_count and (
                    citation_report.citation_coverage < 1.0
                    or citation_report.unknown_citation_count > 0
                    or citation_report.unacknowledged_conflict_count > 0
                )
                unsupported = citation_report.unsupported_claim_count
            if citation_failed:
                ctx.validation_passed = False
                yield (
                    f"\n\n🔗 **[근거 검증]** {unsupported}개 주장에 "
                    f"충분한 출처 근거가 없거나 출처 충돌이 확인되었습니다. 답변을 다시 검토합니다.\n"
                )
    except Exception as e:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK - retry boundary
        logger.exception("Unhandled exception")
        logger.debug("CoV verification skipped: %s", e)
        ctx.validation_passed = False
        ctx.analysis["cov_error"] = "verification_failed"
        yield "\n\n⚠️ **[자기검증 실패]** 검증기를 완료하지 못해 재시도가 필요합니다.\n"


# ─── QUALITY_CHECK 핸들러 ────────────────────────────────────────


def quality_check_handler(ctx: StateContext, orch: object) -> Generator[str, None, None]:
    """품질 확인 및 에러 복구 루프백 처리."""
    _ = orch
    if not getattr(ctx, "validation_passed", True) and ctx.retry_count < ctx.max_retries:
        ctx.retry_count += 1
        yield f"\n\n🔄 **[에러 복구 루프]** 심각한 오류 감지. 자가 수정을 시도합니다 (재시도 {ctx.retry_count}/{ctx.max_retries})\n"

        # 실패 피드백 주입
        ctx.custom_messages.append(
            {
                "role": "user",
                "content": "[시스템 피드백] 이전 답변에서 심각한 검증 오류가 발견되었습니다. 지시사항과 모순점을 다시 확인하고 올바르게 수정한 최종 답변을 작성하세요.",
            }
        )

        setattr(ctx, "_loop_back", True)
        ctx.validation_passed = True  # 다음 루프를 위해 초기화
    else:
        setattr(ctx, "_loop_back", False)
        if not getattr(ctx, "validation_passed", True):
            yield f"\n\n⚠️ **[에러 복구 실패]** 최대 재시도({ctx.max_retries}회)에 도달했습니다. 마지막 결과를 유지합니다.\n"


def quality_check_decision(ctx: StateContext) -> AgentState:
    """QUALITY_CHECK에서 루프백 여부를 결정합니다."""
    if bool(getattr(ctx, "_loop_back", False)):
        # 원 실행 노드로 되돌린다 — MAX/PIPELINE/DEBATE로 실행된 작업을
        # 단일 에이전트로 재시도하면 전략이 조용히 강등된다.
        origin = getattr(ctx, "execution_origin", AgentState.AGENT_EXECUTE)
        return origin if isinstance(origin, AgentState) else AgentState.AGENT_EXECUTE
    return AgentState.MEMORY_SAVE
