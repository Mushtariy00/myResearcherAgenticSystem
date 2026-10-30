"use client";

import { motion, useSpring } from "motion/react";
import type { PointerEvent, ReactNode } from "react";
import { cn } from "@/lib/utils";
import { useFinePointer, useReducedMotionPreference } from "@/studio/hooks/use-media-query";

const TILT_SPRING = { stiffness: 220, damping: 22, mass: 0.6 };

export type TiltCardProps = {
  children: ReactNode;
  className?: string;
  /** Largest tilt in degrees on each axis. Keep it subtle. */
  maxTilt?: number;
};

/**
 * A subtle 3D tilt that follows the pointer. Off for touch screens and with reduced motion
 * (`data-tilt="off"`, no transform at all). The element tree is the same either way, so turning
 * it on after hydration never remounts the children; rotation is a transform, so nothing
 * reflows.
 */
export function TiltCard({ children, className, maxTilt = 5 }: TiltCardProps) {
  const finePointer = useFinePointer();
  const reduced = useReducedMotionPreference();
  const enabled = finePointer && !reduced;
  const rotateX = useSpring(0, TILT_SPRING);
  const rotateY = useSpring(0, TILT_SPRING);

  function move(event: PointerEvent<HTMLDivElement>) {
    if (!enabled || event.pointerType !== "mouse") {
      return;
    }
    const rect = event.currentTarget.getBoundingClientRect();
    const x = (event.clientX - rect.left) / rect.width - 0.5;
    const y = (event.clientY - rect.top) / rect.height - 0.5;
    rotateY.set(x * maxTilt * 2);
    rotateX.set(-y * maxTilt * 2);
  }

  function reset() {
    rotateX.set(0);
    rotateY.set(0);
  }

  return (
    <div
      className={cn(enabled && "[perspective:1000px]", className)}
      data-tilt={enabled ? "on" : "off"}
    >
      <motion.div
        className="h-full"
        style={enabled ? { rotateX, rotateY, transformStyle: "preserve-3d" } : undefined}
        onPointerMove={move}
        onPointerLeave={reset}
      >
        {children}
      </motion.div>
    </div>
  );
}
