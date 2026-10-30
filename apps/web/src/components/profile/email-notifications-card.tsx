"use client";

import { AlertCircleIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useId } from "react";
import { useCurrentUser } from "@/components/app/current-user";
import { QueryError } from "@/components/app/query-state";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { useErrorMessage } from "@/hooks/use-error-message";
import { useMySettings } from "@/hooks/use-my-settings";

/** Notification emails on or off: they go to the account's address, in the UI language. */
export function EmailNotificationsCard() {
  const t = useTranslations("profile.emails");
  const user = useCurrentUser();
  const errorMessage = useErrorMessage();
  const id = useId();
  const { query, setEmailNotifications, saving, saveError } = useMySettings();

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("title")}</CardTitle>
        <CardDescription>{t("description")}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        {saveError && (
          <Alert variant="destructive">
            <AlertCircleIcon aria-hidden />
            <AlertTitle>{t("failed")}</AlertTitle>
            <AlertDescription>{errorMessage(saveError)}</AlertDescription>
          </Alert>
        )}
        {query.isPending ? (
          <Skeleton className="h-14 w-full" />
        ) : query.isError ? (
          <QueryError error={query.error} onRetry={() => query.refetch()} />
        ) : (
          <Label className="flex cursor-pointer items-start justify-between gap-4 rounded-lg border p-3 font-normal leading-normal has-data-disabled:cursor-default">
            <span className="grid gap-1">
              <span id={`${id}-label`} className="font-medium">
                {t("label")}
              </span>
              <span id={`${id}-hint`} className="text-xs leading-snug text-muted-foreground">
                {t("hint", { email: user.email })}
              </span>
            </span>
            <Switch
              aria-labelledby={`${id}-label`}
              aria-describedby={`${id}-hint`}
              checked={query.data.email_notifications}
              onCheckedChange={setEmailNotifications}
              disabled={saving}
            />
          </Label>
        )}
      </CardContent>
    </Card>
  );
}
