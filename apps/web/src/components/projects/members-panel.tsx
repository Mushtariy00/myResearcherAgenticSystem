"use client";

import { AlertCircleIcon, Trash2Icon, UserPlusIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { type FormEvent, useId, useState } from "react";
import { toast } from "sonner";
import type { MemberOut, ProjectRole } from "@/client";
import { useCurrentUser } from "@/components/app/current-user";
import { LoadingRows, QueryError } from "@/components/app/query-state";
import { RoleBadge } from "@/components/app/status-badge";
import { Alert, AlertAction, AlertDescription } from "@/components/ui/alert";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
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
import { useErrorMessage } from "@/hooks/use-error-message";
import { MEMBER_ROLES, type ProjectMembers, useMembers } from "@/hooks/use-members";

function isRole(value: unknown): value is ProjectRole {
  return typeof value === "string" && (MEMBER_ROLES as readonly string[]).includes(value);
}

/** Accounts removed from Better Auth have no name or email left: show the id. */
function memberName(member: MemberOut): string {
  return member.name || member.email || member.user_id;
}

function useRoleItems(): Record<ProjectRole, string> {
  const tr = useTranslations("roles");
  return { owner: tr("owner"), researcher: tr("researcher"), viewer: tr("viewer") };
}

function AddMemberForm({
  members,
  onShowRole,
}: {
  members: ProjectMembers;
  /** Moves to a member's role control (someone added who is a member already). */
  onShowRole: (userId: string) => void;
}) {
  const t = useTranslations("project.members");
  const errorMessage = useErrorMessage();
  const ids = useId();
  const roleItems = useRoleItems();
  const [role, setRole] = useState<ProjectRole>("researcher");
  const error = members.lastError?.action === "add" ? members.lastError : null;
  const existingId = error?.exists ? error.userId : null;

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const email = String(new FormData(formElement).get("email") ?? "");
    const result = await members.add({ email, role });
    if (result.ok) {
      formElement.reset();
      toast.success(t("added", { name: memberName(result.data) }));
    }
  }

  return (
    <form onSubmit={onSubmit} className="grid gap-3">
      {error && (
        <Alert variant="destructive">
          <AlertCircleIcon aria-hidden />
          <AlertDescription>{errorMessage(error.error)}</AlertDescription>
          {existingId && (
            <AlertAction>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => onShowRole(existingId)}
              >
                {t("changeRoleInstead")}
              </Button>
            </AlertAction>
          )}
        </Alert>
      )}
      <div className="grid gap-2">
        <Label htmlFor={`${ids}-email`}>{t("email")}</Label>
        <Input
          id={`${ids}-email`}
          name="email"
          type="email"
          required
          maxLength={320}
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
          <SelectTrigger
            className="w-full"
            aria-labelledby={`${ids}-role-label`}
            aria-describedby={`${ids}-role-hint`}
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {MEMBER_ROLES.map((value) => (
              <SelectItem key={value} value={value}>
                {roleItems[value]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p id={`${ids}-role-hint`} className="text-xs text-muted-foreground">
          {t(`roleHints.${role}`)}
        </p>
      </div>
      <Button type="submit" variant="outline" disabled={members.isAdding}>
        <UserPlusIcon aria-hidden />
        {members.isAdding ? t("adding") : t("add")}
      </Button>
    </form>
  );
}

type PendingRemoval = { member: MemberOut; self: boolean };
type PendingDemotion = { member: MemberOut; role: ProjectRole };

/**
 * A project's members. Owners and lab admins change roles and remove people (after a
 * confirmation), and add people by the email they were invited with; everyone else sees the
 * list. A refused change, such as demoting the last owner, says why under that member.
 */
export function MembersPanel({ projectId, canManage }: { projectId: string; canManage: boolean }) {
  const t = useTranslations("project.members");
  const tr = useTranslations("roles");
  const errorMessage = useErrorMessage();
  const user = useCurrentUser();
  const router = useRouter();
  const members = useMembers(projectId);
  const roleItems = useRoleItems();
  const listId = useId();
  const roleControlId = (userId: string) => `${listId}-role-${userId}`;
  // The dialogs keep what they ask about while they close, so their text does not change.
  const [removal, setRemoval] = useState<PendingRemoval | null>(null);
  const [removalOpen, setRemovalOpen] = useState(false);
  const [demotion, setDemotion] = useState<PendingDemotion | null>(null);
  const [demotionOpen, setDemotionOpen] = useState(false);
  const isAdmin = user.role === "admin";

  async function changeRole(member: MemberOut, role: ProjectRole) {
    const result = await members.updateRole(member.user_id, role);
    if (result.ok) {
      toast.success(
        t("roleChanged", { name: memberName(result.data), role: tr(result.data.role) }),
      );
    }
  }

  function requestRoleChange(member: MemberOut, role: ProjectRole) {
    if (role === member.role) {
      return;
    }
    // An owner who steps down can no longer manage the project: ask first.
    if (!isAdmin && member.user_id === user.id && member.role === "owner") {
      setDemotion({ member, role });
      setDemotionOpen(true);
      return;
    }
    void changeRole(member, role);
  }

  function requestRemoval(member: MemberOut) {
    setRemoval({ member, self: member.user_id === user.id });
    setRemovalOpen(true);
  }

  async function confirmRemoval() {
    if (!removal) {
      return;
    }
    const { member, self } = removal;
    setRemovalOpen(false);
    const result = await members.remove(member.user_id);
    if (!result.ok) {
      return;
    }
    if (self && !isAdmin) {
      // Without a membership the project page would only say "not found".
      toast.success(t("left"));
      router.push("/");
      return;
    }
    toast.success(t("removed", { name: memberName(member) }));
  }

  async function confirmDemotion() {
    if (!demotion) {
      return;
    }
    const { member, role } = demotion;
    setDemotionOpen(false);
    await changeRole(member, role);
  }

  const failed = members.lastError && members.lastError.action !== "add" ? members.lastError : null;

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem] lg:items-start">
      <Card>
        <CardHeader>
          <CardTitle>
            <h2>{t("title")}</h2>
          </CardTitle>
          <CardDescription>{canManage ? t("descriptionManage") : t("description")}</CardDescription>
        </CardHeader>
        <CardContent>
          {members.query.isPending ? (
            <LoadingRows rows={3} />
          ) : members.query.isError ? (
            <QueryError error={members.query.error} onRetry={() => members.query.refetch()} />
          ) : members.members.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("empty")}</p>
          ) : (
            <ul className="divide-y">
              {members.members.map((member) => {
                const name = memberName(member);
                const self = member.user_id === user.id;
                const pending = members.pendingUserIds.has(member.user_id);
                const error = failed?.userId === member.user_id ? failed : null;
                return (
                  <li
                    key={member.user_id}
                    className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 py-3 first:pt-0 last:pb-0"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">
                        {name}
                        {self && (
                          <span className="font-normal text-muted-foreground"> ({t("you")})</span>
                        )}
                      </p>
                      {member.email && member.email !== name && (
                        <p className="truncate text-xs text-muted-foreground">{member.email}</p>
                      )}
                    </div>
                    {canManage ? (
                      <div className="flex items-center gap-1">
                        <Select
                          items={roleItems}
                          value={member.role}
                          disabled={pending}
                          onValueChange={(value) => {
                            if (isRole(value)) {
                              requestRoleChange(member, value);
                            }
                          }}
                        >
                          <SelectTrigger
                            id={roleControlId(member.user_id)}
                            size="sm"
                            className="w-36"
                            aria-label={t("roleOf", { name })}
                          >
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {MEMBER_ROLES.map((value) => (
                              <SelectItem key={value} value={value}>
                                {roleItems[value]}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon-sm"
                          disabled={pending}
                          aria-label={self ? t("leave") : t("removeLabel", { name })}
                          title={self ? t("leave") : t("removeLabel", { name })}
                          onClick={() => requestRemoval(member)}
                        >
                          <Trash2Icon aria-hidden />
                        </Button>
                      </div>
                    ) : (
                      <RoleBadge role={member.role} />
                    )}
                    {error && (
                      <p role="alert" className="w-full text-sm text-destructive">
                        {error.lastOwner ? t("lastOwner") : errorMessage(error.error)}
                      </p>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </CardContent>
      </Card>
      {canManage ? (
        <Card>
          <CardHeader>
            <CardTitle>
              <h3>{t("addTitle")}</h3>
            </CardTitle>
            <CardDescription>{t("addDescription")}</CardDescription>
          </CardHeader>
          <CardContent>
            <AddMemberForm
              members={members}
              onShowRole={(userId) => document.getElementById(roleControlId(userId))?.focus()}
            />
          </CardContent>
        </Card>
      ) : (
        <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
          {t("readOnly")}
        </p>
      )}

      <AlertDialog open={removalOpen} onOpenChange={setRemovalOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {removal?.self
                ? t("leaveTitle")
                : t("removeTitle", { name: removal ? memberName(removal.member) : "" })}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {removal?.self && !isAdmin ? t("leaveDescription") : t("removeDescription")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("keep")}</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={confirmRemoval}>
              {removal?.self ? t("leaveConfirm") : t("removeConfirm")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={demotionOpen} onOpenChange={setDemotionOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t("stepDownTitle", { role: demotion ? tr(demotion.role) : "" })}
            </AlertDialogTitle>
            <AlertDialogDescription>{t("stepDownDescription")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("keepOwner")}</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDemotion}>{t("stepDownConfirm")}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
