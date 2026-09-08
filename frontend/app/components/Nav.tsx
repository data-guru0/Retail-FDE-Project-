import Link from "next/link";
import { auth, signIn, signOut } from "@/auth";
import { CartBadge } from "./CartBadge";

export async function Nav() {
  const session = await auth();
  const roles = (session?.user as unknown as { roles?: string[] })?.roles ?? [];
  const staff = roles.includes("reviewer") || roles.includes("admin");

  return (
    <header
      style={{
        borderBottom: "1px solid var(--border)",
        padding: "0.8rem 1rem",
        display: "flex",
        gap: "1.2rem",
        alignItems: "center",
      }}
    >
      <Link href="/" style={{ fontWeight: 700 }}>
        ReturnGuard
      </Link>
      <Link href="/" className="muted">
        Shop
      </Link>
      {session && (
        <>
          <Link href="/orders" className="muted">
            My orders
          </Link>
          <Link href="/returns" className="muted">
            My returns
          </Link>
        </>
      )}
      {staff && (
        <a href="http://localhost:3000/dashboard" className="muted">
          Dashboard
        </a>
      )}
      <div
        style={{
          marginLeft: "auto",
          display: "flex",
          gap: "1rem",
          alignItems: "center",
        }}
      >
        <CartBadge />
        {session ? (
          <form
            action={async () => {
              "use server";
              await signOut({ redirectTo: "/" });
            }}
          >
            <button className="btn secondary">
              Sign out ({session.user?.email})
            </button>
          </form>
        ) : (
          <form
            action={async () => {
              "use server";
              await signIn("keycloak", { redirectTo: "/" });
            }}
          >
            <button className="btn">Sign in</button>
          </form>
        )}
      </div>
    </header>
  );
}
