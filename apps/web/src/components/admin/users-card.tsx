"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRoundIcon, SaveIcon } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { type FormEvent, useId, useState, useTransition } from "react";
import { toast } from "sonner";
import type { BudgetOut } from "@/client";
import {
  listBudgetsOptions,
  listBudgetsQueryKey,
  setBudgetMutation,
} from "@/client/@tanstack/react-query.gen";
import { LoadingRows, QueryError } from "@/components/app/query-state";
import { RoleBadge } from "@/components/app/status-badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useErrorMessage } from "@/hooks/use-error-message";
import { sendPasswordLink } from "@/lib/admin-actions";
import { authClient, authErrorKey } from "@/lib/auth-client";
import { toAmount, USD } from "@/lib/format";
import type { IssuedLink } from "./link-dialog";

export const ADMIN_USERS_QUERY_KEY = ["admin", "users"] as const;

type LabUser = {
  id: string;
  name: string;
  email: string;
  role?: string | null | undefined;
  banned?: boolean | null | undefined;
  createdAt: Date | string;
};

class AuthRequestError extends Error {
  readonly code: string | undefined;
  readonly status: number | undefined;
  constructor(error: { code?: string | undefined; status?: number | undefined }) {
    super(error.code ?? "UNKNOWN");
    this.code = error.code;
    this.status = error.status;
  }
}

function BudgetEditor({ userId, budget }: { userId: string; budget: BudgetOut | undefined }) {
  const t = useTranslations("admin.users");
  const errorMessage = useErrorMessage();
  const queryClient = useQueryClient();
  const id = useId();
  const initial = String(toAmount(budget?.monthly_usd));
  const [value, setValue] = useState(initial);
  const save = useMutation({
    ...setBudgetMutation(),
    onSuccess: async () => {
      toast.success(t("budgetSaved"));
      await queryClient.invalidateQueries({ queryKey: listBudgetsQueryKey() });
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    save.mutate({ path: { user_id: userId }, body: { monthly_usd: value.trim() || "0" } });
  }

  return (
    <form onSubmit={onSubmit} className="flex items-center gap-1.5">
      <label htmlFor={id} className="sr-only">
        {t("budget")}
      </label>
      <span aria-hidden className="text-muted-foreground">
        $
      </span>
      <Input
        id={id}
        type="number"
        inputMode="decimal"
        min={0}
        max={10000}
        step="0.01"
        required
        value={value}
        onChange={(event) => setValue(event.target.value)}
        className="h-7 w-24 tabular-nums"
      />
      <Button
        type="submit"
        size="icon-sm"
        variant="outline"
        disabled={save.isPending || value === initial}
        aria-label={t("saveBudget")}
        title={t("saveBudget")}
      >
        <SaveIcon aria-hidden />
      </Button>
    </form>
  );
}

export function UsersCard({ onIssued }: { onIssued: (link: IssuedLink) => void }) {
  const t = useTranslations("admin.users");
  const te = useTranslations("auth.errors");
  const format = useFormatter();
  const [pendingLink, startLink] = useTransition();
  const [linkError, setLinkError] = useState<string | null>(null);

  const users = useQuery({
    queryKey: ADMIN_USERS_QUERY_KEY,
    queryFn: async (): Promise<LabUser[]> => {
      const { data, error } = await authClient.admin.listUsers({
        query: { limit: 500, sortBy: "createdAt", sortDirection: "desc" },
      });
      if (error) {
        throw new AuthRequestError(error);
      }
      return data.users as LabUser[];
    },
  });
  const budgets = useQuery(listBudgetsOptions());
  const budgetByUser = new Map((budgets.data ?? []).map((budget) => [budget.user_id, budget]));

  function newLink(email: string) {
    setLinkError(null);
    startLink(async () => {
      const result = await sendPasswordLink({ email });
      if (!result.ok) {
        setLinkError(te(authErrorKey({ code: result.code })));
        return;
      }
      onIssued({ email, url: result.url, emailed: result.emailed, kind: "reset" });
    });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("title")}</CardTitle>
        <CardDescription>{t("description")}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        {linkError && (
          <Alert variant="destructive">
            <AlertDescription>{linkError}</AlertDescription>
          </Alert>
        )}
        {budgets.isError && <QueryError error={budgets.error} onRetry={() => budgets.refetch()} />}
        {users.isPending ? (
          <LoadingRows rows={3} />
        ) : users.isError ? (
          <Alert variant="destructive">
            <AlertDescription>
              {te(
                authErrorKey(
                  users.error instanceof AuthRequestError
                    ? { code: users.error.code, status: users.error.status }
                    : null,
                ),
              )}
            </AlertDescription>
          </Alert>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("user")}</TableHead>
                <TableHead>{t("role")}</TableHead>
                <TableHead>{t("budget")}</TableHead>
                <TableHead className="text-right">{t("spent")}</TableHead>
                <TableHead className="hidden lg:table-cell">{t("joined")}</TableHead>
                <TableHead>
                  <span className="sr-only">{t("actions")}</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.data.map((user) => {
                const budget = budgetByUser.get(user.id);
                return (
                  <TableRow key={user.id}>
                    <TableCell className="max-w-56">
                      <p className="truncate font-medium">{user.name}</p>
                      <p className="truncate text-xs text-muted-foreground">{user.email}</p>
                      {user.banned && <p className="text-xs text-destructive">{t("banned")}</p>}
                    </TableCell>
                    <TableCell>
                      <RoleBadge role={user.role === "admin" ? "admin" : "user"} />
                    </TableCell>
                    <TableCell>
                      {budgets.isPending ? (
                        <span className="text-muted-foreground">…</span>
                      ) : (
                        <BudgetEditor
                          key={budget?.monthly_usd ?? "none"}
                          userId={user.id}
                          budget={budget}
                        />
                      )}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {format.number(toAmount(budget?.spent_usd), USD)}
                    </TableCell>
                    <TableCell className="hidden text-muted-foreground lg:table-cell">
                      {format.dateTime(new Date(user.createdAt), { dateStyle: "medium" })}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={pendingLink}
                        onClick={() => newLink(user.email)}
                      >
                        <KeyRoundIcon aria-hidden />
                        {t("newLink")}
                      </Button>
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
