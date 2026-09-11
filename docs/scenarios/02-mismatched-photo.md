# Scenario 02 — Mismatched photo → escalate

**Route:** escalate · **Group:** decision behaviour · **[demo]**

See [00 — Watching a case live](00-watching-a-case-live.md) for how to read the
Live Trace / Langfuse / MinIO panels this walkthrough refers to.

## What this shows

A photo is a *claim to verify*, not proof by itself. When the uploaded photo
doesn't actually match the product, the real CLIP comparison catches it and
the case goes to a human — even though nothing else about the request looks
wrong.

## The situation

A customer buys a **Vertex Wireless Mouse ($59.99)** and files a return for
"not as described," but uploads a photo of something else entirely (a potted
plant, in our real test run).

## Walkthrough (as the customer)

1. Buy the **Vertex Wireless Mouse** and check out as in
   [scenario 01](01-matching-photo-auto-approve.md).
2. **My orders** → the order → **Return this**.
3. Reason: **not as described** → note "This isn't what I ordered." → upload
   any real photo that is clearly **not** the mouse (a photo of a plant, a
   different object, anything unrelated) → **Submit return**.

## What happens behind the scenes

Real numbers from a live run:

| Agent | What it did | Real result |
|---|---|---|
| **policy** | checked the return-window and condition rules | `eligible: yes` — policy has no opinion on photo content |
| **image** | compared the upload to the mouse's catalog photo, and asked a vision model to describe what it actually saw | `clip_similarity: 0.69` (mismatch); vision model: *"The photo shows a potted plant, not a mouse or its packaging"* |
| **behavior** | scored the account | first order, 100% return rate → `abuse_likelihood: medium` |
| **decision** | weighed the mismatch against policy eligibility | `decision: escalate`, risk 0.62 |
| **critic** | actually *disagreed* with escalating, arguing policy eligibility should win | `veto: true, agree: false` — but a veto is a veto in either direction |
| **GovernanceGate** | a Critic veto of any kind blocks auto-anything | **`escalate`** |

## In the reviewer dashboard

The queue's **escalated** tab shows the case with an amber **escalate** badge
under **Agent**. Opening it, the **Image evidence** shown in the Agent
reasoning section is the tell: a low similarity score plus the vision model's
plain description of what it actually saw in your photo — a human can glance
at both images side by side and decide in seconds.

## Watch it live

- **Live Trace:** the `image` node's `node_end` payload has `verdict:
  "mismatch"` right there in the raw JSON.
- **Langfuse:** the Image agent's vision-model call (only fired because CLIP's
  score was borderline/low) is a real generation with the photo attached.
- **Why the Critic's disagreement didn't flip it:** open the `governance`
  event — its `reason` field literally starts with `"Critic vetoed: ..."`
  followed by the Critic's own argument for the *other* side. A veto forces a
  human regardless of which way it leans.

## Why it matters

An image check that always trusts the upload isn't a check. Wiring in a real
vision model — not a rule that says "a photo was attached, therefore fine" —
is what makes this catchable at all, and routing any Critic disagreement to a
human (instead of "resolving" it in code) is what keeps a disagreement from
quietly becoming a wrong auto-decision in either direction.
