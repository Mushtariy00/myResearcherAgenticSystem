"use client";

import { type UseQueryResult, useQuery } from "@tanstack/react-query";
import { useCallback, useMemo, useState } from "react";
import type { GetStageError, StageAttemptOut, StageDetail, StageStatus } from "@/client";
import { getStageOptions } from "@/client/@tanstack/react-query.gen";
import { RUN_POLL_MS } from "@/hooks/use-run-view";
import {
  type DiffBase,
  findVersion,
  isDemoOutput,
  latestAttempt,
  latestOutput,
  type NarrowedOutput,
  outputAs,
  previousOutput,
  type StageSummary,
  sortedAttempts,
  stageVersions,
  summarize,
  type VersionRef,
} from "@/lib/stage-output";

/** Attempt statuses that can still change (so the detail is polled while the stream is down). */
const LIVE_STATUSES = new Set<StageStatus>(["pending", "running", "output_ready"]);

export type UseStageOptions = {
  /**
   * Show this version instead of following the newest one, such as the output under review
   * (`run.awaiting.id`). Overrides `select()`; null follows the newest version.
   */
  outputId?: string | null;
};

export type StageView = {
  /** The stage detail query: pending and error states, `refetch`. Disabled without a stage. */
  query: UseQueryResult<StageDetail, GetStageError>;
  detail: StageDetail | undefined;
  /** Attempts, oldest first. */
  attempts: StageAttemptOut[];
  /** The newest attempt; it may still be running and have no output yet. */
  currentAttempt: StageAttemptOut | undefined;
  /** Every version of every attempt, oldest first. */
  versions: VersionRef[];
  /** The newest version of the newest attempt that has one. */
  current: VersionRef | undefined;
  /**
   * The version on screen: `options.outputId`, else the one picked with `select`, else
   * `current`. Undefined while an asked-for id is not (yet) in the detail.
   */
  selected: VersionRef | undefined;
  /** No version was asked for, so `selected` follows the newest one. */
  followingLatest: boolean;
  /** Picks a version by output id; null follows the newest again. */
  select: (outputId: string | null) => void;
  /** What `selected` is compared with in a diff (the version or attempt before it). */
  previous: DiffBase | undefined;
  /** `selected`'s data with its stage's type, or raw JSON (see `outputAs`). */
  narrowed: NarrowedOutput | null;
  previousNarrowed: NarrowedOutput | null;
  summary: StageSummary | null;
  /** `selected` is generated demo data: show the Demo badge. */
  isDemo: boolean;
  /** The newest attempt is pending, running or waiting for a decision. */
  live: boolean;
};

type VersionPick = { key: string; outputId: string | null };

/**
 * One stage of a run (`GET /runs/{id}/stages/{stage}`): every attempt with its versions and
 * decisions, the version on screen narrowed to the stage's type, and its diff base.
 *
 * It refetches when the stage's events arrive through `useRunView` on the same page, and polls
 * every RUN_POLL_MS while the stage is live in case the stream is down. A null or empty `stage`
 * disables the query.
 */
export function useStage(
  runId: string,
  stage: string | null | undefined,
  options: UseStageOptions = {},
): StageView {
  const stageId = stage ?? "";
  const query = useQuery({
    ...getStageOptions({ path: { run_id: runId, stage: stageId } }),
    enabled: stageId.length > 0,
    refetchInterval: (current) => {
      const attempt = latestAttempt(current.state.data);
      return attempt && LIVE_STATUSES.has(attempt.status) ? RUN_POLL_MS : false;
    },
  });
  const detail = query.data;

  // A pick belongs to one run and stage; moving to another stage follows its newest version.
  const pickKey = `${runId}/${stageId}`;
  const [picked, setPicked] = useState<VersionPick>({ key: pickKey, outputId: null });
  const select = useCallback(
    (outputId: string | null) => setPicked({ key: pickKey, outputId }),
    [pickKey],
  );
  const pickedId = picked.key === pickKey ? picked.outputId : null;
  const wantedId = options.outputId !== undefined ? options.outputId : pickedId;

  const structure = useMemo(() => {
    const attempts = sortedAttempts(detail);
    return {
      attempts,
      currentAttempt: attempts.at(-1),
      versions: stageVersions(detail),
      current: latestOutput(detail),
    };
  }, [detail]);

  const selected = useMemo(
    () => (wantedId ? findVersion(detail, wantedId) : structure.current),
    [detail, wantedId, structure],
  );

  const shown = useMemo(() => {
    const previous = selected ? previousOutput(detail, selected.output.id) : undefined;
    const narrowed = selected ? outputAs(stageId, selected.output) : null;
    return {
      previous,
      narrowed,
      previousNarrowed: previous ? outputAs(stageId, previous.output) : null,
      summary: narrowed ? summarize(narrowed) : null,
    };
  }, [detail, selected, stageId]);

  const attempt = structure.currentAttempt;
  return {
    query,
    detail,
    ...structure,
    selected,
    followingLatest: !wantedId,
    select,
    ...shown,
    isDemo: isDemoOutput(selected?.output),
    live: attempt !== undefined && LIVE_STATUSES.has(attempt.status),
  };
}
