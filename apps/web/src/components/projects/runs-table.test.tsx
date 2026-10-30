// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import type { RunOut, RunStatus } from "@/client";
import { listRunsQueryKey } from "@/client/@tanstack/react-query.gen";
import { json, mockApi } from "@/hooks/run-hooks.fixtures";
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

beforeEach(() => {
  mockApi(() => json(200, RUNS));
});

afterEach(() => {
  cleanup();
});

function renderTable() {
  const queryClient = makeQueryClient();
  queryClient.setQueryData(listRunsQueryKey({ path: { project_id: PROJECT } }), RUNS);
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
    queryClient.setQueryData(listRunsQueryKey({ path: { project_id: PROJECT } }), []);
    renderPage(<RunsTable projectId={PROJECT} canStartRuns newRunHref="/new" />, { queryClient });
    expect(screen.getByText("No runs yet.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "New run" }).getAttribute("href")).toBe("/new");
  });
});
