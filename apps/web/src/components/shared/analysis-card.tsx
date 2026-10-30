"use client";

import { FileSearchIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import type { EvidenceQuote, PaperAnalysis } from "@/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { authorNames } from "./format";
import type { PaperSummary } from "./paper-summary";

/** Reading notes on one paper: a run's `PaperAnalysis` or the library's `PaperAnalysisOut`. */
export type AnalysisSummary = Pick<
  PaperAnalysis,
  "contribution" | "method" | "results" | "limitations"
> & {
  evidence?: readonly EvidenceQuote[];
};

export type AnalysisCardProps = {
  analysis: AnalysisSummary;
  /** The analysed paper, for the title, authors and PDF availability. */
  paper?: PaperSummary;
  /** Opens the PDF at the quote; shown as "Open in PDF" on each quote. */
  onOpenInPdf?: (quote: EvidenceQuote, index: number) => void;
  /** Overrides `paper.pdf_available`. */
  pdfAvailable?: boolean;
  className?: string;
};

const SECTIONS = ["contribution", "method", "results", "limitations"] as const;

/** A paper analysis with its evidence quotes, each one a jump into the PDF. */
export function AnalysisCard({
  analysis,
  paper,
  onOpenInPdf,
  pdfAvailable,
  className,
}: AnalysisCardProps) {
  const t = useTranslations("shared.analysis");
  const tPapers = useTranslations("shared.papers");
  const evidence = analysis.evidence ?? [];
  const hasPdf = pdfAvailable ?? paper?.pdf_available ?? true;
  const authors = paper ? authorNames(paper.authors) : null;
  return (
    <Card data-slot="analysis-card" className={className}>
      {paper && (
        <CardHeader>
          <CardTitle className="break-words">
            <h3>{paper.title}</h3>
          </CardTitle>
          <CardDescription>
            {authors?.names
              ? authors.truncated
                ? tPapers("etAl", { names: authors.names })
                : authors.names
              : tPapers("unknownAuthors")}
            {" · "}
            {paper.venue ? `${paper.venue} ` : ""}
            {paper.year}
          </CardDescription>
        </CardHeader>
      )}
      <CardContent className="grid gap-4">
        <dl className="grid gap-3">
          {SECTIONS.map((section) => (
            <div key={section}>
              <dt className="text-xs font-medium text-muted-foreground">{t(section)}</dt>
              <dd className="break-words whitespace-pre-line">{analysis[section]}</dd>
            </div>
          ))}
        </dl>
        <section className="grid gap-2" aria-label={t("evidence")}>
          <p className="text-xs font-medium text-muted-foreground">{t("evidence")}</p>
          {evidence.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("noEvidence")}</p>
          ) : (
            <ol className="grid gap-2">
              {evidence.map((quote, index) => (
                <li
                  // Quotes have no id; the same quote may repeat on another page.
                  // biome-ignore lint/suspicious/noArrayIndexKey: the list never reorders
                  key={index}
                >
                  <figure
                    className="grid gap-1.5 rounded-lg border-l-2 border-(--tone) bg-muted/40 py-2 pr-2 pl-3"
                    data-stage="literature"
                  >
                    <blockquote className="break-words">“{quote.quote}”</blockquote>
                    <figcaption className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                      <span className="tabular-nums">{t("page", { page: quote.page })}</span>
                      {onOpenInPdf && (
                        <Button
                          type="button"
                          size="xs"
                          variant="outline"
                          disabled={!hasPdf}
                          onClick={() => onOpenInPdf(quote, index)}
                          aria-label={t("openQuoteInPdf", { index: index + 1, page: quote.page })}
                          title={hasPdf ? undefined : t("noPdf")}
                        >
                          <FileSearchIcon aria-hidden />
                          {t("openInPdf")}
                        </Button>
                      )}
                    </figcaption>
                  </figure>
                </li>
              ))}
            </ol>
          )}
          {!hasPdf && evidence.length > 0 && onOpenInPdf && (
            <p className={cn("text-xs text-muted-foreground")}>{t("noPdf")}</p>
          )}
        </section>
      </CardContent>
    </Card>
  );
}
