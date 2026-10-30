"use client";

import "react-pdf/dist/Page/TextLayer.css";
import { Toolbar } from "@base-ui/react/toolbar";
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  CircleAlertIcon,
  MoveHorizontalIcon,
  QuoteIcon,
  RotateCwIcon,
  ZoomInIcon,
  ZoomOutIcon,
} from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import {
  type KeyboardEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import { Document, Page, pdfjs, type TextContent } from "react-pdf";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  findQuotes,
  highlightItemHtml,
  itemText,
  type QuoteMatch,
  segmentsByItem,
} from "./pdf-highlight";
import type { PdfViewerProps } from "./pdf-viewer-types";
import { useElementWidth, useReducedMotion } from "./use-dom";

// The PDF.js worker comes from the local package (bundled module worker), never a CDN. It must
// be configured in the module that renders react-pdf components.
if (
  typeof window !== "undefined" &&
  typeof Worker !== "undefined" &&
  !pdfjs.GlobalWorkerOptions.workerPort
) {
  pdfjs.GlobalWorkerOptions.workerPort = new Worker(
    new URL("./workers/pdf.worker.ts", import.meta.url),
    { type: "module", name: "pdfjs" },
  );
}

/** XFA forms stay off (the default, stated): reviewers read papers, they do not fill them in. */
const DOCUMENT_OPTIONS = { enableXfa: false } as const;
const ZOOM_STEPS = [0.5, 0.67, 0.8, 0.9, 1, 1.1, 1.25, 1.5, 1.75, 2, 2.5, 3];
const MIN_ZOOM = 0.5;
const MAX_ZOOM = 3;
const PAGE_GUTTER = 32;

type Zoom = { fit: true } | { fit: false; scale: number };
type PageHighlights = { matches: QuoteMatch[]; byItem: ReturnType<typeof segmentsByItem> };

function ToolbarButton({
  label,
  onClick,
  disabled,
  pressed,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  pressed?: boolean;
  children: ReactNode;
}) {
  return (
    <Toolbar.Button
      render={<Button variant="ghost" size="icon-sm" />}
      aria-label={label}
      title={label}
      aria-pressed={pressed}
      disabled={disabled}
      onClick={onClick}
    >
      {children}
    </Toolbar.Button>
  );
}

/** react-pdf viewer with quote highlights; load it through PdfViewer (client only, lazy). */
export function PdfViewerImpl({
  url,
  title,
  quotes = [],
  activeQuote,
  onActiveQuoteChange,
  initialPage = 1,
  height = "70vh",
  className,
}: PdfViewerProps) {
  const t = useTranslations("shared.pdf");
  const format = useFormatter();
  const reducedMotion = useReducedMotion();
  const hintId = useId();
  const scroller = useRef<HTMLDivElement>(null);
  const pageElement = useRef<HTMLDivElement>(null);
  const width = useElementWidth(scroller);

  const [attempt, setAttempt] = useState(0);
  const [failed, setFailed] = useState(false);
  const [numPages, setNumPages] = useState(0);
  const [pageNumber, setPageNumber] = useState(Math.max(1, quotes[0]?.page ?? initialPage));
  const [pageInput, setPageInput] = useState(String(pageNumber));
  const [pageWidth, setPageWidth] = useState<number>();
  const [zoom, setZoom] = useState<Zoom>({ fit: true });
  const [ownQuote, setOwnQuote] = useState(0);
  const [highlights, setHighlights] = useState<ReadonlyMap<number, PageHighlights>>(new Map());
  const [pendingScroll, setPendingScroll] = useState<number | null>(quotes.length > 0 ? 0 : null);
  const [announcement, setAnnouncement] = useState("");

  const quoteIndex = Math.min(Math.max(activeQuote ?? ownQuote, 0), Math.max(quotes.length - 1, 0));
  const current = quotes[quoteIndex];

  // A new document starts over.
  // biome-ignore lint/correctness/useExhaustiveDependencies: reset only when the URL changes
  useEffect(() => {
    setFailed(false);
    setNumPages(0);
    setHighlights(new Map());
  }, [url]);

  const goToPage = useCallback(
    (target: number) => {
      const last = numPages || target;
      const next = Math.min(Math.max(1, Math.round(target)), Math.max(1, last));
      setPageNumber(next);
      setPageInput(String(next));
      if (numPages > 0) {
        setAnnouncement(t("pageStatus", { page: next, total: numPages }));
      }
    },
    [numPages, t],
  );

  // Jump to the active quote's page whenever the active quote changes.
  const activePage = current?.page;
  const activeText = current?.quote;
  // biome-ignore lint/correctness/useExhaustiveDependencies: activeText marks a different quote
  useEffect(() => {
    if (activePage === undefined) {
      return;
    }
    setPageNumber(activePage);
    setPageInput(String(activePage));
    setPendingScroll(quoteIndex);
  }, [activePage, activeText, quoteIndex]);

  function selectQuote(index: number) {
    if (index < 0 || index >= quotes.length) {
      return;
    }
    setOwnQuote(index);
    onActiveQuoteChange?.(index);
  }

  const effectiveScale = zoom.fit
    ? width && pageWidth
      ? Math.max(0.1, (width - PAGE_GUTTER) / pageWidth)
      : 1
    : zoom.scale;

  function zoomBy(direction: 1 | -1) {
    const next =
      direction > 0
        ? (ZOOM_STEPS.find((step) => step > effectiveScale + 0.001) ?? MAX_ZOOM)
        : ([...ZOOM_STEPS].reverse().find((step) => step < effectiveScale - 0.001) ?? MIN_ZOOM);
    setZoom({ fit: false, scale: next });
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (
      event.target instanceof HTMLInputElement ||
      event.altKey ||
      event.ctrlKey ||
      event.metaKey
    ) {
      return;
    }
    if (event.key === "PageDown") {
      event.preventDefault();
      goToPage(pageNumber + 1);
    } else if (event.key === "PageUp") {
      event.preventDefault();
      goToPage(pageNumber - 1);
    } else if (event.key === "+" || event.key === "=") {
      event.preventDefault();
      zoomBy(1);
    } else if (event.key === "-" || event.key === "_") {
      event.preventDefault();
      zoomBy(-1);
    }
  }

  // Quotes on the page being shown, with their index in `quotes`.
  const pageQuotes = useMemo(
    () =>
      quotes
        .map((quote, index) => ({ quote, index }))
        .filter((entry) => entry.quote.page === pageNumber),
    [quotes, pageNumber],
  );

  const onGetText = useCallback(
    ({ items }: TextContent) => {
      const local = findQuotes(
        items.map(itemText),
        pageQuotes.map((entry) => entry.quote.quote),
      ).map((match) => {
        const global = pageQuotes[match.quote]?.index ?? match.quote;
        return {
          ...match,
          quote: global,
          segments: match.segments.map((segment) => ({ ...segment, quote: global })),
        };
      });
      setHighlights((previous) => {
        const next = new Map(previous);
        next.set(pageNumber, { matches: local, byItem: segmentsByItem(local) });
        return next;
      });
    },
    [pageQuotes, pageNumber],
  );

  const pageHighlights = highlights.get(pageNumber);
  const highlighted = activePage === undefined ? undefined : quoteIndex;
  const textRenderer = useCallback(
    ({ str, itemIndex }: { str: string; itemIndex: number }) =>
      highlightItemHtml(str, pageHighlights?.byItem.get(itemIndex), highlighted),
    [pageHighlights, highlighted],
  );

  const quoteCount = quotes.length;
  const pendingPage = pendingScroll === null ? undefined : quotes[pendingScroll]?.page;
  const onTextLayerRendered = useCallback(() => {
    if (pendingScroll === null || pendingPage !== pageNumber || !pageHighlights) {
      return;
    }
    const found = pageHighlights.matches.find((match) => match.quote === pendingScroll)?.found;
    const mark = pageElement.current?.querySelector(`mark[data-quote="${pendingScroll}"]`);
    if (found && mark) {
      mark.scrollIntoView({ block: "center", behavior: reducedMotion ? "auto" : "smooth" });
      setAnnouncement(
        t("quoteOnPage", { index: pendingScroll + 1, total: quoteCount, page: pageNumber }),
      );
    } else {
      setAnnouncement(t("quoteNotFound", { index: pendingScroll + 1, page: pageNumber }));
    }
    setPendingScroll(null);
  }, [pendingScroll, pendingPage, pageNumber, pageHighlights, reducedMotion, quoteCount, t]);

  const currentNotFound =
    current &&
    current.page === pageNumber &&
    pageHighlights?.matches.find((match) => match.quote === quoteIndex)?.found === false;
  const documentLabel = title ? t("document", { title }) : t("documentUntitled");

  return (
    <div
      data-slot="pdf-viewer"
      className={cn("grid min-w-0 overflow-hidden rounded-xl border bg-card", className)}
    >
      <Toolbar.Root
        aria-label={t("toolbar")}
        className="flex flex-wrap items-center gap-1 border-b px-2 py-1.5 text-xs"
      >
        <ToolbarButton
          label={t("previousPage")}
          disabled={pageNumber <= 1}
          onClick={() => goToPage(pageNumber - 1)}
        >
          <ChevronLeftIcon aria-hidden />
        </ToolbarButton>
        <span className="flex items-center gap-1 text-muted-foreground">
          <Toolbar.Input
            value={pageInput}
            inputMode="numeric"
            aria-label={t("pageInput")}
            onChange={(event) => setPageInput(event.target.value.replace(/\D/g, ""))}
            onBlur={() => goToPage(Number(pageInput) || pageNumber)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                goToPage(Number(pageInput) || pageNumber);
              }
            }}
            className="h-7 w-11 rounded-md border bg-background px-1.5 text-center text-foreground tabular-nums outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
          />
          <span className="tabular-nums">{t("pageOf", { total: numPages || "–" })}</span>
        </span>
        <ToolbarButton
          label={t("nextPage")}
          disabled={numPages > 0 && pageNumber >= numPages}
          onClick={() => goToPage(pageNumber + 1)}
        >
          <ChevronRightIcon aria-hidden />
        </ToolbarButton>
        <Toolbar.Separator className="mx-1 h-5 w-px bg-border" />
        <ToolbarButton
          label={t("zoomOut")}
          disabled={effectiveScale <= MIN_ZOOM}
          onClick={() => zoomBy(-1)}
        >
          <ZoomOutIcon aria-hidden />
        </ToolbarButton>
        <span className="min-w-12 text-center text-muted-foreground tabular-nums">
          <span className="sr-only">{t("zoom")} </span>
          {format.number(effectiveScale, { style: "percent", maximumFractionDigits: 0 })}
        </span>
        <ToolbarButton
          label={t("zoomIn")}
          disabled={effectiveScale >= MAX_ZOOM}
          onClick={() => zoomBy(1)}
        >
          <ZoomInIcon aria-hidden />
        </ToolbarButton>
        <ToolbarButton
          label={t("fitWidth")}
          pressed={zoom.fit}
          onClick={() => setZoom({ fit: true })}
        >
          <MoveHorizontalIcon aria-hidden />
        </ToolbarButton>
        {quotes.length > 0 && (
          <>
            <Toolbar.Separator className="mx-1 h-5 w-px bg-border" />
            <ToolbarButton
              label={t("previousQuote")}
              disabled={quoteIndex <= 0}
              onClick={() => selectQuote(quoteIndex - 1)}
            >
              <ChevronLeftIcon aria-hidden />
            </ToolbarButton>
            <span className="flex items-center gap-1 text-muted-foreground tabular-nums">
              <QuoteIcon aria-hidden className="size-3.5" />
              {t("quotePosition", { index: quoteIndex + 1, total: quotes.length })}
            </span>
            <ToolbarButton
              label={t("nextQuote")}
              disabled={quoteIndex >= quotes.length - 1}
              onClick={() => selectQuote(quoteIndex + 1)}
            >
              <ChevronRightIcon aria-hidden />
            </ToolbarButton>
          </>
        )}
      </Toolbar.Root>
      {currentNotFound && current && (
        <p className="flex items-center gap-1.5 border-b px-3 py-1.5 text-xs text-muted-foreground">
          <CircleAlertIcon aria-hidden className="size-3.5" />
          {t("quoteNotFound", { index: quoteIndex + 1, page: current.page })}
        </p>
      )}
      <p id={hintId} className="sr-only">
        {t("shortcuts")}
      </p>
      <p role="status" className="sr-only">
        {announcement}
      </p>
      <section
        ref={scroller}
        aria-label={documentLabel}
        aria-describedby={hintId}
        // biome-ignore lint/a11y/noNoninteractiveTabindex: the page area scrolls and takes the shortcuts
        tabIndex={0}
        onKeyDown={onKeyDown}
        className="overflow-auto bg-muted/40 outline-none focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:ring-inset"
        style={{ height }}
      >
        {failed ? (
          <div className="grid h-full place-content-center gap-3 p-6 text-center text-sm">
            <p className="text-destructive">{t("error")}</p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="mx-auto"
              onClick={() => {
                setFailed(false);
                setAttempt((value) => value + 1);
              }}
            >
              <RotateCwIcon aria-hidden />
              {t("retry")}
            </Button>
          </div>
        ) : (
          <Document
            key={`${url}#${attempt}`}
            file={url}
            options={DOCUMENT_OPTIONS}
            suspense={false}
            onLoadSuccess={(document) => {
              setNumPages(document.numPages);
              setPageNumber((page) => Math.min(Math.max(1, page), document.numPages));
            }}
            onLoadError={() => setFailed(true)}
            loading={
              <div className="grid gap-3 p-6" role="status">
                <span className="sr-only">{t("loading")}</span>
                <Skeleton className="mx-auto h-[60vh] w-full max-w-2xl" />
              </div>
            }
            error={<p className="p-6 text-center text-sm text-destructive">{t("error")}</p>}
            className="flex justify-center py-4"
          >
            {numPages > 0 && (
              <Page
                pageNumber={Math.min(pageNumber, numPages)}
                inputRef={pageElement}
                width={zoom.fit && width ? Math.max(120, width - PAGE_GUTTER) : undefined}
                scale={zoom.fit ? 1 : zoom.scale}
                renderAnnotationLayer={false}
                renderTextLayer
                customTextRenderer={textRenderer}
                onLoadSuccess={(page) => setPageWidth(page.originalWidth)}
                onGetTextSuccess={onGetText}
                onRenderTextLayerSuccess={onTextLayerRendered}
                suspense={false}
                loading={
                  <div className="grid p-6" role="status">
                    <span className="sr-only">{t("loadingPage", { page: pageNumber })}</span>
                    <Skeleton className="mx-auto h-[60vh] w-full max-w-2xl" />
                  </div>
                }
                error={
                  <p className="p-6 text-center text-sm text-destructive">
                    {t("pageError", { page: pageNumber })}
                  </p>
                }
                className="relative shadow-md"
              />
            )}
          </Document>
        )}
      </section>
    </div>
  );
}
