import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { glassClassName } from "@/studio/lib/glass";

/**
 * A titled glass panel of the Studio profile and admin pages: an h2 with an optional
 * description and actions, then the content.
 */
export function StudioSection({
  id,
  title,
  description,
  actions,
  children,
  className,
}: {
  id: string;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      aria-labelledby={`${id}-title`}
      className={cn(glassClassName(), "flex min-w-0 flex-col gap-5 p-5 sm:p-6", className)}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="grid min-w-0 gap-1">
          <h2
            id={`${id}-title`}
            className="studio-display flex flex-wrap items-center gap-2 text-lg text-foreground"
          >
            {title}
          </h2>
          {description && <div className="text-sm text-muted-foreground">{description}</div>}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {children}
    </section>
  );
}

/** A pill in a semantic tone (role names, statuses), readable on glass in both themes. */
export function TonePill({
  tone,
  children,
  className,
}: {
  tone: "neutral" | "info" | "success" | "warning" | "danger";
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      data-tone={tone}
      className={cn(
        "inline-flex h-5 w-fit shrink-0 items-center gap-1.5 rounded-full border border-(--tone)/25 bg-(--tone)/12 px-2 text-xs font-medium whitespace-nowrap text-(--tone-fg)",
        className,
      )}
    >
      {children}
    </span>
  );
}
