// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { PaperDetail } from "@/client";
import { client } from "@/client/client.gen";
import { configureApiClient } from "@/lib/api-client";
import { paperFileUrl, usePaper } from "./use-paper";

const PAPER_ID = "doi:10.5555/depth.2024";

const DETAIL: PaperDetail = {
  paper: {
    paper_id: PAPER_ID,
    title: "Depth from one image",
    authors: ["A. Author"],
    year: 2024,
    venue: "CVPR",
    doi: "10.5555/depth.2024",
    arxiv_id: null,
    url: null,
    abstract: "Abstract",
    citation_count: 3,
    source: "crossref",
    pdf_available: true,
  },
  best_relevance: 0.92,
  runs: [],
  analyses: [],
  demo: true,
};

const fetchMock = vi.fn<typeof fetch>();

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  configureApiClient();
  client.setConfig({ baseUrl: "http://localhost:8080", fetch: fetchMock });
});

afterEach(() => {
  cleanup();
  fetchMock.mockReset();
});

function setup(paperId: string | null) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return renderHook(() => usePaper(paperId), { wrapper });
}

describe("usePaper", () => {
  it("loads the paper, with the slashes of its id encoded", async () => {
    fetchMock.mockResolvedValue(json(200, DETAIL));
    const { result } = setup(PAPER_ID);
    await waitFor(() => expect(result.current.data).toEqual(DETAIL));
    const request = fetchMock.mock.calls[0]?.[0] as Request;
    expect(new URL(request.url).pathname).toBe("/api/v1/papers/doi%3A10.5555%2Fdepth.2024");
  });

  it("reports a paper the caller cannot open with the API's code", async () => {
    fetchMock.mockResolvedValue(json(404, { detail: "paper.not_found" }));
    const { result } = setup(PAPER_ID);
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toMatchObject({ code: "paper.not_found", status: 404 });
  });

  it("waits while there is no id", () => {
    const { result } = setup(null);
    expect(result.current.fetchStatus).toBe("idle");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("paperFileUrl", () => {
  it("points at the PDF route of the API", () => {
    expect(paperFileUrl(PAPER_ID)).toBe(
      "http://localhost:8080/api/v1/papers/doi%3A10.5555%2Fdepth.2024/file",
    );
  });
});
