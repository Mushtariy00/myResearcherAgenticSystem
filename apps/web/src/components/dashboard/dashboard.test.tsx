// @vitest-environment jsdom
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  GpuJobOut,
  GpuQueueOut,
  ProjectOut,
  RecentRunOut,
  RunDetail,
  RunStatus,
  UsageOut,
} from "@/client";
import {
  installBrowserStubs,
  makeQueryClient,
  RESEARCHER,
  renderPage,
} from "@/components/projects/test-utils";
import { json, mockApi } from "@/hooks/run-hooks.fixtures";
import { RUN_CONFIG_DEFAULTS } from "@/lib/new-run-schema";
import { Dashboard } from "./dashboard";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
}));

const OWNED = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const SHARED = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";

function project(id: string, name: string, role: ProjectOut["my_role"]): ProjectOut {
  return {
    id,
    name,
    description: "",
    privacy: "standard",
    allow_free_models: true,
    created_by: "someone",
    created_at: "2026-10-01T00:00:00Z",
    my_role: role,
  };
}

function run(
  id: string,
  topic: string,
  projectId: string,
  ownerId: string,
  status: RunStatus,
): RecentRunOut {
  return {
    id,
    project_id: projectId,
    owner_id: ownerId,
    topic,
    status,
    llm_policy: "auto",
    budget_cap_usd: null,
    config: { ...RUN_CONFIG_DEFAULTS },
    error: null,
    created_at: "2026-10-29T00:00:00Z",
    updated_at: "2026-10-29T00:00:00Z",
    project_name: projectId === OWNED ? "My lab project" : "Shared project",
  };
}

// The user owns one project and is a researcher in the other.
const PROJECTS = [
  project(OWNED, "My lab project", "owner"),
  project(SHARED, "Shared project", "researcher"),
];
const AWAITING = [
  run("run-a", "Depth in my own project", OWNED, "someone-else", "awaiting_approval"),
  run("run-b", "My run in the shared project", SHARED, RESEARCHER.id, "awaiting_approval"),
  run("run-c", "A colleague's run", SHARED, "someone-else", "awaiting_approval"),
];
const RECENT = [
  run("run-d", "Segmentation in progress", OWNED, RESEARCHER.id, "running"),
  run("run-e", "Finished depth study", OWNED, RESEARCHER.id, "completed"),
];

function detail(source: RecentRunOut, stage: string, awaiting: boolean): RunDetail {
  return {
    ...source,
    stages: [
      {
        id: `${source.id}-stage`,
        stage,
        attempt: 1,
        status: awaiting ? "output_ready" : "running",
        feedback: null,
        error: null,
        started_at: "2026-10-29T00:00:00Z",
        finished_at: null,
      },
    ],
    awaiting_stage: awaiting ? stage : null,
    can_steer: true,
  };
}

function job(partial: Partial<GpuJobOut> & Pick<GpuJobOut, "id" | "status">): GpuJobOut {
  return {
    run_id: null,
    topic: null,
    project_name: null,
    owner_name: "Hedy Lamarr",
    is_mine: false,
    dataset: "nyu2",
    progress: 0,
    epoch: null,
    total_epochs: null,
    gpu_memory_mb: null,
    submitted_at: "2026-10-29T00:00:00Z",
    started_at: null,
    estimated_start_at: "2099-01-01T00:00:00Z",
    estimated_finish_at: "2099-01-01T01:00:00Z",
    eta_seconds: 1800,
    estimated: true,
    demo: true,
    ...partial,
  };
}

const GPU: GpuQueueOut = {
  gpu: {
    name: "NVIDIA RTX A6000",
    memory_total_mb: 49_152,
    memory_used_mb: 20_480,
    utilization_percent: 87,
    temperature_c: 71,
    power_draw_w: 250,
    power_limit_w: 300,
    fan_percent: 55,
    sampled_at: "2026-10-30T00:00:00Z",
    demo: true,
  },
  concurrency: 1,
  running: [job({ id: "job-1", status: "running", progress: 0.4, epoch: 8, total_epochs: 20 })],
  queued: [
    job({ id: "job-2", status: "queued" }),
    job({ id: "job-3", status: "queued", is_mine: true, topic: "Segmentation in progress" }),
  ],
  my_position: 2,
  my_jobs: 1,
  per_user_limit: 2,
  demo: true,
};

const DAYS = Array.from({ length: 30 }, (_, index) => ({
  day: `2026-10-${String(index + 1).padStart(2, "0")}`,
  paid_usd: index === 28 ? "1.25" : index === 10 ? "0.25" : "0",
  paid_calls: index === 28 ? 2 : index === 10 ? 1 : 0,
  free_calls: 4,
  prompt_tokens: 1000,
  completion_tokens: 200,
}));

const USAGE: UsageOut = {
  scope: "me",
  days: 30,
  since: "2026-10-01",
  until: "2026-10-30",
  totals: {
    paid_usd: "1.50",
    paid_calls: 3,
    free_calls: 120,
    prompt_tokens: 30_000,
    completion_tokens: 6_000,
  },
  by_day: DAYS,
  by_model: [],
  top_runs: [],
  by_user: [],
  budget: { month: "2026-10", monthly_usd: "20.00", spent_usd: "1.50", remaining_usd: "18.50" },
  demo: true,
};

beforeAll(() => {
  installBrowserStubs();
});

beforeEach(() => {
  mockApi((request, path) => {
    const url = new URL(request.url);
    if (path === "/api/v1/projects") {
      return json(200, PROJECTS);
    }
    if (path === "/api/v1/runs") {
      return json(200, url.searchParams.get("status") === "awaiting_approval" ? AWAITING : RECENT);
    }
    if (path.startsWith("/api/v1/runs/")) {
      const id = path.slice("/api/v1/runs/".length);
      const found = [...AWAITING, ...RECENT].find((item) => item.id === id);
      return found
        ? json(
            200,
            detail(
              found,
              found.status === "running" ? "method" : "literature",
              found.status === "awaiting_approval",
            ),
          )
        : json(404, { detail: "run.not_found" });
    }
    if (path === "/api/v1/gpu/queue") {
      return json(200, GPU);
    }
    if (path === "/api/v1/usage") {
      return json(200, USAGE);
    }
    return json(404, { detail: "unknown" });
  });
});

afterEach(() => {
  cleanup();
});

function renderDashboard() {
  return renderPage(<Dashboard />, { user: RESEARCHER, queryClient: makeQueryClient() });
}

describe("Dashboard", () => {
  it("lists only the reviews the user may decide, with the stage that waits", async () => {
    renderDashboard();
    const review = await screen.findByRole("region", { name: /Needs your review/ });
    expect(await within(review).findByText("Depth in my own project")).toBeTruthy();
    expect(within(review).getByText("My run in the shared project")).toBeTruthy();
    expect(within(review).queryByText("A colleague's run")).toBeNull();
    expect(
      within(review)
        .getByRole("link", { name: "Review “Depth in my own project”" })
        .getAttribute("href"),
    ).toBe("/runs/run-a");
    await waitFor(() =>
      expect(within(review).getAllByText("Literature output to review")).toHaveLength(2),
    );
  });

  it("shows where recent runs are in the pipeline", async () => {
    renderDashboard();
    const recent = await screen.findByRole("region", { name: "Recent runs" });
    const row = (await within(recent).findByText("Segmentation in progress")).closest("tr");
    expect(row && (await within(row).findByText("Method"))).toBeTruthy();
    const finished = within(recent).getByText("Finished depth study").closest("tr");
    expect(finished && within(finished).getByText("Finished")).toBeTruthy();
  });

  it("shows the GPU with the user's place in the queue", async () => {
    renderDashboard();
    const gpu = await screen.findByRole("region", { name: "GPU" });
    expect(await within(gpu).findByText("Your job is number 2 in the queue.")).toBeTruthy();
    expect(within(gpu).getByText("NVIDIA RTX A6000")).toBeTruthy();
    expect(within(gpu).getByRole("meter", { name: "Load" }).getAttribute("aria-valuetext")).toBe(
      "87%",
    );
    expect(within(gpu).getByRole("progressbar", { name: "Epoch 8 of 20" })).toBeTruthy();
    expect(within(gpu).getByText("Demo")).toBeTruthy();
  });

  it("shows paid against free spend and the budget left", async () => {
    renderDashboard();
    const spend = await screen.findByRole("region", { name: "My LLM spend" });
    expect(await within(spend).findByText("$1.50")).toBeTruthy();
    expect(within(spend).getByText("Paid · 3 calls")).toBeTruthy();
    expect(within(spend).getByText("Free · 120 calls")).toBeTruthy();
    expect(within(spend).getByText("$18.50 left this month.")).toBeTruthy();
    expect(
      within(spend).getByText(/Over 30 days you spent \$1\.50 on paid models, at most \$1\.25/),
    ).toBeTruthy();
  });
});
