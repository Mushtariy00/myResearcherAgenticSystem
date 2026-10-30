"use client";

import { CpuIcon, ServerOffIcon } from "lucide-react";
import Link from "next/link";
import { useFormatter, useNow, useTranslations } from "next-intl";
import { useId } from "react";
import type { GpuJobOut, GpuOut, GpuQueueOut } from "@/client";
import { QueryError } from "@/components/app/query-state";
import { DemoBadge } from "@/components/shared/demo-badge";
import { formatDuration } from "@/components/shared/format";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useGpuQueue } from "@/hooks/use-gpu-queue";
import { gpuReadings } from "@/lib/gpu";
import { cn } from "@/lib/utils";
import { Gauge, type GaugeTone, ProgressBar } from "./gauge";

/** Waiting jobs listed before "and N more". */
const QUEUE_SHOWN = 4;

function loadTone(share: number): GaugeTone {
  return share >= 0.95 ? "danger" : share >= 0.85 ? "warning" : "default";
}

/** A reading the GPU does not give: a dash (never 0), which screen readers hear as words. */
function NotReported() {
  const t = useTranslations("dashboard.gpu");
  return (
    <>
      <span aria-hidden>—</span>
      <span className="sr-only">{t("notReported")}</span>
    </>
  );
}

function JobItem({ job, position }: { job: GpuJobOut; position?: number }) {
  const t = useTranslations("dashboard.gpu");
  const format = useFormatter();
  const now = useNow({ updateInterval: 30_000 });
  const title = job.topic ?? t("otherProject");
  const details = [
    job.kind ? t(`kinds.${job.kind}`) : null,
    job.owner_name ?? t("someone"),
    job.project_name,
    job.dataset,
  ].filter(Boolean);
  const startsIn = Math.max(0, (Date.parse(job.estimated_start_at) - now.getTime()) / 1000);

  return (
    <li
      className={cn(
        "grid gap-1.5 rounded-lg border p-2.5",
        job.is_mine && "border-primary/40 bg-primary/5",
      )}
    >
      <div className="flex items-start gap-2">
        {/* The list is ordered, so screen readers already say the place. */}
        {position !== undefined && (
          <span
            aria-hidden
            className="mt-px w-5 shrink-0 text-xs font-medium text-muted-foreground tabular-nums"
          >
            {t("position", { position })}
          </span>
        )}
        <p className="min-w-0 flex-1 text-sm font-medium break-words">
          {job.run_id ? (
            <Link
              href={`/runs/${job.run_id}`}
              className="underline-offset-4 hover:underline focus-visible:underline focus-visible:outline-none"
            >
              {title}
            </Link>
          ) : (
            title
          )}
        </p>
        {job.is_mine && (
          <span className="inline-flex h-5 shrink-0 items-center rounded-full bg-primary/10 px-2 text-xs font-medium text-primary">
            {t("yours")}
          </span>
        )}
      </div>
      <p className="text-xs break-words text-muted-foreground">{details.join(" · ")}</p>
      {job.status === "running" ? (
        <>
          <ProgressBar
            label={
              job.epoch !== null && job.total_epochs !== null
                ? t("epoch", { epoch: job.epoch, total: job.total_epochs })
                : t("progress")
            }
            value={job.progress * 100}
            valueText={format.number(job.progress, { style: "percent" })}
          />
          <p className="text-xs text-muted-foreground">
            {t("finishesIn", { duration: formatDuration(job.eta_seconds, format) })}
          </p>
        </>
      ) : (
        <p className="text-xs text-muted-foreground">
          {t("startsIn", { duration: formatDuration(startsIn, format) })}
        </p>
      )}
    </li>
  );
}

function MyPlace({ data }: { data: GpuQueueOut }) {
  const t = useTranslations("dashboard.gpu");
  const message =
    data.my_position === null
      ? t("mine.none")
      : data.my_position === 0
        ? t("mine.running")
        : t("mine.queued", { position: data.my_position });
  return (
    <div className="grid gap-0.5 rounded-lg bg-muted/50 px-3 py-2">
      <p className="text-sm font-medium">{message}</p>
      <p className="text-xs text-muted-foreground">
        {t("mine.limit", { count: data.my_jobs, limit: data.per_user_limit })}
      </p>
    </div>
  );
}

/** The GPU's latest readings; one it does not give (under WSL, say) shows a dash. */
function Readings({ gpu }: { gpu: GpuOut }) {
  const t = useTranslations("dashboard.gpu");
  const format = useFormatter();
  const gigabytes = (mb: number) =>
    format.number(mb / 1024, { style: "unit", unit: "gigabyte", maximumFractionDigits: 1 });
  const memory = gpu.memory_total_mb > 0 ? gpu.memory_used_mb / gpu.memory_total_mb : 0;
  const draw = gpu.power_draw_w;
  const limit = gpu.power_limit_w;

  return (
    <div className="grid gap-3">
      {gpu.utilization_percent === null ? (
        <div className="grid grid-cols-[1fr_auto] items-baseline gap-x-2 gap-y-1.5">
          <span className="text-xs font-medium text-muted-foreground">{t("utilization")}</span>
          <span className="text-xs tabular-nums">
            <NotReported />
          </span>
          <span aria-hidden className="col-span-2 h-2 rounded-full bg-muted" />
        </div>
      ) : (
        <Gauge
          label={t("utilization")}
          value={gpu.utilization_percent}
          valueText={format.number(gpu.utilization_percent / 100, { style: "percent" })}
          tone={loadTone(gpu.utilization_percent / 100)}
        />
      )}
      <Gauge
        label={t("memory")}
        value={gpu.memory_used_mb}
        max={Math.max(1, gpu.memory_total_mb)}
        valueText={t("memoryValue", {
          used: gigabytes(gpu.memory_used_mb),
          total: gigabytes(gpu.memory_total_mb),
        })}
        tone={loadTone(memory)}
      />
      <dl className="grid grid-cols-2 gap-2">
        <div>
          <dt className="text-xs text-muted-foreground">{t("temperature")}</dt>
          <dd className="text-sm font-medium tabular-nums">
            {gpu.temperature_c === null ? (
              <NotReported />
            ) : (
              format.number(gpu.temperature_c, { style: "unit", unit: "celsius" })
            )}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">{t("power")}</dt>
          <dd className="text-sm font-medium tabular-nums">
            {draw === null ? (
              <NotReported />
            ) : limit === null ? (
              t("powerDraw", { draw: format.number(draw) })
            ) : (
              t("powerValue", { draw: format.number(draw), limit: format.number(limit) })
            )}
          </dd>
        </div>
      </dl>
    </div>
  );
}

function GpuDetails({ data }: { data: GpuQueueOut }) {
  const t = useTranslations("dashboard.gpu");
  const readings = gpuReadings(data);
  const waiting = data.queued.slice(0, QUEUE_SHOWN);
  const more = data.queued.length - waiting.length;

  return (
    <div className="grid gap-4">
      {readings === "offline" ? (
        <Alert role="status" className="border-amber-500/40">
          <ServerOffIcon aria-hidden />
          <AlertTitle>{t("offline.title")}</AlertTitle>
          <AlertDescription>{t("offline.description")}</AlertDescription>
        </Alert>
      ) : readings === "live" && data.gpu ? (
        <Readings gpu={data.gpu} />
      ) : (
        <p className="text-sm text-muted-foreground">{t("noReadings")}</p>
      )}

      <MyPlace data={data} />

      <div className="grid gap-2">
        <h3 className="text-xs font-medium text-muted-foreground">{t("running")}</h3>
        {data.running.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("idle")}</p>
        ) : (
          <ul className="grid gap-2">
            {data.running.map((job) => (
              <JobItem key={job.id} job={job} />
            ))}
          </ul>
        )}
      </div>
      <div className="grid gap-2">
        <h3 className="text-xs font-medium text-muted-foreground">
          {t("waiting", { count: data.queued.length })}
        </h3>
        {waiting.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("queueEmpty")}</p>
        ) : (
          <ol className="grid gap-2">
            {waiting.map((job, index) => (
              <JobItem key={job.id} job={job} position={index + 1} />
            ))}
          </ol>
        )}
        {more > 0 && <p className="text-xs text-muted-foreground">{t("more", { count: more })}</p>}
      </div>
    </div>
  );
}

/**
 * The lab GPU: live load, memory and temperature, the jobs on it (smoke tests and trainings),
 * the queue and the user's place. While the GPU executor is not running it says so, and that
 * queued jobs wait for it, instead of showing readings.
 */
export function GpuWidget() {
  const t = useTranslations("dashboard.gpu");
  const headingId = useId();
  const queue = useGpuQueue();

  return (
    <section aria-labelledby={headingId}>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <CpuIcon aria-hidden className="size-4 text-muted-foreground" />
            <h2 id={headingId}>{t("title")}</h2>
          </CardTitle>
          <CardDescription>{queue.data?.gpu?.name ?? t("description")}</CardDescription>
          {queue.data?.demo && (
            <CardAction>
              <DemoBadge demo />
            </CardAction>
          )}
        </CardHeader>
        <CardContent>
          {queue.isPending ? (
            <div className="grid gap-3" aria-busy="true">
              <span className="sr-only">{t("loading")}</span>
              <Skeleton className="h-6 w-full" />
              <Skeleton className="h-6 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          ) : queue.isError ? (
            <QueryError error={queue.error} onRetry={() => queue.refetch()} />
          ) : (
            <GpuDetails data={queue.data} />
          )}
        </CardContent>
      </Card>
    </section>
  );
}
