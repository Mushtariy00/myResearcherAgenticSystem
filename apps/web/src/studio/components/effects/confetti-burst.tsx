"use client";

import { useEffect, useRef } from "react";
import { useReducedMotionPreference } from "@/studio/hooks/use-media-query";

/** Aurora and stage colours (canvas-confetti needs plain colour strings). */
const COLORS = ["#8b5cf6", "#6366f1", "#22d3ee", "#34d399", "#fbbf24", "#f472b6"];

export type ConfettiBurstProps = {
  /** Fire once when this turns true (e.g. `run.status === "completed"`), never on mount. */
  when: boolean;
  colors?: readonly string[];
};

/**
 * One confetti burst when something reaches its goal (Studio uses it for a run that completes).
 * It fires on the false → true change only, so opening a page for an already finished run stays
 * calm; it never fires while the page is hidden or with reduced motion. canvas-confetti is
 * loaded on demand and draws on its own pointer-transparent canvas.
 */
export function ConfettiBurst({ when, colors = COLORS }: ConfettiBurstProps) {
  const reduced = useReducedMotionPreference();
  const previous = useRef(when);

  useEffect(() => {
    const was = previous.current;
    previous.current = when;
    if (!when || was || reduced) {
      return;
    }
    if (typeof document === "undefined" || document.visibilityState !== "visible") {
      return;
    }
    let cancelled = false;
    void import("canvas-confetti").then(({ default: confetti }) => {
      if (cancelled) {
        return;
      }
      void confetti({
        particleCount: 110,
        spread: 75,
        startVelocity: 38,
        ticks: 220,
        scalar: 0.9,
        origin: { x: 0.5, y: 0.32 },
        colors: [...colors],
        disableForReducedMotion: true,
        zIndex: 60,
      });
    });
    return () => {
      cancelled = true;
    };
  }, [when, reduced, colors]);

  return null;
}
