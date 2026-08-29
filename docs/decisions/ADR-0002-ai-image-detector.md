# ADR-0002 — AI-generated-image detector

**Status:** accepted (M4)

## Context
Fraudulent "damage" returns increasingly use AI-generated photos. We need a
detector that flags a likely-AI image as **one** signal into escalation — never a
lone auto-deny (CLAUDE.md). No universal-winner detector exists in 2026; the pick
is empirical on a small labeled sample.

## The bake-off
`ml/detector_bakeoff/run.py` builds a labeled sample and scores candidates:

- **real/** — real product photos pulled from MinIO (the seeded catalog images).
- **ai/** — AI-generated "product damage" photos from the **OpenAI image API**
  (`openai/gpt-image-1`, via Bifrost). This is a real paid call and the only
  sanctioned way to get genuine AI images locally — generating them with a local
  diffusion model is ruled out by non-negotiable #5 (no hosted inference for
  local models, and we don't ship a diffusion model).

Candidates scored (HF `image-classification`):
`Organika/sdxl-detector`, `umm-maybe/AI-image-detector`,
`haywoodsloan/ai-image-detector-deploy`.

Metric: accuracy at a 0.5 AI-class threshold + the mean-score separation between
the ai/ and real/ sets (n = 6 AI + 6 real; regenerate with
`docker compose run --rm worker python -m ml.detector_bakeoff.run`).

Run of 2026-08-29 (`ml/detector_bakeoff/bakeoff_results.json`):

| model | mean AI score | mean real score | accuracy@0.5 | separation |
|---|---|---|---|---|
| `Organika/sdxl-detector` | 0.999 | 0.512 | 0.75 | 0.49 |
| `umm-maybe/AI-image-detector` | 0.145 | 0.084 | 0.50 | 0.06 |
| **`haywoodsloan/ai-image-detector-deploy`** | **0.991** | **0.173** | **0.92** | **0.82** |

`Organika/sdxl-detector` flags AI images confidently but also scores real product
photos ~0.5 (false positives). `umm-maybe` barely separates the classes.
`haywoodsloan/ai-image-detector-deploy` cleanly separates them.

## Decision
Wire **`haywoodsloan/ai-image-detector-deploy`** via `RG_AI_DETECTOR`. Loaded
lazily on CPU in `pipeline/models_local.py`; its score feeds the **Image** node
only.

## How it's used (never a lone deny)
The Image node reports `ai_generated_score` alongside the CLIP similarity. The
Decision agent's prompt is explicit: a high AI-generated score pushes toward
**escalate**, never a standalone denial. `scripts/run_scenarios.py` A3 exercises
this; the score is in the case export and the live trace.

## Consequences
- One extra ~300 MB model, CPU, lazy — no RAM cost until the first image check.
- The sample is small (bake-off, not an ongoing eval harness). Re-run it if the
  detector is swapped.
