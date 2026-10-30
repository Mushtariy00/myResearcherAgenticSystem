"use client";

import { mergeProps } from "@base-ui/react/merge-props";
import { useRender } from "@base-ui/react/use-render";
import { cn } from "@/lib/utils";
import { type GlassOptions, glassClassName } from "@/studio/lib/glass";

export type GlassCardProps = useRender.ComponentProps<"div"> & GlassOptions;

/**
 * The default Studio surface: white at a few percent over the ink background (frosted white in
 * light mode), a hairline border and a soft highlight on the top edge. Pass `render` to make it
 * a link or a list item, e.g. `render={<Link href="..." />}`.
 */
export function GlassCard({
  variant,
  blur,
  interactive,
  className,
  render,
  ...props
}: GlassCardProps) {
  return useRender({
    defaultTagName: "div",
    render,
    props: mergeProps<"div">(props, {
      className: cn(glassClassName({ variant, blur, interactive }), className),
    }),
  });
}
