import { describe, expect, it } from "vitest";
import {
  findQuotes,
  highlightItemHtml,
  itemText,
  normalizeForMatch,
  segmentsByItem,
} from "./pdf-highlight";

// A page as PDF.js splits it: one item per line, a hyphenated line break, a ligature, and a
// marked-content item (no text) in between.
const items = [
  "Monocular depth estimation is difficult because of unseen",
  "camera intrinsics. We introduce GeoDiﬀ, an uncer-",
  "",
  "tainty-aware model built on state space models.",
  "The EfficientNet-B3 encoder is initialized from ImageNet.",
];

describe("findQuotes", () => {
  it("finds a quote across items, hyphenation and ligatures", () => {
    const [match] = findQuotes(items, ["We introduce GeoDiff, an uncertainty-aware model"]);
    expect(match?.found).toBe(true);
    // "We introduce GeoDiﬀ, an uncer" (the line-break hyphen is left out) and "tainty-aware model".
    expect(match?.segments).toEqual([
      { item: 1, start: 19, end: 48, quote: 0 },
      { item: 3, start: 0, end: 18, quote: 0 },
    ]);
  });

  it("ignores case, spacing and punctuation differences", () => {
    const [match] = findQuotes(items, ["the efficientnet b3 ENCODER is initialized"]);
    expect(match?.found).toBe(true);
    expect(match?.segments).toEqual([{ item: 4, start: 0, end: 42, quote: 0 }]);
  });

  it("reports quotes that are not on the page, and ignores tiny ones", () => {
    expect(findQuotes(items, ["A sentence from another page."])[0]?.found).toBe(false);
    expect(findQuotes(items, ["is"])[0]?.found).toBe(false);
  });

  it("matches Korean text", () => {
    const [match] = findQuotes(["단안 깊이 추정은", "어렵다."], ["깊이 추정은 어렵다"]);
    expect(match?.segments.map((segment) => segment.item)).toEqual([0, 1]);
    expect(normalizeForMatch("ﬁne-tuned")).toBe("finetuned");
  });

  it("reads text from PDF.js items", () => {
    expect(itemText({ str: "abc", hasEOL: false })).toBe("abc");
    expect(itemText({ type: "beginMarkedContent" })).toBe("");
  });
});

describe("highlightItemHtml", () => {
  it("wraps quote ranges in marks and escapes everything", () => {
    const matches = findQuotes(["<b>Risky</b> & the quoted words here"], ["the quoted words"]);
    const byItem = segmentsByItem(matches);
    expect(highlightItemHtml("<b>Risky</b> & the quoted words here", byItem.get(0), 0)).toBe(
      '&lt;b&gt;Risky&lt;/b&gt; &amp; <mark class="pdf-quote" data-quote="0" data-active>the quoted words</mark> here',
    );
  });

  it("returns escaped text when the item has no quote", () => {
    expect(highlightItemHtml('<img src=x onerror="alert(1)">', undefined)).toBe(
      "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;",
    );
  });

  it("marks only the active quote as active", () => {
    const html = highlightItemHtml("alpha beta", [{ item: 0, start: 0, end: 5, quote: 1 }], 0);
    expect(html).toBe('<mark class="pdf-quote" data-quote="1">alpha</mark> beta');
  });
});
