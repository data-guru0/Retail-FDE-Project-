# Qdrant collection: `policy_docs`

The one collection ReturnGuard uses. It is **created programmatically**, not from
a static file, because it is re-created on every policy re-embed (admin Policy
editor → `reembed_policy` job → `worker/pipeline/policy_index.py`).

Config, for reference (see `reembed()`):

| field | value |
|---|---|
| name | `policy_docs` |
| vector size | `1536` (`text-embedding-3-small` via Bifrost) |
| distance | `Cosine` |
| payload | `policy_version` (int), `slug`, `title`, `body` |

Inspect it at http://localhost:6333/dashboard while the stack is up.
Rebuild it with `make reembed-policy`.
