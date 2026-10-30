"use client";

import { RouteIcon, TriangleAlertIcon } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import type { RoutedModelOut } from "@/client";
import { EmptyState, LoadingRows, QueryError } from "@/components/app/query-state";
import { DemoBadge } from "@/components/shared/demo-badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useModelRouting } from "@/hooks/use-model-routing";
import { cn } from "@/lib/utils";
import { keyedChain } from "./admin-format";
import { useAdminLabels, useModelText } from "./admin-labels";

/** A model chain in the order the gateway tries it, with price and context per model. */
function ModelChain({ models, skipped }: { models: RoutedModelOut[]; skipped?: boolean }) {
  const t = useTranslations("admin.routing");
  const describe = useModelText();
  if (models.length === 0) {
    return <span className="text-muted-foreground">{t("none")}</span>;
  }
  return (
    <div className="grid gap-1.5">
      {skipped && <p className="text-xs font-medium text-muted-foreground">{t("skipped")}</p>}
      <ol className={cn("grid gap-2", skipped && "border-l-2 border-dashed pl-2")}>
        {keyedChain(models).map(({ key, model }, index) => {
          const { price, context } = describe(model);
          return (
            <li key={key} className="grid min-w-0 gap-0.5">
              <span className="flex min-w-0 items-baseline gap-1.5">
                <span aria-hidden className="text-xs text-muted-foreground tabular-nums">
                  {index + 1}.
                </span>
                <span className="truncate font-mono text-xs">{model.id}</span>
              </span>
              <span className="pl-4 text-xs whitespace-normal text-muted-foreground">
                {context ? `${price} · ${context}` : price}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

/** Per agent role, the paid and the free model chains, and the kill switch's real state. */
export function ModelRoutingCard() {
  const t = useTranslations("admin.routing");
  const format = useFormatter();
  const labels = useAdminLabels();
  const routing = useModelRouting();
  const paidOn = routing.data?.paid_models_enabled ?? true;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          {t("title")}
          <DemoBadge demo={routing.data?.demo} />
          {routing.data && (
            <Badge variant={paidOn ? "secondary" : "destructive"}>
              {paidOn ? t("paidOn") : t("paidOff")}
            </Badge>
          )}
        </CardTitle>
        <CardDescription>{t("description")}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        {routing.isPending ? (
          <LoadingRows rows={4} />
        ) : routing.isError ? (
          <QueryError error={routing.error} onRetry={() => routing.refetch()} />
        ) : routing.data.roles.length === 0 ? (
          <EmptyState icon={<RouteIcon aria-hidden />} title={t("empty")} />
        ) : (
          <>
            {!paidOn && (
              <Alert>
                <TriangleAlertIcon aria-hidden />
                <AlertDescription>{t("paidOffNotice")}</AlertDescription>
              </Alert>
            )}
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("role")}</TableHead>
                  <TableHead>{t("paid")}</TableHead>
                  <TableHead>{t("free")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {routing.data.roles.map((role) => (
                  <TableRow key={role.role} className="align-top">
                    <TableCell className="align-top">
                      <p className="font-medium">{labels.agentRole(role.role)}</p>
                      <p className="text-xs whitespace-normal text-muted-foreground">
                        {t("maxOutput", { tokens: format.number(role.max_output_tokens) })}
                      </p>
                    </TableCell>
                    <TableCell className="min-w-56 align-top">
                      <ModelChain models={role.paid} skipped={!paidOn} />
                    </TableCell>
                    <TableCell className="min-w-56 align-top">
                      <ModelChain models={role.free} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </>
        )}
      </CardContent>
    </Card>
  );
}
