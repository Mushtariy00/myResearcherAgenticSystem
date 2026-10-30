import {
  BanIcon,
  CircleCheckIcon,
  CircleXIcon,
  ClockIcon,
  EyeIcon,
  LoaderCircleIcon,
  type LucideIcon,
  PauseCircleIcon,
  TriangleAlertIcon,
} from "lucide-react";
import type { RunStatus } from "@/client";
import type { Tone } from "@/studio/lib/stages";

export type RunStatusMeta = {
  tone: Tone;
  icon: LucideIcon;
  /** Work is in progress right now: the status dot pulses. */
  live: boolean;
};

/** How a run status looks in Studio (the stage statuses are in src/studio/lib/stages.ts). */
export const RUN_STATUS_META: Record<RunStatus, RunStatusMeta> = {
  queued: { tone: "neutral", icon: ClockIcon, live: true },
  running: { tone: "info", icon: LoaderCircleIcon, live: true },
  awaiting_approval: { tone: "warning", icon: EyeIcon, live: false },
  paused_budget: { tone: "warning", icon: PauseCircleIcon, live: false },
  completed: { tone: "success", icon: CircleCheckIcon, live: false },
  rejected: { tone: "danger", icon: CircleXIcon, live: false },
  failed: { tone: "danger", icon: TriangleAlertIcon, live: false },
  cancelled: { tone: "neutral", icon: BanIcon, live: false },
};

export function runStatusMeta(status: RunStatus): RunStatusMeta {
  return RUN_STATUS_META[status] ?? RUN_STATUS_META.queued;
}
