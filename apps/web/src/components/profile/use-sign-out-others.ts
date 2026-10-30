"use client";

import { useCallback, useState } from "react";
import { type AuthErrorCode, authClient, authErrorKey } from "@/lib/auth-client";

/**
 * "Sign out everywhere else", shared by both profile pages: Better Auth ends every session of
 * the user except this one (`revokeOtherSessions`). API calls from the other devices stop
 * within a minute, once FastAPI's session cache expires.
 */
export function useSignOutOthers() {
  const [pending, setPending] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<AuthErrorCode | null>(null);

  const signOutOthers = useCallback(async () => {
    setPending(true);
    setDone(false);
    setError(null);
    try {
      const result = await authClient.revokeOtherSessions();
      if (result.error) {
        setError(authErrorKey(result.error));
      } else {
        setDone(true);
      }
    } catch {
      setError("UNKNOWN");
    } finally {
      setPending(false);
    }
  }, []);

  return { pending, done, error, signOutOthers };
}
