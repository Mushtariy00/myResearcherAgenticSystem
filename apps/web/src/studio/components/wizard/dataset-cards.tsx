"use client";

import { Radio } from "@base-ui/react/radio";
import { RadioGroup } from "@base-ui/react/radio-group";
import { DatabaseIcon } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useId } from "react";
import { DemoBadge } from "@/components/shared/demo-badge";
import { formatBytes } from "@/components/shared/format";
import { useDatasets } from "@/hooks/use-datasets";
import { cn } from "@/lib/utils";
import { StudioInlineError } from "@/studio/components/dashboard/studio-panel";
import { LoadingStatus, ShimmerSkeleton } from "@/studio/components/effects/shimmer-skeleton";

const CARD =
  "relative flex cursor-pointer items-start gap-3 rounded-xl border border-(--studio-glass-border) bg-(--studio-glass) p-3 transition-colors hover:bg-(--studio-hover) has-[[data-checked]]:border-(--tone) has-[[data-checked]]:bg-(--tone)/10 has-[:focus-visible]:ring-3 has-[:focus-visible]:ring-ring/50";

const RADIO =
  "mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border-2 border-[color-mix(in_oklch,var(--foreground)_30%,transparent)] outline-none data-checked:border-(--tone)";

/** The radio value of "No dataset" (the form holds "" for it). */
const NONE = "none";

/**
 * The datasets an experiment can mount (useDatasets), as radio cards with what each holds:
 * tasks, modality, samples and size. "No dataset" is a choice too. The registry's Demo badge
 * sits next to the legend.
 */
export function DatasetCards({
  value,
  onChange,
  legendId,
  describedBy,
  experimentIncluded,
}: {
  /** A dataset id, or "" for none. */
  value: string;
  onChange: (value: string) => void;
  legendId: string;
  describedBy?: string;
  /** Whether the run reaches the experiment stage, the one that mounts the dataset. */
  experimentIncluded: boolean;
}) {
  const t = useTranslations("studioWork.wizard.dataset");
  const tCommon = useTranslations("common");
  const format = useFormatter();
  const ids = useId();
  const query = useDatasets();

  if (query.isPending) {
    return (
      <div className="grid gap-3 sm:grid-cols-2" aria-busy="true">
        <LoadingStatus label={tCommon("loading")} />
        <ShimmerSkeleton className="h-24 rounded-xl" />
        <ShimmerSkeleton className="h-24 rounded-xl" />
      </div>
    );
  }
  if (query.isError) {
    return <StudioInlineError error={query.error} onRetry={() => query.refetch()} />;
  }

  const items = query.data.items;
  return (
    <div className="grid gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <DemoBadge demo={query.data.demo} />
        {!experimentIncluded && <p className="text-xs text-muted-foreground">{t("notUsed")}</p>}
      </div>
      <RadioGroup
        value={value === "" ? NONE : value}
        onValueChange={(next) => {
          if (typeof next === "string") {
            onChange(next === NONE ? "" : next);
          }
        }}
        aria-labelledby={legendId}
        aria-describedby={describedBy}
        className="grid gap-3 sm:grid-cols-2"
      >
        {items.map((dataset) => {
          const nameId = `${ids}-${dataset.id}-name`;
          const metaId = `${ids}-${dataset.id}-meta`;
          return (
            // biome-ignore lint/a11y/noLabelWithoutControl: Base UI's Radio renders its input in the label
            <label key={dataset.id} data-stage="experiment" className={CARD}>
              <Radio.Root
                value={dataset.id}
                aria-labelledby={nameId}
                aria-describedby={metaId}
                className={RADIO}
              >
                <Radio.Indicator className="size-2.5 rounded-full bg-(--tone)" />
              </Radio.Root>
              <span className="grid min-w-0 gap-1">
                <span id={nameId} className="flex flex-wrap items-baseline gap-x-2 text-sm">
                  <span className="font-semibold text-foreground">{dataset.name}</span>
                  <span className="font-mono text-xs text-muted-foreground">
                    {t("version", { version: dataset.version })}
                  </span>
                </span>
                <span id={metaId} className="text-xs text-muted-foreground">
                  {[
                    dataset.tasks.join(", "),
                    dataset.modality,
                    t("samples", { count: dataset.samples }),
                    formatBytes(dataset.size_bytes, format),
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
                {dataset.description && (
                  <span className="line-clamp-2 text-xs text-pretty text-muted-foreground">
                    {dataset.description}
                  </span>
                )}
              </span>
            </label>
          );
        })}
        {/* biome-ignore lint/a11y/noLabelWithoutControl: Base UI's Radio renders its input in the label */}
        <label data-tone="neutral" className={cn(CARD, "items-center")}>
          <Radio.Root value={NONE} aria-labelledby={`${ids}-none`} className={RADIO}>
            <Radio.Indicator className="size-2.5 rounded-full bg-(--tone)" />
          </Radio.Root>
          <span id={`${ids}-none`} className="flex items-center gap-2 text-sm text-foreground">
            <DatabaseIcon aria-hidden className="size-4 text-muted-foreground" />
            {t("none")}
          </span>
        </label>
      </RadioGroup>
    </div>
  );
}
