# ADR-0010 — Groq model set (the CLAUDE.md llama-3.x ids are gone)

**Status:** accepted (M3)

## Context
CLAUDE.md's stack table names `llama-3.3-70b-versatile` (policy/behavior) and
`llama-3.1-8b-instant` (intake) on Groq, with a Bifrost fallback to
`openai/gpt-oss-120b` → `gpt-4o-mini`. INSTRUCTIONS flags this as a known unknown:
*"llama-3.3-70b-versatile carried a mid-2026 deprecation notice… If Groq is fully
unavailable, switch the primary to openai/gpt-oss-120b and note it."*

At build time (2026-08-29) `GET https://api.groq.com/openai/v1/models` for our key
returns **neither** llama id. Groq is **not** down — it now serves the `openai/gpt-oss-*`
family, `qwen/qwen3.*`, `groq/compound`, and audio models.

## Decision
Model ids are **config-driven** (`worker/pipeline/models_config.py`, overridable per
role via `RG_MODEL_<ROLE>` env). Role → default:

| role | default | used by |
|---|---|---|
| `fast` | `groq/openai/gpt-oss-20b` | intake, data-quality |
| `reason` | `groq/openai/gpt-oss-120b` | policy, behavior, M3 decision |
| `deep` | `openai/gpt-4o-mini` | decision, critic, explanation |
| `vision` | `openai/gpt-4o` | borderline image checks |
| `embed` | `openai/text-embedding-3-small` | policy RAG |

Bifrost fallback chains stay real: `reason`/`fast` → `openai/gpt-4o-mini`,
`deep` → `openai/gpt-4o`. A Groq 400 yields a genuine OpenAI completion — verified
in M3 (`review_return` fell back to `gpt-4o-mini` on one run and to a real
`groq/openai/gpt-oss-120b` completion on the next; both logged with real tokens).

## Consequences
- No literal model strings at call sites.
- If Groq restores the llama ids (or renames again), change one file / one env var.
- The `deep`/`vision` split keeps the expensive OpenAI models off the hot path.
