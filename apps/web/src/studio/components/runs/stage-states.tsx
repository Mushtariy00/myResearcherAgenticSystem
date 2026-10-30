"use client";

import {
  BanIcon,
  CircleDashedIcon,
  CircleMinusIcon,
  FileQuestionIcon,
  RotateCcwIcon,
  RotateCwIcon,
  TriangleAlertIcon,
} from "lucide-react";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";
import { useErrorMessage } from "@/hooks/use-error-message";
import { cn } from "@/lib/utils";
import { GlassCard } from "@/studio/components/effects/glass-card";
import { PulseDot } from "@/studio/components/effects/pulse-dot";
import { LoadingStatus, ShimmerSkeleton } from "@/studio/components/effects/shimmer-skeleton";
import { StudioStatePanel } from "@/studio/components/studio-state-panel";
import { stageAttr } from "@/studio/lib/stages";
import { OUTLINE_BUTTON } from "@/studio/lib/ui";
import { useEventDescriber } from "./event-lines";
import { useRunPage } from "./run-context";
import { useRunLabels } from "./use-run-labels";

/** Placeholder cards the size of a stage view while its detail loads. */
export function StagePanelSkeleton({ label }: { label: string }) {
  return (
    <div aria-busy="true" className="grid gap-4">
      <LoadingStatus label={label} />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <ShimmerSkeleton className="h-44 rounded-2xl" />
        <ShimmerSkeleton className="h-44 rounded-2xl" />
      </div>
      <ShimmerSkeleton className="h-72 rounded-2xl" />
    </div>
  );
}

/** A stage the run has not reached (yet), or one that ended without an output. */
export function StageEmpty({
  stage,
  kind,
}: {
  stage: string;
  kind: "notStarted" | "skipped" | "cancelled" | "noOutput";
}) {
  const t = useTranslations("studioRun.stage");
  const { view } = useRunPage();
  const labels = useRunLabels();
  const name = labels.stage(stage);
  const index = view.timeline.findIndex((entry) => entry.stage === stage);
  const previous = index > 0 ? view.timeline[index - 1] : undefined;

  if (kind === "notStarted") {
    return (
      <StudioStatePanel
        variant="section"
        headingLevel={4}
        tone="neutral"
        icon={<CircleDashedIcon aria-hidden />}
        title={t("notStarted", { stage: name })}
        description={
          previous
            ? t("notStartedAfter", { previous: labels.stage(previous.stage) })
            : t("notStartedFirst")
        }
      />
    );
  }
  if (kind === "skipped") {
    return (
      <StudioStatePanel
        variant="section"
        headingLevel={4}
        tone="neutral"
        icon={<CircleMinusIcon aria-hidden />}
        title={t("skipped", { stage: name })}
        description={t("skippedDescription")}
      />
    );
  }
  if (kind === "cancelled") {
    return (
      <StudioStatePanel
        variant="section"
        headingLevel={4}
        tone="neutral"
        icon={<BanIcon aria-hidden />}
        title={t("cancelled", { stage: name })}
        description={t("cancelledDescription")}
      >
        <RetryFromHere stage={stage} />
      </StudioStatePanel>
    );
  }
  return (
    <StudioStatePanel
      variant="section"
      headingLevel={4}
      tone="neutral"
      icon={<FileQuestionIcon aria-hidden />}
      title={t("noOutput")}
      description={t("noOutputDescription")}
    />
  );
}

/**
 * A stage at work with nothing to show yet: a pulsing title, its newest progress line from the
 * live log, and placeholders where the output will appear.
 */
export function StageRunning({ stage }: { stage: string }) {
  const t = useTranslations("studioRun.stage");
  const { view } = useRunPage();
  const labels = useRunLabels();
  const describe = useEventDescriber();
  const latest = view.events.findLast(
    (event) =>
      event.payload.stage === stage && (event.type === "log" || event.type === "stage.started"),
  );
  return (
    <GlassCard
      data-stage={stageAttr(stage)}
      aria-busy="true"
      className="relative grid gap-4 overflow-hidden p-5 sm:p-6"
    >
      <div className="flex items-center gap-3">
        <PulseDot stage={stageAttr(stage)} live size="lg" />
        <h4 className="text-base font-semibold tracking-tight text-foreground">
          {t("running", { stage: labels.stage(stage) })}
        </h4>
      </div>
      <p className="text-sm text-muted-foreground">{t("runningDescription")}</p>
      {latest && (
        <p className="flex min-w-0 items-baseline gap-2 font-mono text-xs text-foreground">
          <span className="shrink-0 text-(--tone-fg)">{t("latestStep")}</span>
          <span className="min-w-0 break-words">{describe(latest).text}</span>
        </p>
      )}
      <div aria-hidden className="grid gap-2.5 pt-1">
        <ShimmerSkeleton className="h-3.5 w-11/12" />
        <ShimmerSkeleton className="h-3.5 w-4/5" />
        <ShimmerSkeleton className="h-3.5 w-2/3" />
      </div>
    </GlassCard>
  );
}

/** A stage that stopped without an output: the error it reported and, when allowed, a retry. */
export function StageFailed({ stage, error }: { stage: string; error: string | null }) {
  const t = useTranslations("studioRun.stage");
  const labels = useRunLabels();
  return (
    <StudioStatePanel
      variant="section"
      headingLevel={4}
      tone="danger"
      icon={<TriangleAlertIcon aria-hidden />}
      title={t("failed", { stage: labels.stage(stage) })}
      description={error ? labels.errorText(error) : t("failedDescription")}
    >
      <RetryFromHere stage={stage} />
    </StudioStatePanel>
  );
}

/** The stage detail could not be loaded: why, and a way to try again. */
export function StageLoadError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const t = useTranslations("studioRun.stage");
  const tCommon = useTranslations("common");
  const errorMessage = useErrorMessage();
  return (
    <StudioStatePanel
      variant="section"
      headingLevel={4}
      tone="danger"
      icon={<TriangleAlertIcon aria-hidden />}
      title={t("loadFailed")}
      description={errorMessage(error)}
    >
      <button type="button" onClick={onRetry} className={OUTLINE_BUTTON}>
        <RotateCwIcon aria-hidden />
        {tCommon("retry")}
      </button>
    </StudioStatePanel>
  );
}

/** "Retry from this stage", for a finished run whose retry the visitor may start. */
export function RetryFromHere({
  stage,
  className,
}: {
  stage: string;
  className?: string;
}): ReactNode {
  const t = useTranslations("studioRun.retry");
  const { view, openRetry } = useRunPage();
  if (!view.finished || !(view.retryableStages as readonly string[]).includes(stage)) {
    return null;
  }
  return (
    <button
      type="button"
      aria-haspopup="dialog"
      onClick={() => openRetry(stage)}
      className={cn(OUTLINE_BUTTON, className)}
    >
      <RotateCcwIcon aria-hidden />
      {t("fromHere")}
    </button>
  );
}
