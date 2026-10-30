"use client";

import { useInView } from "motion/react";
import { useRef } from "react";
import { cn } from "@/lib/utils";

const BLOBS = ["1", "2", "3", "4"] as const;

export type AuroraBackgroundProps = {
  /**
   * `subtle` sits behind working screens and stands still; `vivid` (the landing hero and the
   * sign-in panel) is brighter and drifts.
   */
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
 * Mesh-gradient blobs with a masked dot grid and a noise overlay. Purely decorative: hidden from
 * assistive technology, never receives the pointer, and sits behind its siblings. Radial
 * gradients stand in for blur filters, so it costs no backdrop-filter.
 *
 * Behind working screens (`subtle`) nothing moves: the blobs paint once into the backdrop's own
 * layer instead of each holding a viewport-sized GPU layer on every page. The `vivid` blobs
 * drift with `transform` only, pause while off screen, and stand still with reduced motion
 * (globals.css).
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
  const drifting = variant === "vivid";

  return (
    <div
      ref={ref}
      aria-hidden
      data-variant={variant}
      data-paused={drifting && !inView ? "true" : undefined}
      className={cn(
        "studio-aurora pointer-events-none inset-0 -z-10 overflow-hidden select-none",
        fixed ? "fixed" : "absolute",
        className,
      )}
    >
      {BLOBS.map((blob) => (
        <div key={blob} className="studio-aurora-blob" data-blob={blob} />
      ))}
      {grid && <div className="studio-aurora-grid" />}
      {noise && <div className="studio-aurora-noise" />}
    </div>
  );
}
