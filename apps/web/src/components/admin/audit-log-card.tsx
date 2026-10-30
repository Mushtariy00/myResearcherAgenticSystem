"use client";

import { ChevronDownIcon, ChevronLeftIcon, ChevronRightIcon, ScrollTextIcon } from "lucide-react";
import Link from "next/link";
import { useFormatter, useNow, useTranslations } from "next-intl";
import { Fragment, useId } from "react";
import type { AuditEntryOut } from "@/client";
import { EmptyState, LoadingRows, QueryError } from "@/components/app/query-state";
import { JsonView } from "@/components/shared/json-view";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { InterfacePrefix } from "@/lib/notifications";
import { cn } from "@/lib/utils";
import { auditEntryDetails, auditTargetHref, useAdminLabels } from "./admin-labels";
import { useAuditActionItems, useAuditLogView } from "./use-audit-log-view";

/** The target of an entry: its kind and name, linked to its page when it has one. */
export function AuditTarget({
  entry,
  prefix,
  userName,
  className,
}: {
  entry: AuditEntryOut;
  prefix: InterfacePrefix;
  userName: (id: string) => string | null;
  className?: string;
}) {
  const labels = useAdminLabels();
  const { type, name } = labels.auditTarget(entry, userName);
  const href = auditTargetHref(entry, prefix);
  return (
    <span className={cn("grid min-w-0", className)}>
      <span className="text-xs text-muted-foreground">{type}</span>
      {href ? (
        <Link
          href={href}
          className="truncate font-medium underline-offset-4 hover:underline focus-visible:rounded-sm focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
        >
          {name}
        </Link>
      ) : (
        <span className="truncate font-medium">{name}</span>
      )}
    </span>
  );
}

/** The audit log, newest first: who did what to which target and when, a page at a time. */
export function AuditLogCard() {
  const t = useTranslations("admin.audit");
  const format = useFormatter();
  const now = useNow({ updateInterval: 60_000 });
  const labels = useAdminLabels();
  const filterId = useId();
  const items = useAuditActionItems();
  const view = useAuditLogView();
  const { log } = view;
  const { query } = log;

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("title")}</CardTitle>
        <CardDescription>{t("description")}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        <div className="grid gap-2 sm:max-w-xs">
          <Label id={filterId}>{t("filter")}</Label>
          <Select items={items} value={view.action} onValueChange={view.filter}>
            <SelectTrigger className="w-full" aria-labelledby={filterId}>
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
        {query.isPending ? (
          <LoadingRows rows={6} />
        ) : query.isError ? (
          <QueryError error={query.error} onRetry={() => query.refetch()} />
        ) : log.items.length === 0 ? (
          <EmptyState
            icon={<ScrollTextIcon aria-hidden />}
            title={view.filtered ? t("emptyFiltered") : t("empty")}
          />
        ) : (
          <div
            aria-busy={query.isPlaceholderData}
            className={cn("grid gap-3", query.isPlaceholderData && "opacity-60")}
          >
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("when")}</TableHead>
                  <TableHead>{t("actor")}</TableHead>
                  <TableHead>{t("action")}</TableHead>
                  <TableHead>{t("target")}</TableHead>
                  <TableHead className="w-10">
                    <span className="sr-only">{t("details")}</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {log.items.map((entry) => {
                  const open = view.expanded.has(entry.id);
                  const detailsId = `${filterId}-details-${entry.id}`;
                  const created = new Date(entry.created_at);
                  const when = format.relativeTime(created, now);
                  const action = labels.auditAction(entry.action);
                  return (
                    <Fragment key={entry.id}>
                      <TableRow>
                        <TableCell>
                          <time
                            dateTime={entry.created_at}
                            title={format.dateTime(created, {
                              dateStyle: "medium",
                              timeStyle: "medium",
                            })}
                            className="text-muted-foreground"
                          >
                            {when}
                          </time>
                        </TableCell>
                        <TableCell className="max-w-48">
                          <p className="truncate font-medium">
                            {entry.actor_name || entry.actor_email || t("unknownActor")}
                          </p>
                          {entry.actor_name && entry.actor_email && (
                            <p className="truncate text-xs text-muted-foreground">
                              {entry.actor_email}
                            </p>
                          )}
                        </TableCell>
                        <TableCell>
                          <p>{action}</p>
                          <p className="font-mono text-xs text-muted-foreground">{entry.action}</p>
                        </TableCell>
                        <TableCell className="max-w-48">
                          <AuditTarget entry={entry} prefix="" userName={view.userName} />
                        </TableCell>
                        <TableCell className="text-right">
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            aria-expanded={open}
                            aria-controls={open ? detailsId : undefined}
                            aria-label={t("detailsFor", { action, time: when })}
                            title={open ? t("hideDetails") : t("showDetails")}
                            onClick={() => view.toggle(entry.id)}
                          >
                            <ChevronDownIcon
                              aria-hidden
                              className={cn(
                                "transition-transform motion-reduce:transition-none",
                                open && "rotate-180",
                              )}
                            />
                          </Button>
                        </TableCell>
                      </TableRow>
                      {open && (
                        <TableRow className="hover:bg-transparent">
                          <TableCell colSpan={5} className="whitespace-normal" id={detailsId}>
                            <JsonView
                              value={auditEntryDetails(entry)}
                              label={t("detailsOf", { action, time: when })}
                              className="max-h-64"
                            />
                          </TableCell>
                        </TableRow>
                      )}
                    </Fragment>
                  );
                })}
              </TableBody>
            </Table>
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
              <div className="flex items-center gap-2">
                <span className="text-sm text-muted-foreground tabular-nums">
                  {t("page", {
                    page: format.number(view.page + 1),
                    pages: format.number(log.pageCount),
                  })}
                </span>
                <Button
                  variant="outline"
                  size="icon-sm"
                  aria-label={t("previous")}
                  disabled={!log.hasPreviousPage || query.isFetching}
                  onClick={() => view.goTo(view.page - 1)}
                >
                  <ChevronLeftIcon aria-hidden />
                </Button>
                <Button
                  variant="outline"
                  size="icon-sm"
                  aria-label={t("next")}
                  disabled={!log.hasNextPage || query.isFetching}
                  onClick={() => view.goTo(view.page + 1)}
                >
                  <ChevronRightIcon aria-hidden />
                </Button>
              </div>
            </nav>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
