"use client";

import { Radio } from "@base-ui/react/radio";
import { RadioGroup } from "@base-ui/react/radio-group";
import { CheckIcon, SparklesIcon, WalletIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { type KeyboardEvent, useId } from "react";
import { Controller, useWatch } from "react-hook-form";
import type { NewRunForm } from "@/hooks/use-new-run-form";
import {
  isSearchSource,
  LLM_POLICIES,
  lastStageOf,
  NEW_RUN_LIMITS,
  SEARCH_SOURCES,
} from "@/lib/new-run-schema";
import { cn } from "@/lib/utils";
import {
  FieldError,
  STUDIO_FIELD,
  STUDIO_HINT,
  STUDIO_LABEL,
} from "@/studio/components/dashboard/studio-fields";
import { DatasetCards } from "./dataset-cards";
import { StagePrefixChooser } from "./stage-prefix-chooser";
import { useWizardFieldError } from "./wizard-messages";

type StepProps = { wizard: NewRunForm };

/** `aria-describedby` from the ids that are present. */
function describedBy(...ids: (string | false | null | undefined)[]): string | undefined {
  const present = ids.filter(Boolean);
  return present.length > 0 ? present.join(" ") : undefined;
}

const CHOICE_CARD =
  "relative flex cursor-pointer items-start gap-3 rounded-xl border border-(--studio-glass-border) bg-(--studio-glass) p-3 transition-colors hover:bg-(--studio-hover) has-[[data-checked]]:border-(--tone) has-[[data-checked]]:bg-(--tone)/10 has-[:focus-visible]:ring-3 has-[:focus-visible]:ring-ring/50 has-[[data-disabled]]:cursor-not-allowed has-[[data-disabled]]:opacity-70";

const RADIO_DOT =
  "mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border-2 border-[color-mix(in_oklch,var(--foreground)_30%,transparent)] outline-none data-checked:border-(--tone)";

/** Step 1: the research topic. Enter moves on (Shift+Enter for a new line, never mid-IME). */
export function TopicStep({ wizard }: StepProps) {
  const t = useTranslations();
  const fieldError = useWizardFieldError();
  const ids = useId();
  const { register, formState, control } = wizard.form;
  const topic = useWatch({ control, name: "topic" });
  const length = Array.from(typeof topic === "string" ? topic.trim() : "").length;
  const error = fieldError(formState.errors.topic);

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  return (
    <div className="grid gap-2">
      <label htmlFor={`${ids}-topic`} className={STUDIO_LABEL}>
        {t("project.newRun.topic")}
      </label>
      <textarea
        id={`${ids}-topic`}
        rows={3}
        placeholder={t("project.newRun.topicPlaceholder")}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(`${ids}-hint`, error && `${ids}-error`)}
        className={cn(STUDIO_FIELD, "h-auto min-h-24 resize-y py-2.5 leading-relaxed")}
        {...register("topic")}
        onKeyDown={onKeyDown}
      />
      <div className="flex items-start justify-between gap-3">
        <p id={`${ids}-hint`} className={STUDIO_HINT}>
          {t("studioWork.wizard.topic.hint")}
        </p>
        <p
          aria-hidden
          className={cn(
            "shrink-0 font-mono text-xs tabular-nums",
            length > NEW_RUN_LIMITS.topic.max
              ? "text-(--studio-danger-fg)"
              : "text-muted-foreground",
          )}
        >
          {length}/{NEW_RUN_LIMITS.topic.max}
        </p>
      </div>
      {error && <FieldError id={`${ids}-error`}>{error}</FieldError>}
    </div>
  );
}

/** Step 2: where and how far back the literature search looks, and how many papers it keeps. */
export function LiteratureStep({ wizard }: StepProps) {
  const t = useTranslations();
  const fieldError = useWizardFieldError();
  const ids = useId();
  const { register, formState, control } = wizard.form;
  const errors = formState.errors.config;
  const yearFromError = fieldError(errors?.year_from);
  const yearToError = fieldError(errors?.year_to);
  const sourcesError = fieldError(errors?.sources);
  const maxPapersError = fieldError(errors?.max_papers);
  const { year, maxPapers } = NEW_RUN_LIMITS;

  return (
    <div className="grid gap-6">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="grid content-start gap-2">
          <label htmlFor={`${ids}-from`} className={STUDIO_LABEL}>
            {t("studioWork.wizard.literature.yearFrom")}
          </label>
          <input
            id={`${ids}-from`}
            type="number"
            inputMode="numeric"
            min={year.min}
            max={year.max}
            aria-invalid={yearFromError ? true : undefined}
            aria-describedby={yearFromError ? `${ids}-from-error` : undefined}
            className={cn(STUDIO_FIELD, "font-mono tabular-nums")}
            {...register("config.year_from", { valueAsNumber: true })}
          />
          {yearFromError && <FieldError id={`${ids}-from-error`}>{yearFromError}</FieldError>}
        </div>
        <div className="grid content-start gap-2">
          <label htmlFor={`${ids}-to`} className={STUDIO_LABEL}>
            {t("studioWork.wizard.literature.yearTo")}
          </label>
          <input
            id={`${ids}-to`}
            type="number"
            inputMode="numeric"
            min={year.min}
            max={year.max}
            aria-invalid={yearToError ? true : undefined}
            aria-describedby={yearToError ? `${ids}-to-error` : undefined}
            className={cn(STUDIO_FIELD, "font-mono tabular-nums")}
            {...register("config.year_to", { valueAsNumber: true })}
          />
          {yearToError && <FieldError id={`${ids}-to-error`}>{yearToError}</FieldError>}
        </div>
      </div>

      <Controller
        control={control}
        name="config.sources"
        render={({ field }) => {
          const chosen = new Set((field.value ?? []).filter(isSearchSource));
          return (
            <fieldset
              className="grid min-w-0 gap-2"
              aria-describedby={sourcesError ? `${ids}-sources-error` : undefined}
            >
              <legend className={cn(STUDIO_LABEL, "mb-2")}>
                {t("studioWork.wizard.literature.sources")}
              </legend>
              <div className="grid gap-2 min-[420px]:grid-cols-2 sm:grid-cols-3">
                {SEARCH_SOURCES.map((source) => {
                  const checked = chosen.has(source);
                  return (
                    <label
                      key={source}
                      data-stage="literature"
                      className={cn(
                        "flex h-11 cursor-pointer items-center gap-2.5 rounded-xl border px-3 text-sm transition-colors has-[:focus-visible]:ring-3 has-[:focus-visible]:ring-ring/50",
                        checked
                          ? "border-(--tone) bg-(--tone)/10 text-foreground"
                          : "border-(--studio-glass-border) bg-(--studio-glass) text-foreground hover:bg-(--studio-hover)",
                      )}
                    >
                      <input
                        type="checkbox"
                        className="peer sr-only"
                        checked={checked}
                        onBlur={field.onBlur}
                        onChange={(event) => {
                          const next = SEARCH_SOURCES.filter((item) =>
                            item === source ? event.target.checked : chosen.has(item),
                          );
                          field.onChange(next);
                        }}
                      />
                      <span
                        aria-hidden
                        className={cn(
                          "flex size-4.5 shrink-0 items-center justify-center rounded-md border-2",
                          checked
                            ? "border-(--tone) bg-(--tone) text-white"
                            : "border-[color-mix(in_oklch,var(--foreground)_30%,transparent)]",
                        )}
                      >
                        {checked && <CheckIcon className="size-3" strokeWidth={3} />}
                      </span>
                      {t(`shared.papers.sources.${source}`)}
                    </label>
                  );
                })}
              </div>
              {sourcesError && <FieldError id={`${ids}-sources-error`}>{sourcesError}</FieldError>}
            </fieldset>
          );
        }}
      />

      <div className="grid gap-2 sm:max-w-xs">
        <label htmlFor={`${ids}-papers`} className={STUDIO_LABEL}>
          {t("studioWork.wizard.literature.maxPapers")}
        </label>
        <input
          id={`${ids}-papers`}
          type="number"
          inputMode="numeric"
          min={maxPapers.min}
          max={maxPapers.max}
          aria-invalid={maxPapersError ? true : undefined}
          aria-describedby={describedBy(
            `${ids}-papers-hint`,
            maxPapersError && `${ids}-papers-error`,
          )}
          className={cn(STUDIO_FIELD, "font-mono tabular-nums")}
          {...register("config.max_papers", { valueAsNumber: true })}
        />
        <p id={`${ids}-papers-hint`} className={STUDIO_HINT}>
          {t("studioWork.wizard.literature.maxPapersHint", {
            min: maxPapers.min,
            max: maxPapers.max,
          })}
        </p>
        {maxPapersError && <FieldError id={`${ids}-papers-error`}>{maxPapersError}</FieldError>}
      </div>
    </div>
  );
}

/** Step 3: how far the pipeline goes ("stop after"), and the dataset experiments use. */
export function StagesStep({ wizard }: StepProps) {
  const t = useTranslations("studioWork.wizard");
  const fieldError = useWizardFieldError();
  const ids = useId();
  const { formState, control } = wizard.form;
  const stages = useWatch({ control, name: "config.stages" });
  const last = lastStageOf(Array.isArray(stages) ? stages : []);
  const stagesError = fieldError(formState.errors.config?.stages);
  const datasetError = fieldError(formState.errors.config?.dataset);
  const experimentIncluded = Array.isArray(stages) && stages.includes("experiment");

  return (
    <div className="grid gap-6">
      <div className="grid gap-2">
        <p id={`${ids}-stages`} className={STUDIO_LABEL}>
          {t("stages.legend")}
        </p>
        <StagePrefixChooser
          value={last}
          onChange={wizard.setLastStage}
          labelledBy={`${ids}-stages`}
          describedBy={stagesError ? `${ids}-stages-error` : undefined}
          invalid={Boolean(stagesError)}
        />
        {stagesError && <FieldError id={`${ids}-stages-error`}>{stagesError}</FieldError>}
      </div>
      <div className="grid gap-2">
        <p id={`${ids}-dataset`} className={STUDIO_LABEL}>
          {t("dataset.legend")}
        </p>
        <Controller
          control={control}
          name="config.dataset"
          render={({ field }) => (
            <DatasetCards
              value={typeof field.value === "string" ? field.value : ""}
              onChange={(value) => {
                field.onChange(value);
                field.onBlur();
              }}
              legendId={`${ids}-dataset`}
              describedBy={datasetError ? `${ids}-dataset-error` : undefined}
              experimentIncluded={experimentIncluded}
            />
          )}
        />
        {datasetError && <FieldError id={`${ids}-dataset-error`}>{datasetError}</FieldError>}
      </div>
    </div>
  );
}

/** Step 4: paid-then-free or free-only models, and an optional cost cap. */
export function BudgetStep({
  wizard,
  allowFreeModels,
}: StepProps & {
  /** The project allows free models (confidential projects may not). */
  allowFreeModels: boolean;
}) {
  const t = useTranslations();
  const fieldError = useWizardFieldError();
  const ids = useId();
  const { register, formState, control } = wizard.form;
  const policyError = fieldError(formState.errors.llm_policy);
  const capError = fieldError(formState.errors.budget_cap_usd);
  const icons = { auto: WalletIcon, free: SparklesIcon } as const;

  return (
    <div className="grid gap-6">
      <div className="grid gap-2">
        <p id={`${ids}-policy`} className={STUDIO_LABEL}>
          {t("project.newRun.policy")}
        </p>
        <Controller
          control={control}
          name="llm_policy"
          render={({ field }) => (
            <RadioGroup
              value={field.value}
              onValueChange={(next) => {
                if (next === "auto" || next === "free") {
                  field.onChange(next);
                  field.onBlur();
                }
              }}
              aria-labelledby={`${ids}-policy`}
              aria-describedby={policyError ? `${ids}-policy-error` : undefined}
              className="grid gap-3 sm:grid-cols-2"
            >
              {LLM_POLICIES.map((policy) => {
                const Icon = icons[policy];
                const disabled = policy === "free" && !allowFreeModels;
                return (
                  // biome-ignore lint/a11y/noLabelWithoutControl: Base UI's Radio renders its input in the label
                  <label
                    key={policy}
                    data-tone={policy === "auto" ? "info" : "success"}
                    className={CHOICE_CARD}
                  >
                    <Radio.Root
                      value={policy}
                      disabled={disabled}
                      aria-labelledby={`${ids}-${policy}`}
                      aria-describedby={`${ids}-${policy}-description`}
                      className={RADIO_DOT}
                    >
                      <Radio.Indicator className="size-2.5 rounded-full bg-(--tone)" />
                    </Radio.Root>
                    <span className="grid min-w-0 gap-1">
                      <span
                        id={`${ids}-${policy}`}
                        className="flex items-center gap-2 text-sm font-semibold text-foreground"
                      >
                        <Icon aria-hidden className="size-4 text-(--tone-fg)" />
                        {t(`project.newRun.policies.${policy}.label`)}
                      </span>
                      <span
                        id={`${ids}-${policy}-description`}
                        className="text-xs text-pretty text-muted-foreground"
                      >
                        {disabled
                          ? t("studioWork.wizard.budget.freeDisabled")
                          : t(`project.newRun.policies.${policy}.description`)}
                      </span>
                    </span>
                  </label>
                );
              })}
            </RadioGroup>
          )}
        />
        {policyError && <FieldError id={`${ids}-policy-error`}>{policyError}</FieldError>}
      </div>

      <div className="grid gap-2 sm:max-w-xs">
        <label htmlFor={`${ids}-cap`} className={STUDIO_LABEL}>
          {t("project.newRun.cap")}
        </label>
        <div className="relative">
          <span
            aria-hidden
            className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-sm text-muted-foreground"
          >
            $
          </span>
          <input
            id={`${ids}-cap`}
            type="text"
            inputMode="decimal"
            autoComplete="off"
            placeholder={t("project.newRun.capPlaceholder")}
            aria-invalid={capError ? true : undefined}
            aria-describedby={describedBy(`${ids}-cap-hint`, capError && `${ids}-cap-error`)}
            className={cn(STUDIO_FIELD, "pl-7 font-mono tabular-nums")}
            {...register("budget_cap_usd")}
          />
        </div>
        <p id={`${ids}-cap-hint`} className={STUDIO_HINT}>
          {t("project.newRun.capHint")}
        </p>
        {capError && <FieldError id={`${ids}-cap-error`}>{capError}</FieldError>}
      </div>
    </div>
  );
}
