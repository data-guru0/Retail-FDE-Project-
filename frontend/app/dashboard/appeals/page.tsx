import Link from "next/link";
import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { ResolveAppeal } from "./ResolveAppeal";

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
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div className="d-head">
        <h1>Appeals</h1>
        <p>
          A denied return can be contested. The appeal routes to a reviewer who
          is not the one who decided it (conflict-of-interest guard).
        </p>
      </div>
      {rows.length === 0 && <div className="d-empty">no appeals</div>}
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
          <div key={a.id} className="d-section">
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Link href={`/dashboard/${a.return_id}`} style={{ color: "var(--accent)" }}>
                <strong>Return #{a.return_id.slice(0, 8)}</strong>
              </Link>
              <span className="d-badge info">
                <span className="dot" />
                {a.status}
              </span>
              {a.outcome && (
                <span
                  className={`d-badge ${a.outcome === "approve" ? "ok" : "danger"}`}
                >
                  <span className="dot" />
                  {a.outcome}
                </span>
              )}
            </div>
            <div className="muted" style={{ fontSize: 13.5 }}>{a.reason}</div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <span className="d-chip">
                assigned: {a.assigned_to?.slice(0, 8) ?? "—"}
              </span>
              <span className="d-chip">
                COI-excluded: {a.original_reviewer?.slice(0, 8) ?? "—"}
              </span>
            </div>
            {a.status !== "resolved" && <ResolveAppeal id={a.id} />}
          </div>
        ),
      )}
    </div>
  );
}
