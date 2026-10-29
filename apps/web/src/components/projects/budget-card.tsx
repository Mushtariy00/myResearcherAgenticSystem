"use client";

import { useQuery } from "@tanstack/react-query";
import { WalletIcon } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { getMeOptions } from "@/client/@tanstack/react-query.gen";
import { QueryError } from "@/components/app/query-state";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { percentUsed, toAmount, USD } from "@/lib/format";
import { cn } from "@/lib/utils";

export function BudgetCard() {
  const t = useTranslations("budget");
  const format = useFormatter();
  const me = useQuery(getMeOptions());

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <WalletIcon className="size-4 text-muted-foreground" aria-hidden />
          {t("title")}
        </CardTitle>
        <CardDescription>{t("description")}</CardDescription>
      </CardHeader>
      <CardContent>
        {me.isPending ? (
          <div className="grid gap-2">
            <Skeleton className="h-6 w-32" />
            <Skeleton className="h-2 w-full" />
          </div>
        ) : me.isError ? (
          <QueryError error={me.error} onRetry={() => me.refetch()} />
        ) : (
          (() => {
            const budget = toAmount(me.data.budget_usd);
            const spent = toAmount(me.data.spent_usd);
            const used = percentUsed(spent, budget);
            return (
              <div className="grid gap-3">
                <p className="text-2xl font-semibold tabular-nums">
                  {format.number(spent, USD)}
                  <span className="text-sm font-normal text-muted-foreground">
                    {" "}
                    / {format.number(budget, USD)}
                  </span>
                </p>
                <div
                  role="progressbar"
                  aria-label={t("used")}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={Math.round(used)}
                  className="h-2 w-full overflow-hidden rounded-full bg-muted"
                >
                  <div
                    className={cn(
                      "h-full rounded-full bg-primary transition-[width]",
                      used >= 100 ? "bg-destructive" : used >= 80 ? "bg-amber-500" : "bg-primary",
                    )}
                    style={{ width: `${used}%` }}
                  />
                </div>
                <p className="text-sm text-muted-foreground">
                  {budget <= 0
                    ? t("noBudget")
                    : t("remaining", { amount: format.number(Math.max(0, budget - spent), USD) })}
                </p>
                <p className="text-xs text-muted-foreground">{t("resets")}</p>
              </div>
            );
          })()
        )}
      </CardContent>
    </Card>
  );
}
