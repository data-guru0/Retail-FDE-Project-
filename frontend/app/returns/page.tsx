import Link from "next/link";
import { auth } from "@/auth";
import { redirect } from "next/navigation";
import type { ReturnRow } from "../lib/api";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export default async function ReturnsPage() {
  const session = await auth();
  if (!session) redirect("/api/auth/signin");
  const token = (session as unknown as { accessToken?: string }).accessToken;
  const rows: ReturnRow[] = await fetch(`${BACKEND}/returns`, {
    headers: { authorization: `Bearer ${token}` },
    cache: "no-store",
  }).then((r) => r.json());

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <h1 style={{ fontSize: 22, fontWeight: 700 }}>My returns</h1>
      {rows.length === 0 && <p className="muted">No returns yet.</p>}
      {rows.map((r) => (
        <Link
          key={r.id}
          href={`/returns/${r.id}`}
          className="card"
          style={{ padding: 14 }}
        >
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span>
              #{r.id.slice(0, 8)} · {r.reason_code}
            </span>
            <span>
              {r.status}
              {r.refund_state !== "none" ? ` · ${r.refund_state}` : ""}
            </span>
          </div>
          <div className="muted" style={{ fontSize: 13 }}>
            ${r.amount} · {new Date(r.created_at).toLocaleString()}
          </div>
        </Link>
      ))}
    </div>
  );
}
