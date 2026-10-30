"use client";

import { PauseIcon, PlayIcon } from "lucide-react";
import { useInView } from "motion/react";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import type { KnownStage } from "@/lib/labels";
import { STAGE_ORDER, type TimelineStatus } from "@/lib/timeline";
import { cn } from "@/lib/utils";
import { GlassCard } from "@/studio/components/effects/glass-card";
import { PulseDot } from "@/studio/components/effects/pulse-dot";
import { PipelineGraph, type PipelineNode } from "@/studio/components/pipeline-graph";
import { useReducedMotionPreference } from "@/studio/hooks/use-media-query";

type Caption = "running" | "review" | "changes" | "approved" | "done";
type Step = { statuses: TimelineStatus[]; caption: Caption; stage: KnownStage; attempt?: number };

const P = "pending";
const R = "running";
const O = "output_ready";
const A = "approved";
const C = "changes_requested";

/** A scripted run: every stage waits for a person, and the method stage gets one revision. */
const SCRIPT: readonly Step[] = [
  { statuses: [R, P, P, P, P], caption: "running", stage: "literature" },
  { statuses: [O, P, P, P, P], caption: "review", stage: "literature" },
  { statuses: [A, R, P, P, P], caption: "approved", stage: "literature" },
  { statuses: [A, O, P, P, P], caption: "review", stage: "method" },
  { statuses: [A, C, P, P, P], caption: "changes", stage: "method" },
  { statuses: [A, R, P, P, P], caption: "running", stage: "method", attempt: 2 },
  { statuses: [A, O, P, P, P], caption: "review", stage: "method", attempt: 2 },
  { statuses: [A, A, R, P, P], caption: "approved", stage: "method", attempt: 2 },
  { statuses: [A, A, O, P, P], caption: "review", stage: "coding" },
  { statuses: [A, A, A, R, P], caption: "approved", stage: "coding" },
  { statuses: [A, A, A, O, P], caption: "review", stage: "experiment" },
  { statuses: [A, A, A, A, R], caption: "approved", stage: "experiment" },
  { statuses: [A, A, A, A, O], caption: "review", stage: "writing" },
  { statuses: [A, A, A, A, A], caption: "done", stage: "writing" },
];

/** Shown instead of the cycle with reduced motion: a run in full swing. */
const STILL_STEP = 9;
const STEP_MS = 1900;
const LAST_STEP_MS = 4200;

function nodesFor(step: Step): PipelineNode[] {
  return STAGE_ORDER.map((stage, index) => ({
    stage,
    status: step.statuses[index] ?? "pending",
    attempts: stage === "method" && step.attempt ? step.attempt : undefined,
  }));
}

/**
 * The landing page's animated pipeline: an illustrative run cycling through the statuses a real
 * run goes through. It is labelled as an example (no live data), pauses while off screen, does
 * not play with reduced motion, and has a pause button (content that changes on its own must be
 * stoppable). Pause freezes the step on screen, loops included, and Play carries on from it.
 */
export function PipelineDemo() {
  const t = useTranslations();
  const reduced = useReducedMotionPreference();
  const root = useRef<HTMLDivElement>(null);
  const inView = useInView(root, { initial: true, margin: "-10% 0px" });
  const [paused, setPaused] = useState(false);
  const [step, setStep] = useState(0);
  const playing = !reduced && !paused;
  const shown = reduced ? STILL_STEP : step;
  const current = SCRIPT[shown] ?? SCRIPT[0];

  useEffect(() => {
    if (!playing || !inView) {
      return;
    }
    const delay = step === SCRIPT.length - 1 ? LAST_STEP_MS : STEP_MS;
    const timer = window.setTimeout(() => setStep((value) => (value + 1) % SCRIPT.length), delay);
    return () => window.clearTimeout(timer);
  }, [playing, inView, step]);

  if (!current) {
    return null;
  }
  const stageName = t(`stages.${current.stage}`);
  const caption =
    current.caption === "done"
      ? t("studio.landing.demo.steps.done")
      : t(`studio.landing.demo.steps.${current.caption}`, { stage: stageName });
  const live = current.statuses.includes("running");

  return (
    <GlassCard ref={root} className="w-full p-4 sm:p-6">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3 sm:mb-6">
        <div className="min-w-0">
          <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            {t("studio.landing.demo.label")}
          </p>
          <p className="truncate text-sm font-semibold text-foreground">
            {t("studio.landing.demo.topic")}
          </p>
        </div>
        {!reduced && (
          <button
            type="button"
            onClick={() => setPaused((value) => !value)}
            className="inline-flex h-8 items-center gap-1.5 rounded-[10px] border border-(--studio-glass-border) bg-(--studio-glass) px-2.5 text-xs font-medium text-muted-foreground transition-colors outline-none hover:bg-(--studio-hover) hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            {paused ? (
              <PlayIcon aria-hidden className="size-3.5" />
            ) : (
              <PauseIcon aria-hidden className="size-3.5" />
            )}
            {paused ? t("studio.landing.demo.play") : t("studio.landing.demo.pause")}
          </button>
        )}
      </div>
      <PipelineGraph nodes={nodesFor(current)} size="large" paused={!playing} />
      <div className="mt-4 flex min-h-6 items-center gap-2 text-sm text-muted-foreground sm:mt-6">
        <PulseDot
          tone={current.caption === "done" ? "success" : live ? "info" : "warning"}
          live={live && playing}
        />
        {/* A new step remounts the caption (fade in); pausing and playing leave it in place. */}
        <p
          key={shown}
          className={cn("min-w-0 truncate", !reduced && "animate-in fade-in-0 duration-300")}
        >
          {caption}
        </p>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">{t("studio.landing.demo.caption")}</p>
    </GlassCard>
  );
}
