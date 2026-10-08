import type { NextConfig } from "next";

// `npm run dev` outside Docker has no reverse proxy, so forward /api to the backend to keep
// the browser on one origin. In Docker (dev and production) Caddy routes /api instead.
const devApiUrl = process.env.VROS_API_INTERNAL_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    if (process.env.NODE_ENV === "production") return [];
    return [{ source: "/api/:path*", destination: `${devApiUrl}/api/:path*` }];
  },
};

export default nextConfig;
