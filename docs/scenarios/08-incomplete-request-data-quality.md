# Scenario 08 — Incomplete request → data-quality gate → escalate

**Route:** escalate ("insufficient data") **· Automated by:** manual **· Group:** decision behaviour

## What this shows

The pipeline refuses to guess. Evidence is checked at two points: the **API
edge** rejects a return with no photo before it's ever stored, and the
**data-quality node** stops the pipeline for anything that gets past the edge
but still can't be judged (e.g. a product with no reference data for the Image
agent to compare against). Either way, no model is asked to decide on thin
inputs.

## Run it

### Edge guard — a `damaged` return with no photo

```bash
python - <<'PY'
import sys; sys.path.insert(0, "scripts")
from _kc import register_user, token
from _rg import API, httpx
import uuid
email = f"dq-{uuid.uuid4().hex[:8]}@test.local"; pw = "Passw0rd!" + uuid.uuid4().hex[:6]
register_user(email, pw); h = {"Authorization": f"Bearer {token(email, pw)}"}
prods = httpx.get(f"{API}/products?sort=price_asc", timeout=15).json()
o = httpx.post(f"{API}/orders", headers=h, timeout=20, json={
    "lines": [{"product_id": prods[0]["id"], "qty": 1}],
    "shipping_address": {"line1": "1", "city": "x", "zip": "1"},
    "card_number": "4242424242424242", "card_exp": "12/30", "card_cvc": "123"}).json()
r = httpx.post(f"{API}/returns", headers=h, timeout=30,
    data={"order_item_id": o["items"][0]["id"], "reason_code": "damaged", "reason_text": "broke"})
print(r.status_code, r.text)   # -> 422, "photo: Field required"
PY
```

The API declares `photo` required on `POST /returns`, so this returns **422**
and nothing is written. That's the earliest possible refusal.

### Data-quality node — a product with no reference data

```bash
python - <<'PY'
import sys, time; sys.path.insert(0, "scripts")
from _kc import register_user, token
from _rg import API, httpx, db, q1, qall
import uuid, pathlib
pid = q1("select id from products order by created_at limit 1")
old = q1("select description from products where id=%(p)s", p=pid)
with db() as c:                       # simulate a product with no reference data
    c.execute("update products set description='' where id=%(p)s", {"p": pid})
try:
    e = f"dq-{uuid.uuid4().hex[:8]}@t.local"; pw = "Pw1!" + uuid.uuid4().hex[:8]
    register_user(e, pw); h = {"Authorization": f"Bearer {token(e, pw)}"}
    p = next(x for x in httpx.get(f"{API}/products", timeout=15).json() if x["id"] == str(pid))
    o = httpx.post(f"{API}/orders", headers=h, timeout=20, json={
        "lines": [{"product_id": p["id"], "qty": 1}],
        "shipping_address": {"line1": "1", "city": "x", "zip": "1"},
        "card_number": "4242424242424242", "card_exp": "12/30", "card_cvc": "123"}).json()
    photo = pathlib.Path("scenarios/fixtures/mug_photo.jpg").read_bytes()
    rid = httpx.post(f"{API}/returns", headers=h, timeout=30,
        data={"order_item_id": o["items"][0]["id"], "reason_code": "damaged", "reason_text": "cracked"},
        files={"photo": ("m.jpg", photo, "image/jpeg")}).json()["id"]
    print("return:", rid)
    for _ in range(30):
        row = q1("select json_build_object('status',status,'decision',decision,'grid',graph_run_id) "
                 "from returns where id=%(r)s", r=rid)
        if row["status"] in ("escalated", "approved", "denied"): break
        time.sleep(4)
    print("final:", row)
    print("agents fired:", [a[0] for a in qall(
        "select agent from agent_runs where graph_run_id=%(g)s order by created_at", g=row["grid"])])
    print("data_quality:", q1("select parsed_output from agent_runs "
        "where graph_run_id=%(g)s and agent='data_quality'", g=row["grid"]))
finally:
    with db() as c:
        c.execute("update products set description=%(d)s where id=%(p)s", {"d": old, "p": pid})
    print("restored")
PY
```

Expected output:

```
final: {'status': 'escalated', 'decision': 'escalate', 'grid': '...'}
agents fired: ['data_quality', 'governance']
data_quality: {'ok': False, 'reason': 'no reference product data', 'confidence': 0.95}
restored
```

## What happens, step by step

| # | Node | What it does here | What you see |
|---|---|---|---|
| 1 | **data_quality** | checks the photo requirement (`reason ∈ {damaged, defective, not_as_described, wrong_item}` needs one) **and** whether there's reference product data. Here the product has none → problem `"no reference product data"` → `ok = false` | `parsed_output.ok = false`, `reason` set |
| — | **planner … explanation** | **skipped.** The conditional edge after `data_quality` routes straight to `governance` when `ok` is false | `agent_runs` has only `data_quality` + `governance` — no intake/policy/image/decision/critic |
| 2 | **GovernanceGate** | OPA's `governance` policy sees `dq_ok = false` → `data-quality gate failed: no reference product data` → **escalate** with `proposed = escalate`. No LLM decision was ever made | `route = escalate` |

## Why it matters

"Escalate because I don't have enough to go on" is a *correct* answer, and it's
cheaper than a wrong one — no model tokens are spent. A system that always
produces a decision is a system that will confidently produce wrong ones when
the inputs are thin.
