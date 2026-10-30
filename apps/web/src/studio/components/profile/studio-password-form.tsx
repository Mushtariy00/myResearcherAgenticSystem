"use client";

import { CircleCheckIcon, LoaderCircleIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useId } from "react";
import { useCurrentUser } from "@/components/app/current-user";
import {
  PASSWORD_FIELDS,
  type PasswordField,
  useChangePasswordForm,
} from "@/components/profile/use-change-password-form";
import { Label } from "@/components/ui/label";
import { MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH } from "@/lib/password-policy";
import { PasswordInput } from "@/studio/components/auth/fields";
import { FormAlert } from "@/studio/components/auth/form-alert";
import { ShimmerButton } from "@/studio/components/effects/shimmer-button";

/** Change your password in Studio: the same checks and Better Auth call as Classic. */
export function StudioPasswordForm() {
  const t = useTranslations();
  const user = useCurrentUser();
  const ids = useId();
  const { pending, problem, problemText, done, onSubmit } = useChangePasswordForm();
  const problemId = `${ids}-problem`;
  const hintId = `${ids}-hint`;

  function fieldProps(field: PasswordField) {
    const invalid = problem?.field === field;
    return {
      id: `${ids}-${field}`,
      name: PASSWORD_FIELDS[field],
      "aria-invalid": invalid || undefined,
      "aria-describedby":
        [invalid ? problemId : null, field === "new" ? hintId : null].filter(Boolean).join(" ") ||
        undefined,
    };
  }

  return (
    <form onSubmit={onSubmit} noValidate className="grid gap-4">
      <div id={problemId}>
        <FormAlert title={t("profile.password.failed")} message={problemText} />
      </div>
      {done && (
        <p
          role="status"
          data-tone="success"
          className="flex items-center gap-2 rounded-[10px] border border-(--tone)/30 bg-(--tone)/10 px-3 py-2 text-sm text-(--tone-fg)"
        >
          <CircleCheckIcon aria-hidden className="size-4 shrink-0" />
          {t("profile.password.doneSignedOut")}
        </p>
      )}
      <input
        type="text"
        name="username"
        autoComplete="username"
        value={user.email}
        readOnly
        hidden
      />
      <div className="grid gap-2">
        <Label htmlFor={`${ids}-current`}>{t("profile.password.current")}</Label>
        <PasswordInput
          {...fieldProps("current")}
          autoComplete="current-password"
          maxLength={MAX_PASSWORD_LENGTH}
          required
        />
      </div>
      <div className="grid gap-2">
        <Label htmlFor={`${ids}-new`}>{t("auth.fields.newPassword")}</Label>
        <PasswordInput
          {...fieldProps("new")}
          autoComplete="new-password"
          minLength={MIN_PASSWORD_LENGTH}
          maxLength={MAX_PASSWORD_LENGTH}
          required
        />
        <p id={hintId} className="text-xs text-muted-foreground">
          {t("auth.reset.hint", { min: MIN_PASSWORD_LENGTH })}
        </p>
      </div>
      <div className="grid gap-2">
        <Label htmlFor={`${ids}-confirm`}>{t("auth.fields.confirmPassword")}</Label>
        <PasswordInput
          {...fieldProps("confirm")}
          autoComplete="new-password"
          maxLength={MAX_PASSWORD_LENGTH}
          required
        />
      </div>
      <ShimmerButton type="submit" disabled={pending} className="w-full sm:w-fit">
        {pending && <LoaderCircleIcon aria-hidden className="motion-safe:animate-spin" />}
        {pending ? t("profile.password.submitting") : t("profile.password.submit")}
      </ShimmerButton>
    </form>
  );
}
