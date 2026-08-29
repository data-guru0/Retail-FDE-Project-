"""Seed real products: download a real photo per product, re-encode it, store it
in MinIO, insert the product row. Idempotent (upsert by SKU). Also writes the
baseline policy docs (M4 embeds them into Qdrant).

Run: `make seed`  (docker compose run --rm backend python -m seed.seed)

ponytail: product photos come from picsum.photos (real photographs, deterministic
per-SKU seed). Swap `image_url` in products.json for true catalog shots if needed.
"""
from __future__ import annotations

import asyncio
import io
import json
import pathlib

import httpx
from PIL import Image
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.db import Session
from app.models import PolicyDoc, Product
from app.services import storage

HERE = pathlib.Path(__file__).parent
PRODUCTS = json.loads((HERE / "products.json").read_text())

POLICY_DOCS = [
    (
        "return-window",
        "Standard return window",
        "Customers may return most items within 30 days of the delivery date for a full "
        "refund. Items must be in original condition with tags attached where applicable. "
        "Refunds are issued to the original payment method within 5 business days of "
        "approval. Return shipping is free for defective or incorrectly shipped items; "
        "otherwise a flat $6 return shipping fee is deducted from the refund.",
    ),
    (
        "category-exceptions",
        "Category-specific rules",
        "Electronics may be returned within 30 days but must include all original "
        "accessories and packaging; a 15% restocking fee applies to opened Electronics "
        "returned without a defect. Apparel must be unworn and unwashed. Final-sale and "
        "clearance items are not returnable. Perishable Home & Kitchen consumables "
        "(e.g. candles that have been burned) are not returnable once used.",
    ),
    (
        "condition-rules",
        "Condition and evidence rules",
        "A photo of the item is required for any return citing damage, a defect, or a "
        "wrong/not-as-described item. The photo must show the actual item received. "
        "Claims of damage without supporting evidence, or with evidence that does not "
        "match the ordered product, are routed to manual review. Signs of normal wear "
        "are not considered defects.",
    ),
    (
        "high-value-and-fraud",
        "High-value and abuse rules",
        "Any refund over $250 requires human confirmation regardless of automated "
        "assessment. Accounts with an unusually high return rate, or multiple accounts "
        "sharing a shipping address, device, or payment fingerprint, are flagged for "
        "review. Repeated returns of the same item across orders are treated as a "
        "potential abuse pattern.",
    ),
]

MAX_DIM = 900


async def _fetch_image(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
        r = await c.get(url)
        r.raise_for_status()
        img = Image.open(io.BytesIO(r.content))
        img.load()
        img.thumbnail((MAX_DIM, MAX_DIM))
        if img.mode != "RGB":
            img = img.convert("RGB")
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=85)
        return out.getvalue()


async def seed_products() -> int:
    n = 0
    async with Session() as s:
        for p in PRODUCTS:
            key = f"products/{p['sku']}.jpg"
            if not storage.exists(key):
                data = await _fetch_image(p["image_url"])
                storage.put_bytes(key, data, "image/jpeg")
            stmt = insert(Product).values(
                sku=p["sku"], name=p["name"], description=p["description"],
                category=p["category"], price=p["price"], stock=p["stock"], image_key=key,
            ).on_conflict_do_update(
                index_elements=["sku"],
                set_={"name": p["name"], "description": p["description"],
                      "category": p["category"], "price": p["price"], "image_key": key, "stock": p["stock"]},
            )
            await s.execute(stmt)
            n += 1
        await s.commit()
    return n


async def seed_policy() -> int:
    async with Session() as s:
        existing = (await s.execute(select(PolicyDoc).where(PolicyDoc.version == 1))).first()
        if existing:
            return 0
        for slug, title, body in POLICY_DOCS:
            s.add(PolicyDoc(version=1, slug=slug, title=title, body=body, active=True))
        await s.commit()
        return len(POLICY_DOCS)


async def main() -> None:
    prods = await seed_products()
    pol = await seed_policy()
    print(f"seeded {prods} products, {pol} policy docs (v1)")


if __name__ == "__main__":
    asyncio.run(main())
