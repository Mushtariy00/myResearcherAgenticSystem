"use client";

import { RotateCwIcon, TriangleAlertIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";
import { useErrorMessage } from "@/hooks/use-error-message";
import { cn } from "@/lib/utils";
import { glassClassName } from "@/studio/lib/glass";

/**
 * A titled glass section of a Studio work page (dashboard, project, paper): an h2 with an
 * optional badge, a short description and an action on the right.
 */
export function StudioPanel({
  id,
  title,
  description,
  badge,
  action,
  busy,
  className,
  children,
}: {
  /** Prefix of the heading id (the section is labelled by its heading). */
  id: string;
  title: ReactNode;
  description?: ReactNode;
  badge?: ReactNode;
  action?: ReactNode;
  /** Marks the section busy while its content loads. */
  busy?: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section
      aria-labelledby={`${id}-title`}
      aria-busy={busy || undefined}
      className={cn(glassClassName(), "flex min-w-0 flex-col gap-4 p-4 sm:p-6", className)}
    >
      <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
        <div className="grid min-w-0 gap-1">
          <h2
            id={`${id}-title`}
            className="flex flex-wrap items-center gap-2 text-base font-semibold tracking-tight text-foreground"
          >
            {title}
            {badge}
          </h2>
          {description && (
            <p className="text-sm text-pretty text-muted-foreground">{description}</p>
          )}
        </div>
        {action && <div className="flex shrink-0 flex-wrap items-center gap-2">{action}</div>}
      </div>
      {children}
    </section>
  );
}

/**
 * A failed request inside a Studio section: what went wrong (the API's error, translated) and a
 * retry. An alert, so it is announced when it appears.
 */
export function StudioInlineError({
  error,
  onRetry,
  title,
  className,
}: {
  error: unknown;
  onRetry?: () => void;
  /** Defaults to "Could not load this". */
  title?: string;
  className?: string;
}) {
  const t = useTranslations("common");
  const message = useErrorMessage();
  return (
    <div
      role="alert"
      data-tone="danger"
      className={cn(
        "flex flex-wrap items-start gap-3 rounded-xl border border-(--tone)/30 bg-(--tone)/8 px-4 py-3 text-sm",
        className,
      )}
    >
      <TriangleAlertIcon aria-hidden className="mt-0.5 size-4 shrink-0 text-(--tone-fg)" />
      <div className="grid min-w-0 flex-1 gap-0.5">
        <p className="font-medium text-foreground">{title ?? t("loadFailed")}</p>
        <p className="text-pretty text-muted-foreground">{message(error)}</p>
      </div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-[10px] border border-(--studio-glass-border) bg-(--studio-glass) px-3 text-xs font-medium text-foreground outline-none transition-colors hover:bg-(--studio-hover) focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          <RotateCwIcon aria-hidden className="size-3.5" />
          {t("retry")}
        </button>
      )}
    </div>
  );
}
