"""Batch re-run: re-review a window of returns through the current pipeline
(e.g. after a policy edit). Only touches returns still awaiting a human
(status in pending / in_review / escalated with no final_decision).

Usage:
  docker compose run --rm worker python reprocess.py --since 2026-08-01 \
    [--until 2026-08-29] [--policy-version 2] [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio

from arq.connections import RedisSettings, create_pool

from pipeline import db
from pipeline.settings import get_settings


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", required=True)
    ap.add_argument("--until", default=None)
    ap.add_argument("--policy-version", type=int, default=None,
                    help="only returns last decided under a different policy version")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    await db.start()
    clauses = ["r.created_at >= %(since)s", "r.final_decision IS NULL",
               "r.status IN ('pending','in_review','escalated')"]
    params: dict = {"since": a.since}
    if a.until:
        clauses.append("r.created_at < %(until)s")
        params["until"] = a.until
    if a.policy_version is not None:
        clauses.append(
            "COALESCE((SELECT max(ar.policy_version) FROM agent_runs ar "
            "WHERE ar.return_id = r.id), -1) <> %(pv)s"
        )
        params["pv"] = a.policy_version

    rows = await db.fetchall(
        f"SELECT r.id::text AS rid FROM returns r WHERE {' AND '.join(clauses)} ORDER BY r.created_at",
        params,
    )
    print(f"{len(rows)} return(s) match")
    if a.dry_run:
        for r in rows:
            print(" ", r["rid"])
        await db.stop()
        return

    pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    for r in rows:
        await db.execute(
            "UPDATE returns SET status='pending', decision=NULL, decision_reason=NULL, "
            "review_attempts=0 WHERE id=%(r)s AND final_decision IS NULL", {"r": r["rid"]}
        )
        await pool.enqueue_job("review_return", r["rid"])
    print(f"re-enqueued {len(rows)}")
    await db.stop()


if __name__ == "__main__":
    asyncio.run(main())
