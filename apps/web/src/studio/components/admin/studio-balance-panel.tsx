"use client";

import { TriangleAlertIcon } from "lucide-react";
import { motion } from "motion/react";
import { useFormatter, useNow, useTranslations } from "next-intl";
import { useId } from "react";
import { type BalanceGaugeValue, balanceGauge, freeQuota } from "@/components/admin/admin-format";
import { useMonthName } from "@/components/admin/admin-labels";
import { GAUGE_ARC, gaugePoint } from "@/components/admin/balance-gauge";
import { QueryError } from "@/components/app/query-state";
import { DemoBadge } from "@/components/shared/demo-badge";
import { useLabBalance } from "@/hooks/use-lab-balance";
import { USD } from "@/lib/format";
import { NumberTicker } from "@/studio/components/effects/number-ticker";
import { LoadingStatus, ShimmerSkeleton } from "@/studio/components/effects/shimmer-skeleton";
import { StudioSection } from "@/studio/components/profile/studio-section";
import { useMountedAfterHydration } from "@/studio/lib/hydration";
import { FADE, SPRING } from "@/studio/lib/motion";

/**
 * The balance as a half-circle gauge in the tone of how much is left, with a needle that
 * swings to the value (transform only; it jumps there with reduced motion) and a tick at the
 * alert floor.
 */
function StudioBalanceGauge({ value }: { value: BalanceGaugeValue }) {
  const t = useTranslations("admin.balance");
  const format = useFormatter();
  const clientMount = useMountedAfterHydration();
  const percent = Math.round(value.share * 100);
  const angle = -90 + value.share * 180;
  const floorInner = gaugePoint(value.floorShare, 64);
  const floorOuter = gaugePoint(value.floorShare, 96);

  return (
    // biome-ignore lint/a11y/useSemanticElements: the meter is drawn in SVG, which <meter> cannot hold
    <div
      role="meter"
      aria-label={t("gauge")}
      aria-valuemin={0}
      aria-valuemax={value.funds}
      aria-valuenow={value.balance}
      aria-valuetext={t("gaugeValue", { amount: format.number(value.balance, USD), percent })}
      data-tone={value.tone}
      className="relative mx-auto w-full max-w-72"
    >
      <svg viewBox="0 0 200 110" className="w-full overflow-visible" aria-hidden>
        <path
          d={GAUGE_ARC}
          pathLength={100}
          fill="none"
          strokeWidth={14}
          strokeLinecap="round"
          className="stroke-(--studio-glass-strong)"
        />
        {value.share > 0 && (
          <motion.path
            d={GAUGE_ARC}
            pathLength={100}
            fill="none"
            strokeWidth={14}
            strokeLinecap="round"
            strokeDasharray={`${value.share * 100} 100`}
            className="stroke-(--tone) drop-shadow-[0_0_10px_var(--tone)]"
            initial={clientMount ? { opacity: 0 } : false}
            animate={{ opacity: 1 }}
            transition={FADE}
          />
        )}
        {value.floorShare > 0 && (
          <line
            x1={floorInner.x}
            y1={floorInner.y}
            x2={floorOuter.x}
            y2={floorOuter.y}
            strokeWidth={2.5}
            strokeLinecap="round"
            className="stroke-foreground/60"
          />
        )}
      </svg>
      <motion.span
        aria-hidden
        className="absolute left-[calc(50%-1px)] h-[52%] w-0.5 rounded-full bg-foreground/80"
        style={{ bottom: `${(10 / 110) * 100}%`, originX: 0.5, originY: 1 }}
        initial={clientMount ? { rotate: -90 } : false}
        animate={{ rotate: angle }}
        transition={SPRING}
      />
      <span
        aria-hidden
        className="absolute left-1/2 size-3 -translate-x-1/2 translate-y-1/2 rounded-full border-2 border-background bg-foreground"
        style={{ bottom: `${(10 / 110) * 100}%` }}
      />
    </div>
  );
}

/** Studio lab balance: the gauge, spend this month, the alert floor and today's free calls. */
export function StudioBalancePanel() {
  const t = useTranslations("admin.balance");
  const tCommon = useTranslations("common");
  const format = useFormatter();
  const now = useNow({ updateInterval: 60_000 });
  const monthName = useMonthName();
  const quotaTitle = useId();
  const balance = useLabBalance();

  return (
    <StudioSection
      id="studio-admin-balance"
      title={
        <>
          {t("title")}
          <DemoBadge demo={balance.data?.demo} />
        </>
      }
      description={t("description")}
    >
      {balance.isPending ? (
        <div className="grid gap-6 md:grid-cols-2" aria-busy="true">
          <LoadingStatus label={tCommon("loading")} />
          <ShimmerSkeleton className="mx-auto aspect-[2/1.1] w-full max-w-72 rounded-2xl" />
          <ShimmerSkeleton className="h-36 rounded-2xl" />
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
                <div
                  role="alert"
                  data-tone="danger"
                  className="flex items-start gap-2 rounded-xl border border-(--tone)/30 bg-(--tone)/10 px-3 py-2 text-sm text-(--tone-fg)"
                >
                  <TriangleAlertIcon aria-hidden className="mt-0.5 size-4 shrink-0" />
                  <p>
                    <span className="font-semibold">{t("belowFloorTitle")}. </span>
                    {t("belowFloor", { floor: format.number(gauge.floor, USD) })}
                  </p>
                </div>
              )}
              <div className="grid items-center gap-6 md:grid-cols-2">
                <div className="grid justify-items-center gap-2">
                  <StudioBalanceGauge value={gauge} />
                  <p className="font-mono text-3xl font-semibold tracking-tight text-foreground">
                    <NumberTicker value={gauge.balance} format={USD} />
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {t("left", { percent: Math.round(gauge.share * 100) })}
                  </p>
                </div>
                <dl className="grid grid-cols-2 gap-2">
                  {[
                    {
                      label: t("spent", { month: monthName(balance.data.month) }),
                      value: format.number(gauge.spent, USD),
                    },
                    { label: t("floor"), value: format.number(gauge.floor, USD) },
                    {
                      label: t("autoTopUp"),
                      value: balance.data.auto_top_up ? t("on") : t("off"),
                    },
                    {
                      label: t("checkedLabel"),
                      value: format.relativeTime(new Date(balance.data.checked_at), now),
                    },
                  ].map((item) => (
                    <div
                      key={item.label}
                      className="grid min-w-0 gap-1 rounded-xl border border-(--studio-glass-border) bg-(--studio-glass) px-3 py-2.5"
                    >
                      <dt className="truncate text-xs text-muted-foreground">{item.label}</dt>
                      <dd className="font-mono text-sm font-semibold text-foreground">
                        {item.value}
                      </dd>
                    </div>
                  ))}
                </dl>
              </div>
              <section aria-labelledby={quotaTitle} className="grid gap-2">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <h3 id={quotaTitle} className="text-sm font-medium text-foreground">
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
                    className="h-2 w-full overflow-hidden rounded-full bg-(--studio-glass-strong)"
                  >
                    <div
                      data-tone={quota.tone}
                      className="h-full origin-left rounded-full bg-(--tone) transition-transform duration-700 ease-out motion-reduce:transition-none"
                      style={{ transform: `scaleX(${quota.percent / 100})` }}
                    />
                  </div>
                )}
                <p className="text-xs text-muted-foreground">{t("freeHint")}</p>
              </section>
            </div>
          );
        })()
      )}
    </StudioSection>
  );
}
