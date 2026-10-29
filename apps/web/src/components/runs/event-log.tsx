"use client";

import { RotateCwIcon } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useEffect, useRef } from "react";
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

function useSummary() {
  const t = useTranslations("run.events");
  const format = useFormatter();
  const labels = useLabels();
  return (event: RunEvent): string => {
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
        return parts.join(" · ");
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
                  <span className="truncate font-semibold">{event.type}</span>
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
