from __future__ import annotations

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, Field


class ProductOut(BaseModel):
    id: str
    sku: str
    name: str
    description: str
    category: str
    price: Decimal
    image_url: str
    stock: int


class CartLine(BaseModel):
    product_id: str
    qty: int = Field(ge=1, le=20)


class CheckoutIn(BaseModel):
    lines: list[CartLine] = Field(min_length=1)
    shipping_address: dict
    card_number: str          # fake card, Luhn-checked, never stored
    card_exp: str
    card_cvc: str


class OrderItemOut(BaseModel):
    id: str
    product_id: str
    name: str
    unit_price: Decimal
    qty: int


class OrderOut(BaseModel):
    id: str
    status: str
    total: Decimal
    payment_last4: str
    placed_at: dt.datetime
    items: list[OrderItemOut]


class ReturnCreateOut(BaseModel):
    id: str
    status: str
    amount: Decimal


class ReturnOut(BaseModel):
    id: str
    order_id: str
    order_item_id: str
    reason_code: str
    reason_text: str
    status: str
    refund_state: str
    amount: Decimal
    decision: str | None
    decision_reason: str | None
    final_decision: str | None
    created_at: dt.datetime
    photo_urls: list[str] = []
