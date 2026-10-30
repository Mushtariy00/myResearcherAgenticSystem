"use client";

import { useInView } from "motion/react";
import { type CSSProperties, type ReactNode, useRef } from "react";
import { cn } from "@/lib/utils";
import { useReducedMotionPreference } from "@/studio/hooks/use-media-query";

export type MarqueeProps = {
  /** `<li>` items. They render twice for a seamless loop; the copy is hidden from assistive
   *  technology and is inert. */
  children: ReactNode;
  /** Accessible name of the list. */
  label: string;
  /** Seconds per loop. */
  duration?: number;
  reverse?: boolean;
  className?: string;
};

/**
 * An endless row of logos or text. It pauses on hover and keyboard focus, and while off screen.
 * With reduced motion it does not move at all: the copy is dropped and the items wrap, centred.
 */
export function Marquee({
  children,
  label,
  duration = 40,
  reverse = false,
  className,
}: MarqueeProps) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { initial: true });
  const reduced = useReducedMotionPreference();

  return (
    <div
      ref={ref}
      data-paused={inView ? undefined : "true"}
      data-reduced={reduced ? "true" : undefined}
      data-reverse={reverse ? "true" : undefined}
      className={cn("studio-marquee", className)}
      style={{ "--marquee-duration": `${duration}s` } as CSSProperties}
    >
      <div className="studio-marquee-track">
        <ul aria-label={label} className="studio-marquee-group">
          {children}
        </ul>
        {!reduced && (
          <ul aria-hidden="true" inert className="studio-marquee-group">
            {children}
          </ul>
        )}
      </div>
    </div>
  );
}
