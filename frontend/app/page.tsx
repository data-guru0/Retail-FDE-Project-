import Link from "next/link";
import { ProductCard } from "./components/ProductCard";
import type { Product } from "./lib/api";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ category?: string; sort?: string; q?: string }>;
}) {
  const sp = await searchParams;
  const qs = new URLSearchParams();
  if (sp.category) qs.set("category", sp.category);
  if (sp.sort) qs.set("sort", sp.sort);
  if (sp.q) qs.set("q", sp.q);

  const [products, categories] = await Promise.all([
    fetch(`${BACKEND}/products?${qs}`, { cache: "no-store" }).then((r) =>
      r.json(),
    ) as Promise<Product[]>,
    fetch(`${BACKEND}/products/categories`, { cache: "no-store" }).then((r) =>
      r.json(),
    ) as Promise<string[]>,
  ]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div
        style={{
          display: "flex",
          gap: 8,
          flexWrap: "wrap",
          alignItems: "center",
        }}
      >
        <Link href="/" className="btn secondary">
          All
        </Link>
        {categories.map((c) => (
          <Link
            key={c}
            href={`/?category=${encodeURIComponent(c)}`}
            className="btn secondary"
          >
            {c}
          </Link>
        ))}
        <form style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <input
            className="input"
            name="q"
            placeholder="Search…"
            defaultValue={sp.q}
          />
          <select
            className="select"
            name="sort"
            defaultValue={sp.sort ?? "newest"}
          >
            <option value="newest">Newest</option>
            <option value="price_asc">Price ↑</option>
            <option value="price_desc">Price ↓</option>
            <option value="name">Name</option>
          </select>
          <button className="btn">Go</button>
        </form>
      </div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
          gap: 14,
        }}
      >
        {products.map((p) => (
          <ProductCard key={p.id} p={p} />
        ))}
      </div>
    </div>
  );
}
