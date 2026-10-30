"use client";

import { ExternalLinkIcon, FileCheckIcon, FileXIcon, QuoteIcon } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import type { LibraryPaperOut, PaperOut } from "@/client";
import { authorNames } from "@/components/shared/format";
import { cn } from "@/lib/utils";

export type Decision = LibraryPaperOut["decisions"][number];

export const DECISION_TONES: Record<Decision, "success" | "warning" | "neutral"> = {
  include: "success",
  maybe: "warning",
  exclude: "neutral",
};

const DECISION_ORDER: Record<Decision, number> = { include: 0, maybe: 1, exclude: 2 };

/** The most favourable screening decision a paper got in any run (include, then maybe). */
export function bestDecision(decisions: readonly Decision[]): Decision | null {
  return [...decisions].sort((a, b) => DECISION_ORDER[a] - DECISION_ORDER[b])[0] ?? null;
}

/** "A. Author, B. Author, C. Author et al." in the UI language. */
export function useAuthorLine(): (authors: readonly string[]) => string {
  const t = useTranslations("shared.papers");
  return (authors) => {
    const { names, truncated } = authorNames(authors);
    if (!names) {
      return t("unknownAuthors");
    }
    return truncated ? t("etAl", { names }) : names;
  };
}

export function DecisionPill({ decision, className }: { decision: Decision; className?: string }) {
  const t = useTranslations("shared.papers.decisions");
  return (
    <span
      data-tone={DECISION_TONES[decision]}
      className={cn(
        "inline-flex h-5 w-fit shrink-0 items-center rounded-full border border-(--tone)/25 bg-(--tone)/12 px-2 text-xs font-medium whitespace-nowrap text-(--tone-fg)",
        className,
      )}
    >
      {t(decision)}
    </span>
  );
}

/** PDF availability as an icon with its spoken label. */
export function PdfMark({ available }: { available: boolean }) {
  const t = useTranslations("shared.papers");
  const Icon = available ? FileCheckIcon : FileXIcon;
  const label = available ? t("pdfAvailable") : t("pdfMissing");
  return (
    <span
      title={label}
      className={cn(
        "inline-flex items-center gap-1 text-xs",
        available ? "text-foreground" : "text-muted-foreground",
      )}
    >
      <Icon aria-hidden className="size-3.5" />
      <span className="sr-only">{label}</span>
    </span>
  );
}

/** Citations, when the source reported them. */
export function CitationCount({ count }: { count: number | null }) {
  const t = useTranslations("studioWork.papers");
  if (count === null) {
    return null;
  }
  return (
    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground tabular-nums">
      <QuoteIcon aria-hidden className="size-3" />
      {t("citations", { count })}
    </span>
  );
}

/** Relevance (0..1) as a small bar in the literature colour, with the figure. */
export function RelevanceBar({ value, className }: { value: number | null; className?: string }) {
  const t = useTranslations("studioWork.papers");
  const format = useFormatter();
  if (value === null) {
    return null;
  }
  const share = Math.min(1, Math.max(0, value));
  return (
    <span
      data-stage="literature"
      className={cn("inline-flex items-center gap-2 text-xs text-muted-foreground", className)}
    >
      <span aria-hidden className="h-1.5 w-14 overflow-hidden rounded-full bg-(--tone)/15">
        <span
          className="block h-full origin-left rounded-full bg-(--tone)"
          style={{ transform: `scaleX(${share})` }}
        />
      </span>
      <span className="tabular-nums">
        {t("relevance", {
          value: format.number(share, { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
        })}
      </span>
    </span>
  );
}

/** Links out to the paper's DOI, arXiv page and source URL (new tab, no referrer). */
export function PaperLinks({ paper }: { paper: PaperOut }) {
  const t = useTranslations("studioWork.papers.links");
  const links = [
    paper.doi ? { key: "doi", href: `https://doi.org/${paper.doi}`, label: t("doi") } : null,
    paper.arxiv_id
      ? { key: "arxiv", href: `https://arxiv.org/abs/${paper.arxiv_id}`, label: t("arxiv") }
      : null,
    paper.url && /^https?:\/\//i.test(paper.url)
      ? { key: "url", href: paper.url, label: t("source") }
      : null,
  ].filter((link): link is { key: string; href: string; label: string } => link !== null);
  if (links.length === 0) {
    return null;
  }
  return (
    <ul className="flex flex-wrap gap-2">
      {links.map((link) => (
        <li key={link.key}>
          <a
            href={link.href}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex h-8 items-center gap-1.5 rounded-[10px] border border-(--studio-glass-border) bg-(--studio-glass) px-3 text-xs font-medium text-foreground outline-none transition-colors hover:bg-(--studio-hover) focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            <ExternalLinkIcon aria-hidden className="size-3.5" />
            {link.label}
            <span className="sr-only">{t("newTab")}</span>
          </a>
        </li>
      ))}
    </ul>
  );
}
