# Scenario 15 — Reviewer denies, customer appeals, a different reviewer decides

**Route:** human decision (both times) · **Group:** governance controls · **[demo]**

See [00 — Watching a case live](00-watching-a-case-live.md) first.

## What this shows

A denial isn't the end of the story, and the person who reconsiders it can
never be the same person who made it — a real conflict-of-interest guard, not
a policy written down and hoped for.

## Walkthrough (three roles)

**As a customer:** buy an **Alpine Wool Blend Beanie**, file a return outside
the return window (an old order, reason "no longer needed"), and wait for it
to escalate with a proposed deny (same mechanism as
[scenario 08](08-outside-return-window.md)).

**As reviewer 1** (`reviewer1@returnguard.local` / `reviewer1`): claim the
case, type a note, click **Deny (confirm)**, and confirm the native dialog
("Confirm denial? This is the human confirm step."). Real result: `status:
denied`, `final_decision: deny`.

Try clicking **Deny** (or **Approve**) again on the same case — real result:
**HTTP 409, `"already denied"`**. A decided case can't be re-decided, by
anyone, through this endpoint.

**As the customer:** open `/returns/<id>` — because the status is `denied`, a
new **"Appeal this decision"** button has appeared (it only ever appears for
denied returns). Click it, and in the box that expands
(**"Tell us why this should be reconsidered"**), write your case, then
**Submit appeal**. Real confirmation text: *"Appeal submitted — a different
reviewer than the one who decided this case will take another look."*

**As reviewer 1 again:** open the **Appeals** page and try to resolve the
appeal you just caused. Real result: **HTTP 403, `"conflict of interest: you
decided the original case"`** — the system won't even let the original
reviewer act on it, regardless of intent.

**As the reviewer the appeal was actually routed to:** open **Appeals** —
your card shows the reason, an **assigned: `<id>`** chip, and a
**COI-excluded: `<reviewer 1's id>`** chip. Click **Approve appeal** (or
**Deny appeal**, which pops its own confirmation). Real result: the return
flips to `status: approved, final_decision: approve, refund_state: pending` —
a second, independent human decision, on the record right next to the first
one.

## What happens behind the scenes

Real sequence from a live run, verbatim:

| Step | Real result |
|---|---|
| Original deny | `returns.status = denied`, `decided_by = <reviewer 1>` |
| Re-decide attempt (same reviewer) | `409 already denied` |
| Appeal opened | routed to a reviewer chosen specifically because they are *not* `decided_by`; `returns.status → escalated` again |
| Resolve attempt (original reviewer) | `403 conflict of interest: you decided the original case` |
| Resolve (routed reviewer) | `200 {"resolved": "approve"}`; `returns.status = approved`, `refund_state = pending` |

## In the reviewer dashboard

The **Appeals** page is where this entire arc is visible at a glance: the
reason text the customer gave, which reviewer it's assigned to, which
reviewer is explicitly excluded, and — once resolved — a green **approve** or
red **deny** outcome badge.

## Watch it live

- **Audit log:** four distinct actions on one case, in order —
  `decide_deny`, `appeal_open`, and `appeal_resolve` — each with the acting
  reviewer's id, none of them editable or deletable (the audit log is
  append-only, hash-chained; `scripts/verify_audit_chain.py` proves the chain
  itself can't be tampered with after the fact).
- **Analytics → Quality (from real overrides):** the appeal's resolution, if
  it disagrees with the original decision, is exactly the kind of override
  this page's **agreement rate** stat is built from.

## Why it matters

A human-in-the-loop system where the same human can rubber-stamp their own
earlier call isn't really a check at all. Routing appeals to a genuinely
different reviewer — and blocking the original one at the API level, not just
by UI convention — is what makes "you can appeal" a real second look instead
of a formality.
