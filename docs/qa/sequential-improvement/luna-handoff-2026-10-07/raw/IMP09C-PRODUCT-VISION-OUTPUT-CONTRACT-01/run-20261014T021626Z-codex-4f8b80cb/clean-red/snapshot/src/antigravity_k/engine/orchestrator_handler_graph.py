"""State graph assembly for orchestrator handlers."""

from antigravity_k.engine.orchestrator_analysis_handlers import (
    ceo_analyze_handler,
    ceo_gate_decision,
    pre_route_handler,
    route_decision,
    route_handler,
)
from antigravity_k.engine.orchestrator_context_handlers import (
    auto_learn_handler,
    context_enrich_handler,
    init_handler,
    skill_match_handler,
)
from antigravity_k.engine.orchestrator_execution_handlers import (
    agent_execute_handler,
    agi_core_handler,
    debate_execute_handler,
    max_execute_handler,
    pipeline_execute_handler,
)
from antigravity_k.engine.orchestrator_memory_handler import memory_save_handler
from antigravity_k.engine.orchestrator_review_handler import code_review_handler
from antigravity_k.engine.orchestrator_verification_handlers import (
    cov_verify_handler,
    quality_check_decision,
    quality_check_handler,
)
from antigravity_k.engine.state_graph import AgentState, AgentStateGraph, build_default_graph


def build_orchestrator_graph() -> AgentStateGraph:
    """Assemble the production orchestrator state graph."""
    graph = build_default_graph()
    graph = graph.add_node(AgentState.INIT, init_handler)
    graph = graph.add_node(AgentState.CONTEXT_ENRICH, context_enrich_handler)
    graph = graph.add_node(AgentState.AUTO_LEARN, auto_learn_handler)
    graph = graph.add_node(AgentState.SKILL_MATCH, skill_match_handler)
    graph = graph.add_node(AgentState.CEO_ANALYZE, ceo_analyze_handler)
    graph = graph.add_node(AgentState.PRE_ROUTE, pre_route_handler)
    graph = graph.add_node(AgentState.ROUTE, route_handler)
    graph = graph.add_node(AgentState.AGENT_EXECUTE, agent_execute_handler)
    graph = graph.add_node(AgentState.CODE_REVIEW, code_review_handler)
    graph = graph.add_node(AgentState.MAX_EXECUTE, max_execute_handler)
    graph = graph.add_node(AgentState.PIPELINE_EXECUTE, pipeline_execute_handler)
    graph = graph.add_node(AgentState.DEBATE_EXECUTE, debate_execute_handler)
    graph = graph.add_node(AgentState.AGI_CORE, agi_core_handler)
    graph = graph.add_node(AgentState.COV_VERIFY, cov_verify_handler)
    graph = graph.add_node(AgentState.QUALITY_CHECK, quality_check_handler)
    graph = graph.add_node(AgentState.MEMORY_SAVE, memory_save_handler)
    graph = graph.add_conditional_edge(AgentState.ROUTE, route_decision)
    graph = graph.add_conditional_edge(AgentState.QUALITY_CHECK, quality_check_decision)
    # simple_chat 조기 차단 — 풍부화 프리룰(CONTEXT_ENRICH~PRE_ROUTE) 스킵
    graph = graph.add_conditional_edge(AgentState.CEO_ANALYZE, ceo_gate_decision)
    return graph
