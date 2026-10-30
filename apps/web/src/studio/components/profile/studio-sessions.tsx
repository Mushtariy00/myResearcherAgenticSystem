"use client";

import { CircleCheckIcon, LoaderCircleIcon, LogOutIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useSignOutOthers } from "@/components/profile/use-sign-out-others";
import { cn } from "@/lib/utils";
import { FormAlert } from "@/studio/components/auth/form-alert";
import { OUTLINE_BUTTON } from "@/studio/lib/ui";

/** Sign out on every other device, keeping this one: the same Better Auth call as Classic. */
export function StudioSessions() {
  const t = useTranslations();
  const { pending, done, error, signOutOthers } = useSignOutOthers();
  return (
    <div className="grid gap-4">
      <FormAlert
        title={t("profile.sessions.failed")}
        message={error ? t(`auth.errors.${error}`) : null}
      />
      {done && (
        <p
          role="status"
          data-tone="success"
          className="flex items-center gap-2 rounded-[10px] border border-(--tone)/30 bg-(--tone)/10 px-3 py-2 text-sm text-(--tone-fg)"
        >
          <CircleCheckIcon aria-hidden className="size-4 shrink-0" />
          {t("profile.sessions.done")}
        </p>
      )}
      <button
        type="button"
        disabled={pending}
        onClick={signOutOthers}
        className={cn(OUTLINE_BUTTON, "w-full disabled:opacity-60 sm:w-fit")}
      >
        {pending ? (
          <LoaderCircleIcon aria-hidden className="motion-safe:animate-spin" />
        ) : (
          <LogOutIcon aria-hidden />
        )}
        {pending ? t("profile.sessions.working") : t("profile.sessions.signOutOthers")}
      </button>
    </div>
  );
}
