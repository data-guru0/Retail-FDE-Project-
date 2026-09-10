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
    <div
      className="card"
      style={{
        padding: 14,
        display: "flex",
        gap: 16,
        alignItems: "center",
        flexWrap: "wrap",
      }}
    >
      <strong style={{ minWidth: 90 }}>{String(f.scope)}</strong>
      <label>
        level{" "}
        <select
          className="select"
          value={String(f.automation_level)}
          onChange={(e) => setF({ ...f, automation_level: e.target.value })}
          style={{ width: 130, display: "inline-block" }}
        >
          {["shadow", "suggest", "assist", "auto"].map((l) => (
            <option key={l}>{l}</option>
          ))}
        </select>
      </label>
      <label>
        <input
          type="checkbox"
          checked={Boolean(f.kill_switch)}
          onChange={(e) => setF({ ...f, kill_switch: e.target.checked })}
        />{" "}
        kill switch
      </label>
      <label>
        QA %{" "}
        <input
          className="input"
          style={{ width: 60, display: "inline-block" }}
          value={String(f.qa_sample_pct)}
          onChange={(e) => setF({ ...f, qa_sample_pct: e.target.value })}
        />
      </label>
      <label>
        τ_risk{" "}
        <input
          className="input"
          style={{ width: 60, display: "inline-block" }}
          value={String(f.tau_risk)}
          onChange={(e) => setF({ ...f, tau_risk: e.target.value })}
        />
      </label>
      <label>
        τ_conf{" "}
        <input
          className="input"
          style={{ width: 60, display: "inline-block" }}
          value={String(f.tau_conf)}
          onChange={(e) => setF({ ...f, tau_conf: e.target.value })}
        />
      </label>
      <button className="btn" disabled={busy} onClick={save}>
        Save
      </button>
      {err && (
        <div style={{ color: "#ff8a8a", flexBasis: "100%" }}>{err}</div>
      )}
    </div>
  );
}
