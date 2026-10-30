"use client";

import { ExternalLinkIcon, FileXIcon } from "lucide-react";
import Link from "next/link";
import { useFormatter, useTranslations } from "next-intl";
import { Fragment, type ReactNode, type Ref, useId, useMemo, useRef, useState } from "react";
import type { EvidenceQuote, PaperAnalysisOut, PaperDetail, PaperOut, PaperRunOut } from "@/client";
import { RunStatusBadge } from "@/components/app/status-badge";
import { AnalysisCard } from "@/components/shared/analysis-card";
import { CopyButton } from "@/components/shared/copy-button";
import { DemoBadge } from "@/components/shared/demo-badge";
import { authorNames } from "@/components/shared/format";
import { PdfViewer } from "@/components/shared/pdf-viewer";
import { useReducedMotion } from "@/components/shared/use-dom";
import { paperFileUrl } from "@/hooks/use-paper";

/** "page": the paper's own page (PDF beside the text on wide screens); "sheet": the side sheet. */
export type PaperLayout = "page" | "sheet";

const DECISION_TONES: Record<PaperRunOut["decision"], string> = {
  include: "success",
  maybe: "warning",
  exclude: "neutral",
};

/** An http(s) link from paper metadata, or null: other schemes (javascript:, data:) never render. */
export function safeExternalUrl(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch {
    return null;
  }
}

/** Ids such as DOIs keep their slashes in resolver URLs; every part is encoded. */
function encodePath(value: string): string {
  return value.split("/").map(encodeURIComponent).join("/");
}

/** "A. Author, B. Author et al. · CVPR 2024" */
export function PaperByline({ paper }: { paper: Pick<PaperOut, "authors" | "venue" | "year"> }) {
  const t = useTranslations("shared.papers");
  const { names, truncated } = authorNames(paper.authors);
  const authors = names ? (truncated ? t("etAl", { names }) : names) : t("unknownAuthors");
  return (
    <>
      {authors}
      {" · "}
      {paper.venue ? `${paper.venue} ` : ""}
      {paper.year}
    </>
  );
}

function DecisionPill({ decision }: { decision: PaperRunOut["decision"] }) {
  const t = useTranslations("shared.papers.decisions");
  return (
    <span
      data-tone={DECISION_TONES[decision]}
      className="inline-flex h-5 w-fit shrink-0 items-center rounded-full bg-(--tone)/15 px-2 text-xs font-medium whitespace-nowrap text-(--tone-fg)"
    >
      {t(decision)}
    </span>
  );
}

function ExternalLink({ href, children }: { href: string; children: ReactNode }) {
  const t = useTranslations("papers.detail");
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 rounded-sm break-all underline-offset-4 hover:underline focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
    >
      {children}
      <ExternalLinkIcon aria-hidden className="size-3 shrink-0" />
      <span className="sr-only">{t("opensInNewTab")}</span>
    </a>
  );
}

/** A titled part of the paper; its heading level follows the page (h2) or the sheet (h3). */
function Section({
  title,
  level,
  children,
  sectionRef,
}: {
  title: string;
  level: "h2" | "h3";
  children: ReactNode;
  sectionRef?: Ref<HTMLElement>;
}) {
  const id = useId();
  const Heading = level;
  return (
    <section
      ref={sectionRef}
      aria-labelledby={id}
      className="grid min-w-0 scroll-mt-20 content-start gap-3"
    >
      <Heading id={id} className="text-base font-semibold">
        {title}
      </Heading>
      {children}
    </section>
  );
}

function PaperFacts({ detail }: { detail: PaperDetail }) {
  const t = useTranslations("papers.detail");
  const tPapers = useTranslations("shared.papers");
  const format = useFormatter();
  const { paper } = detail;
  const link = safeExternalUrl(paper.url);
  const rows: { key: string; label: string; value: ReactNode }[] = [
    {
      key: "authors",
      label: t("authors"),
      value: paper.authors.length > 0 ? paper.authors.join(", ") : tPapers("unknownAuthors"),
    },
    { key: "year", label: t("year"), value: paper.year },
  ];
  if (paper.venue) {
    rows.push({ key: "venue", label: t("venue"), value: paper.venue });
  }
  if (paper.doi) {
    rows.push({
      key: "doi",
      label: t("doi"),
      value: (
        <ExternalLink href={`https://doi.org/${encodePath(paper.doi)}`}>{paper.doi}</ExternalLink>
      ),
    });
  }
  if (paper.arxiv_id) {
    rows.push({
      key: "arxiv",
      label: t("arxiv"),
      value: (
        <ExternalLink href={`https://arxiv.org/abs/${encodePath(paper.arxiv_id)}`}>
          {paper.arxiv_id}
        </ExternalLink>
      ),
    });
  }
  if (link) {
    rows.push({
      key: "url",
      label: t("link"),
      value: <ExternalLink href={link}>{link}</ExternalLink>,
    });
  }
  rows.push(
    {
      key: "citations",
      label: t("citations"),
      value:
        paper.citation_count === null ? tPapers("unknown") : format.number(paper.citation_count),
    },
    { key: "source", label: t("source"), value: tPapers(`sources.${paper.source}`) },
    {
      key: "pdf",
      label: t("pdf"),
      value: paper.pdf_available ? tPapers("pdfAvailable") : tPapers("pdfMissing"),
    },
    {
      key: "relevance",
      label: t("bestRelevance"),
      value: format.number(detail.best_relevance, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }),
    },
    {
      key: "id",
      label: t("id"),
      value: (
        <span className="inline-flex max-w-full items-center gap-1">
          <code className="font-mono text-xs break-all">{paper.paper_id}</code>
          <CopyButton value={paper.paper_id} label={t("copyId")} size="icon-xs" />
        </span>
      ),
    },
  );
  return (
    <dl className="grid gap-x-4 gap-y-2 sm:grid-cols-[minmax(7rem,auto)_minmax(0,1fr)]">
      {rows.map((row) => (
        <Fragment key={row.key}>
          <dt className="text-xs font-medium text-muted-foreground sm:pt-0.5">{row.label}</dt>
          <dd className="min-w-0 break-words">{row.value}</dd>
        </Fragment>
      ))}
    </dl>
  );
}

/** Every evidence quote of every analysis, in order, and the one the PDF shows. */
function useEvidence(analyses: readonly PaperAnalysisOut[]) {
  const { quotes, offsets } = useMemo(() => {
    const all: EvidenceQuote[] = [];
    const starts: number[] = [];
    for (const analysis of analyses) {
      starts.push(all.length);
      all.push(...analysis.evidence);
    }
    return { quotes: all, offsets: starts };
  }, [analyses]);
  const [active, setActive] = useState(0);
  return {
    quotes,
    active: Math.min(active, Math.max(0, quotes.length - 1)),
    setActive,
    /** The index into `quotes` of quote `quoteIndex` of analysis `analysisIndex`. */
    indexOf: (analysisIndex: number, quoteIndex: number) =>
      (offsets[analysisIndex] ?? 0) + quoteIndex,
  };
}

function AnalysisList({
  detail,
  onOpenQuote,
}: {
  detail: PaperDetail;
  onOpenQuote: (analysisIndex: number, quoteIndex: number) => void;
}) {
  const t = useTranslations("papers.detail");
  const format = useFormatter();
  const runs = new Map(detail.runs.map((run) => [run.id, run]));
  if (detail.analyses.length === 0) {
    return <p className="text-sm text-muted-foreground">{t("noAnalyses")}</p>;
  }
  return (
    <ol className="grid gap-4">
      {detail.analyses.map((analysis, index) => {
        const run = runs.get(analysis.run_id);
        return (
          <li key={analysis.stage_output_id} className="grid gap-2">
            <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
              {run ? (
                <Link
                  href={`/runs/${run.id}`}
                  className="font-medium text-foreground underline-offset-4 hover:underline focus-visible:underline focus-visible:outline-none"
                >
                  {t("analysisFrom", { topic: run.topic })}
                </Link>
              ) : (
                <span>{t("analysisFromOtherRun")}</span>
              )}
              <span>{t("attempt", { attempt: analysis.attempt })}</span>
              <time dateTime={analysis.created_at}>
                {format.dateTime(new Date(analysis.created_at), { dateStyle: "medium" })}
              </time>
              <DemoBadge demo={analysis.demo} />
            </p>
            <AnalysisCard
              analysis={analysis}
              pdfAvailable={detail.paper.pdf_available}
              onOpenInPdf={(_quote, quoteIndex) => onOpenQuote(index, quoteIndex)}
            />
          </li>
        );
      })}
    </ol>
  );
}

function RunList({ runs }: { runs: readonly PaperRunOut[] }) {
  const t = useTranslations("papers.detail");
  const format = useFormatter();
  if (runs.length === 0) {
    return <p className="text-sm text-muted-foreground">{t("noRuns")}</p>;
  }
  return (
    <ul className="grid gap-2">
      {runs.map((run) => (
        <li key={run.id} className="grid gap-1.5 rounded-lg border p-3">
          <div className="flex flex-wrap items-center gap-2">
            <Link
              href={`/runs/${run.id}`}
              className="min-w-0 font-medium break-words underline-offset-4 hover:underline focus-visible:underline focus-visible:outline-none"
            >
              {run.topic}
            </Link>
            <RunStatusBadge status={run.status} />
            <DemoBadge demo={run.demo} />
          </div>
          <p className="flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
            <Link
              href={`/projects/${run.project_id}`}
              className="underline-offset-4 hover:text-foreground hover:underline focus-visible:underline focus-visible:outline-none"
            >
              {run.project_name}
            </Link>
            <span aria-hidden>·</span>
            <time dateTime={run.created_at}>
              {format.dateTime(new Date(run.created_at), { dateStyle: "medium" })}
            </time>
          </p>
          <p className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <DecisionPill decision={run.decision} />
            <span className="tabular-nums">
              {t("relevance", {
                value: format.number(run.relevance, {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                }),
              })}
            </span>
          </p>
          {run.decision_reason && (
            <p className="text-sm break-words text-muted-foreground">{run.decision_reason}</p>
          )}
        </li>
      ))}
    </ul>
  );
}

/**
 * Everything the library knows about a paper: its record, abstract, the analyses of every run
 * that read it (each quote opens the PDF at its page, highlighted), the PDF and the runs that
 * found it. Shared by the paper page and the side sheet of the paper tables.
 */
export function PaperDetailBody({ detail, layout }: { detail: PaperDetail; layout: PaperLayout }) {
  const t = useTranslations("papers.detail");
  const reducedMotion = useReducedMotion();
  const evidence = useEvidence(detail.analyses);
  const pdfSection = useRef<HTMLElement>(null);
  const level = layout === "page" ? "h2" : "h3";
  const { paper } = detail;

  function openQuote(analysisIndex: number, quoteIndex: number) {
    evidence.setActive(evidence.indexOf(analysisIndex, quoteIndex));
    pdfSection.current?.scrollIntoView?.({
      block: "start",
      behavior: reducedMotion ? "auto" : "smooth",
    });
  }

  const facts = (
    <Section title={t("details")} level={level}>
      <PaperFacts detail={detail} />
    </Section>
  );
  const abstract = (
    <Section title={t("abstract")} level={level}>
      {paper.abstract.trim() ? (
        <p className="leading-relaxed break-words whitespace-pre-line">{paper.abstract}</p>
      ) : (
        <p className="text-sm text-muted-foreground">{t("noAbstract")}</p>
      )}
    </Section>
  );
  const analyses = (
    <Section title={t("analyses", { count: detail.analyses.length })} level={level}>
      <AnalysisList detail={detail} onOpenQuote={openQuote} />
    </Section>
  );
  const runs = (
    <Section title={t("runs", { count: detail.runs.length })} level={level}>
      <RunList runs={detail.runs} />
    </Section>
  );
  const pdf = (
    <Section title={t("pdfTitle")} level={level} sectionRef={pdfSection}>
      {paper.pdf_available ? (
        <PdfViewer
          url={paperFileUrl(paper.paper_id)}
          title={paper.title}
          quotes={evidence.quotes}
          activeQuote={evidence.active}
          onActiveQuoteChange={evidence.setActive}
          // On wide pages the viewer stays in view beside the text, so it fits the window.
          height={layout === "page" ? "calc(100dvh - 12rem)" : "60vh"}
        />
      ) : (
        <p className="flex items-center gap-2 rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
          <FileXIcon aria-hidden className="size-4 shrink-0" />
          {t("noPdf")}
        </p>
      )}
    </Section>
  );

  if (layout === "sheet") {
    return (
      <div className="grid gap-6">
        {facts}
        {abstract}
        {analyses}
        {pdf}
        {runs}
      </div>
    );
  }
  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:items-start">
      <div className="grid min-w-0 gap-8">
        {facts}
        {abstract}
        {analyses}
        {runs}
      </div>
      <div className="min-w-0 lg:sticky lg:top-20">{pdf}</div>
    </div>
  );
}
