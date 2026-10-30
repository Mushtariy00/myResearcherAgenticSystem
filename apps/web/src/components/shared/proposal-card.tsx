"use client";

import { FileTextIcon, StarIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useMemo } from "react";
import type { MethodProposal } from "@/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { indexPapers, type PaperSummary } from "./paper-summary";

export type ProposalCardProps = {
  proposal: MethodProposal;
  /** The method stage's recommended option (compare `MethodOutput.recommended_option`). */
  recommended?: boolean;
  /** Papers that `evidence_paper_ids` may refer to, to show their titles. */
  papers?: readonly PaperSummary[];
  /** Makes each supporting paper a button. */
  onOpenPaper?: (paperId: string) => void;
  className?: string;
};

/** One candidate method: why, the expected benefit, the risk, and the papers behind it. */
export function ProposalCard({
  proposal,
  recommended = false,
  papers,
  onOpenPaper,
  className,
}: ProposalCardProps) {
  const t = useTranslations("shared.proposal");
  const byId = useMemo(() => indexPapers(papers), [papers]);
  const evidence = proposal.evidence_paper_ids ?? [];
  return (
    <Card
      data-slot="proposal-card"
      data-recommended={recommended || undefined}
      className={cn(recommended && "ring-2 ring-(--tone)/50", className)}
      data-tone={recommended ? "success" : undefined}
    >
      <CardHeader className="flex flex-wrap items-start justify-between gap-2">
        <CardTitle className="min-w-0 text-base break-words">
          <h3>{proposal.name}</h3>
        </CardTitle>
        {recommended && (
          <span className="inline-flex h-5 shrink-0 items-center gap-1 rounded-full bg-(--tone)/15 px-2 text-xs font-medium text-(--tone-fg)">
            <StarIcon aria-hidden className="size-3" />
            {t("recommended")}
          </span>
        )}
      </CardHeader>
      <CardContent className="grid gap-3">
        <dl className="grid gap-3">
          <div>
            <dt className="text-xs font-medium text-muted-foreground">{t("rationale")}</dt>
            <dd className="break-words whitespace-pre-line">{proposal.rationale}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium text-muted-foreground">{t("benefit")}</dt>
            <dd className="break-words whitespace-pre-line">{proposal.expected_benefit}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium text-muted-foreground">{t("risk")}</dt>
            <dd className="break-words whitespace-pre-line">{proposal.risk}</dd>
          </div>
        </dl>
        {evidence.length > 0 && (
          <div className="grid gap-1.5">
            <p className="text-xs font-medium text-muted-foreground">{t("evidence")}</p>
            <ul className="grid gap-1">
              {evidence.map((paperId) => {
                const paper = byId.get(paperId);
                const title = paper?.title ?? t("unknownPaper", { id: paperId });
                const content = (
                  <>
                    <FileTextIcon aria-hidden className="mt-0.5 size-3.5 shrink-0" />
                    <span className="min-w-0 break-words">
                      {title}
                      {paper && <span className="text-muted-foreground"> ({paper.year})</span>}
                    </span>
                  </>
                );
                return (
                  <li key={paperId}>
                    {onOpenPaper ? (
                      <button
                        type="button"
                        onClick={() => onOpenPaper(paperId)}
                        className="flex w-full items-start gap-1.5 rounded-md text-left text-sm underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"
                      >
                        {content}
                      </button>
                    ) : (
                      <span className="flex items-start gap-1.5 text-sm">{content}</span>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
