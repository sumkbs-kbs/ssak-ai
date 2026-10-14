"""Orchestrator 패키지 — CEO 기반 멀티 에이전트 오케스트레이터.

사용자 명령 → CEO 접수/분석 → 역할별 위임 → 결과 종합 → 스트리밍 응답

핵심 구조:
  1) CEO가 태스크 유형을 판별 (simple_chat / coding / reasoning / complex)
  2) 유형에 따라 최적의 역할(WORKER, ENG_MANAGER 등)과 모델을 자동 매핑
  3) 위임된 에이전트가 실제 작업 수행 (도구 호출 포함)
  4) CEO가 최종 결과를 종합하여 사용자에게 스트리밍
"""

from antigravity_k.engine.orchestrator.agent import OrchestratorAgent

__all__ = ["OrchestratorAgent"]
