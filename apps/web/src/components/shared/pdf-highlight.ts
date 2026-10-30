/**
 * Finding evidence quotes in a PDF page's text layer. PDF.js splits a page into text items
 * (runs of text, often one per line), so a quote usually spans several items, with line-break
 * hyphens, ligatures (ﬁ) and spacing that differ from the quote. Both sides are reduced to
 * letters and digits (NFKD, accents and punctuation dropped, lower case) before matching, and
 * the match is mapped back to character ranges in the original items.
 */

/** A PDF.js text item: TextItem has `str`; marked-content items have none (but take an index). */
export function itemText(item: object): string {
  return "str" in item && typeof item.str === "string" ? item.str : "";
}

export type QuoteSegment = {
  /** Index of the text item (as PDF.js numbers them, marked content included). */
  item: number;
  /** UTF-16 offsets in the item's `str`. */
  start: number;
  end: number;
  /** Index of the quote this range belongs to. */
  quote: number;
};

export type QuoteMatch = { quote: number; found: boolean; segments: QuoteSegment[] };

/** Quotes shorter than this (after normalising) are too ambiguous to highlight. */
const MIN_QUOTE_LENGTH = 4;

const KEEP = /[\p{L}\p{N}]/u;

function normalizeCodePoint(character: string): string {
  let out = "";
  for (const part of character.normalize("NFKD").toLowerCase()) {
    if (KEEP.test(part)) {
      out += part;
    }
  }
  return out;
}

export function normalizeForMatch(text: string): string {
  let out = "";
  for (const character of text) {
    out += normalizeCodePoint(character);
  }
  return out;
}

type CharRef = { item: number; start: number; end: number };

function indexPage(items: readonly string[]): { text: string; refs: CharRef[] } {
  let text = "";
  const refs: CharRef[] = [];
  items.forEach((item, itemIndex) => {
    let offset = 0;
    for (const character of item) {
      const normalized = normalizeCodePoint(character);
      for (const _ of normalized) {
        refs.push({ item: itemIndex, start: offset, end: offset + character.length });
      }
      text += normalized;
      offset += character.length;
    }
  });
  return { text, refs };
}

/**
 * Where each quote occurs on the page (first occurrence), as ranges in the text items.
 * `items` are the items' texts in PDF.js order (use `itemText`; "" for marked content).
 */
export function findQuotes(items: readonly string[], quotes: readonly string[]): QuoteMatch[] {
  const page = indexPage(items);
  return quotes.map((quote, quoteIndex) => {
    const needle = normalizeForMatch(quote);
    const at = needle.length >= MIN_QUOTE_LENGTH ? page.text.indexOf(needle) : -1;
    if (at === -1) {
      return { quote: quoteIndex, found: false, segments: [] };
    }
    const segments: QuoteSegment[] = [];
    for (const ref of page.refs.slice(at, at + needle.length)) {
      const last = segments[segments.length - 1];
      if (last && last.item === ref.item) {
        // Spaces and punctuation skipped inside one item stay highlighted.
        last.end = Math.max(last.end, ref.end);
      } else {
        segments.push({ item: ref.item, start: ref.start, end: ref.end, quote: quoteIndex });
      }
    }
    return { quote: quoteIndex, found: true, segments };
  });
}

/** Segments grouped by text item, for the text-layer renderer. */
export function segmentsByItem(matches: readonly QuoteMatch[]): Map<number, QuoteSegment[]> {
  const byItem = new Map<number, QuoteSegment[]>();
  for (const match of matches) {
    for (const segment of match.segments) {
      const list = byItem.get(segment.item) ?? [];
      list.push(segment);
      byItem.set(segment.item, list);
    }
  }
  return byItem;
}

export function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/**
 * A text item's HTML for the PDF.js text layer: the text escaped, with quote ranges wrapped in
 * `<mark class="pdf-quote" data-quote="n">` (and `data-active` on the active quote). The item
 * text comes from the PDF, so nothing in it is ever interpreted as markup.
 */
export function highlightItemHtml(
  str: string,
  segments: readonly QuoteSegment[] | undefined,
  activeQuote?: number,
): string {
  if (!segments || segments.length === 0) {
    return escapeHtml(str);
  }
  const ordered = [...segments].sort((a, b) => a.start - b.start);
  let html = "";
  let position = 0;
  for (const segment of ordered) {
    const start = Math.max(segment.start, position);
    const end = Math.min(segment.end, str.length);
    if (end <= start) {
      continue;
    }
    html += escapeHtml(str.slice(position, start));
    const active = segment.quote === activeQuote ? " data-active" : "";
    html += `<mark class="pdf-quote" data-quote="${segment.quote}"${active}>${escapeHtml(
      str.slice(start, end),
    )}</mark>`;
    position = end;
  }
  return html + escapeHtml(str.slice(position));
}
