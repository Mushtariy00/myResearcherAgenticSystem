"use client";

import { useFormatter, useTranslations } from "next-intl";
import { useId } from "react";
import { useMonthName } from "@/components/admin/admin-labels";
import { QueryError } from "@/components/app/query-state";
import { PROFILE_USAGE_DAYS, useMyUsage } from "@/components/profile/use-my-usage";
import { DemoBadge } from "@/components/shared/demo-badge";
import { toAmount, USD } from "@/lib/format";
import { NumberTicker } from "@/studio/components/effects/number-ticker";
import { LoadingStatus, ShimmerSkeleton } from "@/studio/components/effects/shimmer-skeleton";

const WHOLE = { maximumFractionDigits: 0 } as const;
const COMPACT = { notation: "compact", maximumFractionDigits: 1 } as const;

function Stat({
  label,
  value,
  format,
}: {
  label: string;
  value: number;
  format?: Intl.NumberFormatOptions;
}) {
  return (
    <div className="grid min-w-0 gap-1 rounded-xl border border-(--studio-glass-border) bg-(--studio-glass) px-3 py-2.5">
      <dt className="truncate text-xs text-muted-foreground">{label}</dt>
      <dd className="font-mono text-lg font-semibold text-foreground">
        <NumberTicker value={value} format={format} />
      </dd>
    </div>
  );
}

/** My budget this month (a spring-counted spend and a bar) and my calls over 30 days. */
export function StudioUsage() {
  const t = useTranslations();
  const format = useFormatter();
  const monthName = useMonthName();
  const ids = useId();
  const { query, figures } = useMyUsage();

  if (query.isPending) {
    return (
      <div className="grid gap-3" aria-busy="true">
        <LoadingStatus label={t("common.loading")} />
        <ShimmerSkeleton className="h-9 w-48" />
        <ShimmerSkeleton className="h-2 w-full" />
        <ShimmerSkeleton className="h-16 w-full rounded-xl" />
      </div>
    );
  }
  if (query.isError || !figures) {
    return <QueryError error={query.error} onRetry={() => query.refetch()} />;
  }

  return (
    <div className="grid gap-6">
      {figures.demo && <DemoBadge demo className="-mt-2" />}
      <section aria-labelledby={`${ids}-month`} className="grid gap-2.5">
        <h3 id={`${ids}-month`} className="text-xs font-medium text-muted-foreground">
          {t("profile.usage.month", { month: monthName(figures.month) })}
        </h3>
        <p className="flex flex-wrap items-baseline gap-x-2 font-mono text-3xl font-semibold tracking-tight text-foreground">
          <NumberTicker value={figures.spent} format={USD} />
          <span className="text-sm font-normal text-muted-foreground">
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
            className="h-1.5 w-full overflow-hidden rounded-full bg-(--studio-glass-strong)"
          >
            <div
              data-tone={figures.tone}
              className="h-full origin-left rounded-full bg-(--tone) transition-transform duration-700 ease-out motion-reduce:transition-none"
              style={{ transform: `scaleX(${figures.percent / 100})` }}
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
        <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Stat label={t("profile.usage.paidSpend")} value={figures.paidUsd} format={USD} />
          <Stat label={t("profile.usage.paidCalls")} value={figures.paidCalls} format={WHOLE} />
          <Stat label={t("profile.usage.freeCalls")} value={figures.freeCalls} format={WHOLE} />
          <Stat label={t("profile.usage.tokens")} value={figures.tokens} format={COMPACT} />
        </dl>
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
                  <span className="min-w-0 truncate font-mono text-xs text-foreground">
                    {model.model}
                  </span>
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
  );
}
