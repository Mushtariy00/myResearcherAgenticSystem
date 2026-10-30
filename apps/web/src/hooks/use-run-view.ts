"use client";

import {
  type QueryClient,
  type QueryKey,
  type UseQueryResult,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { GetRunError, RunDetail, Stage, StageOutputOut } from "@/client";
import {
  getGpuQueueQueryKey,
  getRunOptions,
  getRunQueryKey,
  getStageQueryKey,
  listNotificationsQueryKey,
  listRecentRunsQueryKey,
  listRunArtifactsQueryKey,
  listRunsQueryKey,
  listStagesOptions,
} from "@/client/@tanstack/react-query.gen";
import { type StreamState, useRunEvents } from "@/hooks/use-run-events";
import { toApiError } from "@/lib/api-error";
import {
  mergeEvents,
  type RunEvent,
  type RunSpend,
  type StageWait,
  stageDetailChanges,
  stageWaits,
  summarizeSpend,
  withRunTotal,
} from "@/lib/run-events";
import { type StageOverview, stageOverviews } from "@/lib/stage-output";
import { buildTimeline, isTerminalRunStatus, retryableStages, STAGE_ORDER } from "@/lib/timeline";

/** How often the run detail (and a live stage's detail) is polled in case the stream is down. */
export const RUN_POLL_MS = 20_000;

/** How long to gather stage events before refetching the stage details they changed. */
const STAGE_REFRESH_DELAY_MS = 300;

/** The output waiting for a decision. */
export type AwaitingReview = {
  stage: string;
  /** Decisions must name this output's id and sha256. */
  output: StageOutputOut;
};

export type RunView = {
  /** The run detail query: pending and error states, `refetch`. */
  query: UseQueryResult<RunDetail, GetRunError>;
  run: RunDetail | undefined;
  /** Stage ids in pipeline order (`GET /stages`; the built-in order until it loads). */
  stageOrder: readonly string[];
  /** One entry per stage, in order, with its newest output, summary and demo flag. */
  timeline: StageOverview[];
  /** Live events, oldest first (the newest MAX_EVENTS). */
  events: readonly RunEvent[];
  streamState: StreamState;
  /** Opens the event stream again after it gave up (`streamState === "error"`). */
  reconnect: () => void;
  awaiting: AwaitingReview | null;
  /** The user may approve, request changes, reject, cancel and retry (`run.can_steer`). */
  canSteer: boolean;
  /** An output waits and the user may decide on it. */
  canDecide: boolean;
  /** The user may cancel and the run has not finished. */
  canCancel: boolean;
  /** Completed, rejected, failed or cancelled. */
  finished: boolean;
  /** Stages a retry may restart from, in pipeline order; empty unless the user may steer. */
  retryableStages: readonly Stage[];
  /**
   * LLM spend so far: the total from the run detail (`spend_usd`, refetched after every call),
   * the breakdown by stage and tier from the run's `llm.call` events.
   */
  spend: RunSpend;
  /** Stages whose attempt waits and then runs again by itself (`stage.waiting`), by stage id. */
  waits: Readonly<Record<string, StageWait>>;
  /** Refetches the run and everything on screen that shows it. */
  refresh: () => void;
};

/**
 * Everything a run page shows: the run detail, its live events (one EventSource for the page),
 * the stage timeline, the flags that decide which actions to offer, and the live spend.
 *
 * The event stream also keeps the rest of the page fresh: stage events refetch the details of
 * the stages they name (`useStage`) and the run's artifacts (`useRunArtifacts`).
 *
 * Mount it once per run page and key that component by run id (`<RunPage key={runId} />`):
 * the event stream (use-run-events) keeps its events when `runId` changes.
 */
export function useRunView(runId: string): RunView {
  const queryClient = useQueryClient();
  const query = useQuery({
    ...getRunOptions({ path: { run_id: runId } }),
    // Live events trigger refetches; this is the fallback while the stream is down.
    refetchInterval: (current) =>
      isTerminalRunStatus(current.state.data?.status) ? false : RUN_POLL_MS,
  });
  const stages = useQuery({ ...listStagesOptions(), staleTime: Number.POSITIVE_INFINITY });

  const refreshDetail = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: getRunQueryKey({ path: { run_id: runId } }) });
  }, [queryClient, runId]);
  // Before the stream opens again: is the session still valid and the run still there?
  const canResume = useCallback(async () => {
    try {
      await queryClient.fetchQuery({
        ...getRunOptions({ path: { run_id: runId } }),
        staleTime: 0,
        retry: false,
      });
      return true;
    } catch (error) {
      const status = toApiError(error).status;
      return status !== 401 && status !== 403 && status !== 404;
    }
  }, [queryClient, runId]);
  const stream = useRunEvents(runId, refreshDetail, canResume);
  useStageRefresh(runId, stream.events);
  const loggedSpend = useRunSpend(runId, stream.events);

  const stageOrder = useMemo(
    () =>
      stages.data
        ? [...stages.data].sort((a, b) => a.position - b.position).map((stage) => stage.id)
        : [...STAGE_ORDER],
    [stages.data],
  );
  const run = query.data;
  const timeline = useMemo(
    () => (run ? stageOverviews(buildTimeline(stageOrder, run.stages, run.status)) : []),
    [run, stageOrder],
  );
  const awaiting = useMemo(
    () => (run?.awaiting ? { stage: run.awaiting_stage ?? "", output: run.awaiting } : null),
    [run],
  );
  const canSteer = run?.can_steer === true;
  const finished = isTerminalRunStatus(run?.status);
  const retryable = useMemo(() => (run && canSteer ? retryableStages(run) : []), [run, canSteer]);
  const spendUsd = run?.spend_usd;
  const spend = useMemo(() => withRunTotal(loggedSpend, spendUsd), [loggedSpend, spendUsd]);
  const waits = useMemo(
    () => (finished ? NO_WAITS : stageWaits(stream.events)),
    [finished, stream.events],
  );
  const refresh = useCallback(() => {
    void invalidateRunQueries(queryClient, runId);
  }, [queryClient, runId]);

  return {
    query,
    run,
    stageOrder,
    timeline,
    events: stream.events,
    streamState: stream.state,
    reconnect: stream.reconnect,
    awaiting,
    canSteer,
    canDecide: canSteer && awaiting !== null,
    canCancel: canSteer && run !== undefined && !finished,
    finished,
    retryableStages: retryable,
    spend,
    waits,
    refresh,
  };
}

const NO_WAITS: Readonly<Record<string, StageWait>> = {};

/** A partial key matching every query of one generated operation (TanStack matches partially). */
function everyQueryOf(key: readonly [{ _id: string }], path?: Record<string, string>): QueryKey {
  return [path ? { _id: key[0]._id, path } : { _id: key[0]._id }];
}

/** Every stage detail query of one run. */
function stageQueries(runId: string): QueryKey {
  return everyQueryOf(getStageQueryKey({ path: { run_id: runId, stage: "" } }), {
    run_id: runId,
  });
}

/**
 * Marks everything that shows a run stale, so what is on screen refetches (the rest when it is
 * next used): the run detail, its stage details and artifacts, the run lists, the dashboard and
 * notifications, and with `gpu` the GPU queue. Resolves once the run detail is fresh.
 */
export async function invalidateRunQueries(
  queryClient: QueryClient,
  runId: string,
  options: { gpu?: boolean } = {},
): Promise<void> {
  const related: QueryKey[] = [
    stageQueries(runId),
    listRunArtifactsQueryKey({ path: { run_id: runId } }),
    everyQueryOf(listRunsQueryKey({ path: { project_id: "" } })),
    everyQueryOf(listRecentRunsQueryKey()),
    everyQueryOf(listNotificationsQueryKey()),
  ];
  if (options.gpu) {
    related.push(everyQueryOf(getGpuQueueQueryKey()));
  }
  for (const queryKey of related) {
    void queryClient.invalidateQueries({ queryKey });
  }
  await queryClient.invalidateQueries({ queryKey: getRunQueryKey({ path: { run_id: runId } }) });
}

type PendingRefresh = { stages: Set<string>; all: boolean };

/**
 * Refetches the stage details (and the run's artifacts) that new events changed. Like the run
 * detail refresh in use-run-events, the first change schedules one refresh and later changes
 * join it, so a replay of a long log refetches each stage once.
 */
function useStageRefresh(runId: string, events: readonly RunEvent[]): void {
  const queryClient = useQueryClient();
  const seen = useRef({ runId, seq: 0 });
  const pending = useRef<PendingRefresh>({ stages: new Set(), all: false });
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (seen.current.runId !== runId) {
      seen.current = { runId, seq: 0 };
      pending.current = { stages: new Set(), all: false };
      if (timer.current !== null) {
        clearTimeout(timer.current);
        timer.current = null;
      }
    }
    const changes = stageDetailChanges(events, seen.current.seq);
    seen.current.seq = changes.lastSeq;
    for (const stage of changes.stages) {
      pending.current.stages.add(stage);
    }
    pending.current.all ||= changes.all;
    if (timer.current !== null || (!pending.current.all && pending.current.stages.size === 0)) {
      return;
    }
    timer.current = setTimeout(() => {
      timer.current = null;
      const { stages, all } = pending.current;
      pending.current = { stages: new Set(), all: false };
      const keys: QueryKey[] = all
        ? [stageQueries(runId)]
        : [...stages].map((stage) => getStageQueryKey({ path: { run_id: runId, stage } }));
      keys.push(listRunArtifactsQueryKey({ path: { run_id: runId } }));
      for (const queryKey of keys) {
        void queryClient.invalidateQueries({ queryKey });
      }
    }, STAGE_REFRESH_DELAY_MS);
  }, [events, queryClient, runId]);

  useEffect(
    () => () => {
      if (timer.current !== null) {
        clearTimeout(timer.current);
        timer.current = null;
      }
    },
    [],
  );
}

type SpendCalls = { runId: string; from: readonly RunEvent[]; calls: readonly RunEvent[] };

const NO_EVENTS: readonly RunEvent[] = [];

function llmCalls(events: readonly RunEvent[]): RunEvent[] {
  return events.filter((event) => event.type === "llm.call");
}

/**
 * The spend of every `llm.call` event seen since mount. The calls are kept apart from the event
 * log, which drops its oldest events beyond MAX_EVENTS, so the total never shrinks.
 */
function useRunSpend(runId: string, events: readonly RunEvent[]): RunSpend {
  const [stored, setStored] = useState<SpendCalls>(() => ({
    runId,
    from: events,
    calls: llmCalls(events),
  }));
  let current = stored;
  if (stored.from !== events || stored.runId !== runId) {
    // Adjusts state while rendering (react.dev: "Storing information from previous renders").
    current = {
      runId,
      from: events,
      calls: mergeEvents(
        stored.runId === runId ? stored.calls : NO_EVENTS,
        llmCalls(events),
        Number.POSITIVE_INFINITY,
      ),
    };
    setStored(current);
  }
  const calls = current.calls;
  return useMemo(() => summarizeSpend(calls), [calls]);
}
