import { redirect } from "next/navigation";
import { auth } from "@/auth";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

type VsBaseline = {
  reviewer_hours_saved: number;
  dollars_saved: number;
  time_to_decision_p50_s: number;
  time_to_decision_p95_s: number;
};
type ByModel = { model: string; cost_usd: number; runs: number };
type UnitEconomics = {
  cost_per_decision_usd: number;
  by_model: ByModel[];
  monthly_projection_usd: number;
};
type Quality = {
  reviewed: number;
  agreement_rate: number;
  false_positive_overrides: number;
};
type Counts = {
  auto_approved: number;
  escalated: number;
  human_decided: number;
  qa_samples: number;
};
type PerAgent = {
  agent: string;
  runs: number;
  avg_latency_ms: number;
  avg_confidence: number | null;
  cost_usd: string;
  tokens: number;
  errors: number;
};
type TrendPoint = { day: string; agreement: number; n: number };
type Ring = { kind: string; fingerprint: string; accounts: string[] };

function Stat({ v, l }: { v: string; l: string }) {
  return (
    <div className="d-stat">
      <div className="v">{v}</div>
      <div className="l">{l}</div>
    </div>
  );
}

function BarRow({
  name,
  frac,
  val,
}: {
  name: string;
  frac: number;
  val: string;
}) {
  return (
    <div className="d-bar-row">
      <div className="name" title={name}>
        {name}
      </div>
      <div className="d-bar-track">
        <div
          className="d-bar-fill"
          style={{ width: `${Math.max(3, Math.round(frac * 100))}%` }}
        />
      </div>
      <div className="val">{val}</div>
    </div>
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

  const vs: VsBaseline = a.vs_baseline;
  const econ: UnitEconomics = a.unit_economics;
  const quality: Quality = a.quality;
  const counts: Counts = a.counts;
  const perAgent: PerAgent[] = health.per_agent;
  const trend: TrendPoint[] = health.agreement_trend;
  const ringList: Ring[] = rings;

  const maxModelCost = Math.max(0.000001, ...econ.by_model.map((m) => m.cost_usd));
  const totalRouted =
    counts.auto_approved + counts.escalated + counts.human_decided || 1;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div className="d-head">
        <h1>Analytics</h1>
        <p>
          Every number below comes from a live query against Postgres — decision
          counts, LLM spend, per-agent latency, agent-vs-human agreement, and
          shared-fingerprint clusters. Nothing here is sample data.
        </p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
        <div className="d-section">
          <h3>vs all-human baseline</h3>
          <div className="d-stat-grid">
            <Stat v={`${vs.reviewer_hours_saved}h`} l="hours saved" />
            <Stat v={`$${vs.dollars_saved}`} l="dollars saved" />
            <Stat v={`${vs.time_to_decision_p50_s}s`} l="time to decision (p50)" />
            <Stat v={`${vs.time_to_decision_p95_s}s`} l="time to decision (p95)" />
          </div>
        </div>

        <div className="d-section">
          <h3>Unit economics</h3>
          <div className="d-stat-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
            <Stat v={`$${econ.cost_per_decision_usd}`} l="cost / decision" />
            <Stat
              v={`$${econ.monthly_projection_usd}`}
              l="monthly projection"
            />
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 7, marginTop: 2 }}>
            {econ.by_model.map((m) => (
              <BarRow
                key={m.model}
                name={m.model}
                frac={m.cost_usd / maxModelCost}
                val={`$${m.cost_usd} · ${m.runs}`}
              />
            ))}
          </div>
        </div>

        <div className="d-section">
          <h3>Quality (from real overrides)</h3>
          <div className="d-stat-grid" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
            <Stat v={String(quality.reviewed)} l="human overrides reviewed" />
            <Stat
              v={`${Math.round(quality.agreement_rate * 100)}%`}
              l="agreement rate"
            />
            <Stat
              v={String(quality.false_positive_overrides)}
              l="false-positive overrides"
            />
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 7, marginTop: 2 }}>
            <BarRow
              name="auto-approved"
              frac={counts.auto_approved / totalRouted}
              val={String(counts.auto_approved)}
            />
            <BarRow
              name="escalated"
              frac={counts.escalated / totalRouted}
              val={String(counts.escalated)}
            />
            <BarRow
              name="human-decided"
              frac={counts.human_decided / totalRouted}
              val={String(counts.human_decided)}
            />
            <BarRow
              name="qa samples"
              frac={counts.qa_samples / totalRouted}
              val={String(counts.qa_samples)}
            />
          </div>
        </div>

        <div className="d-section">
          <h3>Agent health</h3>
          <table className="d-table">
            <thead>
              <tr>
                <th>Agent</th>
                <th>Runs</th>
                <th>Latency</th>
                <th>Conf.</th>
                <th>Cost</th>
                <th>Errors</th>
              </tr>
            </thead>
            <tbody>
              {perAgent.map((r) => (
                <tr key={r.agent}>
                  <td>{r.agent}</td>
                  <td className="num muted">{r.runs}</td>
                  <td className="num muted">{r.avg_latency_ms}ms</td>
                  <td className="num muted">{r.avg_confidence ?? "—"}</td>
                  <td className="num muted">${r.cost_usd}</td>
                  <td className="num">
                    {r.errors > 0 ? (
                      <span className="d-badge danger">
                        <span className="dot" />
                        {r.errors}
                      </span>
                    ) : (
                      <span className="muted">0</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="d-section">
        <h3>Agent-vs-human agreement trend</h3>
        {trend.length === 0 ? (
          <div className="d-empty">no overrides recorded yet</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
            {trend.map((t) => (
              <BarRow
                key={t.day}
                name={t.day.slice(0, 10)}
                frac={t.agreement}
                val={`${Math.round(t.agreement * 100)}% · n=${t.n}`}
              />
            ))}
          </div>
        )}
      </div>

      <div className="d-section">
        <h3>Ring detection (shared fingerprints)</h3>
        {ringList.length === 0 ? (
          <div className="d-empty">no shared address/device fingerprints found</div>
        ) : (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
              gap: 10,
            }}
          >
            {ringList.map((ring, i) => (
              <div
                key={i}
                className="d-section"
                style={{ padding: 12, background: "rgba(255,255,255,0.02)" }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span className="d-badge warn">
                    <span className="dot" />
                    {ring.kind}
                  </span>
                  <span className="d-chip">{ring.fingerprint}</span>
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {ring.accounts.map((acc) => (
                    <span key={acc} className="d-chip">
                      {acc}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
