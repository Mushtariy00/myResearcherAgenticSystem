import { cn } from "@/lib/utils";

export type GlassOptions = {
  /** `glass` (default) is translucent; `solid` is the raised surface for dense content. */
  variant?: "glass" | "solid";
  /** Frost what is behind it. Costly: keep at most two blurred layers on screen. */
  blur?: boolean;
  /** Lift 2px and glow on hover and keyboard focus (cards that are links or buttons). */
  interactive?: boolean;
};

/**
 * Class names of the Studio glass surface (globals.css `.studio-glass`), for server components
 * and for elements that cannot be a GlassCard.
 */
export function glassClassName({
  variant = "glass",
  blur = false,
  interactive = false,
}: GlassOptions = {}): string {
  return cn(
    "studio-glass relative rounded-2xl text-card-foreground",
    variant === "solid" && "bg-card",
    blur && "studio-blur",
    interactive && "studio-lift outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
  );
}
