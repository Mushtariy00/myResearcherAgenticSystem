"use client";

import { motion } from "motion/react";
import type { ReactNode } from "react";
import { useMountedAfterHydration } from "@/studio/lib/hydration";
import { PAGE } from "@/studio/lib/motion";

/**
 * Page transition for Studio templates: the new page fades in and rises 8px. Server-rendered
 * pages appear as they are (no hidden content before hydration); only client navigations
 * animate. With reduced motion it is a plain fade (MotionConfig drops the movement).
 */
export function PageTransition({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  const animate = useMountedAfterHydration();
  return (
    <motion.div
      className={className}
      initial={animate ? { opacity: 0, y: 8 } : false}
      animate={{ opacity: 1, y: 0 }}
      transition={PAGE}
    >
      {children}
    </motion.div>
  );
}
