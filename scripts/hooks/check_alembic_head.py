"""Fail if alembic has more than one head (unmerged migration branches)."""
from __future__ import annotations

import pathlib
import re
import sys

versions = pathlib.Path("backend/alembic/versions")
revs, downs = set(), set()
for f in versions.glob("*.py"):
    txt = f.read_text()
    m = re.search(r"^revision\s*=\s*['\"]([^'\"]+)['\"]", txt, re.M)
    d = re.search(r"^down_revision\s*=\s*(?:['\"]([^'\"]+)['\"]|None)", txt, re.M)
    if m:
        revs.add(m.group(1))
    if d and d.group(1):
        downs.add(d.group(1))

heads = revs - downs
if len(heads) > 1:
    print(f"multiple alembic heads: {heads}", file=sys.stderr)
    sys.exit(1)
print(f"alembic head ok: {heads or '(none yet)'}")
