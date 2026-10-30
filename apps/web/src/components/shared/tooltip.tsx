"use client";

import { Popover as PopoverPrimitive } from "@base-ui/react/popover";
import { Tooltip as TooltipPrimitive } from "@base-ui/react/tooltip";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * Popup surfaces for the shared components, themed with the popover tokens. Tooltips are visual
 * hints only (Base UI keeps them off touch screens), so every trigger also carries an accessible
 * name that says the same; content people need to read uses the hover-capable popover instead.
 */

const SURFACE =
  "z-50 origin-(--transform-origin) rounded-lg bg-popover text-popover-foreground shadow-md ring-1 ring-foreground/10 transition-[transform,opacity] duration-100 outline-none data-ending-style:scale-95 data-ending-style:opacity-0 data-starting-style:scale-95 data-starting-style:opacity-0 data-instant:transition-none motion-reduce:transition-none";

export { Popover } from "@base-ui/react/popover";
export { Tooltip } from "@base-ui/react/tooltip";

export function TooltipContent({
  children,
  side = "top",
  sideOffset = 6,
  className,
}: {
  children: ReactNode;
  side?: TooltipPrimitive.Positioner.Props["side"];
  sideOffset?: number;
  className?: string;
}) {
  return (
    <TooltipPrimitive.Portal>
      <TooltipPrimitive.Positioner side={side} sideOffset={sideOffset} className="isolate z-50">
        <TooltipPrimitive.Popup
          className={cn(SURFACE, "max-w-xs px-2.5 py-1.5 text-xs text-balance", className)}
        >
          {children}
        </TooltipPrimitive.Popup>
      </TooltipPrimitive.Positioner>
    </TooltipPrimitive.Portal>
  );
}

export function PopoverContent({
  children,
  side = "bottom",
  align = "start",
  sideOffset = 6,
  className,
}: {
  children: ReactNode;
  side?: PopoverPrimitive.Positioner.Props["side"];
  align?: PopoverPrimitive.Positioner.Props["align"];
  sideOffset?: number;
  className?: string;
}) {
  return (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Positioner
        side={side}
        align={align}
        sideOffset={sideOffset}
        className="isolate z-50"
      >
        <PopoverPrimitive.Popup
          className={cn(SURFACE, "grid max-w-xs gap-1 p-3 text-sm", className)}
        >
          {children}
        </PopoverPrimitive.Popup>
      </PopoverPrimitive.Positioner>
    </PopoverPrimitive.Portal>
  );
}
