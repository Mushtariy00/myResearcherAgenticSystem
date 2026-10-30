"use client";

import { useTranslations } from "next-intl";
import { useCallback, useState, useTransition } from "react";
import { sendPasswordLink } from "@/lib/admin-actions";
import { authErrorKey } from "@/lib/auth-client";
import type { IssuedLink } from "./link-dialog";
import type { LabUser } from "./use-lab-users";

/**
 * A fresh set-password link for an existing account (lost invite or forgotten password), for
 * the users tables of both interfaces. The link goes to `onIssued` (shown by LinkDialog).
 */
export function usePasswordLink(onIssued: (link: IssuedLink) => void) {
  const te = useTranslations("auth.errors");
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  const issue = useCallback(
    (user: Pick<LabUser, "email">) => {
      setError(null);
      startTransition(async () => {
        const result = await sendPasswordLink({ email: user.email });
        if (!result.ok) {
          setError(te(authErrorKey({ code: result.code })));
          return;
        }
        onIssued({ email: user.email, url: result.url, emailed: result.emailed, kind: "reset" });
      });
    },
    [onIssued, te],
  );

  return { issue, pending, error };
}
