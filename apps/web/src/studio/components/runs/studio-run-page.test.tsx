// @vitest-environment jsdom
import { act, cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { EvidenceQuote } from "@/client";
import { FakeEventSource, runEvent } from "@/hooks/run-hooks.fixtures";
import {
  attemptOut,
  DEMO_EXPERIMENT,
  DEMO_LITERATURE,
  DEMO_OUTPUTS,
  runDetailOut,
  stageDetailOut,
  stageRunOut,
  versionOut,
} from "@/lib/stage-output.fixtures";
import {
  api,
  approvedBy,
  artifact,
  outputPair,
  PROJECT,
  RUN_ID,
  renderRunPage,
  seedCompletedRun,
  setUpRunPage,
  waitForRun,
} from "./run-page.fixtures";

const navigation = vi.hoisted(() => ({ search: "" }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(navigation.search),
  usePathname: () => "/studio/runs/22222222-2222-4222-8222-222222222222",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
}));

const toast = vi.hoisted(() => ({
  success: vi.fn(),
  warning: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
}));
vi.mock("sonner", () => ({ toast }));

const confetti = vi.hoisted(() => vi.fn());
vi.mock("canvas-confetti", () => ({ default: confetti }));

// PDF.js and ECharts cannot run in jsdom; their own tests cover them.
vi.mock("@/components/shared/pdf-viewer", () => ({
  PdfViewer: (props: { url: string; quotes?: readonly EvidenceQuote[]; activeQuote?: number }) => (
    <div data-testid="pdf-viewer" data-url={props.url} data-active-quote={props.activeQuote}>
      {(props.quotes ?? []).map((quote) => quote.quote).join(" | ")}
    </div>
  ),
}));
vi.mock("@/components/shared/metrics-chart-echarts", () => ({
  init: vi.fn(() => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() })),
}));
// Charts that mount together import the chart runtime at the same time, and the mock above
// reaches only the first of them: the others get a stand-in core.
vi.mock("echarts/core", () => ({
  init: () => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() }),
  use: () => {},
}));

beforeEach(() => {
  navigation.search = "";
  window.history.replaceState(null, "", "/");
  setUpRunPage();
  HTMLCanvasElement.prototype.getContext = (() =>
    null) as typeof HTMLCanvasElement.prototype.getContext;
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => "visible" });
});

function send(...events: ReturnType<typeof runEvent>[]) {
  act(() => {
    FakeEventSource.latest().open();
    FakeEventSource.latest().send(...events);
  });
}

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

/** A run up to the experiment stage, with the experiment as given. */
function experimentRun(experiment: ReturnType<typeof stageRunOut>) {
  return runDetailOut({
    status: "running",
    stages: [
      stageRunOut("literature", "approved"),
      stageRunOut("method", "approved"),
      stageRunOut("coding", "approved"),
      experiment,
    ],
  });
}

const chartTitles = (scope: HTMLElement) =>
  within(scope)
    .getAllByRole("figure")
    .map((figure) => figure.querySelector("figcaption")?.textContent);

describe("StudioRunPage header", () => {
  it("shows the topic, a live status, the run's facts, its project and the live spend", async () => {
    api.run = runDetailOut({
      status: "running",
      budget_cap_usd: "5.00",
      stages: [stageRunOut("literature", "running")],
    });
    const { container } = renderRunPage();
    await waitForRun();

    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(api.run.topic);
    const status = screen.getByText("Run status:").parentElement as HTMLElement;
    expect(status.textContent).toContain("Running");
    expect(status.querySelector("[data-live='true']")).not.toBeNull();
    expect(screen.getByText("Models: Auto")).toBeTruthy();
    expect(screen.getByText("Cost cap: $5.00")).toBeTruthy();
    const back = await screen.findByRole("link", { name: `Back to ${PROJECT.name}` });
    expect(back.getAttribute("href")).toBe(`/studio/projects/${PROJECT.id}`);
    expect(screen.getByRole("button", { name: "Cancel run" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();

    // The pipeline graph follows the timeline and selects stages.
    const pipeline = screen.getByRole("list", {
      name: "Pipeline stages: select one to see its output",
    });
    expect(within(pipeline).getByRole("button", { name: "Literature: Running" })).toBeTruthy();

    send(
      runEvent("llm.call", { stage: "literature", model: "m", tier: "paid", cost_usd: "0.0125" }),
      runEvent("llm.call", { stage: "literature", model: "m", tier: "free", cost_usd: "0" }),
    );
    await waitFor(() => expect(screen.getAllByText("$0.0125").length).toBeGreaterThan(0));
    expect(screen.getByText("2 calls ·", { exact: false }).textContent).toContain(
      "1 paid · 1 free",
    );
    expect(container.querySelector("[role='progressbar']")).not.toBeNull();
  });

  it("speaks Korean", async () => {
    seedCompletedRun();
    renderRunPage("ko");
    await waitForRun();
    expect(screen.getByText("모델: 자동")).toBeTruthy();
    expect(screen.getAllByText("비용 한도 없음").length).toBeGreaterThan(0);
    expect(screen.getByRole("tab", { name: "논문 작성, 승인됨" })).toBeTruthy();
    expect(screen.getByText("모든 단계가 승인되었습니다")).toBeTruthy();
    expect(await screen.findByRole("heading", { name: "개요" })).toBeTruthy();
  });

  it("says when the run cannot be found", async () => {
    api.run = { ...api.run, id: "someone-else" };
    renderRunPage();
    expect(await screen.findByRole("heading", { level: 1, name: "Run not found" })).toBeTruthy();
  });
});

describe("StudioRunPage stage views", () => {
  it("renders the literature output: plan, papers with filters, findings and synthesis", async () => {
    seedCompletedRun();
    navigation.search = "stage=literature";
    renderRunPage();
    await waitForRun();

    const panel = await screen.findByRole("tabpanel");
    expect(await within(panel).findByRole("heading", { name: "Search plan" })).toBeTruthy();
    expect(within(panel).getByText("Papers screened")).toBeTruthy();
    const table = within(panel).getByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(DEMO_LITERATURE.papers.length + 1);
    expect(within(panel).getByRole("heading", { name: "Key findings" })).toBeTruthy();
    expect(within(panel).getByText(/The search screened 5 papers/)).toBeTruthy();

    // Filters narrow the table.
    fireEvent.click(within(panel).getByRole("button", { name: /^Excluded/ }));
    expect(within(table).getAllByRole("row")).toHaveLength(2);
    expect(within(panel).getByText("1 of 5 papers")).toBeTruthy();
    fireEvent.click(within(panel).getByRole("button", { name: "Clear filters" }));
    fireEvent.change(within(panel).getByRole("searchbox", { name: "Search the papers" }), {
      target: { value: "synthetic data" },
    });
    await waitFor(() => expect(within(table).getAllByRole("row")).toHaveLength(2));
  });

  it("opens a paper sheet with its reading notes and the PDF at an evidence quote", async () => {
    seedCompletedRun();
    navigation.search = "stage=literature";
    renderRunPage();
    await waitForRun();
    const paper = DEMO_LITERATURE.papers[0];
    const analysis = DEMO_LITERATURE.analyses?.[0];
    if (!paper || !analysis) {
      throw new Error("fixture changed");
    }

    const table = await screen.findByRole("table");
    fireEvent.click(within(table).getByRole("button", { name: paper.title }));
    const sheet = await screen.findByRole("dialog", { name: paper.title });
    expect(within(sheet).getByText("Reading notes")).toBeTruthy();
    expect(within(sheet).getByText(analysis.contribution)).toBeTruthy();
    expect(within(sheet).getByText(paper.decision_reason)).toBeTruthy();
    expect(within(sheet).queryByTestId("pdf-viewer")).toBeNull();

    fireEvent.click(within(sheet).getByRole("button", { name: "Open quote 1 in the PDF, page 5" }));
    const viewer = await within(sheet).findByTestId("pdf-viewer");
    expect(viewer.getAttribute("data-url")).toContain(
      `/api/v1/papers/${encodeURIComponent(paper.paper_id)}/file`,
    );
    expect(viewer.getAttribute("data-active-quote")).toBe("0");
    expect(viewer.textContent).toBe(analysis.evidence?.[0]?.quote);
  });

  it("highlights the recommended method proposal with a border beam", async () => {
    seedCompletedRun();
    navigation.search = "stage=method";
    const { container } = renderRunPage();
    await waitForRun();

    await screen.findByRole("heading", { name: "Research gaps" });
    const recommended = container.querySelector("li[data-recommended]") as HTMLElement;
    expect(within(recommended).getByRole("heading", { level: 3 }).textContent).toBe(
      DEMO_OUTPUTS.method.recommended_option,
    );
    expect(within(recommended).getByText("Recommended")).toBeTruthy();
    expect(recommended.querySelector(".studio-beam")).not.toBeNull();
    expect(container.querySelectorAll("li[data-recommended] .studio-beam")).toHaveLength(1);
  });

  it("renders the coding output: summary, smoke test, code and the diff with the attempt before", async () => {
    seedCompletedRun();
    const first = versionOut(
      {
        ...DEMO_OUTPUTS.coding,
        files: DEMO_OUTPUTS.coding.files.filter((file) => file.path !== "README.md"),
      },
      {
        approval: {
          decision: "request_changes",
          comment: "Add a README",
          actor_id: "alice",
          actor_name: "Alice",
          at: "2026-10-30T02:00:00Z",
        },
      },
    );
    const second = api.stages.coding?.attempts[0]?.outputs[0];
    if (!second) {
      throw new Error("fixture changed");
    }
    api.stages.coding = stageDetailOut(RUN_ID, "coding", [
      attemptOut(1, [first], { status: "changes_requested" }),
      attemptOut(2, [second], { status: "approved", feedback: "Add a README" }),
    ]);
    navigation.search = "stage=coding";
    renderRunPage();
    await waitForRun();

    const panel = await screen.findByRole("tabpanel");
    expect(await within(panel).findByRole("heading", { name: "Smoke test" })).toBeTruthy();
    expect(within(panel).getByText("Passed")).toBeTruthy();
    expect(within(panel).getByRole("navigation", { name: "Files" })).toBeTruthy();
    expect(within(panel).getByText("Reviewer feedback for this attempt")).toBeTruthy();
    expect(within(panel).getByRole("group", { name: "Versions" })).toBeTruthy();

    const changes = within(panel).getByRole("heading", { name: "Changes since attempt 1" });
    expect(changes).toBeTruthy();
    expect(within(panel).getByText("1 file changed")).toBeTruthy();
    fireEvent.click(within(panel).getByRole("button", { name: "Show the changes" }));
    expect(await within(panel).findByRole("region", { name: "Changes in README.md" })).toBeTruthy();
  });

  it("renders the experiment output: metric tiles (never 0 for a missing value), a chart per metric, provenance", async () => {
    seedCompletedRun();
    const experiment = {
      ...DEMO_EXPERIMENT,
      final_metrics: { ...DEMO_EXPERIMENT.final_metrics, delta1: null },
    };
    const version = versionOut(experiment, {
      approval: api.stages.experiment?.attempts[0]?.outputs[0]?.approval ?? null,
    });
    api.stages.experiment = stageDetailOut(RUN_ID, "experiment", [
      attemptOut(1, [version], { status: "approved" }),
    ]);
    navigation.search = "stage=experiment";
    const { container } = renderRunPage();
    await waitForRun();

    const metrics = await screen.findByRole("region", { name: "Final metrics" });
    const tiles = within(metrics).getAllByRole("term");
    expect(tiles.map((tile) => tile.textContent)).toEqual([
      "abs_relHeadline",
      "rmse",
      "val_loss",
      "train_loss",
      "delta1",
    ]);
    const missing = tiles[4]?.parentElement?.querySelector("dd") as HTMLElement;
    expect(within(missing).getByText("not measured")).toBeTruthy();
    expect(missing.textContent).not.toMatch(/\d/);
    expect(within(metrics).getAllByText("0.1569").length).toBeGreaterThan(0);
    expect(container.querySelector("[data-headline] .studio-beam")).not.toBeNull();

    const titles = screen
      .getAllByRole("figure")
      .map((figure) => figure.querySelector("figcaption")?.textContent);
    expect(titles).toEqual(["loss per epoch", "abs_rel per epoch", "rmse per epoch"]);
    expect(screen.getByText("Container image")).toBeTruthy();
    expect(screen.getByRole("region", { name: "Training log" })).toBeTruthy();
    expect(screen.getByRole("region", { name: "Last lines of the training log" })).toBeTruthy();
  });

  it("draws the experiment's live training curves while it trains, then its stored series", async () => {
    api.run = experimentRun(stageRunOut("experiment", "running"));
    api.stages.experiment = stageDetailOut(RUN_ID, "experiment", [
      attemptOut(1, [], { status: "running" }),
    ]);
    navigation.search = "stage=experiment";
    renderRunPage();
    await waitForRun();
    const running = await screen.findByRole("heading", { level: 4, name: "Experiment is running" });
    const live = screen.getByRole("region", { name: "Live training curves" });
    expect(within(live).getByText("The curves appear here after the first epoch.")).toBeTruthy();

    send(runEvent("stage.started", { stage: "experiment", attempt: 1 }), epochEvent(0, 0.91));
    expect(await within(live).findByText("1 epoch so far")).toBeTruthy();
    expect(chartTitles(live)).toEqual([
      "loss per epoch",
      "rmse per epoch",
      "mae per epoch",
      "abs_rel per epoch",
    ]);

    // Each epoch extends the curves; one not measured is a gap, never 0.
    send(epochEvent(1, null), epochEvent(2, 0.62));
    expect(await within(live).findByText("3 epochs so far")).toBeTruthy();
    expect(within(live).getByText("Latest: Epoch 2: val RMSE 0.62")).toBeTruthy();
    const table = within(live).getByRole("table", { name: "rmse per epoch: values per epoch" });
    expect(
      [...table.querySelectorAll("tbody tr")].map((row) =>
        [...row.children].map((cell) => cell.textContent),
      ),
    ).toEqual([
      ["0", "0.91", "0.6"],
      ["1", "No value", "0.6"],
      ["2", "0.62", "0.6"],
    ]);
    // The running card's newest step is the epoch.
    const card = running.closest("[aria-busy]") as HTMLElement;
    expect(card.textContent).toContain("Latest stepEpoch 2: val RMSE 0.62");

    // The output is ready (and approved by itself): the stored series take over.
    const { version, output } = outputPair(DEMO_EXPERIMENT, {
      degraded: false,
      degraded_reason: null,
      approval: approvedBy("Alice"),
    });
    api.stages.experiment = stageDetailOut(RUN_ID, "experiment", [
      attemptOut(1, [version], { status: "approved" }),
    ]);
    api.run = experimentRun(stageRunOut("experiment", "approved", { outputs: [output] }));
    send(runEvent("stage.output_ready", { stage: "experiment", attempt: 1 }));
    expect(await screen.findByRole("region", { name: "Final metrics" })).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Live training curves" })).toBeNull();
    expect(chartTitles(screen.getByRole("region", { name: "Training curves" }))).toEqual([
      "loss per epoch",
      "abs_rel per epoch",
      "rmse per epoch",
    ]);
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
    api.stages.experiment = stageDetailOut(RUN_ID, "experiment", [
      attemptOut(1, [earlier], { status: "changes_requested" }),
      attemptOut(2, [], { status: "running", feedback: "Train longer" }),
    ]);
    api.run = experimentRun(stageRunOut("experiment", "running", { attempt: 2 }));
    navigation.search = "stage=experiment";
    renderRunPage();
    await waitForRun();
    expect(
      await screen.findByText("Attempt 2 is running. You are looking at an earlier output."),
    ).toBeTruthy();
    const live = screen.getByRole("region", { name: "Live training curves of attempt 2" });
    send(runEvent("stage.started", { stage: "experiment", attempt: 2 }), epochEvent(0, 0.88));
    expect(await within(live).findByText("1 epoch so far")).toBeTruthy();
    expect(screen.getByRole("region", { name: "Training curves" })).toBeTruthy();
  });

  it("offers the training checkpoint with its size, next to the log and in the downloads", async () => {
    seedCompletedRun();
    const experimentId = api.stages.experiment?.attempts[0]?.outputs[0]?.id ?? "";
    api.artifacts = {
      run_id: RUN_ID,
      items: [
        artifact("experiment", "experiment_log", "experiment.log", experimentId),
        {
          ...artifact("experiment", "checkpoint", "best.pt", experimentId),
          media_type: "application/octet-stream",
          size_bytes: 48_234_496,
        },
      ],
      demo: false,
    };
    navigation.search = "stage=experiment";
    renderRunPage();
    await waitForRun();

    const download = await screen.findByRole("link", { name: /Download the checkpoint/ });
    expect(download.getAttribute("download")).toBe("best.pt");
    expect(download.getAttribute("href")).toMatch(
      new RegExp(`/api/v1/artifacts/${experimentId}\\.checkpoint\\.best\\.pt$`),
    );
    expect(download.textContent).toBe("Download the checkpoint46 MB");

    fireEvent.click(screen.getByRole("button", { name: /^Downloads/ }));
    const item = await screen.findByRole("menuitem", { name: /best\.pt/ });
    expect(item.textContent).toBe("best.ptModel checkpoint · 46 MB");
  });

  it("renders the writing output: draft with contents and citations, outline and downloads", async () => {
    seedCompletedRun();
    const writingId = api.stages.writing?.attempts[0]?.outputs[0]?.id ?? "";
    api.artifacts = {
      run_id: RUN_ID,
      items: [
        artifact("writing", "draft", "draft.md", writingId),
        artifact("writing", "references", "references.bib", writingId),
      ],
      demo: true,
    };
    navigation.search = "stage=writing";
    renderRunPage();
    await waitForRun();

    const panel = await screen.findByRole("tabpanel");
    expect(await within(panel).findByRole("heading", { name: "Outline" })).toBeTruthy();
    expect(within(panel).getByText("Related Work")).toBeTruthy();
    expect(within(panel).getByRole("navigation", { name: "Contents" })).toBeTruthy();
    const citation = within(panel).getByRole("button", {
      name: `Citation 1: ${DEMO_LITERATURE.papers[0]?.title}`,
    });
    fireEvent.click(citation);
    const sheet = await screen.findByRole("dialog", { name: DEMO_LITERATURE.papers[0]?.title });
    expect(within(sheet).getByText("Citation [1]")).toBeTruthy();
    fireEvent.click(within(sheet).getByRole("button", { name: "Close" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    await waitFor(() =>
      expect(
        within(panel)
          .getByRole("link", { name: /draft\.md/ })
          .getAttribute("download"),
      ).toBe("draft.md"),
    );
  });

  it("says why the experiment failed, in words", async () => {
    api.run = runDetailOut({
      status: "failed",
      error: "experiment.invalid_code_config",
      stages: [
        stageRunOut("literature", "approved"),
        stageRunOut("method", "approved"),
        stageRunOut("coding", "approved"),
        stageRunOut("experiment", "failed", { error: "experiment.invalid_code_config" }),
      ],
    });
    api.stages.experiment = stageDetailOut(RUN_ID, "experiment", [
      attemptOut(1, [], { status: "failed", error: "experiment.invalid_code_config" }),
    ]);
    navigation.search = "stage=experiment";
    renderRunPage();
    await waitForRun();
    const message =
      "The approved code's config.json cannot be trained (an edit on approval may have broken it). Retry the run from the coding stage.";
    expect(
      await screen.findByRole("heading", { level: 4, name: "Experiment failed" }),
    ).toBeTruthy();
    expect(screen.getAllByText(message).length).toBeGreaterThanOrEqual(2);
  });

  it("explains stages the run has not reached", async () => {
    api.run = runDetailOut({ status: "running", stages: [stageRunOut("literature", "running")] });
    navigation.search = "stage=method";
    renderRunPage();
    await waitForRun();
    expect(
      await screen.findByRole("heading", { level: 4, name: "Method has not started" }),
    ).toBeTruthy();
    expect(screen.getByText("It starts once the Literature output is approved.")).toBeTruthy();
  });

  it("shows output that fails its stage's schema as JSON", async () => {
    const { version, output } = outputPair({ summary: "placeholder" }, { schema_ok: false });
    api.run = runDetailOut({
      status: "completed",
      stages: [stageRunOut("literature", "approved", { outputs: [output] })],
    });
    api.stages.literature = stageDetailOut(RUN_ID, "literature", [
      attemptOut(1, [version], { status: "approved" }),
    ]);
    renderRunPage();
    await waitForRun();
    expect(await screen.findByRole("heading", { name: "Shown as JSON" })).toBeTruthy();
    expect(screen.getByText(/does not match the stage's format/)).toBeTruthy();
    const json = screen.getByRole("region", { name: "Stage output (JSON)" });
    expect(json.textContent).toContain('"summary": "placeholder"');
  });
});

describe("StudioRunPage stage selection", () => {
  it("opens the stage named in the URL and writes the chosen stage back to it", async () => {
    seedCompletedRun();
    navigation.search = "stage=method";
    const replaceState = vi.spyOn(window.history, "replaceState");
    renderRunPage();
    await waitForRun();

    const tabs = screen.getByRole("tablist", { name: "Stages" });
    expect(
      within(tabs).getByRole("tab", { name: "Method, Approved" }).getAttribute("aria-selected"),
    ).toBe("true");
    fireEvent.click(within(tabs).getByRole("tab", { name: "Coding, Approved" }));
    expect(
      within(tabs).getByRole("tab", { name: "Coding, Approved" }).getAttribute("aria-selected"),
    ).toBe("true");
    expect(String(replaceState.mock.calls.at(-1)?.[2])).toMatch(/\?stage=coding$/);

    fireEvent.click(screen.getByRole("button", { name: "Writing: Approved" }));
    expect(
      within(tabs).getByRole("tab", { name: "Writing, Approved" }).getAttribute("aria-selected"),
    ).toBe("true");
    expect(
      screen.getByRole("button", { name: "Writing: Approved" }).getAttribute("aria-pressed"),
    ).toBe("true");
    expect(String(replaceState.mock.calls.at(-1)?.[2])).toMatch(/\?stage=writing$/);
    replaceState.mockRestore();
  });

  it("opens the output waiting for review when the URL names no stage", async () => {
    const { version, output } = outputPair(DEMO_OUTPUTS.method);
    api.run = runDetailOut({
      status: "awaiting_approval",
      can_steer: false,
      stages: [
        stageRunOut("literature", "approved"),
        stageRunOut("method", "output_ready", { outputs: [output] }),
      ],
      awaiting: output,
      awaiting_stage: "method",
    });
    api.stages.method = stageDetailOut(RUN_ID, "method", [attemptOut(1, [version])]);
    renderRunPage();
    await waitForRun();
    expect(
      screen.getByRole("tab", { name: "Method, Needs review" }).getAttribute("aria-selected"),
    ).toBe("true");
    expect(await screen.findByRole("heading", { name: "Research gaps" })).toBeTruthy();
  });

  it("keeps the active tab in view when the tab list scrolls", async () => {
    seedCompletedRun();
    navigation.search = "stage=writing";
    const scrollTo = vi.fn();
    const original = Object.getOwnPropertyDescriptors(HTMLElement.prototype);
    Object.defineProperties(HTMLElement.prototype, {
      scrollWidth: { configurable: true, get: () => 600 },
      clientWidth: { configurable: true, get: () => 300 },
      offsetWidth: { configurable: true, get: () => 100 },
      offsetLeft: {
        configurable: true,
        get(this: HTMLElement) {
          const tabs = this.parentElement ? [...this.parentElement.children] : [];
          return tabs.indexOf(this) * 110;
        },
      },
    });
    HTMLElement.prototype.scrollTo = scrollTo as typeof HTMLElement.prototype.scrollTo;
    try {
      renderRunPage();
      await waitForRun();
      // Writing (the fifth tab, at 440-540px) is past the 300px the list shows.
      await waitFor(() =>
        expect(scrollTo).toHaveBeenCalledWith(expect.objectContaining({ left: 252 })),
      );
    } finally {
      // scrollWidth and clientWidth live on Element.prototype: drop the overrides to reach them.
      for (const name of ["scrollWidth", "clientWidth", "offsetWidth", "offsetLeft"] as const) {
        const descriptor = Object.hasOwn(original, name) ? original[name] : undefined;
        if (descriptor) {
          Object.defineProperty(HTMLElement.prototype, name, descriptor);
        } else {
          Reflect.deleteProperty(HTMLElement.prototype, name);
        }
      }
      Reflect.deleteProperty(HTMLElement.prototype, "scrollTo");
    }
  });
});

describe("StudioRunPage live log", () => {
  it("shows translated progress, model calls with their cost, outdated stages and retries", async () => {
    api.run = runDetailOut({ status: "running", stages: [stageRunOut("literature", "running")] });
    renderRunPage();
    await waitForRun();
    send(
      runEvent("log", {
        stage: "literature",
        code: "demo.search",
        params: { sources: ["arxiv", "openalex"], queries: 4 },
        message: "Searching arXiv, OpenAlex with 4 queries",
      }),
      runEvent("llm.call", {
        stage: "literature",
        model: "openai/gpt-4o-mini",
        tier: "paid",
        cost_usd: "0.0125",
      }),
      runEvent("stage.invalidated", {
        stage: "method",
        attempt: 1,
        stage_run_id: "x",
        retry_stage: "literature",
      }),
      runEvent("run.retried", { stage: "literature", requested_stage: "literature" }),
      runEvent("log", { stage: "method", code: "demo.unknown", message: "Plain fallback" }),
    );
    const log = await screen.findByRole("log", { name: "Live log" });
    await waitFor(() => expect(within(log).getAllByRole("listitem")).toHaveLength(5));
    const lines = within(log)
      .getAllByRole("listitem")
      .map((line) => line.textContent ?? "");
    expect(lines[0]).toContain("LiteratureSearching arXiv and OpenAlex with 4 queries");
    expect(lines[1]).toContain("LLM call · openai/gpt-4o-mini (paid) · $0.0125");
    expect(lines[2]).toContain("Method: attempt 1 is outdated after the retry from Literature");
    expect(lines[3]).toContain("Run restarted from Literature");
    expect(lines[4]).toContain("Plain fallback");

    fireEvent.click(screen.getByRole("button", { name: /^Model calls/ }));
    await waitFor(() => expect(within(log).getAllByRole("listitem")).toHaveLength(1));
  });
});

describe("StudioRunPage waiting and refreshing", () => {
  it("shows a stage that waits, why, and when it tries again by itself", async () => {
    api.run = runDetailOut({ status: "running", stages: [stageRunOut("literature", "running")] });
    renderRunPage();
    await waitForRun();
    send(
      runEvent("stage.waiting", {
        stage: "literature",
        attempt: 1,
        reason: "free_quota.unavailable",
        retry_at: "2099-01-01T03:00:00Z",
      }),
    );
    const callout = (await screen.findByText("Literature is waiting")).closest(
      "[data-tone]",
    ) as HTMLElement;
    expect(callout.textContent).toContain("No free model is available right now.");
    expect(callout.textContent).toMatch(/It tries again by itself at Jan 1, 12:00\sPM\./);
    expect(screen.getByRole("tab", { name: /^Literature, Running, Waiting/ })).toBeTruthy();

    send(runEvent("log", { stage: "literature", message: "Searching again" }));
    await waitFor(() => expect(screen.queryByText("Literature is waiting")).toBeNull());
    expect(screen.getByRole("tab", { name: /^Literature, Running$/ })).toBeTruthy();
  });

  it("says a run paused for the lab balance continues by itself, and when it checks again", async () => {
    api.run = runDetailOut({
      status: "paused_budget",
      stages: [stageRunOut("literature", "running")],
    });
    renderRunPage();
    await waitForRun();
    const notice = (await screen.findByText("Paused: the lab's LLM balance is used up")).closest(
      "[data-tone]",
    ) as HTMLElement;
    expect(notice.textContent).toContain(
      "The run continues by itself once the balance is topped up",
    );
    send(
      runEvent("stage.waiting", {
        stage: "literature",
        attempt: 1,
        reason: "lab_balance.exhausted",
        retry_at: "2099-01-01T03:15:00Z",
      }),
    );
    await waitFor(() =>
      expect(notice.textContent).toMatch(/The balance is checked again at Jan 1, 12:15\sPM\./),
    );
  });

  it("shows the spend total from the run detail, failed attempts included", async () => {
    api.run = runDetailOut({
      status: "running",
      stages: [stageRunOut("literature", "running")],
      spend_usd: "0.75",
    });
    renderRunPage();
    await waitForRun();
    await waitFor(() => expect(screen.getAllByText("$0.75").length).toBeGreaterThan(0));
  });
});

describe("StudioRunPage celebration", () => {
  it("bursts confetti once when the run completes on the page", async () => {
    api.run = runDetailOut({
      status: "running",
      stages: [stageRunOut("literature", "approved"), stageRunOut("writing", "running")],
    });
    renderRunPage();
    await waitForRun();
    expect(confetti).not.toHaveBeenCalled();

    api.run = { ...api.run, status: "completed" };
    send(runEvent("run.status", { status: "completed", error: null }));
    await waitFor(() => expect(confetti).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("Every stage is approved")).toBeTruthy();

    // Later updates of the completed run stay calm.
    send(runEvent("stage.decided", { stage: "writing", decision: "approve" }));
    await new Promise((resolve) => setTimeout(resolve, 450));
    expect(confetti).toHaveBeenCalledTimes(1);
  });

  it("stays calm when the page opens on a completed run", async () => {
    seedCompletedRun();
    renderRunPage();
    await waitForRun();
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(confetti).not.toHaveBeenCalled();
  });

  it("stays calm when the run completes while the page is hidden", async () => {
    api.run = runDetailOut({ status: "running", stages: [stageRunOut("writing", "running")] });
    renderRunPage();
    await waitForRun();
    Object.defineProperty(document, "visibilityState", { configurable: true, get: () => "hidden" });
    api.run = { ...api.run, status: "completed" };
    send(runEvent("run.status", { status: "completed", error: null }));
    expect(await screen.findByText("Every stage is approved")).toBeTruthy();
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(confetti).not.toHaveBeenCalled();
  });
});
