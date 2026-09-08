"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useCart } from "@/app/lib/cart";

export function AddToCart({
  id,
  name,
  price,
}: {
  id: string;
  name: string;
  price: number;
}) {
  const { add } = useCart();
  const [qty, setQty] = useState(1);
  const router = useRouter();
  return (
    <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
      <input
        className="input"
        type="number"
        min={1}
        max={20}
        value={qty}
        onChange={(e) => setQty(Math.max(1, Number(e.target.value)))}
        style={{ width: 80 }}
      />
      <button
        className="btn"
        onClick={() => {
          add({ product_id: id, name, price }, qty);
          router.push("/shop/cart");
        }}
      >
        Add to cart
      </button>
    </div>
  );
}
