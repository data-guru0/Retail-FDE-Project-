# Scenario 05 — Serial returner → escalate

**Route:** escalate · **Group:** decision behaviour · **[demo]**

See [00 — Watching a case live](00-watching-a-case-live.md) first.

## What this shows

A single return can look completely ordinary and still be the tip of a
pattern. The Behaviour agent scores the account's *history*, not just this
one transaction, so a high-return-rate account gets a human even when the
individual request has a reasonable reason and an acceptable photo.

## The situation

An account has placed 13 orders and already had 9 of them denied. It now
files one more return that, taken alone, looks fine: a $40 desk lamp, reason
"damaged," a real photo.

*(In a real store this history accrues over months; for a live demo, a fresh
account's history has to be pre-loaded so you can see the effect immediately
— every order and return in the real history below is a genuine row in
`orders`/`order_items`/`returns`, just written in bulk instead of one at a
time.)*

## What happens behind the scenes

Real numbers from a live run:

| Agent | What it did | Real result |
|---|---|---|
| **policy** | checked window + condition rules on this one request | `eligible: yes` — this individual request is fine |
| **image** | generic photo, acceptable similarity | `clip_similarity: 0.63` (borderline-fine, not the deciding signal) |
| **behavior** | called `get_customer_history` via ContextForge, pulled the real order/return counts | `return_rate: 0.769`, `prior_denied_returns: 9`, `risk_score: 0.647` |
| **behavior (LLM read)** | described the pattern in words | *"High return rate (77%) with 9 denied and 0 approved returns despite 13 orders, indicating potential return fraud behavior"*, `abuse_likelihood: high` |
| **decision** | weighed the history against this request's own cleanliness | `decision: escalate`, risk 0.65 |
| **critic** | argued the opposite — this one request is eligible | `veto: true, agree: false` |
| **GovernanceGate** | any veto blocks auto-anything, and risk 0.65 is high regardless | **`escalate`** |

## In the reviewer dashboard

Open the case and expand the **behavior** row in Agent reasoning: the real
`return_rate` and `prior_denied_returns` numbers are right there in the raw
JSON, next to the risk score the scikit-learn model actually produced. A
reviewer sees in one glance why an otherwise-unremarkable request is sitting
in their queue.

## Watch it live

- **Analytics page → Agent health table:** the **behavior** row's average
  confidence and run count move with every case like this one.
- **Live Trace:** two `behavior` events fire for every case — one
  `behavior_risk:v<date>` (the trained model) and one LLM read of the
  qualitative pattern — both feed the Decision agent.
- **Dashboard → the account's other returns:** open **My returns** as this
  customer (or query the case's `user_id` from an admin view) to see the 9
  prior denials that produced this score — the pattern is visible, not just
  asserted.

## Why it matters

Context beats the single case. Fraud and abuse show up in the shape of an
account's activity long before any one request looks wrong on its own; scoring
the history — via a real trained classifier, not a hand-written threshold — is
how you catch it without punishing a genuine first-time returner (compare
[scenario 01](01-matching-photo-auto-approve.md), same clean single request,
completely different history, completely different outcome).
