import type { NextConfig } from "next";

// The browser talks to the API same-origin via /api/* by default; Next proxies to the backend.
// This keeps one forwarded port in Codespaces and avoids CORS in local dev.
const apiInternalUrl = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
// Proxied request bodies are buffered by Next and truncated past this size (default 10 MB), which
// would break reference uploads. Allow the API's own limit plus multipart overhead; the API still
// enforces the real limit while streaming. See DECISIONS.md (2026-11-25).
const maxUploadMb = Number(process.env.MAX_UPLOAD_MB ?? 200);

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  poweredByHeader: false,
  experimental: {
    proxyClientMaxBodySize: `${maxUploadMb + 1}mb`,
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiInternalUrl}/api/:path*` }];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(self), microphone=(self)" },
        ],
      },
    ];
  },
};

export default nextConfig;
