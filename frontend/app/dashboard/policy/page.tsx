import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { PolicyEditor } from "./PolicyEditor";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export default async function PolicyPage() {
  const session = await auth();
  if (!session) redirect("/");
  const token = (session as unknown as { accessToken?: string }).accessToken;
  const docs = await fetch(`${BACKEND}/dashboard/policy`, {
    headers: { authorization: `Bearer ${token}` },
    cache: "no-store",
  }).then((r) => r.json());

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div className="d-head">
        <h1>Policy editor</h1>
        <p>
          Saving creates a new <code>policy_docs</code> version and re-embeds
          it into Qdrant. Later cases record which version applied (
          <code>agent_runs.policy_version</code>).
        </p>
      </div>
      <PolicyEditor docs={docs} />
    </div>
  );
}
