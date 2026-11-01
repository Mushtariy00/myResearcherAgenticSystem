"use client";

import { useFormatter, useTranslations } from "next-intl";
import { useCallback } from "react";
import type { EpochRecord } from "@/lib/run-events";
import { epochReading, HARNESS_METRICS } from "@/lib/training-curves";

/** Why a source could not be searched (agentic_scholarly SourceError codes). */
const SOURCE_ERRORS = [
  "source.rate_limited",
  "source.quota_exhausted",
  "source.http_status",
  "source.network",
  "source.bad_response",
] as const;

const SOURCES = ["arxiv", "semantic_scholar", "openalex", "crossref", "core", "demo"] as const;

/**
 * Why a GPU job failed (a smoke test's `error_code`): the harness's codes from results.json
 * (sandbox/pytorch/harness) and the executor's own (agentic_core.gpu_jobs).
 */
export const JOB_ERROR_CODES = [
  "code.refused",
  "code.shape_mismatch",
  "code.import_failed",
  "code.too_large",
  "train.oom",
  "train.non_finite",
  "train.error",
  "job.timeout",
  "job.oom_killed",
  "job.no_result",
  "job.lost",
  "job.start_failed",
  "job.bad_input",
] as const;

const JOB_KINDS = ["smoke", "train"] as const;

const TRAINING_STATUSES = ["succeeded", "failed", "timeout", "cancelled"] as const;

/** A code a job could report but this interface does not know yet ("train.new_kind"). */
const CODE_PATTERN = /^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$/;

type Params = Record<string, unknown>;

function count(value: unknown): number | null {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : null;
}

/** A try or a job's ordinal: counted from 1. */
function ordinal(value: unknown): number | null {
  const number = count(value);
  return number !== null && number > 0 ? number : null;
}

function seconds(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function texts(value: unknown): string[] | null {
  return Array.isArray(value) && value.every((item) => typeof item === "string") ? value : null;
}

function member<T extends string>(list: readonly T[], value: unknown): value is T {
  return typeof value === "string" && (list as readonly string[]).includes(value);
}

/**
 * The progress lines of the real stages (apps/worker: literature/progress.py, the method and
 * writing runners, the GPU job helper gpu.py, and the coding and experiment runners), worded
 * once for both interfaces. Returns null for any other code, or when the params don't fit the
 * code; the caller then shows the worker's English message.
 */
export function useStageLogLine(): (code: string, p: Params) => string | null {
  const t = useTranslations("shared.stageLog");
  const tSources = useTranslations("shared.papers.sources");
  const format = useFormatter();

  return useCallback(
    (code: string, p: Params): string | null => {
      const source = (id: string) => (member(SOURCES, id) ? tSources(id) : id);
      /** "Smoke test 2" or "Training"; null for params that name no job. */
      const job = (kind: unknown, number: unknown): string | null => {
        const which = ordinal(number);
        if (kind === "train") {
          return t("gpu.jobs.train");
        }
        return kind === "smoke" && which !== null ? t("gpu.jobs.smoke", { ordinal: which }) : null;
      };
      switch (code) {
        case "gpu.queue_full": {
          const limit = count(p.limit);
          if (!member(JOB_KINDS, p.kind) || limit === null) {
            return null;
          }
          const name = p.kind === "smoke" ? t("gpu.jobs.smokeAny") : t("gpu.jobs.train");
          return t("gpu.queueFull", { job: name, limit });
        }
        case "gpu.queued":
        case "gpu.started": {
          const name = job(p.kind, p.ordinal);
          if (name === null) {
            return null;
          }
          return code === "gpu.queued"
            ? t("gpu.queued", { job: name })
            : t("gpu.started", { job: name });
        }
        case "gpu.executor_down":
          return t("gpu.executorDown");
        case "coding.written": {
          const number = ordinal(p.try);
          const files = count(p.files);
          const lines = count(p.lines);
          return number !== null && files !== null && lines !== null
            ? t("coding.written", { try: number, files, lines })
            : null;
        }
        case "coding.refused": {
          const number = ordinal(p.try);
          const findings = count(p.findings);
          return number !== null && findings !== null
            ? t("coding.refused", { try: number, findings })
            : null;
        }
        case "coding.smoke_failed": {
          const number = ordinal(p.try);
          const error = text(p.error_code);
          if (number === null || error === null) {
            return null;
          }
          const reason = member(JOB_ERROR_CODES, error)
            ? t(`jobErrors.${error}`)
            : CODE_PATTERN.test(error)
              ? t("jobErrors.unknown", { code: error })
              : null;
          return reason === null ? null : t("coding.smokeFailed", { try: number, reason });
        }
        case "coding.smoke_passed": {
          const number = ordinal(p.try);
          const duration = seconds(p.seconds);
          return number !== null && duration !== null
            ? t("coding.smokePassed", {
                try: number,
                seconds: format.number(duration, { maximumFractionDigits: 1 }),
              })
            : null;
        }
        case "experiment.planned": {
          const epochs = count(p.epochs);
          const steps = count(p.steps);
          const batchSize = count(p.batch_size);
          return epochs !== null && steps !== null && batchSize !== null
            ? t("experiment.planned", { epochs, steps, batchSize })
            : null;
        }
        case "experiment.finished": {
          const epochs = count(p.epochs);
          return member(TRAINING_STATUSES, p.status) && epochs !== null
            ? t(`experiment.finished.${p.status}`, { epochs })
            : null;
        }
        case "literature.searched": {
          const sources = texts(p.sources);
          const queries = count(p.queries);
          const found = count(p.found);
          const incomplete = count(p.incomplete) ?? 0;
          if (!sources || queries === null || found === null) {
            return null;
          }
          const values = {
            sources: format.list(sources.map(source), { type: "conjunction" }),
            queries,
            found,
            incomplete,
          };
          return incomplete > 0
            ? t("literature.searchedIncomplete", values)
            : t("literature.searched", values);
        }
        case "literature.source_failed": {
          if (typeof p.source !== "string" || !member(SOURCE_ERRORS, p.error)) {
            return null;
          }
          const error = p.error.slice("source.".length) as SourceError;
          const reason = t(`literature.sourceErrors.${error}`);
          // Lines written before the counts were added say nothing of the queries answered.
          const answered = count(p.answered) ?? 0;
          const queries = count(p.queries);
          return answered > 0 && queries !== null
            ? t("literature.sourceStopped", { source: source(p.source), reason, answered, queries })
            : t("literature.sourceFailed", { source: source(p.source), reason });
        }
        case "literature.screened": {
          const candidates = count(p.candidates);
          const included = count(p.included);
          return candidates !== null && included !== null
            ? t("literature.screened", { candidates, included })
            : null;
        }
        case "literature.fetched": {
          const pdfs = count(p.pdfs);
          const abstractOnly = count(p.abstract_only);
          if (pdfs === null || abstractOnly === null) {
            return null;
          }
          return abstractOnly > 0
            ? t("literature.fetched", { pdfs, abstractOnly })
            : t("literature.fetchedAll", { pdfs });
        }
        case "literature.parsed":
        case "literature.analyzed": {
          const papers = count(p.papers);
          const key = code === "literature.parsed" ? "literature.parsed" : "literature.analyzed";
          return papers !== null ? t(key, { papers }) : null;
        }
        case "literature.synthesized": {
          const findings = count(p.findings);
          return findings !== null ? t("literature.synthesized", { findings }) : null;
        }
        case "method.proposed": {
          const proposals = count(p.proposals);
          const gaps = count(p.gaps);
          return proposals !== null && gaps !== null
            ? t("method.proposed", { proposals, gaps })
            : null;
        }
        case "writing.outlined": {
          const sections = count(p.sections);
          return sections !== null ? t("writing.outlined", { sections }) : null;
        }
        case "writing.drafted": {
          const section = text(p.section);
          const index = count(p.index);
          const sections = count(p.sections);
          return section && index !== null && sections !== null
            ? t("writing.drafted", { section, index, sections })
            : null;
        }
        case "writing.cited": {
          const citations = count(p.citations);
          const removed = count(p.removed) ?? 0;
          if (citations === null) {
            return null;
          }
          return removed > 0
            ? t("writing.citedRemoved", { citations, removed })
            : t("writing.cited", { citations });
        }
        default:
          return null;
      }
    },
    [t, tSources, format],
  );
}

type SourceError = (typeof SOURCE_ERRORS)[number] extends `source.${infer Name}` ? Name : never;

/** An epoch's line in the log: "Epoch 2: val RMSE 0.512", and the training value as detail. */
export type EpochLine = { text: string; detail: string | null };

/**
 * How the logs of both interfaces word an `experiment.epoch` event: its epoch (from 0, as on
 * the charts' axis), the job when it is a smoke test, and one reading (see `epochReading`). A
 * metric that was not measured says so, never 0. `detail` is the same metric on the training
 * split, for a validation reading.
 */
export function useEpochLine(): (record: EpochRecord) => EpochLine {
  const t = useTranslations("shared.stageLog.experiment");
  const format = useFormatter();

  return useCallback(
    (record: EpochRecord): EpochLine => {
      const value = (number: number | null) =>
        number === null ? t("notMeasured") : format.number(number, { maximumSignificantDigits: 4 });
      const found = epochReading(record);
      const reading = found
        ? t("reading", {
            split: t(`splits.${found.split}`),
            metric: member(HARNESS_METRICS, found.metric)
              ? t(`metrics.${found.metric}`)
              : found.metric,
            value: value(found.value),
          })
        : t("nothingMeasured");
      const line =
        record.kind === "smoke"
          ? t("smokeEpoch", { ordinal: record.ordinal, epoch: record.epoch, reading })
          : t("epoch", { epoch: record.epoch, reading });
      return {
        text: line,
        detail:
          found && found.train !== null ? t("trainValue", { value: value(found.train) }) : null,
      };
    },
    [t, format],
  );
}
