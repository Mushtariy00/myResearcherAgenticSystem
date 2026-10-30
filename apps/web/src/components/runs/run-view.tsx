"use client";

import { CircleAlertIcon, EyeIcon, PauseCircleIcon, RotateCwIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useMemo } from "react";
import { LoadingRows, QueryError } from "@/components/app/query-state";
import { useWaitLabels } from "@/components/shared/wait-text";
import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useErrorMessage } from "@/hooks/use-error-message";
import { useRunView } from "@/hooks/use-run-view";
import { TRAINING_STAGE } from "@/lib/training-curves";
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
  const tCommon = useTranslations("common");
  const labels = useLabels();
  const waitLabels = useWaitLabels();
  const errorMessage = useErrorMessage();
  const view = useRunView(runId);
  const [stageParam, setStage] = useStageParam();
  const literature = useMemo(() => literatureOf(view.run), [view.run]);
  const run = view.query;

  if (run.isPending) {
    return <LoadingRows rows={5} />;
  }
  // Only a first load that failed replaces the page: after a failed refresh the run stays on
  // screen, with the review in progress, and a note says it may be out of date.
  if (run.isLoadingError) {
    return <QueryError error={run.error} onRetry={() => run.refetch()} />;
  }

  const detail = run.data;
  const selected =
    stageParam && view.timeline.some((entry) => entry.stage === stageParam)
      ? stageParam
      : defaultStage(view.timeline, detail.awaiting_stage);
  const awaitingStage = view.awaiting?.stage ?? null;
  const balanceCheck = Object.values(view.waits).find(
    (wait) => wait.reason === "lab_balance.exhausted",
  )?.retryAt;

  function openReview(stage: string) {
    setStage(stage);
    // The callout goes away with the switch; keep focus on the stage it opened.
    requestAnimationFrame(() => document.getElementById(stageTabId(stage))?.focus());
  }

  return (
    <div className="grid gap-6">
      <RunHeader run={detail} view={view} />

      {run.isRefetchError && (
        <Alert role="status" className="border-amber-500/40">
          <CircleAlertIcon aria-hidden />
          <AlertTitle>{t("refreshFailed")}</AlertTitle>
          <AlertDescription>{errorMessage(run.error)}</AlertDescription>
          <AlertAction>
            <Button size="sm" variant="outline" onClick={view.refresh}>
              <RotateCwIcon aria-hidden />
              {tCommon("retry")}
            </Button>
          </AlertAction>
        </Alert>
      )}
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
          <AlertDescription>
            {balanceCheck
              ? `${t("pausedDescription")} ${t("pausedNextCheck", { time: waitLabels.time(balanceCheck) })}`
              : t("pausedDescription")}
          </AlertDescription>
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

      <StageTimeline entries={view.timeline} waits={view.waits} />

      <StageTabs timeline={view.timeline} selected={selected} onSelect={setStage}>
        {(entry) => (
          <StagePanel
            run={detail}
            entry={entry}
            literature={literature}
            wait={view.waits[entry.stage]}
            training={entry.stage === TRAINING_STAGE ? view.training : undefined}
          />
        )}
      </StageTabs>

      <EventLog events={view.events} state={view.streamState} onReconnect={view.reconnect} />
    </div>
  );
}
