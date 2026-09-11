"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

export function GovernanceForm({ flag }: { flag: Record<string, unknown> }) {
  const router = useRouter();
  const [f, setF] = useState(flag);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function save() {
    setBusy(true);
    setErr("");
    const res = await fetch("/api/rg/dashboard/governance", {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        scope: f.scope,
        automation_level: f.automation_level,
        kill_switch: f.kill_switch,
        qa_sample_pct: Number(f.qa_sample_pct),
        tau_risk: Number(f.tau_risk),
        tau_conf: Number(f.tau_conf),
      }),
    });
    setBusy(false);
    if (!res.ok) {
      // a governance control must never fail silently
      setErr(`save failed — ${res.status}: ${await res.text()}`);
      return;
    }
    router.refresh();
  }

  return (
    <div className="d-section">
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span className="d-badge info">
          <span className="dot" />
          {String(f.scope)}
        </span>
        {Boolean(f.kill_switch) && (
          <span className="d-badge danger">
            <span className="dot" />
            kill switch active
          </span>
        )}
      </div>
      <div className="d-gov-grid">
        <div className="d-field">
          <label>Automation level</label>
          <select
            className="select"
            value={String(f.automation_level)}
            onChange={(e) => setF({ ...f, automation_level: e.target.value })}
            style={{ width: 140 }}
          >
            {["shadow", "suggest", "assist", "auto"].map((l) => (
              <option key={l}>{l}</option>
            ))}
          </select>
        </div>
        <div className="d-field">
          <label>Kill switch</label>
          <div className="d-switch-row" style={{ height: 34 }}>
            <input
              type="checkbox"
              checked={Boolean(f.kill_switch)}
              onChange={(e) => setF({ ...f, kill_switch: e.target.checked })}
            />
            force human review
          </div>
        </div>
        <div className="d-field">
          <label>QA sample %</label>
          <input
            className="input"
            style={{ width: 70 }}
            value={String(f.qa_sample_pct)}
            onChange={(e) => setF({ ...f, qa_sample_pct: e.target.value })}
          />
        </div>
        <div className="d-field">
          <label>τ_risk</label>
          <input
            className="input"
            style={{ width: 70 }}
            value={String(f.tau_risk)}
            onChange={(e) => setF({ ...f, tau_risk: e.target.value })}
          />
        </div>
        <div className="d-field">
          <label>τ_conf</label>
          <input
            className="input"
            style={{ width: 70 }}
            value={String(f.tau_conf)}
            onChange={(e) => setF({ ...f, tau_conf: e.target.value })}
          />
        </div>
        <button className="btn" disabled={busy} onClick={save}>
          Save
        </button>
      </div>
      {err && <div className="d-error">{err}</div>}
    </div>
  );
}
