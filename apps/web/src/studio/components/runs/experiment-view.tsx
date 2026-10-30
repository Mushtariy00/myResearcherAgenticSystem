"use client";

import {
  ArrowDownIcon,
  ArrowUpIcon,
  ChartLineIcon,
  DownloadIcon,
  FlaskConicalIcon,
  ScrollTextIcon,
  ShieldCheckIcon,
  SlidersHorizontalIcon,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { Fragment, useId, useMemo } from "react";
import type { ExperimentOutput } from "@/client";
import { CodeBlock } from "@/components/shared/code-block";
import { MetricsChart } from "@/components/shared/metrics-chart";
import { ProvenanceList } from "@/components/shared/provenance-list";
import { artifactUrl, useRunArtifacts } from "@/hooks/use-run-artifacts";
import { headlineMetric } from "@/lib/stage-output";
import { BorderBeam } from "@/studio/components/effects/border-beam";
import { NumberTicker } from "@/studio/components/effects/number-ticker";
import type { Tone } from "@/studio/lib/stages";
import { useRunPage } from "./run-context";
import { groupSeriesByMetric, metricDirection } from "./run-helpers";
import { Chip, SMALL_BUTTON, ViewCard } from "./run-ui";

const STATUS_TONES: Record<ExperimentOutput["status"], Tone> = {
  succeeded: "success",
  failed: "danger",
  timeout: "warning",
  cancelled: "neutral",
};

/**
 * The experiment output: its outcome, the final metrics as spring-counted tiles (a metric that
 * was not measured says so and is never shown as 0; the headline metric carries a beam), one
 * chart per metric, the configuration, the provenance record and the end of the training log.
 */
export function ExperimentView({ data, outputId }: { data: ExperimentOutput; outputId: string }) {
  const t = useTranslations("studioRun.experiment");
  const tChart = useTranslations("shared.chart");
  const { runId } = useRunPage();
  const metricsId = useId();
  const { byStage } = useRunArtifacts(runId);
  const log = byStage.experiment?.find(
    (artifact) => artifact.kind === "experiment_log" && artifact.stage_output_id === outputId,
  );
  const groups = useMemo(() => groupSeriesByMetric(data.series), [data.series]);
  const metricOrder = useMemo(() => groups.map((group) => group.name), [groups]);
  const headline = headlineMetric(data)?.name ?? null;
  const finals = Object.entries(data.final_metrics);
  const configEntries = Object.entries(data.config);

  return (
    <div className="grid min-w-0 gap-4">
      <ViewCard
        title={t("summary")}
        icon={<FlaskConicalIcon aria-hidden />}
        action={<Chip tone={STATUS_TONES[data.status]}>{t(`status.${data.status}`)}</Chip>}
      >
        <p className="text-sm leading-6 break-words whitespace-pre-line text-foreground">
          {data.summary}
        </p>
      </ViewCard>

      <section aria-labelledby={metricsId} className="grid min-w-0 gap-3">
        <h4 id={metricsId} className="text-sm font-semibold tracking-tight text-foreground">
          {t("finalMetrics")}
        </h4>
        {finals.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("noMetrics")}</p>
        ) : (
          <dl className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4">
            {finals.map(([name, value]) => (
              <MetricTile
                key={name}
                name={name}
                value={value}
                higherIsBetter={metricDirection(name, data.series)}
                headline={name === headline}
              />
            ))}
          </dl>
        )}
      </section>

      <ViewCard title={t("curves")} icon={<ChartLineIcon aria-hidden />}>
        {groups.length === 0 ? (
          <p className="text-sm text-muted-foreground">{tChart("empty")}</p>
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            {groups.map((group) => (
              <div
                key={group.name}
                className="min-w-0 rounded-xl border border-(--studio-glass-border) bg-(--studio-glass) p-3"
              >
                <MetricsChart
                  series={group.series}
                  title={t("chartTitle", { metric: group.name })}
                  metricOrder={metricOrder}
                  height="14rem"
                />
              </div>
            ))}
          </div>
        )}
      </ViewCard>

      <div className="grid gap-4 lg:grid-cols-2">
        <ViewCard title={t("config")} icon={<SlidersHorizontalIcon aria-hidden />}>
          <dl className="grid gap-x-4 gap-y-1.5 sm:grid-cols-[auto_minmax(0,1fr)]">
            {configEntries.map(([key, value]) => (
              <Fragment key={key}>
                <dt className="font-mono text-xs text-muted-foreground">{key}</dt>
                <dd className="mb-1 font-mono text-xs break-words text-foreground sm:mb-0">
                  {String(value)}
                </dd>
              </Fragment>
            ))}
          </dl>
        </ViewCard>
        <ViewCard title={t("provenance")} icon={<ShieldCheckIcon aria-hidden />}>
          <ProvenanceList provenance={data.provenance} />
        </ViewCard>
      </div>

      <ViewCard
        title={t("logs")}
        icon={<ScrollTextIcon aria-hidden />}
        action={
          log && (
            <a href={artifactUrl(log.id)} download={log.filename} className={SMALL_BUTTON}>
              <DownloadIcon aria-hidden />
              {t("downloadLog")}
            </a>
          )
        }
      >
        <div className="overflow-hidden rounded-lg border bg-card">
          <CodeBlock code={data.logs_tail} label={t("logText")} maxHeight="16rem" />
        </div>
      </ViewCard>
    </div>
  );
}

function MetricTile({
  name,
  value,
  higherIsBetter,
  headline,
}: {
  name: string;
  value: number | null;
  higherIsBetter: boolean | undefined;
  headline: boolean;
}) {
  const t = useTranslations("studioRun.experiment");
  const tMetric = useTranslations("shared.metric");
  const direction =
    higherIsBetter === undefined
      ? null
      : higherIsBetter
        ? tMetric("higherIsBetter")
        : tMetric("lowerIsBetter");
  const Arrow = higherIsBetter ? ArrowUpIcon : ArrowDownIcon;
  return (
    <div
      data-stage="experiment"
      data-headline={headline || undefined}
      className="studio-glass relative grid min-w-0 content-start gap-1.5 rounded-2xl p-4"
    >
      {headline && (
        <BorderBeam colorFrom="var(--stage-experiment)" colorTo="var(--aurora-cyan)" duration={7} />
      )}
      <dt className="flex min-w-0 flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
        <span className="truncate font-mono">{name}</span>
        {headline && <span className="font-medium text-(--tone-fg)">{t("headline")}</span>}
      </dt>
      <dd className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-1">
        {value === null ? (
          <>
            <span aria-hidden className="font-mono text-2xl font-semibold text-muted-foreground">
              —
            </span>
            <span className="text-sm font-medium text-muted-foreground">
              {tMetric("notMeasured")}
            </span>
          </>
        ) : (
          <NumberTicker
            value={value}
            format={{ maximumFractionDigits: 4 }}
            className="font-mono text-2xl font-semibold tracking-tight text-foreground"
          />
        )}
        {direction && (
          <span
            className="inline-flex items-center gap-0.5 text-xs text-muted-foreground"
            title={direction}
          >
            <Arrow aria-hidden className="size-3" />
            <span className="sr-only">{direction}</span>
          </span>
        )}
      </dd>
    </div>
  );
}
