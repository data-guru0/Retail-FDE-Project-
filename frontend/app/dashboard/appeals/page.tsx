import { redirect } from "next/navigation";
import { auth } from "@/auth";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export default async function Appeals() {
  const session = await auth();
  if (!session) redirect("/");
  const token = (session as unknown as { accessToken?: string }).accessToken;
  const rows = await fetch(`${BACKEND}/appeals`, {
    headers: { authorization: `Bearer ${token}` },
    cache: "no-store",
  }).then((r) => r.json());

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <h1 style={{ fontSize: 22, fontWeight: 700 }}>Appeals</h1>
      <p className="muted">
        A denied return can be contested. The appeal routes to a reviewer who is
        not the one who decided it (conflict-of-interest guard).
      </p>
      {rows.length === 0 && <p className="muted">no appeals</p>}
      {rows.map(
        (a: {
          id: string;
          return_id: string;
          reason: string;
          status: string;
          assigned_to: string | null;
          original_reviewer: string | null;
          outcome: string | null;
        }) => (
          <div key={a.id} className="card" style={{ padding: 14 }}>
            <div>
              <strong>Return #{a.return_id.slice(0, 8)}</strong> · {a.status}
              {a.outcome ? ` · ${a.outcome}` : ""}
            </div>
            <div className="muted">{a.reason}</div>
            <div className="muted" style={{ fontSize: 12 }}>
              assigned: {a.assigned_to?.slice(0, 8) ?? "—"} · COI-excluded:{" "}
              {a.original_reviewer?.slice(0, 8) ?? "—"}
            </div>
          </div>
        ),
      )}
    </div>
  );
}
