# ADR-0003 — Hash-chained, append-only audit log

**Status:** accepted (M3 groundwork, enforced M4)

## Context
Every governed action — an agent decision finalised by GovernanceGate, a reviewer
approve/deny/request-info, a policy edit, an automation-level change — must be
provable after the fact and tamper-evident. A plain table anyone can `UPDATE` is
not a governance record.

## Decision
`audit_log` is **append-only** and **hash-chained**:

- Each row stores `prev_hash` + `row_hash`.
- `row_hash = sha256(prev_hash + canonical(row))` where `canonical` is a compact
  JSON object with **sorted keys** over
  `(ts_iso, actor_type, actor_id, action, entity_type, entity_id, data)`.
  The first row chains from `GENESIS = "0"*64`.
- A Postgres `BEFORE UPDATE OR DELETE` trigger (`audit_log_immutable()`) raises —
  the row cannot be changed or removed once written.
- The chain is appended inside a transaction that takes `FOR UPDATE` on the last
  row, so concurrent appends serialise and can't fork the chain.
- Both writers (`worker/pipeline/audit.py`, `backend/app/services/audit.py`) use
  the **identical** canonical rule. `scripts/verify_audit_chain.py` re-walks the
  whole chain and recomputes every hash with that same rule; it fails on any
  mismatch or broken link.

## Consequences
- Tampering with any historical row (even via direct SQL, which the trigger
  blocks anyway) is detected by the verifier.
- The canonical serialisation is now part of the contract — changing it requires
  a migration + a re-hash, and is an ADR-worthy change itself.
- `verify_m4` / `verify_m5` run the chain verifier after every scripted mutation.
