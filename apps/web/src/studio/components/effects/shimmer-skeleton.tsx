"use client";

import { useRef } from "react";
import { cn } from "@/lib/utils";
import { usePauseOffscreen } from "@/studio/lib/offscreen";

/**
 * A loading placeholder with a soft sweep (still with reduced motion, paused while off screen).
 * Hidden from assistive technology: give the region `aria-busy` and a `LoadingStatus` with the
 * spoken label. Size it like the content it stands for, so nothing moves when the data arrives.
 */
export function ShimmerSkeleton({ className }: { className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  usePauseOffscreen(ref);
  return <div ref={ref} aria-hidden className={cn("studio-skeleton rounded-lg", className)} />;
}

/** The spoken "Loading…" for a region of skeletons. */
export function LoadingStatus({ label }: { label: string }) {
  return (
    <span role="status" className="sr-only">
      {label}
    </span>
  );
}
