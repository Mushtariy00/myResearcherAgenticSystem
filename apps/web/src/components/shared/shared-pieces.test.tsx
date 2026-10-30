// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { MethodProposal, Provenance } from "@/client";
import { AnalysisCard } from "./analysis-card";
import { CopyButton } from "./copy-button";
import { DemoBadge, isDemoContent } from "./demo-badge";
import { DownloadLink } from "./download-link";
import { JsonView } from "./json-view";
import { Metric } from "./metric";
import { ProposalCard } from "./proposal-card";
import { ProvenanceList } from "./provenance-list";
import { StageDot, StageIcon } from "./stage-icon";
import { renderWithIntl } from "./test-utils";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("DemoBadge", () => {
  it("shows only for demo content", () => {
    expect(isDemoContent({ demo: true })).toBe(true);
    expect(isDemoContent({ degradedReason: "stage.demo" })).toBe(true);
    expect(isDemoContent({ degradedReason: "stage.placeholder" })).toBe(false);
    expect(isDemoContent({})).toBe(false);
    const { container } = renderWithIntl(<DemoBadge degradedReason="stage.placeholder" />);
    expect(container.innerHTML).toBe("");
  });

  it("explains the demo data with the degraded reason", async () => {
    renderWithIntl(<DemoBadge degradedReason="literature.demo_search" className="ml-2" />);
    const trigger = screen.getByRole("button", { name: "Demo" });
    expect(trigger.className).toContain("ml-2");
    fireEvent.click(trigger);
    await waitFor(() => expect(screen.getByText("Demo data")).toBeTruthy());
    expect(
      screen.getByText(
        /the search plan is real, but the papers, analyses and synthesis are demo data/,
      ),
    ).toBeTruthy();
  });
});

describe("StageIcon and StageDot", () => {
  it("carry the stage for the colour tokens, and are decorative without a label", () => {
    const { container } = renderWithIntl(
      <>
        <StageIcon stage="coding" />
        <StageDot stage="writing" label="Writing" />
        <StageDot stage="unknown-stage" />
      </>,
    );
    const icon = container.querySelector('[data-slot="stage-icon"]');
    expect(icon?.getAttribute("data-stage")).toBe("coding");
    expect(icon?.getAttribute("aria-hidden")).toBe("true");
    expect(screen.getByRole("img", { name: "Writing" }).getAttribute("data-stage")).toBe("writing");
    expect(
      container.querySelectorAll('[data-slot="stage-dot"]')[1]?.hasAttribute("data-stage"),
    ).toBe(false);
  });
});

describe("Metric", () => {
  it("formats the value and names the better direction", () => {
    renderWithIntl(<Metric label="AbsRel" value={0.15694} higherIsBetter={false} />);
    expect(screen.getByText("0.157")).toBeTruthy();
    expect(screen.getByText("lower is better")).toBeTruthy();
  });

  it("never shows a missing value as zero", () => {
    renderWithIntl(<Metric label="RMSE" value={null} higherIsBetter />);
    expect(screen.queryByText("0")).toBeNull();
    expect(screen.getByText("—")).toBeTruthy();
    expect(screen.getByText("not measured")).toBeTruthy();
  });
});

describe("CopyButton", () => {
  it("copies and announces it", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    renderWithIntl(<CopyButton value="sha256:abc" label="Copy the hash" />);
    fireEvent.click(screen.getByRole("button", { name: "Copy the hash" }));
    expect(writeText).toHaveBeenCalledWith("sha256:abc");
    await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Copied"));
  });

  it("says when copying failed", async () => {
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: vi.fn().mockRejectedValue(new Error("denied")) },
      configurable: true,
    });
    renderWithIntl(<CopyButton value="x" />);
    fireEvent.click(screen.getByRole("button", { name: "Copy" }));
    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toBe(
        "Could not copy. Select the text and copy it yourself.",
      ),
    );
  });
});

describe("DownloadLink", () => {
  it("links same-origin attachments with their size", () => {
    renderWithIntl(
      <DownloadLink href="/api/v1/artifacts/a1" filename="code.zip" sizeBytes={1536} />,
    );
    const link = screen.getByRole("link", { name: "Download code.zip" });
    expect(link.getAttribute("href")).toBe("/api/v1/artifacts/a1");
    expect(link.getAttribute("download")).toBe("code.zip");
    expect(link.textContent).toContain("1.5");
  });

  it("refuses other origins", () => {
    const { container } = renderWithIntl(<DownloadLink href="https://evil.example/file" />);
    expect(container.querySelector("a")).toBeNull();
  });
});

const provenance: Provenance = {
  image_digest: "sha256:b415e5fee28feb439c1b68314e9949b590261650ec1a5b70c60d8e44abdb8d7c",
  code_sha256: "d01cd659593663d5cfe1c4893ca4c508d31984301bc13ec64ea5182295e2e8db",
  config_sha256: "374d56c0f1101b957b8c347cacde0bdbbe5cede1e09928107994ccd1c6805772",
  dataset: "nyu2",
  dataset_version: "2025.03",
  seed: 7,
  gpu_name: null,
  gpu_seconds: 1136.5,
  started_at: "2026-10-30T02:40:32Z",
  finished_at: null,
};

describe("ProvenanceList", () => {
  it("shows short hashes, copies them in full and states what is missing", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    renderWithIntl(<ProvenanceList provenance={provenance} />);
    expect(screen.getByText("sha256:b415e5fee28f…")).toBeTruthy();
    expect(screen.getByText("nyu2, version 2025.03")).toBeTruthy();
    expect(screen.getByText("Not recorded")).toBeTruthy();
    expect(screen.getByText("Not finished")).toBeTruthy();
    expect(screen.getByText(/18\.9/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Copy the full Code (SHA-256) hash" }));
    expect(writeText).toHaveBeenCalledWith(provenance.code_sha256);
  });
});

describe("ProposalCard", () => {
  const proposal: MethodProposal = {
    name: "Scale-aware distillation",
    rationale: "A frozen teacher gives dense targets.",
    expected_benefit: "Lower AbsRel.",
    risk: "Teacher bias.",
    evidence_paper_ids: ["arxiv:1", "arxiv:missing"],
  };

  it("shows the proposal, its recommendation and the supporting papers", () => {
    const onOpenPaper = vi.fn();
    renderWithIntl(
      <ProposalCard
        proposal={proposal}
        recommended
        papers={[{ paper_id: "arxiv:1", title: "GeoDiff", authors: [], year: 2019 }]}
        onOpenPaper={onOpenPaper}
      />,
    );
    expect(screen.getByRole("heading", { name: "Scale-aware distillation" })).toBeTruthy();
    expect(screen.getByText("Recommended")).toBeTruthy();
    expect(screen.getByText("Teacher bias.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /GeoDiff/ }));
    expect(onOpenPaper).toHaveBeenCalledWith("arxiv:1");
    expect(screen.getByRole("button", { name: "Paper arxiv:missing" })).toBeTruthy();
  });
});

describe("AnalysisCard", () => {
  const analysis = {
    contribution: "Introduces GeoDiff.",
    method: "EfficientNet-B3 encoder.",
    results: "RMSE 0.394.",
    limitations: "Needs intrinsics.",
    evidence: [
      { quote: "The encoder is initialized from ImageNet.", page: 5 },
      { quote: "We train for 25 epochs.", page: 6 },
    ],
  };

  it("opens a quote in the PDF", () => {
    const onOpenInPdf = vi.fn();
    renderWithIntl(
      <AnalysisCard
        analysis={analysis}
        paper={{
          paper_id: "p",
          title: "GeoDiff",
          authors: ["A", "B"],
          year: 2019,
          pdf_available: true,
        }}
        onOpenInPdf={onOpenInPdf}
      />,
    );
    expect(screen.getByText("Needs intrinsics.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Open quote 2 in the PDF, page 6" }));
    expect(onOpenInPdf).toHaveBeenCalledWith(analysis.evidence[1], 1);
  });

  it("disables the action without a PDF", () => {
    renderWithIntl(
      <AnalysisCard analysis={analysis} pdfAvailable={false} onOpenInPdf={() => {}} />,
    );
    const button = screen.getByRole("button", { name: "Open quote 1 in the PDF, page 5" });
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("No PDF is available for this paper.")).toBeTruthy();
  });
});

describe("JsonView", () => {
  it("shows markup as text", () => {
    const { container } = renderWithIntl(
      <JsonView
        value={{ summary: "<img src=x onerror=alert(1)>" }}
        label="Output"
        className="mt-2"
      />,
    );
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByRole("region", { name: "Output" }).textContent).toContain("<img src=x");
  });
});
