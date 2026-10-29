"use client";

import {
  BanIcon,
  CircleCheckIcon,
  CircleIcon,
  CircleMinusIcon,
  CircleSlashIcon,
  CircleXIcon,
  EyeIcon,
  LoaderCircleIcon,
  RotateCcwIcon,
  TriangleAlertIcon,
} from "lucide-react";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";
import { StageStatusBadge } from "@/components/app/status-badge";
import type { TimelineEntry, TimelineStatus } from "@/lib/timeline";
import { cn } from "@/lib/utils";
import { useLabels } from "./use-labels";

const ICONS: Record<TimelineStatus, ReactNode> = {
  pending: <CircleIcon className="text-muted-foreground" />,
  running: <LoaderCircleIcon className="text-sky-600 motion-safe:animate-spin dark:text-sky-400" />,
  output_ready: <EyeIcon className="text-amber-600 dark:text-amber-400" />,
  approved: <CircleCheckIcon className="text-emerald-600 dark:text-emerald-400" />,
  changes_requested: <RotateCcwIcon className="text-amber-600 dark:text-amber-400" />,
  rejected: <CircleXIcon className="text-destructive" />,
  failed: <TriangleAlertIcon className="text-destructive" />,
  cancelled: <BanIcon className="text-muted-foreground" />,
  invalidated: <CircleSlashIcon className="text-muted-foreground" />,
  skipped: <CircleMinusIcon className="text-muted-foreground" />,
};

export function StageTimeline({ entries }: { entries: TimelineEntry[] }) {
  const t = useTranslations("run.timeline");
  const labels = useLabels();

  return (
    <section aria-labelledby="timeline-heading">
      <h2 id="timeline-heading" className="mb-3 text-base font-semibold">
        {t("title")}
      </h2>
      <ol className="grid gap-2 sm:grid-cols-5">
        {entries.map((entry, index) => (
          <li
            key={entry.stage}
            aria-current={entry.current ? "step" : undefined}
            className={cn(
              "flex min-w-0 flex-col gap-2 rounded-xl border bg-card p-3",
              entry.current && "border-primary/60 ring-2 ring-primary/15",
              (entry.status === "skipped" || entry.status === "invalidated") && "opacity-70",
            )}
          >
            <div className="flex items-center gap-2">
              <span className="[&_svg]:size-4" aria-hidden>
                {ICONS[entry.status] ?? ICONS.pending}
              </span>
              <span className="text-xs text-muted-foreground tabular-nums">{index + 1}</span>
              <span className="truncate text-sm font-medium">{labels.stage(entry.stage)}</span>
            </div>
            <StageStatusBadge status={entry.status} />
            {entry.attempts > 1 && (
              <p className="text-xs text-muted-foreground">
                {t("attempt", { attempt: entry.latest?.attempt ?? entry.attempts })}
              </p>
            )}
            {entry.latest?.error && (
              <p className="line-clamp-3 text-xs break-words text-destructive">
                {labels.errorText(entry.latest.error)}
              </p>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}
