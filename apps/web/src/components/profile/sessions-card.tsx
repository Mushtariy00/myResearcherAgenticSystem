"use client";

import { AlertCircleIcon, CircleCheckIcon, LogOutIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useSignOutOthers } from "./use-sign-out-others";

/** Sign out on every other device, keeping this one (a lost laptop, a shared computer). */
export function SessionsCard() {
  const t = useTranslations();
  const { pending, done, error, signOutOthers } = useSignOutOthers();
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("profile.sessions.title")}</CardTitle>
        <CardDescription>{t("profile.sessions.description")}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        {error && (
          <Alert variant="destructive">
            <AlertCircleIcon aria-hidden />
            <AlertTitle>{t("profile.sessions.failed")}</AlertTitle>
            <AlertDescription>{t(`auth.errors.${error}`)}</AlertDescription>
          </Alert>
        )}
        {done && (
          <Alert role="status">
            <CircleCheckIcon aria-hidden />
            <AlertDescription>{t("profile.sessions.done")}</AlertDescription>
          </Alert>
        )}
        <Button variant="outline" className="w-fit" disabled={pending} onClick={signOutOthers}>
          <LogOutIcon aria-hidden />
          {pending ? t("profile.sessions.working") : t("profile.sessions.signOutOthers")}
        </Button>
      </CardContent>
    </Card>
  );
}
