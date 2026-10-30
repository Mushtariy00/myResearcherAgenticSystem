"use client";

import { CoinsIcon } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { percentUsed, toAmount, USD } from "@/lib/format";
import { compareStages } from "@/lib/stage-meta";
import { cn } from "@/lib/utils";
import { NumberTicker } from "@/studio/components/effects/number-ticker";
import { stageAttr } from "@/studio/lib/stages";
import { useRunPage } from "./run-context";
import { Chip } from "./run-ui";
import { useRunLabels } from "./use-run-labels";

/** Dollars with cents, and fractions of a cent for the small amounts single calls cost. */
export const SPEND_FORMAT = {
  ...USD,
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
} as const;

/**
 * The run's live LLM spend: a spring-counted total (the run detail's, failed and cancelled
 * attempts included), the share of each stage in stage colours and the paid and free calls (from
 * its `llm.call` events), and the run's cost cap when it has one.
 */
export function SpendTile({ className }: { className?: string }) {
  const { run, view } = useRunPage();
  const t = useTranslations("studioRun.spend");
  const tRun = useTranslations("run.meta");
  const format = useFormatter();
  const labels = useRunLabels();
  const spend = view.spend;
  const cap = run.budget_cap_usd === null ? null : toAmount(run.budget_cap_usd);
  const used = cap !== null && cap > 0 ? percentUsed(spend.totalUsd, cap) : null;
  const segments = Object.entries(spend.byStage)
    .filter(([, amount]) => amount > 0)
    .sort(([a], [b]) => compareStages(a, b));
  const money = (amount: number) => format.number(amount, SPEND_FORMAT);

  return (
    <div
      className={cn(
        "grid w-full min-w-0 content-start gap-3 rounded-2xl border border-(--studio-glass-border) bg-(--studio-glass) p-4 shadow-[inset_0_1px_0_0_var(--studio-glass-highlight)] lg:w-72",
        className,
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          <CoinsIcon aria-hidden className="size-3.5" />
          {t("title")}
        </p>
        {spend.switchedToFree && <Chip tone="warning">{t("switchedToFree")}</Chip>}
      </div>
      <p className="font-mono text-3xl font-semibold tracking-tight text-foreground">
        <NumberTicker value={spend.totalUsd} format={SPEND_FORMAT} />
      </p>
      {segments.length > 0 && (
        <div className="grid gap-2">
          <div
            aria-hidden
            className="flex h-1.5 w-full gap-px overflow-hidden rounded-full bg-(--studio-glass-strong)"
          >
            {segments.map(([stage, amount]) => (
              <span
                key={stage}
                data-stage={stageAttr(stage)}
                className="h-full bg-[var(--tone,var(--studio-neutral))]"
                style={{ width: `${(amount / Math.max(spend.totalUsd, amount)) * 100}%` }}
              />
            ))}
          </div>
          <ul aria-label={t("byStage")} className="flex flex-wrap gap-x-3 gap-y-1 text-[0.7rem]">
            {segments.map(([stage, amount]) => (
              <li key={stage} className="flex items-center gap-1.5 text-muted-foreground">
                <span
                  aria-hidden
                  data-stage={stageAttr(stage)}
                  className="size-1.5 rounded-full bg-[var(--tone,var(--studio-neutral))]"
                />
                <span>{labels.stage(stage)}</span>
                <span className="font-mono text-foreground tabular-nums">{money(amount)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="text-xs text-muted-foreground tabular-nums">
        {t("calls", { count: spend.calls })} ·{" "}
        {t("split", {
          paid: format.number(spend.paidCalls),
          free: format.number(spend.freeCalls),
        })}
      </p>
      {used !== null && cap !== null ? (
        <div className="grid gap-1.5">
          <div
            role="progressbar"
            aria-label={t("capUsed")}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(used)}
            className="h-1 w-full overflow-hidden rounded-full bg-(--studio-glass-strong)"
          >
            <div
              data-tone={used >= 100 ? "danger" : used >= 80 ? "warning" : "success"}
              className="h-full origin-left rounded-full bg-(--tone) transition-transform duration-700 ease-out motion-reduce:transition-none"
              style={{ transform: `scaleX(${used / 100})` }}
            />
          </div>
          <p className="text-xs text-muted-foreground tabular-nums">
            {t("ofCap", { percent: format.number(Math.round(used)), cap: money(cap) })}
          </p>
        </div>
      ) : (
        cap === null && <p className="text-xs text-muted-foreground">{tRun("noCap")}</p>
      )}
      <p className="text-[0.7rem] text-muted-foreground">{t("hint")}</p>
    </div>
  );
}
