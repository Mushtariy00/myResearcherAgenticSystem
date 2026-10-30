import {
  BookOpenTextIcon,
  CircleDashedIcon,
  CodeXmlIcon,
  FlaskConicalIcon,
  LightbulbIcon,
  type LucideIcon,
  PenLineIcon,
} from "lucide-react";
import type { Stage } from "@/client";
import { isKnownStage } from "./labels";
import { STAGE_ORDER } from "./timeline";

/**
 * How each pipeline stage looks, identical in Classic and Studio: its icon, its colour tokens and
 * its place in the pipeline. The colours are CSS variables (src/app/shared.css, light and dark),
 * which the Studio scope may redefine; nothing hard-codes a stage colour. An element with
 * `data-stage="<stage>"` also gets `--tone` (fill) and `--tone-fg` (text) for that stage.
 */
export type StageMeta = {
  stage: Stage;
  /** 0-based position in the pipeline. */
  order: number;
  icon: LucideIcon;
  /** Fill colour for dots, bars and chart series: `var(--stage-<stage>)`. */
  color: string;
  /** Text-safe colour (at least 4.5:1 on the page background): `var(--stage-<stage>-fg)`. */
  colorFg: string;
  /** The custom property names, for code that reads computed colours (charts, canvas). */
  tokens: { color: `--stage-${Stage}`; colorFg: `--stage-${Stage}-fg` };
};

const ICONS: Record<Stage, LucideIcon> = {
  literature: BookOpenTextIcon,
  method: LightbulbIcon,
  coding: CodeXmlIcon,
  experiment: FlaskConicalIcon,
  writing: PenLineIcon,
};

function describe(stage: Stage, order: number): StageMeta {
  return {
    stage,
    order,
    icon: ICONS[stage],
    color: `var(--stage-${stage})`,
    colorFg: `var(--stage-${stage}-fg)`,
    tokens: { color: `--stage-${stage}`, colorFg: `--stage-${stage}-fg` },
  };
}

/** The pipeline stages in order. */
export const STAGES: readonly Stage[] = STAGE_ORDER;

export const STAGE_META: Readonly<Record<Stage, StageMeta>> = {
  literature: describe("literature", 0),
  method: describe("method", 1),
  coding: describe("coding", 2),
  experiment: describe("experiment", 3),
  writing: describe("writing", 4),
};

/** Icon for stages and anything unknown (a stage added by a newer API). */
export const UNKNOWN_STAGE_ICON: LucideIcon = CircleDashedIcon;

/** Presentation of a stage id from the API, or undefined for stages this UI does not know. */
export function stageMeta(stage: string): StageMeta | undefined {
  return isKnownStage(stage) ? STAGE_META[stage] : undefined;
}

export function stageIcon(stage: string): LucideIcon {
  return stageMeta(stage)?.icon ?? UNKNOWN_STAGE_ICON;
}

/** Pipeline order for sorting; unknown stages go last, in their original order. */
export function compareStages(a: string, b: string): number {
  const left = stageMeta(a)?.order ?? STAGES.length;
  const right = stageMeta(b)?.order ?? STAGES.length;
  return left - right;
}
