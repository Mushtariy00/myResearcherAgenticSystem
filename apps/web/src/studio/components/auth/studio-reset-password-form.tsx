"use client";

import { CircleCheckIcon, LinkIcon, LoaderCircleIcon } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";
import { useResetPasswordForm } from "@/components/auth/use-reset-password-form";
import { Label } from "@/components/ui/label";
import { MAX_PASSWORD_LENGTH } from "@/lib/password-policy";
import { cn } from "@/lib/utils";
import { GlassCard } from "@/studio/components/effects/glass-card";
import { ShimmerButton } from "@/studio/components/effects/shimmer-button";
import { STUDIO_LOGIN_PATH } from "@/studio/lib/login-redirect";
import { OUTLINE_BUTTON } from "@/studio/lib/ui";
import { PasswordInput } from "./fields";
import { FormAlert } from "./form-alert";

function Notice({
  tone,
  icon,
  title,
  description,
  children,
}: {
  tone: "success" | "warning";
  icon: ReactNode;
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <GlassCard className="w-full max-w-[25rem] p-6 sm:p-8">
      <span
        data-tone={tone}
        className="mb-5 flex size-11 items-center justify-center rounded-2xl border border-(--tone)/30 bg-(--tone)/12 text-(--tone-fg) [&_svg]:size-5"
      >
        {icon}
      </span>
      <h1 className="studio-display text-2xl text-foreground">{title}</h1>
      <p className="mt-2 text-sm text-pretty text-muted-foreground">{description}</p>
      <div className="mt-6">{children}</div>
    </GlassCard>
  );
}

/**
 * Studio "set your password" (invite and reset links): the same password policy, checks and
 * Better Auth call as Classic (useResetPasswordForm), linking back to the Studio sign-in page.
 */
export function StudioResetPasswordForm({
  token,
  minLength,
}: {
  token: string | null;
  minLength: number;
}) {
  const t = useTranslations("auth");
  const { pending, problemText, done, onSubmit } = useResetPasswordForm(token, minLength);

  if (!token) {
    return (
      <Notice
        tone="warning"
        icon={<LinkIcon aria-hidden />}
        title={t("reset.invalidTitle")}
        description={t("reset.invalidDescription")}
      >
        <Link href={STUDIO_LOGIN_PATH} className={cn(OUTLINE_BUTTON, "w-full")}>
          {t("reset.backToLogin")}
        </Link>
      </Notice>
    );
  }

  if (done) {
    return (
      <Notice
        tone="success"
        icon={<CircleCheckIcon aria-hidden />}
        title={t("reset.doneTitle")}
        description={t("reset.doneDescription")}
      >
        <ShimmerButton size="lg" className="w-full" render={<Link href={STUDIO_LOGIN_PATH} />}>
          {t("reset.goToLogin")}
        </ShimmerButton>
      </Notice>
    );
  }

  return (
    <GlassCard className="w-full max-w-[25rem] p-6 sm:p-8">
      <div className="mb-6 grid gap-1.5">
        <h1 className="studio-display text-2xl text-foreground">{t("reset.title")}</h1>
        <p className="text-sm text-pretty text-muted-foreground">{t("reset.description")}</p>
      </div>
      <form onSubmit={onSubmit} className="grid gap-5" aria-busy={pending}>
        <FormAlert title={t("reset.failed")} message={problemText} />
        <div className="grid gap-2">
          <Label htmlFor="studio-new-password">{t("fields.newPassword")}</Label>
          <PasswordInput
            id="studio-new-password"
            name="password"
            autoComplete="new-password"
            minLength={minLength}
            maxLength={MAX_PASSWORD_LENGTH}
            required
            autoFocus
            aria-describedby="studio-new-password-hint"
          />
          <p id="studio-new-password-hint" className="text-xs text-muted-foreground">
            {t("reset.hint", { min: minLength })}
          </p>
        </div>
        <div className="grid gap-2">
          <Label htmlFor="studio-confirm-password">{t("fields.confirmPassword")}</Label>
          <PasswordInput
            id="studio-confirm-password"
            name="confirm"
            autoComplete="new-password"
            minLength={minLength}
            maxLength={MAX_PASSWORD_LENGTH}
            required
          />
        </div>
        <ShimmerButton type="submit" size="lg" disabled={pending} className="mt-1 w-full">
          {pending && (
            <LoaderCircleIcon aria-hidden className="animate-spin motion-reduce:animate-none" />
          )}
          {pending ? t("reset.submitting") : t("reset.submit")}
        </ShimmerButton>
      </form>
    </GlassCard>
  );
}
