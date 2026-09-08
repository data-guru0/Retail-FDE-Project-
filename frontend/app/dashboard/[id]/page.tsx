import { auth } from "@/auth";
import { CaseActions } from "./CaseActions";
import { LiveTrace } from "./LiveTrace";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export default async function CaseDetail({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const session = await auth();
  const token = (session as unknown as { accessToken?: string }).accessToken;
  const roles = (session?.user as unknown as { roles?: string[] })?.roles ?? [];
  const data = await fetch(`${BACKEND}/dashboard/returns/${id}`, {
    headers: { authorization: `Bearer ${token}` },
    cache: "no-store",
  }).then((r) => r.json());

  const r = data.return;
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 20 }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700 }}>
          Case #{id.slice(0, 8)}
        </h1>
        <div className="card" style={{ padding: 14 }}>
          <div>
            <strong>Status:</strong> {r.status} &nbsp;{" "}
            <strong>Agent proposed:</strong> {r.decision ?? "—"} &nbsp;{" "}
            <strong>Final:</strong> {r.final_decision ?? "—"}
          </div>
          <div>
            <strong>Customer:</strong> {r.customer} &nbsp;{" "}
            <strong>Amount:</strong> ${r.amount}
          </div>
          <div>
            <strong>Reason:</strong> {r.reason_code} — {r.reason_text}
          </div>
          {r.decision_reason && (
            <p className="muted" style={{ marginTop: 8 }}>
              {r.decision_reason}
            </p>
          )}
        </div>

        <h2 style={{ fontWeight: 600 }}>Agent reasoning</h2>
        {data.agent_runs.map(
          (a: {
            agent: string;
            model: string;
            confidence: number | null;
            parsed_output: unknown;
            cost_usd: string;
            latency_ms: number;
            policy_version: number | null;
          }) => (
            <details
              key={a.agent + a.model}
              className="card"
              style={{ padding: 12 }}
            >
              <summary>
                <strong>{a.agent}</strong> · {a.model} · conf{" "}
                {a.confidence ?? "—"} · ${a.cost_usd} · {a.latency_ms}ms
                {a.policy_version ? ` · policy v${a.policy_version}` : ""}
              </summary>
              <pre style={{ overflowX: "auto", fontSize: 12 }}>
                {JSON.stringify(a.parsed_output, null, 2)}
              </pre>
            </details>
          ),
        )}

        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          {data.photo_urls.map((u: string) => (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              key={u}
              src={u}
              alt="return"
              style={{ width: 180, borderRadius: 8 }}
            />
          ))}
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <CaseActions
          id={id}
          canAct={roles.includes("reviewer") || roles.includes("admin")}
          status={r.status}
        />
        <h2 style={{ fontWeight: 600 }}>Live trace</h2>
        <LiveTrace id={id} initial={data.events} />
      </div>
    </div>
  );
}
