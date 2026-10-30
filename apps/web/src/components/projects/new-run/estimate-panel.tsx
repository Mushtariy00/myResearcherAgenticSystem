"use client";

import { InfoIcon } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import type { ReactNode } from "react";
import type { RunEstimateOut } from "@/client";
import { useStageName } from "@/components/dashboard/run-stage";
import { DemoBadge } from "@/components/shared/demo-badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useErrorMessage } from "@/hooks/use-error-message";
import type { NewRunEstimate } from "@/hooks/use-new-run-form";
import { toAmount, USD } from "@/lib/format";

/** Cents are too coarse for single calls: amounts under $1 keep a third decimal. */
function useMoney(): (value: string | number) => string {
  const format = useFormatter();
  return (value) => {
    const amount = toAmount(value);
    return format.number(amount, {
      ...USD,
      maximumFractionDigits: amount > 0 && amount < 1 ? 3 : 2,
    });
  };
}

function Note({ children }: { children: ReactNode }) {
  return (
    <p className="flex items-start gap-2 text-xs leading-snug text-muted-foreground">
      <InfoIcon aria-hidden className="mt-px size-3.5 shrink-0" />
      <span>{children}</span>
    </p>
  );
}

function Assumptions({ data }: { data: RunEstimateOut }) {
  const t = useTranslations("wizard.estimate");
  const format = useFormatter();
  const money = useMoney();
  const stageName = useStageName();
  const { steps, paid_chain: chain } = data.assumptions;
  return (
    <div className="grid gap-3">
      {steps.length > 0 && (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-xs">
            <caption className="px-2 pt-2 text-left font-medium">{t("assumptions.title")}</caption>
            <thead>
              <tr className="border-b text-muted-foreground">
                <th scope="col" className="px-2 py-1.5 text-left font-medium">
                  {t("assumptions.step")}
                </th>
                <th scope="col" className="px-2 py-1.5 text-right font-medium">
                  {t("assumptions.calls")}
                </th>
                <th scope="col" className="px-2 py-1.5 text-right font-medium">
                  {t("assumptions.tokens")}
                </th>
                <th scope="col" className="px-2 py-1.5 text-right font-medium">
                  {t("assumptions.cost")}
                </th>
              </tr>
            </thead>
            <tbody>
              {steps.map((step) => (
                <tr key={`${step.stage}-${step.role}`} className="border-b last:border-b-0">
                  <th scope="row" className="px-2 py-1.5 text-left font-normal">
                    {stageName(step.stage)}
                    <span className="block text-muted-foreground">{t(`roles.${step.role}`)}</span>
                  </th>
                  <td className="px-2 py-1.5 text-right tabular-nums">
                    {t("assumptions.callsValue", {
                      low: step.calls_low,
                      expected: step.calls_expected,
                      high: step.calls_high,
                    })}
                  </td>
                  <td className="px-2 py-1.5 text-right tabular-nums">
                    {t("assumptions.tokensValue", {
                      prompt: format.number(step.prompt_tokens_per_call),
                      completion: format.number(step.completion_tokens_per_call),
                    })}
                  </td>
                  <td className="px-2 py-1.5 text-right whitespace-nowrap tabular-nums">
                    {t("range", { low: money(step.low_usd), high: money(step.high_usd) })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {chain.length > 0 && (
        <div className="grid gap-1">
          <p className="text-xs font-medium">{t("paidChain")}</p>
          <ol className="grid list-decimal gap-0.5 pl-5 text-xs text-muted-foreground">
            {chain.map((model) => (
              <li key={model.id} className="break-words">
                <code className="font-mono text-foreground">{model.id}</code>{" "}
                {model.known
                  ? t("price", {
                      prompt: money(model.prompt_usd_per_mtok),
                      completion: money(model.completion_usd_per_mtok),
                    })
                  : t("priceUnknown")}
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}

/**
 * The cost estimate of the options as they are: the range, expected calls, why paid models may
 * not be used, and (detailed) the assumptions per step. It follows the form as options change.
 */
export function EstimatePanel({
  estimate,
  detailed = false,
}: {
  estimate: NewRunEstimate;
  detailed?: boolean;
}) {
  const t = useTranslations("wizard.estimate");
  const errorMessage = useErrorMessage();
  const money = useMoney();
  const { data, available, isUpdating, error } = estimate;

  const header = (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h3 className="text-sm font-semibold">{t("title")}</h3>
      {data && <DemoBadge demo={data.demo} />}
    </div>
  );

  if (!available) {
    return (
      <div className="grid gap-2">
        {header}
        <p className="text-sm text-muted-foreground">{t("unavailable")}</p>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="grid gap-2" aria-busy={!error}>
        {header}
        {error ? (
          <p role="alert" className="text-sm text-destructive">
            {t("failed", { reason: errorMessage(error) })}
          </p>
        ) : (
          <>
            <span className="sr-only">{t("loading")}</span>
            <Skeleton className="h-8 w-40" />
            <Skeleton className="h-4 w-56" />
          </>
        )}
      </div>
    );
  }

  const free = toAmount(data.high_usd) <= 0;
  return (
    <div className="grid gap-3" aria-busy={isUpdating}>
      {header}
      <div aria-live="polite" className="grid gap-1">
        <p className="text-2xl font-semibold tabular-nums">
          {free ? t("free") : t("range", { low: money(data.low_usd), high: money(data.high_usd) })}
        </p>
        <p className="text-sm text-muted-foreground">
          {free ? null : <>{t("expected", { amount: money(data.expected_usd) })} · </>}
          {t("calls", {
            expected: data.expected_calls,
            low: data.calls_low,
            high: data.calls_high,
          })}
        </p>
      </div>
      {isUpdating && <p className="text-xs text-muted-foreground">{t("updating")}</p>}
      {error && <p className="text-xs text-destructive">{t("stale")}</p>}
      {data.paid_blocked_by && <Note>{t(`paidBlocked.${data.paid_blocked_by}`)}</Note>}
      {data.capped_by && <Note>{t(`cappedBy.${data.capped_by}`)}</Note>}
      {data.llm_policy === "auto" && data.paid_possible && (
        <Note>{t("budgetRemaining", { amount: money(data.budget_remaining_usd) })}</Note>
      )}
      {detailed && <Assumptions data={data} />}
      <p className="text-xs text-muted-foreground">{t("note")}</p>
    </div>
  );
}
