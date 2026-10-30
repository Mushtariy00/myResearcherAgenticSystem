"use client";

import { useTranslations } from "next-intl";
import { useId } from "react";
import { useCurrentUser } from "@/components/app/current-user";
import { QueryError } from "@/components/app/query-state";
import { Switch } from "@/components/ui/switch";
import { useErrorMessage } from "@/hooks/use-error-message";
import { useMySettings } from "@/hooks/use-my-settings";
import { FormAlert } from "@/studio/components/auth/form-alert";
import { STUDIO_HINT, STUDIO_LABEL } from "@/studio/components/dashboard/studio-fields";
import { ShimmerSkeleton } from "@/studio/components/effects/shimmer-skeleton";

/** Notification emails on or off in Studio: the same setting and save as Classic. */
export function StudioEmailNotifications() {
  const t = useTranslations("profile.emails");
  const user = useCurrentUser();
  const errorMessage = useErrorMessage();
  const ids = useId();
  const { query, setEmailNotifications, saving, saveError } = useMySettings();

  if (query.isPending) {
    return <ShimmerSkeleton className="h-16 w-full rounded-[10px]" />;
  }
  if (query.isError) {
    return <QueryError error={query.error} onRetry={() => query.refetch()} />;
  }
  return (
    <div className="grid gap-3">
      <FormAlert title={t("failed")} message={saveError ? errorMessage(saveError) : null} />
      {/* biome-ignore lint/a11y/noLabelWithoutControl: the Base UI switch inside is the control */}
      <label className="flex cursor-pointer items-start justify-between gap-4 rounded-[10px] border border-(--studio-glass-border) bg-(--studio-glass) px-3 py-2.5 shadow-[inset_0_1px_0_0_var(--studio-glass-highlight)] transition-colors hover:bg-(--studio-hover) has-data-disabled:cursor-default">
        <span className="grid min-w-0 gap-0.5">
          <span id={`${ids}-label`} className={STUDIO_LABEL}>
            {t("label")}
          </span>
          <span id={`${ids}-hint`} className={STUDIO_HINT}>
            {t("hint", { email: user.email })}
          </span>
        </span>
        <Switch
          aria-labelledby={`${ids}-label`}
          aria-describedby={`${ids}-hint`}
          checked={query.data.email_notifications}
          onCheckedChange={setEmailNotifications}
          disabled={saving}
          className="mt-0.5"
        />
      </label>
    </div>
  );
}
