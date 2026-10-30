"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";
import { type AuthErrorCode, authClient, authErrorKey } from "@/lib/auth-client";
import { resetSignInRedirect } from "@/lib/auth-redirect";

/**
 * Email + password sign-in, shared by the login forms of both interfaces (Classic and Studio).
 * The form needs `email` and `password` fields. On success the user goes to `next`, which the
 * page has already checked with safeNextPath.
 */
export function useSignInForm(next: string) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<AuthErrorCode | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setPending(true);
    setError(null);
    try {
      const result = await authClient.signIn.email({
        email: String(form.get("email") ?? "").trim(),
        password: String(form.get("password") ?? ""),
      });
      if (result.error) {
        setError(authErrorKey(result.error));
        setPending(false);
        return;
      }
    } catch {
      setError("UNKNOWN");
      setPending(false);
      return;
    }
    // The tab may still hold what the previous user saw (a session that ended without a sign
    // out); nothing of it may reach the next one.
    queryClient.clear();
    resetSignInRedirect();
    router.replace(next);
    router.refresh();
  }

  return { pending, error, onSubmit };
}
