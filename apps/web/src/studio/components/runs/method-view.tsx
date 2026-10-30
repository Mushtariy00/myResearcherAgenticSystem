"use client";

import { CrosshairIcon, DatabaseIcon, GaugeIcon, SearchXIcon, StarIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useId } from "react";
import type { MethodOutput } from "@/client";
import { ProposalCard } from "@/components/shared/proposal-card";
import { cn } from "@/lib/utils";
import { BorderBeam } from "@/studio/components/effects/border-beam";
import { useRunPage } from "./run-context";
import { Callout, Chip, ViewCard } from "./run-ui";

/** Whether `name` is the method stage's recommended option (whitespace and case aside). */
function isRecommended(name: string, recommended: string): boolean {
  return name.trim().toLocaleLowerCase() === recommended.trim().toLocaleLowerCase();
}

/**
 * The method output: research gaps, the implementation focus with datasets and metrics, and the
 * proposals as cards; the recommended one carries a border beam. A proposal's supporting papers
 * open the paper sheet.
 */
export function MethodView({ data }: { data: MethodOutput }) {
  const t = useTranslations("studioRun.method");
  const { literature, openPaper } = useRunPage();
  const proposalsId = useId();
  const papers = literature?.papers;
  const matched = data.proposals.some((proposal) =>
    isRecommended(proposal.name, data.recommended_option),
  );

  return (
    <div className="grid min-w-0 gap-4">
      <div className="grid gap-4 lg:grid-cols-2">
        <ViewCard title={t("gaps")} icon={<SearchXIcon aria-hidden />}>
          <ol className="grid gap-2">
            {data.research_gaps.map((gap, index) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: generated text may repeat; the list never reorders
              <li key={index} className="flex gap-3 text-sm text-foreground">
                <span
                  aria-hidden
                  className="flex size-5 shrink-0 items-center justify-center rounded-md border border-(--tone)/30 bg-(--tone)/12 font-mono text-[0.65rem] font-semibold text-(--tone-fg) tabular-nums"
                >
                  {index + 1}
                </span>
                <span className="min-w-0 break-words">{gap}</span>
              </li>
            ))}
          </ol>
        </ViewCard>
        <ViewCard title={t("focus")} icon={<CrosshairIcon aria-hidden />}>
          <div className="grid gap-4">
            <p className="text-sm leading-6 break-words whitespace-pre-line text-foreground">
              {data.implementation_focus}
            </p>
            <dl className="grid gap-3 sm:grid-cols-2">
              <div className="grid content-start gap-1.5">
                <dt className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <DatabaseIcon aria-hidden className="size-3.5" />
                  {t("datasets")}
                </dt>
                <dd className="flex flex-wrap gap-1.5">
                  {data.datasets.map((dataset) => (
                    <Chip key={dataset} stage="method" mono>
                      {dataset}
                    </Chip>
                  ))}
                </dd>
              </div>
              <div className="grid content-start gap-1.5">
                <dt className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <GaugeIcon aria-hidden className="size-3.5" />
                  {t("metrics")}
                </dt>
                <dd className="flex flex-wrap gap-1.5">
                  {data.evaluation_metrics.map((metric) => (
                    <Chip key={metric} stage="method" mono>
                      {metric}
                    </Chip>
                  ))}
                </dd>
              </div>
            </dl>
          </div>
        </ViewCard>
      </div>

      {!matched && data.recommended_option && (
        <Callout tone="info" icon={StarIcon} title={t("recommended")}>
          {data.recommended_option}
        </Callout>
      )}

      <section aria-labelledby={proposalsId} className="grid min-w-0 gap-3">
        <h4
          id={proposalsId}
          className="flex items-center gap-2 text-sm font-semibold tracking-tight text-foreground"
        >
          {t("proposals")}
          <span className="font-normal text-muted-foreground tabular-nums">
            {data.proposals.length}
          </span>
        </h4>
        <ul className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
          {data.proposals.map((proposal, index) => {
            const recommended = isRecommended(proposal.name, data.recommended_option);
            return (
              <li
                // biome-ignore lint/suspicious/noArrayIndexKey: proposal names may repeat; the list never reorders
                key={index}
                data-recommended={recommended || undefined}
                className={cn(
                  "relative min-w-0 rounded-xl",
                  recommended && "md:col-span-2 2xl:col-span-1",
                )}
              >
                <ProposalCard
                  proposal={proposal}
                  recommended={recommended}
                  papers={papers}
                  onOpenPaper={(paperId) => openPaper({ paperId })}
                  className="h-full bg-(--studio-glass-strong)"
                />
                {recommended && (
                  <BorderBeam
                    colorFrom="var(--stage-method)"
                    colorTo="var(--aurora-cyan)"
                    duration={6}
                    width={2}
                  />
                )}
              </li>
            );
          })}
        </ul>
      </section>
    </div>
  );
}
