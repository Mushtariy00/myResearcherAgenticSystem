"use client";

import { useTranslations } from "next-intl";
import { type FormEvent, useState } from "react";
import { type AuthErrorCode, authClient, authErrorKey } from "@/lib/auth-client";

export type ResetPasswordProblem = AuthErrorCode | "mismatch" | "tooShort";

/**
 * Choosing a password from an invite or reset link, shared by both interfaces. The form needs
 * `password` and `confirm` fields; the password policy (`minLength`) is checked before Better
 * Auth is called. `problemText` is the translated reason the password was not saved.
 */
export function useResetPasswordForm(token: string | null, minLength: number) {
  const t = useTranslations("auth");
  const [pending, setPending] = useState(false);
  const [problem, setProblem] = useState<ResetPasswordProblem | null>(null);
  const [done, setDone] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) {
      return;
    }
    const form = new FormData(event.currentTarget);
    const password = String(form.get("password") ?? "");
    const confirm = String(form.get("confirm") ?? "");
    if (password.length < minLength) {
      setProblem("tooShort");
      return;
    }
    if (password !== confirm) {
      setProblem("mismatch");
      return;
    }
    setPending(true);
    setProblem(null);
    try {
      const result = await authClient.resetPassword({ newPassword: password, token });
      if (result.error) {
        setProblem(authErrorKey(result.error));
        return;
      }
      setDone(true);
    } catch {
      setProblem("UNKNOWN");
    } finally {
      setPending(false);
    }
  }

  const problemText =
    problem === "mismatch"
      ? t("reset.mismatch")
      : problem === "tooShort"
        ? t("reset.tooShort", { min: minLength })
        : problem
          ? t(`errors.${problem}`)
          : null;

  return { pending, problem, problemText, done, onSubmit };
}
