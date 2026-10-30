"use client";

import { Dialog } from "@base-ui/react/dialog";
import { ExternalLinkIcon, FileTextIcon, QuoteIcon, XIcon } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useEffect, useId, useRef, useState } from "react";
import type { PaperOut, PaperRef } from "@/client";
import { AnalysisCard, type AnalysisSummary } from "@/components/shared/analysis-card";
import { DemoBadge } from "@/components/shared/demo-badge";
import { authorNames } from "@/components/shared/format";
import { PdfViewer } from "@/components/shared/pdf-viewer";
import { paperFileUrl, usePaper } from "@/hooks/use-paper";
import { cn } from "@/lib/utils";
import { LoadingStatus, ShimmerSkeleton } from "@/studio/components/effects/shimmer-skeleton";
import { useReducedMotionPreference } from "@/studio/hooks/use-media-query";
import { EYEBROW, ICON_BUTTON } from "@/studio/lib/ui";
import { STUDIO_BACKDROP } from "./confirm-dialog";
import { type PaperTarget, useRunPage } from "./run-context";
import { doiHref, externalHref } from "./run-helpers";
import { Chip, LINK_BUTTON, TOGGLE_BUTTON } from "./run-ui";

const DECISION_TONES = { include: "success", maybe: "warning", exclude: "neutral" } as const;

const SHEET = cn(
  "studio-glass fixed inset-x-0 bottom-0 z-50 flex max-h-[calc(100dvh-2.5rem)] flex-col rounded-t-2xl rounded-b-none bg-popover text-popover-foreground outline-none",
  "sm:inset-y-0 sm:right-0 sm:left-auto sm:max-h-none sm:w-[min(46rem,100vw)] sm:rounded-none sm:rounded-l-2xl",
  "transition-[translate] duration-300 ease-out data-ending-style:translate-y-full data-starting-style:translate-y-full motion-reduce:transition-none",
  "sm:data-ending-style:translate-x-full sm:data-ending-style:translate-y-0 sm:data-starting-style:translate-x-full sm:data-starting-style:translate-y-0",
);

/**
 * A paper in a sheet (from the side on wide screens, from the bottom on phones): its record,
 * the run's screening of it, the abstract, the reading notes with their evidence quotes, and
 * the PDF with those quotes highlighted ("Open in PDF" jumps to one). Opened from the papers
 * table, key findings, proposals and `[n]` citations in the draft. A paper the run's literature
 * output does not list is looked up in the library.
 */
export function PaperSheet({
  target,
  onClose,
}: {
  target: PaperTarget | null;
  onClose: () => void;
}) {
  // Keeps the paper on screen while the sheet slides away.
  const [last, setLast] = useState<PaperTarget | null>(target);
  if (target && target !== last) {
    setLast(target);
  }
  const shown = target ?? last;
  return (
    <Dialog.Root
      open={target !== null}
      onOpenChange={(open) => {
        if (!open) {
          onClose();
        }
      }}
    >
      <Dialog.Portal>
        <Dialog.Backdrop className={STUDIO_BACKDROP} />
        <Dialog.Popup className={SHEET}>
          {shown && (
            <PaperSheetBody
              key={`${shown.paperId ?? "none"}:${shown.citationKey ?? ""}:${shown.quote ?? ""}`}
              target={shown}
            />
          )}
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function PaperSheetBody({ target }: { target: PaperTarget }) {
  const t = useTranslations("studioRun.paper");
  const tPapers = useTranslations("shared.papers");
  const { literature: runLiterature } = useRunPage();
  const literature = target.literature ?? runLiterature;
  const paperId = target.paperId;
  const fromRun = paperId
    ? literature?.papers.find((paper) => paper.paper_id === paperId)
    : undefined;
  const runAnalysis = paperId
    ? literature?.analyses?.find((analysis) => analysis.paper_id === paperId)
    : undefined;
  const library = usePaper(paperId && !fromRun ? paperId : null);
  const paper: PaperRef | PaperOut | undefined = fromRun ?? library.data?.paper;
  const analysis: AnalysisSummary | undefined = runAnalysis ?? library.data?.analyses[0];
  const eyebrow =
    target.citationKey !== undefined ? t("citation", { key: target.citationKey }) : t("eyebrow");

  let title: string;
  let description: string;
  if (paper) {
    const { names, truncated } = authorNames(paper.authors, 6);
    const authors = names
      ? truncated
        ? tPapers("etAl", { names })
        : names
      : tPapers("unknownAuthors");
    title = paper.title;
    description = [authors, paper.venue, String(paper.year)].filter(Boolean).join(" · ");
  } else if (!paperId) {
    title = t("unknownCitation", { key: target.citationKey ?? 0 });
    description = t("unknownCitationDescription");
  } else if (library.isPending) {
    title = t("loading");
    description = paperId;
  } else {
    title = t("notFound");
    description = paperId;
  }

  return (
    <>
      <div className="flex shrink-0 items-start gap-3 border-b border-(--studio-glass-border) p-4 sm:p-5">
        <div className="grid min-w-0 flex-1 gap-1.5">
          <p data-stage="literature" className={EYEBROW}>
            <QuoteIcon aria-hidden className="size-3.5" />
            {eyebrow}
          </p>
          <Dialog.Title className="text-lg leading-snug font-semibold tracking-tight break-words text-foreground">
            {title}
          </Dialog.Title>
          <Dialog.Description className="text-sm break-words text-muted-foreground">
            {description}
          </Dialog.Description>
        </div>
        <Dialog.Close aria-label={t("close")} className={cn(ICON_BUTTON, "-mt-1 -mr-1")}>
          <XIcon aria-hidden />
        </Dialog.Close>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4 sm:p-5">
        {paper ? (
          <PaperDetails
            paper={paper}
            screening={fromRun}
            analysis={analysis}
            demo={library.data?.demo === true || paper.source === "demo"}
            initialQuote={target.quote}
          />
        ) : paperId && library.isPending ? (
          <div aria-busy="true" className="grid gap-3">
            <LoadingStatus label={t("loading")} />
            <ShimmerSkeleton className="h-4 w-3/4" />
            <ShimmerSkeleton className="h-4 w-2/3" />
            <ShimmerSkeleton className="h-32 w-full rounded-xl" />
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            {paperId ? t("notFoundDescription") : t("unknownCitationDescription")}
          </p>
        )}
      </div>
    </>
  );
}

function PaperDetails({
  paper,
  screening,
  analysis,
  demo,
  initialQuote,
}: {
  paper: PaperRef | PaperOut;
  screening: PaperRef | undefined;
  analysis: AnalysisSummary | undefined;
  demo: boolean;
  initialQuote: number | undefined;
}) {
  const t = useTranslations("studioRun.paper");
  const tPapers = useTranslations("shared.papers");
  const format = useFormatter();
  const reduced = useReducedMotionPreference();
  const pdfTitleId = useId();
  const pdfRegion = useRef<HTMLElement>(null);
  const [pdfOpen, setPdfOpen] = useState(initialQuote !== undefined);
  const [quote, setQuote] = useState(initialQuote ?? 0);
  const [scrollRequest, setScrollRequest] = useState(initialQuote !== undefined ? 1 : 0);

  useEffect(() => {
    if (scrollRequest > 0) {
      pdfRegion.current?.scrollIntoView({ block: "start", behavior: reduced ? "auto" : "smooth" });
    }
  }, [scrollRequest, reduced]);

  const links = [
    { key: "doi", href: doiHref(paper.doi), label: paper.doi ? t("doi", { doi: paper.doi }) : "" },
    {
      key: "arxiv",
      href:
        paper.arxiv_id && /^[\w./-]+$/.test(paper.arxiv_id)
          ? `https://arxiv.org/abs/${paper.arxiv_id}`
          : null,
      label: paper.arxiv_id ? t("arxiv", { id: paper.arxiv_id }) : "",
    },
    { key: "url", href: externalHref(paper.url), label: t("sourcePage") },
  ].filter((link): link is { key: string; href: string; label: string } => link.href !== null);
  const evidence = analysis?.evidence ?? [];

  return (
    <div className="grid min-w-0 gap-6">
      <div className="flex flex-wrap items-center gap-2">
        {screening && (
          <Chip tone={DECISION_TONES[screening.decision]}>
            {tPapers(`decisions.${screening.decision}`)}
          </Chip>
        )}
        <Chip>{tPapers(`sources.${paper.source}`)}</Chip>
        {paper.citation_count !== null && paper.citation_count !== undefined && (
          <Chip>{t("citations", { count: paper.citation_count })}</Chip>
        )}
        <Chip tone={paper.pdf_available ? "info" : "neutral"}>
          {paper.pdf_available ? tPapers("pdfAvailable") : tPapers("pdfMissing")}
        </Chip>
        {demo && <DemoBadge demo />}
      </div>

      {screening && (
        <section className="grid gap-2" aria-label={t("screening")}>
          <div className="flex items-center gap-3">
            <span className="text-xs font-medium text-muted-foreground">{t("relevance")}</span>
            <span
              aria-hidden
              data-stage="literature"
              className="h-1.5 w-28 overflow-hidden rounded-full bg-(--studio-glass-strong)"
            >
              <span
                className="block h-full rounded-full bg-(--tone)"
                style={{ width: `${Math.min(1, Math.max(0, screening.relevance)) * 100}%` }}
              />
            </span>
            <span className="font-mono text-xs text-foreground tabular-nums">
              {format.number(screening.relevance, {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              })}
            </span>
          </div>
          {screening.decision_reason && (
            <p className="text-sm break-words text-foreground">
              <span className="font-medium">{t("why")}</span> {screening.decision_reason}
            </p>
          )}
        </section>
      )}

      {links.length > 0 && (
        <ul className="flex flex-wrap gap-x-4 gap-y-2">
          {links.map((link) => (
            <li key={link.key} className="min-w-0">
              <a
                href={link.href}
                target="_blank"
                rel="noopener noreferrer nofollow"
                className={cn(LINK_BUTTON, "break-all")}
              >
                <ExternalLinkIcon aria-hidden />
                {link.label}
                <span className="sr-only"> ({t("newTab")})</span>
              </a>
            </li>
          ))}
        </ul>
      )}

      <section className="grid gap-2" aria-label={t("abstract")}>
        <h3 className={EYEBROW} data-stage="literature">
          {t("abstract")}
        </h3>
        <p className="text-sm leading-7 break-words whitespace-pre-line text-foreground">
          {paper.abstract}
        </p>
      </section>

      <section className="grid gap-2" aria-label={t("analysis")}>
        <h3 className={EYEBROW} data-stage="literature">
          {t("analysis")}
        </h3>
        {analysis ? (
          <AnalysisCard
            analysis={analysis}
            pdfAvailable={paper.pdf_available}
            onOpenInPdf={(_quote, index) => {
              setQuote(index);
              setPdfOpen(true);
              setScrollRequest((value) => value + 1);
            }}
            className="bg-(--studio-glass-strong)"
          />
        ) : (
          <p className="text-sm text-muted-foreground">{t("noAnalysis")}</p>
        )}
      </section>

      <section ref={pdfRegion} aria-labelledby={pdfTitleId} className="grid scroll-mt-4 gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 id={pdfTitleId} className={EYEBROW} data-stage="literature">
            <FileTextIcon aria-hidden className="size-3.5" />
            {t("pdf")}
          </h3>
          {paper.pdf_available && (
            <button
              type="button"
              aria-expanded={pdfOpen}
              onClick={() => setPdfOpen((value) => !value)}
              className={TOGGLE_BUTTON}
              data-stage="literature"
            >
              {pdfOpen ? t("hidePdf") : t("showPdf")}
            </button>
          )}
        </div>
        {!paper.pdf_available ? (
          <p className="text-sm text-muted-foreground">{t("noPdf")}</p>
        ) : (
          pdfOpen && (
            <PdfViewer
              url={paperFileUrl(paper.paper_id)}
              title={paper.title}
              quotes={evidence}
              activeQuote={quote}
              onActiveQuoteChange={setQuote}
              height="70vh"
            />
          )
        )}
      </section>
    </div>
  );
}
