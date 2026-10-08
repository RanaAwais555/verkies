import type { NextConfig } from "next";

// Outside Docker there is no reverse proxy, so forward /api to the backend to keep the browser
// on one origin: always in `npm run dev`, and in a production build only when
// VROS_API_INTERNAL_URL is set at build time (the end-to-end tests). In Docker, Caddy routes
// /api to the API and the image is built without it.
const apiUrl = process.env.VROS_API_INTERNAL_URL ?? "http://localhost:8000";
const proxyApi = process.env.NODE_ENV !== "production" || !!process.env.VROS_API_INTERNAL_URL;

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
    if (!proxyApi) return [];
    return [{ source: "/api/:path*", destination: `${apiUrl}/api/:path*` }];
  },
};

export default nextConfig;
