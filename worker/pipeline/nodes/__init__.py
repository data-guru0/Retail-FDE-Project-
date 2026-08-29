"""LangGraph pipeline nodes.

CLAUDE.md's layout sketches one file per node (data_quality.py, planner.py, …).
They are consolidated here into `agents.py` (≈250 lines, 9 node functions read
top-to-bottom) with the shared machinery in `base.py`. GovernanceGate — the only
finalizer — is `pipeline/governance.py`. The graph wiring is `pipeline/graph.py`.

    agents.data_quality   agents.planner   agents.intake   agents.policy
    agents.image          agents.behavior  agents.decision agents.critic
    agents.explanation    governance.run

Each node writes an `agent_runs` row and streams `agent_run_events`; every LLM
call enforces the per-agent model grant (`models_config.assert_grant`).
"""
