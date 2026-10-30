"use client";

import { ActivityIcon, RotateCwIcon } from "lucide-react";
import { useFormatter, useNow, useTranslations } from "next-intl";
import { EmptyState, LoadingRows, QueryError } from "@/components/app/query-state";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useSystemHealth } from "@/hooks/use-system-health";
import { cn } from "@/lib/utils";
import { HEALTH_TONES, type HealthStatus, useAdminLabels } from "./admin-labels";

const PILL_TONES = {
  success: "bg-emerald-500/15 text-emerald-800 dark:text-emerald-300",
  warning: "bg-amber-500/15 text-amber-800 dark:text-amber-300",
  danger: "bg-destructive/10 text-destructive dark:bg-destructive/20",
  neutral: "bg-muted text-muted-foreground",
} as const;

function HealthPill({ status }: { status: HealthStatus }) {
  const labels = useAdminLabels();
  return (
    <span
      className={cn(
        "inline-flex h-5 w-fit shrink-0 items-center gap-1.5 rounded-full px-2 text-xs font-medium whitespace-nowrap",
        PILL_TONES[HEALTH_TONES[status] ?? "neutral"],
      )}
    >
      <span aria-hidden className="size-1.5 rounded-full bg-current" />
      {labels.healthStatus(status)}
    </span>
  );
}

/** Every service the API depends on, with its status, probe latency and what went wrong. */
export function SystemHealthCard() {
  const t = useTranslations("admin.health");
  const format = useFormatter();
  const now = useNow({ updateInterval: 5_000 });
  const labels = useAdminLabels();
  const health = useSystemHealth();

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          {t("title")}
          {health.data && <HealthPill status={health.data.status} />}
        </CardTitle>
        <CardDescription>
          {health.data
            ? t("checked", { time: format.relativeTime(new Date(health.data.checked_at), now) })
            : t("description")}
        </CardDescription>
        <CardAction>
          <Button
            variant="outline"
            size="sm"
            disabled={health.isFetching}
            onClick={() => health.refetch()}
          >
            <RotateCwIcon
              aria-hidden
              className={cn(health.isFetching && "motion-safe:animate-spin")}
            />
            {t("refresh")}
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent>
        {health.isPending ? (
          <LoadingRows rows={5} />
        ) : health.isError ? (
          <QueryError error={health.error} onRetry={() => health.refetch()} />
        ) : health.data.checks.length === 0 ? (
          <EmptyState icon={<ActivityIcon aria-hidden />} title={t("empty")} />
        ) : (
          <ul className="divide-y rounded-lg border">
            {health.data.checks.map((check) => {
              const detail = labels.healthDetail(check.detail);
              return (
                <li
                  key={check.name}
                  className="grid gap-1 px-3 py-2.5 sm:grid-cols-[minmax(0,1fr)_auto_5rem] sm:items-center sm:gap-4"
                >
                  <div className="min-w-0">
                    <p className="font-medium">{labels.service(check.name)}</p>
                    {detail && <p className="text-xs text-muted-foreground">{detail}</p>}
                  </div>
                  <HealthPill status={check.status} />
                  <p className="text-xs text-muted-foreground tabular-nums sm:text-right">
                    <span className="sr-only">{t("latencyLabel")}: </span>
                    {t("latency", {
                      ms: format.number(check.latency_ms, { maximumFractionDigits: 1 }),
                    })}
                  </p>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
