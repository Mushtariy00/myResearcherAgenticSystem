"use client";

import { ArrowRightIcon, LoaderCircleIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useSignInForm } from "@/components/auth/use-sign-in-form";
import { Label } from "@/components/ui/label";
import { GlassCard } from "@/studio/components/effects/glass-card";
import { ShimmerButton } from "@/studio/components/effects/shimmer-button";
import { PasswordInput, StudioInput } from "./fields";
import { FormAlert } from "./form-alert";

/**
 * Studio sign-in: the same sign-in logic, validation and error messages as Classic
 * (useSignInForm), in a glass card. Goes to `next` (already checked) when it succeeds.
 */
export function StudioLoginForm({ next }: { next: string }) {
  const t = useTranslations("auth");
  const { pending, error, onSubmit } = useSignInForm(next);

  return (
    <GlassCard className="w-full max-w-[25rem] p-6 sm:p-8">
      <div className="mb-6 grid gap-1.5">
        <h1 className="studio-display text-2xl text-foreground">{t("login.title")}</h1>
        <p className="text-sm text-pretty text-muted-foreground">{t("login.description")}</p>
      </div>
      <form onSubmit={onSubmit} className="grid gap-5" aria-busy={pending}>
        <FormAlert message={error ? t(`errors.${error}`) : null} />
        <div className="grid gap-2">
          <Label htmlFor="studio-login-email">{t("fields.email")}</Label>
          <StudioInput
            id="studio-login-email"
            name="email"
            type="email"
            autoComplete="username"
            required
            autoFocus
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="studio-login-password">{t("fields.password")}</Label>
          <PasswordInput
            id="studio-login-password"
            name="password"
            autoComplete="current-password"
            required
          />
        </div>
        <ShimmerButton type="submit" size="lg" disabled={pending} className="mt-1 w-full">
          {pending ? (
            <LoaderCircleIcon aria-hidden className="animate-spin motion-reduce:animate-none" />
          ) : null}
          {pending ? t("login.submitting") : t("login.submit")}
          {!pending && <ArrowRightIcon aria-hidden />}
        </ShimmerButton>
        <p className="text-xs leading-relaxed text-muted-foreground">{t("login.help")}</p>
      </form>
    </GlassCard>
  );
}
