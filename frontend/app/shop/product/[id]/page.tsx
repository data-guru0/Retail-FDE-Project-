import { AddToCart } from "./AddToCart";
import type { Product } from "@/app/lib/api";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export default async function ProductPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const p: Product = await fetch(`${BACKEND}/products/${id}`, {
    cache: "no-store",
  }).then((r) => r.json());
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={p.image_url}
        alt={p.name}
        style={{ width: "100%", borderRadius: 12 }}
      />
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700 }}>{p.name}</h1>
        <div className="muted">{p.category}</div>
        <p>{p.description}</p>
        <div style={{ fontSize: 22, fontWeight: 700 }}>${p.price}</div>
        <div className="muted">{p.stock} in stock</div>
        <AddToCart id={p.id} name={p.name} price={Number(p.price)} />
      </div>
    </div>
  );
}
