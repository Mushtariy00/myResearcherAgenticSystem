"use client";

import { CpuIcon, ServerOffIcon } from "lucide-react";
import Link from "next/link";
import { useFormatter, useNow, useTranslations } from "next-intl";
import type { GpuJobOut, GpuOut } from "@/client";
import { DemoBadge } from "@/components/shared/demo-badge";
import { useGpuQueue } from "@/hooks/use-gpu-queue";
import { gpuReadings } from "@/lib/gpu";
import { NumberTicker } from "@/studio/components/effects/number-ticker";
import { PulseDot } from "@/studio/components/effects/pulse-dot";
import { RingGauge } from "@/studio/components/effects/ring-gauge";
import { LoadingStatus, ShimmerSkeleton } from "@/studio/components/effects/shimmer-skeleton";
import { studioRunPath } from "@/studio/lib/nav";
import { StudioInlineError, StudioPanel } from "./studio-panel";

/** Queued jobs listed; the count says how many more there are. */
const QUEUE_LIMIT = 4;

function JobTitle({ job }: { job: GpuJobOut }) {
  const t = useTranslations("studioWork.dashboard.gpu");
  const topic = job.topic || t("unknownTopic");
  return job.run_id ? (
    <Link
      href={studioRunPath(job.run_id)}
      className="line-clamp-2 rounded-sm font-medium text-foreground [overflow-wrap:anywhere] underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"
    >
      {topic}
    </Link>
  ) : (
    <span className="line-clamp-2 font-medium text-foreground [overflow-wrap:anywhere]">
      {topic}
    </span>
  );
}

function ownerOf(job: GpuJobOut, you: string): string {
  return job.is_mine ? you : (job.owner_name ?? "");
}

/** A reading the GPU does not give: a dash (never 0), which screen readers hear as words. */
function NotReported() {
  const t = useTranslations("studioWork.dashboard.gpu");
  return (
    <>
      <span aria-hidden>—</span>
      <span className="sr-only">{t("notReported")}</span>
    </>
  );
}

/** The utilisation ring, memory, temperature and power; a reading the GPU does not give is a dash. */
function Readings({ gpu }: { gpu: GpuOut }) {
  const t = useTranslations("studioWork.dashboard.gpu");
  const format = useFormatter();
  const utilisation = gpu.utilization_percent;
  const draw = gpu.power_draw_w;
  const limit = gpu.power_limit_w;
  const watts = (value: number) => format.number(value, { maximumFractionDigits: 0 });

  return (
    <div className="flex flex-wrap items-center gap-5">
      <div data-stage="experiment">
        {utilisation === null ? (
          // No meter without a value: an empty ring with a dash.
          <div className="grid size-32 shrink-0 place-items-center rounded-full border-[10px] border-[color-mix(in_oklch,var(--foreground)_10%,transparent)] text-center">
            <span className="grid place-items-center">
              <span className="font-mono text-2xl font-semibold tracking-tight text-muted-foreground">
                <NotReported />
              </span>
              <span className="text-[0.7rem] text-muted-foreground">{t("utilisation")}</span>
            </span>
          </div>
        ) : (
          <RingGauge
            value={utilisation}
            label={t("utilisation")}
            valueText={format.number(utilisation / 100, { style: "percent" })}
          >
            <span className="font-mono text-2xl font-semibold tracking-tight text-foreground">
              <NumberTicker
                value={utilisation / 100}
                format={{ style: "percent", maximumFractionDigits: 0 }}
              />
            </span>
            <span aria-hidden className="text-[0.7rem] text-muted-foreground">
              {t("utilisation")}
            </span>
          </RingGauge>
        )}
      </div>
      {/* At least 12rem wide: in a narrow card the readings wrap below the ring instead of
          squeezing into a sliver beside it. */}
      <dl className="grid min-w-48 flex-1 basis-48 grid-cols-2 gap-x-4 gap-y-3 text-sm">
        <div className="col-span-2 grid min-w-0 gap-0.5">
          <dt className="text-xs text-muted-foreground">{t("device")}</dt>
          <dd className="truncate font-medium text-foreground" title={gpu.name}>
            <CpuIcon aria-hidden className="mr-1.5 inline size-3.5 align-[-2px]" />
            {gpu.name}
          </dd>
        </div>
        <div className="grid min-w-0 gap-0.5">
          <dt className="text-xs text-muted-foreground">{t("memory")}</dt>
          <dd className="font-medium text-foreground tabular-nums">
            {t("memoryValue", {
              used: format.number(gpu.memory_used_mb / 1024, {
                style: "unit",
                unit: "gigabyte",
                maximumFractionDigits: 1,
              }),
              total: format.number(gpu.memory_total_mb / 1024, {
                style: "unit",
                unit: "gigabyte",
                maximumFractionDigits: 0,
              }),
            })}
          </dd>
        </div>
        <div className="grid min-w-0 gap-0.5">
          <dt className="text-xs text-muted-foreground">{t("temperature")}</dt>
          <dd className="font-medium text-foreground tabular-nums">
            {gpu.temperature_c === null ? (
              <NotReported />
            ) : (
              format.number(gpu.temperature_c, { style: "unit", unit: "celsius" })
            )}
          </dd>
        </div>
        <div className="col-span-2 grid min-w-0 gap-0.5">
          <dt className="text-xs text-muted-foreground">{t("power")}</dt>
          <dd className="font-medium text-foreground tabular-nums">
            {draw === null ? (
              <NotReported />
            ) : limit === null ? (
              t("powerDraw", { draw: watts(draw) })
            ) : (
              t("powerValue", { draw: watts(draw), limit: watts(limit) })
            )}
          </dd>
        </div>
      </dl>
    </div>
  );
}

/**
 * The lab GPU: a live utilisation ring, memory, temperature and power, the running jobs (smoke
 * tests and trainings) with their progress, and the queue (the caller's place in it). While the
 * GPU executor is not running it says so, and that queued jobs wait for it, instead of showing
 * readings. Refreshes every 5 seconds while the page is visible (useGpuQueue); readings and jobs
 * the API generates carry the Demo badge.
 */
export function GpuCard({ className }: { className?: string }) {
  const t = useTranslations("studioWork.dashboard.gpu");
  const tCommon = useTranslations("common");
  const format = useFormatter();
  const now = useNow({ updateInterval: 15_000 });
  const query = useGpuQueue();
  const data = query.data;
  const readings = data ? gpuReadings(data) : null;
  const you = t("you");
  const kindOf = (job: GpuJobOut) => (job.kind ? t(`kinds.${job.kind}`) : null);

  return (
    <StudioPanel
      id="studio-gpu"
      title={t("title")}
      description={t("description")}
      busy={query.isPending}
      className={className}
      badge={data ? <DemoBadge demo={data.demo || data.gpu?.demo === true} /> : null}
      action={
        readings === "offline" ? (
          <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
            <PulseDot tone="danger" />
            {t("notRunning")}
          </span>
        ) : readings === "live" && data?.gpu ? (
          <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
            <PulseDot tone="success" live={data.running.length > 0} />
            {t("sampled", { time: format.relativeTime(new Date(data.gpu.sampled_at), now) })}
          </span>
        ) : null
      }
    >
      {query.isPending ? (
        <div className="grid gap-3">
          <LoadingStatus label={tCommon("loading")} />
          <div className="flex items-center gap-5">
            <ShimmerSkeleton className="size-32 rounded-full" />
            <ShimmerSkeleton className="h-24 flex-1 rounded-xl" />
          </div>
          <ShimmerSkeleton className="h-16 rounded-xl" />
        </div>
      ) : query.isError ? (
        <StudioInlineError error={query.error} onRetry={() => query.refetch()} />
      ) : data ? (
        <div className="grid gap-5">
          {readings === "offline" ? (
            <div
              role="status"
              data-tone="warning"
              className="flex items-start gap-3 rounded-xl border border-(--tone)/25 bg-(--tone)/10 px-3 py-2.5 text-sm"
            >
              <ServerOffIcon aria-hidden className="mt-0.5 size-4 shrink-0 text-(--tone-fg)" />
              <span className="grid gap-0.5">
                <span className="font-medium text-foreground">{t("offline")}</span>
                <span className="text-muted-foreground">{t("offlineDescription")}</span>
              </span>
            </div>
          ) : readings === "live" && data.gpu ? (
            <Readings gpu={data.gpu} />
          ) : (
            <p className="text-sm text-muted-foreground">{t("noReadings")}</p>
          )}

          {data.my_position !== null && (
            <p
              data-tone="info"
              className="rounded-xl border border-(--tone)/25 bg-(--tone)/10 px-3 py-2 text-sm text-foreground"
            >
              {data.my_position === 0
                ? t("myRunning")
                : data.my_position === 1
                  ? t("myNext")
                  : t("myQueued", { position: data.my_position })}
            </p>
          )}

          <div className="grid gap-2">
            <h3 className="text-xs font-semibold tracking-[0.08em] text-muted-foreground uppercase">
              {t("running")}
            </h3>
            {data.running.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("idle")}</p>
            ) : (
              <ul className="grid gap-3">
                {data.running.map((job) => {
                  const percent = Math.round(Math.min(1, Math.max(0, job.progress)) * 100);
                  return (
                    <li key={job.id} className="grid gap-1.5 text-sm">
                      <JobTitle job={job} />
                      <div
                        role="progressbar"
                        aria-label={t("progressLabel", { topic: job.topic || t("unknownTopic") })}
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-valuenow={percent}
                        data-stage="experiment"
                        className="h-1.5 overflow-hidden rounded-full bg-[color-mix(in_oklch,var(--foreground)_10%,transparent)]"
                      >
                        <div
                          className="h-full origin-left rounded-full bg-(--tone) transition-transform duration-700 ease-out motion-reduce:transition-none"
                          style={{ transform: `scaleX(${percent / 100})` }}
                        />
                      </div>
                      <p className="flex flex-wrap gap-x-2 gap-y-0.5 text-xs text-muted-foreground">
                        {[
                          kindOf(job),
                          ownerOf(job, you),
                          t("progress", { percent }),
                          job.epoch !== null && job.total_epochs !== null
                            ? t("epoch", { epoch: job.epoch, total: job.total_epochs })
                            : null,
                          t(job.estimated ? "etaEstimated" : "eta", {
                            time: format.relativeTime(new Date(job.estimated_finish_at), now),
                          }),
                        ]
                          .filter(Boolean)
                          .join(" · ")}
                      </p>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          <div className="grid gap-2">
            <h3 className="text-xs font-semibold tracking-[0.08em] text-muted-foreground uppercase">
              {t("queue", { count: data.queued.length })}
            </h3>
            {data.queued.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("queueEmpty")}</p>
            ) : (
              <ol className="grid gap-2">
                {data.queued.slice(0, QUEUE_LIMIT).map((job, index) => (
                  <li
                    key={job.id}
                    data-tone={job.is_mine ? "info" : "neutral"}
                    className="flex items-start gap-3 rounded-xl border border-(--studio-glass-border) px-3 py-2 text-sm"
                  >
                    <span
                      aria-hidden
                      className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full bg-(--tone)/14 font-mono text-xs font-semibold text-(--tone-fg) tabular-nums"
                    >
                      {index + 1}
                    </span>
                    <span className="sr-only">{t("position", { position: index + 1 })}</span>
                    <div className="grid min-w-0 flex-1 gap-0.5">
                      <JobTitle job={job} />
                      <p className="text-xs text-muted-foreground">
                        {[
                          kindOf(job),
                          ownerOf(job, you),
                          t("starts", {
                            time: format.relativeTime(new Date(job.estimated_start_at), now),
                          }),
                        ]
                          .filter(Boolean)
                          .join(" · ")}
                      </p>
                    </div>
                  </li>
                ))}
              </ol>
            )}
            {data.queued.length > QUEUE_LIMIT && (
              <p className="text-xs text-muted-foreground">
                {t("moreQueued", { count: data.queued.length - QUEUE_LIMIT })}
              </p>
            )}
          </div>
        </div>
      ) : null}
    </StudioPanel>
  );
}
