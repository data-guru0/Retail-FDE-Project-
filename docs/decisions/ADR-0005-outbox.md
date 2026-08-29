# ADR-0005 — Transactional outbox for return-review jobs

**Status:** accepted (M2 write, M3 dispatch)

## Context
When a customer submits a return we must (a) persist the `returns` + `return_photos`
rows and (b) get the review pipeline to run. If we enqueue to Redis *after*
committing and the process dies in between, the review is silently lost. If we
enqueue *before* committing and the commit fails, we process a return that
doesn't exist.

## Decision
**Transactional outbox.** Submitting a return writes an `outbox` row
(`topic='return.submitted'`, `payload={return_id}`) **in the same transaction** as
the `returns` row. Then:

- The backend does a **best-effort** `arq` enqueue right after commit (low latency
  for the happy path).
- The worker runs a `dispatch_outbox` cron every 10s that enqueues any
  `return.submitted` row still `dispatched_at IS NULL` and older than 8s — the
  durability backstop.
- `review_return` **claims** the return atomically
  (`UPDATE ... WHERE status IN ('pending','info_requested') RETURNING`),
  marks the outbox row dispatched, and increments `returns.review_attempts`.
  A duplicate enqueue (backend + cron) can't double-process, and the attempt
  counter drives the dead-letter cap independently of arq job identity.

## Consequences
- No review job is ever lost, even across a crash between the DB write and the
  enqueue.
- Exactly-once *effect* (not exactly-once delivery): the claim + attempt counter
  make re-delivery safe.
- `dead_letter` after 3 real attempts → auto-escalate; never an infinite retry.
