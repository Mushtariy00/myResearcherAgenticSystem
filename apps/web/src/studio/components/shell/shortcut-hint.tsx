"use client";

import { useSyncExternalStore } from "react";
import { cn } from "@/lib/utils";

const noop = () => () => {};

function isApplePlatform(): boolean {
  const platform =
    (navigator as Navigator & { userAgentData?: { platform?: string } }).userAgentData?.platform ??
    navigator.platform ??
    "";
  return /mac|iphone|ipad|ipod/i.test(platform);
}

/** "⌘ K" on Apple devices, "Ctrl K" elsewhere ("Ctrl K" while server rendering). */
export function useCommandKeyLabel(): string {
  const apple = useSyncExternalStore(noop, isApplePlatform, () => false);
  return apple ? "⌘" : "Ctrl";
}

/** The visual keyboard hint; the button itself carries `aria-keyshortcuts`. */
export function ShortcutHint({ className }: { className?: string }) {
  const modifier = useCommandKeyLabel();
  return (
    <span aria-hidden className={cn("inline-flex items-center gap-0.5", className)}>
      <kbd className="inline-flex h-5 min-w-5 items-center justify-center rounded-md border border-(--studio-glass-border) bg-(--studio-glass-strong) px-1 font-sans text-[0.7rem] font-medium text-muted-foreground">
        {modifier}
      </kbd>
      <kbd className="inline-flex h-5 min-w-5 items-center justify-center rounded-md border border-(--studio-glass-border) bg-(--studio-glass-strong) px-1 font-sans text-[0.7rem] font-medium text-muted-foreground">
        K
      </kbd>
    </span>
  );
}
