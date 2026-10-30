// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AuditEntryOut } from "@/client";
import { client } from "@/client/client.gen";
import { configureApiClient } from "@/lib/api-client";
import { useAuditLog } from "./use-audit-log";

function entry(id: number): AuditEntryOut {
  return {
    id,
    actor_id: "user-1",
    actor_name: "Ada",
    actor_email: "ada@lab.example",
    action: "run.cancel",
    target_type: "run",
    target_id: "r-1",
    details: {},
    created_at: "2026-10-30T01:00:00Z",
  };
}

const fetchMock = vi.fn<typeof fetch>();
let requests: URLSearchParams[] = [];

beforeEach(() => {
  requests = [];
  configureApiClient();
  client.setConfig({ baseUrl: "http://localhost:8080", fetch: fetchMock });
  fetchMock.mockImplementation(async (input) => {
    const params = new URL((input as Request).url).searchParams;
    requests.push(params);
    const offset = Number(params.get("offset"));
    return new Response(JSON.stringify({ items: [entry(1000 - offset)], total: 120 }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
});

afterEach(() => {
  cleanup();
  fetchMock.mockReset();
});

function setup(initialProps: { page: number; action?: string | null; size?: number }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return renderHook(
    ({ page, action, size }: { page: number; action?: string | null; size?: number }) =>
      useAuditLog(page, action, size),
    { wrapper, initialProps },
  );
}

describe("useAuditLog", () => {
  it("loads one page with the paging the API expects", async () => {
    const { result } = setup({ page: 0 });
    await waitFor(() => expect(result.current.items).toEqual([entry(1000)]));
    expect(Object.fromEntries(requests[0] ?? [])).toEqual({ limit: "50", offset: "0" });
    expect(result.current).toMatchObject({
      total: 120,
      pageIndex: 0,
      pageSize: 50,
      pageCount: 3,
      hasPreviousPage: false,
      hasNextPage: true,
    });
  });

  it("filters by action and keeps the page on screen while the next one loads", async () => {
    const { result, rerender } = setup({ page: 0, action: " run.cancel ", size: 25 });
    await waitFor(() => expect(result.current.items).toHaveLength(1));
    expect(Object.fromEntries(requests[0] ?? [])).toEqual({
      limit: "25",
      offset: "0",
      action: "run.cancel",
    });

    rerender({ page: 4, action: "run.cancel", size: 25 });
    expect(result.current.items).toEqual([entry(1000)]);
    expect(result.current.query.isPlaceholderData).toBe(true);
    await waitFor(() => expect(result.current.items).toEqual([entry(900)]));
    expect(result.current).toMatchObject({ pageIndex: 4, pageCount: 5, hasNextPage: false });
  });

  it("ignores an empty filter and impossible pages", async () => {
    setup({ page: -3, action: "  " });
    await waitFor(() => expect(requests).toHaveLength(1));
    expect(Object.fromEntries(requests[0] ?? [])).toEqual({ limit: "50", offset: "0" });
  });
});
