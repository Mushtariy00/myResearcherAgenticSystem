import path from "node:path";
import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";
import { loadRootEnv } from "./src/lib/load-env.ts";

// The repo-root .env is shared with the Python services; only the web app's own keys are loaded.
loadRootEnv(path.resolve(typeof __dirname === "string" ? __dirname : process.cwd(), "../.."));

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=()" },
];

const nextConfig: NextConfig = {
  // Self-contained server bundle for the Docker image.
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
  // Native argon2 binding and the Postgres driver stay as plain Node modules.
  serverExternalPackages: ["@node-rs/argon2", "pg"],
  // No rewrites to the API: Caddy routes /api/v1/* straight to FastAPI so SSE is never buffered.
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

export default withNextIntl(nextConfig);
