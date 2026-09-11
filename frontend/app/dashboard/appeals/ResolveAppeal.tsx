"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

export function ResolveAppeal({ id }: { id: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function resolve(outcome: "approve" | "deny") {
    if (outcome === "deny" && !confirm("Confirm denial of this appeal?")) return;
    setBusy(true);
    setErr("");
    const res = await fetch(
      `/api/rg/appeals/${id}/resolve?outcome=${outcome}`,
      { method: "POST" },
    );
    setBusy(false);
    if (res.ok) router.refresh();
    else setErr(`${res.status}: ${await res.text()}`);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div className="d-actions-row">
        <button className="btn" disabled={busy} onClick={() => resolve("approve")}>
          Approve appeal
        </button>
        <button
          className="btn"
          style={{ background: "#e5534b", color: "#fff" }}
          disabled={busy}
          onClick={() => resolve("deny")}
        >
          Deny appeal
        </button>
      </div>
      {err && <div className="d-error">{err}</div>}
    </div>
  );
}
