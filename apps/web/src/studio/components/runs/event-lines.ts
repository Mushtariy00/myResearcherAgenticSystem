"use client";

import { useFormatter, useTranslations } from "next-intl";
import { useCallback } from "react";
import type { PaperRef } from "@/client";
import { useEpochLine, useStageLogLine } from "@/components/shared/stage-log";
import { useWaitLabels } from "@/components/shared/wait-text";
import { USD } from "@/lib/format";
import { isRunStatus } from "@/lib/labels";
import { type RunEvent, summarizeEvent } from "@/lib/run-events";
import type { Tone } from "@/studio/lib/stages";
import { runStatusMeta } from "./run-status";
import { useRunLabels } from "./use-run-labels";

export type EventKind =
  | "created"
  | "status"
  | "started"
  | "progress"
  | "ready"
  | "decided"
  | "failed"
  | "waiting"
  | "invalidated"
  | "retried"
  | "llm"
  | "epoch"
  | "log"
  | "raw";

/** What the log's filter groups a line under. */
export type EventGroup = "stages" | "llm";

/** One run event as the log shows it: translated, with its stage and a tone for its icon. */
export type EventLine = {
  kind: EventKind;
  tone: Tone;
  /** The stage the event belongs to, if any (run events have none). */
  stage: string | null;
  text: string;
  /** Secondary text: a cost, an error, a reviewer's comment. */
  detail: string | null;
  group: EventGroup;
};

type Params = Record<string, unknown>;

const PAPER_SOURCES: ReadonlySet<string> = new Set<PaperRef["source"]>([
  "arxiv",
  "semantic_scholar",
  "openalex",
  "crossref",
  "core",
  "demo",
]);

function record(value: unknown): Params {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Params) : {};
}

function word(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function words(value: unknown): string[] | null {
  return Array.isArray(value) && value.length > 0 && value.every((item) => typeof item === "string")
    ? value
    : null;
}

function count(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;
}

/**
 * Turns run events into log lines in the UI language. Demo stages report progress as `log`
 * events with a `code` and `params` (apps/worker/src/agentic_worker/outputs.py), translated
 * here; a code this interface does not know, or params of the wrong type, fall back to the
 * event's English `message`. `llm.call` lines name the model, its tier and the cost of paid
 * calls; `stage.invalidated` and `run.retried` explain a retry; `stage.waiting` says why a
 * stage waits and when it tries again; `experiment.epoch` gives an epoch's headline metric,
 * with its training value as the detail.
 */
export function useEventDescriber(): (event: RunEvent) => EventLine {
  const t = useTranslations("studioRun.log");
  const tEvents = useTranslations("run.events");
  const tSources = useTranslations("shared.papers.sources");
  const format = useFormatter();
  const labels = useRunLabels();
  const waitLabels = useWaitLabels();
  const stageLine = useStageLogLine();
  const epochLine = useEpochLine();

  return useCallback(
    (event: RunEvent): EventLine => {
      const payload = event.payload;
      const stage = word(payload.stage);
      const stageName = stage ? labels.stage(stage) : "";
      const line = (
        kind: EventKind,
        tone: Tone,
        text: string,
        detail: string | null = null,
        group: EventGroup = "stages",
      ): EventLine => ({ kind, tone, stage, text, detail, group });
      const decimal = (value: number, digits: number) =>
        format.number(value, { maximumFractionDigits: digits });

      const progress = (code: string, params: Params): string | null => {
        switch (code) {
          case "demo.search": {
            const sources = words(params.sources);
            const queries = count(params.queries);
            if (!sources || queries === null) {
              return null;
            }
            const names = sources.map((source) =>
              PAPER_SOURCES.has(source) ? tSources(source as PaperRef["source"]) : source,
            );
            return t("progress.search", {
              sources: format.list(names, { type: "conjunction" }),
              queries,
            });
          }
          case "demo.screen": {
            const candidates = count(params.candidates);
            const papers = count(params.papers);
            return candidates === null || papers === null
              ? null
              : t("progress.screen", { candidates, papers });
          }
          case "demo.analyse": {
            const papers = count(params.papers);
            return papers === null ? null : t("progress.analyse", { papers });
          }
          case "demo.synthesise": {
            const findings = count(params.findings);
            return findings === null ? null : t("progress.synthesise", { findings });
          }
          case "demo.gaps": {
            const gaps = count(params.gaps);
            return gaps === null ? null : t("progress.gaps", { gaps });
          }
          case "demo.propose": {
            const proposals = count(params.proposals);
            return proposals === null ? null : t("progress.propose", { proposals });
          }
          case "demo.recommend": {
            const option = word(params.option);
            return option === null ? null : t("progress.recommend", { option });
          }
          case "demo.code": {
            const files = count(params.files);
            const entrypoint = word(params.entrypoint);
            return files === null || entrypoint === null
              ? null
              : t("progress.code", { files, entrypoint });
          }
          case "demo.test": {
            const tests = count(params.tests);
            return tests === null ? null : t("progress.test", { tests });
          }
          case "demo.smoke_test": {
            const seconds = count(params.seconds);
            if (typeof params.passed !== "boolean" || seconds === null) {
              return null;
            }
            const values = { seconds: decimal(seconds, 1) };
            return params.passed
              ? t("progress.smokePassed", values)
              : t("progress.smokeFailed", values);
          }
          case "demo.train": {
            const epochs = count(params.epochs);
            const dataset = word(params.dataset);
            if (epochs === null || dataset === null) {
              return null;
            }
            const gpu = word(params.gpu);
            return gpu
              ? t("progress.trainOnGpu", { epochs, dataset, gpu })
              : t("progress.train", { epochs, dataset });
          }
          case "demo.epoch": {
            const epoch = count(params.epoch);
            const epochs = count(params.epochs);
            const metric = word(params.metric);
            if (epoch === null || epochs === null || metric === null) {
              return null;
            }
            const value = typeof params.value === "number" ? params.value : null;
            return value === null
              ? t("progress.epochNotMeasured", { epoch, epochs, metric })
              : t("progress.epoch", { epoch, epochs, metric, value: decimal(value, 4) });
          }
          case "demo.outline": {
            const sections = count(params.sections);
            return sections === null ? null : t("progress.outline", { sections });
          }
          case "demo.draft": {
            const section = word(params.section);
            const index = count(params.index);
            const sections = count(params.sections);
            return section === null || index === null || sections === null
              ? null
              : t("progress.draft", { section, index, sections });
          }
          case "demo.cite": {
            const citations = count(params.citations);
            return citations === null ? null : t("progress.cite", { citations });
          }
          default:
            return null;
        }
      };

      switch (event.type) {
        case "log": {
          const code = word(payload.code);
          const params = record(payload.params);
          const translated = code ? (stageLine(code, params) ?? progress(code, params)) : null;
          if (translated) {
            return line("progress", "info", translated);
          }
          return line("log", "neutral", word(payload.message) ?? code ?? "");
        }
        case "stage.invalidated": {
          if (!stage) {
            break;
          }
          const attempt = count(payload.attempt);
          const retryStage = word(payload.retry_stage);
          return line(
            "invalidated",
            "neutral",
            attempt !== null && retryStage
              ? t("invalidated", {
                  stage: stageName,
                  attempt,
                  retryStage: labels.stage(retryStage),
                })
              : t("invalidatedPlain", { stage: stageName }),
          );
        }
        case "run.retried": {
          if (!stage) {
            break;
          }
          const requested = word(payload.requested_stage);
          return line(
            "retried",
            "info",
            requested && requested !== stage
              ? t("retriedEarlier", { stage: stageName, requested: labels.stage(requested) })
              : t("retried", { stage: stageName }),
          );
        }
        case "stage.decided": {
          const decision = word(payload.decision);
          if (!stage || !decision) {
            break;
          }
          const text = [
            tEvents("stageDecided", { stage: stageName, decision: labels.decision(decision) }),
            payload.automatic === true ? t("decidedAutomatically") : null,
            payload.edited === true ? t("decidedWithEdits") : null,
          ]
            .filter(Boolean)
            .join(" · ");
          const comment = word(payload.comment);
          const tone: Tone =
            decision === "approve" ? "success" : decision === "reject" ? "danger" : "warning";
          return line("decided", tone, text, comment ? `“${comment}”` : null);
        }
      }

      const summary = summarizeEvent(event);
      switch (summary.kind) {
        case "runCreated":
          return line("created", "info", tEvents("runCreated", { topic: summary.topic }));
        case "runStatus":
          return line(
            "status",
            isRunStatus(summary.status) ? runStatusMeta(summary.status).tone : "neutral",
            tEvents("runStatus", { status: labels.runStatus(summary.status) }),
            summary.error ? labels.errorText(summary.error) : null,
          );
        case "stageStarted": {
          const started = tEvents("stageStarted", { stage: labels.stage(summary.stage) });
          return line(
            "started",
            "info",
            summary.attempt > 1
              ? `${started} · ${tEvents("attempt", { attempt: summary.attempt })}`
              : started,
          );
        }
        case "stageOutputReady":
          return line(
            "ready",
            "warning",
            tEvents("stageOutputReady", { stage: labels.stage(summary.stage) }),
            summary.degraded ? tEvents("degraded") : null,
          );
        case "stageDecided":
          return line(
            "decided",
            "neutral",
            tEvents("stageDecided", {
              stage: labels.stage(summary.stage),
              decision: labels.decision(summary.decision),
            }),
          );
        case "stageFailed":
          return line(
            "failed",
            "danger",
            tEvents("stageFailed", { stage: labels.stage(summary.stage) }),
            summary.error ? labels.errorText(summary.error) : null,
          );
        case "stageWaiting":
          return line(
            "waiting",
            "warning",
            tEvents("stageWaiting", {
              stage: labels.stage(summary.stage),
              reason: waitLabels.reason(summary.reason),
            }),
            summary.retryAt ? waitLabels.retryAt(summary.retryAt) : null,
          );
        case "llmCall": {
          const detail = [
            summary.costUsd !== null
              ? format.number(summary.costUsd, { ...USD, maximumFractionDigits: 4 })
              : null,
            summary.switchedToFree ? tEvents("switchedToFree") : null,
            summary.replayed ? tEvents("replayed") : null,
          ]
            .filter(Boolean)
            .join(" · ");
          return line(
            "llm",
            summary.tier === "paid" ? "warning" : "neutral",
            tEvents("llmCall", { model: summary.model, tier: labels.tier(summary.tier) }),
            detail || null,
            "llm",
          );
        }
        case "experimentEpoch": {
          const epoch = epochLine(summary.record);
          return {
            kind: "epoch",
            tone: "info",
            stage: summary.record.stage,
            text: epoch.text,
            detail: epoch.detail,
            group: "stages",
          };
        }
        case "log":
          return line("log", "neutral", summary.message);
        case "raw":
          return line(
            "raw",
            "neutral",
            summary.text ? `${event.type} ${summary.text}` : event.type,
          );
      }
    },
    [t, tEvents, tSources, format, labels, waitLabels, stageLine, epochLine],
  );
}
