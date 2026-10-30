"use client";

import { mergeProps } from "@base-ui/react/merge-props";
import { useRender } from "@base-ui/react/use-render";
import { type PointerEvent, useRef } from "react";
import { cn } from "@/lib/utils";
import { useFinePointer, useReducedMotionPreference } from "@/studio/hooks/use-media-query";
import { type GlassOptions, glassClassName } from "@/studio/lib/glass";

const RADIUS = 220;

export type SpotlightCardProps = useRender.ComponentProps<"div"> &
  GlassOptions & {
    /** Colour of the highlight (any CSS colour); defaults to the aurora violet. */
    spotlightColor?: string;
  };

/**
 * A glass card with a radial highlight that follows the pointer. The highlight is a
 * pre-rendered gradient moved with `transform` (no repaint), shown only for a mouse or trackpad
 * and never with reduced motion. Interactive by default: it lifts and glows on hover and focus.
 *
 * Only the highlight's own layer clips (the card itself must not: its hover glow is drawn
 * outside its border box). The layer sits behind the content, above the glass fill.
 */
export function SpotlightCard({
  spotlightColor = "var(--aurora-violet)",
  variant,
  blur,
  interactive = true,
  className,
  render,
  children,
  onPointerMove,
  onPointerLeave,
  ...props
}: SpotlightCardProps) {
  const layer = useRef<HTMLSpanElement>(null);
  const spot = useRef<HTMLSpanElement>(null);
  const finePointer = useFinePointer();
  const reduced = useReducedMotionPreference();
  const enabled = finePointer && !reduced;

  function move(event: PointerEvent<HTMLDivElement>) {
    onPointerMove?.(event);
    const element = spot.current;
    if (!enabled || !element || !layer.current || event.pointerType !== "mouse") {
      return;
    }
    const rect = layer.current.getBoundingClientRect();
    const x = event.clientX - rect.left - RADIUS;
    const y = event.clientY - rect.top - RADIUS;
    element.style.transform = `translate3d(${x}px, ${y}px, 0)`;
    element.style.opacity = "1";
  }

  function leave(event: PointerEvent<HTMLDivElement>) {
    onPointerLeave?.(event);
    if (spot.current) {
      spot.current.style.opacity = "0";
    }
  }

  return useRender({
    defaultTagName: "div",
    render,
    props: mergeProps<"div">(props, {
      className: cn(glassClassName({ variant, blur, interactive }), "isolate", className),
      onPointerMove: move,
      onPointerLeave: leave,
      children: (
        <>
          <span
            ref={layer}
            aria-hidden
            className="pointer-events-none absolute inset-0 -z-10 overflow-hidden rounded-[inherit]"
          >
            <span
              ref={spot}
              data-spotlight=""
              className="absolute top-0 left-0 rounded-full opacity-0 transition-opacity duration-300"
              style={{
                width: RADIUS * 2,
                height: RADIUS * 2,
                background: `radial-gradient(closest-side, color-mix(in oklch, ${spotlightColor} 18%, transparent), transparent)`,
              }}
            />
          </span>
          {children}
        </>
      ),
    }),
  });
}
