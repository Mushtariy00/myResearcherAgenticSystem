// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { RecentRunOut } from "@/client";
import { client } from "@/client/client.gen";
import { configureApiClient } from "@/lib/api-client";
import { RUN_CONFIG_DEFAULTS } from "@/lib/new-run-schema";
import { useRecentRuns } from "./use-recent-runs";

const RUN: RecentRunOut = {
  id: "22222222-2222-4222-8222-222222222222",
  project_id: "33333333-3333-4333-8333-333333333333",
  project_name: "Depth lab",
  owner_id: "user-1",
  topic: "Monocular depth",
  status: "awaiting_approval",
  llm_policy: "auto",
  budget_cap_usd: null,
  config: { ...RUN_CONFIG_DEFAULTS },
  error: null,
  created_at: "2026-10-30T00:00:00Z",
  updated_at: "2026-10-30T01:00:00Z",
};

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  configureApiClient();
  client.setConfig({ baseUrl: "http://localhost:8080", fetch: fetchMock });
  fetchMock.mockImplementation(
    async () =>
      new Response(JSON.stringify([RUN]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
  );
});

afterEach(() => {
  cleanup();
  fetchMock.mockReset();
});

function render(limit?: number, status?: RecentRunOut["status"]) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return renderHook(() => useRecentRuns(limit, status), { wrapper });
}

/** The URL of the last request the generated client sent. */
function lastUrl(): URL {
  const request = fetchMock.mock.calls.at(-1)?.[0];
  return new URL(request instanceof Request ? request.url : "http://localhost:8080/none");
}

describe("useRecentRuns", () => {
  it("loads the newest runs, 20 by default", async () => {
    const { result } = render();
    await waitFor(() => expect(result.current.data).toEqual([RUN]));
    expect(lastUrl().pathname).toBe("/api/v1/runs");
    expect(Object.fromEntries(lastUrl().searchParams)).toEqual({ limit: "20" });
  });

  it("keeps one status, and the limit within what the API accepts", async () => {
    const { result } = render(500, "awaiting_approval");
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(Object.fromEntries(lastUrl().searchParams)).toEqual({
      limit: "100",
      status: "awaiting_approval",
    });
  });
});
