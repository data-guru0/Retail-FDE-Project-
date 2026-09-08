import "./globals.css";
import type { Metadata } from "next";
import { Nav } from "./components/Nav";

export const metadata: Metadata = {
  title: "ReturnGuard Shop",
  description: "Shop + governed return review",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <Nav />
        <main
          style={{
            maxWidth: 1080,
            margin: "0 auto",
            padding: "1.5rem 1rem 4rem",
          }}
        >
          {children}
        </main>
      </body>
    </html>
  );
}
