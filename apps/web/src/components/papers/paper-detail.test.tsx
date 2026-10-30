// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import PaperPage from "@/app/(app)/papers/[...paperId]/page";
import type { LibraryPaperOut, PaperDetail, PaperPage as PaperList } from "@/client";
import { installBrowserStubs, renderPage } from "@/components/projects/test-utils";
import type { PdfViewerProps } from "@/components/shared/pdf-viewer-types";
import { json, mockApi, requestsOf } from "@/hooks/run-hooks.fixtures";
import { paperFileUrl } from "@/hooks/use-paper";
import { PaperBrowser } from "./paper-browser";
import { PaperDetailView } from "./paper-detail-view";

// PDF.js cannot run in jsdom: a stand-in shows what the viewer was asked to show.
vi.mock("@/components/shared/pdf-viewer", () => ({
  PdfViewer: ({ url, quotes, activeQuote }: PdfViewerProps) => (
    <div
      data-testid="pdf-viewer"
      data-url={url}
      data-quotes={quotes?.map((quote) => quote.quote).join("|")}
      data-active={activeQuote}
    />
  ),
}));

const PAPER_ID = "doi:10.5555/depth.2024";
const API_PATH = "/api/v1/papers/doi%3A10.5555%2Fdepth.2024";
const RUN_A = "11111111-1111-4111-8111-111111111111";
const RUN_B = "22222222-2222-4222-8222-222222222222";
const PROJECT = "33333333-3333-4333-8333-333333333333";

const DETAIL: PaperDetail = {
  paper: {
    paper_id: PAPER_ID,
    title: "Depth from one image with diffusion priors",
    authors: ["Camila Hernández", "Kofi Diallo"],
    year: 2024,
    venue: "CVPR",
    doi: "10.5555/depth.2024",
    arxiv_id: null,
    url: "javascript:alert(1)",
    abstract: "We estimate depth from a single image.",
    citation_count: 12,
    source: "crossref",
    pdf_available: true,
  },
  best_relevance: 0.92,
  runs: [
    {
      id: RUN_A,
      topic: "Monocular depth estimation",
      status: "completed",
      project_id: PROJECT,
      project_name: "Depth",
      created_at: "2026-10-20T00:00:00Z",
      relevance: 0.92,
      decision: "include",
      decision_reason: "Evaluates on NYU Depth v2.",
      demo: true,
    },
    {
      id: RUN_B,
      topic: "Depth for drones",
      status: "running",
      project_id: PROJECT,
      project_name: "Depth",
      created_at: "2026-10-25T00:00:00Z",
      relevance: 0.61,
      decision: "maybe",
      decision_reason: "",
      demo: true,
    },
  ],
  analyses: [
    {
      run_id: RUN_A,
      stage_output_id: "44444444-4444-4444-8444-444444444444",
      attempt: 1,
      created_at: "2026-10-20T02:00:00Z",
      contribution: "A diffusion prior for depth.",
      method: "Fine-tunes a latent diffusion model.",
      results: "Lower RMSE on NYU Depth v2.",
      limitations: "Slow at inference.",
      evidence: [
        { quote: "We fine-tune a latent diffusion model", page: 2 },
        { quote: "RMSE drops by 12%", page: 5 },
      ],
      demo: true,
    },
    {
      run_id: RUN_B,
      stage_output_id: "55555555-5555-4555-8555-555555555555",
      attempt: 2,
      created_at: "2026-10-25T02:00:00Z",
      contribution: "Same paper, read again.",
      method: "Diffusion prior.",
      results: "Good indoors.",
      limitations: "Not tested outdoors.",
      evidence: [{ quote: "indoor scenes only", page: 7 }],
      demo: true,
    },
  ],
  demo: true,
};

const LISTED: LibraryPaperOut = {
  paper: DETAIL.paper,
  run_count: 2,
  project_count: 1,
  best_relevance: 0.92,
  decisions: ["include", "maybe"],
  last_seen_at: "2026-10-25T02:00:00Z",
  demo: true,
};

let fetchMock: ReturnType<typeof mockApi>;

beforeAll(() => {
  installBrowserStubs();
});

beforeEach(() => {
  fetchMock = mockApi((_request, path) => {
    if (path === API_PATH) {
      return json(200, DETAIL);
    }
    if (path === "/api/v1/papers") {
      const page: PaperList = { items: [LISTED], total: 1, demo: true };
      return json(200, page);
    }
    return json(404, { detail: "paper.not_found" });
  });
});

afterEach(() => {
  cleanup();
});

describe("/papers/[...paperId]", () => {
  it("hands the page the whole id, slashes and colons included", async () => {
    // As Next.js passes the segments: one per "/" left in the URL, each still encoded.
    for (const paperId of [["doi%3A10.5555%2Fdepth.2024"], ["doi%3A10.5555", "depth.2024"]]) {
      const element = await PaperPage({ params: Promise.resolve({ paperId }) });
      expect(element.props.paperId).toBe(PAPER_ID);
      expect(element.key).toBe(PAPER_ID);
    }
  });

  it("answers not found for an id that is not valid percent-encoding", async () => {
    await expect(
      PaperPage({ params: Promise.resolve({ paperId: ["%E0%A4%A"] }) }),
    ).rejects.toThrow();
  });
});

describe("PaperDetailView", () => {
  it("loads the paper by its encoded id and shows what every run found", async () => {
    renderPage(<PaperDetailView paperId={PAPER_ID} />);
    expect(await screen.findByRole("heading", { level: 1, name: DETAIL.paper.title })).toBeTruthy();
    expect(requestsOf(fetchMock)).toContain(`GET ${API_PATH}`);

    expect(screen.getByText("We estimate depth from a single image.")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Analyses (2)" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "From “Monocular depth estimation”" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Runs that found it (2)" })).toBeTruthy();
    expect(screen.getByText("Evaluates on NYU Depth v2.")).toBeTruthy();
    // A link that is not http(s) is never rendered.
    expect(document.querySelector('a[href^="javascript:"]')).toBeNull();
    expect(screen.getByRole("link", { name: /10\.5555\/depth\.2024/ }).getAttribute("href")).toBe(
      "https://doi.org/10.5555/depth.2024",
    );
  });

  it("opens the PDF at the quote an analysis cites", async () => {
    renderPage(<PaperDetailView paperId={PAPER_ID} />);
    const viewer = await screen.findByTestId("pdf-viewer");
    expect(viewer.getAttribute("data-url")).toBe(paperFileUrl(PAPER_ID));
    expect(viewer.getAttribute("data-quotes")).toBe(
      "We fine-tune a latent diffusion model|RMSE drops by 12%|indoor scenes only",
    );
    expect(viewer.getAttribute("data-active")).toBe("0");

    // The second analysis's only quote is the third quote overall.
    fireEvent.click(screen.getByRole("button", { name: "Open quote 1 in the PDF, page 7" }));
    expect(screen.getByTestId("pdf-viewer").getAttribute("data-active")).toBe("2");
  });
});

describe("PaperBrowser", () => {
  it("opens a paper in the sheet, which links to its page", async () => {
    renderPage(<PaperBrowser projectId={PROJECT} />);
    fireEvent.click(await screen.findByRole("button", { name: DETAIL.paper.title }));

    const sheet = await screen.findByRole("dialog");
    const link = await within(sheet).findByRole("link", { name: "Open the paper's page" });
    expect(link.getAttribute("href")).toBe("/papers/doi%3A10.5555%2Fdepth.2024");
    expect(within(sheet).getByTestId("pdf-viewer")).toBeTruthy();
    expect(requestsOf(fetchMock)).toContain(
      `GET /api/v1/papers?limit=20&offset=0&project_id=${PROJECT}`,
    );
    await waitFor(() => expect(requestsOf(fetchMock)).toContain(`GET ${API_PATH}`));
  });
});
