import type { MetricSeries } from "@/client";
import type { StageOverview } from "@/lib/stage-output";

/**
 * The stage a run page shows when the URL names none: the output waiting for review, else the
 * stage being worked on, else the last stage the run reached, else the first one.
 */
export function defaultStage(
  timeline: readonly StageOverview[],
  awaitingStage: string | null | undefined,
): string | null {
  if (awaitingStage && timeline.some((entry) => entry.stage === awaitingStage)) {
    return awaitingStage;
  }
  const current = timeline.find((entry) => entry.current);
  if (current) {
    return current.stage;
  }
  const reached = timeline.filter((entry) => entry.attempts > 0).at(-1);
  return reached?.stage ?? timeline[0]?.stage ?? null;
}

/** Where a schema error points, as "proposals › 0 › risk" (empty for the whole output). */
export function locationPath(loc: readonly (string | number)[]): string {
  return loc.map(String).join(" › ");
}

export type MetricGroup = { name: string; series: MetricSeries[] };

/** Metric series grouped by metric (each split of a metric in one group), in first-seen order. */
export function groupSeriesByMetric(series: readonly MetricSeries[]): MetricGroup[] {
  const groups = new Map<string, MetricSeries[]>();
  for (const entry of series) {
    groups.set(entry.name, [...(groups.get(entry.name) ?? []), entry]);
  }
  return [...groups].map(([name, members]) => ({ name, series: members }));
}

/** Whether a higher value of `metric` is better, from its series; losses are lower-is-better. */
export function metricDirection(
  metric: string,
  series: readonly MetricSeries[],
): boolean | undefined {
  const match = series.find((entry) => entry.name === metric);
  if (match) {
    return match.higher_is_better;
  }
  return /(^|_)loss$/.test(metric) || /^loss(_|$)/.test(metric) ? false : undefined;
}

/** The file of an entry point such as "model.py:DepthNet". */
export function entrypointFile(entrypoint: string): string {
  const [file] = entrypoint.split(":");
  return (file ?? entrypoint).trim();
}

/** An http(s) URL from generated content, or null: nothing else becomes a link. */
export function externalHref(url: string | null | undefined): string | null {
  if (!url) {
    return null;
  }
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : null;
  } catch {
    return null;
  }
}

/** The doi.org link of a DOI ("10.5555/abc"), or null for anything that is not a DOI. */
export function doiHref(doi: string | null | undefined): string | null {
  return doi && /^10\.\d{4,9}\/\S+$/.test(doi) ? `https://doi.org/${encodeURI(doi)}` : null;
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** The first eight characters of an id, for display (the full id is copied). */
export function shortId(id: string): string {
  return id.slice(0, 8);
}
