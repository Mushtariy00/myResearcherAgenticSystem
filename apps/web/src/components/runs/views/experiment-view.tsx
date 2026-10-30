"use client";

import { ArrowDownIcon, ArrowUpIcon } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useMemo } from "react";
import type { ExperimentOutput, MetricSeries } from "@/client";
import { CodeBlock } from "@/components/shared/code-block";
import { DownloadLink } from "@/components/shared/download-link";
import { MetricsChart } from "@/components/shared/metrics-chart";
import { ProvenanceList } from "@/components/shared/provenance-list";
import { useEpochLine } from "@/components/shared/stage-log";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { artifactUrl, useRunArtifacts } from "@/hooks/use-run-artifacts";
import type { LiveTraining } from "@/lib/training-curves";
import { artifactsOf } from "../run-data";
import { Prose, ViewSection } from "./view-section";

const STATUS_TONES: Record<ExperimentOutput["status"], string> = {
  succeeded: "success",
  failed: "danger",
  timeout: "warning",
  cancelled: "neutral",
};

/** The series of each metric (train, validation and test together), in first-seen order. */
function seriesByMetric(series: readonly MetricSeries[]): [string, MetricSeries[]][] {
  const groups = new Map<string, MetricSeries[]>();
  for (const entry of series) {
    groups.set(entry.name, [...(groups.get(entry.name) ?? []), entry]);
  }
  return [...groups];
}

/**
 * Which way is better for a final metric: from the series of the same name, or of a split's
 * prefixed name (`val_loss` → the `loss` series), when the experiment reports one.
 */
function directionOf(name: string, series: readonly MetricSeries[]): boolean | undefined {
  const match = series.find(
    (entry) => entry.name === name || `${entry.split}_${entry.name}` === name,
  );
  return match?.higher_is_better;
}

function FinalMetrics({ data }: { data: ExperimentOutput }) {
  const t = useTranslations("run.experiment");
  const tMetric = useTranslations("shared.metric");
  const format = useFormatter();
  const rows = Object.entries(data.final_metrics);
  if (rows.length === 0) {
    return <p className="text-sm text-muted-foreground">{t("noFinalMetrics")}</p>;
  }
  return (
    <Table>
      <TableCaption className="sr-only">{t("finalMetrics")}</TableCaption>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead>{t("metric")}</TableHead>
          <TableHead className="text-right">{t("value")}</TableHead>
          <TableHead>{t("direction")}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map(([name, value]) => {
          const higherIsBetter = directionOf(name, data.series);
          const Arrow = higherIsBetter ? ArrowUpIcon : ArrowDownIcon;
          return (
            <TableRow key={name}>
              <TableCell className="font-mono text-xs">{name}</TableCell>
              <TableCell className="text-right tabular-nums">
                {value === null ? (
                  <span className="text-muted-foreground">{tMetric("notMeasured")}</span>
                ) : (
                  format.number(value, { maximumFractionDigits: 4 })
                )}
              </TableCell>
              <TableCell className="text-xs text-muted-foreground">
                {higherIsBetter === undefined ? (
                  <span className="sr-only">{t("noDirection")}</span>
                ) : (
                  <span className="inline-flex items-center gap-1">
                    <Arrow aria-hidden className="size-3" />
                    {higherIsBetter ? tMetric("higherIsBetter") : tMetric("lowerIsBetter")}
                  </span>
                )}
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}

/**
 * While the experiment stage trains: its curves so far, from the run's `experiment.epoch`
 * events (useRunView `training`), one chart per metric (validation against training) that
 * grows as each epoch arrives; a metric not measured yet leaves a gap. Before the first epoch
 * it says the curves are on their way. Once the output is ready, ExperimentView shows the
 * stored series instead.
 */
export function LiveTrainingCurves({
  training,
  attempt,
}: {
  training: LiveTraining | null;
  /** Named in the title when an earlier attempt's output is on screen too. */
  attempt?: number;
}) {
  const t = useTranslations("run.experiment");
  const epochLine = useEpochLine();
  const series = training?.series;
  const groups = useMemo(() => seriesByMetric(series ?? []), [series]);
  const metricOrder = useMemo(() => groups.map(([name]) => name), [groups]);

  return (
    <ViewSection
      title={attempt === undefined ? t("live.title") : t("live.titleAttempt", { attempt })}
      actions={
        <span
          data-tone="info"
          className="inline-flex h-6 items-center gap-1.5 rounded-full bg-(--tone)/15 px-2.5 text-xs font-medium text-(--tone-fg)"
        >
          <span
            aria-hidden
            className="size-1.5 rounded-full bg-current motion-safe:animate-pulse"
          />
          {training ? t("live.epochs", { count: training.epochs }) : t("live.badge")}
        </span>
      }
    >
      {training === null ? (
        <p className="rounded-lg border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">
          {t("live.waiting")}
        </p>
      ) : (
        <>
          <p className="text-sm text-muted-foreground">
            {t("live.latest", { line: epochLine(training.latest).text })}
          </p>
          <div className="grid gap-6 lg:grid-cols-2">
            {groups.map(([name, metricSeries]) => (
              <MetricsChart
                key={name}
                live
                series={metricSeries}
                title={t("curve", { metric: name })}
                metricOrder={metricOrder}
                height="14rem"
                emptyText={t("live.notMeasured")}
                className="rounded-xl border p-3"
              />
            ))}
          </div>
        </>
      )}
    </ViewSection>
  );
}

/**
 * An experiment output: the status and summary, one chart per metric (train against
 * validation), the final metrics (a missing measurement says so, never 0), the config, the
 * end of the training log with the log, metrics and checkpoint downloads, and the provenance
 * of the numbers.
 */
export function ExperimentView({
  runId,
  outputId,
  data,
}: {
  runId: string;
  outputId: string;
  data: ExperimentOutput;
}) {
  const t = useTranslations("run.experiment");
  const { artifacts } = useRunArtifacts(runId);
  const groups = useMemo(() => seriesByMetric(data.series), [data.series]);
  const metricOrder = useMemo(() => groups.map(([name]) => name), [groups]);
  const own = artifactsOf(artifacts, outputId);
  const log = own.find((artifact) => artifact.kind === "experiment_log");
  const metricsCsv = own.find((artifact) => artifact.kind === "metrics");
  const checkpoint = own.find((artifact) => artifact.kind === "checkpoint");
  const config = Object.entries(data.config);

  return (
    <div className="grid gap-6">
      <ViewSection
        title={t("result")}
        actions={
          <span
            data-tone={STATUS_TONES[data.status] ?? "neutral"}
            className="inline-flex h-6 items-center rounded-full bg-(--tone)/15 px-2.5 text-xs font-medium text-(--tone-fg)"
          >
            {t(`status.${data.status}`)}
          </span>
        }
      >
        <Prose text={data.summary} />
      </ViewSection>
      <ViewSection title={t("curves")}>
        {groups.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("noCurves")}</p>
        ) : (
          <div className="grid gap-6 lg:grid-cols-2">
            {groups.map(([name, series]) => (
              <MetricsChart
                key={name}
                series={series}
                title={t("curve", { metric: name })}
                metricOrder={metricOrder}
                height="14rem"
                className="rounded-xl border p-3"
              />
            ))}
          </div>
        )}
      </ViewSection>
      <ViewSection title={t("finalMetrics")}>
        <FinalMetrics data={data} />
      </ViewSection>
      <ViewSection title={t("config")}>
        {config.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("noConfig")}</p>
        ) : (
          <dl className="grid gap-x-6 gap-y-1.5 text-sm sm:grid-cols-2">
            {config.map(([key, value]) => (
              <div key={key} className="flex min-w-0 justify-between gap-3 border-b py-1">
                <dt className="font-mono text-xs text-muted-foreground">{key}</dt>
                <dd className="min-w-0 truncate font-mono text-xs" title={String(value)}>
                  {String(value)}
                </dd>
              </div>
            ))}
          </dl>
        )}
      </ViewSection>
      <ViewSection
        title={t("logs")}
        actions={
          (log || metricsCsv || checkpoint) && (
            <div className="flex flex-wrap gap-2">
              {log && (
                <DownloadLink
                  href={artifactUrl(log.id)}
                  filename={log.filename}
                  sizeBytes={log.size_bytes}
                >
                  {t("downloadLog")}
                </DownloadLink>
              )}
              {metricsCsv && (
                <DownloadLink
                  href={artifactUrl(metricsCsv.id)}
                  filename={metricsCsv.filename}
                  sizeBytes={metricsCsv.size_bytes}
                >
                  {t("downloadMetrics")}
                </DownloadLink>
              )}
              {checkpoint && (
                <DownloadLink
                  href={artifactUrl(checkpoint.id)}
                  filename={checkpoint.filename}
                  sizeBytes={checkpoint.size_bytes}
                >
                  {t("downloadCheckpoint")}
                </DownloadLink>
              )}
            </div>
          )
        }
      >
        {data.logs_tail.trim() ? (
          <CodeBlock
            code={data.logs_tail}
            label={t("logsTail")}
            maxHeight="20rem"
            className="rounded-lg border bg-muted/30"
          />
        ) : (
          <p className="text-sm text-muted-foreground">{t("noLogs")}</p>
        )}
      </ViewSection>
      <ViewSection title={t("provenance")}>
        <ProvenanceList provenance={data.provenance} />
      </ViewSection>
    </div>
  );
}
