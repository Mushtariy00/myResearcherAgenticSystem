"use client";

import { HistoryIcon } from "lucide-react";
import Link from "next/link";
import { useFormatter, useNow, useTranslations } from "next-intl";
import type { CSSProperties } from "react";
import type { RecentRunOut } from "@/client";
import { LoadingStatus, ShimmerSkeleton } from "@/studio/components/effects/shimmer-skeleton";
import { StudioStatePanel } from "@/studio/components/studio-state-panel";
import { riseDelay } from "@/studio/lib/motion";
import { studioRunPath } from "@/studio/lib/nav";
import { RunStatusPill } from "./run-status-pill";
import { StudioInlineError, StudioPanel } from "./studio-panel";

export const RECENT_LIMIT = 6;

/** The newest runs across the caller's projects, each a link to its Studio run page. */
export function RecentRuns({
  runs,
  loading,
  error,
  onRetry,
  className,
}: {
  runs: readonly RecentRunOut[];
  loading: boolean;
  error: unknown;
  onRetry: () => void;
  className?: string;
}) {
  const t = useTranslations("studioWork.dashboard.recent");
  const tCommon = useTranslations("common");
  const format = useFormatter();
  const now = useNow({ updateInterval: 60_000 });
  const shown = runs.slice(0, RECENT_LIMIT);

  return (
    <StudioPanel id="studio-recent" title={t("title")} busy={loading} className={className}>
      {loading ? (
        <div className="grid gap-2">
          <LoadingStatus label={tCommon("loading")} />
          {Array.from({ length: 3 }, (_, index) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: static placeholders never reorder
            <ShimmerSkeleton key={index} className="h-16 rounded-xl" />
          ))}
        </div>
      ) : error ? (
        <StudioInlineError error={error} onRetry={onRetry} />
      ) : shown.length === 0 ? (
        <StudioStatePanel
          variant="section"
          headingLevel={3}
          icon={<HistoryIcon aria-hidden />}
          title={t("empty")}
          description={t("emptyDescription")}
        />
      ) : (
        <ul className="-mx-2 grid gap-1">
          {shown.map((run, index) => (
            <li
              key={run.id}
              className="studio-rise"
              style={{ "--rise-delay": riseDelay(index) } as CSSProperties}
            >
              <Link
                href={studioRunPath(run.id)}
                className="grid min-w-0 gap-1 rounded-xl px-2 py-2.5 outline-none transition-colors hover:bg-(--studio-hover) focus-visible:ring-3 focus-visible:ring-ring/50"
              >
                <span className="line-clamp-2 text-sm font-medium text-foreground [overflow-wrap:anywhere]">
                  {run.topic}
                </span>
                <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                  <RunStatusPill status={run.status} className="h-5" />
                  <span className="min-w-0 truncate">{run.project_name}</span>
                  <span aria-hidden>·</span>
                  <span>
                    {t("updated", { time: format.relativeTime(new Date(run.updated_at), now) })}
                  </span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </StudioPanel>
  );
}
