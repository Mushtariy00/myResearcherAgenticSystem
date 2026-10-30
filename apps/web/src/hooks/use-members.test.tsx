// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { MemberOut } from "@/client";
import { getProjectQueryKey } from "@/client/@tanstack/react-query.gen";
import { client } from "@/client/client.gen";
import { configureApiClient } from "@/lib/api-client";
import { isMemberEmail, useMembers } from "./use-members";

const PROJECT = "33333333-3333-4333-8333-333333333333";
const BASE = `/api/v1/projects/${PROJECT}/members`;

const OWNER: MemberOut = {
  user_id: "u-owner",
  email: "owner@lab.example",
  name: "Owner",
  role: "owner",
};
const ADA: MemberOut = { user_id: "u-ada", email: "ada@lab.example", name: "Ada", role: "viewer" };

type Call = { method: string; path: string; body: unknown };

const fetchMock = vi.fn<typeof fetch>();
let calls: Call[] = [];
let members: MemberOut[] = [];
let respond: (call: Call) => Response | Promise<Response> | null;

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  calls = [];
  members = [OWNER, ADA];
  respond = () => null;
  configureApiClient();
  client.setConfig({ baseUrl: "http://localhost:8080", fetch: fetchMock });
  fetchMock.mockImplementation(async (input) => {
    const request = input as Request;
    const path = new URL(request.url).pathname;
    const text = await request.text();
    const call = { method: request.method, path, body: text ? JSON.parse(text) : undefined };
    calls.push(call);
    const custom = await respond(call);
    if (custom) {
      return custom;
    }
    if (request.method === "GET" && path === BASE) {
      return json(200, members);
    }
    if (request.method === "GET" && path === `/api/v1/projects/${PROJECT}`) {
      return json(200, {});
    }
    return json(404, { detail: "unknown" });
  });
});

afterEach(() => {
  cleanup();
  fetchMock.mockReset();
});

function setup() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { ...renderHook(() => useMembers(PROJECT), { wrapper }), queryClient };
}

const listFetches = () => calls.filter((call) => call.method === "GET" && call.path === BASE);

describe("useMembers", () => {
  it("lists the members", async () => {
    const { result } = setup();
    expect(result.current.members).toEqual([]);
    await waitFor(() => expect(result.current.members).toEqual([OWNER, ADA]));
  });

  it("adds someone by email and shows them at once", async () => {
    const grace: MemberOut = {
      user_id: "u-grace",
      email: "grace@lab.example",
      name: "Grace",
      role: "researcher",
    };
    respond = (call) => (call.method === "POST" ? json(201, grace) : null);
    const { result, queryClient } = setup();
    queryClient.setQueryData(getProjectQueryKey({ path: { project_id: PROJECT } }), {} as never);
    await waitFor(() => expect(result.current.members).toHaveLength(2));

    let outcome: unknown;
    await act(async () => {
      outcome = await result.current.add({ email: "  grace@lab.example ", role: "researcher" });
    });
    expect(outcome).toEqual({ ok: true, data: grace });
    expect(calls.find((call) => call.method === "POST")).toEqual({
      method: "POST",
      path: BASE,
      body: { email: "grace@lab.example", role: "researcher" },
    });
    expect(result.current.members.map((member) => member.user_id)).toContain("u-grace");
    // The project's my_role may change with a membership.
    expect(
      queryClient.getQueryState(getProjectQueryKey({ path: { project_id: PROJECT } }))
        ?.isInvalidated,
    ).toBe(true);
  });

  it("refuses an email the API would refuse, without asking it", async () => {
    const { result } = setup();
    await waitFor(() => expect(result.current.members).toHaveLength(2));
    let outcome: unknown;
    await act(async () => {
      outcome = await result.current.add({ email: "not an email", role: "viewer" });
    });
    expect(outcome).toMatchObject({ ok: false, error: { code: "validation.failed" } });
    expect(calls.some((call) => call.method === "POST")).toBe(false);
    expect(isMemberEmail("ada@lab.example")).toBe(true);
    expect(isMemberEmail("ada@@")).toBe(false);
  });

  it("explains an email nobody was invited with", async () => {
    respond = (call) => (call.method === "POST" ? json(404, { detail: "user.not_found" }) : null);
    const { result } = setup();
    await waitFor(() => expect(result.current.members).toHaveLength(2));
    await act(async () => {
      await result.current.add({ email: "nobody@lab.example", role: "viewer" });
    });
    expect(result.current.lastError).toMatchObject({
      action: "add",
      userId: null,
      error: { code: "user.not_found" },
      notFound: true,
      lastOwner: false,
    });
  });

  it("names the member when the email belongs to one already (409), so roles change in the list", async () => {
    respond = (call) => (call.method === "POST" ? json(409, { detail: "member.exists" }) : null);
    const { result } = setup();
    await waitFor(() => expect(result.current.members).toHaveLength(2));
    await act(async () => {
      await result.current.add({ email: "ADA@lab.example", role: "owner" });
    });
    await waitFor(() =>
      expect(result.current.lastError).toMatchObject({
        action: "add",
        userId: ADA.user_id,
        error: { code: "member.exists" },
        exists: true,
      }),
    );
    // Nobody's role changed; the list is refreshed in case they joined after it loaded.
    expect(calls.filter((call) => call.method === "PATCH")).toEqual([]);
    await waitFor(() => expect(listFetches()).toHaveLength(2));
  });

  it("changes a role, marking the member busy until the API answers", async () => {
    let release: (response: Response) => void = () => {};
    respond = (call) =>
      call.method === "PATCH"
        ? new Promise<Response>((resolve) => {
            release = resolve;
          })
        : null;
    const { result } = setup();
    await waitFor(() => expect(result.current.members).toHaveLength(2));

    let pending: Promise<unknown> = Promise.resolve();
    act(() => {
      pending = result.current.updateRole("u-ada", "researcher");
    });
    expect(result.current.pendingUserIds.has("u-ada")).toBe(true);
    // Not optimistic: the list still shows the old role.
    expect(result.current.members[1]?.role).toBe("viewer");
    await waitFor(() => expect(calls.some((call) => call.method === "PATCH")).toBe(true));
    expect(calls.find((call) => call.method === "PATCH")).toMatchObject({
      path: `${BASE}/u-ada`,
      body: { role: "researcher" },
    });

    await act(async () => {
      release(json(200, { ...ADA, role: "researcher" }));
      await pending;
    });
    expect(result.current.pendingUserIds.size).toBe(0);
    expect(result.current.members[1]?.role).toBe("researcher");
  });

  it("explains that the last owner must stay an owner", async () => {
    respond = (call) =>
      call.method === "PATCH" ? json(409, { detail: "member.last_owner" }) : null;
    const { result } = setup();
    await waitFor(() => expect(result.current.members).toHaveLength(2));
    let outcome: unknown;
    await act(async () => {
      outcome = await result.current.updateRole("u-owner", "viewer");
    });
    expect(outcome).toMatchObject({ ok: false, error: { code: "member.last_owner", status: 409 } });
    expect(result.current.lastError).toMatchObject({
      action: "updateRole",
      userId: "u-owner",
      lastOwner: true,
      notFound: false,
    });
    expect(result.current.members[0]?.role).toBe("owner");

    act(() => result.current.clearError());
    expect(result.current.lastError).toBeNull();
  });

  it("removes a member", async () => {
    respond = (call) => (call.method === "DELETE" ? new Response(null, { status: 204 }) : null);
    const { result } = setup();
    await waitFor(() => expect(result.current.members).toHaveLength(2));
    let outcome: unknown;
    await act(async () => {
      outcome = await result.current.remove("u-ada");
    });
    expect(outcome).toEqual({ ok: true, data: null });
    expect(calls.find((call) => call.method === "DELETE")?.path).toBe(`${BASE}/u-ada`);
    expect(result.current.members).toEqual([OWNER]);
  });

  it("refreshes the list when the member is already gone", async () => {
    respond = (call) =>
      call.method === "DELETE" ? json(404, { detail: "member.not_found" }) : null;
    const { result } = setup();
    await waitFor(() => expect(result.current.members).toHaveLength(2));
    members = [OWNER];
    await act(async () => {
      await result.current.remove("u-ada");
    });
    expect(result.current.lastError).toMatchObject({ action: "remove", notFound: true });
    await waitFor(() => expect(result.current.members).toEqual([OWNER]));
    expect(listFetches().length).toBeGreaterThanOrEqual(2);
  });
});
