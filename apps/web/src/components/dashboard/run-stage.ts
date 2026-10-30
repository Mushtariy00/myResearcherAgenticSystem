"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef } from "react";
import type { RunDetail, RunOut } from "@/client";
import { getRunOptions } from "@/client/@tanstack/react-query.gen";
import { isKnownStage } from "@/lib/labels";
import { isPageVisible, pollWhileVisible } from "@/lib/polling";
import { buildTimeline, isTerminalRunStatus } from "@/lib/timeline";

/** How often the stage of a run in progress is refreshed while the page is visible. */
const STAGE_POLL_MS = 30_000;

/** The stage a run is working on or waiting for a decision on; null when queued or finished. */
export function currentStageOf(run: RunDetail): string | null {
  if (isTerminalRunStatus(run.status)) {
    return null;
  }
  if (run.awaiting_stage) {
    return run.awaiting_stage;
  }
  return (
    buildTimeline(run.config.stages, run.stages, run.status).find((entry) => entry.current)
      ?.stage ?? null
  );
}

/**
 * The current stage of a listed run. Run lists carry no stage, so it comes from the run's detail
 * (the run page's cache entry), asked only for runs still in progress: a finished run has no
 * current stage, and its detail, with every stage output, is a large download.
 */
export function useCurrentStage(run: Pick<RunOut, "id" | "status">): {
  stage: string | null;
  loading: boolean;
} {
  const active = !isTerminalRunStatus(run.status);
  const query = useQuery({
    ...getRunOptions({ path: { run_id: run.id } }),
    enabled: active,
    staleTime: 15_000,
    ...pollWhileVisible(STAGE_POLL_MS),
    select: currentStageOf,
  });
  return { stage: active ? (query.data ?? null) : null, loading: active && query.isPending };
}

/** A stage id from the API in the UI language (unknown stages as they are). */
export function useStageName(): (stage: string) => string {
  const t = useTranslations("stages");
  return useCallback((stage: string) => (isKnownStage(stage) ? t(stage) : stage), [t]);
}

/**
 * Calls `refetch` every `intervalMs` while `active` and the page is visible: for lists whose
 * shared hook does not poll (useRecentRuns), so statuses on the dashboard do not go stale.
 */
export function useRefetchWhile(active: boolean, refetch: () => unknown, intervalMs: number): void {
  const latest = useRef(refetch);
  useEffect(() => {
    latest.current = refetch;
  });
  useEffect(() => {
    if (!active) {
      return;
    }
    const timer = window.setInterval(() => {
      if (isPageVisible()) {
        void latest.current();
      }
    }, intervalMs);
    return () => window.clearInterval(timer);
  }, [active, intervalMs]);
}
