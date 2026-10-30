"use client";

import {
  BookMarkedIcon,
  CheckIcon,
  ExternalLinkIcon,
  FileCheckIcon,
  FileSearchIcon,
  LightbulbIcon,
  ListChecksIcon,
  SearchIcon,
  SparklesIcon,
} from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { type ReactNode, useDeferredValue, useId, useMemo, useState } from "react";
import type { LiteratureOutput, PaperRef, ResearchPlan } from "@/client";
import { PapersTable } from "@/components/shared/papers-table";
import { cn } from "@/lib/utils";
import { NumberTicker } from "@/studio/components/effects/number-ticker";
import type { Tone } from "@/studio/lib/stages";
import { useRunPage } from "./run-context";
import { externalHref } from "./run-helpers";
import { Chip, LINK_BUTTON, TOGGLE_BUTTON, ViewCard } from "./run-ui";

type DecisionFilter = "all" | PaperRef["decision"];

const DECISION_FILTERS: readonly DecisionFilter[] = ["all", "include", "maybe", "exclude"];

/**
 * The literature output: screening numbers, the search plan, the papers with filters (a row
 * opens the paper sheet with its reading notes and PDF), the key findings and the synthesis.
 */
export function LiteratureView({ data }: { data: LiteratureOutput }) {
  return (
    <div className="grid min-w-0 gap-4">
      <LiteratureStats data={data} />
      <PlanCard plan={data.plan} />
      <PapersCard data={data} />
      <div className="grid gap-4 xl:grid-cols-2">
        <FindingsCard data={data} />
        <SynthesisCard synthesis={data.synthesis} />
      </div>
    </div>
  );
}

function LiteratureStats({ data }: { data: LiteratureOutput }) {
  const t = useTranslations("studioRun.literature.stats");
  const tiles = useMemo(() => {
    const decided = (decision: PaperRef["decision"]) =>
      data.papers.filter((paper) => paper.decision === decision).length;
    const items: {
      key: "screened" | "included" | "maybe" | "excluded" | "analysed";
      value: number;
      tone?: Tone;
    }[] = [
      { key: "screened", value: data.papers.length },
      { key: "included", value: decided("include"), tone: "success" },
      { key: "maybe", value: decided("maybe"), tone: "warning" },
      { key: "excluded", value: decided("exclude"), tone: "neutral" },
      { key: "analysed", value: data.analyses?.length ?? 0 },
    ];
    return items;
  }, [data]);
  return (
    <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
      {tiles.map((tile) => (
        <div
          key={tile.key}
          data-tone={tile.tone}
          className="studio-glass grid min-w-0 gap-1 rounded-2xl p-3 sm:p-4"
        >
          <dt className="flex min-w-0 items-center gap-1.5 text-xs text-muted-foreground">
            {tile.tone && (
              <span aria-hidden className="size-1.5 shrink-0 rounded-full bg-(--tone)" />
            )}
            <span className="truncate">{t(tile.key)}</span>
          </dt>
          <dd className="font-mono text-2xl font-semibold tracking-tight text-foreground">
            <NumberTicker value={tile.value} />
          </dd>
        </div>
      ))}
    </dl>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid min-w-0 content-start gap-2">
      <h5 className="text-[0.7rem] font-semibold tracking-[0.08em] text-muted-foreground uppercase">
        {label}
      </h5>
      {children}
    </div>
  );
}

function PlanCard({ plan }: { plan: ResearchPlan }) {
  const t = useTranslations("studioRun.literature");
  return (
    <ViewCard title={t("plan")} icon={<ListChecksIcon aria-hidden />} description={plan.topic}>
      <div className="grid gap-5 lg:grid-cols-2">
        <div className="grid content-start gap-5">
          <Field label={t("scope")}>
            <p className="text-sm leading-6 whitespace-pre-line text-foreground">{plan.scope}</p>
          </Field>
          <Field label={t("criteria")}>
            <ul className="grid gap-1.5 text-sm text-foreground">
              {plan.inclusion_criteria.map((criterion, index) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: generated text may repeat; the list never reorders
                <li key={index} className="flex gap-2">
                  <CheckIcon aria-hidden className="mt-1 size-3.5 shrink-0 text-(--tone-fg)" />
                  <span className="min-w-0 break-words">{criterion}</span>
                </li>
              ))}
            </ul>
          </Field>
        </div>
        <div className="grid content-start gap-5">
          <Field label={t("queries")}>
            <ul className="flex flex-wrap gap-1.5">
              {plan.queries.map((query, index) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: generated text may repeat; the list never reorders
                <li key={index} className="max-w-full">
                  <Chip stage="literature" mono>
                    {query}
                  </Chip>
                </li>
              ))}
            </ul>
          </Field>
          <Field label={t("subtopics")}>
            <ul className="flex flex-wrap gap-1.5">
              {plan.subtopics.map((subtopic, index) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: generated text may repeat; the list never reorders
                <li key={index} className="max-w-full">
                  <Chip>{subtopic}</Chip>
                </li>
              ))}
            </ul>
          </Field>
        </div>
      </div>
    </ViewCard>
  );
}

function PapersCard({ data }: { data: LiteratureOutput }) {
  const t = useTranslations("studioRun.literature");
  const tDecisions = useTranslations("shared.papers.decisions");
  const format = useFormatter();
  const { openPaper, openPaperId } = useRunPage();
  const searchId = useId();
  const [decision, setDecision] = useState<DecisionFilter>("all");
  const [query, setQuery] = useState("");
  const [pdfOnly, setPdfOnly] = useState(false);
  const needle = useDeferredValue(query).trim().toLocaleLowerCase();

  const counts = useMemo(() => {
    const result: Record<DecisionFilter, number> = {
      all: data.papers.length,
      include: 0,
      maybe: 0,
      exclude: 0,
    };
    for (const paper of data.papers) {
      result[paper.decision] += 1;
    }
    return result;
  }, [data.papers]);

  const papers = useMemo(
    () =>
      data.papers.filter(
        (paper) =>
          (decision === "all" || paper.decision === decision) &&
          (!pdfOnly || paper.pdf_available) &&
          (needle === "" ||
            [paper.title, paper.venue ?? "", String(paper.year), ...paper.authors].some((field) =>
              field.toLocaleLowerCase().includes(needle),
            )),
      ),
    [data.papers, decision, pdfOnly, needle],
  );
  const filtered = decision !== "all" || pdfOnly || needle !== "";

  return (
    <ViewCard
      title={t("papers")}
      icon={<BookMarkedIcon aria-hidden />}
      action={
        filtered && (
          <button
            type="button"
            className={cn(LINK_BUTTON, "text-xs")}
            onClick={() => {
              setDecision("all");
              setPdfOnly(false);
              setQuery("");
            }}
          >
            {t("filter.clear")}
          </button>
        )
      }
    >
      <div className="grid min-w-0 gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <fieldset className="flex min-w-0 flex-wrap gap-1">
            <legend className="sr-only">{t("filter.decision")}</legend>
            {DECISION_FILTERS.map((value) => (
              <button
                key={value}
                type="button"
                aria-pressed={decision === value}
                onClick={() => setDecision(value)}
                className={TOGGLE_BUTTON}
              >
                {value === "all" ? t("filter.all") : tDecisions(value)}
                <span className="text-muted-foreground tabular-nums">
                  {format.number(counts[value])}
                </span>
              </button>
            ))}
          </fieldset>
          <button
            type="button"
            aria-pressed={pdfOnly}
            onClick={() => setPdfOnly((value) => !value)}
            className={TOGGLE_BUTTON}
          >
            <FileCheckIcon aria-hidden />
            {t("filter.pdfOnly")}
          </button>
          <div className="relative min-w-0 flex-1 basis-48">
            <label htmlFor={searchId} className="sr-only">
              {t("filter.search")}
            </label>
            <SearchIcon
              aria-hidden
              className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground"
            />
            <input
              id={searchId}
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t("filter.searchPlaceholder")}
              autoComplete="off"
              className="h-8 w-full min-w-0 rounded-[10px] border border-(--studio-glass-border) bg-(--studio-glass) pr-2 pl-8 text-sm text-foreground outline-none placeholder:text-muted-foreground focus-visible:ring-3 focus-visible:ring-ring/50"
            />
          </div>
        </div>
        <p aria-live="polite" className="text-xs text-muted-foreground tabular-nums">
          {t("filter.count", { shown: papers.length, total: data.papers.length })}
        </p>
        <div className="min-w-0 overflow-hidden rounded-xl border border-(--studio-glass-border)">
          <PapersTable
            papers={papers}
            selectedId={openPaperId}
            onSelect={(paper) => openPaper({ paperId: paper.paper_id, literature: data })}
            caption={t("papers")}
            emptyMessage={t("filter.empty")}
          />
        </div>
      </div>
    </ViewCard>
  );
}

function FindingsCard({ data }: { data: LiteratureOutput }) {
  const t = useTranslations("studioRun.literature");
  const { openPaper } = useRunPage();
  const known = useMemo(() => new Set(data.papers.map((paper) => paper.paper_id)), [data.papers]);
  return (
    <ViewCard title={t("findings")} icon={<LightbulbIcon aria-hidden />}>
      {data.key_findings.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("noFindings")}</p>
      ) : (
        <ol className="grid gap-3">
          {data.key_findings.map((finding, index) => {
            const href = externalHref(finding.url);
            const paperId =
              finding.paper_id && known.has(finding.paper_id) ? finding.paper_id : null;
            return (
              <li
                // biome-ignore lint/suspicious/noArrayIndexKey: findings have no id; the list never reorders
                key={index}
                className="grid min-w-0 gap-1.5 rounded-xl border border-(--studio-glass-border) bg-(--studio-glass) p-3"
              >
                <p className="text-sm font-medium break-words text-foreground">{finding.title}</p>
                <p className="text-sm leading-6 break-words text-muted-foreground">
                  {finding.summary}
                </p>
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                  <span className="text-xs text-muted-foreground">
                    {t("source", { source: finding.source })}
                  </span>
                  {paperId && (
                    <button
                      type="button"
                      aria-haspopup="dialog"
                      onClick={() => openPaper({ paperId, literature: data })}
                      className={cn(LINK_BUTTON, "text-xs")}
                    >
                      <FileSearchIcon aria-hidden />
                      {t("openPaper")}
                    </button>
                  )}
                  {href && (
                    <a
                      href={href}
                      target="_blank"
                      rel="noopener noreferrer nofollow"
                      className={cn(LINK_BUTTON, "text-xs")}
                    >
                      <ExternalLinkIcon aria-hidden />
                      {t("openSource")}
                      <span className="sr-only"> ({t("newTab")})</span>
                    </a>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </ViewCard>
  );
}

function SynthesisCard({ synthesis }: { synthesis: string }) {
  const t = useTranslations("studioRun.literature");
  const paragraphs = synthesis
    .split(/\n{2,}/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);
  return (
    <ViewCard title={t("synthesis")} icon={<SparklesIcon aria-hidden />}>
      <div className="grid gap-3 text-sm leading-7 text-foreground">
        {paragraphs.map((paragraph, index) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: paragraphs are positional
          <p key={index} className="break-words whitespace-pre-line">
            {paragraph}
          </p>
        ))}
      </div>
    </ViewCard>
  );
}
