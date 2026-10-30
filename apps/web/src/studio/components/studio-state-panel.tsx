import Link from "next/link";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { glassClassName } from "@/studio/lib/glass";
import type { Tone } from "@/studio/lib/stages";
import { OUTLINE_BUTTON } from "@/studio/lib/ui";

const HEADINGS = { 1: "h1", 2: "h2", 3: "h3", 4: "h4" } as const;

export type StudioStatePanelProps = {
  icon: ReactNode;
  code?: string;
  title: string;
  description: string;
  tone?: Tone;
  action?: { href: string; label: string };
  children?: ReactNode;
  /**
   * `page` (the default) is the whole page: centred in the content area, titled with the page's
   * h1. `section` is an empty state inside a page section: a compact dashed panel that takes the
   * section's width and no more height than it needs.
   */
  variant?: "page" | "section";
  /** The title's heading level: 1 for a page; inside a section, one below the section's. */
  headingLevel?: keyof typeof HEADINGS;
};

/** A glass panel for empty, missing and failed pages, or an empty list inside a page. */
export function StudioStatePanel({
  icon,
  code,
  title,
  description,
  tone = "info",
  action,
  children,
  variant = "page",
  headingLevel = variant === "page" ? 1 : 3,
}: StudioStatePanelProps) {
  const Heading = HEADINGS[headingLevel];
  const page = variant === "page";
  const panel = (
    <div
      className={cn(
        glassClassName(),
        "studio-rise flex w-full flex-col items-center gap-4 px-6 py-10 text-center sm:px-10",
        page ? "max-w-md" : "border-dashed",
      )}
    >
      <span
        data-tone={tone}
        className="flex size-12 items-center justify-center rounded-2xl border border-(--tone)/30 bg-(--tone)/12 text-(--tone-fg) [&_svg]:size-6"
      >
        {icon}
      </span>
      <div className="grid max-w-md gap-2">
        {code && (
          <p className="font-mono text-xs font-medium tracking-widest text-muted-foreground">
            {code}
          </p>
        )}
        <Heading className={cn("studio-display text-foreground", page ? "text-2xl" : "text-lg")}>
          {title}
        </Heading>
        <p className="text-sm text-pretty text-muted-foreground">{description}</p>
      </div>
      {action && (
        <Link href={action.href} className={cn(OUTLINE_BUTTON, "mt-2")}>
          {action.label}
        </Link>
      )}
      {children && <div className="mt-2">{children}</div>}
    </div>
  );

  return page ? (
    <div className="flex min-h-[60vh] items-center justify-center py-10">{panel}</div>
  ) : (
    panel
  );
}
