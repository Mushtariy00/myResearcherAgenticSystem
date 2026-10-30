"use client";

import {
  BracesIcon,
  CircleCheckIcon,
  CircleSlashIcon,
  CircleXIcon,
  EyeIcon,
  FileWarningIcon,
  MessageSquareQuoteIcon,
  RotateCcwIcon,
  TriangleAlertIcon,
} from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import type { ApprovalOut } from "@/client";
import { DemoBadge } from "@/components/shared/demo-badge";
import { JsonView } from "@/components/shared/json-view";
import { StageIcon } from "@/components/shared/stage-icon";
import { type StageView, useStage } from "@/hooks/use-stage";
import {
  isDemoOutput,
  type NarrowedOutput,
  outputAs,
  type RawOutput,
  type StageOverview,
  type VersionRef,
} from "@/lib/stage-output";
import { stageAttr } from "@/studio/lib/stages";
import { type CodingBase, CodingView } from "./coding-view";
import { ExperimentView } from "./experiment-view";
import { LiteratureView } from "./literature-view";
import { MethodView } from "./method-view";
import { useRunPage } from "./run-context";
import { Callout, SMALL_BUTTON, StageStatusChip, ViewCard } from "./run-ui";
import {
  RetryFromHere,
  StageEmpty,
  StageFailed,
  StageLoadError,
  StagePanelSkeleton,
  StageRunning,
} from "./stage-states";
import { useRunLabels } from "./use-run-labels";
import { VersionSwitcher } from "./version-switcher";
import { WritingView } from "./writing-view";

/**
 * One stage of the run (useStage): its status, the version on screen with what was decided on
 * it, a switcher across attempts and versions, and the output in its stage view. On the stage
 * waiting for review it shows the version under review (the one a decision applies to) until
 * another is picked. Stages the run has not reached, is still working on, or that ended
 * without an output say so.
 */
export function StagePanel({ entry }: { entry: StageOverview }) {
  const { runId, view } = useRunPage();
  const stage = entry.stage;
  const reviewId = view.awaiting?.stage === stage ? view.awaiting.output.id : null;
  const [picked, setPicked] = useState<string | null>(null);
  const wanted = picked ?? reviewId;
  const detail = useStage(runId, stage, { outputId: wanted ?? undefined });
  const { refetch, isFetching, isSuccess } = detail.query;

  // The run detail can name a version the stage detail does not list yet: fetch it once more.
  const missing = wanted !== null && isSuccess && detail.selected === undefined;
  const [refetchedFor, setRefetchedFor] = useState<string | null>(null);
  useEffect(() => {
    if (missing && wanted !== null && refetchedFor !== wanted && !isFetching) {
      setRefetchedFor(wanted);
      void refetch();
    }
  }, [missing, wanted, refetchedFor, isFetching, refetch]);
  const gaveUp = missing && refetchedFor === wanted && !isFetching;

  const shown = detail.selected ?? (gaveUp ? detail.current : undefined);
  const narrowed = detail.selected ? detail.narrowed : shown ? outputAs(stage, shown.output) : null;

  function pick(outputId: string) {
    setPicked(outputId === (reviewId ?? detail.current?.output.id) ? null : outputId);
  }

  return (
    <div data-stage={stageAttr(stage)} className="grid min-w-0 gap-4">
      <StageHeader entry={entry} detail={detail} shown={shown} reviewId={reviewId} onPick={pick} />
      <StageBody
        entry={entry}
        detail={detail}
        shown={shown}
        narrowed={narrowed}
        waiting={missing && !gaveUp}
        reviewId={reviewId}
        onShowReview={() => setPicked(null)}
      />
    </div>
  );
}

function StageHeader({
  entry,
  detail,
  shown,
  reviewId,
  onPick,
}: {
  entry: StageOverview;
  detail: StageView;
  shown: VersionRef | undefined;
  reviewId: string | null;
  onPick: (outputId: string) => void;
}) {
  const t = useTranslations("studioRun.stage");
  const labels = useRunLabels();
  const output = shown?.output;
  return (
    <div className="grid min-w-0 gap-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="grid min-w-0 gap-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="flex min-w-0 items-center gap-2.5 text-lg font-semibold tracking-tight text-foreground">
              <span
                aria-hidden
                className="flex size-8 shrink-0 items-center justify-center rounded-xl border border-(--tone)/30 bg-(--tone)/12"
              >
                <StageIcon stage={entry.stage} />
              </span>
              <span className="min-w-0 break-words">{labels.stage(entry.stage)}</span>
            </h3>
            <StageStatusChip status={entry.status} />
            {output && (
              <DemoBadge demo={isDemoOutput(output)} degradedReason={output.degraded_reason} />
            )}
          </div>
          {shown && <VersionFacts shown={shown} />}
        </div>
        {detail.versions.length > 1 && (
          <VersionSwitcher
            versions={detail.versions}
            selectedId={output?.id ?? null}
            reviewId={reviewId}
            onSelect={onPick}
          />
        )}
      </div>
      {shown?.attempt.feedback && (
        <Callout tone="warning" icon={MessageSquareQuoteIcon} title={t("feedback")}>
          <q className="whitespace-pre-line">{shown.attempt.feedback}</q>
        </Callout>
      )}
      {output?.approval && <ApprovalNote approval={output.approval} />}
    </div>
  );
}

function VersionFacts({ shown }: { shown: VersionRef }) {
  const t = useTranslations("studioRun.stage");
  const format = useFormatter();
  const { attempt, output } = shown;
  const facts = [
    t("attemptVersion", { attempt: attempt.attempt, version: output.version }),
    output.model ? t("model", { model: output.model }) : null,
    t("produced", {
      date: format.dateTime(new Date(output.created_at), {
        dateStyle: "medium",
        timeStyle: "short",
      }),
    }),
    output.edited_by
      ? output.edited_by_name
        ? t("editedBy", { name: output.edited_by_name })
        : t("editedByUnknown")
      : null,
  ].filter((fact): fact is string => fact !== null);
  return (
    <p className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
      {facts.map((fact) => (
        <span key={fact} className="min-w-0 break-words">
          {fact}
        </span>
      ))}
    </p>
  );
}

function ApprovalNote({ approval }: { approval: ApprovalOut }) {
  const t = useTranslations("studioRun.stage");
  const format = useFormatter();
  const labels = useRunLabels();
  const decision = labels.decision(approval.decision);
  const tone =
    approval.decision === "approve"
      ? "success"
      : approval.decision === "reject"
        ? "danger"
        : "warning";
  const Icon =
    approval.decision === "approve"
      ? CircleCheckIcon
      : approval.decision === "reject"
        ? CircleXIcon
        : RotateCcwIcon;
  return (
    <Callout
      tone={tone}
      icon={Icon}
      title={
        approval.actor_name
          ? t("decidedBy", { decision, name: approval.actor_name })
          : t("decidedByUnknown", { decision })
      }
    >
      <span className="grid gap-1">
        <time dateTime={approval.at} className="text-xs">
          {format.dateTime(new Date(approval.at), { dateStyle: "medium", timeStyle: "short" })}
        </time>
        {approval.comment && <q className="whitespace-pre-line">{approval.comment}</q>}
      </span>
    </Callout>
  );
}

function StageBody({
  entry,
  detail,
  shown,
  narrowed,
  waiting,
  reviewId,
  onShowReview,
}: {
  entry: StageOverview;
  detail: StageView;
  shown: VersionRef | undefined;
  narrowed: NarrowedOutput | null;
  /** The version under review is not in the stage detail yet. */
  waiting: boolean;
  reviewId: string | null;
  onShowReview: () => void;
}) {
  const t = useTranslations("studioRun.stage");
  const { view } = useRunPage();
  const stage = entry.stage;

  if (detail.query.isPending) {
    return <StagePanelSkeleton label={t("loading")} />;
  }
  if (detail.query.isError && !detail.detail) {
    return (
      <StageLoadError error={detail.query.error} onRetry={() => void detail.query.refetch()} />
    );
  }

  const attempt = detail.currentAttempt;
  if (!attempt) {
    if (entry.status === "running") {
      return <StageRunning stage={stage} />;
    }
    if (entry.status === "failed") {
      return <StageFailed stage={stage} error={entry.latest?.error ?? null} />;
    }
    if (entry.status === "cancelled") {
      return <StageEmpty stage={stage} kind="cancelled" />;
    }
    return (
      <StageEmpty stage={stage} kind={entry.status === "skipped" ? "skipped" : "notStarted"} />
    );
  }

  // A finished run's open attempt took the run's outcome (see buildTimeline).
  const working = !view.finished && (attempt.status === "running" || attempt.status === "pending");
  const failed = attempt.status === "failed" || (entry.status === "failed" && !working);

  if (!shown || !narrowed) {
    if (waiting) {
      return <StagePanelSkeleton label={t("loadingVersion")} />;
    }
    if (working) {
      return <StageRunning stage={stage} />;
    }
    if (failed) {
      return <StageFailed stage={stage} error={attempt.error ?? entry.latest?.error ?? null} />;
    }
    if (attempt.status === "cancelled" || entry.status === "cancelled") {
      return <StageEmpty stage={stage} kind="cancelled" />;
    }
    return <StageEmpty stage={stage} kind="noOutput" />;
  }

  const newer = shown.attempt.id !== attempt.id;
  return (
    <>
      {reviewId && shown.output.id !== reviewId && (
        <Callout
          tone="warning"
          icon={EyeIcon}
          title={t("viewingOlder", {
            version: shown.output.version,
            reviewVersion: view.awaiting?.output.version ?? 0,
          })}
          action={
            <button type="button" className={SMALL_BUTTON} onClick={onShowReview}>
              {t("showReviewed")}
            </button>
          }
        />
      )}
      {newer && working && (
        <Callout
          tone="info"
          icon={EyeIcon}
          live
          role="status"
          title={t("attemptRunning", { attempt: attempt.attempt })}
        />
      )}
      {newer && failed && (
        <Callout
          tone="danger"
          icon={TriangleAlertIcon}
          title={t("attemptFailed", { attempt: attempt.attempt })}
          action={<RetryFromHere stage={stage} className="h-8 px-2.5 text-xs" />}
        >
          {attempt.error ? <ErrorText value={attempt.error} /> : null}
        </Callout>
      )}
      {shown.attempt.status === "invalidated" && (
        <Callout tone="neutral" icon={CircleSlashIcon} title={t("invalidatedTitle")}>
          {t("invalidatedDescription")}
        </Callout>
      )}
      {shown.output.degraded && !isDemoOutput(shown.output) && (
        <DegradedNote reason={shown.output.degraded_reason} />
      )}
      <StageOutput narrowed={narrowed} shown={shown} detail={detail} />
    </>
  );
}

function ErrorText({ value }: { value: string }) {
  const labels = useRunLabels();
  return <>{labels.errorText(value)}</>;
}

function DegradedNote({ reason }: { reason: string | null }) {
  const t = useTranslations("run.approval");
  const labels = useRunLabels();
  return (
    <Callout tone="warning" icon={TriangleAlertIcon} title={t("degradedTitle")}>
      <span className="grid gap-1">
        <span>{t("degradedDescription")}</span>
        {reason && (
          <span>
            {t("degradedReason")} {labels.degradedReason(reason)}
          </span>
        )}
      </span>
    </Callout>
  );
}

function StageOutput({
  narrowed,
  shown,
  detail,
}: {
  narrowed: NarrowedOutput;
  shown: VersionRef;
  detail: StageView;
}) {
  switch (narrowed.kind) {
    case "literature":
      return <LiteratureView data={narrowed.data} />;
    case "method":
      return <MethodView data={narrowed.data} />;
    case "coding": {
      // Only the version the hook selected has its diff base worked out.
      const base =
        detail.selected?.output.id === shown.output.id &&
        detail.previous &&
        detail.previousNarrowed?.kind === "coding"
          ? ({
              data: detail.previousNarrowed.data,
              relation: detail.previous.relation,
              attempt: detail.previous.attempt.attempt,
              version: detail.previous.output.version,
            } satisfies CodingBase)
          : null;
      return <CodingView data={narrowed.data} outputId={shown.output.id} previous={base} />;
    }
    case "experiment":
      return <ExperimentView data={narrowed.data} outputId={shown.output.id} />;
    case "writing":
      return <WritingView data={narrowed.data} outputId={shown.output.id} />;
    case "raw":
      return <RawOutputView narrowed={narrowed} />;
  }
}

/** Output that is not its stage's shape (or a stage this interface does not know), as JSON. */
function RawOutputView({ narrowed }: { narrowed: RawOutput }) {
  const t = useTranslations("studioRun.stage");
  return (
    <ViewCard
      title={t("rawTitle")}
      icon={<BracesIcon aria-hidden />}
      description={
        <span className="flex items-start gap-1.5">
          <FileWarningIcon
            aria-hidden
            className="mt-px size-3.5 shrink-0 text-(--studio-warning-fg)"
          />
          {t(`rawReasons.${narrowed.reason}`)}
        </span>
      }
    >
      <JsonView value={narrowed.data} label={t("rawLabel")} />
    </ViewCard>
  );
}
