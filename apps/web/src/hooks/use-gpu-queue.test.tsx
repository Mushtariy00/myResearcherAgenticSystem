// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { GpuQueueOut } from "@/client";
import { client } from "@/client/client.gen";
import { configureApiClient } from "@/lib/api-client";
import { useGpuQueue } from "./use-gpu-queue";

const QUEUE: GpuQueueOut = {
  gpu: {
    name: "GTX 1060 6GB",
    memory_total_mb: 6144,
    memory_used_mb: 2048,
    utilization_percent: 64,
    temperature_c: 61,
    power_draw_w: 80,
    power_limit_w: 120,
    fan_percent: 40,
    sampled_at: "2026-10-30T01:00:00Z",
    demo: true,
  },
  concurrency: 1,
  running: [],
  queued: [],
  my_position: null,
  my_jobs: 0,
  per_user_limit: 2,
  demo: true,
};

const fetchMock = vi.fn<typeof fetch>();
let visibility: DocumentVisibilityState = "visible";

beforeEach(() => {
  visibility = "visible";
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    get: () => visibility,
  });
  vi.useFakeTimers();
  configureApiClient();
  client.setConfig({ baseUrl: "http://localhost:8080", fetch: fetchMock });
  fetchMock.mockImplementation(
    async () =>
      new Response(JSON.stringify(QUEUE), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
  );
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

describe("useGpuQueue", () => {
  it("refreshes every 5 seconds while the page is visible", async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    queryClient.mount();
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useGpuQueue(), { wrapper });
    await advance(0);
    expect(result.current.data).toEqual(QUEUE);
    expect(requestPath()).toBe("/api/v1/gpu/queue");
    await advance(5_000);
    expect(fetchMock).toHaveBeenCalledTimes(2);

    visibility = "hidden";
    window.dispatchEvent(new Event("visibilitychange"));
    await advance(30_000);
    expect(fetchMock).toHaveBeenCalledTimes(2);

    visibility = "visible";
    window.dispatchEvent(new Event("visibilitychange"));
    await advance(0);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    queryClient.unmount();
  });
});

/** The path of the request the generated client sent first. */
function requestPath(): string {
  const request = fetchMock.mock.calls[0]?.[0];
  return request instanceof Request ? new URL(request.url).pathname : "";
}
