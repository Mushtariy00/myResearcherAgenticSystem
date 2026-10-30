"use client";

import { UsersIcon } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useCurrentUser } from "@/components/app/current-user";
import { EmptyState, LoadingRows } from "@/components/app/query-state";
import { RoleBadge } from "@/components/app/status-badge";
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
import { authErrorKey } from "@/lib/auth-client";
import type { IssuedLink } from "./link-dialog";
import { authErrorOf, useLabUsers } from "./use-lab-users";
import { usePasswordLink } from "./use-password-link";
import { UserActionsMenu } from "./user-actions-menu";

/** Every lab account with its role and status, and the row actions (links and offboarding). */
export function UsersCard({ onIssued }: { onIssued: (link: IssuedLink) => void }) {
  const t = useTranslations("admin.users");
  const te = useTranslations("auth.errors");
  const format = useFormatter();
  const me = useCurrentUser();
  const users = useLabUsers();
  const passwordLink = usePasswordLink(onIssued);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("title")}</CardTitle>
        <CardDescription>{t("description")}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        {passwordLink.error && (
          <Alert variant="destructive">
            <AlertDescription>{passwordLink.error}</AlertDescription>
          </Alert>
        )}
        {users.isPending ? (
          <LoadingRows rows={3} />
        ) : users.isError ? (
          <Alert variant="destructive">
            <AlertDescription>{te(authErrorKey(authErrorOf(users.error)))}</AlertDescription>
          </Alert>
        ) : users.data.length === 0 ? (
          <EmptyState icon={<UsersIcon aria-hidden />} title={t("empty")} />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("user")}</TableHead>
                <TableHead>{t("role")}</TableHead>
                <TableHead>{t("status")}</TableHead>
                <TableHead className="hidden md:table-cell">{t("joined")}</TableHead>
                <TableHead className="w-10">
                  <span className="sr-only">{t("actions")}</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.data.map((user) => {
                const isSelf = user.id === me.id;
                return (
                  <TableRow key={user.id}>
                    <TableCell className="max-w-64">
                      <p className="flex min-w-0 items-center gap-2 font-medium">
                        <span className="truncate">{user.name || user.email}</span>
                        {isSelf && <Badge variant="outline">{t("you")}</Badge>}
                      </p>
                      <p className="truncate text-xs text-muted-foreground">{user.email}</p>
                    </TableCell>
                    <TableCell>
                      <RoleBadge role={user.role === "admin" ? "admin" : "user"} />
                    </TableCell>
                    <TableCell>
                      {user.banned ? (
                        <Badge variant="destructive">{t("banned")}</Badge>
                      ) : (
                        <span className="text-muted-foreground">{t("active")}</span>
                      )}
                    </TableCell>
                    <TableCell className="hidden text-muted-foreground md:table-cell">
                      {format.dateTime(new Date(user.createdAt), { dateStyle: "medium" })}
                    </TableCell>
                    <TableCell className="text-right">
                      <UserActionsMenu
                        user={user}
                        isSelf={isSelf}
                        onPasswordLink={passwordLink.issue}
                        passwordLinkPending={passwordLink.pending}
                      />
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
