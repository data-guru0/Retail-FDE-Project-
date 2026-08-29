"""Every prompt .md under worker/pipeline/prompts/ must start with a
`version: <hash-or-int>` line, and a changed prompt must change that line.
Run as a pre-commit hook (staged vs HEAD).
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

PROMPTS = pathlib.Path("worker/pipeline/prompts")


def head_version(path: str) -> str | None:
    try:
        blob = subprocess.run(
            ["git", "show", f"HEAD:{path}"], capture_output=True, text=True, check=True
        ).stdout
    except subprocess.CalledProcessError:
        return None
    return _version_line(blob)


def _version_line(text: str) -> str | None:
    for line in text.splitlines()[:5]:
        if line.lower().startswith("version:"):
            return line.split(":", 1)[1].strip()
    return None


def main() -> int:
    if not PROMPTS.exists():
        return 0
    bad = []
    for f in PROMPTS.glob("**/*.md"):
        cur = _version_line(f.read_text())
        if cur is None:
            bad.append(f"{f}: missing `version:` header line")
            continue
        old = head_version(str(f).replace("\\", "/"))
        if old is not None and old == cur:
            staged = subprocess.run(
                ["git", "diff", "--cached", "--name-only", "--", str(f)],
                capture_output=True, text=True,
            ).stdout.strip()
            body_changed = subprocess.run(
                ["git", "diff", "--cached", "--", str(f)], capture_output=True, text=True
            ).stdout
            if staged and body_changed:
                bad.append(f"{f}: content changed but `version:` ({cur}) did not")
    for b in bad:
        print(b, file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
