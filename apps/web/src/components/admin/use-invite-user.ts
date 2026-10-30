"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { type FormEvent, useState, useTransition } from "react";
import { inviteUser } from "@/lib/admin-actions";
import { authErrorKey } from "@/lib/auth-client";
import type { IssuedLink } from "./link-dialog";
import { ADMIN_USERS_QUERY_KEY } from "./use-lab-users";

export const LAB_ROLES = ["user", "admin"] as const;
export type LabRole = (typeof LAB_ROLES)[number];

/**
 * The invite form of both interfaces: it needs `name` and `email` fields, and the lab role is
 * state (a select). On success the form resets and the set-password link goes to `onIssued`.
 */
export function useInviteUser(onIssued: (link: IssuedLink) => void) {
  const te = useTranslations("auth.errors");
  const queryClient = useQueryClient();
  const [role, setRole] = useState<LabRole>("user");
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const name = String(form.get("name") ?? "").trim();
    const email = String(form.get("email") ?? "").trim();
    setError(null);
    startTransition(async () => {
      const result = await inviteUser({ name, email, role });
      if (!result.ok) {
        setError(te(authErrorKey({ code: result.code })));
        return;
      }
      formElement.reset();
      setRole("user");
      await queryClient.invalidateQueries({ queryKey: ADMIN_USERS_QUERY_KEY });
      onIssued({
        email: email.toLowerCase(),
        url: result.url,
        emailed: result.emailed,
        kind: "invite",
      });
    });
  }

  return {
    role,
    setRole: (value: unknown) => setRole(value === "admin" ? "admin" : "user"),
    error,
    pending,
    onSubmit,
  };
}
