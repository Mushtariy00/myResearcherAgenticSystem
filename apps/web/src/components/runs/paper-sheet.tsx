"use client";

import { Dialog } from "@base-ui/react/dialog";
import { ArrowLeftIcon, ExternalLinkIcon, FileTextIcon, XIcon } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useCallback, useState } from "react";
import type { PaperAnalysis, PaperRef } from "@/client";
import { AnalysisCard } from "@/components/shared/analysis-card";
import { authorNames } from "@/components/shared/format";
import { PdfViewer } from "@/components/shared/pdf-viewer";
import { Button } from "@/components/ui/button";
import { paperFileUrl } from "@/hooks/use-paper";
import { paperLinks } from "./run-data";

type SheetState = { paperId: string; open: boolean };

/**
 * Open/close state of a paper sheet. The paper stays on screen while the sheet animates out,
 * and is cleared once it has closed.
 */
export function usePaperSheet() {
  const [state, setState] = useState<SheetState | null>(null);
  const show = useCallback((paperId: string) => setState({ paperId, open: true }), []);
  const onOpenChange = useCallback(
    (open: boolean) => setState((current) => (current ? { ...current, open } : current)),
    [],
  );
  const onOpenChangeComplete = useCallback((open: boolean) => {
    if (!open) {
      setState(null);
    }
  }, []);
  return {
    paperId: state?.paperId ?? null,
    open: state?.open ?? false,
    show,
    onOpenChange,
    onOpenChangeComplete,
  };
}

export type PaperSheetProps = {
  sheet: ReturnType<typeof usePaperSheet>;
  /** The papers and reading notes of the literature output the paper comes from. */
  papers: readonly PaperRef[];
  analyses?: readonly PaperAnalysis[];
};

/**
 * A side sheet with one paper of a literature output: its record and abstract, this output's
 * reading notes on it, and its PDF with the notes' evidence quotes highlighted.
 */
export function PaperSheet({ sheet, papers, analyses }: PaperSheetProps) {
  const t = useTranslations("run.paper");
  const tc = useTranslations("common");
  const paper = papers.find((item) => item.paper_id === sheet.paperId);
  const analysis = analyses?.find((item) => item.paper_id === sheet.paperId);
  return (
    <Dialog.Root
      open={sheet.open}
      onOpenChange={sheet.onOpenChange}
      onOpenChangeComplete={sheet.onOpenChangeComplete}
    >
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-50 bg-black/20 transition-opacity duration-150 data-ending-style:opacity-0 data-starting-style:opacity-0 motion-reduce:transition-none supports-backdrop-filter:backdrop-blur-xs" />
        <Dialog.Popup
          data-slot="paper-sheet"
          className="fixed inset-y-0 right-0 z-50 flex w-full max-w-3xl flex-col bg-popover text-sm text-popover-foreground shadow-xl ring-1 ring-foreground/10 transition-transform duration-200 outline-none data-ending-style:translate-x-full data-starting-style:translate-x-full motion-reduce:transition-none"
        >
          <div className="flex items-start gap-3 border-b px-4 py-3">
            <FileTextIcon aria-hidden className="mt-1 size-4 shrink-0 text-muted-foreground" />
            <Dialog.Title className="min-w-0 flex-1 text-base leading-snug font-medium break-words">
              {paper?.title ?? t("unknownTitle")}
            </Dialog.Title>
            <Dialog.Close render={<Button variant="ghost" size="icon-sm" />}>
              <XIcon aria-hidden />
              <span className="sr-only">{tc("close")}</span>
            </Dialog.Close>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            {paper ? (
              <PaperSheetBody key={paper.paper_id} paper={paper} analysis={analysis} />
            ) : (
              <Dialog.Description className="text-muted-foreground">
                {t("unknown", { id: sheet.paperId ?? "" })}
              </Dialog.Description>
            )}
          </div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function PaperSheetBody({ paper, analysis }: { paper: PaperRef; analysis?: PaperAnalysis }) {
  const t = useTranslations("run.paper");
  const tPapers = useTranslations("shared.papers");
  const format = useFormatter();
  // Null: the details. A number: the PDF, at that evidence quote.
  const [quote, setQuote] = useState<number | null>(null);
  const quotes = analysis?.evidence ?? [];

  if (quote !== null) {
    return (
      <div className="grid gap-3">
        <Button variant="outline" size="sm" className="w-fit" onClick={() => setQuote(null)}>
          <ArrowLeftIcon aria-hidden />
          {t("backToDetails")}
        </Button>
        <PdfViewer
          url={paperFileUrl(paper.paper_id)}
          title={paper.title}
          quotes={quotes}
          activeQuote={quote}
          onActiveQuoteChange={setQuote}
          height="calc(100dvh - 11rem)"
        />
      </div>
    );
  }

  const { names, truncated } = authorNames(paper.authors, 8);
  const authors = names
    ? truncated
      ? tPapers("etAl", { names })
      : names
    : tPapers("unknownAuthors");
  const links = paperLinks(paper);
  return (
    <div className="grid gap-5">
      <Dialog.Description className="text-muted-foreground">
        {authors}
        {paper.venue ? ` · ${paper.venue}` : ""} · {paper.year}
      </Dialog.Description>
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1.5">
        <dt className="text-muted-foreground">{t("decision")}</dt>
        <dd>
          <span className="font-medium">{tPapers(`decisions.${paper.decision}`)}</span>
          {paper.decision_reason && (
            <span className="block text-muted-foreground">{paper.decision_reason}</span>
          )}
        </dd>
        <dt className="text-muted-foreground">{t("relevance")}</dt>
        <dd className="tabular-nums">
          {format.number(paper.relevance, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </dd>
        <dt className="text-muted-foreground">{t("citations")}</dt>
        <dd className="tabular-nums">
          {paper.citation_count === null || paper.citation_count === undefined
            ? tPapers("unknown")
            : format.number(paper.citation_count)}
        </dd>
        <dt className="text-muted-foreground">{t("source")}</dt>
        <dd>{tPapers(`sources.${paper.source}`)}</dd>
        {paper.doi && (
          <>
            <dt className="text-muted-foreground">{t("doi")}</dt>
            <dd className="font-mono text-xs break-all">{paper.doi}</dd>
          </>
        )}
      </dl>
      {links.length > 0 && (
        <ul className="flex flex-wrap gap-2" aria-label={t("links")}>
          {links.map((link) => (
            <li key={link.kind}>
              <a
                href={link.href}
                target="_blank"
                rel="noopener noreferrer nofollow"
                className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs font-medium outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"
              >
                <ExternalLinkIcon aria-hidden className="size-3.5" />
                {t(`link.${link.kind}`)}
                <span className="sr-only">{t("opensInNewTab")}</span>
              </a>
            </li>
          ))}
        </ul>
      )}
      <section className="grid gap-1.5" aria-labelledby={`abstract-${paper.paper_id}`}>
        <h3 id={`abstract-${paper.paper_id}`} className="text-sm font-semibold">
          {t("abstract")}
        </h3>
        <p className="leading-relaxed break-words whitespace-pre-line">
          {paper.abstract || t("noAbstract")}
        </p>
      </section>
      <section className="grid gap-2" aria-labelledby={`notes-${paper.paper_id}`}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 id={`notes-${paper.paper_id}`} className="text-sm font-semibold">
            {t("notes")}
          </h3>
          <Button
            size="sm"
            variant="outline"
            disabled={!paper.pdf_available}
            onClick={() => setQuote(0)}
          >
            <FileTextIcon aria-hidden />
            {t("openPdf")}
          </Button>
        </div>
        {/* With evidence quotes, the notes say it under the quotes instead. */}
        {!paper.pdf_available && quotes.length === 0 && (
          <p className="text-xs text-muted-foreground">{t("noPdf")}</p>
        )}
        {analysis ? (
          <AnalysisCard
            analysis={analysis}
            pdfAvailable={paper.pdf_available}
            onOpenInPdf={(_quote, index) => setQuote(index)}
          />
        ) : (
          <p className="text-muted-foreground">{t("noNotes")}</p>
        )}
      </section>
    </div>
  );
}
