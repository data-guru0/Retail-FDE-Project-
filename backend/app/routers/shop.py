from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Product
from app.schemas import ProductOut
from app.services import storage

router = APIRouter(prefix="/products", tags=["shop"])

_SORTS = {
    "price_asc": Product.price.asc(),
    "price_desc": Product.price.desc(),
    "name": Product.name.asc(),
    "newest": Product.created_at.desc(),
}


def _out(p: Product) -> ProductOut:
    return ProductOut(
        id=str(p.id), sku=p.sku, name=p.name, description=p.description,
        category=p.category, price=p.price, stock=p.stock,
        image_url=storage.presigned_get(p.image_key),
    )


@router.get("", response_model=list[ProductOut])
async def list_products(
    session: AsyncSession = Depends(get_session),
    category: str | None = None,
    q: str | None = None,
    sort: str = Query("newest"),
) -> list[ProductOut]:
    stmt = select(Product)
    if category:
        stmt = stmt.where(Product.category == category)
    if q:
        stmt = stmt.where(Product.name.ilike(f"%{q}%"))
    stmt = stmt.order_by(_SORTS.get(sort, Product.created_at.desc()))
    rows = (await session.execute(stmt)).scalars().all()
    return [_out(p) for p in rows]


@router.get("/categories", response_model=list[str])
async def categories(session: AsyncSession = Depends(get_session)) -> list[str]:
    rows = (await session.execute(select(Product.category).distinct())).scalars().all()
    return sorted(rows)


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(product_id: str, session: AsyncSession = Depends(get_session)) -> ProductOut:
    p = await session.get(Product, product_id)
    if p is None:
        raise HTTPException(404, "product not found")
    return _out(p)
