// @vitest-environment jsdom
import { act, cleanup, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { RunDetail, StageInfo } from "@/client";
import { MAX_EVENTS } from "@/lib/run-events";
import {
  DEMO_LITERATURE,
  runDetailOut,
  stageDetailOut,
  stageOutputOut,
  stageRunOut,
} from "@/lib/stage-output.fixtures";
import { STAGE_ORDER } from "@/lib/timeline";
import {
  FakeEventSource,
  installEventSource,
  json,
  mockApi,
  renderWithQuery,
  requestsOf,
  runEvent,
} from "./run-hooks.fixtures";
import { useRunArtifacts } from "./use-run-artifacts";
import { useRunView } from "./use-run-view";
import { useStage } from "./use-stage";

const awaitingOutput = stageOutputOut(DEMO_LITERATURE, {
  degraded_reason: "literature.demo_search",
});
const awaitingRun: RunDetail = runDetailOut({
  status: "awaiting_approval",
  stages: [stageRunOut("literature", "output_ready", { outputs: [awaitingOutput] })],
  awaiting: awaitingOutput,
  awaiting_stage: "literature",
});
const RUN_ID = awaitingRun.id;
const STAGES: StageInfo[] = STAGE_ORDER.map((id, position) => ({
  id,
  position,
  auto_approvable: id !== "coding",
}));

let currentRun: RunDetail = awaitingRun;
let fetchMock: ReturnType<typeof mockApi>;

beforeEach(() => {
  currentRun = awaitingRun;
  installEventSource();
  fetchMock = mockApi((_request, path) => {
    if (path === `/api/v1/runs/${RUN_ID}`) {
      return json(200, currentRun);
    }
    if (path === "/api/v1/stages") {
      return json(200, STAGES);
    }
    if (path === `/api/v1/runs/${RUN_ID}/artifacts`) {
      return json(200, { run_id: RUN_ID, items: [], demo: false });
    }
    const stage = path.match(/\/stages\/([a-z]+)$/)?.[1];
    if (stage) {
      return json(200, stageDetailOut(RUN_ID, stage, []));
    }
    return json(404, { detail: "run.not_found" });
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const count = (request: string) => requestsOf(fetchMock).filter((r) => r === request).length;

describe("useRunView", () => {
  it("loads the run and derives the timeline and the actions to offer", async () => {
    const { result } = renderWithQuery(() => useRunView(RUN_ID));
    await waitFor(() => expect(result.current.run).toBeDefined());
    const view = result.current;

    expect(view.timeline.map((entry) => [entry.stage, entry.status])).toEqual([
      ["literature", "output_ready"],
      ["method", "pending"],
      ["coding", "pending"],
      ["experiment", "pending"],
      ["writing", "pending"],
    ]);
    expect(view.timeline[0]).toMatchObject({
      current: true,
      demo: true,
      summary: { kind: "literature", papersIncluded: 3, papersTotal: 5 },
    });
    expect(view.awaiting).toEqual({ stage: "literature", output: awaitingOutput });
    expect(view).toMatchObject({
      canSteer: true,
      canDecide: true,
      canCancel: true,
      finished: false,
      retryableStages: [],
      streamState: "connecting",
    });
    expect(FakeEventSource.latest().url).toBe(`/api/v1/runs/${RUN_ID}/events?after=0`);
  });

  it("offers retries of a finished run's stages, and no cancel", async () => {
    currentRun = runDetailOut({
      status: "failed",
      error: "stage.error",
      stages: [stageRunOut("literature", "approved"), stageRunOut("method", "failed")],
    });
    const { result } = renderWithQuery(() => useRunView(RUN_ID));
    await waitFor(() => expect(result.current.run).toBeDefined());
    expect(result.current).toMatchObject({
      finished: true,
      canCancel: false,
      canDecide: false,
      awaiting: null,
      retryableStages: ["literature", "method"],
    });
  });

  it("offers nothing to people who may only look", async () => {
    currentRun = { ...awaitingRun, can_steer: false };
    const { result } = renderWithQuery(() => useRunView(RUN_ID));
    await waitFor(() => expect(result.current.run).toBeDefined());
    expect(result.current).toMatchObject({ canSteer: false, canDecide: false, canCancel: false });
    expect(result.current.awaiting?.stage).toBe("literature");
  });

  it("sums the live spend from llm.call events", async () => {
    const { result } = renderWithQuery(() => useRunView(RUN_ID));
    const source = FakeEventSource.latest();
    act(() => {
      source.open();
      source.send(
        runEvent("llm.call", { stage: "literature", tier: "paid", cost_usd: "0.0125" }),
        runEvent("llm.call", { stage: "literature", tier: "free", cost_usd: "0" }),
      );
    });
    await waitFor(() => expect(result.current.spend.calls).toBe(2));
    expect(result.current.spend).toMatchObject({ totalUsd: 0.0125, paidCalls: 1, freeCalls: 1 });
    expect(result.current.streamState).toBe("live");
    expect(result.current.events).toHaveLength(2);
  });

  it("keeps the spend of calls the event log has already dropped", async () => {
    const { result } = renderWithQuery(() => useRunView(RUN_ID));
    const source = FakeEventSource.latest();
    act(() => {
      source.send(runEvent("llm.call", { stage: "literature", tier: "paid", cost_usd: "0.5" }));
    });
    await waitFor(() => expect(result.current.spend.totalUsd).toBe(0.5));
    act(() => {
      source.send(
        ...Array.from({ length: MAX_EVENTS }, (_, index) =>
          runEvent("log", { stage: "literature", message: `line ${index}` }),
        ),
      );
    });
    await waitFor(() => expect(result.current.events.at(-1)?.payload.message).toBe("line 1999"));
    expect(result.current.events).toHaveLength(MAX_EVENTS);
    expect(result.current.events.some((event) => event.type === "llm.call")).toBe(false);
    expect(result.current.spend).toMatchObject({ totalUsd: 0.5, calls: 1 });
  });

  it("refetches the run, the stages its events name and the artifacts", async () => {
    const { result } = renderWithQuery(() => ({
      view: useRunView(RUN_ID),
      method: useStage(RUN_ID, "method"),
      coding: useStage(RUN_ID, "coding"),
      artifacts: useRunArtifacts(RUN_ID),
    }));
    await waitFor(() => expect(result.current.method.detail).toBeDefined());
    await waitFor(() => expect(result.current.artifacts.query.isSuccess).toBe(true));
    const run = `GET /api/v1/runs/${RUN_ID}`;
    const method = `GET /api/v1/runs/${RUN_ID}/stages/method`;
    const coding = `GET /api/v1/runs/${RUN_ID}/stages/coding`;
    const artifacts = `GET /api/v1/runs/${RUN_ID}/artifacts`;
    expect([count(run), count(method), count(coding), count(artifacts)]).toEqual([1, 1, 1, 1]);

    // Log lines and calls change no stage detail; a call changes the run's spend.
    act(() => {
      FakeEventSource.latest().send(
        runEvent("log", { stage: "method", message: "Reading papers" }),
        runEvent("llm.call", { stage: "method", tier: "free", cost_usd: "0" }),
      );
    });
    await waitFor(() => expect(result.current.view.events).toHaveLength(2));
    await waitFor(() => expect(count(run)).toBe(2));
    await new Promise((resolve) => setTimeout(resolve, 400));
    expect([count(run), count(method), count(coding), count(artifacts)]).toEqual([2, 1, 1, 1]);

    act(() => {
      FakeEventSource.latest().send(
        runEvent("stage.started", { stage: "method", attempt: 1 }),
        runEvent("run.status", { status: "running" }),
      );
    });
    await waitFor(() => expect(count(method)).toBe(2));
    await waitFor(() => expect(count(run)).toBe(3));
    await waitFor(() => expect(count(artifacts)).toBe(2));
    expect(count(coding)).toBe(1);

    // A run that ends (here: cancelled) may close any stage's attempt without stage events.
    act(() => {
      FakeEventSource.latest().send(runEvent("run.status", { status: "cancelled", error: null }));
    });
    await waitFor(() => expect(count(coding)).toBe(2));
    expect(count(method)).toBe(3);
  });

  it("draws the experiment's live curves from its epochs, without refetching anything", async () => {
    const { result } = renderWithQuery(() => ({
      view: useRunView(RUN_ID),
      experiment: useStage(RUN_ID, "experiment"),
      artifacts: useRunArtifacts(RUN_ID),
    }));
    await waitFor(() => expect(result.current.experiment.detail).toBeDefined());
    await waitFor(() => expect(result.current.artifacts.query.isSuccess).toBe(true));
    expect(result.current.view.training).toBeNull();
    const before = requestsOf(fetchMock).length;

    const epoch = (number: number, rmse: number | null) =>
      runEvent("experiment.epoch", {
        stage: "experiment",
        job_id: "job-1",
        kind: "train",
        ordinal: 1,
        epoch: number,
        train: { loss: 0.5, rmse: 0.6, mae: 0.4, abs_rel: 0.2 },
        val: { loss: 0.45, rmse, mae: 0.38, abs_rel: 0.18 },
      });
    act(() => {
      FakeEventSource.latest().send(epoch(0, 0.71), epoch(1, null));
    });
    await waitFor(() => expect(result.current.view.training?.epochs).toBe(2));
    const rmse = result.current.view.training?.series.find(
      (series) => series.name === "rmse" && series.split === "val",
    );
    expect(rmse?.points).toEqual([
      { epoch: 0, value: 0.71 },
      { epoch: 1, value: null },
    ]);

    act(() => {
      FakeEventSource.latest().send(epoch(2, 0.52));
    });
    await waitFor(() => expect(result.current.view.training?.latest.epoch).toBe(2));
    // Epochs change neither the run, a stage detail nor the artifacts.
    await new Promise((resolve) => setTimeout(resolve, 400));
    expect(requestsOf(fetchMock)).toHaveLength(before);
  });

  it("keeps the epochs the event log has already dropped", async () => {
    const { result } = renderWithQuery(() => useRunView(RUN_ID));
    const source = FakeEventSource.latest();
    act(() => {
      source.send(
        runEvent("stage.started", { stage: "experiment", attempt: 1 }),
        runEvent("experiment.epoch", {
          stage: "experiment",
          job_id: "job-1",
          kind: "train",
          ordinal: 1,
          epoch: 0,
          train: {},
          val: { loss: 0.9 },
        }),
      );
    });
    await waitFor(() => expect(result.current.training?.epochs).toBe(1));
    act(() => {
      source.send(
        ...Array.from({ length: MAX_EVENTS }, (_, index) =>
          runEvent("log", { stage: "experiment", message: `step ${index}` }),
        ),
      );
    });
    await waitFor(() => expect(result.current.events.at(-1)?.payload.message).toBe("step 1999"));
    expect(result.current.events.some((event) => event.type === "experiment.epoch")).toBe(false);
    expect(result.current.training).toMatchObject({ jobId: "job-1", epochs: 1 });
  });

  it("shows the run detail's spend, which counts failed and cancelled attempts too", async () => {
    currentRun = { ...awaitingRun, spend_usd: "0.0125" };
    const { result } = renderWithQuery(() => useRunView(RUN_ID));
    await waitFor(() => expect(result.current.spend.totalUsd).toBe(0.0125));
    expect(result.current.spend.calls).toBe(0);

    // A new call: the detail is refetched, and its total (with the failed attempt) is shown.
    currentRun = { ...awaitingRun, spend_usd: "0.0525" };
    act(() => {
      FakeEventSource.latest().send(
        runEvent("llm.call", { stage: "literature", tier: "paid", cost_usd: "0.04" }),
      );
    });
    await waitFor(() => expect(result.current.spend.totalUsd).toBe(0.0525));
    expect(result.current.spend).toMatchObject({ calls: 1, paidCalls: 1 });
  });

  it("lists the stages that wait, and forgets a wait once the stage moves on", async () => {
    const { result } = renderWithQuery(() => useRunView(RUN_ID));
    await waitFor(() => expect(result.current.run).toBeDefined());
    act(() => {
      FakeEventSource.latest().send(
        runEvent("stage.waiting", {
          stage: "literature",
          attempt: 1,
          reason: "free_quota.exhausted",
          retry_at: "2026-10-30T03:00:00Z",
        }),
      );
    });
    await waitFor(() =>
      expect(result.current.waits.literature?.reason).toBe("free_quota.exhausted"),
    );
    expect(result.current.waits.literature?.retryAt).toEqual(new Date("2026-10-30T03:00:00Z"));

    act(() => {
      FakeEventSource.latest().send(
        runEvent("llm.call", { stage: "literature", tier: "free", cost_usd: "0" }),
      );
    });
    await waitFor(() => expect(result.current.waits).toEqual({}));
  });

  it("does not open the stream again once the run is gone", async () => {
    const { result } = renderWithQuery(() => useRunView(RUN_ID));
    await waitFor(() => expect(result.current.run).toBeDefined());
    fetchMock.mockImplementation(async () => json(404, { detail: "run.not_found" }));
    act(() => FakeEventSource.latest().fail());
    expect(result.current.streamState).toBe("reconnecting");
    await waitFor(() => expect(result.current.streamState).toBe("error"), { timeout: 3000 });
    expect(FakeEventSource.instances).toHaveLength(1);
    // The run that was on screen stays, with the failed refresh noted on the query.
    expect(result.current.run).toBeDefined();
    expect(result.current.query.isRefetchError).toBe(true);
  });

  it("refreshes everything that shows the run on demand", async () => {
    const { result } = renderWithQuery(() => ({
      view: useRunView(RUN_ID),
      method: useStage(RUN_ID, "method"),
    }));
    await waitFor(() => expect(result.current.method.detail).toBeDefined());
    await waitFor(() => expect(result.current.view.run).toBeDefined());
    act(() => result.current.view.refresh());
    await waitFor(() => expect(count(`GET /api/v1/runs/${RUN_ID}/stages/method`)).toBe(2));
    expect(count(`GET /api/v1/runs/${RUN_ID}`)).toBe(2);
  });
});
