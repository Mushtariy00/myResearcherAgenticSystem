// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { UsageOut } from "@/client";
import { client } from "@/client/client.gen";
import { configureApiClient } from "@/lib/api-client";
import { type UsageScope, useUsage } from "./use-usage";

const totals = {
  paid_usd: "1.25",
  paid_calls: 10,
  free_calls: 40,
  prompt_tokens: 1000,
  completion_tokens: 500,
};

function usage(scope: UsageScope, days: number): UsageOut {
  return {
    scope,
    days,
    since: "2026-10-01T00:00:00Z",
    until: "2026-10-31T00:00:00Z",
    totals,
    by_day: [],
    by_model: [],
    top_runs: [],
    by_user: [],
    budget: { month: "2026-10", monthly_usd: "20", spent_usd: "1.25", remaining_usd: "18.75" },
    demo: false,
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
    const body = usage(params.get("scope") as UsageScope, Number(params.get("days")));
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
});

afterEach(() => {
  cleanup();
  fetchMock.mockReset();
});

function setup(initialProps: { scope?: UsageScope; days?: number; enabled?: boolean }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return renderHook(
    ({ scope, days, enabled }: { scope?: UsageScope; days?: number; enabled?: boolean }) =>
      useUsage(scope, days, { enabled }),
    { wrapper, initialProps },
  );
}

describe("useUsage", () => {
  it("loads the caller's own usage over 30 days by default", async () => {
    const { result } = setup({});
    await waitFor(() => expect(result.current.data?.totals).toEqual(totals));
    expect(Object.fromEntries(requests[0] ?? [])).toEqual({ scope: "me", days: "30" });
  });

  it("keeps the window within the API's 7..90 days", async () => {
    const { rerender } = setup({ scope: "lab", days: 3 });
    await waitFor(() => expect(requests).toHaveLength(1));
    expect(Object.fromEntries(requests[0] ?? [])).toEqual({ scope: "lab", days: "7" });
    rerender({ scope: "lab", days: 365 });
    await waitFor(() => expect(requests).toHaveLength(2));
    expect(requests[1]?.get("days")).toBe("90");
  });

  it("keeps the figures while another window loads, but never across scopes", async () => {
    const { result, rerender } = setup({ scope: "me", days: 30 });
    await waitFor(() => expect(result.current.data?.days).toBe(30));
    rerender({ scope: "me", days: 7 });
    expect(result.current.data?.days).toBe(30);
    expect(result.current.isPlaceholderData).toBe(true);
    await waitFor(() => expect(result.current.data?.days).toBe(7));

    rerender({ scope: "lab", days: 7 });
    expect(result.current.data).toBeUndefined();
    await waitFor(() => expect(result.current.data?.scope).toBe("lab"));
  });

  it("waits while disabled", () => {
    const { result } = setup({ scope: "lab", enabled: false });
    expect(result.current.fetchStatus).toBe("idle");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
