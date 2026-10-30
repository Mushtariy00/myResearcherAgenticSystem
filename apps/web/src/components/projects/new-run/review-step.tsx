"use client";

import { PencilIcon } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import type { ReactNode } from "react";
import { useWatch } from "react-hook-form";
import { useStageName } from "@/components/dashboard/run-stage";
import { Button } from "@/components/ui/button";
import { useDatasets } from "@/hooks/use-datasets";
import { toAmount, USD } from "@/lib/format";
import { isSearchSource, type NewRunStepId } from "@/lib/new-run-schema";
import type { NewRunFormApi } from "./wizard-steps";

function Group({
  title,
  editLabel,
  onEdit,
  children,
}: {
  title: string;
  /** The button's accessible name, which says which step it edits. */
  editLabel: string;
  onEdit: () => void;
  children: ReactNode;
}) {
  const t = useTranslations("wizard.review");
  return (
    <section className="grid gap-2 rounded-lg border p-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">{title}</h3>
        <Button type="button" variant="ghost" size="xs" onClick={onEdit} aria-label={editLabel}>
          <PencilIcon aria-hidden />
          {t("editShort")}
        </Button>
      </div>
      <dl className="grid gap-x-4 gap-y-1.5 text-sm sm:grid-cols-[minmax(8rem,auto)_minmax(0,1fr)]">
        {children}
      </dl>
    </section>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </>
  );
}

/** Everything the run will be started with, one group per step, each with a way back to it. */
export function ReviewStep({
  form,
  onEdit,
}: {
  form: NewRunFormApi;
  onEdit: (step: NewRunStepId) => void;
}) {
  const t = useTranslations("wizard");
  const tSources = useTranslations("shared.papers.sources");
  const tPolicy = useTranslations("project.newRun.policies");
  const format = useFormatter();
  const stageName = useStageName();
  const datasets = useDatasets();
  const values = useWatch({ control: form.control });
  const config = values.config;
  const sources = (config?.sources ?? []).filter(isSearchSource);
  const stages = (config?.stages ?? []).filter(
    (stage): stage is string => typeof stage === "string",
  );
  const dataset = config?.dataset
    ? (datasets.data?.items.find((item) => item.id === config.dataset) ?? null)
    : null;
  const cap =
    typeof values.budget_cap_usd === "string"
      ? values.budget_cap_usd.trim()
      : values.budget_cap_usd;
  const edit = (step: NewRunStepId) => () => onEdit(step);
  const editLabel = (step: NewRunStepId) => t("review.edit", { step: t(`steps.${step}.title`) });

  return (
    <div className="grid gap-3">
      <Group title={t("steps.topic.title")} editLabel={editLabel("topic")} onEdit={edit("topic")}>
        <Row label={t("review.topic")}>{(values.topic ?? "").trim()}</Row>
      </Group>
      <Group
        title={t("steps.literature.title")}
        editLabel={editLabel("literature")}
        onEdit={edit("literature")}
      >
        <Row label={t("review.years")}>
          {t("review.yearRange", { from: String(config?.year_from), to: String(config?.year_to) })}
        </Row>
        <Row label={t("review.sources")}>
          {sources.map((source) => tSources(source)).join(", ")}
        </Row>
        <Row label={t("review.maxPapers")}>{String(config?.max_papers ?? "")}</Row>
      </Group>
      <Group
        title={t("steps.stages.title")}
        editLabel={editLabel("stages")}
        onEdit={edit("stages")}
      >
        <Row label={t("review.stages")}>{stages.map(stageName).join(" → ")}</Row>
        <Row label={t("review.dataset")}>
          {config?.dataset
            ? dataset
              ? t("dataset.option", { name: dataset.name, version: dataset.version })
              : config.dataset
            : t("dataset.none")}
          {config?.dataset && !stages.includes("experiment") && (
            <span className="block text-xs text-muted-foreground">{t("dataset.notUsed")}</span>
          )}
        </Row>
      </Group>
      <Group
        title={t("steps.budget.title")}
        editLabel={editLabel("budget")}
        onEdit={edit("budget")}
      >
        <Row label={t("review.policy")}>
          {values.llm_policy ? tPolicy(`${values.llm_policy}.label`) : ""}
        </Row>
        <Row label={t("review.cap")}>
          {cap === "" || cap === null || cap === undefined
            ? t("review.noCap")
            : format.number(toAmount(cap), USD)}
        </Row>
      </Group>
    </div>
  );
}
