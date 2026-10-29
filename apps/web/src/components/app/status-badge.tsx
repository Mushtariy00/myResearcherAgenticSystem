"use client";

import { useTranslations } from "next-intl";
import type { ProjectRole, RunStatus } from "@/client";
import type { TimelineStatus } from "@/lib/timeline";
import { cn } from "@/lib/utils";

type Tone = "neutral" | "info" | "warning" | "success" | "danger";

const TONE_CLASSES: Record<Tone, string> = {
  neutral: "bg-muted text-muted-foreground",
  info: "bg-sky-500/15 text-sky-800 dark:text-sky-300",
  warning: "bg-amber-500/15 text-amber-800 dark:text-amber-300",
  success: "bg-emerald-500/15 text-emerald-800 dark:text-emerald-300",
  danger: "bg-destructive/10 text-destructive dark:bg-destructive/20",
};

const RUN_TONES: Record<RunStatus, Tone> = {
  queued: "neutral",
  running: "info",
  awaiting_approval: "warning",
  completed: "success",
  rejected: "danger",
  failed: "danger",
  cancelled: "neutral",
  paused_budget: "warning",
};

const STAGE_TONES: Record<TimelineStatus, Tone> = {
  pending: "neutral",
  running: "info",
  output_ready: "warning",
  approved: "success",
  changes_requested: "warning",
  rejected: "danger",
  failed: "danger",
  cancelled: "neutral",
  invalidated: "neutral",
  skipped: "neutral",
};

function Pill({ tone, pulse, children }: { tone: Tone; pulse?: boolean; children: string }) {
  return (
    <span
      className={cn(
        "inline-flex h-5 w-fit shrink-0 items-center gap-1.5 rounded-full px-2 text-xs font-medium whitespace-nowrap",
        TONE_CLASSES[tone],
      )}
    >
      <span
        aria-hidden
        className={cn("size-1.5 rounded-full bg-current", pulse && "motion-safe:animate-pulse")}
      />
      {children}
    </span>
  );
}

export function RunStatusBadge({ status }: { status: RunStatus }) {
  const t = useTranslations("runStatus");
  return (
    <Pill tone={RUN_TONES[status] ?? "neutral"} pulse={status === "running"}>
      {t(status)}
    </Pill>
  );
}

export function StageStatusBadge({ status }: { status: TimelineStatus }) {
  const t = useTranslations("stageStatus");
  return (
    <Pill tone={STAGE_TONES[status] ?? "neutral"} pulse={status === "running"}>
      {t(status)}
    </Pill>
  );
}

export function RoleBadge({ role }: { role: ProjectRole | "admin" | "user" | null | undefined }) {
  const t = useTranslations("roles");
  if (!role) {
    return null;
  }
  return (
    <span className="inline-flex h-5 w-fit items-center rounded-full border px-2 text-xs font-medium text-muted-foreground">
      {t(role)}
    </span>
  );
}
