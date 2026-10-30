import type { ElementType, ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * Aurora gradient text for display headings. The stops are text-safe per theme (darker in light
 * mode), the text stays real text for search and screen readers, and forced-colors mode falls
 * back to the system text colour (globals.css).
 */
export function GradientText({
  children,
  className,
  as: Component = "span",
}: {
  children: ReactNode;
  className?: string;
  as?: ElementType;
}) {
  return <Component className={cn("studio-gradient-text", className)}>{children}</Component>;
}
