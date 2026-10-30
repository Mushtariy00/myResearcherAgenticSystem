"use client";

import { useTranslations } from "next-intl";
import { useMemo } from "react";
import { isKnownDegradedReason, runErrorKey } from "@/lib/api-error";
import { isDecision, isKnownStage, isLlmTier, isRunStatus } from "@/lib/labels";

export type RunLabels = {
  stage: (value: string) => string;
  runStatus: (value: string) => string;
  decision: (value: string) => string;
  tier: (value: string) => string;
  /** Error codes stored on runs, stages and events (`stage.error`); other text as it is. */
  errorText: (value: string) => string;
  /** Why an output is degraded (`stage.placeholder`); unknown reasons as they are. */
  degradedReason: (value: string) => string;
};

/**
 * Translated names for values that arrive as data (stage ids, statuses, decisions, codes),
 * from the shared namespaces. Values this interface does not know are shown as they are.
 */
export function useRunLabels(): RunLabels {
  const t = useTranslations();
  return useMemo(
    () => ({
      stage: (value) => (isKnownStage(value) ? t(`stages.${value}`) : value),
      runStatus: (value) => (isRunStatus(value) ? t(`runStatus.${value}`) : value),
      decision: (value) => (isDecision(value) ? t(`decisions.${value}`) : value),
      tier: (value) => (isLlmTier(value) ? t(`tiers.${value}`) : value),
      errorText: (value) => {
        const key = runErrorKey(value);
        return key ? t(`errors.${key}`) : value;
      },
      degradedReason: (value) =>
        isKnownDegradedReason(value) ? t(`degradedReasons.${value}`) : value,
    }),
    [t],
  );
}
