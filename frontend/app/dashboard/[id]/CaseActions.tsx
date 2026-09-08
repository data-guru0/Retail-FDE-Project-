"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

export function CaseActions({
  id,
  canAct,
  status,
}: {
  id: string;
  canAct: boolean;
  status: string;
}) {
  const router = useRouter();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const done = ["approved", "denied", "refunded"].includes(status);

  async function call(path: string, body?: object) {
    setBusy(true);
    setMsg("");
    const res = await fetch(`/api/rg/dashboard/returns/${id}/${path}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
    setBusy(false);
    if (res.ok) router.refresh();
    else setMsg(`${res.status}: ${await res.text()}`);
  }

  if (!canAct) return null;
  return (
    <div
      className="card"
      style={{ padding: 14, display: "flex", flexDirection: "column", gap: 8 }}
    >
      <strong>Actions</strong>
      <button
        className="btn secondary"
        disabled={busy}
        onClick={() => call("claim")}
      >
        Claim
      </button>
      <textarea
        className="input"
        rows={2}
        placeholder="decision note / question"
        value={note}
        onChange={(e) => setNote(e.target.value)}
      />
      <div style={{ display: "flex", gap: 8 }}>
        <button
          className="btn"
          disabled={busy || done}
          onClick={() => call("decide", { decision: "approve", note })}
        >
          Approve
        </button>
        <button
          className="btn"
          style={{ background: "#e5534b", color: "#fff" }}
          disabled={busy || done}
          onClick={() => {
            if (confirm("Confirm denial? This is the human confirm step."))
              call("decide", { decision: "deny", note, confirm: true });
          }}
        >
          Deny (confirm)
        </button>
      </div>
      <button
        className="btn secondary"
        disabled={busy || done || !note}
        onClick={() => call("request-info", { question: note })}
      >
        Request info from customer
      </button>
      {msg && <div style={{ color: "#ff8a8a", fontSize: 13 }}>{msg}</div>}
    </div>
  );
}
