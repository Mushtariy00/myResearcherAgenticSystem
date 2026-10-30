// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import type { Locale } from "@/i18n/config";
import { useStageLogLine } from "./stage-log";
import { renderWithIntl } from "./test-utils";

function Line({ code, params }: { code: string; params: Record<string, unknown> }) {
  const line = useStageLogLine()(code, params);
  return <p>{line ?? "(fallback)"}</p>;
}

function lineOf(code: string, params: Record<string, unknown>, locale: Locale = "en"): string {
  const { container, unmount } = renderWithIntl(<Line code={code} params={params} />, { locale });
  const text = container.textContent ?? "";
  unmount();
  return text;
}

describe("useStageLogLine", () => {
  it("words each step of the real literature stage", () => {
    expect(
      lineOf("literature.searched", {
        queries: 6,
        sources: ["openalex", "arxiv"],
        found: 215,
        incomplete: 5,
      }),
    ).toBe(
      "Searched OpenAlex and arXiv with 6 queries: 215 papers found, 5 of them left out for lack " +
        "of authors, a year or an abstract",
    );
    expect(lineOf("literature.searched", { queries: 1, sources: ["arxiv"], found: 1 })).toBe(
      "Searched arXiv with 1 query: 1 paper found",
    );
    expect(
      lineOf("literature.source_failed", {
        source: "semantic_scholar",
        error: "source.rate_limited",
      }),
    ).toBe(
      "Semantic Scholar could not be searched (it is limiting requests); continuing without it",
    );
    expect(lineOf("literature.screened", { candidates: 15, included: 4 })).toBe(
      "Screened 15 candidates and included 4 papers for full reading",
    );
    expect(lineOf("literature.fetched", { pdfs: 3, abstract_only: 1 })).toBe(
      "Fetched 3 open-access PDFs; 1 paper has only an abstract",
    );
    expect(lineOf("literature.fetched", { pdfs: 4, abstract_only: 0 })).toBe(
      "Fetched 4 open-access PDFs: every included paper has its full text",
    );
    expect(lineOf("literature.parsed", { papers: 4 })).toBe("Extracted the full text of 4 papers");
    expect(lineOf("literature.analyzed", { papers: 1 })).toBe("Analysed 1 paper");
    expect(lineOf("literature.synthesized", { findings: 4 })).toBe(
      "Wrote the synthesis from 4 key findings",
    );
  });

  it("words the method and writing stages", () => {
    expect(lineOf("method.proposed", { proposals: 3, gaps: 2 })).toBe(
      "Proposed 3 methods for 2 research gaps",
    );
    expect(lineOf("writing.outlined", { sections: 6 })).toBe("Outlined 6 sections");
    expect(lineOf("writing.drafted", { section: "Related work", index: 2, sections: 6 })).toBe(
      "Drafted Related work (2/6)",
    );
    expect(lineOf("writing.cited", { citations: 1, removed: 0 })).toBe("Cited 1 paper");
    expect(lineOf("writing.cited", { citations: 9, removed: 2 })).toBe(
      "Cited 9 papers; removed 2 citations of papers that are not in the review",
    );
  });

  it("reads the same lines in Korean", () => {
    expect(lineOf("literature.screened", { candidates: 15, included: 4 }, "ko")).toBe(
      "후보 15편을 선별해 4편을 정독 대상으로 포함했습니다",
    );
    expect(
      lineOf(
        "literature.source_failed",
        { source: "openalex", error: "source.quota_exhausted" },
        "ko",
      ),
    ).toBe("OpenAlex에서 검색하지 못해(일일 한도 소진) 이 출처 없이 계속합니다");
    expect(lineOf("method.proposed", { proposals: 3, gaps: 2 }, "ko")).toBe(
      "연구 공백 2개에 대해 방법 3개를 제안했습니다",
    );
  });

  it("leaves other codes and malformed params to the worker's English message", () => {
    expect(lineOf("demo.search", { queries: 3, sources: ["arxiv"] })).toBe("(fallback)");
    expect(lineOf("literature.screened", { candidates: "15", included: 4 })).toBe("(fallback)");
    expect(lineOf("literature.source_failed", { source: "arxiv", error: "boom" })).toBe(
      "(fallback)",
    );
    expect(lineOf("literature.parsed", { papers: -1 })).toBe("(fallback)");
    expect(lineOf("writing.drafted", { section: "", index: 1, sections: 2 })).toBe("(fallback)");
  });
});
