"use client";

import { useInView } from "motion/react";
import { useRef } from "react";
import { cn } from "@/lib/utils";

export type AuroraBackgroundProps = {
  /** `subtle` sits behind working screens; `vivid` is for the landing hero and sign-in. */
  variant?: "subtle" | "vivid";
  /** Cover the viewport (`fixed`) instead of the nearest positioned ancestor. */
  fixed?: boolean;
  /** The masked dot grid near the top. */
  grid?: boolean;
  /** The fine film-grain overlay. */
  noise?: boolean;
  className?: string;
};

/**
 * Slow mesh-gradient blobs with a masked dot grid and a noise overlay. Purely decorative: hidden
 * from assistive technology, never receives the pointer, and sits behind its siblings. The blobs
 * move with `transform` only, pause while off screen, and stand still with reduced motion
 * (globals.css). Radial gradients stand in for blur filters, so it costs no backdrop-filter.
 */
export function AuroraBackground({
  variant = "subtle",
  fixed = false,
  grid = true,
  noise = true,
  className,
}: AuroraBackgroundProps) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { initial: true });

  return (
    <div
      ref={ref}
      aria-hidden
      data-variant={variant}
      data-paused={inView ? undefined : "true"}
      className={cn(
        "studio-aurora pointer-events-none inset-0 -z-10 overflow-hidden select-none",
        fixed ? "fixed" : "absolute",
        className,
      )}
    >
      <div className="studio-aurora-blob" data-blob="1" />
      <div className="studio-aurora-blob" data-blob="2" />
      <div className="studio-aurora-blob" data-blob="3" />
      <div className="studio-aurora-blob" data-blob="4" />
      {grid && <div className="studio-aurora-grid" />}
      {noise && <div className="studio-aurora-noise" />}
    </div>
  );
}
