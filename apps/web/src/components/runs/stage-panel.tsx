"use client";

import {
  CircleDashedIcon,
  CircleMinusIcon,
  EyeIcon,
  HistoryIcon,
  LoaderCircleIcon,
  TriangleAlertIcon,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { useId } from "react";
import type { LiteratureOutput, RunDetail, StageAttemptOut } from "@/client";
import { EmptyState, LoadingRows, QueryError } from "@/components/app/query-state";
import { StageStatusBadge } from "@/components/app/status-badge";
import { JsonView } from "@/components/shared/json-view";
import { StageIcon } from "@/components/shared/stage-icon";
import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { type StageView, useStage } from "@/hooks/use-stage";
import type { StageWait } from "@/lib/run-events";
import type { StageOverview } from "@/lib/stage-output";
import { isTerminalRunStatus } from "@/lib/timeline";
import type { LiveTraining } from "@/lib/training-curves";
import { ApprovalPanel, AwaitingPreview } from "./approval-panel";
import { StageWaitAlert } from "./stage-wait";
import { useLabels } from "./use-labels";
import { VersionDetails, VersionSwitcher } from "./versions";
import type { CodingBase } from "./views/coding-view";
import { LiveTrainingCurves } from "./views/experiment-view";
import { StageOutputView } from "./views/stage-output-view";

/**
 * The live curves of a stage that trains (`undefined` for the stages that don't): null until
 * the first epoch of its current attempt arrives.
 */
type Training = LiveTraining | null | undefined;

/** The stage's newest attempt while it works without an output yet (a finished run has none). */
function workingAttempt(run: RunDetail, view: StageView): StageAttemptOut | null {
  const attempt = view.currentAttempt;
  return attempt &&
    !isTerminalRunStatus(run.status) &&
    (attempt.status === "running" || attempt.status === "pending") &&
    attempt.outputs.length === 0
    ? attempt
    : null;
}

/** The coding version or attempt that `view.selected` is compared with, if any. */
function codingBaseOf(view: StageView): CodingBase | null {
  const previous = view.previous;
  const narrowed = view.previousNarrowed;
  if (!previous || narrowed?.kind !== "coding") {
    return null;
  }
  return {
    relation: previous.relation,
    attempt: previous.attempt.attempt,
    version: previous.output.version,
    files: narrowed.data.files,
  };
}

/** The stage has no output to show: why, and what happens next. */
function NoOutput({
  run,
  entry,
  view,
  training,
}: {
  run: RunDetail;
  entry: StageOverview;
  view: StageView;
  training: Training;
}) {
  const t = useTranslations("run.stage");
  const labels = useLabels();
  const attempt = view.currentAttempt;
  const working = workingAttempt(run, view);
  if (working && training !== undefined) {
    // A stage that trains shows its curves while it works.
    return (
      <div className="grid gap-4">
        <Alert role="status">
          <LoaderCircleIcon aria-hidden className="motion-safe:animate-spin" />
          <AlertTitle>{t("working", { attempt: working.attempt })}</AlertTitle>
          <AlertDescription>{t("workingDescription")}</AlertDescription>
        </Alert>
        <LiveTrainingCurves training={training} />
      </div>
    );
  }
  if (!run.config.stages.some((stage) => stage === entry.stage)) {
    return (
      <EmptyState
        icon={<CircleMinusIcon aria-hidden />}
        title={t("notInRun")}
        description={t("notInRunDescription")}
      />
    );
  }
  if (!attempt) {
    return entry.status === "skipped" ? (
      <EmptyState
        icon={<CircleMinusIcon aria-hidden />}
        title={t("skipped")}
        description={t("skippedDescription")}
      />
    ) : (
      <EmptyState
        icon={<CircleDashedIcon aria-hidden />}
        title={t("notStarted")}
        description={t("notStartedDescription")}
      />
    );
  }
  if (attempt.status === "failed" || attempt.status === "cancelled") {
    return (
      <Alert
        variant={attempt.status === "failed" ? "destructive" : "default"}
        role={attempt.status === "failed" ? "alert" : "note"}
      >
        <TriangleAlertIcon aria-hidden />
        <AlertTitle>
          {attempt.status === "failed"
            ? t("failedNoOutput", { attempt: attempt.attempt })
            : t("cancelledNoOutput", { attempt: attempt.attempt })}
        </AlertTitle>
        {attempt.error && (
          <AlertDescription className="break-words">
            {labels.errorText(attempt.error)}
          </AlertDescription>
        )}
      </Alert>
    );
  }
  if (attempt.status === "running" || attempt.status === "pending") {
    return (
      <EmptyState
        icon={<LoaderCircleIcon aria-hidden className="motion-safe:animate-spin" />}
        title={t("working", { attempt: attempt.attempt })}
        description={t("workingDescription")}
      />
    );
  }
  return <EmptyState icon={<CircleDashedIcon aria-hidden />} title={t("noOutput")} />;
}

/** A newer attempt has no output yet (or failed): say so above the older output on screen. */
function NewerAttemptNote({ view }: { view: StageView }) {
  const t = useTranslations("run.stage");
  const labels = useLabels();
  const newest = view.currentAttempt;
  const shown = view.selected;
  if (!view.followingLatest || !newest || !shown || newest.attempt <= shown.attempt.attempt) {
    return null;
  }
  const failed = newest.status === "failed";
  const ended = failed || newest.status === "cancelled";
  return (
    // A failure is urgent; a newer attempt at work is news, announced politely.
    <Alert variant={failed ? "destructive" : "default"} role={failed ? "alert" : "status"}>
      {ended ? (
        <TriangleAlertIcon aria-hidden />
      ) : (
        <LoaderCircleIcon aria-hidden className="motion-safe:animate-spin" />
      )}
      <AlertTitle>
        {failed
          ? t("failedNoOutput", { attempt: newest.attempt })
          : ended
            ? t("cancelledNoOutput", { attempt: newest.attempt })
            : t("working", { attempt: newest.attempt })}
      </AlertTitle>
      <AlertDescription className="break-words">
        {ended && newest.error ? `${labels.errorText(newest.error)} ` : ""}
        {t("showingAttempt", { attempt: shown.attempt.attempt })}
      </AlertDescription>
    </Alert>
  );
}

function StageBody({
  run,
  entry,
  view,
  literature,
  underReview,
  training,
}: {
  run: RunDetail;
  entry: StageOverview;
  view: StageView;
  literature: LiteratureOutput | null;
  /** An output of this stage waits for review while another version is on screen. */
  underReview: boolean;
  training: Training;
}) {
  const t = useTranslations("run.stage");
  const tApproval = useTranslations("run.approval");
  if (view.query.isPending && !view.detail) {
    return <LoadingRows rows={4} label={t("loading")} />;
  }
  if (view.query.isError) {
    return <QueryError error={view.query.error} onRetry={() => view.query.refetch()} />;
  }
  const selected = view.selected;
  if (!selected || !view.narrowed) {
    return <NoOutput run={run} entry={entry} view={view} training={training} />;
  }
  const newest = view.current;
  // A newer attempt trains while an earlier attempt's output is on screen.
  const trainingAttempt = training !== undefined ? workingAttempt(run, view) : null;
  return (
    <div className="grid gap-4">
      {underReview && (
        <Alert role="note">
          <EyeIcon aria-hidden />
          <AlertTitle>{t("otherThanReview")}</AlertTitle>
          <AlertAction>
            {/* The output under review is always the stage's newest version. */}
            <Button size="sm" variant="outline" onClick={() => view.select(null)}>
              {t("backToReview")}
            </Button>
          </AlertAction>
        </Alert>
      )}
      {!underReview &&
        !view.followingLatest &&
        newest &&
        newest.output.id !== selected.output.id && (
          <Alert role="note">
            <HistoryIcon aria-hidden />
            <AlertTitle>{t("olderVersion")}</AlertTitle>
            <AlertAction>
              <Button size="sm" variant="outline" onClick={() => view.select(null)}>
                {t("showLatest")}
              </Button>
            </AlertAction>
          </Alert>
        )}
      <NewerAttemptNote view={view} />
      {training !== undefined && trainingAttempt && (
        <LiveTrainingCurves training={training} attempt={trainingAttempt.attempt} />
      )}
      <VersionDetails version={selected} />
      <StageOutputView
        runId={run.id}
        outputId={selected.output.id}
        narrowed={view.narrowed}
        literature={literature}
        codingBase={codingBaseOf(view)}
      />
      {view.narrowed.kind !== "raw" && (
        <details className="group rounded-lg border">
          <summary className="cursor-pointer rounded-lg px-3 py-2 text-sm font-medium outline-none select-none hover:bg-muted/50 focus-visible:ring-3 focus-visible:ring-ring/50">
            {t("json")}
          </summary>
          <div className="border-t p-3">
            <JsonView value={selected.output.data} label={tApproval("outputLabel")} />
          </div>
        </details>
      )}
    </div>
  );
}

/**
 * One stage of the run: its versions (with a switcher when there are several) and the chosen
 * one in the stage's view. While the stage's output waits for review, the review takes its place:
 * the approval panel for people who may decide, a read-only preview for everyone else. A stage
 * that trains (the experiment) draws its live curves while its attempt works.
 */
export function StagePanel({
  run,
  entry,
  literature,
  wait,
  training,
}: {
  run: RunDetail;
  entry: StageOverview;
  /** The run's latest literature output, for method proposals and draft citations. */
  literature: LiteratureOutput | null;
  /** The stage's attempt waits before it tries again (`stage.waiting`). */
  wait?: StageWait;
  /**
   * For the experiment stage: its live training curves (null before the first epoch); left
   * out for the other stages.
   */
  training?: LiveTraining | null;
}) {
  const labels = useLabels();
  const headingId = useId();
  const view = useStage(run.id, entry.stage);
  const awaiting = run.awaiting && run.awaiting_stage === entry.stage ? run.awaiting : null;
  // Following the newest version shows the review; picking another version shows that one.
  const reviewing =
    awaiting !== null && (view.followingLatest || view.selected?.output.id === awaiting.id);
  return (
    <section aria-labelledby={headingId} className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <StageIcon stage={entry.stage} className="size-5" />
          <h2 id={headingId} className="text-lg font-semibold">
            {labels.stage(entry.stage)}
          </h2>
          <StageStatusBadge status={entry.status} />
        </div>
        {view.versions.length > 1 && (
          <VersionSwitcher view={view} underReviewId={awaiting?.id ?? null} />
        )}
      </div>
      {entry.status === "running" && <StageWaitAlert wait={wait} />}
      {reviewing ? (
        run.can_steer ? (
          <ApprovalPanel run={run} literature={literature} />
        ) : (
          <AwaitingPreview run={run} literature={literature} />
        )
      ) : (
        <StageBody
          run={run}
          entry={entry}
          view={view}
          literature={literature}
          underReview={awaiting !== null}
          training={training}
        />
      )}
    </section>
  );
}
