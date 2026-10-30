"use client";

import { Radio } from "@base-ui/react/radio";
import { RadioGroup } from "@base-ui/react/radio-group";
import { useFormatter, useTranslations } from "next-intl";
import { type CSSProperties, useId } from "react";
import type { Stage } from "@/client";
import { isStage } from "@/lib/new-run-schema";
import { STAGE_ORDER } from "@/lib/timeline";
import { cn } from "@/lib/utils";
import { STAGE_ICONS } from "@/studio/lib/stages";

/**
 * "Stop after": the five pipeline stages drawn as a mini pipeline graph, where choosing a stage
 * runs the pipeline up to and including it (runs always start with literature and follow the
 * pipeline order). Stages that will run keep their colour and the beams between them fill;
 * later ones step back, dashed and neutral, with their names at full contrast. A radio group:
 * arrow keys move between stages, and the summary below says what runs and what does not.
 */
export function StagePrefixChooser({
  value,
  onChange,
  labelledBy,
  describedBy,
  invalid = false,
}: {
  /** The last stage the run goes through; null while the stages are not a valid prefix. */
  value: Stage | null;
  onChange: (stage: Stage) => void;
  labelledBy: string;
  describedBy?: string;
  invalid?: boolean;
}) {
  const t = useTranslations();
  const format = useFormatter();
  const ids = useId();
  const last = value ? STAGE_ORDER.indexOf(value) : -1;
  const skipped = STAGE_ORDER.slice(last + 1).map((stage) => t(`stages.${stage}`));
  const summaryId = `${ids}-summary`;

  return (
    <div className="grid gap-3">
      <RadioGroup
        value={value ?? ""}
        onValueChange={(next) => {
          if (isStage(next)) {
            onChange(next);
          }
        }}
        aria-labelledby={labelledBy}
        aria-describedby={[summaryId, describedBy].filter(Boolean).join(" ")}
        aria-invalid={invalid || undefined}
        className="studio-glass grid grid-cols-5 rounded-2xl px-1 py-4 sm:px-3"
      >
        {STAGE_ORDER.map((stage, index) => {
          const included = index <= last;
          const Icon = STAGE_ICONS[stage];
          const next = STAGE_ORDER[index + 1];
          const labelId = `${ids}-${stage}`;
          return (
            <div
              key={stage}
              data-stage={included ? stage : undefined}
              data-tone={included ? undefined : "neutral"}
              data-included={included ? "true" : "false"}
              className="relative flex min-w-0 flex-col items-center"
            >
              {next && (
                <span
                  aria-hidden
                  className={cn(
                    "absolute top-5 left-[calc(50%+1.5rem)] h-0.5 w-[calc(100%-3rem)] -translate-y-1/2 rounded-full",
                    index < last
                      ? "bg-linear-to-r from-(--from) to-(--to)"
                      : "bg-[color-mix(in_oklch,var(--foreground)_14%,transparent)]",
                  )}
                  style={
                    {
                      "--from": `color-mix(in oklch, var(--stage-${stage}) 75%, transparent)`,
                      "--to": `color-mix(in oklch, var(--stage-${next}) 75%, transparent)`,
                    } as CSSProperties
                  }
                />
              )}
              {/* biome-ignore lint/a11y/noLabelWithoutControl: Base UI's Radio renders its input in the label */}
              <label className="group/stage flex min-w-0 cursor-pointer flex-col items-center gap-2 px-0.5 text-center">
                <Radio.Root
                  value={stage}
                  aria-labelledby={labelId}
                  className={cn(
                    "relative flex size-10 items-center justify-center rounded-full border-2 text-(--tone-fg) outline-none transition-[transform,box-shadow] duration-200 focus-visible:ring-3 focus-visible:ring-ring/60 motion-reduce:transition-none",
                    included
                      ? "border-(--tone) bg-(--tone)/14"
                      : "border-dashed border-(--tone)/60 bg-transparent",
                    "group-hover/stage:scale-105 motion-reduce:group-hover/stage:scale-100",
                    "data-checked:shadow-[0_0_0_4px_color-mix(in_oklch,var(--tone)_28%,transparent)]",
                  )}
                >
                  <Icon aria-hidden className="size-4.5" />
                </Radio.Root>
                {/* One line: at 360px a long name ("Experiment") reaches a few pixels past its
                    column, which the short names beside it leave free. */}
                <span
                  id={labelId}
                  className={cn(
                    "text-[0.68rem] leading-tight font-medium whitespace-nowrap sm:text-xs",
                    included ? "text-foreground" : "text-muted-foreground",
                  )}
                >
                  {t(`stages.${stage}`)}
                </span>
              </label>
            </div>
          );
        })}
      </RadioGroup>
      <p id={summaryId} className="text-sm text-pretty text-muted-foreground">
        {value
          ? t("studioWork.wizard.stages.summary", { stage: t(`stages.${value}`) })
          : t("studioWork.wizard.stages.choose")}
        {value && skipped.length > 0 && (
          <>
            {" "}
            {t("studioWork.wizard.stages.skipped", {
              stages: format.list(skipped, { type: "conjunction" }),
            })}
          </>
        )}
      </p>
    </div>
  );
}
