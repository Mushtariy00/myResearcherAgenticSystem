import { adminClient } from "better-auth/client/plugins";
import { createAuthClient } from "better-auth/react";

export { type AuthErrorCode, authErrorKey } from "./auth-errors";

/** Browser client for Better Auth on the same origin (`/api/auth/*`). */
export const authClient = createAuthClient({
  plugins: [adminClient()],
  // How often SessionRefresh checks the session (seconds), so a tab left open keeps it renewed.
  sessionOptions: { refetchInterval: 60 * 60 },
});
