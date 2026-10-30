"use client";

import { mergeProps } from "@base-ui/react/merge-props";
import { useRender } from "@base-ui/react/use-render";
import { useRef } from "react";
import { cn } from "@/lib/utils";
import { useReducedMotionPreference } from "@/studio/hooks/use-media-query";
import { usePauseOffscreen } from "@/studio/lib/offscreen";

const SIZES = {
  sm: "h-8 gap-1.5 px-3 text-sm [&_svg:not([class*='size-'])]:size-3.5",
  md: "h-10 gap-2 px-4 text-sm [&_svg:not([class*='size-'])]:size-4",
  lg: "h-12 gap-2 px-6 text-base [&_svg:not([class*='size-'])]:size-4.5",
} as const;

export type ShimmerButtonProps = useRender.ComponentProps<"button"> & {
  size?: keyof typeof SIZES;
};

/**
 * The primary call to action: violet-to-indigo (white text keeps >= 5.5:1), a soft aurora glow
 * and a light sweep every few seconds (none with reduced motion, paused while off screen).
 * Renders a `<button type="button">` unless `render` swaps it, e.g.
 * `render={<Link href="/studio/login" />}`.
 */
export function ShimmerButton({
  size = "md",
  className,
  render,
  children,
  type,
  ref,
  ...props
}: ShimmerButtonProps) {
  const own = useRef<HTMLButtonElement>(null);
  const reduced = useReducedMotionPreference();
  usePauseOffscreen(own, !reduced);
  return useRender({
    defaultTagName: "button",
    render,
    ref: ref ? [ref, own] : own,
    props: mergeProps<"button">(props, {
      type: render ? undefined : (type ?? "button"),
      className: cn(
        "studio-shimmer group/shimmer relative isolate inline-flex shrink-0 items-center justify-center overflow-hidden rounded-[10px] font-medium whitespace-nowrap text-(--studio-cta-foreground) outline-none select-none",
        "bg-linear-to-br from-(--studio-cta-from) to-(--studio-cta-to)",
        "shadow-[inset_0_1px_0_0_rgb(255_255_255/0.22),0_10px_30px_-10px_var(--studio-glow),0_0_0_1px_rgb(255_255_255/0.06)]",
        "transition-transform duration-150 active:translate-y-px motion-reduce:transition-none",
        "focus-visible:ring-3 focus-visible:ring-ring/60 focus-visible:ring-offset-2 focus-visible:ring-offset-background",
        "disabled:pointer-events-none disabled:opacity-60 aria-disabled:pointer-events-none aria-disabled:opacity-60",
        "[&_svg]:pointer-events-none [&_svg]:shrink-0",
        SIZES[size],
        className,
      ),
      children: (
        <>
          <span
            aria-hidden
            className="absolute inset-0 -z-10 bg-white/0 transition-colors duration-200 group-hover/shimmer:bg-white/8"
          />
          <span className="relative inline-flex items-center gap-[inherit]">{children}</span>
        </>
      ),
    }),
  });
}
