"use client";
import Link from "next/link";
import { useCart } from "@/app/lib/cart";

export default function CartPage() {
  const { items, setQty, total } = useCart();
  if (items.length === 0)
    return (
      <div>
        <p>Your cart is empty.</p>
        <Link href="/" className="btn secondary">
          Browse products
        </Link>
      </div>
    );
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <h1 style={{ fontSize: 22, fontWeight: 700 }}>Cart</h1>
      {items.map((i) => (
        <div
          key={i.product_id}
          className="card"
          style={{ padding: 12, display: "flex", gap: 12 }}
        >
          <div style={{ flex: 1 }}>{i.name}</div>
          <div>${i.price.toFixed(2)}</div>
          <input
            className="input"
            type="number"
            min={0}
            max={20}
            value={i.qty}
            onChange={(e) => setQty(i.product_id, Number(e.target.value))}
            style={{ width: 70 }}
          />
          <div style={{ width: 80, textAlign: "right" }}>
            ${(i.price * i.qty).toFixed(2)}
          </div>
        </div>
      ))}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <strong>Total: ${total.toFixed(2)}</strong>
        <Link href="/shop/checkout" className="btn">
          Checkout
        </Link>
      </div>
    </div>
  );
}
