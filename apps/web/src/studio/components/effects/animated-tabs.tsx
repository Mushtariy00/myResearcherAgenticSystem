"use client";

import { Tabs } from "@base-ui/react/tabs";
import { LayoutGroup, motion } from "motion/react";
import { createContext, type ReactNode, use, useId, useState } from "react";
import { cn } from "@/lib/utils";
import { SPRING } from "@/studio/lib/motion";

type TabsContextValue = { value: string | null; indicatorId: string };

const AnimatedTabsContext = createContext<TabsContextValue | null>(null);

export type AnimatedTabsProps = {
  /** Controlled value; leave out (with `defaultValue`) for an uncontrolled set of tabs. */
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  children: ReactNode;
  className?: string;
};

/**
 * Tabs whose active indicator slides between tabs (a shared `layoutId`). Semantics and keyboard
 * support come from Base UI Tabs: a tablist, arrow keys with roving focus, and panels linked to
 * their tabs. With reduced motion the indicator jumps instead of sliding (MotionConfig).
 *
 * ```tsx
 * <AnimatedTabs defaultValue="runs">
 *   <AnimatedTabsList aria-label="Project">
 *     <AnimatedTabsTab value="runs">Runs</AnimatedTabsTab>
 *     <AnimatedTabsTab value="papers">Papers</AnimatedTabsTab>
 *   </AnimatedTabsList>
 *   <AnimatedTabsPanel value="runs">…</AnimatedTabsPanel>
 *   <AnimatedTabsPanel value="papers">…</AnimatedTabsPanel>
 * </AnimatedTabs>
 * ```
 */
export function AnimatedTabs({
  value: controlled,
  defaultValue,
  onValueChange,
  children,
  className,
}: AnimatedTabsProps) {
  const [uncontrolled, setUncontrolled] = useState<string | null>(defaultValue ?? null);
  const value = controlled ?? uncontrolled;
  const id = useId();

  return (
    <AnimatedTabsContext value={{ value, indicatorId: `${id}-indicator` }}>
      <LayoutGroup id={id}>
        <Tabs.Root
          value={value}
          onValueChange={(next: unknown) => {
            if (typeof next !== "string") {
              return;
            }
            if (controlled === undefined) {
              setUncontrolled(next);
            }
            onValueChange?.(next);
          }}
          className={className}
        >
          {children}
        </Tabs.Root>
      </LayoutGroup>
    </AnimatedTabsContext>
  );
}

export function AnimatedTabsList({
  children,
  className,
  "aria-label": ariaLabel,
}: {
  children: ReactNode;
  className?: string;
  "aria-label"?: string;
}) {
  return (
    <Tabs.List
      aria-label={ariaLabel}
      className={cn(
        "studio-glass relative isolate inline-flex max-w-full items-center gap-1 overflow-x-auto rounded-xl p-1",
        className,
      )}
    >
      {children}
    </Tabs.List>
  );
}

export function AnimatedTabsTab({
  value,
  children,
  stage,
  className,
}: {
  value: string;
  children: ReactNode;
  /** Colour the active indicator with a pipeline stage (`literature`, `method`, ...). */
  stage?: string;
  className?: string;
}) {
  const context = use(AnimatedTabsContext);
  const active = context?.value === value;

  return (
    <Tabs.Tab
      value={value}
      data-stage={stage}
      className={cn(
        "relative inline-flex h-8 shrink-0 items-center gap-1.5 rounded-lg px-3 text-sm font-medium whitespace-nowrap text-muted-foreground outline-none transition-colors select-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 data-active:text-foreground [&_svg]:size-4 [&_svg]:shrink-0",
        className,
      )}
    >
      {active && context && (
        <motion.span
          layoutId={context.indicatorId}
          transition={SPRING}
          aria-hidden
          className={cn(
            "absolute inset-0 z-0 rounded-lg border border-(--studio-glass-border) bg-(--studio-glass-strong) shadow-[inset_0_1px_0_0_var(--studio-glass-highlight)]",
            stage && "border-(--tone)/40 bg-(--tone)/14",
          )}
        />
      )}
      <span className="relative z-10 inline-flex items-center gap-1.5">{children}</span>
    </Tabs.Tab>
  );
}

export function AnimatedTabsPanel({
  value,
  children,
  className,
}: {
  value: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Tabs.Panel
      value={value}
      className={cn(
        "outline-none animate-in fade-in-0 duration-200 focus-visible:ring-3 focus-visible:ring-ring/50",
        className,
      )}
    >
      {children}
    </Tabs.Panel>
  );
}
