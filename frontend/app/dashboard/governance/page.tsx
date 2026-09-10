import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { GovernanceForm } from "./GovernanceForm";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export default async function GovernancePage() {
  const session = await auth();
  if (!session) redirect("/");
  const token = (session as unknown as { accessToken?: string }).accessToken;
  const flags = await fetch(`${BACKEND}/dashboard/governance`, {
    headers: { authorization: `Bearer ${token}` },
    cache: "no-store",
  }).then((r) => r.json());

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <h1 style={{ fontSize: 22, fontWeight: 700 }}>Governance</h1>
      <p className="muted">
        shadow → suggest → assist → auto. Every deployment starts in shadow;
        moving up is a deliberate act, justified by the agreement trend. The
        kill switch forces every case to a human regardless of level.
      </p>
      {flags.map((f: Record<string, unknown>) => (
        <GovernanceForm key={f.scope as string} flag={f} />
      ))}
    </div>
  );
}
