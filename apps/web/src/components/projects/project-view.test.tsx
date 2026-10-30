// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { MemberOut, ProjectOut, ProjectRole, ProjectSettings } from "@/client";
import {
  getProjectQueryKey,
  getProjectSettingsQueryKey,
  listMembersQueryKey,
} from "@/client/@tanstack/react-query.gen";
import { json, mockApi } from "@/hooks/run-hooks.fixtures";
import { ProjectView } from "./project-view";
import { installBrowserStubs, makeQueryClient, OWNER, RESEARCHER, renderPage } from "./test-utils";

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

const navigation = vi.hoisted(() => ({
  params: new URLSearchParams(),
  router: { push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() },
}));
vi.mock("next/navigation", () => ({
  useSearchParams: () => navigation.params,
  useRouter: () => navigation.router,
}));

const PROJECT = "33333333-3333-4333-8333-333333333333";
const path = { project_id: PROJECT };

const SETTINGS: ProjectSettings = {
  privacy: "standard",
  allow_free_models: true,
  auto_approve: false,
  approval_expiry_days: 7,
};

function project(role: ProjectRole): ProjectOut {
  return {
    id: PROJECT,
    name: "Depth estimation",
    description: "Monocular depth on NYU Depth v2",
    privacy: "standard",
    allow_free_models: true,
    created_by: OWNER.id,
    created_at: "2026-10-01T00:00:00Z",
    my_role: role,
  };
}

const MEMBERS: MemberOut[] = [
  { user_id: OWNER.id, email: OWNER.email, name: OWNER.name, role: "owner" },
];

let saved: unknown[];

beforeAll(() => {
  installBrowserStubs();
});

beforeEach(() => {
  saved = [];
  navigation.params = new URLSearchParams("tab=settings");
  mockApi(async (request, url) => {
    if (url === `/api/v1/projects/${PROJECT}/settings` && request.method !== "GET") {
      const body = (await request.json()) as ProjectSettings;
      saved.push(body);
      return json(200, body);
    }
    if (url === `/api/v1/projects/${PROJECT}/settings`) {
      return json(200, saved.at(-1) ?? SETTINGS);
    }
    if (url === `/api/v1/projects/${PROJECT}`) {
      return json(200, project("owner"));
    }
    return json(404, { detail: "project.not_found" });
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.restoreAllMocks();
});

function renderProject(role: ProjectRole, user = role === "owner" ? OWNER : RESEARCHER) {
  const queryClient = makeQueryClient();
  queryClient.setQueryData(getProjectQueryKey({ path }), project(role));
  queryClient.setQueryData(getProjectSettingsQueryKey({ path }), SETTINGS);
  queryClient.setQueryData(listMembersQueryKey({ path }), MEMBERS);
  return renderPage(<ProjectView projectId={PROJECT} />, { user, queryClient });
}

describe("ProjectView tabs", () => {
  it("opens the tab named in the URL and keeps the chosen tab there", () => {
    const replaceState = vi.spyOn(window.history, "replaceState");
    renderProject("owner");
    expect(screen.getByRole("tab", { name: "Settings" }).getAttribute("aria-selected")).toBe(
      "true",
    );
    expect(screen.getByRole("heading", { name: "Settings" })).toBeTruthy();

    fireEvent.click(screen.getByRole("tab", { name: "Members" }));
    expect(screen.getByRole("tab", { name: "Members" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByRole("heading", { name: "Members" })).toBeTruthy();
    expect(replaceState).toHaveBeenCalledWith(null, "", "/?tab=members");
  });

  it("falls back to the runs tab for an unknown tab", () => {
    navigation.params = new URLSearchParams("tab=nonsense");
    renderProject("owner");
    expect(screen.getByRole("tab", { name: "Runs" }).getAttribute("aria-selected")).toBe("true");
  });
});

describe("Project settings", () => {
  it("are read-only for researchers", () => {
    renderProject("researcher");
    expect(
      screen.getByText("Only project owners and lab admins can change these settings."),
    ).toBeTruthy();
    for (const name of ["Allow free models", "Approve stages automatically"]) {
      expect(screen.getByRole("switch", { name }).getAttribute("aria-readonly")).toBe("true");
    }
    expect(screen.getByRole("radiogroup", { name: "Privacy" }).getAttribute("aria-readonly")).toBe(
      "true",
    );
    expect(
      (screen.getByRole("spinbutton", { name: "Approval expiry" }) as HTMLInputElement).readOnly,
    ).toBe(true);
    expect(screen.queryByRole("button", { name: "Save changes" })).toBeNull();
    // Nothing can be changed either.
    fireEvent.click(screen.getByRole("switch", { name: "Approve stages automatically" }));
    expect(
      screen
        .getByRole("switch", { name: "Approve stages automatically" })
        .getAttribute("aria-checked"),
    ).toBe("false");
    // Coding is never auto-approved, whoever reads the settings.
    expect(screen.getByText(/The coding stage is never approved automatically/)).toBeTruthy();
  });

  it("are saved by owners", async () => {
    renderProject("owner");
    const save = screen.getByRole("button", { name: "Save changes" }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);

    fireEvent.click(screen.getByRole("switch", { name: "Approve stages automatically" }));
    await waitFor(() => expect(save.disabled).toBe(false));
    fireEvent.click(save);

    await waitFor(() => expect(saved).toEqual([{ ...SETTINGS, auto_approve: true }]));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Settings saved."));
  });

  it("explain an expiry outside 1 to 30 days", async () => {
    renderProject("owner");
    const expiry = screen.getByRole("spinbutton", { name: "Approval expiry" });
    fireEvent.change(expiry, { target: { value: "45" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Choose between 1 and 30 days.")).toBeTruthy();
    expect(saved).toEqual([]);
  });
});
