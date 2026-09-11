import { auth } from "@/auth";
import { redirect } from "next/navigation";
import type { ReturnRow } from "@/app/lib/api";
import { AnswerInfoRequest } from "./AnswerInfoRequest";
import { FileAppeal } from "./FileAppeal";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

const STAGES = ["under review", "decided", "refunded"];

export default async function ReturnStatusPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const session = await auth();
  if (!session) redirect("/api/auth/signin");
  const { id } = await params;
  const token = (session as unknown as { accessToken?: string }).accessToken;
  const h = { authorization: `Bearer ${token}` };
  const [r, infoReq]: [ReturnRow, { id?: string; question?: string }] =
    await Promise.all([
      fetch(`${BACKEND}/returns/${id}`, { headers: h, cache: "no-store" }).then(
        (res) => res.json(),
      ),
      fetch(`${BACKEND}/returns/${id}/info-request`, {
        headers: h,
        cache: "no-store",
      }).then((res) => res.json()),
    ]);

  const stageIdx =
    r.refund_state === "refunded"
      ? 2
      : ["approved", "denied"].includes(r.status)
        ? 1
        : 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <h1 style={{ fontSize: 22, fontWeight: 700 }}>
        Return #{r.id.slice(0, 8)}
      </h1>

      <div style={{ display: "flex", gap: 8 }}>
        {STAGES.map((s, i) => (
          <div
            key={s}
            className="card"
            style={{
              padding: "6px 12px",
              opacity: i <= stageIdx ? 1 : 0.4,
              borderColor: i === stageIdx ? "var(--accent)" : "var(--border)",
            }}
          >
            {s}
          </div>
        ))}
      </div>

      {infoReq?.question && (
        <AnswerInfoRequest returnId={id} question={infoReq.question} />
      )}

      <div className="card" style={{ padding: 14 }}>
        <div>
          <strong>Status:</strong> {r.status}
        </div>
        <div>
          <strong>Reason:</strong> {r.reason_code}
          {r.reason_text ? ` — ${r.reason_text}` : ""}
        </div>
        <div>
          <strong>Amount:</strong> ${r.amount}
        </div>
        {r.final_decision && (
          <div>
            <strong>Decision:</strong> {r.final_decision}
          </div>
        )}
        {r.decision_reason && (
          <div style={{ marginTop: 8 }}>
            <strong>Explanation:</strong>
            <p className="muted">{r.decision_reason}</p>
          </div>
        )}
      </div>

      {r.status === "denied" && <FileAppeal returnId={id} />}

      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        {r.photo_urls.map((u) => (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            key={u}
            src={u}
            alt="return"
            style={{ width: 200, borderRadius: 8 }}
          />
        ))}
      </div>
    </div>
  );
}
