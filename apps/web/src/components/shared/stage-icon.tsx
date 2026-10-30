import { stageMeta, UNKNOWN_STAGE_ICON } from "@/lib/stage-meta";
import { cn } from "@/lib/utils";

export type StageMarkProps = {
  /** A stage id from the API; unknown stages get a neutral mark. */
  stage: string;
  /** Accessible name. Without it the mark is decorative (the stage is named next to it). */
  label?: string;
  className?: string;
};

/**
 * The stage's icon in its text-safe stage colour (`--tone-fg` from `data-stage`), the same in
 * Classic and Studio. Pass `className="text-current"` to inherit the surrounding colour.
 */
export function StageIcon({ stage, label, className }: StageMarkProps) {
  const meta = stageMeta(stage);
  const Icon = meta?.icon ?? UNKNOWN_STAGE_ICON;
  return (
    <Icon
      data-stage={meta?.stage}
      data-slot="stage-icon"
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      className={cn("size-4 shrink-0 text-[var(--tone-fg,currentColor)]", className)}
    />
  );
}

/** A small dot in the stage's fill colour (`--tone` from `data-stage`). */
export function StageDot({ stage, label, className }: StageMarkProps) {
  const meta = stageMeta(stage);
  const classes = cn(
    "inline-block size-2 shrink-0 rounded-full bg-[var(--tone,var(--muted-foreground))]",
    className,
  );
  return label ? (
    <span
      data-stage={meta?.stage}
      data-slot="stage-dot"
      role="img"
      aria-label={label}
      className={classes}
    />
  ) : (
    <span data-stage={meta?.stage} data-slot="stage-dot" aria-hidden className={classes} />
  );
}
