"use client";

import {
  ActivityIcon,
  ArrowDownIcon,
  BracesIcon,
  ChevronRightIcon,
  CircleCheckIcon,
  CircleSlashIcon,
  CircleXIcon,
  CpuIcon,
  EyeIcon,
  type LucideIcon,
  MessageSquareIcon,
  PlayIcon,
  RotateCcwIcon,
  SparklesIcon,
  TerminalIcon,
  TriangleAlertIcon,
} from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { RunEvent } from "@/lib/run-events";
import { cn } from "@/lib/utils";
import { AnimatedList } from "@/studio/components/effects/animated-list";
import { GlassCard } from "@/studio/components/effects/glass-card";
import { stageAttr } from "@/studio/lib/stages";
import { type EventGroup, type EventKind, type EventLine, useEventDescriber } from "./event-lines";
import { useRunPage } from "./run-context";
import { shortId } from "./run-helpers";
import { RUN_LOG_ID, StreamStatePill } from "./run-hero";
import { SMALL_BUTTON, TOGGLE_BUTTON } from "./run-ui";
import { useRunLabels } from "./use-run-labels";

/** Lines shown at once; older ones come in pages of the same size. */
export const LOG_PAGE_SIZE = 120;

type LogFilter = "all" | EventGroup;

const FILTERS: readonly LogFilter[] = ["all", "stages", "llm"];

const KIND_ICONS: Record<EventKind, LucideIcon> = {
  created: SparklesIcon,
  status: ActivityIcon,
  started: PlayIcon,
  progress: ChevronRightIcon,
  ready: EyeIcon,
  decided: MessageSquareIcon,
  failed: TriangleAlertIcon,
  invalidated: CircleSlashIcon,
  retried: RotateCcwIcon,
  llm: CpuIcon,
  log: ChevronRightIcon,
  raw: BracesIcon,
};

type LogItem = { seq: number; at: string; time: string; line: EventLine };

function iconOf(line: EventLine): LucideIcon {
  if (line.kind === "decided") {
    return line.tone === "success"
      ? CircleCheckIcon
      : line.tone === "danger"
        ? CircleXIcon
        : MessageSquareIcon;
  }
  return KIND_ICONS[line.kind];
}

/**
 * The run's live events as a terminal: translated lines slide in at the bottom (AnimatedList)
 * and the view follows them unless the reader scrolls up ("Jump to the latest line" brings it
 * back). Lines can be narrowed to stage progress or to model calls, and the newest
 * LOG_PAGE_SIZE are shown, with earlier ones a click away. The terminal stays dark in both
 * themes: it takes Studio's dark tokens (contrast checked) through its own scope.
 */
export function RunLog() {
  const { run, view } = useRunPage();
  const t = useTranslations("studioRun.log");
  const format = useFormatter();
  const describe = useEventDescriber();
  const titleId = useId();
  const viewport = useRef<HTMLElement>(null);
  const [filter, setFilter] = useState<LogFilter>("all");
  const [limit, setLimit] = useState(LOG_PAGE_SIZE);
  const [following, setFollowing] = useState(true);

  // Events keep their identity as the log grows, so each one is described once per language.
  // biome-ignore lint/correctness/useExhaustiveDependencies: another language starts a new cache
  const described = useMemo(() => new WeakMap<RunEvent, LogItem>(), [describe, format]);
  const items = useMemo<LogItem[]>(
    () =>
      view.events.map((event) => {
        const known = described.get(event);
        if (known) {
          return known;
        }
        const item: LogItem = {
          seq: event.seq,
          at: event.created_at,
          time: event.created_at
            ? format.dateTime(new Date(event.created_at), {
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
                hourCycle: "h23",
              })
            : `#${event.seq}`,
          line: describe(event),
        };
        described.set(event, item);
        return item;
      }),
    [view.events, described, describe, format],
  );
  const counts = useMemo(() => {
    const result: Record<LogFilter, number> = { all: items.length, stages: 0, llm: 0 };
    for (const item of items) {
      result[item.line.group] += 1;
    }
    return result;
  }, [items]);
  const matching = useMemo(
    () => (filter === "all" ? items : items.filter((item) => item.line.group === filter)),
    [items, filter],
  );
  const visible = matching.length > limit ? matching.slice(matching.length - limit) : matching;
  const earlier = matching.length - visible.length;
  const newest = visible.at(-1)?.seq ?? 0;
  const live = view.streamState === "live" && !view.finished;

  // biome-ignore lint/correctness/useExhaustiveDependencies: follow new lines and filter changes
  useEffect(() => {
    const element = viewport.current;
    if (element && following) {
      element.scrollTop = element.scrollHeight;
    }
  }, [newest, filter, following]);

  function jumpToLatest() {
    setFollowing(true);
    const element = viewport.current;
    if (element) {
      element.scrollTop = element.scrollHeight;
    }
  }

  return (
    <section
      id={RUN_LOG_ID}
      aria-labelledby={titleId}
      className="min-w-0 scroll-mt-20 2xl:sticky 2xl:top-20"
    >
      <GlassCard className="grid min-w-0 gap-3 p-4 sm:p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2
            id={titleId}
            className="flex items-center gap-2 text-base font-semibold tracking-tight text-foreground"
          >
            <TerminalIcon aria-hidden className="size-4.5 text-(--studio-accent-fg)" />
            {t("title")}
          </h2>
          <StreamStatePill />
        </div>
        <fieldset className="flex min-w-0 flex-wrap gap-1">
          <legend className="sr-only">{t("filter")}</legend>
          {FILTERS.map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={filter === value}
              onClick={() => {
                setFilter(value);
                setLimit(LOG_PAGE_SIZE);
                setFollowing(true);
              }}
              className={TOGGLE_BUTTON}
            >
              {t(`filters.${value}`)}
              <span className="text-muted-foreground tabular-nums">
                {format.number(counts[value])}
              </span>
            </button>
          ))}
        </fieldset>

        <div
          data-ui="studio"
          className="dark relative min-w-0 overflow-hidden rounded-xl border border-(--studio-glass-border) bg-background text-foreground shadow-[inset_0_1px_0_0_var(--studio-glass-highlight)]"
        >
          <div className="flex items-center gap-2 border-b border-(--studio-glass-border) px-3 py-2">
            <span aria-hidden className="flex shrink-0 gap-1.5">
              <span className="size-2.5 rounded-full bg-(--studio-danger)/70" />
              <span className="size-2.5 rounded-full bg-(--studio-warning)/70" />
              <span className="size-2.5 rounded-full bg-(--studio-success)/70" />
            </span>
            <span className="min-w-0 flex-1 truncate font-mono text-[0.7rem] text-muted-foreground">
              {t("terminal", { run: shortId(run.id) })}
            </span>
            <span className="shrink-0 font-mono text-[0.7rem] text-muted-foreground tabular-nums">
              {t("lines", { count: matching.length })}
            </span>
          </div>
          <section
            ref={viewport}
            aria-label={t("scroll")}
            // biome-ignore lint/a11y/noNoninteractiveTabindex: keyboard users must be able to scroll the log
            tabIndex={0}
            onScroll={(event) => {
              const element = event.currentTarget;
              setFollowing(element.scrollHeight - element.scrollTop - element.clientHeight < 24);
            }}
            className="max-h-[26rem] min-h-40 overflow-y-auto overscroll-contain font-mono text-xs leading-5 outline-none focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:ring-inset"
          >
            {earlier > 0 && (
              <div className="px-3 pt-2">
                <button
                  type="button"
                  onClick={() => setLimit((value) => value + LOG_PAGE_SIZE)}
                  className={cn(SMALL_BUTTON, "h-7 w-full font-sans")}
                >
                  {t("earlier", { count: Math.min(earlier, LOG_PAGE_SIZE) })}
                </button>
              </div>
            )}
            {visible.length === 0 ? (
              <p className="px-4 py-4 text-muted-foreground">
                {view.events.length === 0 ? t("empty") : t("emptyFiltered")}
              </p>
            ) : (
              <AnimatedList
                as="ol"
                live
                enterFrom="bottom"
                aria-label={t("title")}
                items={visible}
                getKey={(item) => item.seq}
                className="gap-px p-2"
                itemClassName="min-w-0"
                renderItem={(item) => <LogLine item={item} />}
              />
            )}
            {live && (
              <div aria-hidden className="flex items-center gap-2 px-4 pb-3 text-muted-foreground">
                <span>›</span>
                <span className="inline-block h-3.5 w-1.5 animate-pulse bg-(--studio-success) motion-reduce:animate-none" />
              </div>
            )}
          </section>
          {!following && visible.length > 0 && (
            <button
              type="button"
              onClick={jumpToLatest}
              className={cn(SMALL_BUTTON, "absolute right-3 bottom-3 font-sans shadow-lg")}
            >
              <ArrowDownIcon aria-hidden />
              {t("jumpToLatest")}
            </button>
          )}
        </div>
      </GlassCard>
    </section>
  );
}

function LogLine({ item }: { item: LogItem }) {
  const labels = useRunLabels();
  const { line } = item;
  const Icon = iconOf(line);
  return (
    <div className="grid grid-cols-[auto_auto_minmax(0,1fr)] items-baseline gap-x-2 rounded-md px-2 py-0.5 transition-colors hover:bg-(--studio-hover) motion-reduce:transition-none">
      <time dateTime={item.at || undefined} className="text-muted-foreground tabular-nums">
        {item.time}
      </time>
      <span data-tone={line.tone} className="text-(--tone-fg)">
        <Icon aria-hidden className="size-3 translate-y-0.5" />
      </span>
      <span className="min-w-0 break-words">
        {line.stage && (
          <span
            data-stage={stageAttr(line.stage)}
            className="mr-2 text-[var(--tone-fg,var(--muted-foreground))]"
          >
            {labels.stage(line.stage)}
          </span>
        )}
        <span className={line.tone === "danger" ? "text-(--studio-danger-fg)" : "text-foreground"}>
          {line.text}
        </span>
        {line.detail && <span className="text-muted-foreground"> · {line.detail}</span>}
      </span>
    </div>
  );
}
