"use client";

import { useTranslations } from "next-intl";
import { type FormEvent, useState } from "react";
import { type AuthErrorCode, authClient, authErrorKey } from "@/lib/auth-client";
import { MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH } from "@/lib/password-policy";

/** The fields of the change-password forms (their `name`s), in both interfaces. */
export const PASSWORD_FIELDS = {
  current: "currentPassword",
  new: "newPassword",
  confirm: "confirmPassword",
} as const;

export type PasswordField = keyof typeof PASSWORD_FIELDS;

/** Checked here before Better Auth is called; INVALID_PASSWORD comes from Better Auth. */
export type PasswordProblemCode =
  | "currentRequired"
  | "tooShort"
  | "tooLong"
  | "sameAsCurrent"
  | "mismatch"
  | "INVALID_PASSWORD";

export type PasswordProblem = {
  code: PasswordProblemCode | AuthErrorCode;
  /** The field to fix, or null when the problem is not about one field. */
  field: PasswordField | null;
};

/** The password policy (src/lib/password-policy.ts) and the form's own rules, in that order. */
export function validatePasswordChange({
  current,
  next,
  confirm,
}: {
  current: string;
  next: string;
  confirm: string;
}): PasswordProblem | null {
  if (current.length === 0) {
    return { code: "currentRequired", field: "current" };
  }
  if (next.length < MIN_PASSWORD_LENGTH) {
    return { code: "tooShort", field: "new" };
  }
  if (next.length > MAX_PASSWORD_LENGTH) {
    return { code: "tooLong", field: "new" };
  }
  if (next === current) {
    return { code: "sameAsCurrent", field: "new" };
  }
  if (confirm !== next) {
    return { code: "mismatch", field: "confirm" };
  }
  return null;
}

/** What a Better Auth refusal of changePassword means for the form. */
function refusal(error: {
  code?: string | undefined;
  status?: number | undefined;
}): PasswordProblem {
  if (error.status !== 429 && error.code === "INVALID_PASSWORD") {
    return { code: "INVALID_PASSWORD", field: "current" };
  }
  const key = authErrorKey(error);
  if (key === "PASSWORD_TOO_SHORT") {
    return { code: "tooShort", field: "new" };
  }
  if (key === "PASSWORD_TOO_LONG") {
    return { code: "tooLong", field: "new" };
  }
  return { code: key, field: null };
}

const FORM_CODES = new Set<string>([
  "currentRequired",
  "tooShort",
  "tooLong",
  "sameAsCurrent",
  "mismatch",
  "INVALID_PASSWORD",
]);

function focusField(form: HTMLFormElement, field: PasswordField | null) {
  if (!field) {
    return;
  }
  const element = form.elements.namedItem(PASSWORD_FIELDS[field]);
  if (element instanceof HTMLInputElement) {
    element.focus();
  }
}

/**
 * Changing your password (Better Auth `changePassword`), shared by both interfaces: the
 * current password, the new one twice, and whether to sign out the other devices (a
 * `signOutOthers` checkbox). Problems name the field to fix, which gets the focus.
 */
export function useChangePasswordForm() {
  const t = useTranslations();
  const [pending, setPending] = useState(false);
  const [problem, setProblem] = useState<PasswordProblem | null>(null);
  const [done, setDone] = useState<{ signedOutOthers: boolean } | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const current = String(data.get(PASSWORD_FIELDS.current) ?? "");
    const next = String(data.get(PASSWORD_FIELDS.new) ?? "");
    const confirm = String(data.get(PASSWORD_FIELDS.confirm) ?? "");
    const signOutOthers = data.get("signOutOthers") === "on";
    setDone(null);
    const invalid = validatePasswordChange({ current, next, confirm });
    if (invalid) {
      setProblem(invalid);
      focusField(form, invalid.field);
      return;
    }
    setProblem(null);
    setPending(true);
    try {
      const result = await authClient.changePassword({
        currentPassword: current,
        newPassword: next,
        revokeOtherSessions: signOutOthers,
      });
      if (result.error) {
        const refused = refusal(result.error);
        setProblem(refused);
        focusField(form, refused.field);
        return;
      }
      form.reset();
      setDone({ signedOutOthers: signOutOthers });
    } catch {
      setProblem({ code: "UNKNOWN", field: null });
    } finally {
      setPending(false);
    }
  }

  let problemText: string | null = null;
  if (problem && FORM_CODES.has(problem.code)) {
    problemText = t(`profile.password.problems.${problem.code as PasswordProblemCode}`, {
      min: MIN_PASSWORD_LENGTH,
      max: MAX_PASSWORD_LENGTH,
    });
  } else if (problem) {
    problemText = t(`auth.errors.${problem.code as AuthErrorCode}`);
  }

  return { pending, problem, problemText, done, onSubmit };
}
