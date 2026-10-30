"use client";

import { ChevronDownIcon, ChevronLeftIcon, ChevronRightIcon, ScrollTextIcon } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useFormatter, useNow, useTranslations } from "next-intl";
import { useId } from "react";
import { auditEntryDetails, useAdminLabels } from "@/components/admin/admin-labels";
import { AuditTarget } from "@/components/admin/audit-log-card";
import { useAuditActionItems, useAuditLogView } from "@/components/admin/use-audit-log-view";
import { QueryError } from "@/components/app/query-state";
import { JsonView } from "@/components/shared/json-view";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { STUDIO_INPUT } from "@/studio/components/auth/fields";
import { LoadingStatus, ShimmerSkeleton } from "@/studio/components/effects/shimmer-skeleton";
import { StudioSection } from "@/studio/components/profile/studio-section";
import { StudioStatePanel } from "@/studio/components/studio-state-panel";
import { FADE } from "@/studio/lib/motion";
import { ICON_BUTTON } from "@/studio/lib/ui";

/** Studio audit log: who did what to which target and when, filtered and a page at a time. */
export function StudioAuditPanel() {
  const t = useTranslations("admin.audit");
  const tCommon = useTranslations("common");
  const format = useFormatter();
  const now = useNow({ updateInterval: 60_000 });
  const labels = useAdminLabels();
  const ids = useId();
  const items = useAuditActionItems();
  const view = useAuditLogView();
  const { log } = view;
  const { query } = log;

  return (
    <StudioSection
      id="studio-admin-audit"
      title={t("title")}
      description={t("description")}
      actions={
        <div className="grid w-full gap-1.5 sm:w-64">
          <Label id={`${ids}-filter`} className="text-xs text-muted-foreground">
            {t("filter")}
          </Label>
          <Select items={items} value={view.action} onValueChange={view.filter}>
            <SelectTrigger
              className={cn(STUDIO_INPUT, "h-9 w-full")}
              aria-labelledby={`${ids}-filter`}
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(items).map(([value, label]) => (
                <SelectItem key={value} value={value}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      }
    >
      {query.isPending ? (
        <div className="grid gap-2" aria-busy="true">
          <LoadingStatus label={tCommon("loading")} />
          {Array.from({ length: 6 }, (_, index) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: static placeholders never reorder
            <ShimmerSkeleton key={index} className="h-16 rounded-xl" />
          ))}
        </div>
      ) : query.isError ? (
        <QueryError error={query.error} onRetry={() => query.refetch()} />
      ) : log.items.length === 0 ? (
        <StudioStatePanel
          variant="section"
          icon={<ScrollTextIcon aria-hidden />}
          title={view.filtered ? t("emptyFiltered") : t("empty")}
          description={t("description")}
        />
      ) : (
        <div
          aria-busy={query.isPlaceholderData}
          className={cn(
            "grid gap-4 transition-opacity duration-200",
            query.isPlaceholderData && "opacity-60",
          )}
        >
          <ol className="grid gap-2">
            {log.items.map((entry) => {
              const open = view.expanded.has(entry.id);
              const detailsId = `${ids}-details-${entry.id}`;
              const created = new Date(entry.created_at);
              const when = format.relativeTime(created, now);
              const action = labels.auditAction(entry.action);
              return (
                <li
                  key={entry.id}
                  className="rounded-xl border border-(--studio-glass-border) bg-(--studio-glass) px-3 py-2.5"
                >
                  <div className="flex items-start gap-3">
                    <div className="grid min-w-0 flex-1 gap-1.5 sm:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_minmax(0,1fr)] sm:items-center sm:gap-4">
                      <div className="grid min-w-0">
                        <p className="truncate text-sm font-medium text-foreground">{action}</p>
                        <p className="truncate font-mono text-xs text-muted-foreground">
                          {entry.action}
                        </p>
                      </div>
                      <p className="min-w-0 truncate text-sm text-foreground">
                        <span className="sr-only">{t("actor")}: </span>
                        {entry.actor_name || entry.actor_email || t("unknownActor")}
                      </p>
                      <AuditTarget
                        entry={entry}
                        prefix="/studio"
                        userName={view.userName}
                        className="text-sm"
                      />
                    </div>
                    <time
                      dateTime={entry.created_at}
                      title={format.dateTime(created, { dateStyle: "medium", timeStyle: "medium" })}
                      className="hidden shrink-0 pt-0.5 text-xs text-muted-foreground tabular-nums sm:block"
                    >
                      {when}
                    </time>
                    <button
                      type="button"
                      aria-expanded={open}
                      aria-controls={open ? detailsId : undefined}
                      aria-label={t("detailsFor", { action, time: when })}
                      title={open ? t("hideDetails") : t("showDetails")}
                      onClick={() => view.toggle(entry.id)}
                      className={cn(ICON_BUTTON, "size-8")}
                    >
                      <ChevronDownIcon
                        aria-hidden
                        className={cn(
                          "transition-transform duration-200 motion-reduce:transition-none",
                          open && "rotate-180",
                        )}
                      />
                    </button>
                  </div>
                  <time
                    dateTime={entry.created_at}
                    className="mt-1 block text-xs text-muted-foreground tabular-nums sm:hidden"
                  >
                    {when}
                  </time>
                  <AnimatePresence initial={false}>
                    {open && (
                      <motion.div
                        key="details"
                        id={detailsId}
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        transition={FADE}
                        className="mt-3"
                      >
                        <JsonView
                          value={auditEntryDetails(entry)}
                          label={t("detailsOf", { action, time: when })}
                          className="max-h-64 border-(--studio-glass-border) bg-(--studio-glass-strong)"
                        />
                      </motion.div>
                    )}
                  </AnimatePresence>
                </li>
              );
            })}
          </ol>
          <nav
            aria-label={t("pagination")}
            className="flex flex-wrap items-center justify-between gap-2"
          >
            <p className="text-sm text-muted-foreground tabular-nums">
              {t("range", {
                from: format.number(view.from),
                to: format.number(view.to),
                total: format.number(log.total),
              })}
            </p>
            <div className="flex items-center gap-1">
              <span className="mr-1 text-sm text-muted-foreground tabular-nums">
                {t("page", {
                  page: format.number(view.page + 1),
                  pages: format.number(log.pageCount),
                })}
              </span>
              <button
                type="button"
                aria-label={t("previous")}
                disabled={!log.hasPreviousPage || query.isFetching}
                onClick={() => view.goTo(view.page - 1)}
                className={ICON_BUTTON}
              >
                <ChevronLeftIcon aria-hidden />
              </button>
              <button
                type="button"
                aria-label={t("next")}
                disabled={!log.hasNextPage || query.isFetching}
                onClick={() => view.goTo(view.page + 1)}
                className={ICON_BUTTON}
              >
                <ChevronRightIcon aria-hidden />
              </button>
            </div>
          </nav>
        </div>
      )}
    </StudioSection>
  );
}
