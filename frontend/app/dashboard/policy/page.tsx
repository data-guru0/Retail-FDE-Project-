import { auth } from "@/auth";
import { PolicyEditor } from "./PolicyEditor";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export default async function PolicyPage() {
  const session = await auth();
  const token = (session as unknown as { accessToken?: string }).accessToken;
  const docs = await fetch(`${BACKEND}/dashboard/policy`, {
    headers: { authorization: `Bearer ${token}` },
    cache: "no-store",
  }).then((r) => r.json());

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <h1 style={{ fontSize: 22, fontWeight: 700 }}>Policy editor</h1>
      <p className="muted">
        Saving creates a new <code>policy_docs</code> version and re-embeds it
        into Qdrant. Later cases record which version applied (
        <code>agent_runs.policy_version</code>).
      </p>
      <PolicyEditor docs={docs} />
    </div>
  );
}
