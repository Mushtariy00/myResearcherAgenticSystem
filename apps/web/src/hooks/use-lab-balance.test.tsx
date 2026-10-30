// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { LabBalanceOut } from "@/client";
import { client } from "@/client/client.gen";
import { configureApiClient } from "@/lib/api-client";
import { useLabBalance } from "./use-lab-balance";

const BALANCE: LabBalanceOut = {
  balance_usd: "42.10",
  month: "2026-10",
  spent_this_month_usd: "7.90",
  free_daily_limit: 1000,
  free_calls_today: 120,
  auto_top_up: false,
  alert_floor_usd: "10.00",
  below_floor: false,
  checked_at: "2026-10-30T01:00:00Z",
  demo: true,
};

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  configureApiClient();
  client.setConfig({ baseUrl: "http://localhost:8080", fetch: fetchMock });
});

afterEach(() => {
  cleanup();
  fetchMock.mockReset();
});

function setup() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return renderHook(() => useLabBalance(), { wrapper });
}

describe("useLabBalance", () => {
  it("loads the lab's balance", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify(BALANCE), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const { result } = setup();
    await waitFor(() => expect(result.current.data).toEqual(BALANCE));
    expect(requestPath()).toBe("/api/v1/admin/balance");
  });

  it("reports a non-admin's 403 with the API's code", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: "permission.denied" }), {
        status: 403,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const { result } = setup();
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toMatchObject({ code: "permission.denied", status: 403 });
  });
});

/** The path of the request the generated client sent first. */
function requestPath(): string {
  const request = fetchMock.mock.calls[0]?.[0];
  return request instanceof Request ? new URL(request.url).pathname : "";
}
