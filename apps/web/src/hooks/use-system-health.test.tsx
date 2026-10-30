// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { SystemHealthOut } from "@/client";
import { client } from "@/client/client.gen";
import { configureApiClient } from "@/lib/api-client";
import { useSystemHealth } from "./use-system-health";

const HEALTH: SystemHealthOut = {
  status: "degraded",
  checked_at: "2026-10-30T01:00:00Z",
  checks: [
    { name: "postgres", status: "ok", latency_ms: 2.5, detail: null },
    { name: "temporal", status: "degraded", latency_ms: 950, detail: "temporal.slow" },
  ],
};

const fetchMock = vi.fn<typeof fetch>();

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => "visible" });
  vi.useFakeTimers();
  configureApiClient();
  client.setConfig({ baseUrl: "http://localhost:8080", fetch: fetchMock });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  fetchMock.mockReset();
});

async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

function setup() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return renderHook(() => useSystemHealth(), { wrapper });
}

describe("useSystemHealth", () => {
  it("probes the system every 15 seconds", async () => {
    fetchMock.mockImplementation(async () => json(200, HEALTH));
    const { result } = setup();
    await advance(0);
    expect(result.current.data).toEqual(HEALTH);
    expect(requestPath()).toBe("/api/v1/admin/health");
    await advance(14_000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await advance(1_000);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("stops asking someone who is not a lab admin", async () => {
    fetchMock.mockImplementation(async () => json(403, { detail: "permission.denied" }));
    const { result } = setup();
    await advance(0);
    expect(result.current.error).toMatchObject({ code: "permission.denied", status: 403 });
    await advance(120_000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

/** The path of the request the generated client sent first. */
function requestPath(): string {
  const request = fetchMock.mock.calls[0]?.[0];
  return request instanceof Request ? new URL(request.url).pathname : "";
}
