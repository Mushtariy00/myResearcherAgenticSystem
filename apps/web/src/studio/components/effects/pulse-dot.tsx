"use client";

import { cn } from "@/lib/utils";
import { useReducedMotionPreference } from "@/studio/hooks/use-media-query";
import type { Tone } from "@/studio/lib/stages";

const SIZES = { sm: "size-1.5", md: "size-2", lg: "size-2.5" } as const;

export type PulseDotProps = {
  /** Semantic tone, or a pipeline stage (`literature`, `method`, ...) for its colour. */
  tone?: Tone;
  stage?: string;
  /** Pulse while something is live (running). A still dot otherwise. */
  live?: boolean;
  size?: keyof typeof SIZES;
  /** Spoken label, when the dot is the only cue (otherwise keep the text next to it). */
  label?: string;
  className?: string;
};

/** A status dot whose ring pulses only while live, and never with reduced motion. */
export function PulseDot({
  tone = "info",
  stage,
  live = false,
  size = "md",
  label,
  className,
}: PulseDotProps) {
  const reduced = useReducedMotionPreference();
  return (
    <span
      data-tone={stage ? undefined : tone}
      data-stage={stage}
      data-live={live ? "true" : undefined}
      className={cn("relative inline-flex shrink-0", SIZES[size], className)}
    >
      {live && !reduced && (
        <span aria-hidden className="studio-pulse absolute inset-0 rounded-full bg-(--tone)" />
      )}
      <span aria-hidden className="relative inline-flex size-full rounded-full bg-(--tone)" />
      {label && <span className="sr-only">{label}</span>}
    </span>
  );
}
