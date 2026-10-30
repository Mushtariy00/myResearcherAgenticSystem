// @vitest-environment jsdom
import { QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { ArtifactOut, ProjectOut, RunDetail, StageDetail, StageInfo } from "@/client";
import {
  FakeEventSource,
  installEventSource,
  json,
  makeQueryClient,
  mockApi,
  runEvent,
} from "@/hooks/run-hooks.fixtures";
import {
  attemptOut,
  DEMO_EXPERIMENT,
  DEMO_LITERATURE,
  DEMO_METHOD,
  runDetailOut,
  stageDetailOut,
  stageOutputOut,
  stageRunOut,
  versionOut,
} from "@/lib/stage-output.fixtures";
import { STAGE_ORDER } from "@/lib/timeline";
import { enMessages as messages } from "@/test/messages";
import { RunView } from "./run-view";

// ECharts draws on canvas, which jsdom lacks (the chart is covered by its own tests). Its core
// is mocked: charts that mount together import the chart runtime at the same time, and a mock
// of that module reaches only the first of them.
const chart = vi.hoisted(() => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() }));
vi.mock("echarts/core", () => ({ init: () => chart, use: () => {} }));

const toast = vi.hoisted(() => ({
  success: vi.fn(),
  warning: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
}));
vi.mock("sonner", () => ({ toast }));

// The URL is the browser's: the stage tab reads and replaces `?stage=` there.
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(window.location.search),
  usePathname: () => window.location.pathname,
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
  }),
}));

const RUN_ID = "22222222-2222-4222-8222-222222222222";
const PROJECT: ProjectOut = {
  id: "33333333-3333-4333-8333-333333333333",
  name: "Depth lab",
  description: "",
  privacy: "standard",
  allow_free_models: true,
  created_by: "owner",
  created_at: "2026-10-01T00:00:00Z",
  my_role: "owner",
};
const STAGES: StageInfo[] = STAGE_ORDER.map((id, position) => ({
  id,
  position,
  auto_approvable: id !== "coding",
}));

// Literature: approved after Bob corrected it (version 2). Method: attempt 1 was sent back,
// attempt 2 waits for review.
const literatureV1 = versionOut(DEMO_LITERATURE, { degraded_reason: "literature.demo_search" });
const literatureV2 = versionOut(
  { ...DEMO_LITERATURE, synthesis: "Corrected synthesis." },
  {
    version: 2,
    degraded_reason: "literature.demo_search",
    edited_by: "bob",
    edited_by_name: "Bob",
    approval: {
      decision: "approve",
      comment: "Good after the fix",
      actor_id: "alice",
      actor_name: "Alice",
      at: "2026-10-30T01:10:00Z",
    },
  },
);
const methodSentBack = versionOut(
  { ...DEMO_METHOD, recommended_option: "Lightweight state-space encoder for long-range context" },
  {
    approval: {
      decision: "request_changes",
      comment: "Prefer distillation",
      actor_id: "alice",
      actor_name: "Alice",
      at: "2026-10-30T01:30:00Z",
    },
  },
);
const awaitingOutput = stageOutputOut(DEMO_METHOD, { version: 1 });
const methodAwaiting = versionOut(DEMO_METHOD, {
  id: awaitingOutput.id,
  sha256: awaitingOutput.sha256,
});

const DETAILS: Record<string, StageDetail> = {
  literature: stageDetailOut(RUN_ID, "literature", [
    attemptOut(1, [literatureV1, literatureV2], { status: "approved" }),
  ]),
  method: stageDetailOut(RUN_ID, "method", [
    attemptOut(1, [methodSentBack], { status: "changes_requested" }),
    attemptOut(2, [methodAwaiting], { feedback: "Prefer distillation" }),
  ]),
};

const awaitingRun: RunDetail = runDetailOut({
  id: RUN_ID,
  project_id: PROJECT.id,
  status: "awaiting_approval",
  budget_cap_usd: "5.00",
  stages: [
    stageRunOut("literature", "approved", { outputs: [literatureV1, literatureV2] }),
    stageRunOut("method", "changes_requested", { outputs: [methodSentBack] }),
    stageRunOut("method", "output_ready", { attempt: 2, outputs: [awaitingOutput] }),
  ],
  awaiting: awaitingOutput,
  awaiting_stage: "method",
  can_steer: true,
});

function artifact(
  kind: ArtifactOut["kind"],
  stage: string,
  filename: string,
  path: string | null = null,
): ArtifactOut {
  return {
    id: `${awaitingOutput.id}.${filename}`,
    stage,
    kind,
    filename,
    path,
    media_type: "text/plain",
    size_bytes: 1536,
    sha256: "c".repeat(64),
    stage_output_id: awaitingOutput.id,
    version: 1,
    created_at: "2026-10-30T01:00:00Z",
    demo: true,
  };
}

let currentRun: RunDetail = awaitingRun;
let currentArtifacts: ArtifactOut[] = [];
/** Stage details a test sets, over DETAILS. */
let stageDetails: Record<string, StageDetail> = {};
/** Set to make GET /runs/<id> fail (a proxy error while the API restarts, say). */
let runFailure: (() => Response) | null = null;

beforeAll(() => {
  Element.prototype.scrollIntoView = () => {};
  HTMLCanvasElement.prototype.getContext = (() =>
    null) as typeof HTMLCanvasElement.prototype.getContext;
});

beforeEach(() => {
  currentRun = awaitingRun;
  currentArtifacts = [];
  stageDetails = {};
  runFailure = null;
  window.history.replaceState(null, "", `/runs/${RUN_ID}`);
  installEventSource();
  mockApi((_request, path) => {
    if (path === `/api/v1/runs/${RUN_ID}`) {
      return runFailure ? runFailure() : json(200, currentRun);
    }
    if (path === "/api/v1/stages") {
      return json(200, STAGES);
    }
    if (path === `/api/v1/runs/${RUN_ID}/artifacts`) {
      return json(200, {
        run_id: RUN_ID,
        items: currentArtifacts,
        demo: currentArtifacts.some((item) => item.demo),
      });
    }
    if (path === `/api/v1/projects/${PROJECT.id}`) {
      return json(200, PROJECT);
    }
    const stage = path.match(/\/stages\/([a-z]+)$/)?.[1];
    if (stage) {
      return json(200, stageDetails[stage] ?? DETAILS[stage] ?? stageDetailOut(RUN_ID, stage, []));
    }
    return json(404, { detail: "run.not_found" });
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

function renderRun() {
  return render(
    <QueryClientProvider client={makeQueryClient()}>
      <NextIntlClientProvider locale="en" messages={messages} timeZone="Asia/Seoul">
        <RunView runId={RUN_ID} />
      </NextIntlClientProvider>
    </QueryClientProvider>,
  );
}

const tab = (name: RegExp) => screen.getByRole("tab", { name });
const stageParam = () => new URLSearchParams(window.location.search).get("stage");

/** An experiment.epoch event of the training job, as the executor writes it. */
function epochEvent(epoch: number, rmse: number | null) {
  return runEvent("experiment.epoch", {
    stage: "experiment",
    job_id: "job-1",
    kind: "train",
    ordinal: 1,
    epoch,
    train: { loss: 0.5, rmse: 0.6, mae: 0.4, abs_rel: 0.2 },
    val: { loss: 0.45, rmse, mae: 0.38, abs_rel: 0.18 },
  });
}

/** A run that has reached the experiment stage, with the stage as given. */
function experimentRun(experiment: RunDetail["stages"][number], status: RunDetail["status"]) {
  return runDetailOut({
    id: RUN_ID,
    project_id: PROJECT.id,
    status,
    stages: [
      stageRunOut("literature", "approved", { outputs: [literatureV1] }),
      stageRunOut("method", "approved"),
      stageRunOut("coding", "approved"),
      experiment,
    ],
  });
}

/** The values of a chart's data table, by row. */
function chartRows(name: string): string[][] {
  const table = screen.getByRole("table", { name: `${name}: values per epoch` });
  return [...table.querySelectorAll("tbody tr")].map((row) =>
    [...row.children].map((cell) => cell.textContent ?? ""),
  );
}

describe("RunView", () => {
  it("shows the header with live spend and opens the stage that waits for review", async () => {
    renderRun();
    expect(await screen.findByRole("heading", { level: 1, name: awaitingRun.topic })).toBeTruthy();
    expect(await screen.findByRole("link", { name: "Back to Depth lab" })).toBeTruthy();
    expect(screen.getByText("Cost cap: $5.00")).toBeTruthy();
    expect(screen.getByText("Spent so far: $0.00")).toBeTruthy();

    act(() => {
      FakeEventSource.latest().send(
        runEvent("llm.call", { stage: "method", model: "m", tier: "paid", cost_usd: "0.0125" }),
        runEvent("llm.call", { stage: "method", model: "m", tier: "free", cost_usd: "0" }),
      );
    });
    expect(await screen.findByText("Spent so far: $0.0125")).toBeTruthy();
    expect(screen.getByText("(2 LLM calls: 1 paid, 1 free)")).toBeTruthy();

    expect(tab(/^Method/).getAttribute("aria-selected")).toBe("true");
    expect(tab(/^Literature/).textContent).toContain("3 of 5 papers included");
    expect(screen.getByRole("heading", { name: "Review the Method output" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Cancel run" })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Downloads/ })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Retry…" })).toBeNull();
  });

  it("keeps the stage in the URL and points back to the review from other stages", async () => {
    renderRun();
    fireEvent.click(await screen.findByRole("tab", { name: /^Literature/ }));
    expect(stageParam()).toBe("literature");
    expect(tab(/^Literature/).getAttribute("aria-selected")).toBe("true");
    expect(await screen.findByRole("heading", { name: "Research plan" })).toBeTruthy();

    const callout = screen.getByText("The Method output is waiting for your review.");
    expect(callout).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Review it" }));
    expect(stageParam()).toBe("method");
    expect(screen.getByRole("heading", { name: "Review the Method output" })).toBeTruthy();
    expect(screen.queryByText("The Method output is waiting for your review.")).toBeNull();
  });

  it("opens the stage the URL names", async () => {
    window.history.replaceState(null, "", `/runs/${RUN_ID}?stage=coding`);
    renderRun();
    expect(await screen.findByText("Not started yet")).toBeTruthy();
    expect(tab(/^Coding/).getAttribute("aria-selected")).toBe("true");
  });

  it("switches between attempts and versions, with who edited and decided each", async () => {
    window.history.replaceState(null, "", `/runs/${RUN_ID}?stage=literature`);
    renderRun();
    const versions = await screen.findByRole("radiogroup", { name: "Versions" });
    const radios = within(versions).getAllByRole("radio");
    expect(radios.map((radio) => radio.getAttribute("aria-label"))).toEqual([
      "Attempt 1, version 1",
      "Attempt 1, version 2: Approved by Alice, edited by Bob",
    ]);
    // The newest version is on screen, with its editor and the decision on it.
    expect(radios[1]?.getAttribute("aria-checked")).toBe("true");
    expect(screen.getByText("Corrected synthesis.")).toBeTruthy();
    expect(screen.getByText("Bob")).toBeTruthy();
    expect(screen.getByText("Approved by Alice")).toBeTruthy();
    expect(screen.getByText("Good after the fix")).toBeTruthy();

    fireEvent.click(radios[0] as HTMLElement);
    expect(screen.getByText("You are looking at an older version.")).toBeTruthy();
    expect(screen.queryByText("Corrected synthesis.")).toBeNull();
    expect(screen.queryByText("Good after the fix")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Show the newest" }));
    expect(screen.getByText("Corrected synthesis.")).toBeTruthy();
  });

  it("shows an earlier attempt of the stage under review, and goes back to the review", async () => {
    renderRun();
    const versions = await screen.findByRole("radiogroup", { name: "Versions" });
    expect(
      within(versions)
        .getAllByRole("radio")
        .map((radio) => radio.getAttribute("aria-label")),
    ).toEqual([
      "Attempt 1, version 1: Changes requested by Alice",
      "Attempt 2, version 1: waiting for review",
    ]);
    fireEvent.click(within(versions).getByRole("radio", { name: /^Attempt 1/ }));
    expect(screen.getByText("This is not the version waiting for review.")).toBeTruthy();
    expect(screen.getByText("Changes requested by Alice")).toBeTruthy();
    expect(screen.getByText("Prefer distillation")).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Review the Method output" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Go to the review" }));
    expect(screen.getByRole("heading", { name: "Review the Method output" })).toBeTruthy();
  });

  it("hides the decisions, cancel and retry from people who may only look", async () => {
    currentRun = { ...awaitingRun, can_steer: false };
    renderRun();
    expect(
      await screen.findByRole("heading", { name: "Method output waiting for review" }),
    ).toBeTruthy();
    for (const name of ["Approve", "Request changes", "Reject", "Cancel run", "Retry…"]) {
      expect(screen.queryByRole("button", { name })).toBeNull();
    }
    expect(screen.queryByRole("tab", { name: "Edit before approving" })).toBeNull();
    expect(screen.getByRole("button", { name: /Downloads/ })).toBeTruthy();

    fireEvent.click(tab(/^Literature/));
    expect(
      screen.getByText(
        "The Method output is waiting for review by the run owner or a project owner.",
      ),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "View it" })).toBeTruthy();
  });

  it("lists the run's files by stage in the downloads menu", async () => {
    currentArtifacts = [
      artifact("draft", "writing", "run-draft.md"),
      artifact("code_file", "coding", "model.py", "model.py"),
      artifact("code_archive", "coding", "run-code.zip"),
      artifact("metrics", "experiment", "run-metrics.csv"),
    ];
    renderRun();
    fireEvent.click(await screen.findByRole("button", { name: /Downloads/ }));
    const archive = await screen.findByRole("menuitem", { name: /All code \(\.zip\)/ });
    expect(archive.getAttribute("href")).toMatch(
      new RegExp(`/api/v1/artifacts/${awaitingOutput.id}\\.run-code\\.zip$`),
    );
    expect(archive.getAttribute("download")).toBe("run-code.zip");
    const menu = screen.getByRole("menu");
    // The archive comes before single files; stages keep the API's order.
    expect(
      within(menu)
        .getAllByRole("menuitem")
        .map((item) => item.textContent),
    ).toEqual([
      expect.stringContaining("Draft (.md)"),
      expect.stringContaining("All code (.zip)"),
      expect.stringContaining("model.py"),
      expect.stringContaining("Metrics (.csv)"),
    ]);
    expect(menu.textContent).toContain("Demo data:");
  });

  it("lists the training checkpoint with its size, as a download", async () => {
    currentArtifacts = [
      artifact("experiment_log", "experiment", "run-experiment.log"),
      { ...artifact("checkpoint", "experiment", "best.pt"), size_bytes: 48_234_496 },
      artifact("metrics", "experiment", "run-metrics.csv"),
    ];
    renderRun();
    fireEvent.click(await screen.findByRole("button", { name: /Downloads/ }));
    const checkpoint = await screen.findByRole("menuitem", { name: /Model checkpoint \(\.pt\)/ });
    expect(checkpoint.getAttribute("download")).toBe("best.pt");
    expect(checkpoint.getAttribute("href")).toMatch(/\/api\/v1\/artifacts\/.+\.best\.pt$/);
    expect(checkpoint.textContent).toContain("46 MB");
    expect(
      within(screen.getByRole("menu"))
        .getAllByRole("menuitem")
        .map((item) => item.textContent),
    ).toEqual([
      expect.stringContaining("Training log"),
      expect.stringContaining("Metrics"),
      expect.stringContaining("Model checkpoint"),
    ]);
  });

  it("draws the experiment's live training curves while it trains, then its stored series", async () => {
    currentRun = experimentRun(stageRunOut("experiment", "running"), "running");
    stageDetails.experiment = stageDetailOut(RUN_ID, "experiment", [
      attemptOut(1, [], { status: "running" }),
    ]);
    window.history.replaceState(null, "", `/runs/${RUN_ID}?stage=experiment`);
    renderRun();
    expect(await screen.findByText("Attempt 1 is working")).toBeTruthy();
    const live = screen.getByRole("region", { name: "Live training curves" });
    expect(within(live).getByText("The curves appear here after the first epoch.")).toBeTruthy();

    act(() => {
      FakeEventSource.latest().open();
      FakeEventSource.latest().send(
        runEvent("stage.started", { stage: "experiment", attempt: 1 }),
        epochEvent(0, 0.91),
      );
    });
    expect(await within(live).findByText("1 epoch so far")).toBeTruthy();
    expect(
      within(live)
        .getAllByRole("figure")
        .map((figure) => figure.querySelector("figcaption")?.textContent),
    ).toEqual(["loss per epoch", "rmse per epoch", "mae per epoch", "abs_rel per epoch"]);

    // Each epoch extends the curves as it arrives; one not measured is a gap, never 0.
    act(() => {
      FakeEventSource.latest().send(epochEvent(1, null), epochEvent(2, 0.62));
    });
    expect(await within(live).findByText("3 epochs so far")).toBeTruthy();
    expect(within(live).getByText("Latest: Epoch 2: val RMSE 0.62")).toBeTruthy();
    expect(chartRows("rmse per epoch")).toEqual([
      ["0", "0.91", "0.6"],
      ["1", "No value", "0.6"],
      ["2", "0.62", "0.6"],
    ]);
    // The live charts extend their lines instead of drawing them again.
    await waitFor(() =>
      expect(chart.setOption).toHaveBeenLastCalledWith(expect.anything(), {
        replaceMerge: ["series"],
      }),
    );
    expect(screen.getByText("Experiment: Epoch 2: val RMSE 0.62 · train 0.6")).toBeTruthy();

    // The output is ready (and approved by itself): the stored series take over.
    const version = versionOut(DEMO_EXPERIMENT, {
      degraded: false,
      degraded_reason: null,
      approval: {
        decision: "approve",
        comment: "",
        actor_id: "system:auto-approve",
        actor_name: null,
        at: "2026-10-31T01:00:00Z",
      },
    });
    stageDetails.experiment = stageDetailOut(RUN_ID, "experiment", [
      attemptOut(1, [version], { status: "approved" }),
    ]);
    currentRun = experimentRun(stageRunOut("experiment", "approved"), "running");
    act(() => {
      FakeEventSource.latest().send(
        runEvent("stage.output_ready", { stage: "experiment", attempt: 1 }),
      );
    });
    expect(await screen.findByRole("region", { name: "Training curves" })).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Live training curves" })).toBeNull();
    expect(screen.getByText("Succeeded")).toBeTruthy();
  });

  it("draws a newer attempt's live curves above the earlier output on screen", async () => {
    const earlier = versionOut(DEMO_EXPERIMENT, {
      approval: {
        decision: "request_changes",
        comment: "Train longer",
        actor_id: "alice",
        actor_name: "Alice",
        at: "2026-10-31T01:00:00Z",
      },
    });
    stageDetails.experiment = stageDetailOut(RUN_ID, "experiment", [
      attemptOut(1, [earlier], { status: "changes_requested" }),
      attemptOut(2, [], { status: "running", feedback: "Train longer" }),
    ]);
    currentRun = experimentRun(stageRunOut("experiment", "running", { attempt: 2 }), "running");
    window.history.replaceState(null, "", `/runs/${RUN_ID}?stage=experiment`);
    renderRun();
    expect(await screen.findByText("Showing the output of attempt 1.")).toBeTruthy();
    act(() => {
      FakeEventSource.latest().send(
        runEvent("stage.started", { stage: "experiment", attempt: 1 }),
        epochEvent(0, 0.95),
        runEvent("stage.started", { stage: "experiment", attempt: 2 }),
      );
    });
    // Attempt 1's epochs are not attempt 2's curves.
    const live = await screen.findByRole("region", { name: "Live training curves of attempt 2" });
    expect(within(live).getByText("The curves appear here after the first epoch.")).toBeTruthy();
    act(() => {
      FakeEventSource.latest().send(epochEvent(0, 0.88));
    });
    expect(await within(live).findByText("1 epoch so far")).toBeTruthy();
    // The earlier output keeps its own curves.
    expect(screen.getByRole("region", { name: "Training curves" })).toBeTruthy();
  });

  it("says why the coding stage failed on the GPU, in words", async () => {
    currentRun = runDetailOut({
      id: RUN_ID,
      project_id: PROJECT.id,
      status: "failed",
      error: "coding.smoke_failed",
      stages: [
        stageRunOut("literature", "approved", { outputs: [literatureV1] }),
        stageRunOut("method", "approved"),
        stageRunOut("coding", "failed", { error: "coding.smoke_failed" }),
      ],
    });
    stageDetails.coding = stageDetailOut(RUN_ID, "coding", [
      attemptOut(1, [], { status: "failed", error: "coding.smoke_failed" }),
    ]);
    window.history.replaceState(null, "", `/runs/${RUN_ID}?stage=coding`);
    renderRun();
    const message =
      "The generated code failed its smoke test on the GPU in every try (at most 3). The event log says why each try failed.";
    expect(await screen.findByText("Attempt 1 failed before it produced an output")).toBeTruthy();
    // On the run, in the timeline and on the stage.
    expect(screen.getAllByText(message)).toHaveLength(3);
    expect(screen.queryByText("coding.smoke_failed")).toBeNull();
  });

  it("says when the run has no files yet", async () => {
    renderRun();
    fireEvent.click(await screen.findByRole("button", { name: /Downloads/ }));
    expect(
      await screen.findByText("No files yet. The coding, experiment and writing stages make them."),
    ).toBeTruthy();
  });

  it("offers a retry of a finished run to those who may steer it, and no cancel", async () => {
    currentRun = runDetailOut({
      id: RUN_ID,
      project_id: PROJECT.id,
      status: "failed",
      error: "stage.error",
      stages: [
        stageRunOut("literature", "approved", { outputs: [literatureV1] }),
        stageRunOut("method", "failed", { error: "stage.error" }),
      ],
    });
    const view = renderRun();
    expect(await screen.findByRole("button", { name: "Retry…" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Cancel run" })).toBeNull();
    expect(screen.getByText("The run reported an error")).toBeTruthy();
    view.unmount();

    currentRun = { ...currentRun, can_steer: false };
    renderRun();
    expect(await screen.findByText("The run reported an error")).toBeTruthy();
    await waitFor(() => expect(screen.queryByRole("button", { name: "Retry…" })).toBeNull());
  });

  it("keeps the run and the review in progress on screen when a refresh fails", async () => {
    renderRun();
    expect(await screen.findByRole("heading", { name: "Review the Method output" })).toBeTruthy();
    const comment = screen.getByLabelText("Comment") as HTMLTextAreaElement;
    fireEvent.change(comment, { target: { value: "Half-written thoughts" } });

    runFailure = () => new Response("Bad Gateway", { status: 502 });
    act(() => {
      FakeEventSource.latest().send(runEvent("stage.started", { stage: "method", attempt: 2 }));
    });
    expect(
      await screen.findByText("Could not refresh the run, so what you see may be out of date."),
    ).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Review the Method output" })).toBeTruthy();
    expect((screen.getByLabelText("Comment") as HTMLTextAreaElement).value).toBe(
      "Half-written thoughts",
    );
    expect(screen.queryByText("Could not load this")).toBeNull();

    runFailure = null;
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() =>
      expect(
        screen.queryByText("Could not refresh the run, so what you see may be out of date."),
      ).toBeNull(),
    );
  });

  it("shows the whole-page error only when the run never loaded", async () => {
    runFailure = () => json(403, { detail: "permission.denied" });
    renderRun();
    expect(await screen.findByText("You do not have permission to do that.")).toBeTruthy();
    expect(screen.queryByRole("heading", { level: 1 })).toBeNull();
  });

  it("shows a stage that waits, why, and when it tries again by itself", async () => {
    currentRun = runDetailOut({
      id: RUN_ID,
      project_id: PROJECT.id,
      status: "running",
      stages: [
        stageRunOut("literature", "approved", { outputs: [literatureV1] }),
        stageRunOut("method", "running"),
      ],
    });
    window.history.replaceState(null, "", `/runs/${RUN_ID}?stage=method`);
    renderRun();
    expect(await screen.findByRole("heading", { level: 1, name: currentRun.topic })).toBeTruthy();
    act(() => {
      FakeEventSource.latest().send(
        runEvent("stage.waiting", {
          stage: "method",
          attempt: 1,
          reason: "free_quota.exhausted",
          retry_at: "2099-01-01T03:00:00Z",
        }),
      );
    });

    const alert = await screen.findByText("Method is waiting");
    const box = alert.closest('[data-slot="alert"]') as HTMLElement;
    expect(box.textContent).toContain(
      "The lab's free-model quota or rate limit is used up for now.",
    );
    // 03:00 UTC is noon in Seoul, the app's time zone (ICU puts a narrow space before PM).
    expect(box.textContent).toMatch(/It tries again by itself at Jan 1, 12:00\sPM\./);
    const timeline = screen.getByRole("region", { name: "Stages" });
    expect(within(timeline).getByText(/It tries again by itself at Jan 1/)).toBeTruthy();
    expect(screen.getByText(/Method is waiting: The lab's free-model quota/)).toBeTruthy();

    // The stage runs again: its next event ends the wait.
    act(() => {
      FakeEventSource.latest().send(
        runEvent("llm.call", { stage: "method", model: "m", tier: "free", cost_usd: "0" }),
      );
    });
    await waitFor(() => expect(screen.queryByText("Method is waiting")).toBeNull());
  });

  it("says a run paused for the lab balance continues by itself, and when it checks again", async () => {
    currentRun = runDetailOut({
      id: RUN_ID,
      project_id: PROJECT.id,
      status: "paused_budget",
      stages: [stageRunOut("literature", "running")],
    });
    renderRun();
    const title = await screen.findByText("Paused: the lab's LLM balance is used up");
    const box = title.closest('[data-slot="alert"]') as HTMLElement;
    expect(box.textContent).toContain("The run continues by itself once the balance is topped up");
    act(() => {
      FakeEventSource.latest().send(
        runEvent("stage.waiting", {
          stage: "literature",
          attempt: 1,
          reason: "lab_balance.exhausted",
          retry_at: "2099-01-01T03:15:00Z",
        }),
      );
    });
    await waitFor(() =>
      expect(box.textContent).toMatch(/The balance is checked again at Jan 1, 12:15\sPM\./),
    );
  });
});
