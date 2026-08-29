"""Deterministic single-node replay.

Given a graph_run_id and a node name, rebuild that node's exact input from the
recorded agent_run_events and re-run just that node. Nothing is written to
`returns` — this is for debugging an agent's behaviour, not re-deciding a case.

Usage:
  docker compose run --rm worker python replay.py <graph_run_id> <node>
"""
from __future__ import annotations

import asyncio
import json
import sys

from pipeline import db
from pipeline.nodes import agents

NODES = {
    "data_quality": agents.data_quality, "planner": agents.planner, "intake": agents.intake,
    "policy": agents.policy, "image": agents.image, "behavior": agents.behavior,
    "decision": agents.decision, "critic": agents.critic, "explanation": agents.explanation,
}


async def rebuild_state(graph_run_id: str) -> dict:
    row = await db.fetchrow(
        "SELECT r.id::text AS rid FROM agent_runs ar JOIN returns r ON r.id = ar.return_id "
        "WHERE ar.graph_run_id = %(g)s LIMIT 1", {"g": graph_run_id}
    )
    if not row:
        raise SystemExit(f"no run {graph_run_id}")
    ctx = await db.get_review_context(row["rid"])
    state: dict = {
        "return_id": row["rid"], "graph_run_id": graph_run_id + "-replay",
        "automation_level": "shadow", "kill_switch": False,
        "category": ctx["category"], "context": ctx, "seq": 10_000, "errors": [],
    }
    # replay recorded node outputs into the state so a later node sees the same inputs
    runs = await db.fetchall(
        "SELECT agent, parsed_output FROM agent_runs WHERE graph_run_id = %(g)s "
        "AND parsed_output IS NOT NULL ORDER BY created_at", {"g": graph_run_id}
    )
    for r in runs:
        out = r["parsed_output"]
        if r["agent"] == "planner":
            state["plan"] = out.get("plan", [])
        elif r["agent"] in ("intake", "policy", "image", "behavior", "decision", "critic"):
            state[r["agent"]] = out
        elif r["agent"] == "explanation":
            state["explanation"] = out.get("explanation")
    return state


async def main() -> None:
    if len(sys.argv) != 3 or sys.argv[2] not in NODES:
        raise SystemExit(f"usage: replay.py <graph_run_id> <{'|'.join(NODES)}>")
    grid, node = sys.argv[1], sys.argv[2]
    await db.start()
    state = await rebuild_state(grid)
    print(f"replaying '{node}' for run {grid}\n")
    update = await NODES[node](state)
    print(json.dumps(update, indent=2, default=str))
    await db.stop()


if __name__ == "__main__":
    asyncio.run(main())
