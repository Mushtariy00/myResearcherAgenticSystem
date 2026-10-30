"use client";

import { useQuery } from "@tanstack/react-query";
import { WalletIcon } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { listBudgetsOptions } from "@/client/@tanstack/react-query.gen";
import { EmptyState, LoadingRows, QueryError } from "@/components/app/query-state";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { authErrorKey } from "@/lib/auth-client";
import { USD } from "@/lib/format";
import { cn } from "@/lib/utils";
import { budgetUse } from "./admin-format";
import { BudgetEditor } from "./budget-editor";
import { authErrorOf, displayName, useLabUsers } from "./use-lab-users";

const BAR_TONES = {
  success: "bg-primary",
  warning: "bg-amber-500",
  danger: "bg-destructive",
} as const;

/** Monthly LLM budgets of every lab member, edited inline, with this month's spend. */
export function BudgetsCard() {
  const t = useTranslations("admin.budgets");
  const te = useTranslations("auth.errors");
  const format = useFormatter();
  const users = useLabUsers();
  const budgets = useQuery(listBudgetsOptions());
  const budgetByUser = new Map((budgets.data ?? []).map((budget) => [budget.user_id, budget]));

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("title")}</CardTitle>
        <CardDescription>{t("description")}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        {budgets.isError && <QueryError error={budgets.error} onRetry={() => budgets.refetch()} />}
        {users.isPending ? (
          <LoadingRows rows={3} />
        ) : users.isError ? (
          <Alert variant="destructive">
            <AlertDescription>{te(authErrorKey(authErrorOf(users.error)))}</AlertDescription>
          </Alert>
        ) : users.data.length === 0 ? (
          <EmptyState icon={<WalletIcon aria-hidden />} title={t("empty")} />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("user")}</TableHead>
                <TableHead>{t("budget")}</TableHead>
                <TableHead className="text-right">{t("spent")}</TableHead>
                <TableHead className="hidden sm:table-cell">{t("used")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.data.map((user) => {
                const budget = budgetByUser.get(user.id);
                const use = budgetUse(budget);
                const name = displayName(user);
                return (
                  <TableRow key={user.id}>
                    <TableCell className="max-w-56">
                      <p className="truncate font-medium">{name}</p>
                      <p className="truncate text-xs text-muted-foreground">{user.email}</p>
                    </TableCell>
                    <TableCell>
                      {budgets.isPending ? (
                        <span className="text-muted-foreground">…</span>
                      ) : (
                        <BudgetEditor
                          key={budget?.monthly_usd ?? "none"}
                          userId={user.id}
                          userName={name}
                          budget={budget}
                        />
                      )}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {format.number(use.spent, USD)}
                    </TableCell>
                    <TableCell className="hidden w-40 sm:table-cell">
                      {use.monthly > 0 && (
                        <div className="flex items-center gap-2">
                          <div
                            role="progressbar"
                            aria-label={t("usedFor", { name })}
                            aria-valuemin={0}
                            aria-valuemax={100}
                            aria-valuenow={Math.round(use.percent)}
                            className="h-1.5 w-full overflow-hidden rounded-full bg-muted"
                          >
                            <div
                              className={cn("h-full rounded-full", BAR_TONES[use.tone])}
                              style={{ width: `${use.percent}%` }}
                            />
                          </div>
                          <span className="w-10 shrink-0 text-right text-xs text-muted-foreground tabular-nums">
                            {format.number(use.percent / 100, {
                              style: "percent",
                              maximumFractionDigits: 0,
                            })}
                          </span>
                        </div>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
