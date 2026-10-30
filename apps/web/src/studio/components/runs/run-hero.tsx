"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeftIcon,
  CalendarClockIcon,
  CpuIcon,
  GaugeIcon,
  HashIcon,
  RotateCwIcon,
  TerminalIcon,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { useFormatter, useTranslations } from "next-intl";
import { useMemo } from "react";
import { listProjectsOptions } from "@/client/@tanstack/react-query.gen";
import { CopyButton } from "@/components/shared/copy-button";
import { DemoBadge } from "@/components/shared/demo-badge";
import type { StreamState } from "@/hooks/use-run-events";
import { toAmount, USD } from "@/lib/format";
import { cn } from "@/lib/utils";
import { PulseDot } from "@/studio/components/effects/pulse-dot";
import { nodesFromTimeline, PipelineGraph } from "@/studio/components/pipeline-graph";
import { FADE } from "@/studio/lib/motion";
import { studioProjectPath } from "@/studio/lib/nav";
import { stageAttr, type Tone } from "@/studio/lib/stages";
import { useEventDescriber } from "./event-lines";
import { RunActions } from "./run-actions";
import { useRunPage } from "./run-context";
import { shortId } from "./run-helpers";
import { SpendTile } from "./run-spend";
import { runStatusMeta } from "./run-status";
import { SMALL_BUTTON } from "./run-ui";
import { useRunLabels } from "./use-run-labels";

export const RUN_LOG_ID = "run-log";

/**
 * The top of the run page: the project link and the run's actions, its status and the live
 * stream, the topic as the page title, when it started, its model policy and cost cap, the live
 * spend, and the large pipeline graph (selecting a stage shows its output) with the newest event.
 * A soft glow behind it takes the colour of the stage on screen.
 */
export function RunHero() {
  const { run, view, activeStage, showStage } = useRunPage();
  const t = useTranslations();
  const labels = useRunLabels();
  const projects = useQuery(listProjectsOptions());
  const projectName = projects.data?.find((project) => project.id === run.project_id)?.name;
  const meta = runStatusMeta(run.status);
  const StatusIcon = meta.icon;
  const nodes = useMemo(() => nodesFromTimeline(view.timeline), [view.timeline]);
  const demo = view.timeline.some((entry) => entry.demo);

  return (
    <section
      aria-labelledby="run-title"
      className="studio-glass relative isolate grid min-w-0 gap-6 rounded-3xl p-4 sm:p-6 lg:p-8"
    >
      <span
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10 overflow-hidden rounded-[inherit]"
      >
        <span
          data-stage={stageAttr(activeStage)}
          className="absolute -top-48 -right-40 size-[34rem] rounded-full bg-[radial-gradient(closest-side,color-mix(in_oklch,var(--tone,var(--aurora-violet))_22%,transparent),transparent)]"
        />
        <span className="absolute -bottom-56 -left-48 size-[30rem] rounded-full bg-[radial-gradient(closest-side,color-mix(in_oklch,var(--aurora-indigo)_12%,transparent),transparent)]" />
      </span>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link
          href={studioProjectPath(run.project_id)}
          className="inline-flex max-w-full min-w-0 items-center gap-1.5 rounded-md text-sm font-medium text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          <ArrowLeftIcon aria-hidden className="size-4 shrink-0" />
          <span className="truncate">
            {projectName
              ? t("studioRun.hero.backTo", { project: projectName })
              : t("run.backToProject")}
          </span>
        </Link>
        <RunActions />
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
        <div className="grid min-w-0 content-start gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <span
              data-tone={meta.tone}
              className="inline-flex h-7 items-center gap-2 rounded-full border border-(--tone)/25 bg-(--tone)/12 px-3 text-xs font-semibold text-(--tone-fg)"
            >
              {meta.live ? (
                <PulseDot tone={meta.tone} live size="sm" />
              ) : (
                <StatusIcon aria-hidden className="size-3.5" />
              )}
              <span className="sr-only">{t("studioRun.hero.status")}: </span>
              {labels.runStatus(run.status)}
            </span>
            <StreamStatePill />
            {demo && <DemoBadge demo />}
          </div>
          <h1
            id="run-title"
            className="studio-display text-2xl break-words text-foreground sm:text-3xl lg:text-[2.5rem]"
          >
            {run.topic}
          </h1>
          <RunFacts />
        </div>
        <SpendTile />
      </div>

      <div className="grid min-w-0 gap-3">
        <PipelineGraph
          nodes={nodes}
          size="large"
          onSelect={showStage}
          selectedStage={activeStage}
          aria-label={t("studioRun.pipeline.label")}
        />
        <LatestEvent />
      </div>
    </section>
  );
}

/** When the run started, its model policy, its cost cap and its id. */
function RunFacts() {
  const { run } = useRunPage();
  const t = useTranslations();
  const format = useFormatter();
  const fact =
    "flex min-w-0 items-center gap-1.5 [&_svg]:size-3.5 [&_svg]:shrink-0 [&_svg]:text-muted-foreground";
  return (
    <dl className="flex flex-wrap items-center gap-x-5 gap-y-1.5 text-sm text-muted-foreground">
      <div className={fact}>
        <dt className="sr-only">{t("studioRun.hero.started")}</dt>
        <CalendarClockIcon aria-hidden />
        <dd>
          <time dateTime={run.created_at}>
            {t("run.meta.created", {
              date: format.dateTime(new Date(run.created_at), {
                dateStyle: "medium",
                timeStyle: "short",
              }),
            })}
          </time>
        </dd>
      </div>
      <div className={fact}>
        <dt className="sr-only">{t("studioRun.hero.models")}</dt>
        <CpuIcon aria-hidden />
        <dd>{t("run.meta.policy", { policy: t(`studioRun.hero.policies.${run.llm_policy}`) })}</dd>
      </div>
      <div className={fact}>
        <dt className="sr-only">{t("studioRun.hero.cap")}</dt>
        <GaugeIcon aria-hidden />
        <dd>
          {run.budget_cap_usd === null
            ? t("run.meta.noCap")
            : t("run.meta.cap", { amount: format.number(toAmount(run.budget_cap_usd), USD) })}
        </dd>
      </div>
      <div className={fact}>
        <dt className="sr-only">{t("studioRun.hero.runId")}</dt>
        <HashIcon aria-hidden />
        <dd className="flex items-center gap-1 font-mono text-xs">
          <span title={run.id}>{shortId(run.id)}</span>
          <CopyButton value={run.id} label={t("studioRun.hero.copyRunId")} size="icon-xs" />
        </dd>
      </div>
    </dl>
  );
}

const STREAM_TONES: Record<StreamState, Tone> = {
  connecting: "neutral",
  live: "success",
  reconnecting: "warning",
  ended: "neutral",
  error: "danger",
};

/** Whether live updates arrive; a way to reconnect once the browser has given up. */
export function StreamStatePill({ className }: { className?: string }) {
  const { view } = useRunPage();
  const t = useTranslations("run.events");
  const state = view.streamState;
  if (view.finished && (state === "ended" || state === "live")) {
    return null;
  }
  const tone = STREAM_TONES[state];
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <span
        data-tone={tone}
        className="inline-flex h-7 items-center gap-2 rounded-full border border-(--tone)/25 bg-(--tone)/12 px-3 text-xs font-medium text-(--tone-fg)"
      >
        <PulseDot tone={tone} live={state === "live"} size="sm" />
        {t(`state.${state}`)}
      </span>
      {state === "error" && (
        <button type="button" onClick={view.reconnect} className={SMALL_BUTTON}>
          <RotateCwIcon aria-hidden />
          {t("reconnect")}
        </button>
      )}
    </span>
  );
}

/** The newest event under the pipeline, sliding in as it arrives; a link to the full log. */
function LatestEvent() {
  const { view } = useRunPage();
  const t = useTranslations("studioRun.pipeline");
  const labels = useRunLabels();
  const describe = useEventDescriber();
  const last = view.events.at(-1);
  if (!last) {
    return null;
  }
  const line = describe(last);
  const live = view.streamState === "live" && !view.finished;
  return (
    <div className="flex min-w-0 items-center gap-3 rounded-xl border border-(--studio-glass-border) bg-(--studio-glass) px-3 py-2">
      <PulseDot tone={live ? "info" : "neutral"} live={live} size="sm" />
      <div className="relative min-w-0 flex-1 overflow-hidden">
        <AnimatePresence initial={false} mode="popLayout">
          <motion.p
            key={last.seq}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={FADE}
            className="truncate text-sm text-foreground"
          >
            {line.stage && (
              <span data-stage={stageAttr(line.stage)} className="font-medium text-(--tone-fg)">
                {labels.stage(line.stage)}
                {" · "}
              </span>
            )}
            {line.text}
          </motion.p>
        </AnimatePresence>
      </div>
      <a
        href={`#${RUN_LOG_ID}`}
        className="inline-flex shrink-0 items-center gap-1.5 rounded-md text-xs font-medium text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        <TerminalIcon aria-hidden className="size-3.5" />
        <span className="hidden sm:inline">{t("viewLog")}</span>
        <span className="sr-only sm:hidden">{t("viewLog")}</span>
      </a>
    </div>
  );
}
