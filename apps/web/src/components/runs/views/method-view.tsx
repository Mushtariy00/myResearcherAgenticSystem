"use client";

import { StarIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import type { LiteratureOutput, MethodOutput } from "@/client";
import { ProposalCard } from "@/components/shared/proposal-card";
import { PaperSheet, usePaperSheet } from "../paper-sheet";
import { Prose, TagList, ViewSection } from "./view-section";

/** Compares proposal names the way a reader would (case and spacing do not matter). */
function sameName(a: string, b: string): boolean {
  const normalize = (value: string) => value.trim().replace(/\s+/g, " ").toLowerCase();
  return normalize(a) === normalize(b);
}

/**
 * A method output: the research gaps, the candidate methods (the recommended one highlighted;
 * their supporting papers open in the paper sheet), the implementation focus, and the datasets
 * and metrics the experiment will use.
 */
export function MethodView({
  data,
  literature,
}: {
  data: MethodOutput;
  /** The literature output the proposals cite, to name and open their papers. */
  literature: LiteratureOutput | null;
}) {
  const t = useTranslations("run.method");
  const sheet = usePaperSheet();
  const papers = literature?.papers ?? [];
  return (
    <div className="grid gap-6">
      <ViewSection title={t("gaps")}>
        {data.research_gaps.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("none")}</p>
        ) : (
          <ul className="grid list-disc gap-1 pl-5">
            {data.research_gaps.map((gap, index) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: gaps are positional
              <li key={index} className="break-words">
                {gap}
              </li>
            ))}
          </ul>
        )}
      </ViewSection>
      <ViewSection title={t("proposals")}>
        <p className="flex items-start gap-1.5 text-sm">
          <StarIcon aria-hidden className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
          <span>
            <span className="font-medium">{t("recommended")}</span>{" "}
            <span className="break-words">{data.recommended_option}</span>
          </span>
        </p>
        {data.proposals.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("noProposals")}</p>
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            {data.proposals.map((proposal, index) => (
              <ProposalCard
                // Names usually differ, but generated output may repeat one.
                // biome-ignore lint/suspicious/noArrayIndexKey: proposals never reorder
                key={index}
                proposal={proposal}
                recommended={sameName(proposal.name, data.recommended_option)}
                papers={papers}
                onOpenPaper={literature ? sheet.show : undefined}
              />
            ))}
          </div>
        )}
      </ViewSection>
      <ViewSection title={t("focus")}>
        <Prose text={data.implementation_focus} />
      </ViewSection>
      <div className="grid gap-6 sm:grid-cols-2">
        <ViewSection title={t("datasets")}>
          <TagList items={data.datasets} empty={t("none")} />
        </ViewSection>
        <ViewSection title={t("metrics")}>
          <TagList items={data.evaluation_metrics} empty={t("none")} />
        </ViewSection>
      </div>
      <PaperSheet sheet={sheet} papers={papers} analyses={literature?.analyses} />
    </div>
  );
}
