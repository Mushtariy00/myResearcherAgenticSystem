"use client";

import { useInView } from "motion/react";
import { useTranslations } from "next-intl";
import { type CSSProperties, useRef } from "react";
import { isKnownStage } from "@/lib/labels";
import type { TimelineEntry, TimelineStatus } from "@/lib/timeline";
import { cn } from "@/lib/utils";
import { beamState, stageAttr, stageIcon, statusMeta } from "@/studio/lib/stages";
import { BorderBeam } from "./effects/border-beam";
import { PulseDot } from "./effects/pulse-dot";

export type PipelineNode = {
  stage: string;
  status: TimelineStatus;
  /** Attempts so far; shown from the second one (a change request starts a new attempt). */
  attempts?: number;
};

type Orientation = "auto" | "horizontal" | "vertical";
type Size = "compact" | "large";

export type PipelineGraphProps = {
  /** The stages in pipeline order (see `nodesFromTimeline`). */
  nodes: readonly PipelineNode[];
  /** `large` for the landing hero and the run header; `compact` for lists and tiles. */
  size?: Size;
  /** `auto` stacks the stages vertically when the graph is narrower than 48rem (large only). */
  orientation?: Orientation;
  /** Makes each stage a button; called with the stage id. */
  onSelect?: (stage: string) => void;
  /** The stage whose details are open (shown as pressed). */
  selectedStage?: string | null;
  /** Freezes the loops (border beam, pulse, flowing particles), e.g. while a demo is paused. */
  paused?: boolean;
  "aria-label"?: string;
  className?: string;
};

/** PipelineGraph nodes from the run timeline (src/lib/timeline.ts). */
export function nodesFromTimeline(entries: readonly TimelineEntry[]): PipelineNode[] {
  return entries.map((entry) => ({
    stage: entry.stage,
    status: entry.status,
    attempts: entry.latest?.attempt ?? entry.attempts,
  }));
}

/* Tailwind needs whole class names, so each orientation spells out its classes. */
const LIST: Record<Size, Record<Orientation, string>> = {
  large: {
    horizontal: "grid grid-cols-5 gap-8",
    vertical: "grid grid-cols-1 gap-5",
    auto: "grid grid-cols-1 gap-5 @3xl/pipeline:grid-cols-5 @3xl/pipeline:gap-8",
  },
  compact: {
    horizontal: "flex items-center gap-5",
    vertical: "flex flex-col items-start gap-4",
    auto: "flex items-center gap-5",
  },
};

/* In five columns every node fills its row, so the beams line up and the pills sit level. */
const NODE_LAYOUT: Record<Orientation, string> = {
  horizontal: "h-full flex-col items-start gap-3 p-4",
  vertical: "flex-row items-center gap-3 p-3",
  auto: "flex-row items-center gap-3 p-3 @3xl/pipeline:h-full @3xl/pipeline:flex-col @3xl/pipeline:items-start @3xl/pipeline:p-4",
};

/* In a row the stage name keeps room for itself; a long status wraps inside its pill instead. */
const NAME_LAYOUT: Record<Orientation, string> = {
  horizontal: "min-w-0",
  vertical: "min-w-20",
  auto: "min-w-20 @3xl/pipeline:min-w-0",
};

/* In five columns a long status ("Changes requested") wraps onto a second line, so the slot
   always holds two (2 × 1rem lines, py-0.5, 1px borders): the graph keeps its height as the
   statuses change. In a row the 40px icon tile already leaves room, so the slot steps aside. */
const STATUS_SLOT: Record<Orientation, string> = {
  horizontal: "flex min-h-[2.375rem] max-w-full items-end",
  vertical: "contents",
  auto: "contents @3xl/pipeline:flex @3xl/pipeline:min-h-[2.375rem] @3xl/pipeline:max-w-full @3xl/pipeline:items-end",
};

const BEAM_POSITION: Record<Size, Record<Orientation, string>> = {
  large: {
    horizontal: "top-1/2 left-full h-3 w-8 -translate-y-1/2",
    vertical: "top-full left-8 h-5 w-3 -translate-x-1/2",
    auto: "top-full left-8 h-5 w-3 -translate-x-1/2 @3xl/pipeline:top-1/2 @3xl/pipeline:left-full @3xl/pipeline:h-3 @3xl/pipeline:w-8 @3xl/pipeline:translate-x-0 @3xl/pipeline:-translate-y-1/2",
  },
  compact: {
    horizontal: "top-1/2 left-full h-3 w-5 -translate-y-1/2",
    vertical: "top-full left-3.5 h-4 w-3 -translate-x-1/2",
    auto: "top-1/2 left-full h-3 w-5 -translate-y-1/2",
  },
};

function axisOf(size: Size, orientation: Orientation): "x" | "y" | "auto" {
  if (orientation === "vertical") {
    return "y";
  }
  return orientation === "horizontal" || size === "compact" ? "x" : "auto";
}

function stageColor(stage: string): string {
  return isKnownStage(stage) ? `var(--stage-${stage})` : "var(--studio-neutral)";
}

/**
 * The five pipeline stages in order, coloured by stage and showing each status: waiting,
 * running (pulsing dot and a beam around the node), needs review, approved, changes requested,
 * rejected, failed, cancelled, outdated or not run. Stages that were cancelled, never ran or
 * are outdated step back (dashed outline, neutral colours) without fading their text. Beams
 * between stages fill with colour once an approved output has moved on, and particles flow
 * along them while the next stage runs.
 *
 * Accessible as an ordered list: every node says "<stage>: <status>" in text, the stage being
 * worked on is `aria-current="step"`, and with `onSelect` the nodes are focusable buttons.
 * Loops pause while the graph is off screen or `paused`; reduced motion stills them all.
 */
export function PipelineGraph({
  nodes,
  size = "large",
  orientation = "auto",
  onSelect,
  selectedStage,
  paused = false,
  "aria-label": ariaLabel,
  className,
}: PipelineGraphProps) {
  const t = useTranslations();
  const root = useRef<HTMLDivElement>(null);
  const inView = useInView(root, { initial: true });
  const axis = axisOf(size, orientation);

  return (
    <div
      ref={root}
      data-pipeline-axis={axis}
      data-paused={paused || !inView ? "true" : undefined}
      className={cn("@container/pipeline w-full min-w-0", className)}
    >
      <ol aria-label={ariaLabel ?? t("studio.pipeline.label")} className={LIST[size][orientation]}>
        {nodes.map((node, index) => {
          const next = nodes[index + 1];
          const meta = statusMeta(node.status);
          const current = meta.live || node.status === "output_ready";
          const stageLabel = isKnownStage(node.stage) ? t(`stages.${node.stage}`) : node.stage;
          const statusLabel = t(`stageStatus.${node.status}`);
          const attempt =
            node.attempts && node.attempts > 1
              ? t("studio.pipeline.attempt", { attempt: node.attempts })
              : null;
          const spoken = [
            t("studio.pipeline.node", { stage: stageLabel, status: statusLabel }),
            attempt,
          ]
            .filter(Boolean)
            .join(", ");
          return (
            <li
              key={node.stage}
              data-stage={stageAttr(node.stage)}
              data-status={node.status}
              aria-current={current ? "step" : undefined}
              className="relative min-w-0"
            >
              {size === "large" ? (
                <LargeNode
                  node={node}
                  index={index}
                  orientation={orientation}
                  stageLabel={stageLabel}
                  statusLabel={statusLabel}
                  attempt={attempt}
                  spoken={spoken}
                  onSelect={onSelect}
                  selected={selectedStage === undefined ? undefined : selectedStage === node.stage}
                />
              ) : (
                <CompactNode
                  node={node}
                  index={index}
                  spoken={spoken}
                  onSelect={onSelect}
                  selected={selectedStage === undefined ? undefined : selectedStage === node.stage}
                />
              )}
              {next && (
                <Beam
                  from={node}
                  to={next}
                  className={BEAM_POSITION[size][orientation]}
                  dense={size === "compact"}
                />
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

type NodeProps = {
  node: PipelineNode;
  index: number;
  spoken: string;
  onSelect: ((stage: string) => void) | undefined;
  selected: boolean | undefined;
};

function nodeTone(status: TimelineStatus): string {
  const meta = statusMeta(status);
  if (meta.live) {
    return "border-(--tone)/45 shadow-[0_0_0_1px_color-mix(in_oklch,var(--tone)_30%,transparent),0_14px_44px_-16px_color-mix(in_oklch,var(--tone)_60%,transparent)]";
  }
  if (meta.attention) {
    return "border-(--studio-warning)/55 shadow-[0_0_0_1px_color-mix(in_oklch,var(--studio-warning)_25%,transparent),0_12px_36px_-18px_color-mix(in_oklch,var(--studio-warning)_55%,transparent)]";
  }
  if (status === "failed" || status === "rejected") {
    return "border-(--studio-danger)/50";
  }
  if (meta.done) {
    return "border-(--tone)/30";
  }
  /* Stepped back without opacity, so the index, name and status keep their full contrast. */
  return meta.dimmed ? "border-dashed border-(--tone)/45 bg-transparent shadow-none" : "";
}

function LargeNode({
  node,
  index,
  orientation,
  stageLabel,
  statusLabel,
  attempt,
  spoken,
  onSelect,
  selected,
}: NodeProps & {
  orientation: Orientation;
  stageLabel: string;
  statusLabel: string;
  attempt: string | null;
}) {
  const meta = statusMeta(node.status);
  const StageIcon = stageIcon(node.stage);
  const StatusIcon = meta.icon;
  const interactive = Boolean(onSelect);
  const className = cn(
    "studio-glass group/node relative flex w-full min-w-0 rounded-2xl text-left",
    NODE_LAYOUT[orientation],
    nodeTone(node.status),
    interactive &&
      "studio-lift cursor-pointer outline-none focus-visible:ring-3 focus-visible:ring-ring/60",
    selected && "ring-2 ring-ring/70",
  );
  const body = (
    <>
      {meta.live && (
        <BorderBeam colorFrom="var(--tone)" colorTo="var(--aurora-cyan)" duration={3.6} />
      )}
      <span
        aria-hidden
        className="flex size-10 shrink-0 items-center justify-center rounded-xl border border-(--tone)/30 bg-(--tone)/12 text-(--tone-fg)"
      >
        <StageIcon className="size-5" />
      </span>
      {/* The name may be cut short in a narrow row: the tooltip holds the whole node. */}
      <span
        aria-hidden
        title={spoken}
        className={cn("grid flex-1 content-start gap-0.5", NAME_LAYOUT[orientation])}
      >
        <span className="flex items-center gap-1.5 font-mono text-[0.7rem] text-muted-foreground tabular-nums">
          {String(index + 1).padStart(2, "0")}
          {attempt && <span className="truncate font-sans">· {attempt}</span>}
        </span>
        <span
          className={cn(
            "truncate text-sm font-semibold tracking-tight",
            meta.dimmed ? "text-muted-foreground" : "text-foreground",
          )}
        >
          {stageLabel}
        </span>
      </span>
      {/* The status is the point of the node: it wraps onto a second line, never truncates. */}
      <span className={STATUS_SLOT[orientation]}>
        <span
          aria-hidden
          data-tone={meta.tone}
          className="inline-flex min-h-6 max-w-full items-center gap-1.5 rounded-xl border border-(--tone)/25 bg-(--tone)/12 px-2 py-0.5 text-xs font-medium text-(--tone-fg)"
        >
          {meta.live ? (
            <PulseDot tone={meta.tone} live size="sm" />
          ) : (
            <StatusIcon className="size-3.5 shrink-0" />
          )}
          <span>{statusLabel}</span>
        </span>
      </span>
      <span className="sr-only">{spoken}</span>
    </>
  );
  /* A stage that steps back loses its stage colour, so its icon tile goes neutral too. */
  const tone = meta.dimmed ? "neutral" : undefined;

  if (interactive) {
    return (
      <button
        type="button"
        data-tone={tone}
        className={className}
        aria-pressed={selected}
        onClick={() => onSelect?.(node.stage)}
      >
        {body}
      </button>
    );
  }
  return (
    <div data-tone={tone} className={className}>
      {body}
    </div>
  );
}

function CompactNode({ node, index, spoken, onSelect, selected }: NodeProps) {
  const meta = statusMeta(node.status);
  const StatusIcon = meta.icon;
  const interactive = Boolean(onSelect);
  const className = cn(
    "relative flex size-7 items-center justify-center rounded-full border-2 text-(--tone-fg) transition-transform duration-200",
    /* Stepped back with a dashed, unfilled ring in neutral colours: no opacity on the icon. */
    meta.dimmed ? "border-dashed bg-transparent" : "bg-(--tone)/12",
    meta.done || meta.live ? "border-(--tone)" : "border-(--tone)/45",
    meta.attention && "border-(--studio-warning) text-(--studio-warning-fg)",
    (node.status === "failed" || node.status === "rejected") &&
      "border-(--studio-danger) text-(--studio-danger-fg)",
    interactive &&
      "cursor-pointer outline-none hover:scale-110 focus-visible:ring-3 focus-visible:ring-ring/60 motion-reduce:hover:scale-100",
    selected && "ring-2 ring-ring/70 ring-offset-2 ring-offset-background",
  );
  const tone = meta.dimmed ? "neutral" : undefined;
  const body = (
    <>
      {meta.live ? (
        <PulseDot stage={stageAttr(node.stage)} live size="md" />
      ) : node.status === "pending" ? (
        <span aria-hidden className="font-mono text-[0.65rem] font-semibold tabular-nums">
          {index + 1}
        </span>
      ) : (
        <StatusIcon aria-hidden className="size-3.5" />
      )}
      <span className="sr-only">{spoken}</span>
    </>
  );

  if (interactive) {
    return (
      <button
        type="button"
        title={spoken}
        data-tone={tone}
        className={className}
        aria-pressed={selected}
        onClick={() => onSelect?.(node.stage)}
      >
        {body}
      </button>
    );
  }
  return (
    <span title={spoken} data-tone={tone} className={className}>
      {body}
    </span>
  );
}

function Beam({
  from,
  to,
  className,
  dense,
}: {
  from: PipelineNode;
  to: PipelineNode;
  className: string;
  dense: boolean;
}) {
  const state = beamState(from.status, to.status);
  return (
    <span
      aria-hidden
      data-state={state}
      className={cn("studio-pipeline-beam", className)}
      style={
        {
          "--beam-from-color": stageColor(from.stage),
          "--beam-to-color": stageColor(to.stage),
        } as CSSProperties
      }
    >
      {state === "flowing" && (
        <span className="studio-flow">
          {(dense ? [0] : [0, 1]).map((particle) => (
            <span
              key={particle}
              className="studio-flow-track"
              style={{ "--flow-delay": `${particle * -1.2}s` } as CSSProperties}
            >
              <span
                className="studio-flow-dot"
                style={{ "--flow-color": stageColor(to.stage) } as CSSProperties}
              />
            </span>
          ))}
        </span>
      )}
    </span>
  );
}
