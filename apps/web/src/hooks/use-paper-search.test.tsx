// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { LibraryPaperOut, PaperPage } from "@/client";
import { client } from "@/client/client.gen";
import { configureApiClient } from "@/lib/api-client";
import { type PaperSearchParams, usePaperSearch } from "./use-paper-search";

const PROJECT = "33333333-3333-4333-8333-333333333333";

function paper(id: string): LibraryPaperOut {
  return {
    paper: {
      paper_id: id,
      title: `Paper ${id}`,
      authors: ["A. Author"],
      year: 2024,
      venue: null,
      doi: null,
      arxiv_id: null,
      url: null,
      abstract: "Abstract",
      citation_count: null,
      source: "arxiv",
      pdf_available: true,
    },
    run_count: 1,
    project_count: 1,
    best_relevance: 0.9,
    decisions: ["include"],
    last_seen_at: "2026-10-30T00:00:00Z",
    demo: true,
  };
}

const fetchMock = vi.fn<typeof fetch>();
let requests: URLSearchParams[] = [];
let total = 45;

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  requests = [];
  total = 45;
  configureApiClient();
  client.setConfig({ baseUrl: "http://localhost:8080", fetch: fetchMock });
  fetchMock.mockImplementation(async (input) => {
    const url = new URL((input as Request).url);
    requests.push(url.searchParams);
    const offset = Number(url.searchParams.get("offset"));
    const page: PaperPage = { items: [paper(`p${offset}`)], total, demo: true };
    return json(200, page);
  });
});

afterEach(() => {
  cleanup();
  fetchMock.mockReset();
});

function setup(initialProps: PaperSearchParams) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return renderHook((params: PaperSearchParams) => usePaperSearch({ debounceMs: 30, ...params }), {
    wrapper,
    initialProps,
  });
}

const last = () => Object.fromEntries(requests.at(-1)?.entries() ?? []);

describe("usePaperSearch", () => {
  it("sends the filters the API knows and leaves out empty ones", async () => {
    const { result } = setup({
      projectId: PROJECT,
      yearFrom: 2020,
      yearTo: 2024,
      decision: "include",
      source: "openalex",
      pageSize: 10,
    });
    await waitFor(() => expect(result.current.items).toHaveLength(1));
    expect(last()).toEqual({
      limit: "10",
      offset: "0",
      project_id: PROJECT,
      year_from: "2020",
      year_to: "2024",
      decision: "include",
      source: "openalex",
    });
    expect(result.current).toMatchObject({ total: 45, pageCount: 5, demo: true });
  });

  it("searches once the text stops changing", async () => {
    const { result, rerender } = setup({ q: "" });
    await waitFor(() => expect(requests).toHaveLength(1));
    rerender({ q: "dep" });
    rerender({ q: " depth  " });
    expect(result.current.isSearching).toBe(true);
    await waitFor(() => expect(requests).toHaveLength(2));
    expect(last()).toMatchObject({ q: "depth" });
    await waitFor(() => expect(result.current.isSearching).toBe(false));
    expect(result.current.searchedQ).toBe("depth");
  });

  it("keeps the search text within the API's 200 characters", async () => {
    setup({ q: "x".repeat(250) });
    await waitFor(() => expect(requests).toHaveLength(1));
    expect(last().q).toHaveLength(200);
  });

  it("pages through the results and starts over when a filter changes", async () => {
    const { result, rerender } = setup({ pageSize: 20 });
    await waitFor(() => expect(result.current.pageCount).toBe(3));
    expect(result.current.hasPreviousPage).toBe(false);

    act(() => result.current.nextPage());
    await waitFor(() => expect(last()).toMatchObject({ offset: "20" }));
    expect(result.current.pageIndex).toBe(1);
    await waitFor(() => expect(result.current.items[0]?.paper.paper_id).toBe("p20"));

    act(() => result.current.setPageIndex(2));
    await waitFor(() => expect(last()).toMatchObject({ offset: "40" }));
    expect(result.current.hasNextPage).toBe(false);

    rerender({ pageSize: 20, decision: "maybe" });
    expect(result.current.pageIndex).toBe(0);
    await waitFor(() => expect(last()).toMatchObject({ offset: "0", decision: "maybe" }));
  });

  it("keeps the previous results on screen while the next page loads", async () => {
    const { result } = setup({});
    await waitFor(() => expect(result.current.items).toHaveLength(1));
    act(() => result.current.nextPage());
    expect(result.current.items[0]?.paper.paper_id).toBe("p0");
    expect(result.current.query.isPlaceholderData).toBe(true);
    await waitFor(() => expect(result.current.items[0]?.paper.paper_id).toBe("p20"));
  });

  it("asks nothing while the year range is invalid", async () => {
    const { result, rerender } = setup({ yearFrom: 2025, yearTo: 2020 });
    expect(result.current.yearRangeInvalid).toBe(true);
    rerender({ yearFrom: 1800 });
    expect(result.current.yearRangeInvalid).toBe(true);
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(requests).toHaveLength(0);

    rerender({ yearFrom: 2020, yearTo: 2025 });
    expect(result.current.yearRangeInvalid).toBe(false);
    await waitFor(() => expect(requests).toHaveLength(1));
  });

  it("reads an empty library as one empty page", async () => {
    total = 0;
    fetchMock.mockImplementation(async () => json(200, { items: [], total: 0, demo: false }));
    const { result } = setup({});
    await waitFor(() => expect(result.current.query.isSuccess).toBe(true));
    expect(result.current).toMatchObject({
      items: [],
      total: 0,
      pageCount: 1,
      hasNextPage: false,
      demo: false,
    });
  });
});
