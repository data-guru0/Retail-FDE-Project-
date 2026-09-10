"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

export function AnswerInfoRequest({
  returnId,
  question,
}: {
  returnId: string;
  question: string;
}) {
  const router = useRouter();
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function send() {
    setBusy(true);
    setErr("");
    const fd = new FormData();
    fd.set("answer", answer);
    const res = await fetch(`/api/rg/returns/${returnId}/info-request`, {
      method: "POST",
      body: fd,
    });
    setBusy(false);
    if (res.ok) router.refresh();
    else setErr(`could not send — ${res.status}: ${await res.text()}`);
  }

  return (
    <div className="card" style={{ padding: 14, borderColor: "var(--accent)" }}>
      <strong>The reviewer has a question:</strong>
      <p className="muted">{question}</p>
      <textarea
        className="input"
        rows={3}
        value={answer}
        onChange={(e) => setAnswer(e.target.value)}
        placeholder="Your answer…"
      />
      <button
        className="btn"
        style={{ marginTop: 8 }}
        disabled={busy || !answer}
        onClick={send}
      >
        {busy ? "Sending…" : "Send answer — this re-opens the review"}
      </button>
      {err && (
        <div style={{ color: "#ff8a8a", marginTop: 8 }}>{err}</div>
      )}
    </div>
  );
}
