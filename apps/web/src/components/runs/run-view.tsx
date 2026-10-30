"use client";

import { ChevronLeftIcon, CircleAlertIcon, PauseCircleIcon } from "lucide-react";
import Link from "next/link";
import { useFormatter, useTranslations } from "next-intl";
import { LoadingRows, PageHeader, QueryError } from "@/components/app/query-state";
import { RunStatusBadge } from "@/components/app/status-badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { useRunView } from "@/hooks/use-run-view";
import { toAmount, USD } from "@/lib/format";
import { ApprovalPanel, AwaitingPreview } from "./approval-panel";
import { CancelRunButton } from "./cancel-run-button";
import { EventLog } from "./event-log";
import { StageTimeline } from "./stage-timeline";
import { useLabels } from "./use-labels";

export function RunView({ runId }: { runId: string }) {
  const t = useTranslations("run");
  const tp = useTranslations("project.newRun.policies");
  const format = useFormatter();
  const labels = useLabels();
  const view = useRunView(runId);
  const run = view.query;

  if (run.isPending) {
    return <LoadingRows rows={5} />;
  }
  if (run.isError) {
    return <QueryError error={run.error} onRetry={() => run.refetch()} />;
  }

  const detail = run.data;

  return (
    <div className="grid gap-6">
      <div>
        <Link
          href={`/projects/${detail.project_id}`}
          className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ChevronLeftIcon className="size-4" aria-hidden />
          {t("backToProject")}
        </Link>
        <PageHeader
          title={detail.topic}
          actions={view.canCancel ? <CancelRunButton runId={detail.id} /> : null}
        >
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 pt-1 text-sm text-muted-foreground">
            <RunStatusBadge status={detail.status} />
            <span>
              {t("meta.created", {
                date: format.dateTime(new Date(detail.created_at), {
                  dateStyle: "medium",
                  timeStyle: "short",
                }),
              })}
            </span>
            <span>{t("meta.policy", { policy: tp(`${detail.llm_policy}.label`) })}</span>
            <span>
              {detail.budget_cap_usd === null
                ? t("meta.noCap")
                : t("meta.cap", { amount: format.number(toAmount(detail.budget_cap_usd), USD) })}
            </span>
          </div>
        </PageHeader>
      </div>

      {detail.error && (
        <Alert variant="destructive">
          <CircleAlertIcon aria-hidden />
          <AlertTitle>{t("errorTitle")}</AlertTitle>
          <AlertDescription className="break-words">
            {labels.errorText(detail.error)}
          </AlertDescription>
        </Alert>
      )}
      {detail.status === "paused_budget" && (
        <Alert>
          <PauseCircleIcon aria-hidden />
          <AlertTitle>{t("pausedTitle")}</AlertTitle>
          <AlertDescription>{t("pausedDescription")}</AlertDescription>
        </Alert>
      )}

      <StageTimeline entries={view.timeline} />

      {view.awaiting &&
        (view.canSteer ? (
          <ApprovalPanel key={detail.awaiting_stage ?? "awaiting"} run={detail} />
        ) : (
          <AwaitingPreview run={detail} />
        ))}

      <EventLog events={view.events} state={view.streamState} onReconnect={view.reconnect} />
    </div>
  );
}
