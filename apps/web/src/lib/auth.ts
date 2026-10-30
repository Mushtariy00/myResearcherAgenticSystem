/**
 * Better Auth (ADR 0003): email + password, no public sign-up, admin plugin, rate limiting.
 * Tables live in the `auth` schema (AUTH_DATABASE_URL sets search_path=auth).
 *
 * Relative imports carry `.ts` extensions so plain Node (scripts/bootstrap-admin.ts) and the
 * Better Auth CLI can load this file as well as Next.js.
 */
import path from "node:path";
import { betterAuth } from "better-auth";
import { nextCookies } from "better-auth/next-js";
import { admin } from "better-auth/plugins";
import { Pool } from "pg";
import { sendSetPasswordEmail } from "./auth-emails.ts";
import { loadRootEnv } from "./load-env.ts";
import { hashPassword, verifyPassword } from "./password.ts";
import {
  MAX_PASSWORD_LENGTH,
  MIN_PASSWORD_LENGTH,
  SET_PASSWORD_LINK_HOURS,
} from "./password-policy.ts";
import { currentSetPasswordCapture } from "./reset-link.ts";

if (!process.env.AUTH_DATABASE_URL) {
  // CLI and scripts run from apps/web; Next.js already loaded these in next.config.ts.
  loadRootEnv(path.resolve(process.cwd(), "../.."));
}

export { MIN_PASSWORD_LENGTH };

const baseURL = process.env.BETTER_AUTH_URL;

// One pool per process, also across dev hot reloads. Exported so scripts can close it and exit.
const globalPool = globalThis as typeof globalThis & { __arpAuthPool?: Pool };
if (!globalPool.__arpAuthPool) {
  globalPool.__arpAuthPool = new Pool({ connectionString: process.env.AUTH_DATABASE_URL, max: 10 });
}
export const authDbPool: Pool = globalPool.__arpAuthPool;

export const auth = betterAuth({
  appName: "Agentic Research Platform",
  baseURL,
  // Extra origins allowed to sign in, comma-separated (e.g. localhost next to a demo tunnel URL).
  trustedOrigins: (process.env.BETTER_AUTH_TRUSTED_ORIGINS ?? "")
    .split(",")
    .map((origin) => origin.trim())
    .filter(Boolean),
  secret: process.env.BETTER_AUTH_SECRET,
  database: authDbPool,
  emailAndPassword: {
    enabled: true,
    disableSignUp: true, // accounts come from admin invites or the bootstrap CLI only
    minPasswordLength: MIN_PASSWORD_LENGTH,
    maxPasswordLength: MAX_PASSWORD_LENGTH,
    password: { hash: hashPassword, verify: verifyPassword },
    resetPasswordTokenExpiresIn: SET_PASSWORD_LINK_HOURS * 60 * 60,
    revokeSessionsOnPasswordReset: true,
    // Invites and resets use the same single-use link; admins issue both (see lib/invites.ts).
    sendResetPassword: async ({ user, url }) => {
      const capture = currentSetPasswordCapture();
      if (capture) {
        capture.url = url;
      }
      const emailed = await sendSetPasswordEmail(capture?.purpose ?? "reset", {
        to: user.email,
        name: user.name,
        url,
        hours: SET_PASSWORD_LINK_HOURS,
      });
      if (capture) {
        capture.emailed = emailed;
      }
    },
  },
  // Reset tokens are stored hashed, so a database dump does not leak usable links.
  verification: { storeIdentifier: "hashed" },
  session: {
    expiresIn: 60 * 60 * 24 * 7,
    updateAge: 60 * 60 * 24,
  },
  rateLimit: {
    enabled: true,
    storage: "database",
    customRules: {
      // FastAPI checks every API cookie here without a client IP (one shared bucket), and the
      // answer is cached for up to 60 s there; throttling it would lock everyone out at once.
      "/get-session": false,
    },
  },
  // Self-service reset requests are off: links come from admins (no public email trigger).
  disabledPaths: ["/request-password-reset"],
  advanced: {
    useSecureCookies: baseURL?.startsWith("https://") ?? false,
    defaultCookieAttributes: { httpOnly: true, sameSite: "lax", path: "/" },
  },
  telemetry: { enabled: false },
  plugins: [admin({ defaultRole: "user", adminRoles: ["admin"] }), nextCookies()],
});

export type Session = typeof auth.$Infer.Session;
