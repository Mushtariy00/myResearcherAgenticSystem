// @vitest-environment jsdom
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { isValidElement, type ReactElement } from "react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import StudioPaperPage from "@/app/studio/(app)/papers/[...paperId]/page";
import type { PaperDetail } from "@/client";
import { client } from "@/client/client.gen";
import { paperFileUrl } from "@/hooks/use-paper";
import { configureApiClient } from "@/lib/api-client";
import { paperIdFromSegments, studioPaperPath } from "@/studio/lib/nav";
import { installDomFakes } from "@/studio/test/dom";
import { makeQueryClient, renderStudio, TEST_USER } from "@/studio/test/render";
import { StudioPaperDetail } from "./studio-paper-detail";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/studio/papers/doi%3A10.5555/xyz.123",
}));
const viewer = vi.hoisted(() => ({ props: [] as { url: string; activeQuote?: number }[] }));
vi.mock("@/components/shared/pdf-viewer", () => ({
  PdfViewer: (props: { url: string; activeQuote?: number }) => {
    viewer.props.push(props);
    return <div data-testid="pdf-viewer" data-url={props.url} data-active={props.activeQuote} />;
  },
}));

const PAPER_ID = "doi:10.5555/xyz.123";

const DETAIL: PaperDetail = {
  paper: {
    paper_id: PAPER_ID,
    title: "Depth estimation, revisited",
    authors: ["A. Author", "B. Author"],
    year: 2025,
    venue: "NeurIPS",
    doi: "10.5555/xyz.123",
    arxiv_id: "2501.00001",
    url: null,
    abstract: "We revisit depth estimation.",
    citation_count: 12,
    source: "semantic_scholar",
    pdf_available: true,
  },
  best_relevance: 0.88,
  runs: [
    {
      id: "r1",
      topic: "Monocular depth estimation",
      status: "completed",
      project_id: "p1",
      project_name: "Monocular depth",
      created_at: "2026-10-01T00:00:00Z",
      relevance: 0.88,
      decision: "include",
      decision_reason: "Directly on topic.",
      demo: false,
    },
  ],
  analyses: [
    {
      run_id: "r1",
      stage_output_id: "o1",
      attempt: 1,
      created_at: "2026-10-01T00:00:00Z",
      contribution: "A new loss.",
      method: "Scale-invariant training.",
      results: "Better RMSE.",
      limitations: "Indoor only.",
      evidence: [
        { quote: "We propose a loss", page: 2 },
        { quote: "RMSE drops by 10%", page: 6 },
      ],
      demo: true,
    },
  ],
  demo: true,
};

/**
 * The params Next hands a `[...paperId]` page for a request path: the matched part split on
 * "/", each segment decoded and then encoded again (next/dist/.../get-dynamic-param.js).
 */
function nextParams(path: string): string[] {
  return path
    .replace(/^\/studio\/papers\//, "")
    .split("/")
    .map((segment) => encodeURIComponent(decodeURIComponent(segment)));
}

const fetchMock = vi.fn<typeof fetch>();
let requested: string[] = [];

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeAll(() => {
  installDomFakes();
});

beforeEach(() => {
  requested = [];
  viewer.props = [];
  configureApiClient();
  client.setConfig({ baseUrl: "http://localhost:8080", fetch: fetchMock });
  fetchMock.mockImplementation(async (input) => {
    const url = new URL((input as Request).url);
    requested.push(url.pathname);
    return url.pathname === "/api/v1/papers/doi%3A10.5555%2Fxyz.123"
      ? json(200, DETAIL)
      : json(404, { detail: "paper.not_found" });
  });
});

afterEach(() => {
  cleanup();
  fetchMock.mockReset();
});

describe("Studio paper URLs", () => {
  it.each([
    "doi:10.5555/xyz.123",
    "arxiv:2401.01234v2",
    "s2:0f1e2d3c",
    "doi:10.1000/a b#c?d%e",
    "doi:10.1000/../escape",
    "openalex:W123//double",
  ])("round-trip %s through the catch-all route", (id) => {
    const path = studioPaperPath(id);
    expect(path.startsWith("/studio/papers/")).toBe(true);
    // Nothing a browser would resolve away or read as a query or fragment.
    expect(path.slice("/studio/papers/".length)).not.toMatch(/[?#]|(^|\/)\.\.?(\/|$)|\/\//);
    expect(paperIdFromSegments(nextParams(path))).toBe(id);
  });

  it("keep slashes as path separators and encode the rest like paperFileUrl", () => {
    expect(studioPaperPath(PAPER_ID)).toBe("/studio/papers/doi%3A10.5555/xyz.123");
    expect(paperFileUrl(PAPER_ID)).toBe(
      "http://localhost:8080/api/v1/papers/doi%3A10.5555%2Fxyz.123/file",
    );
  });

  it("read hand-typed and fully encoded addresses too", () => {
    expect(paperIdFromSegments(nextParams("/studio/papers/doi:10.5555/xyz.123"))).toBe(PAPER_ID);
    expect(paperIdFromSegments(nextParams("/studio/papers/doi%3A10.5555%2Fxyz.123"))).toBe(
      PAPER_ID,
    );
  });
});

describe("Studio paper page", () => {
  it("hands the decoded id to the paper view", async () => {
    const element = await StudioPaperPage({
      params: Promise.resolve({ paperId: nextParams(studioPaperPath(PAPER_ID)) }),
    });
    expect(isValidElement(element)).toBe(true);
    expect((element as ReactElement<{ paperId: string }>).props.paperId).toBe(PAPER_ID);
  });

  it("shows the paper, its PDF with the evidence, the analyses and the runs", async () => {
    renderStudio(<StudioPaperDetail paperId={PAPER_ID} />, {
      user: TEST_USER,
      queryClient: makeQueryClient(),
    });
    expect(
      await screen.findByRole("heading", { level: 1, name: "Depth estimation, revisited" }),
    ).toBeTruthy();
    expect(requested).toContain("/api/v1/papers/doi%3A10.5555%2Fxyz.123");

    const pdf = screen.getByTestId("pdf-viewer");
    expect(pdf.getAttribute("data-url")).toBe(paperFileUrl(PAPER_ID));
    expect(screen.getByRole("link", { name: /DOI/ }).getAttribute("href")).toBe(
      "https://doi.org/10.5555/xyz.123",
    );

    fireEvent.click(screen.getByRole("button", { name: "Open quote 2 in the PDF, page 6" }));
    expect(pdf.getAttribute("data-active")).toBe("1");

    const runs = screen.getByRole("region", { name: /Runs that found it/ });
    expect(
      within(runs).getByRole("link", { name: "Monocular depth estimation" }).getAttribute("href"),
    ).toBe("/studio/runs/r1");
    expect(within(runs).getByText("Directly on topic.")).toBeTruthy();
    expect(screen.getAllByText("Demo").length).toBeGreaterThan(0);
  });

  it("says when the paper is not in the library", async () => {
    renderStudio(<StudioPaperDetail paperId="doi:10.0000/missing" />, {
      user: TEST_USER,
      queryClient: makeQueryClient(),
    });
    expect(await screen.findByRole("heading", { level: 1, name: "Paper not found" })).toBeTruthy();
    expect(requested).toContain("/api/v1/papers/doi%3A10.0000%2Fmissing");
    const back = screen.getAllByRole("link", { name: "Paper library" });
    expect(back.every((link) => link.getAttribute("href") === "/studio/papers")).toBe(true);
  });
});
