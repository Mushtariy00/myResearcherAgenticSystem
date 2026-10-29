"use client";

import { useQuery } from "@tanstack/react-query";
import { HistoryIcon } from "lucide-react";
import Link from "next/link";
import { useFormatter, useTranslations } from "next-intl";
import { listRunsOptions } from "@/client/@tanstack/react-query.gen";
import { EmptyState, LoadingRows, QueryError } from "@/components/app/query-state";
import { RunStatusBadge } from "@/components/app/status-badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { toAmount, USD } from "@/lib/format";
import { isTerminalRunStatus } from "@/lib/timeline";

export function RunsCard({ projectId }: { projectId: string }) {
  const t = useTranslations("project.runs");
  const tp = useTranslations("project.newRun.policies");
  const format = useFormatter();
  const runs = useQuery({
    ...listRunsOptions({ path: { project_id: projectId } }),
    // Keep statuses fresh while something is still running.
    refetchInterval: (query) =>
      query.state.data?.some((run) => !isTerminalRunStatus(run.status)) ? 15_000 : false,
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("title")}</CardTitle>
      </CardHeader>
      <CardContent>
        {runs.isPending ? (
          <LoadingRows rows={3} />
        ) : runs.isError ? (
          <QueryError error={runs.error} onRetry={() => runs.refetch()} />
        ) : runs.data.length === 0 ? (
          <EmptyState icon={<HistoryIcon aria-hidden />} title={t("empty")} />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("topic")}</TableHead>
                <TableHead>{t("status")}</TableHead>
                <TableHead className="hidden sm:table-cell">{t("policy")}</TableHead>
                <TableHead className="hidden text-right md:table-cell">{t("cap")}</TableHead>
                <TableHead className="hidden md:table-cell">{t("created")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {runs.data.map((run) => (
                <TableRow key={run.id}>
                  <TableCell className="max-w-72 whitespace-normal">
                    <Link
                      href={`/runs/${run.id}`}
                      className="line-clamp-2 font-medium underline-offset-4 hover:underline focus-visible:underline focus-visible:outline-none"
                    >
                      {run.topic}
                    </Link>
                  </TableCell>
                  <TableCell>
                    <RunStatusBadge status={run.status} />
                  </TableCell>
                  <TableCell className="hidden sm:table-cell">
                    {tp(`${run.llm_policy}.label`)}
                  </TableCell>
                  <TableCell className="hidden text-right tabular-nums md:table-cell">
                    {run.budget_cap_usd === null
                      ? t("noCap")
                      : format.number(toAmount(run.budget_cap_usd), USD)}
                  </TableCell>
                  <TableCell className="hidden text-muted-foreground md:table-cell">
                    {format.dateTime(new Date(run.created_at), {
                      dateStyle: "medium",
                      timeStyle: "short",
                    })}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
