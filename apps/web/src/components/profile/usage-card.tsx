"use client";

import { WalletIcon } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useId } from "react";
import { useMonthName } from "@/components/admin/admin-labels";
import { QueryError } from "@/components/app/query-state";
import { DemoBadge } from "@/components/shared/demo-badge";
import { Metric } from "@/components/shared/metric";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { toAmount, USD } from "@/lib/format";
import { cn } from "@/lib/utils";
import { PROFILE_USAGE_DAYS, useMyUsage } from "./use-my-usage";

const BAR_TONES = {
  success: "bg-primary",
  warning: "bg-amber-500",
  danger: "bg-destructive",
} as const;

const WHOLE = { maximumFractionDigits: 0 } as const;
const COMPACT = { notation: "compact", maximumFractionDigits: 1 } as const;

/** My budget this month and my LLM calls over the last 30 days. */
export function UsageCard() {
  const t = useTranslations();
  const format = useFormatter();
  const monthName = useMonthName();
  const ids = useId();
  const { query, figures } = useMyUsage();

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          <WalletIcon className="size-4 text-muted-foreground" aria-hidden />
          {t("profile.usage.title")}
          <DemoBadge demo={figures?.demo} />
        </CardTitle>
        <CardDescription>
          {t("profile.usage.description", { days: PROFILE_USAGE_DAYS })}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {query.isPending ? (
          <div className="grid gap-3" aria-busy="true">
            <Skeleton className="h-6 w-40" />
            <Skeleton className="h-2 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        ) : query.isError || !figures ? (
          <QueryError error={query.error} onRetry={() => query.refetch()} />
        ) : (
          <div className="grid gap-6">
            <section aria-labelledby={`${ids}-month`} className="grid gap-2">
              <h3 id={`${ids}-month`} className="text-xs font-medium text-muted-foreground">
                {t("profile.usage.month", { month: monthName(figures.month) })}
              </h3>
              <p className="text-2xl font-semibold tabular-nums">
                {format.number(figures.spent, USD)}
                <span className="text-sm font-normal text-muted-foreground">
                  {" "}
                  / {format.number(figures.budget, USD)}
                </span>
              </p>
              {figures.budget > 0 && (
                <div
                  role="progressbar"
                  aria-label={t("budget.used")}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={Math.round(figures.percent)}
                  className="h-2 w-full overflow-hidden rounded-full bg-muted"
                >
                  <div
                    className={cn("h-full rounded-full", BAR_TONES[figures.tone])}
                    style={{ width: `${figures.percent}%` }}
                  />
                </div>
              )}
              <p className="text-sm text-muted-foreground">
                {figures.budget <= 0
                  ? t("budget.noBudget")
                  : t("budget.remaining", { amount: format.number(figures.remaining, USD) })}
              </p>
              <p className="text-xs text-muted-foreground">{t("budget.resets")}</p>
            </section>
            <section aria-labelledby={`${ids}-window`} className="grid gap-3">
              <h3 id={`${ids}-window`} className="text-xs font-medium text-muted-foreground">
                {t("profile.usage.lastDays", { days: PROFILE_USAGE_DAYS })}
              </h3>
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                <Metric label={t("profile.usage.paidSpend")} value={figures.paidUsd} format={USD} />
                <Metric
                  label={t("profile.usage.paidCalls")}
                  value={figures.paidCalls}
                  format={WHOLE}
                />
                <Metric
                  label={t("profile.usage.freeCalls")}
                  value={figures.freeCalls}
                  format={WHOLE}
                />
                <Metric label={t("profile.usage.tokens")} value={figures.tokens} format={COMPACT} />
              </div>
              {figures.topModels.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  {t("profile.usage.noCalls", { days: PROFILE_USAGE_DAYS })}
                </p>
              ) : (
                <div className="grid gap-1.5">
                  <h4 className="text-xs font-medium text-muted-foreground">
                    {t("profile.usage.topModels")}
                  </h4>
                  <ul className="grid gap-1">
                    {figures.topModels.map((model) => (
                      <li
                        key={`${model.tier}:${model.model}`}
                        className="flex items-baseline justify-between gap-3"
                      >
                        <span className="min-w-0 truncate font-mono text-xs">{model.model}</span>
                        <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                          {t("profile.usage.modelLine", {
                            calls: model.paid_calls + model.free_calls,
                            spend: format.number(toAmount(model.paid_usd), USD),
                          })}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </section>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
