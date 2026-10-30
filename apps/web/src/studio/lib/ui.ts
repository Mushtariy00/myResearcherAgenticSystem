/**
 * Shared Studio class names (10px control radius, 36px hit targets, visible focus rings).
 * Hover fills use `--studio-hover` (a light ink tint, a white tint in dark mode), never a glass
 * fill: white glass on white paper does not show.
 */

export const ICON_BUTTON =
  "relative inline-flex size-9 shrink-0 items-center justify-center rounded-[10px] text-muted-foreground outline-none transition-colors hover:bg-(--studio-hover) hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-4.5 [&_svg]:shrink-0";

export const GHOST_BUTTON =
  "inline-flex h-9 shrink-0 items-center justify-center gap-2 rounded-[10px] px-3 text-sm font-medium text-muted-foreground outline-none transition-colors hover:bg-(--studio-hover) hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 [&_svg]:size-4 [&_svg]:shrink-0";

export const OUTLINE_BUTTON =
  "inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-[10px] border border-(--studio-glass-border) bg-(--studio-glass) px-4 text-sm font-medium text-foreground shadow-[inset_0_1px_0_0_var(--studio-glass-highlight)] outline-none transition-colors hover:bg-(--studio-hover) focus-visible:ring-3 focus-visible:ring-ring/50 [&_svg]:size-4 [&_svg]:shrink-0";

/** Restyles the shared Classic header controls (LocaleSwitcher, ThemeToggle) for Studio. */
export const SHARED_CONTROL =
  "contents [&_button]:h-9 [&_button]:min-w-9 [&_button]:rounded-[10px] [&_button]:text-muted-foreground [&_button]:hover:bg-(--studio-hover) [&_button]:hover:text-foreground [&_button_svg]:size-4.5";

export const EYEBROW =
  "inline-flex items-center gap-2 text-xs font-semibold tracking-[0.12em] text-(--tone-fg) uppercase";
