"""Push every worker/pipeline/prompts/*.md to Langfuse as a `production` prompt.

Idempotent: a new Langfuse version is created only when the file body differs
from the current `production` version. Run after `make up` (or as part of
`make m4-setup` / `make sync-prompts`):

    docker compose run --rm worker python -m pipeline.sync_prompts
"""
from __future__ import annotations

import logging
import pathlib

from pipeline.observability import lf
from pipeline.prompts.registry import read_file

_DIR = pathlib.Path(__file__).parent / "prompts"


def _current(client, name: str) -> str | None:
    """Body of the live `production` prompt, or None if it doesn't exist yet.
    The SDK logs an ERROR line for the expected first-run 404 — suppress ERROR
    globally for just this probe (CRITICAL still surfaces real failures)."""
    logging.disable(logging.ERROR)
    try:
        cur = client.get_prompt(name, label="production", cache_ttl_seconds=0,
                                max_retries=1)
        return cur.prompt if isinstance(cur.prompt, str) else None
    except Exception:  # noqa: BLE001 — not found yet, or a Langfuse hiccup
        return None
    finally:
        logging.disable(logging.NOTSET)


def main() -> None:
    client = lf()
    pushed = 0
    for md in sorted(_DIR.glob("*.md")):
        name = md.stem
        body, fver = read_file(name)
        cur = _current(client, name)
        if cur is not None and cur.strip() == body.strip():
            print(f"  {name}: up to date")
            continue
        p = client.create_prompt(name=name, prompt=body, type="text",
                                 labels=["production"],
                                 commit_message=f"sync from {name}.md v{fver}")
        pushed += 1
        print(f"  {name}: pushed -> lf v{p.version}")
    client.flush()
    print(f"sync_prompts: {pushed} prompt(s) pushed")


if __name__ == "__main__":
    main()
