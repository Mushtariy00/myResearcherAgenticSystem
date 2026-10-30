"use client";

import { authClient } from "@/lib/auth-client";

/**
 * Keeps the session sliding while the app is open (auth.ts `deferSessionRefresh`). Better Auth's
 * session store reads /api/auth/get-session on mount, on focus and every hour; when the session
 * is due for renewal it POSTs there, and that response, from the Next.js route, carries the
 * renewed cookie. Renders nothing.
 */
export function SessionRefresh(): null {
  authClient.useSession();
  return null;
}
