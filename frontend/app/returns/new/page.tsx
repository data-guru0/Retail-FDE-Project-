"use client";
import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

const REASONS = [
  "damaged",
  "defective",
  "not_as_described",
  "wrong_item",
  "quality",
  "arrived_late",
  "no_longer_needed",
];

function Wizard() {
  const sp = useSearchParams();
  const router = useRouter();
  const itemId = sp.get("item") ?? "";
  const itemName = sp.get("name") ?? "this item";

  const [step, setStep] = useState(1);
  const [reason, setReason] = useState("damaged");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function submit() {
    if (!file) {
      setErr("A photo is required.");
      return;
    }
    setBusy(true);
    setErr("");
    const fd = new FormData();
    fd.set("order_item_id", itemId);
    fd.set("reason_code", reason);
    fd.set("reason_text", text);
    fd.set("photo", file);
    const res = await fetch("/api/rg/returns", { method: "POST", body: fd });
    if (!res.ok) {
      setErr(`${res.status}: ${await res.text()}`);
      setBusy(false);
      return;
    }
    const r = await res.json();
    router.push(`/returns/${r.id}`);
  }

  return (
    <div
      style={{
        maxWidth: 520,
        display: "flex",
        flexDirection: "column",
        gap: 12,
      }}
    >
      <h1 style={{ fontSize: 22, fontWeight: 700 }}>Return: {itemName}</h1>
      <div className="muted">Step {step} of 3</div>

      {step === 1 && (
        <>
          <label>Why are you returning this?</label>
          <select
            className="select"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          >
            {REASONS.map((r) => (
              <option key={r} value={r}>
                {r.replace(/_/g, " ")}
              </option>
            ))}
          </select>
          <button className="btn" onClick={() => setStep(2)}>
            Next
          </button>
        </>
      )}

      {step === 2 && (
        <>
          <label>Tell us more (optional)</label>
          <textarea
            className="input"
            rows={4}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="e.g. The rim was cracked when it arrived."
          />
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn secondary" onClick={() => setStep(1)}>
              Back
            </button>
            <button className="btn" onClick={() => setStep(3)}>
              Next
            </button>
          </div>
        </>
      )}

      {step === 3 && (
        <>
          <label>Upload a photo of the item (required)</label>
          <input
            className="input"
            type="file"
            accept="image/*"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          {err && <div style={{ color: "#ff8a8a" }}>{err}</div>}
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn secondary" onClick={() => setStep(2)}>
              Back
            </button>
            <button className="btn" disabled={busy} onClick={submit}>
              {busy ? "Submitting…" : "Submit return"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

export default function NewReturnPage() {
  return (
    <Suspense fallback={<p>Loading…</p>}>
      <Wizard />
    </Suspense>
  );
}
