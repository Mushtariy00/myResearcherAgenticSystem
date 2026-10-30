import type { Transition } from "motion/react";

/**
 * Studio motion timing (docs/design/studio.md, "Motion"): springs for spatial moves, short
 * fades, slightly longer page transitions, and list staggers capped at a dozen items.
 */
export const EASE_OUT = [0.22, 1, 0.36, 1] as const;

export const SPRING: Transition = { type: "spring", stiffness: 300, damping: 30 };

export const FADE: Transition = { duration: 0.2, ease: EASE_OUT };

export const PAGE: Transition = { duration: 0.38, ease: EASE_OUT };

/** Seconds between items of a staggered reveal. */
export const STAGGER = 0.04;

/** Items after this many appear together, so long lists never take long to reveal. */
export const MAX_STAGGERED_ITEMS = 12;

/** Delay of the `index`th item of a staggered reveal, in seconds. */
export function staggerDelay(index: number): number {
  return Math.min(Math.max(index, 0), MAX_STAGGERED_ITEMS - 1) * STAGGER;
}

/** The same delay as a CSS time, for `.studio-rise` (the `--rise-delay` variable). */
export function riseDelay(index: number, offsetMs = 0): string {
  return `${Math.round(staggerDelay(index) * 1000 + offsetMs)}ms`;
}
