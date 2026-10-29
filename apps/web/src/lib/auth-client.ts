import { adminClient } from "better-auth/client/plugins";
import { createAuthClient } from "better-auth/react";

export { type AuthErrorCode, authErrorKey } from "./auth-errors";

/** Browser client for Better Auth on the same origin (`/api/auth/*`). */
export const authClient = createAuthClient({
  plugins: [adminClient()],
});
