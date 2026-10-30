"use client";

import { HourglassIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useStageWaitText } from "@/components/shared/wait-text";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import type { StageWait } from "@/lib/run-events";
import { useLabels } from "./use-labels";

/** A stage attempt that waits and then runs again by itself: why, and when (`stage.waiting`). */
export function StageWaitAlert({ wait }: { wait: StageWait | undefined }) {
  const t = useTranslations("run.waiting");
  const labels = useLabels();
  const text = useStageWaitText(wait);
  if (!wait || !text) {
    return null;
  }
  return (
    <Alert role="status" className="border-amber-500/40">
      <HourglassIcon aria-hidden />
      <AlertTitle>{t("title", { stage: labels.stage(wait.stage) })}</AlertTitle>
      <AlertDescription>
        {text.retry ? `${text.reason} ${text.retry}` : text.reason}
      </AlertDescription>
    </Alert>
  );
}

/** The same in one line under the stage in the timeline; the stage's tab says why. */
export function TimelineWait({ wait }: { wait: StageWait | undefined }) {
  const t = useTranslations("run.events.types.stage");
  const text = useStageWaitText(wait);
  if (!text) {
    return null;
  }
  return (
    <p className="flex items-start gap-1 text-xs text-amber-800 dark:text-amber-300">
      <HourglassIcon aria-hidden className="mt-0.5 size-3 shrink-0" />
      <span className="line-clamp-3 break-words">
        <span className="font-medium">{t("waiting")}</span> {text.retry ?? text.reason}
      </span>
    </p>
  );
}
