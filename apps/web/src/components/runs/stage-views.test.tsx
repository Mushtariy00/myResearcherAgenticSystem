// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactElement } from "react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { ArtifactList, ArtifactOut, ExperimentOutput, WritingOutput } from "@/client";
import { listRunArtifactsQueryKey } from "@/client/@tanstack/react-query.gen";
import { client } from "@/client/client.gen";
import type { PdfViewerProps } from "@/components/shared/pdf-viewer-types";
import { configureApiClient } from "@/lib/api-client";
import {
  DEMO_CODING,
  DEMO_EXPERIMENT,
  DEMO_LITERATURE,
  DEMO_METHOD,
  DEMO_WRITING,
} from "@/lib/stage-output.fixtures";
import { enMessages } from "@/test/messages";
import { StageOutputView } from "./views/stage-output-view";

// ECharts draws on canvas, which jsdom lacks (the chart is covered by its own tests).
vi.mock("@/components/shared/metrics-chart-echarts", () => ({
  init: () => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() }),
}));

// PDF.js cannot run in jsdom: a stand-in shows what the viewer was given.
vi.mock("@/components/shared/pdf-viewer", () => ({
  PdfViewer: (props: PdfViewerProps) => (
    <div
      data-testid="pdf-viewer"
      data-url={props.url}
      data-active={props.activeQuote}
      data-quotes={JSON.stringify(props.quotes ?? [])}
    />
  ),
}));

const RUN_ID = "22222222-2222-4222-8222-222222222222";
const OUTPUT_ID = "44444444-4444-4444-8444-444444444444";

function artifact(kind: ArtifactOut["kind"], stage: string, filename: string): ArtifactOut {
  return {
    id: `${OUTPUT_ID}.${kind}`,
    stage,
    kind,
    filename,
    path: null,
    media_type: "text/plain",
    size_bytes: 2048,
    sha256: "c".repeat(64),
    stage_output_id: OUTPUT_ID,
    version: 1,
    created_at: "2026-10-30T01:00:00Z",
    demo: true,
  };
}

const ARTIFACTS: ArtifactList = {
  run_id: RUN_ID,
  items: [
    artifact("code_archive", "coding", "run-code.zip"),
    artifact("experiment_log", "experiment", "run-experiment.log"),
    artifact("metrics", "experiment", "run-metrics.csv"),
    {
      ...artifact("checkpoint", "experiment", "best.pt"),
      media_type: "application/octet-stream",
      size_bytes: 48_234_496,
    },
    artifact("draft", "writing", "run-draft.md"),
    artifact("references", "writing", "run-references.bib"),
  ],
  demo: true,
};

const fetchMock = vi.fn<typeof fetch>();

beforeAll(() => {
  Element.prototype.scrollIntoView = () => {};
  HTMLCanvasElement.prototype.getContext = (() =>
    null) as typeof HTMLCanvasElement.prototype.getContext;
});

beforeEach(() => {
  configureApiClient();
  // Same-origin download links, as in the browser; nothing here may reach the network.
  client.setConfig({ baseUrl: undefined, fetch: fetchMock });
});

afterEach(() => {
  cleanup();
  fetchMock.mockReset();
});

function renderView(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  });
  queryClient.setQueryData(listRunArtifactsQueryKey({ path: { run_id: RUN_ID } }), ARTIFACTS);
  return render(
    <QueryClientProvider client={queryClient}>
      <NextIntlClientProvider locale="en" messages={enMessages} timeZone="Asia/Seoul">
        {ui}
      </NextIntlClientProvider>
    </QueryClientProvider>,
  );
}

const view = (
  narrowed: Parameters<typeof StageOutputView>[0]["narrowed"],
  outputId = OUTPUT_ID,
) => (
  <StageOutputView
    runId={RUN_ID}
    outputId={outputId}
    narrowed={narrowed}
    literature={DEMO_LITERATURE}
  />
);

describe("literature view", () => {
  it("shows the plan, filters papers by decision and opens a paper with its notes and PDF", async () => {
    renderView(view({ kind: "literature", stage: "literature", data: DEMO_LITERATURE }));
    expect(screen.getByRole("heading", { name: "Research plan" })).toBeTruthy();
    expect(screen.getByText(DEMO_LITERATURE.plan.queries[0] ?? "")).toBeTruthy();
    expect(screen.getByText("Geometric priors")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Synthesis" })).toBeTruthy();

    const table = screen.getByRole("table", { name: "Papers found by the literature search" });
    expect(within(table).getAllByRole("row")).toHaveLength(1 + 5);
    fireEvent.click(screen.getByRole("radio", { name: "Excluded: 1" }));
    expect(within(table).getAllByRole("row")).toHaveLength(1 + 1);
    expect(within(table).getByText(/NOVA-Plus/)).toBeTruthy();
    fireEvent.click(screen.getByRole("radio", { name: "All: 5" }));

    const title = "When Does Synthetic Data Help Monocular Depth Estimation on NYU Depth v2?";
    fireEvent.click(within(table).getByRole("button", { name: title }));
    const sheet = await screen.findByRole("dialog", { name: title });
    expect(within(sheet).getByText(/DepthNet-XL reaches AbsRel 0.109/)).toBeTruthy();
    expect(
      within(sheet).getByText("On NYU Depth V2, DepthNet-XL achieves AbsRel of 0.109.", {
        exact: false,
      }),
    ).toBeTruthy();
    expect(
      within(sheet)
        .getByRole("link", { name: /DOI page/ })
        .getAttribute("href"),
    ).toBe("https://doi.org/10.5555/ieeetip.2024.94516");

    fireEvent.click(within(sheet).getByRole("button", { name: "Open quote 1 in the PDF, page 6" }));
    const pdf = within(sheet).getByTestId("pdf-viewer");
    expect(pdf.getAttribute("data-url")).toBe("/api/v1/papers/arxiv%3A2412.99517/file");
    expect(pdf.getAttribute("data-active")).toBe("0");
    expect(JSON.parse(pdf.getAttribute("data-quotes") ?? "[]")).toEqual([
      { quote: "On NYU Depth V2, DepthNet-XL achieves AbsRel of 0.109.", page: 6 },
    ]);
    fireEvent.click(within(sheet).getByRole("button", { name: "Back to the paper" }));
    expect(within(sheet).queryByTestId("pdf-viewer")).toBeNull();
  });
});

describe("method view", () => {
  it("highlights the recommended proposal and opens its evidence papers", async () => {
    const { container } = renderView(view({ kind: "method", stage: "method", data: DEMO_METHOD }));
    const recommended = container.querySelectorAll('[data-slot="proposal-card"][data-recommended]');
    expect(recommended).toHaveLength(1);
    expect(recommended[0]?.textContent).toContain(DEMO_METHOD.recommended_option);
    expect(screen.getByText(DEMO_METHOD.research_gaps[0] ?? "")).toBeTruthy();
    expect(screen.getByText("abs_rel")).toBeTruthy();

    const card = recommended[0] as HTMLElement;
    fireEvent.click(within(card).getByRole("button", { name: /Revisiting Monocular Depth/ }));
    expect(
      await screen.findByRole("dialog", {
        name: "Revisiting Monocular Depth Estimation on NYU Depth v2: A Large-Scale Benchmark",
      }),
    ).toBeTruthy();
  });
});

describe("coding view", () => {
  it("shows the smoke test, the files with the archive and a comparison with the attempt before", () => {
    renderView(
      <StageOutputView
        runId={RUN_ID}
        outputId={OUTPUT_ID}
        narrowed={{ kind: "coding", stage: "coding", data: DEMO_CODING }}
        literature={null}
        codingBase={{
          relation: "attempt",
          attempt: 1,
          version: 1,
          files: DEMO_CODING.files.map((file) =>
            file.path === "losses.py" ? { ...file, content: "import torch\n" } : file,
          ),
        }}
      />,
    );
    expect(screen.getByText("model.py:DepthNet")).toBeTruthy();
    expect(screen.getByText("Passed")).toBeTruthy();
    expect(screen.getByRole("region", { name: "Smoke test log" }).textContent).toContain(
      "4 passed in 8.28s",
    );
    expect(screen.getByRole("region", { name: "Contents of model.py" })).toBeTruthy();
    expect(screen.getByRole("link", { name: /Download all files/ }).getAttribute("href")).toBe(
      `/api/v1/artifacts/${OUTPUT_ID}.code_archive`,
    );

    const compare = screen.getByRole("button", { name: "Compare with attempt 1" });
    expect(compare.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(compare);
    expect(screen.getByText("1 file changed")).toBeTruthy();
    expect(screen.getByRole("region", { name: "Changes in losses.py" })).toBeTruthy();
  });

  it("offers no archive for a version the archive was not made from", () => {
    renderView(view({ kind: "coding", stage: "coding", data: DEMO_CODING }, "another-output"));
    expect(screen.queryByRole("link", { name: /Download all files/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Compare with/ })).toBeNull();
  });
});

describe("experiment view", () => {
  it("charts each metric, and says 'not measured' for a missing final metric (never 0)", () => {
    const data: ExperimentOutput = {
      ...DEMO_EXPERIMENT,
      final_metrics: { ...DEMO_EXPERIMENT.final_metrics, delta1: null },
    };
    renderView(view({ kind: "experiment", stage: "experiment", data }));
    expect(screen.getByText("Succeeded")).toBeTruthy();
    for (const metric of ["loss", "abs_rel", "rmse"]) {
      expect(screen.getByRole("figure", { name: `${metric} per epoch` })).toBeTruthy();
    }
    const finals = screen.getByRole("table", { name: "Final metrics" });
    const rows = within(finals)
      .getAllByRole("row")
      .slice(1)
      .map((row) => [...row.children].slice(0, 2).map((cell) => cell.textContent));
    expect(rows).toEqual([
      ["abs_rel", "0.1569"],
      ["rmse", "0.5734"],
      ["val_loss", "0.5401"],
      ["train_loss", "0.377"],
      ["delta1", "not measured"],
    ]);
    expect(screen.getByText("learning_rate")).toBeTruthy();
    expect(
      screen.getByRole("region", { name: "Last lines of the training log" }).textContent,
    ).toContain("epoch 21 step 800");
    expect(screen.getByText("NVIDIA GeForce GTX 1060 6GB")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Metrics \(CSV\)/ }).getAttribute("href")).toBe(
      `/api/v1/artifacts/${OUTPUT_ID}.metrics`,
    );
    // The model checkpoint is a binary download, with its size.
    const checkpoint = screen.getByRole("link", { name: /Checkpoint \(\.pt\)/ });
    expect(checkpoint.getAttribute("href")).toBe(`/api/v1/artifacts/${OUTPUT_ID}.checkpoint`);
    expect(checkpoint.getAttribute("download")).toBe("best.pt");
    expect(checkpoint.textContent).toBe("Checkpoint (.pt)(46 MB)");
  });
});

describe("writing view", () => {
  const hostile: WritingOutput = {
    ...DEMO_WRITING,
    title: '<img src=x onerror="window.__pwned=1"> Depth',
    abstract: "<script>window.__pwned = 1</script> An abstract.",
    markdown: [
      "# Draft",
      "",
      "## 1. Introduction",
      "",
      'Results [1] <img src="x" onerror="window.__pwned=1"> and <script>window.__pwned=1</script>.',
      "",
      "## 2. Method",
      "",
      "[click](javascript:alert(1)) and [3].",
    ].join("\n"),
  };

  it("renders a hostile draft inert, with contents, citations and downloads", async () => {
    const { container } = renderView(view({ kind: "writing", stage: "writing", data: hostile }));
    for (const tag of ["script", "img", "iframe"]) {
      expect(container.querySelector(tag), tag).toBeNull();
    }
    expect((window as { __pwned?: number }).__pwned).toBeUndefined();
    expect(screen.getByRole("heading", { name: hostile.title })).toBeTruthy();
    expect(screen.getByText(/<script>window.__pwned = 1<\/script> An abstract./)).toBeTruthy();
    expect(screen.getByText("click").closest("a")).toBeNull();
    expect(screen.getByRole("navigation", { name: "Contents" })).toBeTruthy();
    expect(screen.getByText(DEMO_WRITING.review_focus)).toBeTruthy();
    expect(screen.getByRole("link", { name: /Draft \(\.md\)/ }).getAttribute("href")).toBe(
      `/api/v1/artifacts/${OUTPUT_ID}.draft`,
    );
    expect(screen.getByRole("link", { name: /References \(\.bib\)/ })).toBeTruthy();

    fireEvent.click(
      screen.getByRole("button", {
        name: "Citation 3: When Does Synthetic Data Help Monocular Depth Estimation on NYU Depth v2?",
      }),
    );
    await waitFor(() =>
      expect(
        screen.getByRole("dialog", {
          name: "When Does Synthetic Data Help Monocular Depth Estimation on NYU Depth v2?",
        }),
      ).toBeTruthy(),
    );
  });
});

describe("raw output", () => {
  it("shows data that fails its stage's schema as JSON, with the reason", () => {
    const { container } = renderView(
      view({
        kind: "raw",
        stage: "method",
        data: { summary: "<b>placeholder</b>" },
        reason: "schema_failed",
      }),
    );
    expect(screen.getByText("This output does not match the Method format")).toBeTruthy();
    expect(screen.getByRole("region", { name: "Method output (JSON)" }).textContent).toContain(
      "<b>placeholder</b>",
    );
    expect(container.querySelector("b")).toBeNull();
  });
});
