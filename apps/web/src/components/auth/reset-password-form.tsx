"use client";

import { AlertCircleIcon, CheckCircle2Icon } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { type FormEvent, useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { type AuthErrorCode, authClient, authErrorKey } from "@/lib/auth-client";
import { MAX_PASSWORD_LENGTH } from "@/lib/password-policy";

type Problem = AuthErrorCode | "mismatch" | "tooShort";

export function ResetPasswordForm({
  token,
  minLength,
}: {
  token: string | null;
  minLength: number;
}) {
  const t = useTranslations("auth");
  const [pending, setPending] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [done, setDone] = useState(false);

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
