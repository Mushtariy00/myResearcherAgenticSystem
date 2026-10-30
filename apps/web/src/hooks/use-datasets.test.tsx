// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { DatasetList } from "@/client";
import { client } from "@/client/client.gen";
import { configureApiClient } from "@/lib/api-client";
import { useDatasets } from "./use-datasets";

const DATASETS: DatasetList = {
  items: [
    {
      id: "nyu2",
      name: "NYU Depth V2",
      version: "1.0",
      tasks: ["depth"],
      modality: "rgb-d",
      scenes: "indoor",
      description: "Indoor scenes",
      width: 640,
      height: 480,
      samples: 1449,
      splits: [{ name: "train", samples: 795 }],
      size_bytes: 2_800_000_000,
      license: "research",
      homepage: null,
      mount_path: "/data/nyu2",
      checksum_sha256: "a".repeat(64),
      registered_at: "2026-10-01T00:00:00Z",
      contract: {
        inputs: "rgb",
        targets: "depth",
        units: "m",
        valid_range: null,
        missing_values: null,
        evaluation: null,
      },
      demo: true,
    },
  ],
  demo: true,
};

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  configureApiClient();
  client.setConfig({ baseUrl: "http://localhost:8080", fetch: fetchMock });
  fetchMock.mockImplementation(
    async () =>
      new Response(JSON.stringify(DATASETS), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
  );
});

afterEach(() => {
  cleanup();
  fetchMock.mockReset();
});

describe("useDatasets", () => {
  it("loads the registry once and keeps it", async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
    const first = renderHook(() => useDatasets(), { wrapper });
    await waitFor(() => expect(first.result.current.data).toEqual(DATASETS));
    expect(requestPath()).toBe("/api/v1/datasets");

    // Another component asking for it a moment later is served from the cache.
    const second = renderHook(() => useDatasets(), { wrapper });
    expect(second.result.current.data).toEqual(DATASETS);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("keeps a size and checksum the executor has not measured yet unknown, not 0", async () => {
    const [nyu2] = DATASETS.items;
    if (!nyu2) {
      throw new Error("fixture changed");
    }
    const unmeasured: DatasetList = {
      items: [{ ...nyu2, size_bytes: null, checksum_sha256: null, demo: false }],
      demo: false,
    };
    fetchMock.mockImplementation(
      async () =>
        new Response(JSON.stringify(unmeasured), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    );
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useDatasets(), { wrapper });
    await waitFor(() => expect(result.current.data).toEqual(unmeasured));
    expect(result.current.data?.items[0]).toMatchObject({
      size_bytes: null,
      checksum_sha256: null,
    });
  });
});

/** The path of the request the generated client sent first. */
function requestPath(): string {
  const request = fetchMock.mock.calls[0]?.[0];
  return request instanceof Request ? new URL(request.url).pathname : "";
}
