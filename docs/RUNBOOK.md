# Runbook

## Start / stop

```bash
make up          # full stack (runs scripts/preflight.sh first)
make up-lite     # same set today (observability profile is opt-in)
make down        # stop, keep data
make nuke        # stop + delete all volumes (full reset)
make logs        # tail everything
docker compose --profile observability up -d prometheus grafana
```

## Kill-switch drill

Something is wrong with the agents — stop autonomy immediately without a deploy:

1. Dashboard → Governance → tick **kill switch** on the `global` row → Save.
   (or: `PUT /dashboard/governance {"scope":"global","kill_switch":true}` as an admin)
2. Effect is immediate — the Governance Gate reads `feature_flags` per run, so
   the next case (and every case) routes to a human regardless of level.
3. Confirm: submit a trivially-legit return; it should land in the queue as
   `escalated` with an `audit_log` row showing `kill_switch=true`.
4. To resume: untick, and consider dropping `automation_level` to `shadow` while
   you investigate.

## Queue drain (backlog of escalations)

- Bulk-claim + decide from the dashboard Queue.
- Or scale worker replicas if the backlog is pipeline throughput, not human
  throughput: `docker compose up -d --scale worker=3`. arq is a shared Redis
  queue; replicas cooperate. The atomic claim in `review_return` prevents
  double-processing.

## Dead-letter handling

- `dead_letter` rows mean a case crashed 3× — it was auto-escalated, so a human
  will see it, but the root cause needs a look.
- Inspect: `select * from dead_letter order by created_at desc;` and the matching
  `agent_run_events` (kind `error`).
- Re-run one case after a fix:
  `docker compose run --rm worker python replay.py <graph_run_id> <node>` to
  debug a single node, or reset + re-enqueue:
  `update returns set status='pending', review_attempts=0 where id='…';` (the
  `dispatch_outbox` cron will pick it up).

## Policy change rollout

1. Dashboard → Policy → edit → Save. This writes a new `policy_docs` version and
   enqueues `reembed_policy` (Qdrant re-embed).
2. New cases use the new version automatically; `agent_runs.policy_version`
   records which applied.
3. Re-review cases still awaiting a human under the old policy:
   `docker compose run --rm worker python reprocess.py --since <date> --policy-version <new>`

## Key rotation

1. Update the key in Vault: `docker compose exec vault vault kv patch
   secret/returnguard/llm openai_api_key=sk-…` (or `groq_api_key=…`).
2. Restart the consumers: `docker compose restart backend worker`. Settings are
   cached per process, so a restart is required.
3. For DB / MinIO / Keycloak credentials, update `.env`, `make nuke` is the clean
   path (they're baked into container init); otherwise rotate in-place per that
   service's docs and re-run `make vault-init`.

## Load test

`python scripts/loadtest.py --factor 20` submits ~20× a normal minute of return
volume and reports p50/p95 time-to-decision. The scaling lever is worker
replicas (above). *(Status: script is a stub — see STATUS.md.)*

## Backup / restore

`bash scripts/backup.sh` → `backups/<timestamp>/` (pg_dump + Qdrant snapshot +
MinIO mirror). `bash scripts/restore.sh backups/<timestamp>` to restore.
