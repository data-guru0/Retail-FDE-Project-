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

  async function send() {
    setBusy(true);
    const fd = new FormData();
    fd.set("answer", answer);
    const res = await fetch(`/api/rg/returns/${returnId}/info-request`, {
      method: "POST",
      body: fd,
    });
    setBusy(false);
    if (res.ok) router.refresh();
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
    </div>
  );
}
