"""Shared node machinery: emit trace events, run an LLM agent (Bifrost + the
agent's virtual key), guardrail-validate, write agent_runs, record Langfuse.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass

import structlog

from pipeline import db
from pipeline.guardrails import parse_validated
from pipeline.llm import chat
from pipeline.observability import record_generation
from pipeline.prompts.registry import load, prompt_version

log = structlog.get_logger()

# Keycloak service-account subject per agent (recorded on agent_runs for identity).
SA_SUBJECT = {a: f"service-account-returnguard-agent-{a}" for a in
              ("planner", "intake", "policy", "image", "behavior",
               "decision", "critic", "explanation")}

# Bifrost virtual key per agent (spend cap / model scope). Falls back to no key.
def virtual_key(agent: str) -> str | None:
    return os.getenv(f"RG_BIFROST_VK_{agent.upper()}")


@dataclass
class RunCtx:
    return_id: str
    graph_run_id: str
    automation_level: str
    policy_version: int | None = None

    async def emit(self, state: dict, kind: str, agent: str, payload: dict) -> None:
        state["seq"] = state.get("seq", 0) + 1
        await db.add_event(self.return_id, self.graph_run_id, state["seq"], agent, kind, payload)


async def run_llm_agent(
    rc: RunCtx,
    state: dict,
    *,
    agent: str,
    prompt_name: str,
    role: str,
    facts: dict | str,
    schema: dict,
    max_tokens: int = 900,
    merge: dict | None = None,
) -> dict:
    """One agent turn: real LLM call -> validated JSON -> agent_runs row -> Langfuse.
    `merge` is applied deterministically over the parsed output before it is stored
    (for hard, non-LLM facts like the high-value flag)."""
    system, _, _ = load(prompt_name)
    user = facts if isinstance(facts, str) else json.dumps(facts, indent=2, default=str)
    input_hash = hashlib.sha256(user.encode()).hexdigest()
    vk = virtual_key(agent)

    await rc.emit(state, "node_start", agent, {"prompt": prompt_version(prompt_name), "role": role})
    result = chat(role, system, user, virtual_key=vk, max_tokens=max_tokens)
    parsed, result = parse_validated(
        result, schema, role=role, system=system, user=user, virtual_key=vk
    )
    if merge:
        parsed.update(merge)

    trace_id = record_generation(
        agent=agent, model=result.model, prompt=user, output=result.text,
        return_id=rc.return_id, graph_run_id=rc.graph_run_id,
        tokens_in=result.tokens_in, tokens_out=result.tokens_out, cost=result.cost_usd,
    )
    try:
        from pipeline.metrics import LLM_COST

        LLM_COST.inc(float(result.cost_usd))
    except Exception:  # noqa: BLE001
        pass
    conf = parsed.get("confidence")
    run_id = await db.insert_agent_run(
        return_id=rc.return_id, graph_run_id=rc.graph_run_id, agent=agent,
        sa_subject=SA_SUBJECT.get(agent), model=result.model,
        prompt_version=prompt_version(prompt_name), policy_version=rc.policy_version,
        automation_level=rc.automation_level, input_hash=input_hash,
        raw_response=result.text, parsed_output=parsed,
        confidence=round(float(conf), 3) if conf is not None else None,
        tokens_in=result.tokens_in, tokens_out=result.tokens_out,
        cost_usd=result.cost_usd, latency_ms=result.latency_ms,
        langfuse_trace_id=trace_id, error=None,
    )
    await rc.emit(state, "node_end", agent, {
        "agent_run_id": run_id, "model": result.model, "output": parsed,
        "tokens_in": result.tokens_in, "tokens_out": result.tokens_out,
        "cost_usd": result.cost_usd, "latency_ms": result.latency_ms,
    })
    return parsed


async def record_local_agent(
    rc: RunCtx, state: dict, *, agent: str, output: dict, model: str, latency_ms: int
) -> str:
    """agent_runs row for a non-LLM agent step (CLIP, sklearn, ring SQL)."""
    input_hash = hashlib.sha256(
        json.dumps(output, sort_keys=True, default=str).encode()
    ).hexdigest()
    run_id = await db.insert_agent_run(
        return_id=rc.return_id, graph_run_id=rc.graph_run_id, agent=agent,
        sa_subject=SA_SUBJECT.get(agent), model=model, prompt_version=None,
        policy_version=rc.policy_version, automation_level=rc.automation_level,
        input_hash=input_hash, raw_response=None, parsed_output=output,
        confidence=output.get("confidence"), tokens_in=0, tokens_out=0,
        cost_usd=0, latency_ms=latency_ms, langfuse_trace_id=None, error=None,
    )
    return run_id
