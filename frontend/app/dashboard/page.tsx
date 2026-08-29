import Link from "next/link";
import { auth } from "@/auth";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

type Row = {
  id: string;
  status: string;
  decision: string | null;
  amount: string;
  reason_code: string;
  created_at: string;
  claimed_by: string | null;
  customer: string;
  item: string;
};

export default async function Queue({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>;
}) {
  const sp = await searchParams;
  const status = sp.status ?? "escalated";
  const session = await auth();
  const token = (session as unknown as { accessToken?: string }).accessToken;
  const rows: Row[] = await fetch(`${BACKEND}/dashboard/queue?status=${status}`, {
    headers: { authorization: `Bearer ${token}` },
    cache: "no-store",
  }).then((r) => r.json());

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", gap: 8 }}>
        {["escalated", "in_review", "info_requested", "approved", "denied"].map((s) => (
          <Link
            key={s}
            href={`/dashboard?status=${s}`}
            className="btn secondary"
            style={{ borderColor: s === status ? "var(--accent)" : "var(--border)" }}
          >
            {s}
          </Link>
        ))}
      </div>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr className="muted" style={{ textAlign: "left", fontSize: 13 }}>
            <th style={{ padding: 8 }}>Case</th>
            <th>Item</th>
            <th>Reason</th>
            <th>Amount</th>
            <th>Agent</th>
            <th>Age</th>
            <th>Claimed</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} style={{ borderTop: "1px solid var(--border)" }}>
              <td style={{ padding: 8 }}>
                <Link href={`/dashboard/${r.id}`} style={{ color: "var(--accent)" }}>
                  #{r.id.slice(0, 8)}
                </Link>
              </td>
              <td>{r.item}</td>
              <td>{r.reason_code}</td>
              <td>${r.amount}</td>
              <td>{r.decision ?? "—"}</td>
              <td className="muted">
                {Math.round((Date.now() - new Date(r.created_at).getTime()) / 60000)}m
              </td>
              <td className="muted">{r.claimed_by ? "yes" : "—"}</td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={7} className="muted" style={{ padding: 16 }}>
                nothing in {status}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
