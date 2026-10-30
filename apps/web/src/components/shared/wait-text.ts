"use client";

import { useFormatter, useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";
import { isKnownWaitReason, type StageWait } from "@/lib/run-events";

/** When a waiting stage runs again: day and time, in the UI language and the app's time zone. */
const RETRY_FORMAT = {
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
} as const;

/** setTimeout's limit is about 24 days; far-off waits are re-checked every hour instead. */
const MAX_TIMER_MS = 60 * 60 * 1000;

export type WaitLabels = {
  /** Why a stage waits (`stage.waiting` reason codes, such as `free_quota.exhausted`). */
  reason: (code: string) => string;
  /** The day and time a wait ends. */
  time: (at: Date) => string;
  /** "It tries again by itself at <time>." */
  retryAt: (at: Date) => string;
};

/** Words for `stage.waiting` events, shared by both interfaces' logs. */
export function useWaitLabels(): WaitLabels {
  const t = useTranslations("run.waiting");
  const format = useFormatter();
  const reason = useCallback(
    (code: string) => (isKnownWaitReason(code) ? t(`reasons.${code}`) : t("unknownReason")),
    [t],
  );
  const time = useCallback((at: Date) => format.dateTime(at, RETRY_FORMAT), [format]);
  const retryAt = useCallback((at: Date) => t("retryAt", { time: time(at) }), [t, time]);
  return useMemo(() => ({ reason, time, retryAt }), [reason, time, retryAt]);
}

/**
 * A waiting stage as its page shows it: why it waits, and when it tries again by itself, which
 * turns into "trying again now" once that time has passed (the component renders again then).
 */
export function useStageWaitText(
  wait: StageWait | undefined,
): { reason: string; retry: string | null } | null {
  const t = useTranslations("run.waiting");
  const labels = useWaitLabels();
  const [now, setNow] = useState(() => Date.now());
  const retryTime = wait?.retryAt?.getTime() ?? null;

  useEffect(() => {
    if (retryTime === null || retryTime <= now) {
      return;
    }
    const delay = Math.min(Math.max(retryTime - Date.now(), 0), MAX_TIMER_MS);
    const timer = setTimeout(() => setNow(Date.now()), delay);
    return () => clearTimeout(timer);
  }, [retryTime, now]);

  if (!wait) {
    return null;
  }
  const retry =
    wait.retryAt === null
      ? null
      : wait.retryAt.getTime() <= now
        ? t("retryNow")
        : labels.retryAt(wait.retryAt);
  return { reason: labels.reason(wait.reason), retry };
}
