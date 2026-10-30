// @vitest-environment jsdom
import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MarkdownDraft } from "./markdown-draft";
import { slugify, splitCitations } from "./markdown-plugins";
import type { PaperSummary } from "./paper-summary";
import { renderWithIntl } from "./test-utils";

afterEach(cleanup);

const papers: PaperSummary[] = [
  {
    paper_id: "arxiv:1",
    title: "Depth from a single image",
    authors: ["Ada Lovelace"],
    year: 2019,
  },
  { paper_id: "arxiv:2", title: "Scale-aware distillation", authors: ["Alan Turing"], year: 2025 },
];
const citations = [
  { key: 1, paper_id: "arxiv:1" },
  { key: 2, paper_id: "arxiv:2" },
];

/** Every attribute value in the rendered tree, lower-cased. */
function attributeValues(root: Element): string[] {
  return [...root.querySelectorAll("*")].flatMap((element) =>
    [...element.attributes].map((attribute) =>
      `${attribute.name}=${attribute.value}`.toLowerCase(),
    ),
  );
}

describe("MarkdownDraft sanitisation", () => {
  const hostile = [
    "# Results",
    "",
    "Before <script>window.__pwned = true</script> after.",
    "",
    '<img src="x" onerror="window.__pwned = true">',
    "",
    '<a href="javascript:alert(1)">raw link</a> and <b onclick="alert(1)">bold</b>',
    "",
    "[markdown link](javascript:alert(1)) and [data link](data:text/html;base64,PHNjcmlwdD4=)",
    "",
    "![tracker](javascript:alert(1)) ![remote](https://evil.example/pixel.png)",
    "",
    '<iframe src="https://evil.example"></iframe><style>body{display:none}</style>',
  ].join("\n");

  it("renders scripts, event handlers and javascript: links inert", () => {
    const { container } = renderWithIntl(<MarkdownDraft markdown={hostile} toc={false} />);
    for (const tag of ["script", "img", "iframe", "style", "b"]) {
      expect(container.querySelector(tag), tag).toBeNull();
    }
    const values = attributeValues(container);
    expect(values.filter((value) => value.startsWith("on"))).toEqual([]);
    expect(values.filter((value) => value.includes("javascript:"))).toEqual([]);
    expect(values.filter((value) => value.includes("data:text/html"))).toEqual([]);
    expect(values.filter((value) => value.includes("evil.example"))).toEqual([]);
    expect((window as { __pwned?: boolean }).__pwned).toBeUndefined();
    // Link text survives as plain text; the dangerous targets do not.
    expect(screen.getByText("markdown link").closest("a")).toBeNull();
    expect(screen.getByText("data link").closest("a")).toBeNull();
    // Images from elsewhere are named but never loaded.
    expect(screen.getByText("Image not shown: remote")).toBeTruthy();
  });

  it("keeps ordinary links, tables and math", () => {
    const { container } = renderWithIntl(
      <MarkdownDraft
        markdown={
          "See [the site](https://example.org).\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\nInline $x^2$ math."
        }
        toc={false}
      />,
    );
    const link = screen.getByRole("link", { name: "the site" });
    expect(link.getAttribute("href")).toBe("https://example.org");
    expect(link.getAttribute("rel")).toContain("noopener");
    expect(container.querySelector("table td")?.textContent).toBe("1");
    expect(container.querySelector(".katex")).not.toBeNull();
  });
});

describe("MarkdownDraft citations", () => {
  it("turns [n] markers into buttons with the cited paper's title", () => {
    const onCite = vi.fn();
    const { container } = renderWithIntl(
      <MarkdownDraft
        markdown={
          "Depth [1] and distillation [1, 2]; unknown [7].\n\nNormalised to [0, 1] in `[3]`."
        }
        citations={citations}
        papers={papers}
        onCite={onCite}
        toc={false}
      />,
    );
    const first = screen.getAllByRole("button", { name: "Citation 1: Depth from a single image" });
    expect(first).toHaveLength(2);
    expect(
      screen.getByRole("button", { name: "Citation 2: Scale-aware distillation" }),
    ).toBeTruthy();
    const unknown = screen.getByRole("button", { name: "Citation 7 is not in the reference list" });
    expect(unknown.hasAttribute("data-unresolved")).toBe(true);

    // An interval and code are left alone.
    expect(container.textContent).toContain("[0, 1]");
    expect(container.querySelector("code")?.textContent).toBe("[3]");
    expect(container.querySelectorAll("[data-cite]")).toHaveLength(4);

    fireEvent.click(screen.getByRole("button", { name: "Citation 2: Scale-aware distillation" }));
    expect(onCite).toHaveBeenCalledWith(2, papers[1]);
    fireEvent.click(unknown);
    expect(onCite).toHaveBeenLastCalledWith(7, undefined);
  });

  it("names citations in Korean too", () => {
    renderWithIntl(
      <MarkdownDraft markdown="깊이 추정 [2]" citations={citations} papers={papers} toc={false} />,
      { locale: "ko" },
    );
    expect(screen.getByRole("button", { name: "인용 2: Scale-aware distillation" })).toBeTruthy();
  });

  it("splits citation groups but not intervals", () => {
    expect(splitCitations("no markers")).toBeNull();
    expect(splitCitations("between [0, 1]")).toBeNull();
    const parts = splitCitations("see [2–4] here") ?? [];
    expect(parts.filter((part) => part.type === "element")).toHaveLength(2);
    expect(parts.map((part) => ("value" in part ? part.value : "<button>")).join("")).toBe(
      "see [<button>–<button>] here",
    );
  });
});

describe("MarkdownDraft headings", () => {
  const draft = [
    "# Scale-aware distillation",
    "",
    "## 1. Introduction",
    "Text.[^note]",
    "",
    "## 2. Method",
    "### 2.1 Loss",
    "## 2. Method",
    "",
    "[^note]: A footnote.",
  ].join("\n");

  it("gives headings ids, anchor links and a table of contents", () => {
    const { container } = renderWithIntl(<MarkdownDraft markdown={draft} />);
    const nav = screen.getByRole("navigation", { name: "Contents" });
    const links = [...nav.querySelectorAll("a")].map((link) => link.getAttribute("href") ?? "");
    // The lone title is skipped; sections and subsections are listed; duplicates get a suffix.
    expect(links).toEqual([
      "#section-1-introduction",
      "#section-2-method",
      "#section-2-1-loss",
      "#section-2-method-1",
    ]);
    for (const href of links) {
      expect(container.querySelector(`[id="${href.slice(1)}"]`), href).not.toBeNull();
    }
    expect(
      screen.getByRole("link", { name: "Link to this section: 1. Introduction" }),
    ).toBeTruthy();
  });

  it("keeps footnote links pointing at their (sanitised) targets", () => {
    const { container } = renderWithIntl(<MarkdownDraft markdown={draft} toc={false} />);
    const fragments = [...container.querySelectorAll('a[href^="#user-content-"]')];
    expect(fragments.length).toBeGreaterThan(0);
    for (const link of fragments) {
      const target = link.getAttribute("href")?.slice(1) ?? "";
      expect(container.querySelector(`[id="${target}"]`), target).not.toBeNull();
    }
    // GFM's "Footnotes" label stays visually hidden and out of the contents.
    expect(container.querySelector("#user-content-footnote-label")?.className).toBe("sr-only");
  });

  it("slugifies any script", () => {
    expect(slugify("2. Related Work")).toBe("2-related-work");
    expect(slugify("관련 연구")).toBe("관련-연구");
  });
});
