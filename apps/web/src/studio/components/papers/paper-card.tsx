"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import type { CSSProperties } from "react";
import type { LibraryPaperOut } from "@/client";
import { DemoBadge } from "@/components/shared/demo-badge";
import { SpotlightCard } from "@/studio/components/effects/spotlight-card";
import { riseDelay } from "@/studio/lib/motion";
import { studioPaperPath } from "@/studio/lib/nav";
import {
  bestDecision,
  CitationCount,
  DecisionPill,
  PdfMark,
  RelevanceBar,
  useAuthorLine,
} from "./paper-meta";

/**
 * A library paper as a glass card with a cursor spotlight. The title is the link to the paper's
 * page (a short name for screen readers) and stretches over the card for pointer users; the
 * Demo badge stays pressable above it.
 */
export function PaperCard({ item, index }: { item: LibraryPaperOut; index: number }) {
  const t = useTranslations();
  const authorLine = useAuthorLine();
  const { paper } = item;
  const decision = bestDecision(item.decisions);

  return (
    <SpotlightCard
      spotlightColor="var(--aurora-cyan)"
      className="studio-rise group/paper flex h-full flex-col gap-3 p-4 sm:p-5"
      style={{ "--rise-delay": riseDelay(index) } as CSSProperties}
    >
      <p className="flex flex-wrap items-center gap-2 text-xs font-medium text-muted-foreground">
        <span data-stage="literature" className="text-(--tone-fg)">
          {t(`shared.papers.sources.${paper.source}`)}
        </span>
        <span aria-hidden>·</span>
        <span className="tabular-nums">{paper.year}</span>
        <span className="relative z-20 ml-auto">
          <DemoBadge demo={item.demo} />
        </span>
      </p>
      <h3 className="text-base leading-snug font-semibold tracking-tight text-foreground">
        <Link
          href={studioPaperPath(paper.paper_id)}
          className="line-clamp-3 rounded-sm [overflow-wrap:anywhere] outline-none after:absolute after:inset-0 after:z-10 after:rounded-2xl after:content-[''] focus-visible:after:ring-3 focus-visible:after:ring-ring/50"
        >
          {paper.title}
        </Link>
      </h3>
      <p className="line-clamp-2 text-sm text-muted-foreground">
        {authorLine(paper.authors)}
        {paper.venue && <> · {paper.venue}</>}
      </p>
      {paper.abstract && (
        <p className="line-clamp-3 text-xs leading-relaxed text-pretty text-muted-foreground">
          {paper.abstract}
        </p>
      )}
      <div className="mt-auto flex flex-wrap items-center gap-x-3 gap-y-2 pt-1">
        {decision && <DecisionPill decision={decision} />}
        <RelevanceBar value={item.best_relevance} />
        <CitationCount count={paper.citation_count} />
        <PdfMark available={paper.pdf_available} />
      </div>
      <p className="text-xs text-muted-foreground">
        {t("studioWork.papers.foundIn", { runs: item.run_count, projects: item.project_count })}
      </p>
    </SpotlightCard>
  );
}
