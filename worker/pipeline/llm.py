"""Thin LLM client: the OpenAI SDK pointed at Bifrost. No retry/fallback/circuit
logic here — Bifrost owns all of that (ADR-0007). We just pass the fallback list
and the per-agent virtual key, and record what came back.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from openai import OpenAI

from pipeline.models_config import fallbacks, model
from pipeline.settings import get_settings


@dataclass
class LLMResult:
    text: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: int
    raw: dict


def _client(virtual_key: str | None) -> OpenAI:
    s = get_settings()
    headers = {}
    if virtual_key:
        headers["x-bf-vk"] = virtual_key  # Bifrost virtual key header
    return OpenAI(base_url=f"{s.bifrost_url}/v1", api_key="bifrost", default_headers=headers)


def chat(
    role: str,
    system: str,
    user: str,
    *,
    virtual_key: str | None = None,
    max_tokens: int = 1200,
    temperature: float = 0.1,
    json_mode: bool = True,
) -> LLMResult:
    m = model(role)
    fb = fallbacks(role)
    extra: dict = {}
    if fb:
        extra["fallbacks"] = fb
    if json_mode:
        extra["response_format"] = {"type": "json_object"}

    start = time.perf_counter()
    resp = _client(virtual_key).chat.completions.create(
        model=m,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=max_tokens,
        temperature=temperature,
        extra_body=extra,
    )
    latency_ms = int((time.perf_counter() - start) * 1000)
    d = resp.model_dump()
    choice = d["choices"][0]["message"]
    text = choice.get("content") or choice.get("reasoning_content") or ""
    usage = d.get("usage") or {}
    used_model = d.get("model", m)
    cost = _cost(used_model, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))
    return LLMResult(
        text=text.strip(),
        model=used_model,
        tokens_in=usage.get("prompt_tokens", 0),
        tokens_out=usage.get("completion_tokens", 0),
        cost_usd=cost,
        latency_ms=latency_ms,
        raw=d,
    )


def chat_vision(*, role: str, system: str, text: str, image_bytes: bytes,
                virtual_key: str | None = None, max_tokens: int = 300) -> str:
    """Vision call via Bifrost. Image is inlined as a base64 data URL (OpenAI's
    servers can't reach our local MinIO)."""
    import base64

    b64 = base64.b64encode(image_bytes).decode()
    resp = _client(virtual_key).chat.completions.create(
        model=model(role),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": [
                {"type": "text", "text": text},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ]},
        ],
        max_tokens=max_tokens,
        temperature=0,
        extra_body={"fallbacks": fallbacks(role)} if fallbacks(role) else {},
    )
    m = resp.model_dump()["choices"][0]["message"]
    return (m.get("content") or m.get("reasoning_content") or "").strip()


# rough public prices (USD per 1M tokens) — good enough for the unit-economics view;
# Langfuse holds the authoritative figure per span.
_PRICES = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "openai/gpt-oss-120b": (0.15, 0.60),
    "openai/gpt-oss-20b": (0.05, 0.20),
    "text-embedding-3-small": (0.02, 0.0),
}


def _cost(model_id: str, tin: int, tout: int) -> float:
    key = model_id.split("/", 1)[-1] if model_id.startswith(("openai/", "groq/")) else model_id
    for k, (pin, pout) in _PRICES.items():
        if k in model_id or k == key:
            return round(tin / 1e6 * pin + tout / 1e6 * pout, 6)
    return 0.0
