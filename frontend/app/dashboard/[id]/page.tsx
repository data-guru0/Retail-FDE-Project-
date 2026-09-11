import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { CaseActions } from "./CaseActions";
import { LiveTrace } from "./LiveTrace";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

function statusBadge(v: string | null) {
  const cls =
    v === "approved" || v === "refunded"
      ? "ok"
      : v === "denied"
        ? "danger"
        : v === "escalated"
          ? "warn"
          : v === "deny"
            ? "danger"
            : v === "approve"
              ? "ok"
              : v === "escalate"
                ? "warn"
                : "";
  return (
    <span className={`d-badge ${cls}`}>
      <span className="dot" />
      {v ?? "—"}
    </span>
  );
}

export default async function CaseDetail({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const session = await auth();
  if (!session) redirect("/");
  const token = (session as unknown as { accessToken?: string }).accessToken;
  const roles = (session?.user as unknown as { roles?: string[] })?.roles ?? [];
  const data = await fetch(`${BACKEND}/dashboard/returns/${id}`, {
    headers: { authorization: `Bearer ${token}` },
    cache: "no-store",
  }).then((r) => r.json());

  const r = data.return;
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 20 }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <div className="d-head">
          <h1>Case #{id.slice(0, 8)}</h1>
        </div>
        <div className="d-section">
          <div className="d-kv-grid">
            <div>
              <div className="k">Status</div>
              <div className="v">{statusBadge(r.status)}</div>
            </div>
            <div>
              <div className="k">Agent proposed</div>
              <div className="v">{statusBadge(r.decision)}</div>
            </div>
            <div>
              <div className="k">Final</div>
              <div className="v">{statusBadge(r.final_decision)}</div>
            </div>
            <div>
              <div className="k">Amount</div>
              <div className="v">${r.amount}</div>
            </div>
            <div>
              <div className="k">Customer</div>
              <div className="v" style={{ fontSize: 13, fontWeight: 500 }}>
                {r.customer}
              </div>
            </div>
            <div>
              <div className="k">Reason</div>
              <div className="v" style={{ fontSize: 13, fontWeight: 500 }}>
                {r.reason_code}
              </div>
            </div>
          </div>
          <p className="muted" style={{ fontSize: 13.5 }}>{r.reason_text}</p>
          {r.decision_reason && (
            <>
              <div
                style={{
                  height: 1,
                  background: "var(--border)",
                  margin: "2px 0",
                }}
              />
              <p className="muted" style={{ fontSize: 13.5, lineHeight: 1.5 }}>
                {r.decision_reason}
              </p>
            </>
          )}
        </div>

        {data.info_requests.length > 0 && (
          <div className="d-section">
            <h3>Info requests</h3>
            {data.info_requests.map(
              (
                q: {
                  question: string;
                  answer: string | null;
                  created_at: string;
                  answered_at: string | null;
                },
                i: number,
              ) => (
                <div key={i} style={{ fontSize: 13.5, lineHeight: 1.5 }}>
                  <div>
                    <span className="d-badge info">
                      <span className="dot" />
                      asked
                    </span>{" "}
                    {q.question}
                  </div>
                  {q.answer ? (
                    <div style={{ marginTop: 4 }}>
                      <span className="d-badge ok">
                        <span className="dot" />
                        answered
                      </span>{" "}
                      {q.answer}
                    </div>
                  ) : (
                    <div className="muted" style={{ marginTop: 4 }}>
                      <span className="d-badge warn">
                        <span className="dot" />
                        waiting on customer
                      </span>
                    </div>
                  )}
                </div>
              ),
            )}
          </div>
        )}

        <h2 style={{ fontSize: 15, fontWeight: 700 }}>Agent reasoning</h2>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
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
              <details key={a.agent + a.model} className="d-section d-agent">
                <summary>
                  <span className="d-badge info">
                    <span className="dot" />
                    {a.agent}
                  </span>
                  <span className="muted">{a.model}</span>
                  <span className="muted">conf {a.confidence ?? "—"}</span>
                  <span className="muted num">${a.cost_usd}</span>
                  <span className="muted num">{a.latency_ms}ms</span>
                  {a.policy_version ? (
                    <span className="d-chip">policy v{a.policy_version}</span>
                  ) : null}
                </summary>
                <pre>{JSON.stringify(a.parsed_output, null, 2)}</pre>
              </details>
            ),
          )}
        </div>

        {data.photo_urls.length > 0 && (
          <div className="d-section">
            <h3>Return photos</h3>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              {data.photo_urls.map((u: string) => (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  key={u}
                  src={u}
                  alt="return"
                  style={{
                    width: 180,
                    borderRadius: 8,
                    border: "1px solid var(--border)",
                  }}
                />
              ))}
            </div>
          </div>
        )}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <CaseActions
          id={id}
          canAct={roles.includes("reviewer") || roles.includes("admin")}
          status={r.status}
          level={data.automation_level}
          agentDecision={r.decision}
          agentReason={r.decision_reason}
        />
        <h2 style={{ fontSize: 15, fontWeight: 700 }}>Live trace</h2>
        <LiveTrace id={id} initial={data.events} />
      </div>
    </div>
  );
}
