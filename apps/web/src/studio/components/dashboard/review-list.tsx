"use client";

import { ArrowRightIcon, CircleCheckIcon, HourglassIcon } from "lucide-react";
import Link from "next/link";
import { useFormatter, useNow, useTranslations } from "next-intl";
import type { CSSProperties } from "react";
import { isKnownStage } from "@/lib/labels";
import { cn } from "@/lib/utils";
import { LoadingStatus, ShimmerSkeleton } from "@/studio/components/effects/shimmer-skeleton";
import { PipelineGraph } from "@/studio/components/pipeline-graph";
import { StudioStatePanel } from "@/studio/components/studio-state-panel";
import { riseDelay } from "@/studio/lib/motion";
import { STUDIO_ROUTES, studioRunPath } from "@/studio/lib/nav";
import { stageAttr } from "@/studio/lib/stages";
import { GHOST_BUTTON } from "@/studio/lib/ui";
import type { ReviewItem } from "./dashboard-data";
import { StudioInlineError, StudioPanel } from "./studio-panel";

/** Rows shown; the rest are a link away, on the notifications page. */
export const REVIEW_LIMIT = 5;

/**
 * "Needs your review": outputs waiting for the caller's decision, each a card with the run's
 * compact pipeline. The topic is the link (its name stays short for screen readers) and
 * stretches over the whole card for pointer users.
 */
export function ReviewList({
  items,
  loading,
  error,
  onRetry,
  className,
}: {
  items: readonly ReviewItem[];
  loading: boolean;
  error: unknown;
  onRetry: () => void;
  className?: string;
}) {
  const t = useTranslations("studioWork.dashboard.review");
  const tAll = useTranslations();
  const format = useFormatter();
  const now = useNow({ updateInterval: 60_000 });
  const shown = items.slice(0, REVIEW_LIMIT);
  const more = items.length - shown.length;

  return (
    <StudioPanel
      id="studio-review"
      title={t("title")}
      description={t("description")}
      busy={loading}
      className={className}
      badge={
        items.length > 0 ? (
          <span
            data-tone="warning"
            className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-(--tone)/14 px-1.5 text-xs font-semibold text-(--tone-fg) tabular-nums"
          >
            {items.length}
          </span>
        ) : null
      }
      action={
        <Link href={STUDIO_ROUTES.notifications} className={cn(GHOST_BUTTON, "h-8 px-2.5")}>
          {t("all")}
          <ArrowRightIcon aria-hidden />
        </Link>
      }
    >
      {loading ? (
        <div className="grid gap-3">
          <LoadingStatus label={tAll("common.loading")} />
          {Array.from({ length: 2 }, (_, index) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: static placeholders never reorder
            <ShimmerSkeleton key={index} className="h-24 rounded-xl" />
          ))}
        </div>
      ) : error ? (
        <StudioInlineError error={error} onRetry={onRetry} />
      ) : shown.length === 0 ? (
        <StudioStatePanel
          variant="section"
          headingLevel={3}
          tone="success"
          icon={<CircleCheckIcon aria-hidden />}
          title={t("empty")}
          description={t("emptyDescription")}
        />
      ) : (
        <ul className="grid gap-3">
          {shown.map((item, index) => {
            const stage = isKnownStage(item.stage) ? tAll(`stages.${item.stage}`) : item.stage;
            return (
              <li
                key={item.key}
                className="studio-rise relative isolate flex flex-col gap-3 rounded-xl border border-(--studio-glass-border) bg-(--studio-glass) p-3 transition-colors hover:bg-(--studio-hover) sm:p-4 lg:flex-row lg:items-center"
                style={{ "--rise-delay": riseDelay(index) } as CSSProperties}
              >
                <div className="grid min-w-0 flex-1 gap-1">
                  <p className="flex flex-wrap items-center gap-2 text-xs font-medium">
                    <span
                      data-stage={stageAttr(item.stage)}
                      data-tone={stageAttr(item.stage) ? undefined : "neutral"}
                      className="inline-flex h-5 items-center rounded-full border border-(--tone)/25 bg-(--tone)/12 px-2 text-(--tone-fg)"
                    >
                      {t("stage", { stage })}
                    </span>
                    {item.expiring && (
                      <span
                        data-tone="danger"
                        className="inline-flex h-5 items-center gap-1 rounded-full border border-(--tone)/25 bg-(--tone)/12 px-2 text-(--tone-fg)"
                      >
                        <HourglassIcon aria-hidden className="size-3" />
                        {t("expiring")}
                      </span>
                    )}
                  </p>
                  <Link
                    href={studioRunPath(item.runId)}
                    className="line-clamp-2 rounded-sm text-sm font-semibold text-foreground [overflow-wrap:anywhere] outline-none after:absolute after:inset-0 after:z-10 after:rounded-xl after:content-[''] focus-visible:after:ring-3 focus-visible:after:ring-ring/50"
                  >
                    {item.topic}
                  </Link>
                  <p className="text-xs text-muted-foreground">
                    {[
                      item.project,
                      t("ready", { time: format.relativeTime(new Date(item.readyAt), now) }),
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                </div>
                <PipelineGraph
                  nodes={item.nodes}
                  size="compact"
                  aria-label={t("pipeline", { topic: item.topic })}
                  className="w-auto shrink-0"
                />
              </li>
            );
          })}
        </ul>
      )}
      {more > 0 && !loading && !error && (
        <p className="text-sm text-muted-foreground">
          <Link
            href={STUDIO_ROUTES.notifications}
            className="rounded-sm font-medium text-foreground underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            {t("more", { count: more })}
          </Link>
        </p>
      )}
    </StudioPanel>
  );
}
