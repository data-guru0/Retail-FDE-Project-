import Link from "next/link";
import { auth } from "@/auth";
import { redirect } from "next/navigation";
import type { Order } from "../lib/api";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export default async function OrdersPage() {
  const session = await auth();
  if (!session) redirect("/api/auth/signin");
  const token = (session as unknown as { accessToken?: string }).accessToken;
  const orders: Order[] = await fetch(`${BACKEND}/orders`, {
    headers: { authorization: `Bearer ${token}` },
    cache: "no-store",
  }).then((r) => r.json());

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <h1 style={{ fontSize: 22, fontWeight: 700 }}>My orders</h1>
      {orders.length === 0 && <p className="muted">No orders yet.</p>}
      {orders.map((o) => (
        <Link key={o.id} href={`/orders/${o.id}`} className="card" style={{ padding: 14 }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span>#{o.id.slice(0, 8)}</span>
            <span>${o.total}</span>
          </div>
          <div className="muted" style={{ fontSize: 13 }}>
            {new Date(o.placed_at).toLocaleString()} · {o.items.length} item(s) · {o.status}
          </div>
        </Link>
      ))}
    </div>
  );
}
