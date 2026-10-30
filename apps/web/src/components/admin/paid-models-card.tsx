"use client";

import { useTranslations } from "next-intl";
import { useId } from "react";
import { QueryError } from "@/components/app/query-state";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { usePaidModels } from "./use-paid-models";

/** Lab-wide kill switch: off means every LLM call uses free models, whatever the budgets. */
export function PaidModelsCard() {
  const t = useTranslations("admin.paidModels");
  const id = useId();
  const { setting, pending, setEnabled } = usePaidModels();

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("title")}</CardTitle>
        <CardDescription>{t("description")}</CardDescription>
      </CardHeader>
      <CardContent>
        {setting.isPending ? (
          <Skeleton className="h-6 w-40" />
        ) : setting.isError ? (
          <QueryError error={setting.error} onRetry={() => setting.refetch()} />
        ) : (
          <div className="flex items-center gap-3">
            <Switch
              id={id}
              checked={setting.data.enabled}
              disabled={pending}
              onCheckedChange={setEnabled}
            />
            <Label htmlFor={id} className="font-normal">
              {setting.data.enabled ? t("on") : t("off")}
            </Label>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
