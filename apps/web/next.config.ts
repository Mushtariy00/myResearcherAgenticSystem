import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Self-contained server bundle for the Docker image.
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
  // No rewrites to the API: Caddy routes /api/v1/* straight to FastAPI so SSE is never buffered.
};

export default nextConfig;
