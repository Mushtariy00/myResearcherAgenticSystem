// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  renderHook,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { DatasetList, RunEstimateOut, RunOut } from "@/client";
import { listDatasetsQueryKey } from "@/client/@tanstack/react-query.gen";
import { client } from "@/client/client.gen";
import { configureApiClient } from "@/lib/api-client";
import { RUN_CONFIG_DEFAULTS } from "@/lib/new-run-schema";
import { installDomFakes } from "@/studio/test/dom";
import { makeQueryClient, renderStudio, TEST_USER } from "@/studio/test/render";
import { enMessages } from "@/test/messages";
import { NewRunWizard } from "./new-run-wizard";
import { useWizardFieldError } from "./wizard-messages";

const router = vi.hoisted(() => ({
  push: vi.fn(),
  replace: vi.fn(),
  refresh: vi.fn(),
  prefetch: vi.fn(),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => router,
  usePathname: () => "/studio/projects/p1",
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const PROJECT = "33333333-3333-4333-8333-333333333333";

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
  assumptions: { paid_chain: [], steps: [] },
  demo: true,
};

const FREE_ESTIMATE: RunEstimateOut = {
  ...ESTIMATE,
  llm_policy: "free",
  low_usd: "0.00",
  expected_usd: "0.00",
  high_usd: "0.00",
  paid_possible: false,
  paid_blocked_by: "policy",
};

const RUN: RunOut = {
  id: "22222222-2222-4222-8222-222222222222",
  project_id: PROJECT,
  owner_id: TEST_USER.id,
  topic: "Monocular depth estimation",
  status: "queued",
  llm_policy: "auto",
  budget_cap_usd: null,
  config: { ...RUN_CONFIG_DEFAULTS },
  error: null,
  created_at: "2026-10-30T00:00:00Z",
  updated_at: "2026-10-30T00:00:00Z",
};

const DATASETS = {
  items: [
    {
      id: "nyu2",
      name: "NYU Depth V2",
      version: "1.0",
      tasks: ["depth"],
      modality: "RGB-D",
      scenes: "indoor",
      description: "Indoor scenes with depth.",
      width: 640,
      height: 480,
      samples: 1449,
      splits: [],
      size_bytes: 2_800_000_000,
      license: "CC BY",
      homepage: null,
      mount_path: "/data/nyu2",
      checksum_sha256: "abc",
      registered_at: "2026-01-01T00:00:00Z",
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
  demo: true,
} as DatasetList;

type Call = { method: string; path: string; body: unknown };
const fetchMock = vi.fn<typeof fetch>();
let calls: Call[] = [];

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const estimates = () => calls.filter((call) => call.path === "/api/v1/runs/estimate");
const creations = () => calls.filter((call) => call.path === `/api/v1/projects/${PROJECT}/runs`);

beforeAll(() => {
  installDomFakes();
});

beforeEach(() => {
  calls = [];
  configureApiClient();
  client.setConfig({ baseUrl: "http://localhost:8080", fetch: fetchMock });
  fetchMock.mockImplementation(async (input) => {
    const request = input as Request;
    const path = new URL(request.url).pathname;
    const body = request.method === "GET" ? undefined : await request.json();
    calls.push({ method: request.method, path, body });
    if (path === "/api/v1/runs/estimate") {
      const free = (body as { llm_policy?: string }).llm_policy === "free";
      return json(200, free ? FREE_ESTIMATE : ESTIMATE);
    }
    if (path === `/api/v1/projects/${PROJECT}/runs`) {
      return json(201, RUN);
    }
    return json(404, { detail: "run.not_found" });
  });
});

afterEach(() => {
  cleanup();
  fetchMock.mockReset();
  vi.clearAllMocks();
});

function renderWizard() {
  const queryClient = makeQueryClient();
  queryClient.setQueryData(listDatasetsQueryKey(), DATASETS);
  const onOpenChange = vi.fn();
  renderStudio(<NewRunWizard projectId={PROJECT} open onOpenChange={onOpenChange} />, {
    user: TEST_USER,
    queryClient,
  });
  return { onOpenChange, dialog: screen.getByRole("dialog") };
}

/** The current step's heading ("Step 2 of 4 Literature"), once it has slid in. */
async function stepHeading(title: string, step: number) {
  return screen.findByRole("heading", { name: `Step ${step} of 4 ${title}` }, { timeout: 3000 });
}

/** The message a field error code shows: the shared wizard copy once it exists, else Studio's. */
function message(code: string, values: Record<string, number> = {}): string {
  type Tree = { [key: string]: Tree | string };
  const find = (root: Tree | undefined, path: string[]) =>
    path.reduce<Tree | string | undefined>(
      (node, key) => (typeof node === "object" ? node[key] : undefined),
      root,
    );
  const path = code.split(".");
  const shared = find(enMessages as Tree, ["wizard", "errors", ...path]);
  const studio = find(enMessages as Tree, ["studioWork", "wizard", "errors", ...path]);
  const text = typeof shared === "string" ? shared : String(studio);
  return text.replace(/\{(\w+)\}/g, (_, key: string) => String(values[key] ?? `{${key}}`));
}

const next = () => fireEvent.click(screen.getByRole("button", { name: /^Next/ }));

describe("NewRunWizard steps", () => {
  it("walks the four steps, validating each before moving on", async () => {
    renderWizard();
    const first = await stepHeading("Topic", 1);
    // The dialog opens on the step's heading.
    await waitFor(() => expect(document.activeElement).toBe(first));

    next();
    const topic = await screen.findByRole("textbox", { name: "Research topic" });
    expect(await screen.findByText(message("topic.tooShort", { min: 3, max: 500 }))).toBeTruthy();
    expect(topic.getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByRole("heading", { name: "Step 1 of 4 Topic" })).toBeTruthy();

    fireEvent.change(topic, { target: { value: "Monocular depth estimation" } });
    next();
    const literature = await stepHeading("Literature", 2);
    await waitFor(() => expect(document.activeElement).toBe(literature));
    expect(screen.getByRole("spinbutton", { name: "Papers to keep" })).toBeTruthy();

    next();
    await stepHeading("Stages", 3);
    next();
    await stepHeading("Models and budget", 4);
    expect(screen.getByRole("button", { name: "Start run" })).toBeTruthy();

    // Back at once through the stepper; the values are kept.
    fireEvent.click(
      within(screen.getByRole("navigation", { name: "Steps" })).getByRole("button", {
        name: /Topic/,
      }),
    );
    await stepHeading("Topic", 1);
    expect(
      (screen.getByRole("textbox", { name: "Research topic" }) as HTMLTextAreaElement).value,
    ).toBe("Monocular depth estimation");
  });

  it("chooses where the run stops on the mini pipeline, and starts it", async () => {
    const { onOpenChange } = renderWizard();
    fireEvent.change(await screen.findByRole("textbox", { name: "Research topic" }), {
      target: { value: "Monocular depth estimation" },
    });
    next();
    await stepHeading("Literature", 2);
    next();
    await stepHeading("Stages", 3);

    const chooser = screen.getByRole("radiogroup", { name: "Stop after" });
    expect(within(chooser).getAllByRole("radio")).toHaveLength(5);
    fireEvent.click(within(chooser).getByRole("radio", { name: "Coding" }));
    expect(
      within(chooser).getByRole("radio", { name: "Coding" }).getAttribute("aria-checked"),
    ).toBe("true");
    expect(screen.getByText(/The run goes up to and including Coding\./)).toBeTruthy();
    expect(screen.getByText(/Not run: Experiment and Writing\./)).toBeTruthy();
    expect(screen.getByRole("radiogroup", { name: "Dataset" })).toBeTruthy();
    expect(screen.getByText("NYU Depth V2")).toBeTruthy();

    next();
    await stepHeading("Models and budget", 4);
    fireEvent.click(screen.getByRole("button", { name: "Start run" }));

    await waitFor(() => expect(creations()).toHaveLength(1));
    expect(creations()[0]?.body).toMatchObject({
      topic: "Monocular depth estimation",
      llm_policy: "auto",
      config: { stages: ["literature", "method", "coding"], dataset: "nyu2" },
    });
    await waitFor(() => expect(router.push).toHaveBeenCalledWith(`/studio/runs/${RUN.id}`));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});

describe("NewRunWizard cost estimate", () => {
  it("shows the live estimate and follows the options", async () => {
    renderWizard();
    const panel = await screen.findByRole("region", { name: "Estimated cost" });
    await waitFor(() => expect(panel.textContent).toContain("Between $0.08 and $0.55"), {
      timeout: 3000,
    });
    expect(panel.textContent).toContain("$0.21");
    expect(panel.textContent).toContain("42 (30 to 60)");
    expect(within(panel).getByText("Demo")).toBeTruthy();
    expect(estimates()[0]?.body).toMatchObject({ llm_policy: "auto", budget_cap_usd: null });

    fireEvent.change(screen.getByRole("textbox", { name: "Research topic" }), {
      target: { value: "Monocular depth estimation" },
    });
    next();
    await stepHeading("Literature", 2);
    next();
    await stepHeading("Stages", 3);
    next();
    await stepHeading("Models and budget", 4);
    fireEvent.click(screen.getByRole("radio", { name: "Free only" }));
    await waitFor(
      () => expect(panel.textContent).toContain("Free models only: this run spends nothing."),
      { timeout: 3000 },
    );
    expect(estimates().at(-1)?.body).toMatchObject({ llm_policy: "free" });
  });

  it("asks to fix invalid options instead of estimating them", async () => {
    renderWizard();
    fireEvent.change(await screen.findByRole("textbox", { name: "Research topic" }), {
      target: { value: "Monocular depth estimation" },
    });
    next();
    await stepHeading("Literature", 2);
    fireEvent.change(screen.getByRole("spinbutton", { name: "Papers to keep" }), {
      target: { value: "500" },
    });
    const panel = screen.getByRole("region", { name: "Estimated cost" });
    await waitFor(() =>
      expect(panel.textContent).toContain("Fix the highlighted options to see an estimate."),
    );
  });
});

describe("wizard field errors", () => {
  function renderError(messages: typeof enMessages) {
    const wrapper = ({ children }: { children: ReactNode }) => (
      <NextIntlClientProvider locale="en" messages={messages} timeZone="Asia/Seoul">
        {children}
      </NextIntlClientProvider>
    );
    return renderHook(() => useWizardFieldError(), { wrapper }).result;
  }

  it("use Studio's copy until the shared wizard messages have the code", () => {
    const { wizard: _shared, ...withoutShared } = enMessages;
    const result = renderError(withoutShared);
    let text: string | null = null;
    act(() => {
      text = result.current({ message: "maxPapers.outOfRange" });
    });
    expect(text).toBe("Choose between 5 and 50 papers.");
    expect(result.current(undefined)).toBeNull();
  });

  it("prefer the shared wizard copy once it exists", () => {
    const result = renderError({
      ...enMessages,
      wizard: { errors: { maxPapers: { outOfRange: "Shared: {min} to {max}." } } },
    });
    expect(result.current({ message: "maxPapers.outOfRange" })).toBe("Shared: 5 to 50.");
    // Codes the shared copy does not cover yet still read in Studio's words.
    expect(result.current({ message: "topic.tooShort" })).toBe(
      "Describe the topic in at least 3 characters.",
    );
  });
});
