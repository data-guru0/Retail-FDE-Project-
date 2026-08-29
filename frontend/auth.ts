import NextAuth from "next-auth";
import Keycloak from "next-auth/providers/keycloak";

const ISSUER = process.env.KEYCLOAK_ISSUER ?? "http://localhost:8081/realms/returnguard";

export const { handlers, auth, signIn, signOut } = NextAuth({
  trustHost: true,
  providers: [
    Keycloak({
      issuer: ISSUER,
      clientId: process.env.KEYCLOAK_CLIENT_ID ?? "returnguard-web",
      clientSecret: process.env.KEYCLOAK_CLIENT_SECRET ?? "",
    }),
  ],
  callbacks: {
    async jwt({ token, account }) {
      if (account) {
        token.accessToken = account.access_token;
        token.refreshToken = account.refresh_token;
        token.expiresAt = account.expires_at;
      }
      return token;
    },
    async session({ session, token }) {
      // expose the Keycloak access token + realm roles to the client
      (session as unknown as { accessToken?: string }).accessToken =
        token.accessToken as string | undefined;
      try {
        const claims = JSON.parse(
          Buffer.from((token.accessToken as string).split(".")[1], "base64").toString(),
        );
        (session.user as unknown as { roles: string[] }).roles =
          claims?.realm_access?.roles ?? [];
      } catch {
        (session.user as unknown as { roles: string[] }).roles = [];
      }
      return session;
    },
  },
});
