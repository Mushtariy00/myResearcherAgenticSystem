"use client";

import { ExternalLinkIcon, FileTextIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import type { LiteratureOutput, PaperFinding, PaperRef, ResearchPlan } from "@/client";
import { PapersTable } from "@/components/shared/papers-table";
import { Card, CardContent } from "@/components/ui/card";
import { ChipRadioGroup } from "../chip-radio-group";
import { PaperSheet, usePaperSheet } from "../paper-sheet";
import { externalUrl } from "../run-data";
import { Prose, TagList, ViewSection } from "./view-section";

const FILTERS = ["all", "include", "maybe", "exclude"] as const;
type Filter = (typeof FILTERS)[number];

function isFilter(value: string): value is Filter {
  return (FILTERS as readonly string[]).includes(value);
}

function PlanSection({ plan }: { plan: ResearchPlan }) {
  const t = useTranslations("run.literature");
  return (
    <ViewSection title={t("plan")}>
      <Card size="sm">
        <CardContent className="grid gap-4 @container">
          <div className="grid gap-1">
            <p className="text-xs font-medium text-muted-foreground">{t("scope")}</p>
            <p className="leading-relaxed break-words whitespace-pre-line">{plan.scope}</p>
          </div>
          <div className="grid gap-4 @2xl:grid-cols-2">
            <div className="grid content-start gap-1.5">
              <p className="text-xs font-medium text-muted-foreground">{t("queries")}</p>
              <ol className="grid list-decimal gap-1 pl-5">
                {plan.queries.map((query, index) => (
                  // biome-ignore lint/suspicious/noArrayIndexKey: queries are positional
                  <li key={index} className="font-mono text-xs break-words">
                    {query}
                  </li>
                ))}
              </ol>
            </div>
            <div className="grid content-start gap-1.5">
              <p className="text-xs font-medium text-muted-foreground">{t("criteria")}</p>
              <ul className="grid list-disc gap-1 pl-5">
                {plan.inclusion_criteria.map((criterion, index) => (
                  // biome-ignore lint/suspicious/noArrayIndexKey: criteria are positional
                  <li key={index} className="break-words">
                    {criterion}
                  </li>
                ))}
              </ul>
            </div>
          </div>
          <div className="grid gap-1.5">
            <p className="text-xs font-medium text-muted-foreground">{t("subtopics")}</p>
            <TagList items={plan.subtopics} empty={t("none")} />
          </div>
        </CardContent>
      </Card>
    </ViewSection>
  );
}

function Findings({
  findings,
  papers,
  onOpenPaper,
}: {
  findings: readonly PaperFinding[];
  papers: readonly PaperRef[];
  onOpenPaper: (paperId: string) => void;
}) {
  const t = useTranslations("run.literature");
  const known = useMemo(() => new Set(papers.map((paper) => paper.paper_id)), [papers]);
  return (
    <ViewSection title={t("findings")}>
      {findings.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("noFindings")}</p>
      ) : (
        <ul className="grid gap-3 md:grid-cols-2">
          {findings.map((finding, index) => {
            const paperId =
              finding.paper_id && known.has(finding.paper_id) ? finding.paper_id : null;
            const link = paperId ? null : externalUrl(finding.url);
            return (
              // biome-ignore lint/suspicious/noArrayIndexKey: findings have no id and never reorder
              <li key={index} className="grid content-start gap-1.5 rounded-xl border p-3">
                <p className="font-medium break-words">{finding.title}</p>
                <p className="text-xs text-muted-foreground">{finding.source}</p>
                <p className="leading-relaxed break-words whitespace-pre-line">{finding.summary}</p>
                {paperId && (
                  <button
                    type="button"
                    onClick={() => onOpenPaper(paperId)}
                    aria-label={t("openPaperNamed", { title: finding.title })}
                    className="inline-flex w-fit items-center gap-1 rounded-sm text-xs font-medium text-primary underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"
                  >
                    <FileTextIcon aria-hidden className="size-3.5" />
                    {t("openPaper")}
                  </button>
                )}
                {link && (
                  <a
                    href={link}
                    target="_blank"
                    rel="noopener noreferrer nofollow"
                    className="inline-flex w-fit items-center gap-1 rounded-sm text-xs font-medium text-primary underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"
                  >
                    <ExternalLinkIcon aria-hidden className="size-3.5" />
                    {t("openSource")}
                  </a>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </ViewSection>
  );
}

/**
 * A literature output: the research plan, the screened papers (filtered by decision; a paper
 * opens in a side sheet with its notes and PDF), the key findings and the synthesis.
 */
export function LiteratureView({ data }: { data: LiteratureOutput }) {
  const t = useTranslations("run.literature");
  const tDecisions = useTranslations("shared.papers.decisions");
  const [filter, setFilter] = useState<Filter>("all");
  const sheet = usePaperSheet();
  const counts = useMemo(
    () => ({
      all: data.papers.length,
      include: data.papers.filter((paper) => paper.decision === "include").length,
      maybe: data.papers.filter((paper) => paper.decision === "maybe").length,
      exclude: data.papers.filter((paper) => paper.decision === "exclude").length,
    }),
    [data.papers],
  );
  const shown = useMemo(
    () =>
      filter === "all" ? data.papers : data.papers.filter((paper) => paper.decision === filter),
    [data.papers, filter],
  );

  return (
    <div className="grid gap-6">
      <PlanSection plan={data.plan} />
      <ViewSection title={t("papers")}>
        <ChipRadioGroup
          label={t("filter")}
          value={filter}
          onValueChange={(value) => setFilter(isFilter(value) ? value : "all")}
          options={FILTERS.map((value) => {
            const name = value === "all" ? t("filterAll") : tDecisions(value);
            return {
              value,
              label: (
                <>
                  {name}
                  <span className="tabular-nums opacity-70">{counts[value]}</span>
                </>
              ),
              name: t("filterOption", { name, count: counts[value] }),
              muted: counts[value] === 0,
            };
          })}
        />
        <PapersTable
          papers={shown}
          selectedId={sheet.open ? sheet.paperId : null}
          onSelect={(paper) => sheet.show(paper.paper_id)}
          caption={t("papersCaption")}
          emptyMessage={data.papers.length === 0 ? t("noPapers") : t("noPapersForFilter")}
        />
      </ViewSection>
      <Findings findings={data.key_findings} papers={data.papers} onOpenPaper={sheet.show} />
      <ViewSection title={t("synthesis")}>
        {data.synthesis.trim() ? (
          <Prose text={data.synthesis} />
        ) : (
          <p className="text-sm text-muted-foreground">{t("noSynthesis")}</p>
        )}
      </ViewSection>
      <PaperSheet sheet={sheet} papers={data.papers} analyses={data.analyses} />
    </div>
  );
}
