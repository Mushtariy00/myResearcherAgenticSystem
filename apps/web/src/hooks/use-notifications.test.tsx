// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { NotificationList, NotificationOut } from "@/client";
import { client } from "@/client/client.gen";
import { configureApiClient } from "@/lib/api-client";
import { useNotifications } from "./use-notifications";

function item(key: string, read = false): NotificationOut {
  return {
    key,
    kind: "run_completed",
    created_at: "2026-10-30T01:00:00Z",
    read,
    run_id: "22222222-2222-4222-8222-222222222222",
    project_id: "33333333-3333-4333-8333-333333333333",
    stage: null,
    params: { topic: "Depth", project: "Lab", error: null },
  };
}

const LIST: NotificationList = {
  items: [item("a"), item("b", true), item("c")],
  unread_count: 5,
};

const fetchMock = vi.fn<typeof fetch>();
let marks: unknown[] = [];
let markResponse: () => Promise<Response>;

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** A response that arrives when the test says so. */
function deferred() {
  let release: (response: Response) => void = () => {};
  const promise = new Promise<Response>((resolve) => {
    release = resolve;
  });
  return { promise, release };
}

beforeEach(() => {
  marks = [];
  markResponse = async () => json(200, LIST);
  configureApiClient();
  client.setConfig({ baseUrl: "http://localhost:8080", fetch: fetchMock });
  fetchMock.mockImplementation(async (input) => {
    const request = input as Request;
    const path = new URL(request.url).pathname;
    if (path === "/api/v1/me/notifications/read") {
      marks.push(await request.json());
      return markResponse();
    }
    if (path === "/api/v1/me/notifications") {
      return json(200, LIST);
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
  return renderHook(() => useNotifications(), { wrapper });
}

const readFlags = (list: { items: NotificationOut[] }) =>
  list.items.map((notification) => [notification.key, notification.read]);

describe("useNotifications", () => {
  it("lists the notifications with the overall unread count", async () => {
    const { result } = setup();
    expect(result.current.unreadCount).toBeNull();
    expect(result.current.items).toEqual([]);
    await waitFor(() => expect(result.current.unreadCount).toBe(5));
    expect(result.current.items).toEqual(LIST.items);
  });

  it("shows notifications read at once, then keeps the API's answer", async () => {
    const answer = deferred();
    markResponse = () => answer.promise;
    const { result } = setup();
    await waitFor(() => expect(result.current.unreadCount).toBe(5));

    let marking: Promise<unknown> = Promise.resolve();
    act(() => {
      marking = result.current.markRead(["a", "b"]);
    });
    // Only "a" was unread; "b" is not sent again.
    await waitFor(() => expect(marks).toEqual([{ keys: ["a"] }]));
    expect(readFlags(result.current)).toEqual([
      ["a", true],
      ["b", true],
      ["c", false],
    ]);
    expect(result.current.unreadCount).toBe(4);
    expect(result.current.isMarking).toBe(true);

    const server: NotificationList = { items: [item("a", true), item("b", true)], unread_count: 3 };
    await act(async () => {
      answer.release(json(200, server));
      await marking;
    });
    await waitFor(() => expect(result.current.items).toEqual(server.items));
    expect(result.current.unreadCount).toBe(3);
    expect(result.current.isMarking).toBe(false);
  });

  it("sends nothing when everything given is read already", async () => {
    const { result } = setup();
    await waitFor(() => expect(result.current.unreadCount).toBe(5));
    let outcome: unknown;
    await act(async () => {
      outcome = await result.current.markRead(["b", "b", ""]);
    });
    expect(outcome).toMatchObject({ ok: true });
    expect(marks).toEqual([]);
  });

  it("marks everything read, listed or not", async () => {
    markResponse = async () =>
      json(200, { items: LIST.items.map((n) => ({ ...n, read: true })), unread_count: 0 });
    const { result } = setup();
    await waitFor(() => expect(result.current.unreadCount).toBe(5));
    let outcome: unknown;
    await act(async () => {
      outcome = await result.current.markAllRead();
    });
    expect(outcome).toMatchObject({ ok: true, data: { unread_count: 0 } });
    expect(marks).toEqual([{ all: true }]);
    await waitFor(() => expect(result.current.unreadCount).toBe(0));
    expect(result.current.items.every((notification) => notification.read)).toBe(true);
  });

  it("puts the list back and reports why when the API refuses", async () => {
    markResponse = async () => json(503, { detail: "db.unavailable" });
    const { result } = setup();
    await waitFor(() => expect(result.current.unreadCount).toBe(5));
    let outcome: unknown;
    await act(async () => {
      outcome = await result.current.markRead(["c"]);
    });
    expect(outcome).toMatchObject({ ok: false, error: { code: "db.unavailable", status: 503 } });
    await waitFor(() => expect(result.current.markError?.code).toBe("db.unavailable"));
    await waitFor(() => expect(readFlags(result.current)).toEqual(readFlags(LIST)));
    expect(result.current.unreadCount).toBe(5);
  });
});
