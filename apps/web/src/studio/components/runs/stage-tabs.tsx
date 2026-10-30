"use client";

import { HourglassIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { StageIcon } from "@/components/shared/stage-icon";
import type { TimelineStatus } from "@/lib/timeline";
import {
  AnimatedTabs,
  AnimatedTabsList,
  AnimatedTabsPanel,
  AnimatedTabsTab,
} from "@/studio/components/effects/animated-tabs";
import { PulseDot } from "@/studio/components/effects/pulse-dot";
import { stageAttr, statusMeta } from "@/studio/lib/stages";
import { useRunPage } from "./run-context";
import { StagePanel } from "./stage-panel";
import { useRunLabels } from "./use-run-labels";

export const STAGE_SECTION_ID = "run-stages";

/**
 * A small mark after the stage name: pulsing while running, an hourglass while the running
 * stage waits to try again (the panel says why), a dot while a person is needed.
 */
function TabStatus({ status, waiting }: { status: TimelineStatus; waiting: boolean }) {
  const t = useTranslations("stageStatus");
  const tEvents = useTranslations("run.events.types.stage");
  const meta = statusMeta(status);
  const shown =
    meta.live || meta.attention || meta.done || status === "failed" || status === "rejected";
  if (waiting) {
    return (
      <>
        <HourglassIcon aria-hidden data-tone="warning" className="size-3 text-(--tone-fg)" />
        <span className="sr-only">
          , {t(status)}, {tEvents("waiting")}
        </span>
      </>
    );
  }
  return (
    <>
      {shown &&
        (meta.live ? (
          <PulseDot tone={meta.tone} live size="sm" />
        ) : (
          <span
            aria-hidden
            data-tone={meta.tone}
            className="inline-flex size-1.5 rounded-full bg-(--tone)"
          />
        ))}
      <span className="sr-only">, {t(status)}</span>
    </>
  );
}

/**
 * The stage outputs: one tab per stage in stage colours (with its status), and the selected
 * stage's panel. Arrow keys move between tabs; the selection lives in the URL (`?stage=`).
 */
export function StageTabs() {
  const { view, activeStage, selectStage } = useRunPage();
  const t = useTranslations("studioRun.tabs");
  const labels = useRunLabels();
  return (
    <section
      id={STAGE_SECTION_ID}
      aria-labelledby={`${STAGE_SECTION_ID}-title`}
      className="grid min-w-0 scroll-mt-20 gap-4"
    >
      <h2 id={`${STAGE_SECTION_ID}-title`} className="sr-only">
        {t("title")}
      </h2>
      <AnimatedTabs value={activeStage} onValueChange={selectStage} className="grid min-w-0 gap-4">
        <AnimatedTabsList aria-label={t("label")} className="justify-self-start">
          {view.timeline.map((entry) => (
            <AnimatedTabsTab
              key={entry.stage}
              value={entry.stage}
              stage={stageAttr(entry.stage)}
              className="h-9"
            >
              <StageIcon stage={entry.stage} />
              <span>{labels.stage(entry.stage)}</span>
              <TabStatus
                status={entry.status}
                waiting={entry.status === "running" && entry.stage in view.waits}
              />
            </AnimatedTabsTab>
          ))}
        </AnimatedTabsList>
        {view.timeline.map((entry) => (
          <AnimatedTabsPanel key={entry.stage} value={entry.stage} className="min-w-0 rounded-2xl">
            <StagePanel entry={entry} />
          </AnimatedTabsPanel>
        ))}
      </AnimatedTabs>
    </section>
  );
}
