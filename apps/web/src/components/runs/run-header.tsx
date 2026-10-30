"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronLeftIcon, CoinsIcon } from "lucide-react";
import Link from "next/link";
import { useFormatter, useTranslations } from "next-intl";
import type { RunDetail } from "@/client";
import { getProjectOptions } from "@/client/@tanstack/react-query.gen";
import { PageHeader } from "@/components/app/query-state";
import { RunStatusBadge } from "@/components/app/status-badge";
import { DemoBadge } from "@/components/shared/demo-badge";
import type { RunView } from "@/hooks/use-run-view";
import { toAmount, USD } from "@/lib/format";
import type { RunSpend } from "@/lib/run-events";
import { CancelRunButton } from "./cancel-run-button";
import { DownloadsMenu } from "./downloads-menu";
import { RetryRunDialog } from "./retry-run-dialog";

/** The run's LLM spend so far (see RunView `spend`), with its calls from the live events. */
function SpendSummary({ spend }: { spend: RunSpend }) {
  const t = useTranslations("run.meta");
  const format = useFormatter();
  return (
    <span className="inline-flex flex-wrap items-center gap-x-1.5" title={t("spendHint")}>
      <CoinsIcon aria-hidden className="size-3.5" />
      <span>
        {t("spend", {
          amount: format.number(spend.totalUsd, {
            ...USD,
            minimumFractionDigits: 2,
            maximumFractionDigits: spend.totalUsd > 0 && spend.totalUsd < 1 ? 4 : 2,
          }),
        })}
      </span>
      <span className="text-xs">
        {spend.calls === 0
          ? t("spendNoCalls")
          : t("spendCalls", { calls: spend.calls, paid: spend.paidCalls, free: spend.freeCalls })}
      </span>
      {spend.switchedToFree && (
        <span className="text-xs text-amber-800 dark:text-amber-300">{t("spendSwitched")}</span>
      )}
    </span>
  );
}

/**
 * The top of the run page: the project link, the topic, status, start time, model policy, cost
 * cap and live spend, and the actions the user may take: downloads, retry (a finished run) and
 * cancel (a run in progress).
 */
export function RunHeader({ run, view }: { run: RunDetail; view: RunView }) {
  const t = useTranslations("run");
  const tp = useTranslations("project.newRun.policies");
  const format = useFormatter();
  // Only for the link text; the plain wording stays while it loads or if it fails.
  const project = useQuery({
    ...getProjectOptions({ path: { project_id: run.project_id } }),
    staleTime: 60_000,
  });
  const demo = view.timeline.some((entry) => entry.demo);
  const retryable = view.finished && view.retryableStages.length > 0;

  return (
    <div>
      <Link
        href={`/projects/${run.project_id}`}
        className="mb-4 inline-flex max-w-full items-center gap-1 rounded-sm text-sm text-muted-foreground outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        <ChevronLeftIcon className="size-4 shrink-0" aria-hidden />
        <span className="truncate">
          {project.data
            ? t("backToNamedProject", { project: project.data.name })
            : t("backToProject")}
        </span>
      </Link>
      <PageHeader
        title={run.topic}
        actions={
          <>
            <DownloadsMenu runId={run.id} />
            {retryable && (
              <RetryRunDialog run={run} stages={view.retryableStages} timeline={view.timeline} />
            )}
            {view.canCancel && <CancelRunButton runId={run.id} />}
          </>
        }
      >
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 pt-1 text-sm text-muted-foreground">
          <RunStatusBadge status={run.status} />
          <DemoBadge demo={demo} />
          <span>
            {t("meta.created", {
              date: format.dateTime(new Date(run.created_at), {
                dateStyle: "medium",
                timeStyle: "short",
              }),
            })}
          </span>
          <span>{t("meta.policy", { policy: tp(`${run.llm_policy}.label`) })}</span>
          <span>
            {run.budget_cap_usd === null
              ? t("meta.noCap")
              : t("meta.cap", { amount: format.number(toAmount(run.budget_cap_usd), USD) })}
          </span>
          <SpendSummary spend={view.spend} />
        </div>
      </PageHeader>
    </div>
  );
}
