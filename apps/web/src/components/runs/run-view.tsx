"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeftIcon, CircleAlertIcon, PauseCircleIcon } from "lucide-react";
import Link from "next/link";
import { useFormatter, useTranslations } from "next-intl";
import { useCallback, useMemo } from "react";
import {
  getRunOptions,
  getRunQueryKey,
  listStagesOptions,
} from "@/client/@tanstack/react-query.gen";
import { LoadingRows, PageHeader, QueryError } from "@/components/app/query-state";
import { RunStatusBadge } from "@/components/app/status-badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { useRunEvents } from "@/hooks/use-run-events";
import { toAmount, USD } from "@/lib/format";
import { buildTimeline, isTerminalRunStatus, STAGE_ORDER } from "@/lib/timeline";
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
  const queryClient = useQueryClient();

  const run = useQuery({
    ...getRunOptions({ path: { run_id: runId } }),
    // Live events trigger refetches; this is the fallback while the stream is down.
    refetchInterval: (query) => (isTerminalRunStatus(query.state.data?.status) ? false : 20_000),
  });
  const stages = useQuery({ ...listStagesOptions(), staleTime: Number.POSITIVE_INFINITY });

  const refreshRun = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: getRunQueryKey({ path: { run_id: runId } }) });
  }, [queryClient, runId]);
  const stream = useRunEvents(runId, refreshRun);

  const stageOrder = useMemo(
    () =>
      stages.data
        ? [...stages.data].sort((a, b) => a.position - b.position).map((stage) => stage.id)
        : [...STAGE_ORDER],
    [stages.data],
  );
  const timeline = useMemo(
    () => (run.data ? buildTimeline(stageOrder, run.data.stages, run.data.status) : []),
    [run.data, stageOrder],
  );

  if (run.isPending) {
    return <LoadingRows rows={5} />;
  }
  if (run.isError) {
    return <QueryError error={run.error} onRetry={() => run.refetch()} />;
  }

  const detail = run.data;
  const finished = isTerminalRunStatus(detail.status);

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
          actions={detail.can_steer && !finished ? <CancelRunButton runId={detail.id} /> : null}
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

      <StageTimeline entries={timeline} />

      {detail.awaiting &&
        (detail.can_steer ? (
          <ApprovalPanel key={detail.awaiting_stage ?? "awaiting"} run={detail} />
        ) : (
          <AwaitingPreview run={detail} />
        ))}

      <EventLog events={stream.events} state={stream.state} onReconnect={stream.reconnect} />
    </div>
  );
}
