"use client";

import { CoinsIcon } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useId } from "react";
import type { BudgetStatusOut, UsageDayOut, UsageOut } from "@/client";
import { QueryError } from "@/components/app/query-state";
import { DemoBadge } from "@/components/shared/demo-badge";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { USAGE_DAYS, useUsage } from "@/hooks/use-usage";
import { percentUsed, toAmount, USD } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Gauge } from "./gauge";

/** Usage days are UTC dates ("2026-10-30"); show them as such, whatever the local zone. */
const DAY_FORMAT = { month: "short", day: "numeric", timeZone: "UTC" } as const;

function dayDate(day: string): Date {
  return new Date(`${day}T00:00:00Z`);
}

/** Paid and free calls side by side: a two-part bar with a legend that carries the numbers. */
function CallsByTier({ paid, free }: { paid: number; free: number }) {
  const t = useTranslations("dashboard.spend");
  return (
    <div className="grid gap-2">
      <h3 className="text-xs font-medium text-muted-foreground">{t("callsByTier")}</h3>
      <div aria-hidden className="flex h-2 gap-0.5 overflow-hidden rounded-full bg-muted">
        {paid > 0 && (
          <span className="rounded-full bg-(--chart-series-1)" style={{ flexGrow: paid }} />
        )}
        {free > 0 && (
          <span className="rounded-full bg-(--chart-series-2)" style={{ flexGrow: free }} />
        )}
      </div>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
        <li className="flex items-center gap-1.5">
          <span aria-hidden className="size-2 rounded-full bg-(--chart-series-1)" />
          {t("paidCalls", { count: paid })}
        </li>
        <li className="flex items-center gap-1.5">
          <span aria-hidden className="size-2 rounded-full bg-(--chart-series-2)" />
          {t("freeCalls", { count: free })}
        </li>
      </ul>
    </div>
  );
}

/** Paid spend per day as thin columns; screen readers get a summary and the figures table. */
function DailySpend({ days }: { days: readonly UsageDayOut[] }) {
  const t = useTranslations("dashboard.spend");
  const format = useFormatter();
  const amounts = days.map((day) => ({ day: day.day, amount: toAmount(day.paid_usd) }));
  const top = amounts.reduce<{ day: string; amount: number } | null>(
    (best, entry) => (best === null || entry.amount > best.amount ? entry : best),
    null,
  );
  if (top === null || top.amount <= 0) {
    return <p className="text-sm text-muted-foreground">{t("noPaidSpend")}</p>;
  }
  const total = amounts.reduce((sum, entry) => sum + entry.amount, 0);
  const first = amounts[0];
  const last = amounts.at(-1);
  const label = (day: string) => format.dateTime(dayDate(day), DAY_FORMAT);

  return (
    <figure className="grid gap-1.5">
      <figcaption className="text-xs font-medium text-muted-foreground">
        {t("chartTitle")}
      </figcaption>
      <p className="sr-only">
        {t("chartSummary", {
          days: amounts.length,
          total: format.number(total, USD),
          max: format.number(top.amount, USD),
          date: label(top.day),
        })}
      </p>
      <div aria-hidden className="flex h-16 items-end gap-0.5 border-b border-border">
        {amounts.map((entry) => (
          <span
            key={entry.day}
            title={t("dayValue", {
              date: label(entry.day),
              amount: format.number(entry.amount, USD),
            })}
            className={cn(
              "min-w-0 flex-1 rounded-t-[3px]",
              entry.amount > 0 ? "bg-(--chart-series-1) hover:opacity-80" : "bg-transparent",
            )}
            style={{
              height: entry.amount > 0 ? `${Math.max(6, (entry.amount / top.amount) * 100)}%` : 0,
            }}
          />
        ))}
      </div>
      {first && last && (
        <div aria-hidden className="flex justify-between text-[11px] text-muted-foreground">
          <span>{label(first.day)}</span>
          <span>{label(last.day)}</span>
        </div>
      )}
      <details className="text-xs">
        <summary className="w-fit cursor-pointer rounded-sm text-muted-foreground outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50">
          {t("showTable")}
        </summary>
        <div className="mt-2 max-h-48 overflow-auto rounded-lg border">
          <table className="w-full">
            <caption className="sr-only">{t("chartTitle")}</caption>
            <thead className="sticky top-0 bg-muted">
              <tr>
                <th scope="col" className="px-2 py-1 text-left font-medium">
                  {t("day")}
                </th>
                <th scope="col" className="px-2 py-1 text-right font-medium">
                  {t("paid")}
                </th>
              </tr>
            </thead>
            <tbody>
              {amounts.map((entry) => (
                <tr key={entry.day} className="border-t">
                  <th scope="row" className="px-2 py-1 text-left font-normal">
                    {label(entry.day)}
                  </th>
                  <td className="px-2 py-1 text-right tabular-nums">
                    {format.number(entry.amount, USD)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}

function BudgetStatus({ budget }: { budget: BudgetStatusOut }) {
  const t = useTranslations("dashboard.spend");
  const tBudget = useTranslations("budget");
  const format = useFormatter();
  const monthly = toAmount(budget.monthly_usd);
  const spent = toAmount(budget.spent_usd);
  const used = percentUsed(spent, monthly);
  return (
    <div className="grid gap-2 border-t pt-4">
      {monthly > 0 ? (
        <>
          <Gauge
            label={t("budgetMonth")}
            value={used}
            valueText={t("budgetValue", {
              spent: format.number(spent, USD),
              budget: format.number(monthly, USD),
            })}
            tone={used >= 100 ? "danger" : used >= 80 ? "warning" : "default"}
          />
          <p className="text-sm">
            {tBudget("remaining", { amount: format.number(toAmount(budget.remaining_usd), USD) })}
          </p>
        </>
      ) : (
        <p className="text-sm">{tBudget("noBudget")}</p>
      )}
      <p className="text-xs text-muted-foreground">{tBudget("resets")}</p>
    </div>
  );
}

function SpendDetails({ data }: { data: UsageOut }) {
  const t = useTranslations("dashboard.spend");
  const format = useFormatter();
  const { totals } = data;
  const calls = totals.paid_calls + totals.free_calls;
  return (
    <div className="grid gap-5">
      <div>
        <p className="text-2xl font-semibold tabular-nums">
          {format.number(toAmount(totals.paid_usd), USD)}
        </p>
        <p className="text-xs text-muted-foreground">{t("paidSpend", { days: data.days })}</p>
      </div>
      {calls === 0 ? (
        <p className="text-sm text-muted-foreground">{t("noCalls", { days: data.days })}</p>
      ) : (
        <>
          <CallsByTier paid={totals.paid_calls} free={totals.free_calls} />
          <DailySpend days={data.by_day} />
        </>
      )}
      <BudgetStatus budget={data.budget} />
    </div>
  );
}

/** The user's LLM spend over the last 30 days (paid against free) and what is left this month. */
export function SpendWidget() {
  const t = useTranslations("dashboard.spend");
  const headingId = useId();
  const usage = useUsage("me", USAGE_DAYS.default);

  return (
    <section aria-labelledby={headingId}>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <CoinsIcon aria-hidden className="size-4 text-muted-foreground" />
            <h2 id={headingId}>{t("title")}</h2>
          </CardTitle>
          <CardDescription>{t("description", { days: USAGE_DAYS.default })}</CardDescription>
          {usage.data?.demo && (
            <CardAction>
              <DemoBadge demo />
            </CardAction>
          )}
        </CardHeader>
        <CardContent>
          {usage.isPending ? (
            <div className="grid gap-3" aria-busy="true">
              <span className="sr-only">{t("loading")}</span>
              <Skeleton className="h-8 w-32" />
              <Skeleton className="h-2 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          ) : usage.isError ? (
            <QueryError error={usage.error} onRetry={() => usage.refetch()} />
          ) : (
            <SpendDetails data={usage.data} />
          )}
        </CardContent>
      </Card>
    </section>
  );
}
