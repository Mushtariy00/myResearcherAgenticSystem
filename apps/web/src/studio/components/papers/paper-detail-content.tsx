"use client";

import { FileSearchIcon, FileXIcon, HistoryIcon, NotebookTextIcon } from "lucide-react";
import Link from "next/link";
import { useFormatter, useTranslations } from "next-intl";
import { useMemo, useRef, useState } from "react";
import type { EvidenceQuote, PaperDetail } from "@/client";
import { AnalysisCard } from "@/components/shared/analysis-card";
import { DemoBadge } from "@/components/shared/demo-badge";
import { PdfViewer } from "@/components/shared/pdf-viewer";
import { paperFileUrl, usePaper } from "@/hooks/use-paper";
import { toApiError } from "@/lib/api-error";
import { cn } from "@/lib/utils";
import { RunStatusPill } from "@/studio/components/dashboard/run-status-pill";
import { StudioInlineError } from "@/studio/components/dashboard/studio-panel";
import { LoadingStatus, ShimmerSkeleton } from "@/studio/components/effects/shimmer-skeleton";
import { StudioStatePanel } from "@/studio/components/studio-state-panel";
import { glassClassName } from "@/studio/lib/glass";
import { STUDIO_ROUTES, studioRunPath } from "@/studio/lib/nav";
import {
  CitationCount,
  DecisionPill,
  PaperLinks,
  PdfMark,
  RelevanceBar,
  useAuthorLine,
} from "./paper-meta";

type Variant = "page" | "sheet";

/** Every evidence quote of the paper's analyses in one list, and where each analysis starts. */
function flattenEvidence(detail: PaperDetail): { quotes: EvidenceQuote[]; offsets: number[] } {
  const quotes: EvidenceQuote[] = [];
  const offsets: number[] = [];
  for (const analysis of detail.analyses) {
    offsets.push(quotes.length);
    quotes.push(...analysis.evidence);
  }
  return { quotes, offsets };
}

/**
 * A library paper in full (usePaper): its record and links, the abstract, the PDF in a glass
 * frame with every analysis's evidence highlighted (an analysis's "Open in PDF" jumps there),
 * the analyses, and the runs that found it with their screening. The paper page shows it as the
 * page (`h1`); the project's paper sheet shows it under the sheet's title.
 */
export function PaperDetailContent({ paperId, variant }: { paperId: string; variant: Variant }) {
  const t = useTranslations("studioWork.papers.detail");
  const tAll = useTranslations();
  const format = useFormatter();
  const authorLine = useAuthorLine();
  const query = usePaper(paperId);
  const viewer = useRef<HTMLDivElement>(null);
  const [activeQuote, setActiveQuote] = useState(0);
  const evidence = useMemo(
    () => (query.data ? flattenEvidence(query.data) : { quotes: [], offsets: [] }),
    [query.data],
  );
  const page = variant === "page";
  const Title = page ? "h1" : "h2";
  const Section = page ? "h2" : "h3";

  if (query.isPending) {
    return (
      <div className="grid gap-4" aria-busy="true">
        <LoadingStatus label={tAll("common.loading")} />
        <ShimmerSkeleton className="h-8 w-3/4" />
        <ShimmerSkeleton className="h-4 w-1/2" />
        <ShimmerSkeleton className="h-32 rounded-2xl" />
        <ShimmerSkeleton className="h-[50vh] rounded-2xl" />
      </div>
    );
  }
  if (query.isError) {
    const notFound = toApiError(query.error).code === "paper.not_found";
    if (notFound) {
      return (
        <StudioStatePanel
          variant={page ? "page" : "section"}
          headingLevel={page ? 1 : 3}
          icon={<FileXIcon aria-hidden />}
          title={t("notFoundTitle")}
          description={tAll("errors.paper.not_found")}
          action={page ? { href: STUDIO_ROUTES.papers, label: t("backToLibrary") } : undefined}
        />
      );
    }
    return <StudioInlineError error={query.error} onRetry={() => query.refetch()} />;
  }

  const { paper, analyses, runs } = query.data;
  const runTopics = new Map(runs.map((run) => [run.id, run.topic]));

  function openQuote(analysisIndex: number, quoteIndex: number) {
    setActiveQuote((evidence.offsets[analysisIndex] ?? 0) + quoteIndex);
    viewer.current?.scrollIntoView({ block: "start", behavior: "smooth" });
  }

  return (
    <article className="grid min-w-0 gap-6" aria-labelledby={`paper-${variant}-title`}>
      <header className="grid min-w-0 gap-3">
        <p className="flex flex-wrap items-center gap-2 text-xs font-medium text-muted-foreground">
          <span data-stage="literature" className="text-(--tone-fg)">
            {tAll(`shared.papers.sources.${paper.source}`)}
          </span>
          <span aria-hidden>·</span>
          <span className="tabular-nums">{paper.year}</span>
          <DemoBadge demo={query.data.demo} />
        </p>
        <Title
          id={`paper-${variant}-title`}
          className={cn(
            "studio-display text-foreground [overflow-wrap:anywhere]",
            page ? "text-2xl sm:text-3xl lg:text-4xl" : "text-xl",
          )}
        >
          {paper.title}
        </Title>
        <p className="text-sm text-pretty text-muted-foreground">
          {authorLine(paper.authors)}
          {paper.venue && <> · {paper.venue}</>}
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <RelevanceBar value={query.data.best_relevance} />
          <CitationCount count={paper.citation_count} />
          <PdfMark available={paper.pdf_available} />
        </div>
        <PaperLinks paper={paper} />
      </header>

      {paper.abstract && (
        <section
          aria-labelledby={`paper-${variant}-abstract`}
          className={cn(glassClassName(), "grid gap-2 p-4 sm:p-5")}
        >
          <Section
            id={`paper-${variant}-abstract`}
            className="text-sm font-semibold text-foreground"
          >
            {t("abstract")}
          </Section>
          <p className="text-sm leading-relaxed text-pretty whitespace-pre-line text-muted-foreground">
            {paper.abstract}
          </p>
        </section>
      )}

      <div
        className={cn("grid min-w-0 gap-6", page && "xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]")}
      >
        <section
          ref={viewer}
          aria-labelledby={`paper-${variant}-pdf`}
          className="grid min-w-0 scroll-mt-24 content-start gap-3"
        >
          <Section
            id={`paper-${variant}-pdf`}
            className="flex items-center gap-2 text-sm font-semibold text-foreground"
          >
            <FileSearchIcon aria-hidden className="size-4 text-muted-foreground" />
            {t("pdf")}
          </Section>
          {paper.pdf_available ? (
            <div className={cn(glassClassName(), "min-w-0 overflow-hidden p-1.5 sm:p-2")}>
              <PdfViewer
                url={paperFileUrl(paper.paper_id)}
                title={paper.title}
                quotes={evidence.quotes}
                activeQuote={activeQuote}
                onActiveQuoteChange={setActiveQuote}
                height={page ? "75vh" : "60vh"}
                className="rounded-xl"
              />
            </div>
          ) : (
            <p className="rounded-2xl border border-dashed border-(--studio-glass-border) px-4 py-8 text-center text-sm text-muted-foreground">
              {tAll("shared.analysis.noPdf")}
            </p>
          )}
        </section>

        <section
          aria-labelledby={`paper-${variant}-analyses`}
          className="grid min-w-0 content-start gap-3"
        >
          <Section
            id={`paper-${variant}-analyses`}
            className="flex items-center gap-2 text-sm font-semibold text-foreground"
          >
            <NotebookTextIcon aria-hidden className="size-4 text-muted-foreground" />
            {t("analyses", { count: analyses.length })}
          </Section>
          {analyses.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("noAnalyses")}</p>
          ) : (
            <ol className="grid gap-4">
              {analyses.map((analysis, index) => (
                <li key={analysis.stage_output_id} className="grid min-w-0 gap-2">
                  <p className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <span>
                      {t("analysisFrom", {
                        topic: runTopics.get(analysis.run_id) ?? t("unknownRun"),
                        date: format.dateTime(new Date(analysis.created_at), {
                          dateStyle: "medium",
                        }),
                      })}
                    </span>
                    {analysis.attempt > 1 && (
                      <span>· {tAll("run.timeline.attempt", { attempt: analysis.attempt })}</span>
                    )}
                    <DemoBadge demo={analysis.demo} />
                  </p>
                  <AnalysisCard
                    analysis={analysis}
                    pdfAvailable={paper.pdf_available}
                    onOpenInPdf={(_quote, quoteIndex) => openQuote(index, quoteIndex)}
                  />
                </li>
              ))}
            </ol>
          )}
        </section>
      </div>

      <section aria-labelledby={`paper-${variant}-runs`} className="grid min-w-0 gap-3">
        <Section
          id={`paper-${variant}-runs`}
          className="flex items-center gap-2 text-sm font-semibold text-foreground"
        >
          <HistoryIcon aria-hidden className="size-4 text-muted-foreground" />
          {t("runs", { count: runs.length })}
        </Section>
        {runs.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("noRuns")}</p>
        ) : (
          <ul className="grid gap-2">
            {runs.map((run) => (
              <li
                key={run.id}
                className="grid gap-2 rounded-xl border border-(--studio-glass-border) bg-(--studio-glass) p-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start"
              >
                <div className="grid min-w-0 gap-1">
                  <Link
                    href={studioRunPath(run.id)}
                    className="line-clamp-2 w-fit rounded-sm text-sm font-medium text-foreground [overflow-wrap:anywhere] underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"
                  >
                    {run.topic}
                  </Link>
                  <p className="text-xs text-muted-foreground">
                    {run.project_name} ·{" "}
                    {format.dateTime(new Date(run.created_at), { dateStyle: "medium" })}
                  </p>
                  {run.decision_reason && (
                    <p className="text-xs text-pretty text-muted-foreground">
                      {run.decision_reason}
                    </p>
                  )}
                </div>
                <div className="flex flex-wrap items-center gap-2 sm:justify-end">
                  <RunStatusPill status={run.status} className="h-5" />
                  <DecisionPill decision={run.decision} />
                  <RelevanceBar value={run.relevance} />
                  <DemoBadge demo={run.demo} />
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </article>
  );
}
