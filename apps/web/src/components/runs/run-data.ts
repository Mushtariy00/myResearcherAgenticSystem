/**
 * Small pure helpers of the Classic run page: which stage to open, the literature a later stage
 * refers to, the artifacts of one output, and links and field paths taken from generated data.
 */
import type { ArtifactOut, LiteratureOutput, RunDetail, StageRunOut } from "@/client";
import { latestVersion, type StageOverview, stageData } from "@/lib/stage-output";

/**
 * The run's newest literature output, typed: the newest version of the latest literature
 * attempt that has one. Method proposals and draft citations name its papers. Null when there
 * is none, or when it is not a literature output (an old placeholder).
 */
export function literatureOf(run: Pick<RunDetail, "stages"> | undefined): LiteratureOutput | null {
  let latest: StageRunOut | undefined;
  for (const stageRun of run?.stages ?? []) {
    if (
      stageRun.stage === "literature" &&
      (stageRun.outputs?.length ?? 0) > 0 &&
      (!latest || stageRun.attempt > latest.attempt)
    ) {
      latest = stageRun;
    }
  }
  return stageData("literature", latestVersion(latest?.outputs));
}

/**
 * The stage to open when the URL names none: the one waiting for review, else the one at work,
 * else the furthest stage that has started, else the first.
 */
export function defaultStage(
  timeline: readonly StageOverview[],
  awaitingStage: string | null | undefined,
): string | undefined {
  if (awaitingStage && timeline.some((entry) => entry.stage === awaitingStage)) {
    return awaitingStage;
  }
  const current = timeline.find((entry) => entry.current);
  if (current) {
    return current.stage;
  }
  const started = timeline.filter((entry) => entry.latest !== undefined);
  return (started.at(-1) ?? timeline[0])?.stage;
}

/**
 * The stage a retry most likely restarts from: where the run stopped (the last stage that
 * failed, was rejected or was cancelled), if a retry may start there.
 */
export function suggestedRetryStage(
  timeline: readonly StageOverview[],
  retryable: readonly string[],
): string | null {
  const stopped = timeline.filter(
    (entry) =>
      (entry.status === "failed" || entry.status === "rejected" || entry.status === "cancelled") &&
      retryable.includes(entry.stage),
  );
  return stopped.at(-1)?.stage ?? null;
}

/** The artifacts made from one output (artifacts follow each stage's latest output only). */
export function artifactsOf(
  artifacts: readonly ArtifactOut[],
  outputId: string | null | undefined,
): ArtifactOut[] {
  return outputId ? artifacts.filter((artifact) => artifact.stage_output_id === outputId) : [];
}

/** A schema error's location as a JSON path: `["proposals", 0, "risk"]` → `proposals[0].risk`. */
export function formatFieldPath(loc: readonly (string | number)[]): string {
  return loc.reduce<string>((path, part) => {
    if (typeof part === "number") {
      return `${path}[${part}]`;
    }
    return path ? `${path}.${part}` : part;
  }, "");
}

/**
 * An http(s) link from generated content, normalised, or null: `javascript:`, `data:`,
 * relative and malformed links never become clickable.
 */
export function externalUrl(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch {
    return null;
  }
}

/** Where a paper can be read: its DOI, its arXiv page and the URL the source gave. */
export function paperLinks(paper: {
  doi?: string | null;
  arxiv_id?: string | null;
  url?: string | null;
}): { kind: "doi" | "arxiv" | "source"; href: string }[] {
  const links: { kind: "doi" | "arxiv" | "source"; href: string }[] = [];
  const doi = paper.doi ? externalUrl(`https://doi.org/${paper.doi}`) : null;
  const arxiv = paper.arxiv_id ? externalUrl(`https://arxiv.org/abs/${paper.arxiv_id}`) : null;
  const source = externalUrl(paper.url);
  if (doi) {
    links.push({ kind: "doi", href: doi });
  }
  if (arxiv) {
    links.push({ kind: "arxiv", href: arxiv });
  }
  if (source && source !== doi && source !== arxiv) {
    links.push({ kind: "source", href: source });
  }
  return links;
}

/** The file part of a coding entrypoint (`model.py:DepthNet` → `model.py`). */
export function entrypointFile(entrypoint: string): string {
  return entrypoint.split(":")[0] ?? entrypoint;
}
