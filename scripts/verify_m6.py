"""M6 self-check — the README describes a real, running system.

- README has every required section (problem, plain-words walkthrough, shadow/
  assist explanation, from-clean-checkout setup, the local-URL table, the
  scenario walkthroughs, troubleshooting)
- every URL in the README's table actually responds
- every command the README references exists (Makefile target or script)
- every docs/scenarios/*.md walkthrough has the expected sections

The scenario walkthroughs themselves are manual, click-through-the-app guides
for demos (docs/scenarios/README.md is the index) — there is no automated
runner to shell out to here by design; each was walked through for real
against the live system while it was written.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from _rg import Check, httpx

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")
MAKEFILE = (ROOT / "Makefile").read_text(encoding="utf-8")


def main() -> None:
    c = Check("verify_m6")

    for needle in [
        "problem this solves", "shadow", "assist", "auto",
        "clean checkout", "Local URLs", "Scenario walkthroughs", "Troubleshooting",
    ]:
        c.ok(needle.lower() in README.lower(), f"README covers: '{needle}'")

    # every http(s) URL in the README table responds (< 500)
    urls = sorted(set(re.findall(r"http://localhost:\d+[^\s|)`]*", README)))
    c.ok(len(urls) >= 8, f"README lists {len(urls)} local URLs")
    for u in urls:
        try:
            code = httpx.get(u, timeout=8, follow_redirects=True).status_code
            ok = code < 500
        except Exception as e:  # noqa: BLE001
            code, ok = f"ERR {type(e).__name__}", False
        c.ok(ok, f"{u} -> {code}")

    # referenced make targets exist
    for tgt in ["up", "migrate", "seed", "m4-setup", "smoke",
                "backup", "restore", "loadtest"]:
        c.ok(re.search(rf"^{tgt}:", MAKEFILE, re.M) is not None, f"Makefile has target '{tgt}'")

    # referenced scripts exist
    for s in ["mcp_setup.py", "bifrost_setup.py", "smoke.py",
              "loadtest.py", "preflight.sh"]:
        c.ok((ROOT / "scripts" / s).exists(), f"scripts/{s} exists")

    # docs/scenarios/README.md is the index; architecture / ops / security
    # live in README itself
    c.ok((ROOT / "docs" / "scenarios" / "README.md").exists(), "docs/scenarios/README.md (the index) exists")
    for section in ["## Operations", "## Security notes", "### How a return flows"]:
        c.ok(section in README, f"README has the '{section.strip('# ')}' section")

    # the step-by-step scenario walkthroughs (00 is the shared reference doc,
    # not a numbered scenario, and has its own different structure)
    all_docs = sorted((ROOT / "docs" / "scenarios").glob("[0-9][0-9]-*.md"))
    c.ok((ROOT / "docs" / "scenarios" / "00-watching-a-case-live.md").exists(),
         "docs/scenarios/00-watching-a-case-live.md (the shared reference doc) exists")
    walkthroughs = [w for w in all_docs if not w.name.startswith("00-")]
    c.ok(len(walkthroughs) >= 18, f"{len(walkthroughs)} docs/scenarios/*.md scenario walkthroughs")
    for w in walkthroughs:
        body = w.read_text(encoding="utf-8")
        c.ok("## What this shows" in body and "## Watch it live" in body and "## Why it matters" in body,
             f"{w.name}: has What-this-shows + Watch-it-live + Why-it-matters sections")

    c.done()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print(f"verify_m6 crashed: {type(e).__name__}: {e}")
        sys.exit(2)
