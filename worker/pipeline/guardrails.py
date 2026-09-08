"""Validate LLM JSON against a schema. Extraction/repair of the raw text is done
by `json-repair` (handles markdown fences, trailing junk, truncation, unquoted
keys). If the repaired object still fails the schema, one real LLM repair
round-trip hands the model its own bad output + the validation error.
"""
from __future__ import annotations

from json_repair import repair_json
from jsonschema import Draft202012Validator

from pipeline.llm import LLMResult, chat


def _extract_json(text: str) -> dict:
    obj = repair_json(text, return_objects=True)
    if isinstance(obj, list) and obj:
        obj = obj[0]
    if not isinstance(obj, dict) or not obj:
        raise ValueError(f"no JSON object in model output: {text[:200]}")
    return obj


def parse_validated(
    result: LLMResult,
    schema: dict,
    *,
    role: str,
    system: str,
    user: str,
    agent: str | None = None,
) -> tuple[dict, LLMResult]:
    """Returns (parsed_obj, final_result). final_result is the repaired call if one
    was needed (so tokens/cost/latency reflect the real total)."""
    validator = Draft202012Validator(schema)
    try:
        obj = _extract_json(result.text)
        errs = sorted(validator.iter_errors(obj), key=str)
        if not errs:
            return obj, result
        problem = "; ".join(e.message for e in errs[:5])
    except ValueError as e:
        problem = str(e)

    repair = chat(
        role,
        system,
        f"{user}\n\nYour previous reply was invalid: {problem}\n"
        f"Previous reply:\n{result.text}\n\n"
        f"Return ONLY valid JSON matching the schema. No prose, no code fences.",
        agent=agent,
        max_tokens=1400,
    )
    obj = _extract_json(repair.text)
    Draft202012Validator(schema).validate(obj)  # raises if still bad — no third try
    merged = LLMResult(
        text=repair.text,
        model=repair.model,
        tokens_in=result.tokens_in + repair.tokens_in,
        tokens_out=result.tokens_out + repair.tokens_out,
        cost_usd=round(result.cost_usd + repair.cost_usd, 6),
        latency_ms=result.latency_ms + repair.latency_ms,
        raw=repair.raw,
    )
    return obj, merged
