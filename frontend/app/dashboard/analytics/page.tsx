import { redirect } from "next/navigation";
import { auth } from "@/auth";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

function J({ v }: { v: unknown }) {
  return (
    <pre style={{ overflowX: "auto", fontSize: 12 }}>
      {JSON.stringify(v, null, 2)}
    </pre>
  );
}

export default async function Analytics() {
  const session = await auth();
  if (!session) redirect("/");
  const token = (session as unknown as { accessToken?: string }).accessToken;
  const h = { authorization: `Bearer ${token}` };
  const [a, health, rings] = await Promise.all([
    fetch(`${BACKEND}/dashboard/analytics`, {
      headers: h,
      cache: "no-store",
    }).then((r) => r.json()),
    fetch(`${BACKEND}/dashboard/agent-health`, {
      headers: h,
      cache: "no-store",
    }).then((r) => r.json()),
    fetch(`${BACKEND}/dashboard/rings`, { headers: h, cache: "no-store" }).then(
      (r) => r.json(),
    ),
  ]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <h1 style={{ fontSize: 22, fontWeight: 700 }}>Analytics</h1>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
        <div className="card" style={{ padding: 14 }}>
          <h3>vs all-human baseline</h3>
          <J v={a.vs_baseline} />
        </div>
        <div className="card" style={{ padding: 14 }}>
          <h3>Unit economics</h3>
          <J v={a.unit_economics} />
        </div>
        <div className="card" style={{ padding: 14 }}>
          <h3>Quality (from real overrides)</h3>
          <J v={a.quality} />
          <J v={a.counts} />
        </div>
        <div className="card" style={{ padding: 14 }}>
          <h3>Agent health</h3>
          <J v={health.per_agent} />
        </div>
      </div>
      <div className="card" style={{ padding: 14 }}>
        <h3>Agent-vs-human agreement trend</h3>
        <J v={health.agreement_trend} />
      </div>
      <div className="card" style={{ padding: 14 }}>
        <h3>Ring detection (shared fingerprints)</h3>
        <J v={rings} />
      </div>
    </div>
  );
}
