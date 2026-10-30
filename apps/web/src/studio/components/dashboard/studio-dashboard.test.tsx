// @vitest-environment jsdom
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  GpuQueueOut,
  NotificationOut,
  ProjectOut,
  RecentRunOut,
  RunStatus,
  UsageOut,
} from "@/client";
import { listProjectsQueryKey } from "@/client/@tanstack/react-query.gen";
import { useGpuQueue } from "@/hooks/use-gpu-queue";
import { useNotifications } from "@/hooks/use-notifications";
import { useRecentRuns } from "@/hooks/use-recent-runs";
import { useUsage } from "@/hooks/use-usage";
import { RUN_CONFIG_DEFAULTS } from "@/lib/new-run-schema";
import { installDomFakes } from "@/studio/test/dom";
import { makeQueryClient, renderStudio, TEST_USER } from "@/studio/test/render";
import { StudioDashboard } from "./studio-dashboard";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/studio/dashboard",
}));
vi.mock("@/hooks/use-recent-runs", () => ({
  RECENT_RUNS_LIMIT: { default: 20, max: 100 },
  useRecentRuns: vi.fn(),
}));
vi.mock("@/hooks/use-usage", () => ({
  USAGE_DAYS: { min: 7, max: 90, default: 30 },
  useUsage: vi.fn(),
}));
vi.mock("@/hooks/use-notifications", () => ({ useNotifications: vi.fn() }));
vi.mock("@/hooks/use-gpu-queue", () => ({ useGpuQueue: vi.fn() }));
// jsdom has no canvas: the chart runtime and the colour probe are stand-ins here.
const chart = vi.hoisted(() => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() }));
vi.mock("./spend-chart-echarts", () => ({ init: vi.fn(() => chart) }));
vi.mock("@/components/shared/css-color", () => ({
  resolveColors: (_scope: Element, expressions: Record<string, string>) => expressions,
}));

const NOW = new Date();
const today = NOW.toISOString().slice(0, 10);
const hoursAgo = (hours: number) => new Date(NOW.getTime() - hours * 3_600_000).toISOString();

function run(id: string, status: RunStatus, overrides: Partial<RecentRunOut> = {}): RecentRunOut {
  return {
    id,
    project_id: "p-depth",
    owner_id: TEST_USER.id,
    topic: `Topic ${id}`,
    status,
    llm_policy: "auto",
    budget_cap_usd: null,
    config: { ...RUN_CONFIG_DEFAULTS, stages: ["literature", "method", "coding"] },
    error: null,
    created_at: hoursAgo(2),
    updated_at: hoursAgo(1),
    project_name: "Monocular depth",
    ...overrides,
  };
}

const RUNS: RecentRunOut[] = [
  run("r-review", "awaiting_approval", { topic: "Depth from a single image" }),
  run("r-running", "running"),
  run("r-queued", "queued"),
  run("r-done", "completed", { created_at: hoursAgo(24 * 30) }),
];

function notification(overrides: Partial<NotificationOut>): NotificationOut {
  return {
    key: "approval:o-1",
    kind: "approval_needed",
    created_at: hoursAgo(5),
    read: false,
    run_id: "r-review",
    project_id: "p-depth",
    stage: "method",
    params: { topic: "Depth from a single image", project: "Monocular depth", stage: "method" },
    ...overrides,
  };
}

const NOTIFICATIONS: NotificationOut[] = [
  notification({}),
  notification({
    key: "approval.expiring:o-1",
    kind: "approval_expiring",
    created_at: hoursAgo(1),
  }),
  notification({
    key: "run.finished:r-done",
    kind: "run_completed",
    run_id: "r-done",
    stage: null,
    params: { topic: "Topic r-done", project: "Monocular depth" },
  }),
];

const USAGE: UsageOut = {
  scope: "me",
  days: 30,
  since: hoursAgo(24 * 29),
  until: NOW.toISOString(),
  totals: {
    paid_usd: "18.40",
    paid_calls: 40,
    free_calls: 120,
    prompt_tokens: 0,
    completion_tokens: 0,
  },
  by_day: [
    {
      day: "2026-01-01",
      paid_usd: "1.00",
      paid_calls: 3,
      free_calls: 5,
      prompt_tokens: 0,
      completion_tokens: 0,
    },
    {
      day: today,
      paid_usd: "2.25",
      paid_calls: 2,
      free_calls: 7,
      prompt_tokens: 0,
      completion_tokens: 0,
    },
  ],
  by_model: [],
  top_runs: [],
  by_user: [],
  budget: {
    month: today.slice(0, 7),
    monthly_usd: "50.00",
    spent_usd: "12.50",
    remaining_usd: "37.50",
  },
  demo: false,
};

const GPU: GpuQueueOut = {
  gpu: {
    name: "NVIDIA RTX 4090",
    memory_total_mb: 24_576,
    memory_used_mb: 18_000,
    utilization_percent: 87,
    temperature_c: 71,
    power_draw_w: 380,
    power_limit_w: 450,
    fan_percent: 60,
    sampled_at: hoursAgo(0),
    demo: true,
  },
  concurrency: 1,
  running: [
    {
      id: "job-1",
      status: "running",
      run_id: "r-running",
      topic: "Topic r-running",
      project_name: "Monocular depth",
      owner_name: "Grace Hopper",
      is_mine: false,
      dataset: "nyu2",
      progress: 0.42,
      epoch: 4,
      total_epochs: 10,
      gpu_memory_mb: 18_000,
      submitted_at: hoursAgo(3),
      started_at: hoursAgo(1),
      estimated_start_at: hoursAgo(1),
      estimated_finish_at: new Date(NOW.getTime() + 40 * 60_000).toISOString(),
      eta_seconds: 2400,
      estimated: false,
      demo: true,
    },
  ],
  queued: [],
  my_position: null,
  my_jobs: 0,
  per_user_limit: 2,
  demo: true,
};

const PROJECTS: ProjectOut[] = [
  {
    id: "p-depth",
    name: "Monocular depth",
    description: "NYU Depth V2 baselines",
    privacy: "standard",
    allow_free_models: true,
    created_by: TEST_USER.id,
    created_at: "2026-10-01T00:00:00Z",
    my_role: "owner",
  },
];

/** What a TanStack query result looks like to the dashboard. */
function loaded<T>(data: T) {
  return { data, isPending: false, isError: false, isSuccess: true, error: null, refetch: vi.fn() };
}

function failed(code = "server.error") {
  return {
    data: undefined,
    isPending: false,
    isError: true,
    isSuccess: false,
    error: Object.assign(new Error(code), { code, status: 500 }),
    refetch: vi.fn(),
  };
}

const pending = () => ({
  data: undefined,
  isPending: true,
  isError: false,
  isSuccess: false,
  error: null,
  refetch: vi.fn(),
});

beforeAll(() => {
  installDomFakes();
});

beforeEach(() => {
  vi.mocked(useRecentRuns).mockReturnValue(loaded(RUNS) as never);
  vi.mocked(useUsage).mockReturnValue(loaded(USAGE) as never);
  vi.mocked(useGpuQueue).mockReturnValue(loaded(GPU) as never);
  vi.mocked(useNotifications).mockReturnValue({
    query: loaded({ items: NOTIFICATIONS, unread_count: 3 }),
    items: NOTIFICATIONS,
    unreadCount: 3,
  } as never);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderDashboard({
  locale = "en",
  projects = PROJECTS,
}: {
  locale?: "en" | "ko";
  projects?: ProjectOut[];
} = {}) {
  const queryClient = makeQueryClient();
  queryClient.setQueryData(listProjectsQueryKey(), projects);
  return renderStudio(<StudioDashboard />, { user: TEST_USER, queryClient, locale });
}

const tile = (name: string) => screen.getByRole("group", { name });

describe("StudioDashboard metrics", () => {
  it("shows the four tiles from the shared hooks, each with a sparkline", () => {
    renderDashboard();

    const active = tile("Active runs");
    // Awaiting approval, running and queued are in progress; the completed run is not.
    expect(within(active).getAllByText("3").length).toBeGreaterThan(0);
    expect(active.textContent).toContain("Started in the last 14 days: 3");

    const review = tile("Awaiting your review");
    expect(within(review).getAllByText("1").length).toBeGreaterThan(0);
    expect(review.textContent).toContain("1 expires within a day");

    const spend = tile("Spend this month");
    expect(spend.textContent).toContain("$12.50");
    expect(spend.textContent).toContain("25% of $50.00 used");
    expect(within(spend).getByRole("progressbar").getAttribute("aria-valuenow")).toBe("25");

    const free = tile("Free calls today");
    expect(within(free).getAllByText("7").length).toBeGreaterThan(0);
    expect(free.textContent).toContain("2 paid calls");

    for (const group of [active, review, spend, free]) {
      expect(group.querySelector("[data-slot=sparkline]")).not.toBeNull();
    }
  });

  it("asks the hooks for the newest runs and 30 days of the caller's own usage", () => {
    renderDashboard();
    expect(useRecentRuns).toHaveBeenCalledWith(100);
    expect(useUsage).toHaveBeenCalledWith("me", 30);
  });

  it("holds a skeleton while loading and offers a retry when a source fails", () => {
    const usage = failed();
    vi.mocked(useUsage).mockReturnValue(usage as never);
    vi.mocked(useRecentRuns).mockReturnValue(pending() as never);
    renderDashboard();

    expect(tile("Active runs").querySelector(".studio-skeleton")).not.toBeNull();
    const spend = tile("Spend this month");
    expect(spend.textContent).toContain("Could not load");
    expect(spend.textContent).not.toContain("$");
    fireEvent.click(within(spend).getByRole("button", { name: "Try again" }));
    expect(usage.refetch).toHaveBeenCalled();
  });

  it("keeps the greeting as the only h1, with a word-break fallback for long names", () => {
    renderDashboard();
    const headings = screen.getAllByRole("heading", { level: 1 });
    expect(headings).toHaveLength(1);
    expect(headings[0]?.textContent).toMatch(/Ada Lovelace/);
    expect(headings[0]?.className).toMatch(/overflow-wrap:anywhere/);
  });
});

describe("StudioDashboard sections", () => {
  it("lists what needs a review with the run's pipeline, linking to the Studio run page", () => {
    renderDashboard();
    const section = screen.getByRole("region", { name: /Needs your review/ });
    const link = within(section).getByRole("link", { name: "Depth from a single image" });
    expect(link.getAttribute("href")).toBe("/studio/runs/r-review");

    const pipeline = within(section).getByRole("list", {
      name: "Pipeline of Depth from a single image",
    });
    const stages = within(pipeline).getAllByRole("listitem");
    expect(stages.map((stage) => stage.getAttribute("data-status"))).toEqual([
      "approved",
      "output_ready",
      "pending",
      "skipped",
      "skipped",
    ]);
    expect(within(section).getByText("Expires within a day")).toBeTruthy();
  });

  it("says so when nothing waits for the user", () => {
    vi.mocked(useNotifications).mockReturnValue({
      query: loaded({ items: [], unread_count: 0 }),
      items: [],
      unreadCount: 0,
    } as never);
    renderDashboard();
    const section = screen.getByRole("region", { name: /Needs your review/ });
    expect(
      within(section).getByRole("heading", { name: "Nothing is waiting for you" }),
    ).toBeTruthy();
  });

  it("shows the GPU as a live ring with the running job, marked as demo data", () => {
    renderDashboard();
    const gpu = screen.getByRole("region", { name: /Lab GPU/ });
    const ring = within(gpu).getByRole("meter", { name: "Utilisation" });
    expect(ring.getAttribute("aria-valuenow")).toBe("87");
    expect(within(gpu).getByText("Demo")).toBeTruthy();
    expect(within(gpu).getByRole("link", { name: "Topic r-running" }).getAttribute("href")).toBe(
      "/studio/runs/r-running",
    );
    expect(within(gpu).getByRole("progressbar").getAttribute("aria-valuenow")).toBe("42");
    expect(within(gpu).getByText("No experiments are waiting.")).toBeTruthy();
  });

  it("draws 30 days of paid spend, with the same figures in a data table", async () => {
    renderDashboard();
    const spend = screen.getByRole("region", { name: /Spend, last 30 days/ });
    expect(spend.textContent).toContain("$18.40");
    const table = within(spend).getByRole("table", { name: "Paid spend and LLM calls per day" });
    expect(within(table).getAllByRole("row")).toHaveLength(USAGE.by_day.length + 1);
    await vi.waitFor(() => expect(chart.setOption).toHaveBeenCalled());
    const [option] = chart.setOption.mock.calls.at(-1) as [{ series: { data: number[] }[] }];
    expect(option.series[0]?.data).toEqual([1, 2.25]);
  });

  it("lists recent runs and the projects, with their runs in progress", () => {
    renderDashboard();
    const recent = screen.getByRole("region", { name: "Recent runs" });
    expect(within(recent).getAllByRole("link")).toHaveLength(RUNS.length);
    expect(
      within(recent)
        .getByRole("link", { name: /Topic r-running/ })
        .getAttribute("href"),
    ).toBe("/studio/runs/r-running");

    const projects = screen.getByRole("region", { name: "Projects" });
    const card = within(projects).getByRole("link", { name: /Monocular depth/ });
    expect(card.getAttribute("href")).toBe("/studio/projects/p-depth");
    expect(card.textContent).toContain("3 active runs");
    expect(within(projects).getByRole("button", { name: /New project/ })).toBeTruthy();
  });

  it("speaks Korean", () => {
    renderDashboard({ locale: "ko" });
    expect(tile("진행 중인 실행")).toBeTruthy();
    expect(tile("내 검토 대기")).toBeTruthy();
    expect(tile("이번 달 사용액").textContent).toContain("$12.50");
    expect(screen.getByRole("region", { name: /검토가 필요한 결과/ })).toBeTruthy();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });
});
