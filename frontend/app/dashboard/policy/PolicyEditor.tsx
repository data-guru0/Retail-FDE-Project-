"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

type Doc = { slug: string; title: string; body: string; version: number };

export function PolicyEditor({ docs }: { docs: Doc[] }) {
  const router = useRouter();
  const [edits, setEdits] = useState<Record<string, Doc>>(
    Object.fromEntries(docs.map((d) => [d.slug, d])),
  );
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  async function save() {
    setBusy(true);
    setMsg("");
    const res = await fetch("/api/rg/dashboard/policy", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(Object.values(edits)),
    });
    setBusy(false);
    if (res.ok) {
      const j = await res.json();
      setMsg(`saved as version ${j.new_version}, re-embed ${j.reembed}`);
      router.refresh();
    } else setMsg(`${res.status}: ${await res.text()}`);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div className="d-version">current version: {docs[0]?.version}</div>
      {docs.map((d) => (
        <div key={d.slug} className="d-section">
          <div className="d-doc-head">
            <span className="d-chip">{d.slug}</span>
          </div>
          <input
            className="input"
            style={{ fontWeight: 600 }}
            value={edits[d.slug].title}
            onChange={(e) =>
              setEdits({
                ...edits,
                [d.slug]: { ...edits[d.slug], title: e.target.value },
              })
            }
          />
          <textarea
            className="input"
            rows={5}
            value={edits[d.slug].body}
            onChange={(e) =>
              setEdits({
                ...edits,
                [d.slug]: { ...edits[d.slug], body: e.target.value },
              })
            }
          />
        </div>
      ))}
      <button className="btn" disabled={busy} onClick={save}>
        Save new version + re-embed
      </button>
      {msg && <div className="d-toast">{msg}</div>}
    </div>
  );
}
