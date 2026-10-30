"use client";

import {
  ActivityIcon,
  DatabaseIcon,
  type LucideIcon,
  NetworkIcon,
  RotateCwIcon,
  ServerCogIcon,
  WorkflowIcon,
  ZapIcon,
} from "lucide-react";
import { useFormatter, useNow, useTranslations } from "next-intl";
import type { CSSProperties } from "react";
import {
  HEALTH_TONES,
  type HealthService,
  type HealthStatus,
  useAdminLabels,
} from "@/components/admin/admin-labels";
import { QueryError } from "@/components/app/query-state";
import { useSystemHealth } from "@/hooks/use-system-health";
import { cn } from "@/lib/utils";
import { PulseDot } from "@/studio/components/effects/pulse-dot";
import { LoadingStatus, ShimmerSkeleton } from "@/studio/components/effects/shimmer-skeleton";
import { StudioSection, TonePill } from "@/studio/components/profile/studio-section";
import { StudioStatePanel } from "@/studio/components/studio-state-panel";
import { riseDelay } from "@/studio/lib/motion";
import { GHOST_BUTTON } from "@/studio/lib/ui";

const SERVICE_ICONS: Record<HealthService, LucideIcon> = {
  postgres: DatabaseIcon,
  valkey: ZapIcon,
  temporal: WorkflowIcon,
  gateway: NetworkIcon,
  worker: ServerCogIcon,
};

/** Services that answer pulse; down and unknown ones keep a still dot. */
function isLive(status: HealthStatus): boolean {
  return status === "ok" || status === "degraded";
}

/** Studio system health: a grid of services with pulse dots, latency and what went wrong. */
export function StudioHealthPanel() {
  const t = useTranslations("admin.health");
  const tCommon = useTranslations("common");
  const format = useFormatter();
  const now = useNow({ updateInterval: 5_000 });
  const labels = useAdminLabels();
  const health = useSystemHealth();

  return (
    <StudioSection
      id="studio-admin-health"
      title={
        <>
          {t("title")}
          {health.data && (
            <TonePill tone={HEALTH_TONES[health.data.status] ?? "neutral"}>
              {labels.healthStatus(health.data.status)}
            </TonePill>
          )}
        </>
      }
      description={
        health.data
          ? t("checked", { time: format.relativeTime(new Date(health.data.checked_at), now) })
          : t("description")
      }
      actions={
        <button
          type="button"
          disabled={health.isFetching}
          onClick={() => health.refetch()}
          className={cn(GHOST_BUTTON, "disabled:pointer-events-none disabled:opacity-50")}
        >
          <RotateCwIcon
            aria-hidden
            className={cn(health.isFetching && "motion-safe:animate-spin")}
          />
          {t("refresh")}
        </button>
      }
    >
      {health.isPending ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" aria-busy="true">
          <LoadingStatus label={tCommon("loading")} />
          {Array.from({ length: 5 }, (_, index) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: static placeholders never reorder
            <ShimmerSkeleton key={index} className="h-28 rounded-2xl" />
          ))}
        </div>
      ) : health.isError ? (
        <QueryError error={health.error} onRetry={() => health.refetch()} />
      ) : health.data.checks.length === 0 ? (
        <StudioStatePanel
          variant="section"
          icon={<ActivityIcon aria-hidden />}
          title={t("empty")}
          description={t("description")}
        />
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {health.data.checks.map((check, index) => {
            const tone = HEALTH_TONES[check.status] ?? "neutral";
            const Icon = SERVICE_ICONS[check.name] ?? ActivityIcon;
            const detail = labels.healthDetail(check.detail);
            return (
              <li
                key={check.name}
                data-tone={tone}
                className="studio-rise grid content-start gap-3 rounded-2xl border border-(--studio-glass-border) bg-(--studio-glass) p-4"
                style={{ "--rise-delay": riseDelay(index) } as CSSProperties}
              >
                <div className="flex items-start justify-between gap-3">
                  <span className="flex min-w-0 items-center gap-2.5">
                    <span
                      aria-hidden
                      className="flex size-8 shrink-0 items-center justify-center rounded-lg border border-(--tone)/25 bg-(--tone)/12 text-(--tone-fg) [&_svg]:size-4"
                    >
                      <Icon />
                    </span>
                    <span className="truncate text-sm font-medium text-foreground">
                      {labels.service(check.name)}
                    </span>
                  </span>
                  <PulseDot tone={tone} live={isLive(check.status)} size="lg" className="mt-2" />
                </div>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <TonePill tone={tone}>{labels.healthStatus(check.status)}</TonePill>
                  <p className="font-mono text-xs text-muted-foreground">
                    <span className="sr-only">{t("latencyLabel")}: </span>
                    {t("latency", {
                      ms: format.number(check.latency_ms, { maximumFractionDigits: 1 }),
                    })}
                  </p>
                </div>
                {detail && <p className="text-xs text-pretty text-muted-foreground">{detail}</p>}
              </li>
            );
          })}
        </ul>
      )}
    </StudioSection>
  );
}
