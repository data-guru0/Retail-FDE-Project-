"""Run every verify_* + the audit-chain + security checks. `make smoke`.

The scenario catalog itself (docs/scenarios/*.md) is a manual, click-through
walkthrough for demos, not an automated check — see docs/scenarios/README.md.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
CHECKS = [
    "verify_m1.py", "verify_m2.py", "verify_m2_frontend.py",
    "verify_m3.py", "verify_m3_dlq.py",
    "verify_m4.py", "verify_audit_chain.py",
    "verify_security.py", "verify_m5.py",
    "verify_m6.py",
]


def main() -> None:
    only = sys.argv[1:]
    results = {}
    for name in CHECKS:
        if only and not any(o in name for o in only):
            continue
        print(f"\n{'=' * 60}\n{name}\n{'=' * 60}")
        t0 = time.time()
        rc = subprocess.run([sys.executable, str(HERE / name)]).returncode
        results[name] = (rc == 0, round(time.time() - t0, 1))

    print(f"\n{'=' * 60}\nSMOKE SUMMARY\n{'=' * 60}")
    ok = True
    for name, (passed, secs) in results.items():
        print(f"  {'PASS' if passed else 'FAIL'}  {name:26} {secs:>6}s")
        ok = ok and passed
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
