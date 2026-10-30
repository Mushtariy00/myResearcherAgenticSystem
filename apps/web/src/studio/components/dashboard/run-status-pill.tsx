"use client";

import { useTranslations } from "next-intl";
import type { RunStatus } from "@/client";
import { cn } from "@/lib/utils";
import { PulseDot } from "@/studio/components/effects/pulse-dot";
import type { Tone } from "@/studio/lib/stages";

export const RUN_STATUS_TONES: Record<RunStatus, Tone> = {
  queued: "neutral",
  running: "info",
  awaiting_approval: "warning",
  completed: "success",
  rejected: "danger",
  failed: "danger",
  cancelled: "neutral",
  paused_budget: "warning",
};

/** A run's status as a Studio pill: its tone, a dot that pulses while running, and the label. */
export function RunStatusPill({ status, className }: { status: RunStatus; className?: string }) {
  const t = useTranslations("runStatus");
  const tone = RUN_STATUS_TONES[status] ?? "neutral";
  return (
    <span
      data-tone={tone}
      className={cn(
        "inline-flex h-6 w-fit shrink-0 items-center gap-1.5 rounded-full border border-(--tone)/25 bg-(--tone)/12 px-2 text-xs font-medium whitespace-nowrap text-(--tone-fg)",
        className,
      )}
    >
      <PulseDot tone={tone} live={status === "running"} size="sm" />
      {t(status)}
    </span>
  );
}
