import type { CSSProperties } from "react";
import { cn } from "@/lib/utils";

export type BorderBeamProps = {
  /** Seconds per lap. */
  duration?: number;
  /** Beam colours (any CSS colour); default from the aurora gradient. */
  colorFrom?: string;
  colorTo?: string;
  /** Border thickness in pixels. */
  width?: number;
  className?: string;
};

/**
 * An animated gradient border for the active or running element. Put it inside a `relative`
 * element with rounded corners; it inherits the radius and never takes the pointer. A rotating
 * conic gradient behind a ring mask: transform-only, and a still gradient ring with reduced
 * motion (globals.css). Wrap a region in `data-paused="true"` to stop it while off screen.
 */
export function BorderBeam({
  duration = 4,
  colorFrom = "var(--aurora-violet)",
  colorTo = "var(--aurora-cyan)",
  width = 1.5,
  className,
}: BorderBeamProps) {
  return (
    <span
      aria-hidden
      className={cn("studio-beam", className)}
      style={
        {
          "--beam-duration": `${duration}s`,
          "--beam-from": colorFrom,
          "--beam-to": colorTo,
          "--beam-width": `${width}px`,
        } as CSSProperties
      }
    />
  );
}
