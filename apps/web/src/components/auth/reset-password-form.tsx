"use client";

import { AlertCircleIcon, CheckCircle2Icon } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { MAX_PASSWORD_LENGTH } from "@/lib/password-policy";
import { useResetPasswordForm } from "./use-reset-password-form";

export function ResetPasswordForm({
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
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-lg">{t("reset.invalidTitle")}</CardTitle>
          <CardDescription>{t("reset.invalidDescription")}</CardDescription>
        </CardHeader>
        <CardContent>
          <Link
            href="/login"
            className={buttonVariants({ variant: "outline", className: "w-full" })}
          >
            {t("reset.backToLogin")}
          </Link>
        </CardContent>
      </Card>
    );
  }

  if (done) {
    return (
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <CheckCircle2Icon className="size-5 text-emerald-600" aria-hidden />
            {t("reset.doneTitle")}
          </CardTitle>
          <CardDescription>{t("reset.doneDescription")}</CardDescription>
        </CardHeader>
        <CardContent>
          <Link href="/login" className={buttonVariants({ className: "w-full" })}>
            {t("reset.goToLogin")}
          </Link>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="w-full max-w-sm">
      <CardHeader>
        <CardTitle className="text-lg">{t("reset.title")}</CardTitle>
        <CardDescription>{t("reset.description")}</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="grid gap-4">
          {problemText && (
            <Alert variant="destructive">
              <AlertCircleIcon aria-hidden />
              <AlertTitle>{t("reset.failed")}</AlertTitle>
              <AlertDescription>{problemText}</AlertDescription>
            </Alert>
          )}
          <div className="grid gap-2">
            <Label htmlFor="new-password">{t("fields.newPassword")}</Label>
            <Input
              id="new-password"
              name="password"
              type="password"
              autoComplete="new-password"
              minLength={minLength}
              maxLength={MAX_PASSWORD_LENGTH}
              required
              autoFocus
              aria-describedby="new-password-hint"
            />
            <p id="new-password-hint" className="text-xs text-muted-foreground">
              {t("reset.hint", { min: minLength })}
            </p>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="confirm-password">{t("fields.confirmPassword")}</Label>
            <Input
              id="confirm-password"
              name="confirm"
              type="password"
              autoComplete="new-password"
              minLength={minLength}
              maxLength={MAX_PASSWORD_LENGTH}
              required
            />
          </div>
          <Button type="submit" disabled={pending} className="w-full">
            {pending ? t("reset.submitting") : t("reset.submit")}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
