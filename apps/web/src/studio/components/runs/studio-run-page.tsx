"use client";

import {
  CircleAlertIcon,
  CompassIcon,
  PartyPopperIcon,
  PauseCircleIcon,
  RotateCwIcon,
  TriangleAlertIcon,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { useCallback, useMemo, useState } from "react";
import type { RunDetail } from "@/client";
import { useWaitLabels } from "@/components/shared/wait-text";
import { useErrorMessage } from "@/hooks/use-error-message";
import { type RunView, useRunView } from "@/hooks/use-run-view";
import { ApiError } from "@/lib/api-error";
import { stageData } from "@/lib/stage-output";
import { ConfettiBurst } from "@/studio/components/effects/confetti-burst";
import { LoadingStatus, ShimmerSkeleton } from "@/studio/components/effects/shimmer-skeleton";
import { StudioStatePanel } from "@/studio/components/studio-state-panel";
import { useReducedMotionPreference } from "@/studio/hooks/use-media-query";
import { STUDIO_ROUTES } from "@/studio/lib/nav";
import { OUTLINE_BUTTON } from "@/studio/lib/ui";
import { ApprovalDock, AwaitingNotice } from "./approval-dock";
import { PaperSheet } from "./paper-sheet";
import { RetryRunDialog } from "./retry-run-dialog";
import { type PaperTarget, RunPageProvider, type RunPageValue, useRunPage } from "./run-context";
import { defaultStage } from "./run-helpers";
import { RunHero } from "./run-hero";
import { RunLog } from "./run-log";
import { Callout, SMALL_BUTTON } from "./run-ui";
import { STAGE_SECTION_ID, StageTabs } from "./stage-tabs";
import { useCompletedTransition } from "./use-completed-transition";
import { useRunLabels } from "./use-run-labels";
import { useStageParam } from "./use-stage-param";

/**
 * The Studio run page (`/studio/runs/<id>`): the hero with the live pipeline, the stage outputs
 * in stage-coloured tabs (`?stage=`), the review dock when the visitor can decide on the output
 * waiting for review, and the live log. One confetti burst greets a run that completes while
 * the page is open. Mount it keyed by run id (the event stream belongs to one run).
 */
export function StudioRunPage({ runId }: { runId: string }) {
  const view = useRunView(runId);
  const run = view.query.data;
  if (run) {
    return <LoadedRun runId={runId} view={view} run={run} />;
  }
  if (view.query.isError) {
    return <RunLoadError error={view.query.error} onRetry={() => void view.query.refetch()} />;
  }
  return <RunPageSkeleton />;
}

function LoadedRun({ runId, view, run }: { runId: string; view: RunView; run: RunDetail }) {
  const [chosen, choose] = useStageParam();
  const reduced = useReducedMotionPreference();
  const [paper, setPaper] = useState<PaperTarget | null>(null);
  const [retry, setRetry] = useState<{ open: boolean; stage: string | null }>({
    open: false,
    stage: null,
  });
  const celebrate = useCompletedTransition(run.status);

  const stages = view.timeline.map((entry) => entry.stage);
  const fallback = defaultStage(view.timeline, view.awaiting?.stage) ?? stages[0] ?? "";
  const activeStage = chosen && stages.includes(chosen) ? chosen : fallback;
  const literatureOutput = view.timeline.find((entry) => entry.stage === "literature")?.output;
  const literature = useMemo(() => stageData("literature", literatureOutput), [literatureOutput]);

  const showStage = useCallback(
    (stage: string) => {
      choose(stage);
      requestAnimationFrame(() => {
        const section = document.getElementById(STAGE_SECTION_ID);
        const top = section?.getBoundingClientRect().top;
        if (section && top !== undefined && (top < 0 || top > window.innerHeight * 0.6)) {
          section.scrollIntoView({ block: "start", behavior: reduced ? "auto" : "smooth" });
        }
      });
    },
    [choose, reduced],
  );

  const value: RunPageValue = {
    runId,
    run,
    view,
    activeStage,
    selectStage: choose,
    showStage,
    openPaper: setPaper,
    openPaperId: paper?.paperId ?? null,
    openRetry: (stage) => setRetry({ open: true, stage: stage ?? null }),
    literature,
  };

  const reviewing = view.awaiting !== null && view.canDecide;

  return (
    <RunPageProvider value={value}>
      <div className="grid min-w-0 gap-6 lg:gap-8">
        <RunHero />
        <RunNotices refreshError={view.query.isError ? view.query.error : null} />
        <div className="grid min-w-0 gap-6 2xl:grid-cols-[minmax(0,1fr)_24rem] 2xl:items-start">
          <div className="grid min-w-0 content-start gap-4">
            <StageTabs />
            {view.awaiting && (reviewing ? <ApprovalDock /> : <AwaitingNotice />)}
          </div>
          <RunLog />
        </div>
        {/* On phones the review dock covers the end of the page: leave room to scroll past it. */}
        {reviewing && <div aria-hidden className="h-40 md:hidden" />}
      </div>
      <RetryRunDialog
        open={retry.open}
        initialStage={retry.stage}
        onOpenChange={(open) => setRetry((current) => ({ ...current, open }))}
      />
      <PaperSheet target={paper} onClose={() => setPaper(null)} />
      <ConfettiBurst when={celebrate} />
    </RunPageProvider>
  );
}

/** The run's error, a budget pause, a completed run, or a refresh that failed. */
function RunNotices({ refreshError }: { refreshError: unknown }) {
  const t = useTranslations("studioRun");
  const tRun = useTranslations("run");
  const tCommon = useTranslations("common");
  const labels = useRunLabels();
  const waitLabels = useWaitLabels();
  const errorMessage = useErrorMessage();
  const { run, view, showStage } = useRunPage();
  const writing = view.timeline.some((entry) => entry.stage === "writing");
  const balanceCheck = Object.values(view.waits).find(
    (wait) => wait.reason === "lab_balance.exhausted",
  )?.retryAt;
  return (
    <>
      {refreshError !== null && (
        <Callout
          tone="warning"
          icon={CircleAlertIcon}
          role="alert"
          title={t("refreshError")}
          action={
            <button type="button" className={SMALL_BUTTON} onClick={view.refresh}>
              <RotateCwIcon aria-hidden />
              {tCommon("retry")}
            </button>
          }
        >
          {errorMessage(refreshError)}
        </Callout>
      )}
      {run.error && (
        <Callout tone="danger" icon={TriangleAlertIcon} role="alert" title={tRun("errorTitle")}>
          {labels.errorText(run.error)}
        </Callout>
      )}
      {run.status === "paused_budget" && (
        <Callout tone="warning" icon={PauseCircleIcon} title={tRun("pausedTitle")}>
          {balanceCheck
            ? `${tRun("pausedDescription")} ${tRun("pausedNextCheck", { time: waitLabels.time(balanceCheck) })}`
            : tRun("pausedDescription")}
        </Callout>
      )}
      {run.status === "completed" && (
        <Callout
          tone="success"
          icon={PartyPopperIcon}
          title={t("notices.completedTitle")}
          action={
            writing && (
              <button type="button" className={SMALL_BUTTON} onClick={() => showStage("writing")}>
                {t("notices.openDraft")}
              </button>
            )
          }
        >
          {t("notices.completedDescription")}
        </Callout>
      )}
    </>
  );
}

function RunPageSkeleton() {
  const t = useTranslations("studioRun");
  return (
    <div aria-busy="true" className="grid gap-6 lg:gap-8">
      <LoadingStatus label={t("loading")} />
      <div className="studio-glass grid gap-6 rounded-3xl p-4 sm:p-6 lg:p-8">
        <ShimmerSkeleton className="h-4 w-40" />
        <div className="grid gap-3">
          <ShimmerSkeleton className="h-7 w-28 rounded-full" />
          <ShimmerSkeleton className="h-9 w-full max-w-2xl" />
          <ShimmerSkeleton className="h-4 w-full max-w-md" />
        </div>
        <div className="grid grid-cols-1 gap-5 md:grid-cols-5 md:gap-8">
          {Array.from({ length: 5 }, (_, index) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: static placeholders never reorder
            <ShimmerSkeleton key={index} className="h-16 rounded-2xl md:h-28" />
          ))}
        </div>
      </div>
      <ShimmerSkeleton className="h-11 w-full max-w-xl rounded-xl" />
      <ShimmerSkeleton className="h-80 w-full rounded-2xl" />
    </div>
  );
}

function RunLoadError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const t = useTranslations("studioRun");
  const errorMessage = useErrorMessage();
  const code = error instanceof ApiError ? error.code : null;
  if (code === "run.not_found" || code === "permission.denied") {
    return (
      <StudioStatePanel
        icon={<CompassIcon aria-hidden />}
        code="404"
        title={t("notFound.title")}
        description={t("notFound.description")}
        action={{ href: STUDIO_ROUTES.dashboard, label: t("notFound.back") }}
      />
    );
  }
  return (
    <StudioStatePanel
      icon={<TriangleAlertIcon aria-hidden />}
      tone="danger"
      title={t("loadError.title")}
      description={errorMessage(error)}
    >
      <button type="button" onClick={onRetry} className={OUTLINE_BUTTON}>
        <RotateCwIcon aria-hidden />
        {t("loadError.retry")}
      </button>
    </StudioStatePanel>
  );
}
