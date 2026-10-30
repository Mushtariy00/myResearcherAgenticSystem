// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { MemberOut } from "@/client";
import { listMembersQueryKey } from "@/client/@tanstack/react-query.gen";
import { json, mockApi, requestsOf } from "@/hooks/run-hooks.fixtures";
import { MembersPanel } from "./members-panel";
import {
  chooseOption,
  installBrowserStubs,
  makeQueryClient,
  OWNER,
  RESEARCHER,
  renderPage,
} from "./test-utils";

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));

const PROJECT = "33333333-3333-4333-8333-333333333333";
const MEMBERS_PATH = `/api/v1/projects/${PROJECT}/members`;

const ADA: MemberOut = { user_id: OWNER.id, email: OWNER.email, name: OWNER.name, role: "owner" };
const GRACE: MemberOut = {
  user_id: RESEARCHER.id,
  email: RESEARCHER.email,
  name: RESEARCHER.name,
  role: "researcher",
};

let fetchMock: ReturnType<typeof mockApi>;
let bodies: unknown[];
/** The API's member list: changes stick, as they would on the server. */
let members: MemberOut[];

beforeAll(() => {
  installBrowserStubs();
});

beforeEach(() => {
  bodies = [];
  members = [ADA, GRACE];
  fetchMock = mockApi(async (request, path) => {
    if (request.method === "GET" && path === MEMBERS_PATH) {
      return json(200, members);
    }
    if (request.method === "PATCH" && path === `${MEMBERS_PATH}/${GRACE.user_id}`) {
      const body = (await request.json()) as { role: MemberOut["role"] };
      bodies.push(body);
      members = members.map((member) =>
        member.user_id === GRACE.user_id ? { ...member, role: body.role } : member,
      );
      return json(200, { ...GRACE, role: body.role });
    }
    if (request.method === "PATCH" && path === `${MEMBERS_PATH}/${ADA.user_id}`) {
      bodies.push(await request.json());
      return json(409, { detail: "member.last_owner" });
    }
    if (request.method === "DELETE" && path === `${MEMBERS_PATH}/${GRACE.user_id}`) {
      members = members.filter((member) => member.user_id !== GRACE.user_id);
      return new Response(null, { status: 204 });
    }
    if (request.method === "POST" && path === MEMBERS_PATH) {
      return json(409, { detail: "member.exists" });
    }
    return json(404, { detail: "member.not_found" });
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderPanel(canManage = true) {
  const queryClient = makeQueryClient();
  queryClient.setQueryData(listMembersQueryKey({ path: { project_id: PROJECT } }), [ADA, GRACE]);
  return renderPage(<MembersPanel projectId={PROJECT} canManage={canManage} />, {
    user: OWNER,
    queryClient,
  });
}

function row(name: string): HTMLElement {
  const item = screen.getByText(name).closest("li");
  if (!item) {
    throw new Error(`No member row for ${name}`);
  }
  return item;
}

describe("MembersPanel", () => {
  it("changes a member's role and shows the new one", async () => {
    renderPanel();
    await chooseOption(screen.getByRole("combobox", { name: "Role of Grace Hopper" }), "Viewer");

    await waitFor(() => expect(bodies).toEqual([{ role: "viewer" }]));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Grace Hopper is now: Viewer."));
    expect(
      within(row("Grace Hopper")).getByRole("combobox", { name: "Role of Grace Hopper" })
        .textContent,
    ).toContain("Viewer");
  });

  it("asks before the last owner steps down, then explains why the API refused", async () => {
    renderPanel();
    await chooseOption(
      screen.getByRole("combobox", { name: "Role of Ada Lovelace" }),
      "Researcher",
    );

    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText("Change your own role to Researcher?")).toBeTruthy();
    expect(bodies).toEqual([]);
    fireEvent.click(within(dialog).getByRole("button", { name: "Change my role" }));

    const alert = await within(row("Ada Lovelace")).findByRole("alert");
    expect(alert.textContent).toBe(
      "A project needs at least one owner. Make someone else an owner first.",
    );
    expect(bodies).toEqual([{ role: "researcher" }]);
    // Nothing changed: the role on screen is still the one the API has.
    expect(
      within(row("Ada Lovelace")).getByRole("combobox", { name: "Role of Ada Lovelace" })
        .textContent,
    ).toContain("Owner");
    expect(toast.success).not.toHaveBeenCalled();
  });

  it("points to the role control when the person added is a member already", async () => {
    renderPanel();
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: GRACE.email } });
    fireEvent.click(screen.getByRole("button", { name: "Add member" }));

    expect(
      await screen.findByText(
        "This person is already a member. Change their role in the member list instead.",
      ),
    ).toBeTruthy();
    expect(toast.success).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Change their role" }));
    expect(document.activeElement).toBe(
      screen.getByRole("combobox", { name: "Role of Grace Hopper" }),
    );
  });

  it("removes a member only after confirmation", async () => {
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Remove Grace Hopper" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText("Remove Grace Hopper?")).toBeTruthy();
    expect(requestsOf(fetchMock).some((call) => call.startsWith("DELETE"))).toBe(false);

    fireEvent.click(within(dialog).getByRole("button", { name: "Remove" }));
    await waitFor(() =>
      expect(requestsOf(fetchMock)).toContain(`DELETE ${MEMBERS_PATH}/${GRACE.user_id}`),
    );
    await waitFor(() => expect(screen.queryByText("Grace Hopper")).toBeNull());
    expect(toast.success).toHaveBeenCalledWith("Grace Hopper was removed from this project.");
  });

  it("shows the list without controls to people who cannot manage members", () => {
    renderPanel(false);
    expect(screen.getByText("Grace Hopper")).toBeTruthy();
    expect(screen.queryByRole("combobox")).toBeNull();
    expect(screen.queryByRole("button", { name: /Remove/ })).toBeNull();
    expect(screen.queryByRole("button", { name: "Add member" })).toBeNull();
    expect(
      screen.getByText("Only project owners and lab admins can change who is in this project."),
    ).toBeTruthy();
  });
});
