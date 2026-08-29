"""The LangGraph pipeline.

Data-quality gate -> Planner -> Intake -> Policy (RAG) -> [Image] -> Behavior ->
Decision -> Critic -> Explanation -> GovernanceGate.

If the data-quality gate fails, we skip straight to GovernanceGate, which
escalates "insufficient data" (never guesses). Image runs only when the Planner
kept it in the plan (a return photo AND a reference image exist).

Postgres checkpointer (schema `langgraph`) makes every run resumable and
inspectable; `worker/replay.py` uses it for deterministic single-node replay.
"""
from __future__ import annotations

import structlog
from langgraph.graph import END, StateGraph

from pipeline import governance
from pipeline.nodes import agents
from pipeline.settings import get_settings
from pipeline.state import PipelineState

log = structlog.get_logger()
_compiled = None
_saver_cm = None


def _after_dq(state: dict) -> str:
    return "planner" if state.get("data_quality", {}).get("ok") else "governance"


def _after_policy(state: dict) -> str:
    return "image" if "image" in state.get("plan", []) else "behavior"


async def get_graph():
    global _compiled, _saver_cm
    if _compiled is not None:
        return _compiled

    g = StateGraph(PipelineState)
    g.add_node("data_quality", agents.data_quality)
    g.add_node("planner", agents.planner)
    g.add_node("intake", agents.intake)
    g.add_node("policy", agents.policy)
    g.add_node("image", agents.image)
    g.add_node("behavior", agents.behavior)
    g.add_node("decision", agents.decision)
    g.add_node("critic", agents.critic)
    g.add_node("explanation", agents.explanation)
    g.add_node("governance", governance.run)

    g.set_entry_point("data_quality")
    g.add_conditional_edges("data_quality", _after_dq, {"planner": "planner", "governance": "governance"})
    g.add_edge("planner", "intake")
    g.add_edge("intake", "policy")
    g.add_conditional_edges("policy", _after_policy, {"image": "image", "behavior": "behavior"})
    g.add_edge("image", "behavior")
    g.add_edge("behavior", "decision")
    g.add_edge("decision", "critic")
    g.add_edge("critic", "explanation")
    g.add_edge("explanation", "governance")
    g.add_edge("governance", END)

    checkpointer = None
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        dsn = get_settings().database_url.replace("postgresql+psycopg://", "postgresql://")
        _saver_cm = AsyncPostgresSaver.from_conn_string(dsn)
        checkpointer = await _saver_cm.__aenter__()
        await checkpointer.setup()
        log.info("graph.checkpointer.postgres")
    except Exception as e:  # noqa: BLE001
        log.warning("graph.checkpointer.unavailable", error=f"{type(e).__name__}: {e}")

    _compiled = g.compile(checkpointer=checkpointer)
    return _compiled


async def run_pipeline(initial: dict) -> dict:
    graph = await get_graph()
    cfg = {"configurable": {"thread_id": initial["return_id"]}}
    final_state = await graph.ainvoke(initial, cfg)
    return final_state
