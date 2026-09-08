"use client";
import { useEffect, useState } from "react";

type Ev = { seq?: number; agent: string; kind: string; payload: unknown };

export function LiveTrace({ id, initial }: { id: string; initial: Ev[] }) {
  const [events, setEvents] = useState<Ev[]>(initial ?? []);

  useEffect(() => {
    const ws = new WebSocket(`ws://localhost:8000/ws/returns/${id}`);
    ws.onmessage = (m) => {
      try {
        const e = JSON.parse(m.data);
        if (e.kind) setEvents((cur) => [...cur, e]);
      } catch {
        /* heartbeat */
      }
    };
    return () => ws.close();
  }, [id]);

  return (
    <div
      className="card"
      style={{ padding: 12, maxHeight: 480, overflowY: "auto" }}
    >
      {events.map((e, i) => (
        <div
          key={i}
          style={{ borderBottom: "1px solid var(--border)", padding: "6px 0" }}
        >
          <div style={{ fontSize: 13 }}>
            <strong>{e.agent}</strong> · {e.kind}
          </div>
          <pre
            className="muted"
            style={{ fontSize: 11, overflowX: "auto", margin: 0 }}
          >
            {JSON.stringify(e.payload, null, 1)}
          </pre>
        </div>
      ))}
      {events.length === 0 && (
        <div className="muted">waiting for pipeline events…</div>
      )}
    </div>
  );
}
