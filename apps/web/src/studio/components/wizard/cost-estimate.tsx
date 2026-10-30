"use client";

import { CircleAlertIcon, CoinsIcon } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { DemoBadge } from "@/components/shared/demo-badge";
import type { NewRunEstimate } from "@/hooks/use-new-run-form";
import { toAmount, USD } from "@/lib/format";
import { cn } from "@/lib/utils";
import { StudioInlineError } from "@/studio/components/dashboard/studio-panel";
import { NumberTicker } from "@/studio/components/effects/number-ticker";
import { PulseDot } from "@/studio/components/effects/pulse-dot";
import { ShimmerSkeleton } from "@/studio/components/effects/shimmer-skeleton";

/**
 * The live cost estimate beside the wizard (useNewRunForm's estimate): the expected paid spend
 * as a spring-counted figure, its range and the LLM calls, and why paid models will not be used
 * or what caps them. It follows the options as they settle; while new options are estimated the
 * previous figures stay, marked as updating. A polite live region announces new figures.
 */
export function CostEstimate({
  estimate,
  className,
}: {
  estimate: NewRunEstimate;
  className?: string;
}) {
  const t = useTranslations("studioWork.wizard.estimate");
  const format = useFormatter();
  const data = estimate.data;
  const usd = (value: string) => format.number(toAmount(value), USD);

  return (
    <section
      aria-labelledby="studio-estimate-title"
      aria-busy={estimate.isUpdating || undefined}
      className={cn("studio-glass grid content-start gap-4 rounded-2xl p-4 sm:p-5", className)}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3
          id="studio-estimate-title"
          className="flex items-center gap-2 text-sm font-semibold text-foreground"
        >
          <CoinsIcon aria-hidden className="size-4 text-(--studio-accent-fg)" />
          {t("title")}
        </h3>
        <div className="flex items-center gap-2">
          {estimate.isUpdating && (
            <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
              <PulseDot tone="info" live size="sm" />
              {t("updating")}
            </span>
          )}
          <DemoBadge demo={data?.demo} />
        </div>
      </div>

      {!estimate.available ? (
        <p className="flex items-start gap-2 text-sm text-muted-foreground">
          <CircleAlertIcon aria-hidden className="mt-0.5 size-4 shrink-0" />
          {t("invalid")}
        </p>
      ) : estimate.error && !data ? (
        <StudioInlineError
          error={estimate.error}
          onRetry={() => estimate.query.refetch()}
          title={t("failed")}
        />
      ) : !data ? (
        <div className="grid gap-2" aria-busy="true">
          <span className="sr-only">{t("loading")}</span>
          <ShimmerSkeleton className="h-9 w-32" />
          <ShimmerSkeleton className="h-4 w-48" />
        </div>
      ) : (
        <div className="grid gap-3" aria-live="polite" aria-atomic="true">
          <div className="grid gap-0.5">
            <p className="text-xs text-muted-foreground">{t("expected")}</p>
            <p className="font-mono text-3xl font-semibold tracking-tight text-foreground">
              <NumberTicker value={toAmount(data.expected_usd)} format={USD} />
            </p>
            <p className="text-xs text-muted-foreground tabular-nums">
              {t("range", { low: usd(data.low_usd), high: usd(data.high_usd) })}
            </p>
          </div>
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <div className="grid gap-0.5">
              <dt className="text-xs text-muted-foreground">{t("calls")}</dt>
              <dd className="font-medium text-foreground tabular-nums">
                {t("callsValue", {
                  expected: format.number(data.expected_calls),
                  low: format.number(data.calls_low),
                  high: format.number(data.calls_high),
                })}
              </dd>
            </div>
            <div className="grid gap-0.5">
              <dt className="text-xs text-muted-foreground">{t("budgetLeft")}</dt>
              <dd className="font-medium text-foreground tabular-nums">
                {usd(data.budget_remaining_usd)}
              </dd>
            </div>
          </dl>
          {data.paid_blocked_by ? (
            <p
              data-tone={data.paid_blocked_by === "policy" ? "success" : "warning"}
              className="rounded-xl border border-(--tone)/25 bg-(--tone)/10 px-3 py-2 text-xs text-pretty text-foreground"
            >
              {t(`blocked.${data.paid_blocked_by}`)}
            </p>
          ) : data.capped_by ? (
            <p
              data-tone="info"
              className="rounded-xl border border-(--tone)/25 bg-(--tone)/10 px-3 py-2 text-xs text-pretty text-foreground"
            >
              {t(`capped.${data.capped_by}`)}
            </p>
          ) : (
            <p className="text-xs text-pretty text-muted-foreground">{t("paidPossible")}</p>
          )}
        </div>
      )}
    </section>
  );
}
