// @vitest-environment jsdom
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PaperRef } from "@/client";
import { PapersTable } from "./papers-table";
import { renderWithIntl } from "./test-utils";

afterEach(cleanup);

function paper(overrides: Partial<PaperRef> & Pick<PaperRef, "paper_id" | "title">): PaperRef {
  return {
    authors: ["Camila Hernández", "Kofi Diallo"],
    year: 2020,
    venue: "CVPR",
    abstract: "",
    citation_count: 10,
    source: "arxiv",
    pdf_available: true,
    relevance: 0.5,
    decision: "include",
    decision_reason: "On topic",
    ...overrides,
  };
}

const papers: PaperRef[] = [
  paper({ paper_id: "a", title: "Alpha depth", relevance: 0.61, year: 2019, citation_count: 120 }),
  paper({
    paper_id: "b",
    title: "Beta distillation",
    relevance: 0.93,
    year: 2025,
    citation_count: null,
    decision: "maybe",
    pdf_available: false,
  }),
  paper({
    paper_id: "c",
    title: "Gamma benchmark",
    relevance: 0.42,
    year: 2022,
    citation_count: 7,
    decision: "exclude",
    source: "openalex",
    authors: ["A One", "B Two", "C Three", "D Four"],
  }),
];

function rowText(title: string): string {
  return screen.getByText(title).closest("tr")?.textContent ?? "";
}

/** Paper titles in row order. */
function order(): string[] {
  const body = screen.getAllByRole("rowgroup")[1];
  return within(body as HTMLElement)
    .getAllByRole("row")
    .map(
      (row) =>
        within(row).getAllByRole("cell")[0]?.querySelector("button, span")?.textContent ?? "",
    );
}

describe("PapersTable", () => {
  it("lists papers most relevant first, with authors, venue and year", () => {
    renderWithIntl(<PapersTable papers={papers} onSelect={() => {}} />);
    expect(order()).toEqual(["Beta distillation", "Alpha depth", "Gamma benchmark"]);
    expect(rowText("Gamma benchmark")).toContain("A One, B Two, C Three et al. · CVPR · 2022");
    const relevance = screen.getByRole("columnheader", { name: /Relevance/ });
    expect(relevance.getAttribute("aria-sort")).toBe("descending");
    // The unknown citation count is a dash with a spoken "Unknown", never 0.
    expect(screen.getAllByText("Unknown").length).toBeGreaterThan(0);
  });

  it("sorts by a column header and reverses on the second click", () => {
    renderWithIntl(<PapersTable papers={papers} />);
    fireEvent.click(screen.getByRole("button", { name: "Year" }));
    expect(order()).toEqual(["Beta distillation", "Gamma benchmark", "Alpha depth"]);
    expect(screen.getByRole("columnheader", { name: /Year/ }).getAttribute("aria-sort")).toBe(
      "descending",
    );
    expect(screen.getByRole("columnheader", { name: /Relevance/ }).hasAttribute("aria-sort")).toBe(
      false,
    );
    fireEvent.click(screen.getByRole("button", { name: "Year" }));
    expect(order()).toEqual(["Alpha depth", "Gamma benchmark", "Beta distillation"]);

    fireEvent.click(screen.getByRole("button", { name: "Paper" }));
    expect(order()).toEqual(["Alpha depth", "Beta distillation", "Gamma benchmark"]);

    // Unknown citation counts sort last in both directions.
    fireEvent.click(screen.getByRole("button", { name: "Citations" }));
    expect(order()).toEqual(["Alpha depth", "Gamma benchmark", "Beta distillation"]);
    fireEvent.click(screen.getByRole("button", { name: "Citations" }));
    expect(order()).toEqual(["Gamma benchmark", "Alpha depth", "Beta distillation"]);

    fireEvent.click(screen.getByRole("button", { name: "Decision" }));
    expect(order()).toEqual(["Alpha depth", "Beta distillation", "Gamma benchmark"]);
  });

  it("selects a paper by clicking its row", () => {
    const onSelect = vi.fn();
    renderWithIntl(<PapersTable papers={papers} onSelect={onSelect} />);
    const row = screen.getByText("Gamma benchmark").closest("tr");
    fireEvent.click(within(row as HTMLElement).getByText("OpenAlex"));
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith(papers[2]);
  });

  it("is one tab stop with arrow-key navigation, and marks the selected paper", () => {
    const onSelect = vi.fn();
    renderWithIntl(<PapersTable papers={papers} onSelect={onSelect} selectedId="a" />);
    const titles = ["Beta distillation", "Alpha depth", "Gamma benchmark"].map((name) =>
      screen.getByRole("button", { name }),
    );
    // The selected row holds the tab stop.
    expect(titles.map((button) => button.tabIndex)).toEqual([-1, 0, -1]);
    expect(titles[1]?.getAttribute("aria-current")).toBe("true");
    expect(screen.getByText("Alpha depth").closest("tr")?.getAttribute("data-state")).toBe(
      "selected",
    );

    titles[1]?.focus();
    fireEvent.keyDown(titles[1] as HTMLElement, { key: "ArrowDown" });
    expect(document.activeElement).toBe(titles[2]);
    fireEvent.keyDown(titles[2] as HTMLElement, { key: "ArrowDown" });
    expect(document.activeElement).toBe(titles[2]); // stays on the last row
    fireEvent.keyDown(titles[2] as HTMLElement, { key: "Home" });
    expect(document.activeElement).toBe(titles[0]);
    expect(titles.map((button) => button.tabIndex)).toEqual([0, -1, -1]);
    fireEvent.keyDown(titles[0] as HTMLElement, { key: "End" });
    expect(document.activeElement).toBe(titles[2]);
    fireEvent.keyDown(titles[2] as HTMLElement, { key: "ArrowUp" });
    expect(document.activeElement).toBe(titles[1]);

    // Enter and Space activate the focused title button (native button behaviour).
    fireEvent.click(document.activeElement as HTMLElement);
    expect(onSelect).toHaveBeenCalledWith(papers[0]);
  });

  it("shows loading placeholders, then an empty state", () => {
    const { container, rerender } = renderWithIntl(<PapersTable papers={[]} loading />);
    expect(screen.getByRole("table").getAttribute("aria-busy")).toBe("true");
    expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0);
    expect(screen.getByRole("status").textContent).toBe("Loading papers…");

    rerender(<PapersTable papers={[]} />);
    expect(screen.getByText("No papers yet.")).toBeTruthy();
    rerender(<PapersTable papers={[]} emptyMessage="Nothing matched." />);
    expect(screen.getByText("Nothing matched.")).toBeTruthy();
  });

  it("speaks Korean", () => {
    renderWithIntl(<PapersTable papers={papers} />, { locale: "ko" });
    expect(screen.getByRole("button", { name: "관련도" })).toBeTruthy();
    expect(screen.getAllByText("포함").length).toBeGreaterThan(0);
    expect(rowText("Gamma benchmark")).toContain("A One, B Two, C Three 외");
  });
});
