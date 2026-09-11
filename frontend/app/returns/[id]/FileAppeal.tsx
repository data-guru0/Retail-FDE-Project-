"use client";
import { useState } from "react";

export function FileAppeal({ returnId }: { returnId: string }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [done, setDone] = useState(false);

  async function send() {
    setBusy(true);
    setErr("");
    const res = await fetch(`/api/rg/appeals/returns/${returnId}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ reason }),
    });
    setBusy(false);
    if (res.ok) {
      // no router.refresh() here: opening the appeal flips returns.status away
      // from "denied" server-side, which would unmount this component (via the
      // `status === "denied"` check in page.tsx) before the confirmation ever
      // painted. The next real page load picks up the fresh status normally.
      setDone(true);
    } else setErr(`${res.status}: ${await res.text()}`);
  }

  if (done) {
    return (
      <div className="card" style={{ padding: 14, borderColor: "var(--accent)" }}>
        Appeal submitted — a different reviewer than the one who decided this
        case will take another look.
      </div>
    );
  }

  if (!open) {
    return (
      <button className="btn secondary" onClick={() => setOpen(true)}>
        Appeal this decision
      </button>
    );
  }

  return (
    <div className="card" style={{ padding: 14, borderColor: "var(--accent)" }}>
      <strong>Tell us why this should be reconsidered</strong>
      <textarea
        className="input"
        rows={3}
        style={{ marginTop: 8 }}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder="e.g. The photo does show the defect described…"
      />
      <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
        <button className="btn" disabled={busy || !reason} onClick={send}>
          {busy ? "Sending…" : "Submit appeal"}
        </button>
        <button className="btn secondary" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
      {err && <div style={{ color: "#ff8a8a", marginTop: 8 }}>{err}</div>}
    </div>
  );
}
