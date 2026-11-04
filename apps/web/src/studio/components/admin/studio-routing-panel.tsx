"use client";

import { RouteIcon, TriangleAlertIcon } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import type { CSSProperties } from "react";
import type { RoutedModelOut } from "@/client";
import { keyedChain } from "@/components/admin/admin-format";
import { useAdminLabels, useModelText } from "@/components/admin/admin-labels";
import { RoleModelsDialog } from "@/components/admin/role-models-dialog";
import { QueryError } from "@/components/app/query-state";
import { DemoBadge } from "@/components/shared/demo-badge";
import { useModelRouting } from "@/hooks/use-model-routing";
import { cn } from "@/lib/utils";
import { LoadingStatus, ShimmerSkeleton } from "@/studio/components/effects/shimmer-skeleton";
import { StudioSection, TonePill } from "@/studio/components/profile/studio-section";
import { StudioStatePanel } from "@/studio/components/studio-state-panel";
import { riseDelay } from "@/studio/lib/motion";

function Chain({
  title,
  models,
  tone,
  skipped = false,
  own,
  empty,
}: {
  title: string;
  models: RoutedModelOut[];
  tone: "info" | "success";
  skipped?: boolean;
  /** The role has its own list rather than the lab's. */
  own: boolean;
  /** What an empty chain means. */
  empty: string;
}) {
  const t = useTranslations("admin.routing");
  const describe = useModelText();
  return (
    <div className="grid content-start gap-2">
      <p className="flex flex-wrap items-center gap-2 text-xs font-medium text-muted-foreground">
        <span data-tone={tone} aria-hidden className="size-1.5 rounded-full bg-(--tone)" />
        {title}
        {own && <TonePill tone="info">{t("ownList")}</TonePill>}
        {skipped && <TonePill tone="neutral">{t("skipped")}</TonePill>}
      </p>
      {models.length === 0 ? (
        <p className="text-sm text-muted-foreground">{empty}</p>
      ) : (
        <ol
          className={cn(
            "grid gap-1.5",
            skipped && "rounded-lg border border-dashed border-(--studio-glass-border) p-1.5",
          )}
        >
          {keyedChain(models).map(({ key, model }, index) => {
            const { price, context } = describe(model);
            return (
              <li key={key} className="grid min-w-0 gap-0.5 rounded-lg px-2 py-1.5">
                <span className="flex min-w-0 items-baseline gap-2">
                  <span aria-hidden className="font-mono text-xs text-muted-foreground">
                    {index + 1}
                  </span>
                  <span className="truncate font-mono text-xs text-foreground" title={model.id}>
                    {model.id}
                  </span>
                </span>
                <span className="pl-4 text-xs text-muted-foreground">
                  {context ? `${price} · ${context}` : price}
                </span>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}

/** Studio model routing: per agent role, its paid and free chains in the order they are tried. */
export function StudioRoutingPanel() {
  const t = useTranslations("admin.routing");
  const tCommon = useTranslations("common");
  const format = useFormatter();
  const labels = useAdminLabels();
  const routing = useModelRouting();
  const paidOn = routing.data?.paid_models_enabled ?? true;

  return (
    <StudioSection
      id="studio-admin-routing"
      title={
        <>
          {t("title")}
          <DemoBadge demo={routing.data?.demo} />
          {routing.data && (
            <TonePill tone={paidOn ? "success" : "danger"}>
              {paidOn ? t("paidOn") : t("paidOff")}
            </TonePill>
          )}
        </>
      }
      description={t("description")}
    >
      {routing.isPending ? (
        <div className="grid gap-3 lg:grid-cols-2" aria-busy="true">
          <LoadingStatus label={tCommon("loading")} />
          {Array.from({ length: 4 }, (_, index) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: static placeholders never reorder
            <ShimmerSkeleton key={index} className="h-44 rounded-2xl" />
          ))}
        </div>
      ) : routing.isError ? (
        <QueryError error={routing.error} onRetry={() => routing.refetch()} />
      ) : routing.data.roles.length === 0 ? (
        <StudioStatePanel
          variant="section"
          icon={<RouteIcon aria-hidden />}
          title={t("empty")}
          description={t("description")}
        />
      ) : (
        <div className="grid gap-4">
          {!paidOn && (
            <p
              data-tone="warning"
              className="flex items-start gap-2 rounded-xl border border-(--tone)/30 bg-(--tone)/10 px-3 py-2 text-sm text-(--tone-fg)"
            >
              <TriangleAlertIcon aria-hidden className="mt-0.5 size-4 shrink-0" />
              {t("paidOffNotice")}
            </p>
          )}
          {routing.data.catalog_checked_at === null && (
            <p
              data-tone="warning"
              className="flex items-start gap-2 rounded-xl border border-(--tone)/30 bg-(--tone)/10 px-3 py-2 text-sm text-(--tone-fg)"
            >
              <TriangleAlertIcon aria-hidden className="mt-0.5 size-4 shrink-0" />
              {t("catalogMissing")}
            </p>
          )}
          <ul className="grid gap-3 xl:grid-cols-2">
            {routing.data.roles.map((role, index) => (
              <li
                key={role.role}
                className="studio-rise grid gap-4 rounded-2xl border border-(--studio-glass-border) bg-(--studio-glass) p-4"
                style={{ "--rise-delay": riseDelay(index) } as CSSProperties}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="grid min-w-0 gap-0.5">
                    <h3 className="text-sm font-semibold text-foreground">
                      {labels.agentRole(role.role)}
                    </h3>
                    <p className="text-xs text-muted-foreground tabular-nums">
                      {t("maxOutput", { tokens: format.number(role.max_output_tokens) })}
                    </p>
                  </div>
                  <RoleModelsDialog role={role} routing={routing.data} />
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Chain
                    title={t("paid")}
                    models={role.paid}
                    tone="info"
                    skipped={!paidOn}
                    own={!role.paid_is_lab_default}
                    empty={t("noPaid")}
                  />
                  <Chain
                    title={t("free")}
                    models={role.free}
                    tone="success"
                    own={!role.free_is_lab_default}
                    empty={t("none")}
                  />
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </StudioSection>
  );
}
