// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ModelRoutingOut } from "@/client";
import { client } from "@/client/client.gen";
import { configureApiClient } from "@/lib/api-client";
import { useModelRouting } from "./use-model-routing";

const ROUTING: ModelRoutingOut = {
  paid_models_enabled: true,
  roles: [
    {
      role: "screener",
      max_output_tokens: 800,
      paid: [
        {
          id: "openai/gpt-5-mini",
          free: false,
          in_catalog: true,
          context_length: 400_000,
          prompt_usd_per_mtok: "0.25",
          completion_usd_per_mtok: "2.00",
        },
      ],
      free: [],
    },
  ],
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

describe("useModelRouting", () => {
  it("loads the model chains of every agent role", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify(ROUTING), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useModelRouting(), { wrapper });
    await waitFor(() => expect(result.current.data).toEqual(ROUTING));
    expect(requestPath()).toBe("/api/v1/admin/models");
  });
});

/** The path of the request the generated client sent first. */
function requestPath(): string {
  const request = fetchMock.mock.calls[0]?.[0];
  return request instanceof Request ? new URL(request.url).pathname : "";
}
