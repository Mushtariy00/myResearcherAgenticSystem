"use client";

import { AlertCircleIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useSignInForm } from "./use-sign-in-form";

export function LoginForm({ next }: { next: string }) {
  const t = useTranslations("auth");
  const { pending, error, onSubmit } = useSignInForm(next);

  return (
    <Card className="w-full max-w-sm">
      <CardHeader>
        <CardTitle className="text-lg">{t("login.title")}</CardTitle>
        <CardDescription>{t("login.description")}</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="grid gap-4">
          {error && (
            <Alert variant="destructive">
              <AlertCircleIcon aria-hidden />
              <AlertDescription>{t(`errors.${error}`)}</AlertDescription>
            </Alert>
          )}
          <div className="grid gap-2">
            <Label htmlFor="login-email">{t("fields.email")}</Label>
            <Input
              id="login-email"
              name="email"
              type="email"
              autoComplete="username"
              required
              autoFocus
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="login-password">{t("fields.password")}</Label>
            <Input
              id="login-password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
            />
          </div>
          <Button type="submit" disabled={pending} className="w-full">
            {pending ? t("login.submitting") : t("login.submit")}
          </Button>
          <p className="text-xs text-muted-foreground">{t("login.help")}</p>
        </form>
      </CardContent>
    </Card>
  );
}
