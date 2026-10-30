// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { DatasetList, RunEstimateOut, RunOut } from "@/client";
import { json, mockApi } from "@/hooks/run-hooks.fixtures";
import { RUN_CONFIG_DEFAULTS } from "@/lib/new-run-schema";
import { installBrowserStubs, renderPage } from "../test-utils";
import { NewRunWizard } from "./new-run-wizard";

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));

const PROJECT = "33333333-3333-4333-8333-333333333333";
const TOPIC = "Monocular depth estimation on NYU Depth v2";

const ESTIMATE: RunEstimateOut = {
  llm_policy: "auto",
  low_usd: "0.08",
  expected_usd: "0.21",
  high_usd: "0.55",
  calls_low: 30,
  expected_calls: 42,
  calls_high: 60,
  paid_possible: true,
  paid_blocked_by: null,
  paid_models_enabled: true,
  budget_remaining_usd: "18.00",
  capped_by: null,
  assumptions: {
    paid_chain: [
      {
        id: "anthropic/claude-sonnet",
        prompt_usd_per_mtok: "3",
        completion_usd_per_mtok: "15",
        known: true,
      },
    ],
    steps: [
      {
        stage: "literature",
        role: "screener",
        calls_low: 10,
        calls_expected: 14,
        calls_high: 20,
        prompt_tokens_per_call: 1200,
        completion_tokens_per_call: 300,
        low_usd: "0.02",
        expected_usd: "0.05",
        high_usd: "0.09",
      },
    ],
  },
  demo: true,
};

const DATASETS: DatasetList = {
  demo: true,
  items: [
    {
      id: "nyu2",
      name: "NYU Depth V2",
      version: "1.0",
      tasks: ["depth"],
      modality: "RGB-D",
      scenes: "indoor",
      description: "Indoor scenes from a Kinect camera.",
      width: 640,
      height: 480,
      samples: 1449,
      splits: [
        { name: "train", samples: 795 },
        { name: "test", samples: 654 },
      ],
      size_bytes: 2_800_000_000,
      license: "CC BY 4.0",
      homepage: null,
      mount_path: "/datasets/nyu2",
      checksum_sha256: "a".repeat(64),
      registered_at: "2026-10-01T00:00:00Z",
      contract: {
        inputs: "RGB",
        targets: "depth",
        units: "m",
        valid_range: null,
        missing_values: null,
        evaluation: null,
      },
      demo: true,
    },
  ],
};

const RUN: RunOut = {
  id: "22222222-2222-4222-8222-222222222222",
  project_id: PROJECT,
  owner_id: "user-owner",
  topic: TOPIC,
  status: "queued",
  llm_policy: "auto",
  budget_cap_usd: null,
  config: { ...RUN_CONFIG_DEFAULTS },
  error: null,
  created_at: "2026-10-30T00:00:00Z",
  updated_at: "2026-10-30T00:00:00Z",
};

let estimates: unknown[];
let created: unknown[];
let createResponse: () => Response;
let datasets: DatasetList = DATASETS;

beforeAll(() => {
  installBrowserStubs();
});

beforeEach(() => {
  estimates = [];
  created = [];
  createResponse = () => json(201, RUN);
  datasets = DATASETS;
  mockApi(async (request, path) => {
    if (path === "/api/v1/runs/estimate") {
      estimates.push(await request.json());
      return json(200, ESTIMATE);
    }
    if (path === "/api/v1/datasets") {
      return json(200, datasets);
    }
    if (path === `/api/v1/projects/${PROJECT}/runs` && request.method === "POST") {
      created.push(await request.json());
      return createResponse();
    }
    return json(404, { detail: "project.not_found" });
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderWizard() {
  return renderPage(<NewRunWizard projectId={PROJECT} allowFreeModels estimateDebounceMs={10} />);
}

const stepHeading = () => screen.getByRole("heading", { level: 2 }).textContent;
const button = (name: string) => screen.getByRole("button", { name });

async function expectStep(title: string) {
  await waitFor(() => expect(stepHeading()).toBe(title));
}

async function fillTopicAndContinue() {
  fireEvent.change(screen.getByRole("textbox", { name: "Research topic" }), {
    target: { value: TOPIC },
  });
  fireEvent.click(button("Next"));
  await expectStep("Literature");
}

describe("NewRunWizard steps", () => {
  it("checks each step before moving on and keeps the values when going back", async () => {
    renderWizard();
    expect(stepHeading()).toBe("Topic");

    fireEvent.click(button("Next"));
    expect(await screen.findByText("Describe the topic in at least 3 characters.")).toBeTruthy();
    expect(stepHeading()).toBe("Topic");

    await fillTopicAndContinue();
    fireEvent.click(button("Back"));
    await expectStep("Topic");
    expect(
      (screen.getByRole("textbox", { name: "Research topic" }) as HTMLTextAreaElement).value,
    ).toBe(TOPIC);

    fireEvent.click(button("Next"));
    await expectStep("Literature");
    fireEvent.change(screen.getByRole("spinbutton", { name: "From" }), {
      target: { value: "2025" },
    });
    fireEvent.change(screen.getByRole("spinbutton", { name: "To" }), {
      target: { value: "2020" },
    });
    fireEvent.click(button("Next"));
    expect(await screen.findByText("The first year must not be after the last one.")).toBeTruthy();
    expect(stepHeading()).toBe("Literature");

    fireEvent.change(screen.getByRole("spinbutton", { name: "From" }), {
      target: { value: "2019" },
    });
    fireEvent.click(button("Next"));
    await expectStep("Stages");
  });

  it("shows the chosen dataset's facts, its size unknown until it is measured (never 0)", async () => {
    renderWizard();
    await fillTopicAndContinue();
    fireEvent.click(button("Next"));
    await expectStep("Stages");
    expect(await screen.findByText("1,449 samples · 2.6 GB · RGB-D · CC BY 4.0")).toBeTruthy();
    cleanup();

    datasets = {
      ...DATASETS,
      items: DATASETS.items.map((item) => ({ ...item, size_bytes: null, checksum_sha256: null })),
    };
    renderWizard();
    await fillTopicAndContinue();
    fireEvent.click(button("Next"));
    await expectStep("Stages");
    expect(
      await screen.findByText("1,449 samples · size unknown · RGB-D · CC BY 4.0"),
    ).toBeTruthy();
  });

  it("asks for at least one source", async () => {
    renderWizard();
    await fillTopicAndContinue();
    for (const source of ["arXiv", "Semantic Scholar", "OpenAlex"]) {
      fireEvent.click(screen.getByRole("checkbox", { name: source }));
    }
    fireEvent.click(button("Next"));
    expect(await screen.findByText("Tick at least one source.")).toBeTruthy();
    expect(stepHeading()).toBe("Literature");
  });

  it("stops the pipeline after the chosen stage and estimates that run", async () => {
    renderWizard();
    await fillTopicAndContinue();
    fireEvent.click(button("Next"));
    await expectStep("Stages");

    fireEvent.click(screen.getByRole("radio", { name: "Coding" }));
    const preview = screen.getByRole("list", { name: "Stages of this run" });
    expect(within(preview).getByText("Experiment").textContent).toBe("Experimentnot run");
    expect(within(preview).getByText("Coding").textContent).toBe("Codingincluded");
    expect(
      screen.getByText("This run stops before the experiment, so it does not use a dataset."),
    ).toBeTruthy();

    fireEvent.click(button("Next"));
    await expectStep("Models and budget");
    fireEvent.click(button("Review"));
    await expectStep("Review");

    expect(screen.getByText("Literature → Method → Coding")).toBeTruthy();
    expect(await screen.findByText("$0.08 – $0.55")).toBeTruthy();
    expect(screen.getByText(/about 42 LLM calls \(30–60\)/)).toBeTruthy();
    expect(screen.getByText("Assumed calls per step")).toBeTruthy();
    expect(screen.getByText("Screening")).toBeTruthy();
    expect(screen.getAllByText("Demo").length).toBeGreaterThan(0);
    await waitFor(() =>
      expect(estimates.at(-1)).toMatchObject({
        config: { stages: ["literature", "method", "coding"] },
      }),
    );
  });
});

describe("NewRunWizard start", () => {
  it("starts the run from the review and opens its page", async () => {
    renderWizard();
    fireEvent.change(screen.getByRole("textbox", { name: "Research topic" }), {
      target: { value: TOPIC },
    });
    // The step list jumps straight to the review once every step is valid.
    fireEvent.click(screen.getByRole("button", { name: "Step 5 of 5: Review" }));
    await expectStep("Review");

    fireEvent.click(button("Start run"));
    await waitFor(() => expect(router.push).toHaveBeenCalledWith(`/runs/${RUN.id}`));
    expect(created).toEqual([
      {
        topic: TOPIC,
        llm_policy: "auto",
        budget_cap_usd: null,
        config: { ...RUN_CONFIG_DEFAULTS },
      },
    ]);
    expect(toast.success).toHaveBeenCalledWith("Run started.");
  });

  it("shows a value the API refused on the step it belongs to", async () => {
    createResponse = () =>
      json(422, {
        detail: [
          {
            loc: ["body", "config", "max_papers"],
            msg: "Input should be less than or equal to 50",
            type: "less_than_equal",
          },
        ],
      });
    renderWizard();
    fireEvent.change(screen.getByRole("textbox", { name: "Research topic" }), {
      target: { value: TOPIC },
    });
    fireEvent.click(screen.getByRole("button", { name: "Step 5 of 5: Review" }));
    await expectStep("Review");

    fireEvent.click(button("Start run"));
    await expectStep("Literature");
    expect(await screen.findByText("Choose between 5 and 50 papers.")).toBeTruthy();
    expect(router.push).not.toHaveBeenCalled();
  });
});
