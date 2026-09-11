import Link from "next/link";
import { redirect } from "next/navigation";
import { auth } from "@/auth";
import "./dashboard.css";

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
    <div className="d-shell">
      <nav className="d-nav">
        <Link href="/dashboard">Queue</Link>
        <Link href="/dashboard/analytics">Analytics</Link>
        <Link href="/dashboard/appeals">Appeals</Link>
        {admin && (
          <Link href="/dashboard/governance" className="admin">
            Governance
          </Link>
        )}
        {admin && (
          <Link href="/dashboard/policy" className="admin">
            Policy
          </Link>
        )}
      </nav>
      {children}
    </div>
  );
}
