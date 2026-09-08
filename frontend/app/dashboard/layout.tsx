import Link from "next/link";
import { redirect } from "next/navigation";
import { auth } from "@/auth";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await auth();
  const roles = (session?.user as unknown as { roles?: string[] })?.roles ?? [];
  if (!session || !(roles.includes("reviewer") || roles.includes("admin"))) {
    redirect("/");
  }
  const admin = roles.includes("admin");
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <nav style={{ display: "flex", gap: 12 }}>
        <Link href="/dashboard" className="btn secondary">
          Queue
        </Link>
        <Link href="/dashboard/analytics" className="btn secondary">
          Analytics
        </Link>
        <Link href="/dashboard/appeals" className="btn secondary">
          Appeals
        </Link>
        {admin && (
          <Link href="/dashboard/governance" className="btn secondary">
            Governance
          </Link>
        )}
        {admin && (
          <Link href="/dashboard/policy" className="btn secondary">
            Policy
          </Link>
        )}
      </nav>
      {children}
    </div>
  );
}
