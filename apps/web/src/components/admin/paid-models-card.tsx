"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useId } from "react";
import { toast } from "sonner";
import {
  getPaidModelsOptions,
  getPaidModelsQueryKey,
  setPaidModelsMutation,
} from "@/client/@tanstack/react-query.gen";
import { QueryError } from "@/components/app/query-state";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { useErrorMessage } from "@/hooks/use-error-message";

/** Lab-wide kill switch: off means every LLM call uses free models, whatever the budgets. */
export function PaidModelsCard() {
  const t = useTranslations("admin.paidModels");
  const errorMessage = useErrorMessage();
  const queryClient = useQueryClient();
  const id = useId();
  const setting = useQuery(getPaidModelsOptions());
  const update = useMutation({
    ...setPaidModelsMutation(),
    onSuccess: (data) => {
      queryClient.setQueryData(getPaidModelsQueryKey(), data);
      toast.success(data.enabled ? t("enabledToast") : t("disabledToast"));
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

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
              disabled={update.isPending}
              onCheckedChange={(enabled) => update.mutate({ body: { enabled } })}
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
