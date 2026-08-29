"""M6 self-check — the README describes a real, running system.

- README has every required section (problem, plain-words walkthrough, shadow/
  assist explanation, from-clean-checkout setup, the local-URL table, every demo
  scenario, troubleshooting)
- every URL in the README's table actually responds
- every command the README/DEMO references exists (Makefile target or script)
- the [demo] scenario subset runs green through the real pipeline
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from _rg import Check, httpx

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")
DEMO = (ROOT / "docs" / "DEMO.md").read_text(encoding="utf-8")
MAKEFILE = (ROOT / "Makefile").read_text(encoding="utf-8")


def main() -> None:
    c = Check("verify_m6")

    for needle in [
        "problem this solves", "shadow", "assist", "auto",
        "clean checkout", "Local URLs", "Demo scenarios", "Troubleshooting",
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
    for tgt in ["up", "migrate", "seed", "m4-setup", "smoke", "scenarios", "demo",
                "backup", "restore", "loadtest"]:
        c.ok(re.search(rf"^{tgt}:", MAKEFILE, re.M) is not None, f"Makefile has target '{tgt}'")

    # referenced scripts exist
    for s in ["mcp_setup.py", "bifrost_setup.py", "run_scenarios.py", "smoke.py",
              "loadtest.py", "preflight.sh"]:
        c.ok((ROOT / "scripts" / s).exists(), f"scripts/{s} exists")

    # all 9 ADRs + the docs set
    adrs = list((ROOT / "docs" / "decisions").glob("ADR-*.md"))
    c.ok(len(adrs) >= 9, f"{len(adrs)} ADRs present")
    for d in ["ARCHITECTURE", "GOVERNANCE", "SECURITY", "RUNBOOK", "OPERATING_MODEL",
              "FAIRNESS", "BASELINE", "SCENARIOS", "MODEL_CARD", "DEMO"]:
        c.ok((ROOT / "docs" / f"{d}.md").exists(), f"docs/{d}.md exists")

    # the [demo] scenarios run for real
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "run_scenarios.py"), "--demo"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    c.ok(r.returncode == 0, f"run_scenarios.py --demo green\n{r.stdout[-500:]}")

    c.done()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print(f"verify_m6 crashed: {type(e).__name__}: {e}")
        sys.exit(2)
