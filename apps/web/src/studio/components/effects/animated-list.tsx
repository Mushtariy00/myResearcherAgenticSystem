"use client";

import { AnimatePresence, motion } from "motion/react";
import { type Key, type ReactNode, useState } from "react";
import { cn } from "@/lib/utils";
import { useMountedAfterHydration } from "@/studio/lib/hydration";
import { EASE_OUT, staggerDelay } from "@/studio/lib/motion";

export type AnimatedListProps<T> = {
  items: readonly T[];
  getKey: (item: T) => Key;
  renderItem: (item: T, index: number) => ReactNode;
  /** `ol` for ordered content such as log lines. */
  as?: "ul" | "ol";
  className?: string;
  itemClassName?: string;
  /** Entering items come from above (newest first, like notifications) or below (logs). */
  enterFrom?: "top" | "bottom";
  /** `role="log"` with polite announcements, for live logs. */
  live?: boolean;
  "aria-label"?: string;
};

/**
 * A list whose items slide in and fade out as they come and go (log lines, notifications).
 * The items present when the list mounts on the client stagger in (40 ms apart, capped at 12);
 * server-rendered items are shown as they are. Remaining items move to their new place with a
 * layout animation. With reduced motion, items only fade (MotionConfig drops the movement).
 */
export function AnimatedList<T>({
  items,
  getKey,
  renderItem,
  as = "ul",
  className,
  itemClassName,
  enterFrom = "top",
  live = false,
  "aria-label": ariaLabel,
}: AnimatedListProps<T>) {
  const clientMount = useMountedAfterHydration();
  const [firstKeys] = useState(() => new Set(items.map(getKey)));
  const List = as;
  const offset = enterFrom === "top" ? -8 : 8;

  return (
    <List
      className={cn("grid", className)}
      role={live ? "log" : undefined}
      aria-live={live ? "polite" : undefined}
      aria-label={ariaLabel}
    >
      <AnimatePresence initial={clientMount}>
        {items.map((item, index) => {
          const key = getKey(item);
          return (
            <motion.li
              key={key}
              layout="position"
              className={itemClassName}
              initial={{ opacity: 0, y: offset }}
              animate={{
                opacity: 1,
                y: 0,
                transition: {
                  duration: 0.24,
                  ease: EASE_OUT,
                  delay: firstKeys.has(key) ? staggerDelay(index) : 0,
                },
              }}
              exit={{ opacity: 0, transition: { duration: 0.15 } }}
            >
              {renderItem(item, index)}
            </motion.li>
          );
        })}
      </AnimatePresence>
    </List>
  );
}
