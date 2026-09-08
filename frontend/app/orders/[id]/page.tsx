import Link from "next/link";
import { auth } from "@/auth";
import { redirect } from "next/navigation";
import type { Order } from "@/app/lib/api";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export default async function OrderPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const session = await auth();
  if (!session) redirect("/api/auth/signin");
  const { id } = await params;
  const token = (session as unknown as { accessToken?: string }).accessToken;
  const o: Order = await fetch(`${BACKEND}/orders/${id}`, {
    headers: { authorization: `Bearer ${token}` },
    cache: "no-store",
  }).then((r) => r.json());

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <h1 style={{ fontSize: 22, fontWeight: 700 }}>
        Order #{o.id.slice(0, 8)}
      </h1>
      <div className="muted">
        {new Date(o.placed_at).toLocaleString()} · card ****{o.payment_last4} ·{" "}
        {o.status}
      </div>
      {o.items.map((it) => (
        <div
          key={it.id}
          className="card"
          style={{ padding: 12, display: "flex", gap: 12 }}
        >
          <div style={{ flex: 1 }}>
            {it.name} × {it.qty}
          </div>
          <div>${it.unit_price}</div>
          <Link
            href={`/returns/new?item=${it.id}&name=${encodeURIComponent(it.name)}`}
            className="btn secondary"
          >
            Return this
          </Link>
        </div>
      ))}
      <strong>Total: ${o.total}</strong>
    </div>
  );
}
