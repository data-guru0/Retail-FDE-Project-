"use client";
import Link from "next/link";
import { useCart } from "../lib/cart";
import type { Product } from "../lib/api";

export function ProductCard({ p }: { p: Product }) {
  const { add } = useCart();
  return (
    <div className="card" style={{ padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
      <Link href={`/shop/product/${p.id}`}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={p.image_url}
          alt={p.name}
          style={{ width: "100%", aspectRatio: "1", objectFit: "cover", borderRadius: 8 }}
        />
      </Link>
      <div style={{ fontWeight: 600 }}>{p.name}</div>
      <div className="muted" style={{ fontSize: 13 }}>
        {p.category}
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <strong>${p.price}</strong>
        <button
          className="btn"
          onClick={() => add({ product_id: p.id, name: p.name, price: Number(p.price) })}
        >
          Add
        </button>
      </div>
    </div>
  );
}
