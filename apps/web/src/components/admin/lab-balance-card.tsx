"use client";

import { TriangleAlertIcon } from "lucide-react";
import { useFormatter, useNow, useTranslations } from "next-intl";
import { useId } from "react";
import { QueryError } from "@/components/app/query-state";
import { DemoBadge } from "@/components/shared/demo-badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useLabBalance } from "@/hooks/use-lab-balance";
import { USD } from "@/lib/format";
import { cn } from "@/lib/utils";
import { balanceGauge, freeQuota } from "./admin-format";
import { useMonthName } from "./admin-labels";
import { BalanceGauge } from "./balance-gauge";

const BAR_TONES = {
  success: "bg-primary",
  warning: "bg-amber-500",
  danger: "bg-destructive",
} as const;

/** The lab's prepaid balance as a gauge, this month's paid spend, and today's free calls. */
export function LabBalanceCard() {
  const t = useTranslations("admin.balance");
  const format = useFormatter();
  const now = useNow({ updateInterval: 60_000 });
  const monthName = useMonthName();
  const balance = useLabBalance();
  const quotaTitle = useId();

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          {t("title")}
          <DemoBadge demo={balance.data?.demo} />
        </CardTitle>
        <CardDescription>{t("description")}</CardDescription>
      </CardHeader>
      <CardContent>
        {balance.isPending ? (
          <div className="grid gap-4 md:grid-cols-2" aria-busy="true">
            <Skeleton className="mx-auto h-36 w-full max-w-64" />
            <div className="grid content-start gap-3">
              <Skeleton className="h-5 w-40" />
              <Skeleton className="h-5 w-32" />
              <Skeleton className="h-2 w-full" />
            </div>
          </div>
        ) : balance.isError ? (
          <QueryError error={balance.error} onRetry={() => balance.refetch()} />
        ) : (
          (() => {
            const gauge = balanceGauge(balance.data);
            const quota = freeQuota(balance.data);
            return (
              <div className="grid gap-6">
                {gauge.tone === "danger" && (
                  <Alert variant="destructive">
                    <TriangleAlertIcon aria-hidden />
                    <AlertTitle>{t("belowFloorTitle")}</AlertTitle>
                    <AlertDescription>
                      {t("belowFloor", { floor: format.number(gauge.floor, USD) })}
                    </AlertDescription>
                  </Alert>
                )}
                <div className="grid items-center gap-6 md:grid-cols-2">
                  <BalanceGauge value={gauge} />
                  <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
                    <div className="grid gap-0.5">
                      <dt className="text-xs text-muted-foreground">
                        {t("spent", { month: monthName(balance.data.month) })}
                      </dt>
                      <dd className="font-medium tabular-nums">
                        {format.number(gauge.spent, USD)}
                      </dd>
                    </div>
                    <div className="grid gap-0.5">
                      <dt className="text-xs text-muted-foreground">{t("floor")}</dt>
                      <dd className="font-medium tabular-nums">
                        {format.number(gauge.floor, USD)}
                      </dd>
                    </div>
                    <div className="grid gap-0.5">
                      <dt className="text-xs text-muted-foreground">{t("autoTopUp")}</dt>
                      <dd className="font-medium">
                        {balance.data.auto_top_up ? t("on") : t("off")}
                      </dd>
                    </div>
                    <div className="grid gap-0.5">
                      <dt className="text-xs text-muted-foreground">{t("checkedLabel")}</dt>
                      <dd className="font-medium">
                        <time dateTime={balance.data.checked_at}>
                          {format.relativeTime(new Date(balance.data.checked_at), now)}
                        </time>
                      </dd>
                    </div>
                  </dl>
                </div>
                <section aria-labelledby={quotaTitle} className="grid gap-2">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <h3 id={quotaTitle} className="text-sm font-medium">
                      {t("freeTitle")}
                    </h3>
                    <p className="text-sm text-muted-foreground tabular-nums">
                      {quota.limit === null
                        ? t("freeUnlimited", { used: format.number(quota.used) })
                        : t("freeUsed", {
                            used: format.number(quota.used),
                            limit: format.number(quota.limit),
                          })}
                    </p>
                  </div>
                  {quota.limit !== null && (
                    <div
                      role="progressbar"
                      aria-labelledby={quotaTitle}
                      aria-valuemin={0}
                      aria-valuemax={quota.limit}
                      aria-valuenow={Math.min(quota.used, quota.limit)}
                      className="h-2 w-full overflow-hidden rounded-full bg-muted"
                    >
                      <div
                        className={cn("h-full rounded-full", BAR_TONES[quota.tone])}
                        style={{ width: `${quota.percent}%` }}
                      />
                    </div>
                  )}
                  <p className="text-xs text-muted-foreground">{t("freeHint")}</p>
                </section>
              </div>
            );
          })()
        )}
      </CardContent>
    </Card>
  );
}
