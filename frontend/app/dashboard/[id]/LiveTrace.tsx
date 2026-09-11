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
    <div className="d-section" style={{ padding: 10 }}>
      <div className="d-trace">
        {events.map((e, i) => (
          <div key={i} className="d-trace-item">
            <span className={`d-trace-dot ${e.kind}`} />
            <div className="d-trace-body">
              <div className="d-trace-head">
                <strong>{e.agent}</strong>
                <span className="muted">· {e.kind}</span>
              </div>
              <pre>{JSON.stringify(e.payload, null, 1)}</pre>
            </div>
          </div>
        ))}
        {events.length === 0 && (
          <div className="d-empty">waiting for pipeline events…</div>
        )}
      </div>
    </div>
  );
}
