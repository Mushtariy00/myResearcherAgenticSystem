// @vitest-environment jsdom

import type { QueryClient } from "@tanstack/react-query";
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import type { RunOut, RunStatus } from "@/client";
import { listRunsInfiniteQueryKey } from "@/client/@tanstack/react-query.gen";
import { json, mockApi, requestsOf } from "@/hooks/run-hooks.fixtures";
import { RUNS_PAGE_SIZE } from "@/hooks/use-project-runs";
import { RUN_CONFIG_DEFAULTS } from "@/lib/new-run-schema";
import { RunsTable } from "./runs-table";
import { chooseOption, installBrowserStubs, makeQueryClient, renderPage } from "./test-utils";

const PROJECT = "33333333-3333-4333-8333-333333333333";

function makeRun(id: string, topic: string, status: RunStatus, createdAt: string): RunOut {
  return {
    id,
    project_id: PROJECT,
    owner_id: "user-owner",
    topic,
    status,
    llm_policy: "auto",
    budget_cap_usd: null,
    config: { ...RUN_CONFIG_DEFAULTS },
    error: null,
    created_at: createdAt,
    updated_at: createdAt,
  };
}

const RUNS: RunOut[] = [
  makeRun("run-1", "Monocular depth estimation", "completed", "2026-10-20T01:00:00Z"),
  makeRun(
    "run-2",
    "Depth completion from sparse LiDAR",
    "awaiting_approval",
    "2026-10-28T01:00:00Z",
  ),
  makeRun("run-3", "Semantic segmentation of street scenes", "running", "2026-10-29T01:00:00Z"),
  makeRun("run-4", "Self-supervised depth for drones", "failed", "2026-10-25T01:00:00Z"),
];

beforeAll(() => {
  installBrowserStubs();
});

let fetchMock: ReturnType<typeof mockApi>;

beforeEach(() => {
  fetchMock = mockApi(() => json(200, RUNS));
});

afterEach(() => {
  cleanup();
});

/** The project's runs as already loaded pages (newest first). */
function seedRuns(queryClient: QueryClient, ...pages: RunOut[][]) {
  queryClient.setQueryData(
    listRunsInfiniteQueryKey({ path: { project_id: PROJECT }, query: { limit: RUNS_PAGE_SIZE } }),
    { pages, pageParams: pages.map((_, index) => pages[index - 1]?.at(-1)?.id ?? null) },
  );
}

function renderTable() {
  const queryClient = makeQueryClient();
  seedRuns(queryClient, RUNS);
  return renderPage(
    <RunsTable projectId={PROJECT} canStartRuns newRunHref={`/projects/${PROJECT}/runs/new`} />,
    { queryClient },
  );
}

/** The topics in the order the table shows them. */
function topics(): string[] {
  const table = screen.getByRole("table");
  return within(table)
    .queryAllByRole("link")
    .map((link) => link.textContent ?? "");
}

function chooseStatus(label: string) {
  return chooseOption(screen.getByRole("combobox", { name: "Status" }), label);
}

describe("RunsTable", () => {
  it("lists the newest runs first and searches the topics", () => {
    renderTable();
    expect(topics()).toEqual([
      "Semantic segmentation of street scenes",
      "Depth completion from sparse LiDAR",
      "Self-supervised depth for drones",
      "Monocular depth estimation",
    ]);
    expect(screen.getByText("4 of 4 runs")).toBeTruthy();

    fireEvent.change(screen.getByRole("searchbox", { name: "Search topics" }), {
      target: { value: "DEPTH" },
    });
    expect(topics()).toEqual([
      "Depth completion from sparse LiDAR",
      "Self-supervised depth for drones",
      "Monocular depth estimation",
    ]);
    expect(screen.getByText("3 of 4 runs")).toBeTruthy();
  });

  it("filters by status, together with the search, and clears both", async () => {
    renderTable();
    await chooseStatus("Awaiting approval (1)");
    await waitFor(() => expect(topics()).toEqual(["Depth completion from sparse LiDAR"]));

    fireEvent.change(screen.getByRole("searchbox", { name: "Search topics" }), {
      target: { value: "segmentation" },
    });
    expect(topics()).toEqual([]);
    expect(screen.getByText("No runs match these filters.")).toBeTruthy();

    fireEvent.click(screen.getAllByRole("button", { name: "Clear filters" })[0] as HTMLElement);
    expect(topics()).toHaveLength(4);
    expect(
      (screen.getByRole("searchbox", { name: "Search topics" }) as HTMLInputElement).value,
    ).toBe("");
  });

  it("sorts by status, runs needing someone first", () => {
    renderTable();
    fireEvent.click(screen.getByRole("button", { name: "Status" }));
    expect(topics()).toEqual([
      "Depth completion from sparse LiDAR",
      "Semantic segmentation of street scenes",
      "Self-supervised depth for drones",
      "Monocular depth estimation",
    ]);
    const header = screen.getByRole("columnheader", { name: "Status" });
    expect(header.getAttribute("aria-sort")).toBe("ascending");
  });

  it("offers a first run when the project has none", () => {
    const queryClient = makeQueryClient();
    seedRuns(queryClient, []);
    renderPage(<RunsTable projectId={PROJECT} canStartRuns newRunHref="/new" />, { queryClient });
    expect(screen.getByText("No runs yet.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "New run" }).getAttribute("href")).toBe("/new");
  });

  it("loads older runs a page at a time", async () => {
    const page = Array.from({ length: RUNS_PAGE_SIZE }, (_, index) =>
      makeRun(`run-new-${index}`, `Topic ${index}`, "completed", "2026-10-29T01:00:00Z"),
    );
    fetchMock = mockApi((request) => {
      const before = new URL(request.url).searchParams.get("before");
      return json(200, before === null ? page : RUNS);
    });
    renderPage(<RunsTable projectId={PROJECT} canStartRuns newRunHref="/new" />);
    expect(
      await screen.findByText(`${RUNS_PAGE_SIZE} of ${RUNS_PAGE_SIZE} runs`, { exact: false }),
    ).toBeTruthy();
    expect(screen.getByText(/Search and filters cover the runs loaded so far/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Load older runs" }));
    await waitFor(() => expect(topics()).toHaveLength(RUNS_PAGE_SIZE + RUNS.length));
    expect(requestsOf(fetchMock)).toEqual([
      `GET /api/v1/projects/${PROJECT}/runs?limit=${RUNS_PAGE_SIZE}`,
      `GET /api/v1/projects/${PROJECT}/runs?before=run-new-${RUNS_PAGE_SIZE - 1}&limit=${RUNS_PAGE_SIZE}`,
    ]);
    // A page shorter than the limit is the last one.
    expect(screen.queryByRole("button", { name: "Load older runs" })).toBeNull();
    expect(screen.queryByText(/Search and filters cover the runs loaded so far/)).toBeNull();
  });

  it("keeps the runs on screen when a refresh fails", async () => {
    const queryClient = makeQueryClient();
    seedRuns(queryClient, RUNS);
    renderPage(<RunsTable projectId={PROJECT} canStartRuns newRunHref="/new" />, { queryClient });
    fetchMock.mockImplementation(async () => json(503, { detail: "db.unavailable" }));
    await queryClient.refetchQueries();
    await waitFor(() =>
      expect(queryClient.getQueryCache().getAll()[0]?.state.status).toBe("error"),
    );
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(screen.queryByText("Could not load this")).toBeNull();
    expect(topics()).toHaveLength(RUNS.length);
  });
});
