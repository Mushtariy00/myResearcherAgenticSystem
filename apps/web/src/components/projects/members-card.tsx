"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircleIcon, UserPlusIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { type FormEvent, useId, useState } from "react";
import { toast } from "sonner";
import type { ProjectRole } from "@/client";
import {
  addMemberMutation,
  listMembersOptions,
  listMembersQueryKey,
} from "@/client/@tanstack/react-query.gen";
import { LoadingRows, QueryError } from "@/components/app/query-state";
import { RoleBadge } from "@/components/app/status-badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { useErrorMessage } from "@/hooks/use-error-message";

const ROLES: readonly ProjectRole[] = ["owner", "researcher", "viewer"];

function isRole(value: unknown): value is ProjectRole {
  return typeof value === "string" && (ROLES as readonly string[]).includes(value);
}

function AddMemberForm({ projectId }: { projectId: string }) {
  const t = useTranslations("project.members");
  const tr = useTranslations("roles");
  const errorMessage = useErrorMessage();
  const queryClient = useQueryClient();
  const ids = useId();
  const [role, setRole] = useState<ProjectRole>("researcher");
  const add = useMutation({
    ...addMemberMutation(),
    onSuccess: async (member, _variables) => {
      await queryClient.invalidateQueries({
        queryKey: listMembersQueryKey({ path: { project_id: projectId } }),
      });
      toast.success(t("added", { name: member.name || member.email }));
    },
  });

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const email = String(new FormData(formElement).get("email") ?? "").trim();
    add.mutate(
      { path: { project_id: projectId }, body: { email, role } },
      { onSuccess: () => formElement.reset() },
    );
  }

  const roleItems = Object.fromEntries(ROLES.map((value) => [value, tr(value)]));

  return (
    <form onSubmit={onSubmit} className="grid gap-3">
      <p className="text-sm font-medium">{t("addTitle")}</p>
      {add.isError && (
        <Alert variant="destructive">
          <AlertCircleIcon aria-hidden />
          <AlertDescription>{errorMessage(add.error)}</AlertDescription>
        </Alert>
      )}
      <div className="grid gap-2">
        <Label htmlFor={`${ids}-email`}>{t("email")}</Label>
        <Input
          id={`${ids}-email`}
          name="email"
          type="email"
          required
          autoComplete="off"
          placeholder={t("emailPlaceholder")}
        />
      </div>
      <div className="grid gap-2">
        <Label id={`${ids}-role-label`}>{t("role")}</Label>
        <Select
          items={roleItems}
          value={role}
          onValueChange={(value) => {
            if (isRole(value)) {
              setRole(value);
            }
          }}
        >
          <SelectTrigger className="w-full" aria-labelledby={`${ids}-role-label`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {ROLES.map((value) => (
              <SelectItem key={value} value={value}>
                {tr(value)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-xs text-muted-foreground">{t(`roleHints.${role}`)}</p>
      </div>
      <Button type="submit" variant="outline" disabled={add.isPending}>
        <UserPlusIcon aria-hidden />
        {add.isPending ? t("adding") : t("add")}
      </Button>
    </form>
  );
}

export function MembersCard({ projectId, canManage }: { projectId: string; canManage: boolean }) {
  const t = useTranslations("project.members");
  const members = useQuery(listMembersOptions({ path: { project_id: projectId } }));

  return (
    <Card className="h-fit">
      <CardHeader>
        <CardTitle>{t("title")}</CardTitle>
        <CardDescription>{canManage ? t("descriptionOwner") : t("description")}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        {members.isPending ? (
          <LoadingRows rows={2} />
        ) : members.isError ? (
          <QueryError error={members.error} onRetry={() => members.refetch()} />
        ) : members.data.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("empty")}</p>
        ) : (
          <ul className="grid gap-3">
            {members.data.map((member) => (
              <li key={member.user_id} className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  {/* Accounts removed from Better Auth have no name or email left: show the id. */}
                  <p className="truncate text-sm font-medium">
                    {member.name || member.email || member.user_id}
                  </p>
                  {member.email && (
                    <p className="truncate text-xs text-muted-foreground">{member.email}</p>
                  )}
                </div>
                <RoleBadge role={member.role} />
              </li>
            ))}
          </ul>
        )}
        {canManage && (
          <>
            <Separator />
            <AddMemberForm projectId={projectId} />
          </>
        )}
      </CardContent>
    </Card>
  );
}
