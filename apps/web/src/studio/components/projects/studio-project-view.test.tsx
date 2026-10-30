// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  MemberOut,
  PaperPage,
  ProjectOut,
  ProjectRole,
  ProjectSettings,
  RunEstimateOut,
  RunOut,
} from "@/client";
import { client } from "@/client/client.gen";
import { configureApiClient } from "@/lib/api-client";
import { RUN_CONFIG_DEFAULTS } from "@/lib/new-run-schema";
import { installDomFakes } from "@/studio/test/dom";
import { makeQueryClient, renderStudio, TEST_USER } from "@/studio/test/render";
import { projectPermissions } from "./project-permissions";
import { StudioProjectView } from "./studio-project-view";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/studio/projects/p1",
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/components/shared/pdf-viewer", () => ({
  PdfViewer: ({ url }: { url: string }) => <div data-testid="pdf-viewer" data-url={url} />,
}));

const PROJECT_ID = "p1";

function project(role: ProjectRole | null): ProjectOut {
  return {
    id: PROJECT_ID,
    name: "Monocular depth",
    description: "NYU Depth V2 baselines",
    privacy: "confidential",
    allow_free_models: true,
    created_by: TEST_USER.id,
    created_at: "2026-10-01T00:00:00Z",
    my_role: role,
  };
}

function run(id: string, topic: string, status: RunOut["status"], created_at: string): RunOut {
  return {
    id,
    project_id: PROJECT_ID,
    owner_id: TEST_USER.id,
    topic,
    status,
    llm_policy: "auto",
    budget_cap_usd: id === "r2" ? "5.00" : null,
    config: { ...RUN_CONFIG_DEFAULTS },
    error: null,
    created_at,
    updated_at: created_at,
  };
}

const RUNS = [
  run("r1", "Depth from a single image", "completed", "2026-10-02T00:00:00Z"),
  run("r2", "Self-supervised depth", "awaiting_approval", "2026-10-05T00:00:00Z"),
];

const MEMBERS: MemberOut[] = [
  { user_id: TEST_USER.id, email: TEST_USER.email, name: TEST_USER.name, role: "owner" },
  { user_id: "u2", email: "grace@lab.example", name: "Grace Hopper", role: "viewer" },
];

const SETTINGS: ProjectSettings = {
  privacy: "confidential",
  allow_free_models: true,
  auto_approve: false,
  approval_expiry_days: 7,
};

const PAPERS: PaperPage = {
  items: [
    {
      paper: {
        paper_id: "doi:10.5555/depth.1",
        title: "Depth Anything",
        authors: ["L. Yang"],
        year: 2024,
        venue: "CVPR",
        doi: "10.5555/depth.1",
        arxiv_id: null,
        url: null,
        abstract: "A foundation model for depth.",
        citation_count: 120,
        source: "openalex",
        pdf_available: false,
      },
      run_count: 1,
      project_count: 1,
      best_relevance: 0.91,
      decisions: ["include"],
      last_seen_at: "2026-10-05T00:00:00Z",
      demo: true,
    },
  ],
  total: 1,
  demo: true,
};

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

type Call = { method: string; path: string; search: string; body: unknown };
const fetchMock = vi.fn<typeof fetch>();
let calls: Call[] = [];
let role: ProjectRole | null = "owner";

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeAll(() => {
  installDomFakes();
});

beforeEach(() => {
  calls = [];
  role = "owner";
  window.history.replaceState(null, "", "/studio/projects/p1");
  configureApiClient();
  client.setConfig({ baseUrl: "http://localhost:8080", fetch: fetchMock });
  fetchMock.mockImplementation(async (input) => {
    const request = input as Request;
    const url = new URL(request.url);
    const body = ["GET", "DELETE"].includes(request.method) ? undefined : await request.json();
    calls.push({ method: request.method, path: url.pathname, search: url.search, body });
    const route = `${request.method} ${url.pathname}`;
    switch (route) {
      case `GET /api/v1/projects/${PROJECT_ID}`:
        return json(200, project(role));
      case `GET /api/v1/projects/${PROJECT_ID}/runs`:
        return json(200, RUNS);
      case `GET /api/v1/projects/${PROJECT_ID}/members`:
        return json(200, MEMBERS);
      case `PATCH /api/v1/projects/${PROJECT_ID}/members/${TEST_USER.id}`:
        return json(409, { detail: "member.last_owner" });
      case `GET /api/v1/projects/${PROJECT_ID}/settings`:
        return json(200, SETTINGS);
      case `PUT /api/v1/projects/${PROJECT_ID}/settings`:
        return json(200, body);
      case "GET /api/v1/papers":
        return json(200, PAPERS);
      case "POST /api/v1/runs/estimate":
        return json(200, ESTIMATE);
      default:
        return json(404, { detail: "project.not_found" });
    }
  });
});

afterEach(() => {
  cleanup();
  fetchMock.mockReset();
  vi.clearAllMocks();
});

function renderProject(initialTab?: string, user = TEST_USER) {
  return renderStudio(<StudioProjectView projectId={PROJECT_ID} initialTab={initialTab} />, {
    user,
    queryClient: makeQueryClient(),
  });
}

async function tab(name: string) {
  const tablist = await screen.findByRole("tablist", { name: "Project sections" });
  return within(tablist).getByRole("tab", { name });
}

describe("project permissions", () => {
  it("follow the project role, and lab admins may do everything", () => {
    expect(projectPermissions("user", "owner")).toEqual({
      canStartRuns: true,
      canManageMembers: true,
      canEditSettings: true,
    });
    expect(projectPermissions("user", "researcher")).toEqual({
      canStartRuns: true,
      canManageMembers: false,
      canEditSettings: false,
    });
    expect(projectPermissions("user", "viewer")).toEqual({
      canStartRuns: false,
      canManageMembers: false,
      canEditSettings: false,
    });
    expect(projectPermissions("admin", null)).toEqual({
      canStartRuns: true,
      canManageMembers: true,
      canEditSettings: true,
    });
  });
});

describe("StudioProjectView tabs", () => {
  it("opens on the runs, searchable, filterable and sortable", async () => {
    renderProject();
    expect(await screen.findByRole("heading", { level: 1, name: "Monocular depth" })).toBeTruthy();
    expect(screen.getByText("Your role: Owner")).toBeTruthy();
    expect(screen.getByRole("button", { name: "New run" })).toBeTruthy();
    expect((await tab("Runs")).getAttribute("aria-selected")).toBe("true");

    const table = await screen.findByRole("table", { name: "Runs of this project" });
    // The table is drawn again after an empty result, so it is looked up each time.
    const topics = () =>
      within(screen.getByRole("table", { name: "Runs of this project" }))
        .getAllByRole("link")
        .map((link) => link.textContent);
    // Newest first by default.
    expect(topics()).toEqual(["Self-supervised depth", "Depth from a single image"]);
    expect(
      within(table).getByRole("link", { name: "Depth from a single image" }).getAttribute("href"),
    ).toBe("/studio/runs/r1");

    const topicHeader = within(table).getByRole("columnheader", { name: /Topic/ });
    fireEvent.click(within(topicHeader).getByRole("button"));
    expect(topicHeader.getAttribute("aria-sort")).toBe("ascending");
    expect(topics()).toEqual(["Depth from a single image", "Self-supervised depth"]);

    fireEvent.change(screen.getByRole("searchbox", { name: "Search runs" }), {
      target: { value: "self" },
    });
    expect(topics()).toEqual(["Self-supervised depth"]);
    expect(screen.getByText("Showing 1 of 2")).toBeTruthy();

    fireEvent.change(screen.getByRole("combobox", { name: "Status" }), {
      target: { value: "completed" },
    });
    expect(screen.getByText("No runs match the search and filter.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Clear search and filter" }));
    expect(topics()).toHaveLength(2);
  });

  it("keeps the open tab in the address and searches the project's papers", async () => {
    renderProject();
    fireEvent.click(await tab("Papers"));
    expect(window.location.search).toBe("?tab=papers");
    const table = await screen.findByRole("table", { name: "Papers found by this project's runs" });
    await within(table).findByText("Depth Anything");
    const search = calls.find((call) => call.path === "/api/v1/papers");
    expect(new URLSearchParams(search?.search).get("project_id")).toBe(PROJECT_ID);

    fireEvent.click(within(table).getByRole("button", { name: "Depth Anything" }));
    const sheet = await screen.findByRole("dialog", { name: "Depth Anything" });
    expect(
      within(sheet)
        .getByRole("link", { name: /Paper page/ })
        .getAttribute("href"),
    ).toBe("/studio/papers/doi%3A10.5555/depth.1");
  });

  it("opens the new-run wizard on demand, asking for an estimate only then", async () => {
    renderProject();
    const start = await screen.findByRole("button", { name: "New run" });
    await screen.findByRole("table", { name: "Runs of this project" });
    expect(calls.some((call) => call.path === "/api/v1/runs/estimate")).toBe(false);

    fireEvent.click(start);
    expect(await screen.findByRole("dialog", { name: "New run" })).toBeTruthy();
    await waitFor(() =>
      expect(calls.some((call) => call.path === "/api/v1/runs/estimate")).toBe(true),
    );
  });

  it("opens the tab named in the address", async () => {
    renderProject("settings");
    expect((await tab("Settings")).getAttribute("aria-selected")).toBe("true");
    expect(await screen.findByRole("form", { name: "Project settings" })).toBeTruthy();
  });
});

describe("StudioProjectView members", () => {
  it("lets an owner change roles, and never shows a refused change as done", async () => {
    renderProject("members");
    const select = await screen.findByRole("combobox", { name: "Role of Ada Lovelace" });
    expect((select as HTMLSelectElement).value).toBe("owner");
    expect(screen.getByRole("button", { name: "Remove Grace Hopper" })).toBeTruthy();
    expect(screen.getByRole("textbox", { name: "Email" })).toBeTruthy();

    fireEvent.change(select, { target: { value: "researcher" } });
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("A project needs at least one owner.");
    expect(alert.textContent).toContain("Ada Lovelace is the last owner.");
    expect((select as HTMLSelectElement).value).toBe("owner");
    expect(calls.at(-1)).toMatchObject({ method: "PATCH", body: { role: "researcher" } });
  });

  it("shows a viewer the members without controls", async () => {
    role = "viewer";
    renderProject("members");
    const list = await screen.findByRole("region", { name: /Members/ });
    await within(list).findByText("Grace Hopper");
    expect(within(list).queryByRole("combobox")).toBeNull();
    expect(within(list).queryByRole("button", { name: /Remove/ })).toBeNull();
    expect(screen.queryByRole("textbox", { name: "Email" })).toBeNull();
    expect(screen.queryByRole("button", { name: "New run" })).toBeNull();
    expect(
      screen.getByText(
        "You are a viewer in this project: you can follow its runs but not start them.",
      ),
    ).toBeTruthy();
  });
});

describe("StudioProjectView settings", () => {
  it("lets an owner save changed settings", async () => {
    renderProject("settings");
    const save = await screen.findByRole("button", { name: "Save settings" });
    expect(save.hasAttribute("disabled")).toBe(true);
    fireEvent.click(screen.getByRole("switch", { name: "Approve stages automatically" }));
    await waitFor(() => expect(save.hasAttribute("disabled")).toBe(false));
    fireEvent.click(save);
    await waitFor(() =>
      expect(calls.find((call) => call.method === "PUT")?.body).toEqual({
        ...SETTINGS,
        auto_approve: true,
      }),
    );
  });

  it("is read-only for everyone else", async () => {
    role = "researcher";
    renderProject("settings");
    expect(
      await screen.findByText("Only project owners and lab admins can change these settings."),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Save settings" })).toBeNull();
    const toggle = screen.getByRole("switch", { name: "Approve stages automatically" });
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-checked")).toBe("false");
    expect(calls.some((call) => call.method === "PUT")).toBe(false);
  });
});
