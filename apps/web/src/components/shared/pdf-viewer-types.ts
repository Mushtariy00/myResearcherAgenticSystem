import type { EvidenceQuote } from "@/client";

export type PdfViewerProps = {
  /** Same-origin URL of the PDF (e.g. `paperFileUrl(paper.paper_id)`); cookies are sent. */
  url: string;
  /** The document's title, for the accessible name of the page area. */
  title?: string;
  /** Evidence quotes to highlight, each on its page. */
  quotes?: readonly EvidenceQuote[];
  /** The quote to show (index into `quotes`); default the first. Changing it jumps there. */
  activeQuote?: number;
  onActiveQuoteChange?: (index: number) => void;
  /** First page shown when there are no quotes (1-based). */
  initialPage?: number;
  /** CSS height of the scrollable page area; default 70vh. */
  height?: string;
  className?: string;
};
