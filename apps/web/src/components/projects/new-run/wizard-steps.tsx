"use client";

import { Checkbox } from "@base-ui/react/checkbox";
import { CheckboxGroup } from "@base-ui/react/checkbox-group";
import { CheckIcon } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useId } from "react";
import { Controller, type UseFormReturn, useWatch } from "react-hook-form";
import type { DatasetOut, LlmPolicy, Stage } from "@/client";
import { QueryError } from "@/components/app/query-state";
import { DemoBadge } from "@/components/shared/demo-badge";
import { formatBytes } from "@/components/shared/format";
import { StageIcon } from "@/components/shared/stage-icon";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useDatasets } from "@/hooks/use-datasets";
import {
  isStage,
  LLM_POLICIES,
  lastStageOf,
  NEW_RUN_LIMITS,
  type NewRunFormInput,
  type NewRunValues,
  SEARCH_SOURCES,
} from "@/lib/new-run-schema";
import { STAGE_ORDER } from "@/lib/timeline";
import { cn } from "@/lib/utils";
import { describedBy, FieldError } from "./field-error";

export type NewRunFormApi = UseFormReturn<NewRunFormInput, unknown, NewRunValues>;

/** The dataset select's value for "no dataset" (the form holds ""). */
const NO_DATASET = "none";

const OPTION_CLASS =
  "flex cursor-pointer items-start gap-3 rounded-lg border p-3 font-normal leading-normal has-data-checked:border-primary has-data-checked:bg-muted/50 has-data-disabled:cursor-not-allowed has-data-disabled:opacity-60";

export function TopicStep({ form }: { form: NewRunFormApi }) {
  const t = useTranslations("wizard.topic");
  const ids = useId();
  const error = form.formState.errors.topic;
  const topic = useWatch({ control: form.control, name: "topic" });
  // The API counts code points (Python's len), as the schema does.
  const length = Array.from((topic ?? "").trim()).length;

  return (
    <div className="grid gap-2">
      <Label htmlFor={`${ids}-topic`}>{t("label")}</Label>
      <Textarea
        id={`${ids}-topic`}
        rows={3}
        placeholder={t("placeholder")}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(`${ids}-hint`, `${ids}-error`, Boolean(error))}
        {...form.register("topic")}
        onKeyDown={(event) => {
          // Enter moves on, as in a one-line field; Shift+Enter starts a new line.
          if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault();
            event.currentTarget.form?.requestSubmit();
          }
        }}
      />
      <div className="flex flex-wrap justify-between gap-2 text-xs text-muted-foreground">
        <p id={`${ids}-hint`}>{t("hint")}</p>
        <p className="tabular-nums">
          {t("count", { count: length, max: NEW_RUN_LIMITS.topic.max })}
        </p>
      </div>
      <FieldError id={`${ids}-error`} error={error} />
    </div>
  );
}

export function LiteratureStep({ form }: { form: NewRunFormApi }) {
  const t = useTranslations("wizard.literature");
  const tSources = useTranslations("shared.papers.sources");
  const ids = useId();
  const errors = form.formState.errors.config;
  const yearError = errors?.year_from ?? errors?.year_to;
  const { year, maxPapers } = NEW_RUN_LIMITS;

  return (
    <div className="grid gap-6">
      <fieldset className="grid gap-2">
        <legend className="mb-1 text-sm font-medium">{t("years")}</legend>
        <div className="flex flex-wrap items-end gap-4">
          <div className="grid gap-1.5">
            <Label htmlFor={`${ids}-from`} className="font-normal text-muted-foreground">
              {t("yearFrom")}
            </Label>
            <Input
              id={`${ids}-from`}
              type="number"
              inputMode="numeric"
              min={year.min}
              max={year.max}
              step={1}
              className="w-28"
              aria-invalid={errors?.year_from ? true : undefined}
              aria-describedby={describedBy(null, `${ids}-years-error`, Boolean(yearError))}
              {...form.register("config.year_from", { valueAsNumber: true })}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor={`${ids}-to`} className="font-normal text-muted-foreground">
              {t("yearTo")}
            </Label>
            <Input
              id={`${ids}-to`}
              type="number"
              inputMode="numeric"
              min={year.min}
              max={year.max}
              step={1}
              className="w-28"
              aria-invalid={errors?.year_to ? true : undefined}
              aria-describedby={describedBy(null, `${ids}-years-error`, Boolean(yearError))}
              {...form.register("config.year_to", { valueAsNumber: true })}
            />
          </div>
        </div>
        <div id={`${ids}-years-error`}>
          <FieldError error={errors?.year_from} />
          {/* The order is reported on the end year; skip it while the start year is invalid. */}
          {!errors?.year_from && <FieldError error={errors?.year_to} />}
        </div>
      </fieldset>

      <fieldset className="grid gap-2">
        <legend id={`${ids}-sources`} className="mb-1 text-sm font-medium">
          {t("sources")}
        </legend>
        <p id={`${ids}-sources-hint`} className="text-xs text-muted-foreground">
          {t("sourcesHint")}
        </p>
        <Controller
          control={form.control}
          name="config.sources"
          render={({ field }) => (
            <CheckboxGroup
              aria-labelledby={`${ids}-sources`}
              aria-describedby={describedBy(
                `${ids}-sources-hint`,
                `${ids}-sources-error`,
                Boolean(errors?.sources),
              )}
              value={field.value}
              // Keep the display order, whatever order they were ticked in.
              onValueChange={(value) =>
                field.onChange(SEARCH_SOURCES.filter((source) => value.includes(source)))
              }
              className="grid gap-2 sm:grid-cols-2"
            >
              {SEARCH_SOURCES.map((source) => (
                <Label key={source} className={cn(OPTION_CLASS, "items-center")}>
                  <Checkbox.Root
                    value={source}
                    onBlur={field.onBlur}
                    className="peer flex size-4 shrink-0 items-center justify-center rounded-[4px] border border-input outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 data-checked:border-primary data-checked:bg-primary data-checked:text-primary-foreground dark:bg-input/30"
                  >
                    <Checkbox.Indicator className="flex data-unchecked:hidden">
                      <CheckIcon aria-hidden className="size-3.5" />
                    </Checkbox.Indicator>
                  </Checkbox.Root>
                  <span>{tSources(source)}</span>
                </Label>
              ))}
            </CheckboxGroup>
          )}
        />
        <FieldError id={`${ids}-sources-error`} error={errors?.sources} />
      </fieldset>

      <div className="grid gap-1.5">
        <Label htmlFor={`${ids}-papers`}>{t("maxPapers")}</Label>
        <Input
          id={`${ids}-papers`}
          type="number"
          inputMode="numeric"
          min={maxPapers.min}
          max={maxPapers.max}
          step={1}
          className="w-28"
          aria-invalid={errors?.max_papers ? true : undefined}
          aria-describedby={describedBy(
            `${ids}-papers-hint`,
            `${ids}-papers-error`,
            Boolean(errors?.max_papers),
          )}
          {...form.register("config.max_papers", { valueAsNumber: true })}
        />
        <p id={`${ids}-papers-hint`} className="text-xs text-muted-foreground">
          {t("maxPapersHint", maxPapers)}
        </p>
        <FieldError id={`${ids}-papers-error`} error={errors?.max_papers} />
      </div>
    </div>
  );
}

/** Which stages a run goes through, in order, with the ones it skips struck out. */
function PipelinePreview({ stages }: { stages: readonly string[] }) {
  const t = useTranslations("wizard.stages");
  const tStages = useTranslations("stages");
  const included = new Set(stages);
  return (
    <ol aria-label={t("preview")} className="flex flex-wrap items-center gap-1.5 text-xs">
      {STAGE_ORDER.map((stage, index) => {
        const on = included.has(stage);
        return (
          <li key={stage} className="flex items-center gap-1.5">
            {index > 0 && (
              <span aria-hidden className="text-muted-foreground">
                →
              </span>
            )}
            <span
              data-stage={on ? stage : undefined}
              className={cn(
                "inline-flex h-6 items-center gap-1 rounded-full border px-2",
                on
                  ? "border-(--tone)/40 bg-(--tone)/10 font-medium"
                  : "text-muted-foreground line-through",
              )}
            >
              <StageIcon stage={stage} className={on ? undefined : "text-current"} />
              {tStages(stage)}
              <span className="sr-only">{on ? t("included") : t("skipped")}</span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}

function DatasetDetails({ dataset }: { dataset: DatasetOut }) {
  const t = useTranslations("wizard.dataset");
  const format = useFormatter();
  return (
    <div className="grid gap-1 rounded-lg border bg-muted/30 p-3 text-xs">
      <p className="text-sm">{dataset.description}</p>
      <p className="text-muted-foreground">
        {t("facts", {
          samples: format.number(dataset.samples),
          size: formatBytes(dataset.size_bytes, format),
          modality: dataset.modality,
          license: dataset.license,
        })}
      </p>
      {dataset.splits.length > 0 && (
        <p className="text-muted-foreground">
          {t("splits", {
            splits: dataset.splits
              .map((split) => `${split.name} ${format.number(split.samples)}`)
              .join(" · "),
          })}
        </p>
      )}
    </div>
  );
}

function DatasetField({ form, used }: { form: NewRunFormApi; used: boolean }) {
  const t = useTranslations("wizard.dataset");
  const ids = useId();
  const datasets = useDatasets();
  const error = form.formState.errors.config?.dataset;
  const chosen = useWatch({ control: form.control, name: "config.dataset" });
  const items: Record<string, string> = {
    [NO_DATASET]: t("none"),
    ...Object.fromEntries(
      (datasets.data?.items ?? []).map((dataset) => [
        dataset.id,
        t("option", { name: dataset.name, version: dataset.version }),
      ]),
    ),
  };
  const selected = datasets.data?.items.find((dataset) => dataset.id === chosen);

  return (
    <div className="grid gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <Label id={`${ids}-label`}>{t("label")}</Label>
        {datasets.data?.demo && <DemoBadge demo />}
      </div>
      {datasets.isError ? (
        <QueryError error={datasets.error} onRetry={() => datasets.refetch()} />
      ) : (
        <Controller
          control={form.control}
          name="config.dataset"
          render={({ field }) => (
            <Select
              items={items}
              value={field.value ? field.value : NO_DATASET}
              disabled={datasets.isPending}
              onValueChange={(value) =>
                field.onChange(typeof value === "string" && value !== NO_DATASET ? value : "")
              }
            >
              <SelectTrigger
                className="w-full sm:w-96"
                aria-labelledby={`${ids}-label`}
                aria-describedby={describedBy(`${ids}-hint`, `${ids}-error`, Boolean(error))}
                aria-invalid={error ? true : undefined}
                onBlur={field.onBlur}
              >
                <SelectValue placeholder={t("loading")} />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(items).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        />
      )}
      <p id={`${ids}-hint`} className="text-xs text-muted-foreground">
        {used ? t("hint") : t("notUsed")}
      </p>
      {selected && <DatasetDetails dataset={selected} />}
      <FieldError id={`${ids}-error`} error={error} />
    </div>
  );
}

export function StagesStep({
  form,
  setLastStage,
}: {
  form: NewRunFormApi;
  setLastStage: (stage: Stage) => void;
}) {
  const t = useTranslations("wizard.stages");
  const tStages = useTranslations("stages");
  const ids = useId();
  const stages = useWatch({ control: form.control, name: "config.stages" }) ?? [];
  const last = lastStageOf(stages);
  const error = form.formState.errors.config?.stages;

  return (
    <div className="grid gap-6">
      <fieldset className="grid gap-2">
        <legend id={`${ids}-stages`} className="mb-1 text-sm font-medium">
          {t("label")}
        </legend>
        <p id={`${ids}-hint`} className="text-xs text-muted-foreground">
          {t("hint")}
        </p>
        <RadioGroup
          aria-labelledby={`${ids}-stages`}
          aria-describedby={describedBy(`${ids}-hint`, `${ids}-error`, Boolean(error))}
          value={last}
          onValueChange={(value) => {
            if (isStage(value)) {
              setLastStage(value);
            }
          }}
          className="grid gap-2"
        >
          {STAGE_ORDER.map((stage) => (
            <Label key={stage} className={OPTION_CLASS}>
              <RadioGroupItem
                value={stage}
                className="mt-0.5"
                aria-labelledby={`${ids}-${stage}-label`}
                aria-describedby={`${ids}-${stage}-description`}
              />
              <span className="grid gap-1">
                <span
                  id={`${ids}-${stage}-label`}
                  className="flex items-center gap-1.5 font-medium"
                >
                  <StageIcon stage={stage} />
                  {t("stopAfter", { stage: tStages(stage) })}
                </span>
                <span
                  id={`${ids}-${stage}-description`}
                  className="text-xs leading-snug text-muted-foreground"
                >
                  {t(`descriptions.${stage}`)}
                </span>
              </span>
            </Label>
          ))}
        </RadioGroup>
        <PipelinePreview stages={stages} />
        <FieldError id={`${ids}-error`} error={error} />
      </fieldset>
      <DatasetField form={form} used={stages.includes("experiment")} />
    </div>
  );
}

export function BudgetStep({
  form,
  allowFreeModels,
}: {
  form: NewRunFormApi;
  /** The project may forbid free models (privacy); then only Auto is offered. */
  allowFreeModels: boolean;
}) {
  const t = useTranslations("wizard.budget");
  const tPolicy = useTranslations("project.newRun.policies");
  const ids = useId();
  const errors = form.formState.errors;
  const policy = useWatch({ control: form.control, name: "llm_policy" });

  return (
    <div className="grid gap-6">
      <fieldset className="grid gap-2">
        <legend id={`${ids}-policy`} className="mb-1 text-sm font-medium">
          {t("policy")}
        </legend>
        <Controller
          control={form.control}
          name="llm_policy"
          render={({ field }) => (
            <RadioGroup
              aria-labelledby={`${ids}-policy`}
              value={field.value}
              onValueChange={(value) => {
                if ((LLM_POLICIES as readonly unknown[]).includes(value)) {
                  field.onChange(value as LlmPolicy);
                }
              }}
              className="grid gap-2 sm:grid-cols-2"
            >
              {LLM_POLICIES.map((value) => {
                const disabled = value === "free" && !allowFreeModels;
                return (
                  <Label key={value} className={OPTION_CLASS}>
                    <RadioGroupItem
                      value={value}
                      disabled={disabled}
                      className="mt-0.5"
                      aria-labelledby={`${ids}-${value}-label`}
                      aria-describedby={`${ids}-${value}-description`}
                    />
                    <span className="grid gap-1">
                      <span id={`${ids}-${value}-label`} className="font-medium">
                        {tPolicy(`${value}.label`)}
                      </span>
                      <span
                        id={`${ids}-${value}-description`}
                        className="text-xs leading-snug text-muted-foreground"
                      >
                        {disabled ? t("freeNotAllowed") : tPolicy(`${value}.description`)}
                      </span>
                    </span>
                  </Label>
                );
              })}
            </RadioGroup>
          )}
        />
        <FieldError error={errors.llm_policy} />
      </fieldset>

      <div className="grid gap-1.5 sm:max-w-xs">
        <Label htmlFor={`${ids}-cap`}>{t("cap")}</Label>
        <Input
          id={`${ids}-cap`}
          type="number"
          inputMode="decimal"
          min={NEW_RUN_LIMITS.budget.min}
          max={NEW_RUN_LIMITS.budget.max}
          step="0.01"
          placeholder={t("capPlaceholder")}
          aria-invalid={errors.budget_cap_usd ? true : undefined}
          aria-describedby={describedBy(
            `${ids}-cap-hint`,
            `${ids}-cap-error`,
            Boolean(errors.budget_cap_usd),
          )}
          {...form.register("budget_cap_usd")}
        />
        <p id={`${ids}-cap-hint`} className="text-xs text-muted-foreground">
          {policy === "free" ? t("capHintFree") : t("capHint")}
        </p>
        <FieldError id={`${ids}-cap-error`} error={errors.budget_cap_usd} />
      </div>
    </div>
  );
}
