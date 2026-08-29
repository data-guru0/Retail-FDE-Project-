import type { NextConfig } from "next";

const config: NextConfig = {
  images: {
    remotePatterns: [{ protocol: "http", hostname: "localhost", port: "9000" }],
  },
  async rewrites() {
    return [{ source: "/api/backend/:path*", destination: "http://localhost:8000/:path*" }];
  },
};

export default config;
