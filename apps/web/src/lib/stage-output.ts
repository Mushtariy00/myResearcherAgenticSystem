/**
 * Stage outputs for every interface (Classic and Studio): each output narrowed to its stage's
 * typed shape (the strict schemas of packages/core/src/agentic_core/schemas.py, generated into
 * src/client), the version and attempt selectors that stage views and diffs need, and the
 * per-stage summaries that timelines, cards and the pipeline graph show.
 *
 * Narrowing never throws. Data that is not its stage's shape (an old placeholder, a stage this
 * client has no type for, or `schema_ok: false` from the API) comes back as `kind: "raw"` with
 * the original JSON, for a plain JSON view.
 */
import type {
  CodingOutput,
  ExperimentOutput,
  LiteratureOutput,
  MethodOutput,
  MetricSeries,
  OutputVersionOut,
  Stage,
  StageAttemptOut,
  StageDetail,
  StageOutputOut,
  WritingOutput,
} from "@/client";
import { DEMO_DEGRADED_REASONS } from "./api-error";
import { isKnownStage } from "./labels";
import type { TimelineEntry } from "./timeline";

type OutputTypes = {
  literature: LiteratureOutput;
  method: MethodOutput;
  coding: CodingOutput;
  experiment: ExperimentOutput;
  writing: WritingOutput;
};

/** Each pipeline stage's output data. A stage the API adds without a type here fails to compile. */
export type StageOutputData = { [S in Stage]: OutputTypes[S] };

/**
 * What narrowing reads from an output: a run detail output (`StageOutputOut`) or a version from
 * `GET /runs/{id}/stages/{stage}` (`OutputVersionOut`, which adds the API's schema check).
 */
export type OutputLike = Pick<StageOutputOut, "data" | "degraded_reason"> & {
  /** OutputVersionOut only: whether `data` passed the stage's strict schema on the server. */
  schema_ok?: boolean;
};

/** An output whose data has its stage's type; switch on `kind` to narrow `data`. */
export type TypedOutput = { [S in Stage]: { kind: S; stage: S; data: StageOutputData[S] } }[Stage];

/** Why an output is shown as plain JSON instead of its stage's view. */
export type RawReason =
  /** This client has no type for the stage. */
  | "unknown_stage"
  /** The API says the data fails the stage's schema (`schema_ok: false`). */
  | "schema_failed"
  /** The data does not have the stage's shape (such as an old placeholder). */
  | "unexpected_shape";

export type RawOutput = {
  kind: "raw";
  stage: string;
  data: Record<string, unknown>;
  reason: RawReason;
};

export type NarrowedOutput = TypedOutput | RawOutput;

// --- Shape checks ------------------------------------------------------------------------------
// The API validates outputs strictly before storing them; these checks only make sure the data
// has the fields and types the views read, so a view never crashes on an unexpected object.

type Check = (value: unknown) => boolean;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

const text: Check = (value) => typeof value === "string";
const num: Check = (value) => typeof value === "number" && Number.isFinite(value);
const flag: Check = (value) => typeof value === "boolean";
const scalar: Check = (value) => text(value) || num(value) || flag(value);
/** `field?: T` */
const optional =
  (check: Check): Check =>
  (value) =>
    value === undefined || check(value);
/** `field?: T | null` */
const maybe =
  (check: Check): Check =>
  (value) =>
    value === undefined || value === null || check(value);
/** `field: T | null` */
const nullable =
  (check: Check): Check =>
  (value) =>
    value === null || check(value);
const listOf =
  (check: Check): Check =>
  (value) =>
    Array.isArray(value) && value.every(check);
const mapOf =
  (check: Check): Check =>
  (value) =>
    isRecord(value) && Object.values(value).every(check);
const shape =
  (fields: Record<string, Check>): Check =>
  (value) =>
    isRecord(value) && Object.entries(fields).every(([key, check]) => check(value[key]));

const researchPlan = shape({
  topic: text,
  queries: listOf(text),
  scope: text,
  inclusion_criteria: listOf(text),
  subtopics: listOf(text),
});
const paperRef = shape({
  paper_id: text,
  title: text,
  authors: listOf(text),
  year: num,
  venue: maybe(text),
  doi: maybe(text),
  arxiv_id: maybe(text),
  url: maybe(text),
  abstract: text,
  citation_count: maybe(num),
  source: text,
  pdf_available: flag,
  relevance: num,
  decision: text,
  decision_reason: text,
});
const paperAnalysis = shape({
  paper_id: text,
  contribution: text,
  method: text,
  results: text,
  limitations: text,
  evidence: optional(listOf(shape({ quote: text, page: num }))),
});
const paperFinding = shape({
  title: text,
  source: text,
  summary: text,
  url: maybe(text),
  paper_id: maybe(text),
});
const methodProposal = shape({
  name: text,
  rationale: text,
  expected_benefit: text,
  risk: text,
  evidence_paper_ids: optional(listOf(text)),
});
const metricSeries = shape({
  name: text,
  split: text,
  higher_is_better: flag,
  points: listOf(shape({ epoch: num, value: nullable(num) })),
});
const provenance = shape({
  image_digest: text,
  code_sha256: text,
  config_sha256: text,
  dataset: text,
  dataset_version: text,
  seed: num,
  gpu_name: maybe(text),
  gpu_seconds: num,
  started_at: text,
  finished_at: maybe(text),
});

const OUTPUT_SHAPES: { [S in Stage]: Check } = {
  literature: shape({
    plan: researchPlan,
    papers: listOf(paperRef),
    analyses: optional(listOf(paperAnalysis)),
    key_findings: listOf(paperFinding),
    synthesis: text,
  }),
  method: shape({
    research_gaps: listOf(text),
    proposals: listOf(methodProposal),
    recommended_option: text,
    implementation_focus: text,
    datasets: listOf(text),
    evaluation_metrics: listOf(text),
  }),
  coding: shape({
    summary: text,
    files: listOf(shape({ path: text, language: text, role: text, content: text })),
    entrypoint: text,
    smoke_test: shape({ passed: flag, duration_seconds: num, log: text }),
  }),
  experiment: shape({
    status: text,
    summary: text,
    config: mapOf(scalar),
    series: listOf(metricSeries),
    final_metrics: mapOf(nullable(num)),
    logs_tail: text,
    provenance,
  }),
  writing: shape({
    title: text,
    abstract: text,
    markdown: text,
    sections: listOf(shape({ name: text, objective: text })),
    citations: optional(listOf(shape({ key: num, paper_id: text }))),
    output_format: text,
    review_focus: text,
  }),
};

// --- Narrowing ---------------------------------------------------------------------------------

/**
 * `output`'s data with its stage's type, or `kind: "raw"` (with the original JSON and the
 * reason) when the stage is unknown, the API flagged `schema_ok: false`, or the data does not
 * have the stage's shape. Null for no output.
 */
export function outputAs(stage: string, output: OutputLike): NarrowedOutput;
export function outputAs(
  stage: string,
  output: OutputLike | null | undefined,
): NarrowedOutput | null;
export function outputAs(
  stage: string,
  output: OutputLike | null | undefined,
): NarrowedOutput | null {
  if (!output) {
    return null;
  }
  const data = isRecord(output.data) ? output.data : {};
  if (!isKnownStage(stage)) {
    return { kind: "raw", stage, data, reason: "unknown_stage" };
  }
  if (output.schema_ok === false) {
    return { kind: "raw", stage, data, reason: "schema_failed" };
  }
  if (!OUTPUT_SHAPES[stage](data)) {
    return { kind: "raw", stage, data, reason: "unexpected_shape" };
  }
  return { kind: stage, stage, data } as TypedOutput;
}

/** `output`'s data as `stage`'s type, or null when it is missing or does not have that shape. */
export function stageData<S extends Stage>(
  stage: S,
  output: OutputLike | null | undefined,
): StageOutputData[S] | null {
  const narrowed = outputAs(stage, output);
  return narrowed !== null && narrowed.kind === stage
    ? (narrowed.data as StageOutputData[S])
    : null;
}

/**
 * Whether a degraded reason marks generated demo content: one of DEMO_DEGRADED_REASONS, or any
 * code the API itself treats as demo (a dotted part that is `demo` or starts with `demo_`, as in
 * agentic_api.demo.is_demo_reason), so the badge matches the API's `demo: true` flags.
 */
export function isDemoReason(reason: string | null | undefined): boolean {
  if (!reason) {
    return false;
  }
  return (
    DEMO_DEGRADED_REASONS.has(reason) ||
    reason.split(".").some((part) => part === "demo" || part.startsWith("demo_"))
  );
}

/** The output is generated demo data, not a research result: show the Demo badge. */
export function isDemoOutput(
  output: Pick<OutputLike, "degraded_reason"> | null | undefined,
): boolean {
  return isDemoReason(output?.degraded_reason);
}

// --- Versions and attempts ---------------------------------------------------------------------

/** One output version and the attempt that produced it. */
export type VersionRef = { attempt: StageAttemptOut; output: OutputVersionOut };

/**
 * What a version is compared with in a diff. `version`: the version before it in the same
 * attempt (an approve-with-edits version). `attempt`: the newest version of an earlier attempt
 * (the output a reviewer asked to change).
 */
export type DiffBase = VersionRef & { relation: "version" | "attempt" };

type AttemptsOf = Pick<StageDetail, "attempts"> | null | undefined;

/** The output with the highest `version` (works for run detail and stage detail outputs). */
export function latestVersion<T extends { version: number }>(
  outputs: readonly T[] | null | undefined,
): T | undefined {
  let latest: T | undefined;
  for (const output of outputs ?? []) {
    if (!latest || output.version > latest.version) {
      latest = output;
    }
  }
  return latest;
}

/** A stage's attempts, oldest first. */
export function sortedAttempts(detail: AttemptsOf): StageAttemptOut[] {
  return [...(detail?.attempts ?? [])].sort((a, b) => a.attempt - b.attempt);
}

/** The newest attempt (it may still be running and have no output yet). */
export function latestAttempt(detail: AttemptsOf): StageAttemptOut | undefined {
  return sortedAttempts(detail).at(-1);
}

/** Every version of every attempt: oldest attempt first, each attempt's versions oldest first. */
export function stageVersions(detail: AttemptsOf): VersionRef[] {
  return sortedAttempts(detail).flatMap((attempt) =>
    [...attempt.outputs]
      .sort((a, b) => a.version - b.version)
      .map((output) => ({ attempt, output })),
  );
}

/** The newest version of the newest attempt that has one. */
export function latestOutput(detail: AttemptsOf): VersionRef | undefined {
  const attempts = sortedAttempts(detail);
  for (let index = attempts.length - 1; index >= 0; index -= 1) {
    const attempt = attempts[index];
    const output = latestVersion(attempt?.outputs);
    if (attempt && output) {
      return { attempt, output };
    }
  }
  return undefined;
}

export function findVersion(
  detail: AttemptsOf,
  outputId: string | null | undefined,
): VersionRef | undefined {
  if (!outputId) {
    return undefined;
  }
  return stageVersions(detail).find((ref) => ref.output.id === outputId);
}

/**
 * The diff base of a version: the version before it in its attempt, else the newest version of
 * the closest earlier attempt that has one. Undefined for a stage's first output (or an id the
 * detail does not list).
 */
export function previousOutput(
  detail: AttemptsOf,
  outputId: string | null | undefined,
): DiffBase | undefined {
  const target = findVersion(detail, outputId);
  if (!target) {
    return undefined;
  }
  let earlier: OutputVersionOut | undefined;
  for (const output of target.attempt.outputs) {
    if (output.version < target.output.version && (!earlier || output.version > earlier.version)) {
      earlier = output;
    }
  }
  if (earlier) {
    return { attempt: target.attempt, output: earlier, relation: "version" };
  }
  const before = sortedAttempts(detail).filter(
    (attempt) => attempt.attempt < target.attempt.attempt,
  );
  for (let index = before.length - 1; index >= 0; index -= 1) {
    const attempt = before[index];
    const output = latestVersion(attempt?.outputs);
    if (attempt && output) {
      return { attempt, output, relation: "attempt" };
    }
  }
  return undefined;
}

// --- Summaries ---------------------------------------------------------------------------------

export type HeadlineMetric = {
  /** The metric's key as the experiment reports it, such as "abs_rel" or "val_loss". */
  name: string;
  split: MetricSeries["split"] | null;
  higherIsBetter: boolean;
  /** The final value; null when it was not measured (never 0 as a stand-in). */
  value: number | null;
};

export type LiteratureSummary = {
  kind: "literature";
  papersTotal: number;
  papersIncluded: number;
  papersMaybe: number;
  papersExcluded: number;
  /** Included papers with reading notes. */
  analyses: number;
};
export type MethodSummary = { kind: "method"; proposals: number; recommended: string };
export type CodingSummary = {
  kind: "coding";
  files: number;
  lines: number;
  smokeTestPassed: boolean;
  entrypoint: string;
};
export type ExperimentSummary = {
  kind: "experiment";
  status: ExperimentOutput["status"];
  epochs: number;
  headline: HeadlineMetric | null;
};
export type WritingSummary = {
  kind: "writing";
  title: string;
  words: number;
  sections: number;
  citations: number;
};
export type RawSummary = { kind: "raw"; stage: string; reason: RawReason };

/** The headline numbers of one output; `kind` is the stage, or "raw" for untyped data. */
export type StageSummary =
  | LiteratureSummary
  | MethodSummary
  | CodingSummary
  | ExperimentSummary
  | WritingSummary
  | RawSummary;

/** Matches the n of "[n]" citation markers, alone or in lists and ranges ("[1, 2]", "[3–5]"). */
const CITATION_MARKERS = /\[\d+(?:\s*[,–-]\s*\d+)*\]/g;
/** The target of a Markdown link or image ("](https://…)"); the link text stays. */
const LINK_TARGETS = /\]\([^)]*\)/g;

let segmenter: Intl.Segmenter | null | undefined;

function wordSegmenter(): Intl.Segmenter | null {
  if (segmenter === undefined) {
    segmenter =
      typeof Intl !== "undefined" && typeof Intl.Segmenter === "function"
        ? new Intl.Segmenter("en", { granularity: "word" })
        : null;
  }
  return segmenter;
}

/**
 * Words in a draft, by Unicode word boundaries (so Korean and English count alike). Citation
 * markers and link targets do not count; Markdown punctuation is never a word.
 */
export function countWords(markdown: string): number {
  const plain = markdown.replace(LINK_TARGETS, "] ").replace(CITATION_MARKERS, " ");
  const words = wordSegmenter();
  if (words) {
    let count = 0;
    for (const segment of words.segment(plain)) {
      if (segment.isWordLike) {
        count += 1;
      }
    }
    return count;
  }
  return plain.split(/\s+/).filter((token) => /[\p{L}\p{N}]/u.test(token)).length;
}

function lineCount(content: string): number {
  if (content.length === 0) {
    return 0;
  }
  const lines = content.split("\n").length;
  return content.endsWith("\n") ? lines - 1 : lines;
}

/** The final value of a series: its last epoch's value (null when that epoch was not measured). */
function finalValue(series: MetricSeries): number | null {
  let last: MetricSeries["points"][number] | undefined;
  for (const point of series.points) {
    if (!last || point.epoch >= last.epoch) {
      last = point;
    }
  }
  return last?.value ?? null;
}

/**
 * The metric a card or the pipeline graph shows for an experiment: the first metric series that
 * is not a loss (the one the writing stage reports first), with its value from `final_metrics`.
 * Falls back to the validation loss; null when the experiment reports neither.
 */
export function headlineMetric(experiment: ExperimentOutput): HeadlineMetric | null {
  const finals = experiment.final_metrics;
  const series = experiment.series.find((item) => item.name !== "loss" && item.points.length > 0);
  if (series) {
    return {
      name: series.name,
      split: series.split,
      higherIsBetter: series.higher_is_better,
      value: Object.hasOwn(finals, series.name)
        ? (finals[series.name] ?? null)
        : finalValue(series),
    };
  }
  if (Object.hasOwn(finals, "val_loss")) {
    return {
      name: "val_loss",
      split: "val",
      higherIsBetter: false,
      value: finals.val_loss ?? null,
    };
  }
  return null;
}

function epochCount(experiment: ExperimentOutput): number {
  const configured = experiment.config.epochs;
  if (typeof configured === "number" && Number.isInteger(configured) && configured > 0) {
    return configured;
  }
  return Math.max(0, ...experiment.series.map((series) => series.points.length));
}

/** The headline numbers of a narrowed output. */
export function summarize(narrowed: NarrowedOutput): StageSummary {
  switch (narrowed.kind) {
    case "literature": {
      const papers = narrowed.data.papers;
      const count = (decision: string) => papers.filter((p) => p.decision === decision).length;
      return {
        kind: "literature",
        papersTotal: papers.length,
        papersIncluded: count("include"),
        papersMaybe: count("maybe"),
        papersExcluded: count("exclude"),
        analyses: narrowed.data.analyses?.length ?? 0,
      };
    }
    case "method":
      return {
        kind: "method",
        proposals: narrowed.data.proposals.length,
        recommended: narrowed.data.recommended_option,
      };
    case "coding":
      return {
        kind: "coding",
        files: narrowed.data.files.length,
        lines: narrowed.data.files.reduce((total, file) => total + lineCount(file.content), 0),
        smokeTestPassed: narrowed.data.smoke_test.passed,
        entrypoint: narrowed.data.entrypoint,
      };
    case "experiment":
      return {
        kind: "experiment",
        status: narrowed.data.status,
        epochs: epochCount(narrowed.data),
        headline: headlineMetric(narrowed.data),
      };
    case "writing":
      return {
        kind: "writing",
        title: narrowed.data.title,
        words: countWords(narrowed.data.markdown),
        sections: narrowed.data.sections.length,
        citations: narrowed.data.citations?.length ?? 0,
      };
    case "raw":
      return { kind: "raw", stage: narrowed.stage, reason: narrowed.reason };
  }
}

/** The headline numbers of `output` (null for no output). */
export function summarizeOutput(
  stage: string,
  output: OutputLike | null | undefined,
): StageSummary | null {
  const narrowed = outputAs(stage, output);
  return narrowed ? summarize(narrowed) : null;
}

/** A timeline entry with what cards and the pipeline graph show about its latest attempt. */
export type StageOverview = TimelineEntry & {
  /** The newest output of the latest attempt (none while that attempt is working). */
  output: StageOutputOut | undefined;
  summary: StageSummary | null;
  /** The output is generated demo data (show the Demo badge). */
  demo: boolean;
};

/** Adds each stage's newest output, its summary and its demo flag to the run timeline. */
export function stageOverviews(entries: readonly TimelineEntry[]): StageOverview[] {
  return entries.map((entry) => {
    const output = latestVersion(entry.latest?.outputs);
    return {
      ...entry,
      output,
      summary: summarizeOutput(entry.stage, output),
      demo: isDemoOutput(output),
    };
  });
}
