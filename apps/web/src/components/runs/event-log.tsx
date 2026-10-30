"use client";

import { RotateCwIcon } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useEffect, useRef } from "react";
import type { PaperRef } from "@/client";
import { useEpochLine, useStageLogLine } from "@/components/shared/stage-log";
import { useWaitLabels } from "@/components/shared/wait-text";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { StreamState } from "@/hooks/use-run-events";
import { USD } from "@/lib/format";
import { type RunEvent, summarizeEvent } from "@/lib/run-events";
import { cn } from "@/lib/utils";
import { useLabels } from "./use-labels";

const STATE_DOT: Record<StreamState, string> = {
  connecting: "bg-muted-foreground",
  live: "bg-emerald-500 motion-safe:animate-pulse",
  reconnecting: "bg-amber-500 motion-safe:animate-pulse",
  ended: "bg-muted-foreground",
  error: "bg-destructive",
};

/** Event types with a translated label under `run.events.types` (others show their id). */
const EVENT_TYPES = [
  "run.created",
  "run.status",
  "run.retried",
  "stage.started",
  "stage.output_ready",
  "stage.decided",
  "stage.failed",
  "stage.invalidated",
  "stage.waiting",
  "llm.call",
  "experiment.epoch",
  "log",
] as const;
type EventType = (typeof EVENT_TYPES)[number];

function isEventType(value: string): value is EventType {
  return (EVENT_TYPES as readonly string[]).includes(value);
}

type Params = Record<string, unknown>;

const SOURCES: readonly PaperRef["source"][] = [
  "arxiv",
  "semantic_scholar",
  "openalex",
  "crossref",
  "core",
  "demo",
];

function isSource(value: string): value is PaperRef["source"] {
  return (SOURCES as readonly string[]).includes(value);
}

function paramsOf(value: unknown): Params {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Params)
    : {};
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function count(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;
}

function texts(value: unknown): string[] | null {
  return Array.isArray(value) && value.every((item) => typeof item === "string") ? value : null;
}

/**
 * Progress lines of the demo stages (apps/worker outputs.py `progress_steps`), each with a code
 * and params the browser translates; the English `message` is the fallback for anything else.
 */
function useLogLine() {
  const t = useTranslations("run.events.log");
  const tSources = useTranslations("shared.papers.sources");
  const format = useFormatter();
  const source = (id: string) => (isSource(id) ? tSources(id) : id);

  return (code: string, p: Params): string | null => {
    switch (code) {
      case "demo.search": {
        const sources = texts(p.sources);
        const queries = count(p.queries);
        return sources && queries !== null
          ? t("demo.search", { sources: format.list(sources.map(source)), queries })
          : null;
      }
      case "demo.screen": {
        const candidates = count(p.candidates);
        const papers = count(p.papers);
        return candidates !== null && papers !== null
          ? t("demo.screen", { candidates, papers })
          : null;
      }
      case "demo.analyse": {
        const papers = count(p.papers);
        return papers !== null ? t("demo.analyse", { papers }) : null;
      }
      case "demo.synthesise": {
        const findings = count(p.findings);
        return findings !== null ? t("demo.synthesise", { findings }) : null;
      }
      case "demo.gaps": {
        const gaps = count(p.gaps);
        return gaps !== null ? t("demo.gaps", { gaps }) : null;
      }
      case "demo.propose": {
        const proposals = count(p.proposals);
        return proposals !== null ? t("demo.propose", { proposals }) : null;
      }
      case "demo.recommend": {
        const option = text(p.option);
        return option ? t("demo.recommend", { option }) : null;
      }
      case "demo.code": {
        const files = count(p.files);
        const entrypoint = text(p.entrypoint);
        return files !== null && entrypoint ? t("demo.code", { files, entrypoint }) : null;
      }
      case "demo.test": {
        const tests = count(p.tests);
        return tests !== null ? t("demo.test", { tests }) : null;
      }
      case "demo.smoke_test": {
        const seconds = count(p.seconds);
        return typeof p.passed === "boolean" && seconds !== null
          ? t("demo.smoke_test", {
              result: p.passed ? t("passed") : t("failed"),
              seconds: format.number(seconds, { maximumFractionDigits: 1 }),
            })
          : null;
      }
      case "demo.train": {
        const epochs = count(p.epochs);
        const dataset = text(p.dataset);
        return epochs !== null && dataset
          ? t("demo.train", { epochs, dataset, gpu: text(p.gpu) ?? t("unknownGpu") })
          : null;
      }
      case "demo.epoch": {
        const epoch = count(p.epoch);
        const epochs = count(p.epochs);
        const metric = text(p.metric);
        const value = p.value === null ? null : count(p.value);
        if (epoch === null || epochs === null || !metric || (p.value !== null && value === null)) {
          return null;
        }
        return t("demo.epoch", {
          epoch,
          epochs,
          metric,
          value:
            value === null ? t("notMeasured") : format.number(value, { maximumFractionDigits: 3 }),
        });
      }
      case "demo.outline": {
        const sections = count(p.sections);
        return sections !== null ? t("demo.outline", { sections }) : null;
      }
      case "demo.draft": {
        const section = text(p.section);
        const index = count(p.index);
        const sections = count(p.sections);
        return section && index !== null && sections !== null
          ? t("demo.draft", { section, index, sections })
          : null;
      }
      case "demo.cite": {
        const citations = count(p.citations);
        return citations !== null ? t("demo.cite", { citations }) : null;
      }
      default:
        return null;
    }
  };
}

function useSummary() {
  const t = useTranslations("run.events");
  const format = useFormatter();
  const labels = useLabels();
  const logLine = useLogLine();
  const stageLine = useStageLogLine();
  const epochLine = useEpochLine();
  const waitLabels = useWaitLabels();
  /** Prefixes a line with its stage, when the event names one. */
  const inStage = (stage: unknown, line: string) => {
    const name = text(stage);
    return name ? t("inStage", { stage: labels.stage(name), line }) : line;
  };

  return (event: RunEvent): string => {
    const p = event.payload;
    // Event types the shared summary does not know yet, and the richer forms of two it does.
    switch (event.type) {
      case "stage.invalidated": {
        const stage = text(p.stage);
        const retryStage = text(p.retry_stage);
        if (stage) {
          const attempt = count(p.attempt) ?? 1;
          return retryStage
            ? t("stageInvalidated", {
                stage: labels.stage(stage),
                attempt,
                retryStage: labels.stage(retryStage),
              })
            : t("stageInvalidatedPlain", { stage: labels.stage(stage), attempt });
        }
        break;
      }
      case "run.retried": {
        const stage = text(p.stage);
        const requested = text(p.requested_stage);
        if (stage) {
          return requested && requested !== stage
            ? t("runRetriedEarlier", {
                stage: labels.stage(stage),
                requested: labels.stage(requested),
              })
            : t("runRetried", { stage: labels.stage(stage) });
        }
        break;
      }
      case "log": {
        const code = text(p.code);
        const params = paramsOf(p.params);
        const translated = code ? (stageLine(code, params) ?? logLine(code, params)) : null;
        const line = translated ?? text(p.message);
        if (line) {
          return inStage(p.stage, line);
        }
        break;
      }
    }

    const summary = summarizeEvent(event);
    switch (summary.kind) {
      case "runCreated":
        return t("runCreated", { topic: summary.topic });
      case "runStatus": {
        const line = t("runStatus", { status: labels.runStatus(summary.status) });
        return summary.error ? `${line}: ${labels.errorText(summary.error)}` : line;
      }
      case "stageStarted": {
        const line = t("stageStarted", { stage: labels.stage(summary.stage) });
        return summary.attempt > 1
          ? `${line} · ${t("attempt", { attempt: summary.attempt })}`
          : line;
      }
      case "stageOutputReady": {
        const line = t("stageOutputReady", { stage: labels.stage(summary.stage) });
        return summary.degraded ? `${line} · ${t("degraded")}` : line;
      }
      case "stageDecided":
        return t("stageDecided", {
          stage: labels.stage(summary.stage),
          decision: labels.decision(summary.decision),
        });
      case "stageFailed": {
        const line = t("stageFailed", { stage: labels.stage(summary.stage) });
        return summary.error ? `${line}: ${labels.errorText(summary.error)}` : line;
      }
      case "stageWaiting": {
        const line = t("stageWaiting", {
          stage: labels.stage(summary.stage),
          reason: waitLabels.reason(summary.reason),
        });
        return summary.retryAt ? `${line} ${waitLabels.retryAt(summary.retryAt)}` : line;
      }
      case "llmCall": {
        const parts = [t("llmCall", { model: summary.model, tier: labels.tier(summary.tier) })];
        if (summary.costUsd !== null) {
          parts.push(format.number(summary.costUsd, { ...USD, maximumFractionDigits: 4 }));
        }
        if (summary.switchedToFree) {
          parts.push(t("switchedToFree"));
        }
        if (summary.replayed) {
          parts.push(t("replayed"));
        }
        return inStage(p.stage, parts.join(" · "));
      }
      case "experimentEpoch": {
        const line = epochLine(summary.record);
        return inStage(
          summary.record.stage,
          line.detail ? `${line.text} · ${line.detail}` : line.text,
        );
      }
      case "log":
        return summary.message;
      case "raw":
        return summary.text;
    }
  };
}

export function EventLog({
  events,
  state,
  onReconnect,
}: {
  events: readonly RunEvent[];
  state: StreamState;
  onReconnect: () => void;
}) {
  const t = useTranslations("run.events");
  const format = useFormatter();
  const summarize = useSummary();
  const viewport = useRef<HTMLDivElement>(null);
  const followTail = useRef(true);

  // Keep the newest event in view unless the reader scrolled up to look at older ones.
  // biome-ignore lint/correctness/useExhaustiveDependencies: scroll again whenever events change
  useEffect(() => {
    const element = viewport.current;
    if (element && followTail.current) {
      element.scrollTop = element.scrollHeight;
    }
  }, [events]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("title")}</CardTitle>
        <CardAction className="flex items-center gap-2 text-xs text-muted-foreground">
          <span aria-hidden className={cn("size-2 rounded-full", STATE_DOT[state])} />
          <span>{t(`state.${state}`)}</span>
          {state === "error" && (
            <Button size="xs" variant="outline" onClick={onReconnect}>
              <RotateCwIcon aria-hidden />
              {t("reconnect")}
            </Button>
          )}
        </CardAction>
      </CardHeader>
      <CardContent>
        <div
          ref={viewport}
          onScroll={(event) => {
            const element = event.currentTarget;
            followTail.current =
              element.scrollHeight - element.scrollTop - element.clientHeight < 48;
          }}
          role="log"
          aria-label={t("title")}
          // biome-ignore lint/a11y/noNoninteractiveTabindex: keyboard users must be able to scroll the log
          tabIndex={0}
          className="max-h-96 overflow-y-auto rounded-lg border bg-muted/30 font-mono text-xs focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
        >
          {events.length === 0 ? (
            <p className="p-3 text-muted-foreground">{t("empty")}</p>
          ) : (
            <ol>
              {events.map((event) => (
                <li
                  key={event.seq}
                  className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-0.5 border-b px-3 py-1.5 last:border-0 sm:grid-cols-[auto_11rem_minmax(0,1fr)]"
                >
                  <time dateTime={event.created_at} className="text-muted-foreground tabular-nums">
                    {event.created_at
                      ? format.dateTime(new Date(event.created_at), {
                          hour: "2-digit",
                          minute: "2-digit",
                          second: "2-digit",
                          hourCycle: "h23",
                        })
                      : `#${event.seq}`}
                  </time>
                  <span className="truncate font-semibold" title={event.type}>
                    {isEventType(event.type) ? t(`types.${event.type}`) : event.type}
                  </span>
                  <span className="col-span-2 break-words whitespace-pre-wrap sm:col-span-1">
                    {summarize(event)}
                  </span>
                </li>
              ))}
            </ol>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
