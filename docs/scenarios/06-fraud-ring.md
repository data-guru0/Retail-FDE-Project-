# Scenario 06 — Fraud ring (shared fingerprint) → escalate

**Route:** escalate · **Group:** decision behaviour · **[demo]**

See [00 — Watching a case live](00-watching-a-case-live.md) first.

## What this shows

Fraud is a graph, not a row. Two accounts that share a shipping address or
device fingerprint are linked by the Behaviour agent's `flag_ring` tool, and a
return from either one is routed to a human — even if that single return
looks unremarkable by itself.

## The situation

Two customer accounts were created through the normal signup flow, each
placed a real order. Behind the scenes they share the same address and device
fingerprint (in a real store this comes from checkout address matching and
device/browser fingerprinting; for the demo it's seeded directly into the
`fingerprints` table the same way a real fraud-detection pipeline would
populate it). One account files a return.

## What happens behind the scenes

Real numbers from a live run:

| Agent | What it did | Real result |
|---|---|---|
| **policy** | checked this return on its own merits | `eligible: yes`, not high-value |
| **image** | photo didn't closely match (a generic evidence photo) | `clip_similarity: 0.66` (mismatch) — a secondary signal here, not the main story |
| **behavior** | called **`get_customer_history`** (unremarkable alone) **and `flag_ring`** — the tool joins the `fingerprints` table on shared address/device hashes | `shared_device_accounts: 1`, `shared_address_accounts: 1` |
| **behavior (LLM read)** | *"Single order followed by an immediate return with a 100% return rate, no approved returns, and a shared fingerprint linking to another account"*, `abuse_likelihood: high` | |
| **decision** | a confirmed account link plus a photo mismatch | `decision: escalate`, risk 0.78 |
| **critic** | argued the ring link shouldn't override plain policy eligibility | `veto: true` — disagreement either way still forces a human |
| **GovernanceGate** | proposed = `escalate` | **`escalate`** |

## In the reviewer dashboard

Open the case and expand **behavior** in Agent reasoning — `ring_accounts`
lists the linked account id directly in the raw JSON. On the **Analytics**
page's **Ring detection** section, the same two accounts show up as a card:
the shared fingerprint value and both account ids, so a reviewer (or an
admin investigating a pattern across many cases) can see the connection
without digging through raw tables.

## Watch it live

- **Live Trace:** look for a `tool_call` event with `tool: "flag_ring"` — its
  payload shows `via: "contextforge"` and `ok: true`. This tool call happens
  for *every* case (it's routine due diligence); what's different here is that
  it actually finds something.
- **Per-agent least privilege:** the Behaviour agent is the *only* agent
  granted the `flag_ring` tool — the Image agent, for instance, is granted
  zero MCP tools at all. `scripts/verify_security.py` is the real proof of
  this boundary; you can see the effect here by noting `flag_ring` never
  appears under any other agent's tool calls in the trace.
- **Analytics → Ring detection (shared fingerprints):** the live card for
  this exact pair of accounts.

## Why it matters

Per-account checks miss coordinated abuse by design — nothing about either
account looks wrong in isolation. The fingerprint join is how one refund
request pulls in everything connected to it, and it runs as a governed MCP
tool the Behaviour agent is explicitly granted through its own Keycloak
service account and ContextForge virtual server — not a blanket permission
every agent shares.
