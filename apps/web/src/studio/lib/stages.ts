import {
  BanIcon,
  BookOpenTextIcon,
  CircleCheckIcon,
  CircleDashedIcon,
  CircleMinusIcon,
  CircleSlashIcon,
  CircleXIcon,
  CodeXmlIcon,
  EyeIcon,
  FlaskConicalIcon,
  LightbulbIcon,
  LoaderCircleIcon,
  type LucideIcon,
  PenLineIcon,
  RotateCcwIcon,
  TriangleAlertIcon,
} from "lucide-react";
import { isKnownStage, type KnownStage } from "@/lib/labels";
import type { TimelineStatus } from "@/lib/timeline";

/**
 * Stage and status presentation for Studio. Colours come from CSS: an element with
 * `data-stage="<stage>"` or `data-tone="<tone>"` gets `--tone` (fill) and `--tone-fg` (text)
 * from the Studio block in globals.css.
 */
export const STAGE_ICONS: Record<KnownStage, LucideIcon> = {
  literature: BookOpenTextIcon,
  method: LightbulbIcon,
  coding: CodeXmlIcon,
  experiment: FlaskConicalIcon,
  writing: PenLineIcon,
};

export function stageIcon(stage: string): LucideIcon {
  return isKnownStage(stage) ? STAGE_ICONS[stage] : CircleDashedIcon;
}

/** `data-stage` value: known stages get their colour, anything else stays neutral. */
export function stageAttr(stage: string): KnownStage | undefined {
  return isKnownStage(stage) ? stage : undefined;
}

export type Tone = "neutral" | "info" | "success" | "warning" | "danger";

type StatusMeta = {
  tone: Tone;
  icon: LucideIcon;
  /** Something is happening right now (pulse, beam). */
  live: boolean;
  /** The stage finished with an output that later stages may use. */
  done: boolean;
  /** Waiting for a person: review, or rework after a change request. */
  attention: boolean;
  /**
   * Steps back: cancelled, outdated or never run (a dashed outline and neutral colours; the
   * text keeps its full contrast, so never use opacity for it).
   */
  dimmed: boolean;
};

export const STATUS_META: Record<TimelineStatus, StatusMeta> = {
  pending: {
    tone: "neutral",
    icon: CircleDashedIcon,
    live: false,
    done: false,
    attention: false,
    dimmed: false,
  },
  running: {
    tone: "info",
    icon: LoaderCircleIcon,
    live: true,
    done: false,
    attention: false,
    dimmed: false,
  },
  output_ready: {
    tone: "warning",
    icon: EyeIcon,
    live: false,
    done: false,
    attention: true,
    dimmed: false,
  },
  approved: {
    tone: "success",
    icon: CircleCheckIcon,
    live: false,
    done: true,
    attention: false,
    dimmed: false,
  },
  changes_requested: {
    tone: "warning",
    icon: RotateCcwIcon,
    live: false,
    done: false,
    attention: true,
    dimmed: false,
  },
  rejected: {
    tone: "danger",
    icon: CircleXIcon,
    live: false,
    done: false,
    attention: false,
    dimmed: false,
  },
  failed: {
    tone: "danger",
    icon: TriangleAlertIcon,
    live: false,
    done: false,
    attention: false,
    dimmed: false,
  },
  cancelled: {
    tone: "neutral",
    icon: BanIcon,
    live: false,
    done: false,
    attention: false,
    dimmed: true,
  },
  invalidated: {
    tone: "neutral",
    icon: CircleSlashIcon,
    live: false,
    done: false,
    attention: false,
    dimmed: true,
  },
  skipped: {
    tone: "neutral",
    icon: CircleMinusIcon,
    live: false,
    done: false,
    attention: false,
    dimmed: true,
  },
};

export function statusMeta(status: TimelineStatus): StatusMeta {
  return STATUS_META[status] ?? STATUS_META.pending;
}

/**
 * How the beam between two neighbouring stages looks: `flowing` while the approved output of
 * the first feeds the running second, `complete` once data has moved on, `idle` otherwise.
 */
export type BeamState = "idle" | "complete" | "flowing";

export function beamState(from: TimelineStatus, to: TimelineStatus): BeamState {
  if (from !== "approved") {
    return "idle";
  }
  if (to === "running") {
    return "flowing";
  }
  return to === "pending" || to === "skipped" || to === "cancelled" ? "idle" : "complete";
}
