"use client";

import { Tabs } from "@base-ui/react/tabs";
import { FlaskConicalIcon } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import type { ReactNode } from "react";
import { StageStatusBadge } from "@/components/app/status-badge";
import { StageIcon } from "@/components/shared/stage-icon";
import type { StageOverview, StageSummary } from "@/lib/stage-output";
import { useLabels } from "./use-labels";

/** The element id of a stage's tab, to move focus to it from elsewhere on the page. */
export function stageTabId(stage: string): string {
  return `stage-tab-${stage}`;
}

/** One line about a stage's newest output: papers kept, proposals, files, the headline metric. */
export function useSummaryText(): (summary: StageSummary | null) => string | null {
  const t = useTranslations("run.tabs");
  const tExperiment = useTranslations("run.experiment");
  const tMetric = useTranslations("shared.metric");
  const format = useFormatter();
  return (summary) => {
    if (!summary) {
      return null;
    }
    switch (summary.kind) {
      case "literature":
        return t("literature", { included: summary.papersIncluded, total: summary.papersTotal });
      case "method":
        return t("method", { count: summary.proposals });
      case "coding":
        return `${t("codingFiles", { count: summary.files })} · ${
          summary.smokeTestPassed ? t("smokePassed") : t("smokeFailed")
        }`;
      case "experiment":
        return summary.headline
          ? t("experimentMetric", {
              metric: summary.headline.name,
              value:
                summary.headline.value === null
                  ? tMetric("notMeasured")
                  : format.number(summary.headline.value, { maximumSignificantDigits: 3 }),
            })
          : tExperiment(`status.${summary.status}`);
      case "writing":
        return t("writing", { words: summary.words, citations: summary.citations });
      case "raw":
        return t("raw");
    }
  };
}

/**
 * The run's stages as tabs, each with its status, a one-line summary of its newest output and a
 * Demo mark for demo data. The selected stage's panel is the only one mounted.
 */
export function StageTabs({
  timeline,
  selected,
  onSelect,
  children,
}: {
  timeline: readonly StageOverview[];
  selected: string | undefined;
  onSelect: (stage: string) => void;
  /** The content of the selected stage's panel. */
  children: (entry: StageOverview) => ReactNode;
}) {
  const t = useTranslations("run.tabs");
  const tDemo = useTranslations("shared.demo");
  const labels = useLabels();
  const summaryText = useSummaryText();
  return (
    <Tabs.Root
      value={selected ?? null}
      onValueChange={(value) => onSelect(String(value))}
      className="grid gap-4"
    >
      <Tabs.List
        aria-label={t("label")}
        className="-mx-1 flex gap-2 overflow-x-auto px-1 pt-1 pb-2 sm:grid sm:grid-cols-5 sm:overflow-visible"
      >
        {timeline.map((entry) => {
          const summary = summaryText(entry.summary);
          return (
            <Tabs.Tab
              key={entry.stage}
              value={entry.stage}
              id={stageTabId(entry.stage)}
              className="flex min-w-40 flex-col items-start gap-1.5 rounded-xl border bg-card p-3 text-left outline-none hover:bg-muted/50 focus-visible:ring-3 focus-visible:ring-ring/50 data-active:border-primary data-active:ring-2 data-active:ring-primary/20 sm:min-w-0"
            >
              <span className="flex w-full min-w-0 items-center gap-2">
                <StageIcon stage={entry.stage} />
                <span className="truncate text-sm font-medium">{labels.stage(entry.stage)}</span>
                {entry.demo && (
                  <span
                    data-tone="warning"
                    className="ml-auto inline-flex h-5 shrink-0 items-center gap-1 rounded-full bg-(--tone)/15 px-1.5 text-[0.7rem] font-medium text-(--tone-fg)"
                  >
                    <FlaskConicalIcon aria-hidden className="size-3" />
                    {tDemo("badge")}
                  </span>
                )}
              </span>
              <StageStatusBadge status={entry.status} />
              <span className="line-clamp-2 text-xs text-muted-foreground">
                {summary ?? (entry.attempts > 0 ? t("noOutputYet") : t("notReached"))}
              </span>
            </Tabs.Tab>
          );
        })}
      </Tabs.List>
      {timeline.map((entry) => (
        <Tabs.Panel
          key={entry.stage}
          value={entry.stage}
          className="rounded-xl outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          {entry.stage === selected ? children(entry) : null}
        </Tabs.Panel>
      ))}
    </Tabs.Root>
  );
}
