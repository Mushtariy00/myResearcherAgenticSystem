"use client";

import { CircleAlertIcon, EyeIcon, PauseCircleIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useMemo } from "react";
import { LoadingRows, QueryError } from "@/components/app/query-state";
import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useRunView } from "@/hooks/use-run-view";
import { EventLog } from "./event-log";
import { defaultStage, literatureOf } from "./run-data";
import { RunHeader } from "./run-header";
import { StagePanel } from "./stage-panel";
import { StageTabs, stageTabId } from "./stage-tabs";
import { StageTimeline } from "./stage-timeline";
import { useLabels } from "./use-labels";
import { useStageParam } from "./use-stage-param";

/**
 * The Classic run page: header and actions, the stage timeline, one tab per stage with its
 * output (and the review, while an output waits for a decision), and the live event log.
 */
export function RunView({ runId }: { runId: string }) {
  const t = useTranslations("run");
  const labels = useLabels();
  const view = useRunView(runId);
  const [stageParam, setStage] = useStageParam();
  const literature = useMemo(() => literatureOf(view.run), [view.run]);
  const run = view.query;

  if (run.isPending) {
    return <LoadingRows rows={5} />;
  }
  if (run.isError) {
    return <QueryError error={run.error} onRetry={() => run.refetch()} />;
  }

  const detail = run.data;
  const selected =
    stageParam && view.timeline.some((entry) => entry.stage === stageParam)
      ? stageParam
      : defaultStage(view.timeline, detail.awaiting_stage);
  const awaitingStage = view.awaiting?.stage ?? null;

  function openReview(stage: string) {
    setStage(stage);
    // The callout goes away with the switch; keep focus on the stage it opened.
    requestAnimationFrame(() => document.getElementById(stageTabId(stage))?.focus());
  }

  return (
    <div className="grid gap-6">
      <RunHeader run={detail} view={view} />

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
      {awaitingStage !== null && selected !== awaitingStage && (
        // A status, not an alert: it reappears whenever another stage is opened.
        <Alert role="status" className="border-amber-500/40">
          <EyeIcon aria-hidden />
          <AlertTitle>
            {view.canDecide
              ? t("review.callout", { stage: labels.stage(awaitingStage) })
              : t("review.calloutReadOnly", { stage: labels.stage(awaitingStage) })}
          </AlertTitle>
          <AlertAction>
            <Button size="sm" variant="outline" onClick={() => openReview(awaitingStage)}>
              {view.canDecide ? t("review.open") : t("review.view")}
            </Button>
          </AlertAction>
        </Alert>
      )}

      <StageTimeline entries={view.timeline} />

      <StageTabs timeline={view.timeline} selected={selected} onSelect={setStage}>
        {(entry) => <StagePanel run={detail} entry={entry} literature={literature} />}
      </StageTabs>

      <EventLog events={view.events} state={view.streamState} onReconnect={view.reconnect} />
    </div>
  );
}
