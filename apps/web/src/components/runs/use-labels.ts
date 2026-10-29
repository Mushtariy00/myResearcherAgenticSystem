"use client";

import { useTranslations } from "next-intl";
import { useCallback } from "react";
import { isKnownDegradedReason, runErrorKey } from "@/lib/api-error";
import { isDecision, isKnownStage, isLlmTier, isRunStatus } from "@/lib/labels";

/** Translated names for values that arrive as data (stage ids, statuses, codes). */
export function useLabels() {
  const t = useTranslations();
  const stage = useCallback(
    (value: string) => (isKnownStage(value) ? t(`stages.${value}`) : value),
    [t],
  );
  const runStatus = useCallback(
    (value: string) => (isRunStatus(value) ? t(`runStatus.${value}`) : value),
    [t],
  );
  const decision = useCallback(
    (value: string) => (isDecision(value) ? t(`decisions.${value}`) : value),
    [t],
  );
  const tier = useCallback(
    (value: string) => (isLlmTier(value) ? t(`tiers.${value}`) : value),
    [t],
  );
  /** Error codes stored on runs, stages and events (e.g. `stage.error`); other text as is. */
  const errorText = useCallback(
    (value: string) => {
      const key = runErrorKey(value);
      return key ? t(`errors.${key}`) : value;
    },
    [t],
  );
  /** Why an output is degraded (e.g. `stage.placeholder`); unknown reasons as is. */
  const degradedReason = useCallback(
    (value: string) => (isKnownDegradedReason(value) ? t(`degradedReasons.${value}`) : value),
    [t],
  );
  return { stage, runStatus, decision, tier, errorText, degradedReason };
}
