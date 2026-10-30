"use client";

import { AlertDialog } from "@base-ui/react/alert-dialog";
import { CrownIcon, TrashIcon, TriangleAlertIcon, UserPlusIcon, UsersIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { type FormEvent, useId, useState } from "react";
import { toast } from "sonner";
import type { MemberOut, ProjectRole } from "@/client";
import { useCurrentUser } from "@/components/app/current-user";
import { useErrorMessage } from "@/hooks/use-error-message";
import { MEMBER_ROLES, useMembers } from "@/hooks/use-members";
import { cn } from "@/lib/utils";
import { STUDIO_BACKDROP } from "@/studio/components/dashboard/create-project-dialog";
import {
  STUDIO_FIELD,
  STUDIO_HINT,
  STUDIO_LABEL,
  StudioSelect,
} from "@/studio/components/dashboard/studio-fields";
import { StudioInlineError, StudioPanel } from "@/studio/components/dashboard/studio-panel";
import { PulseDot } from "@/studio/components/effects/pulse-dot";
import { ShimmerButton } from "@/studio/components/effects/shimmer-button";
import { LoadingStatus, ShimmerSkeleton } from "@/studio/components/effects/shimmer-skeleton";
import { StudioAvatar } from "@/studio/components/shell/user-card";
import { StudioStatePanel } from "@/studio/components/studio-state-panel";
import { GHOST_BUTTON, ICON_BUTTON } from "@/studio/lib/ui";

const ROLE_TONES: Record<ProjectRole, "info" | "success" | "neutral"> = {
  owner: "info",
  researcher: "success",
  viewer: "neutral",
};

function isRole(value: string): value is ProjectRole {
  return (MEMBER_ROLES as readonly string[]).includes(value);
}

/** Accounts removed from Better Auth have no name or email left: the id stands in. */
function memberName(member: MemberOut): string {
  return member.name || member.email || member.user_id;
}

function RolePill({ role }: { role: ProjectRole }) {
  const t = useTranslations("roles");
  return (
    <span
      data-tone={ROLE_TONES[role]}
      className="inline-flex h-6 shrink-0 items-center gap-1 rounded-full border border-(--tone)/25 bg-(--tone)/12 px-2 text-xs font-medium text-(--tone-fg)"
    >
      {role === "owner" && <CrownIcon aria-hidden className="size-3" />}
      {t(role)}
    </span>
  );
}

function AddMemberForm({
  onAdd,
  adding,
}: {
  onAdd: (input: { email: string; role: ProjectRole }) => Promise<boolean>;
  adding: boolean;
}) {
  const t = useTranslations("project.members");
  const tRoles = useTranslations("roles");
  const ids = useId();
  const [role, setRole] = useState<ProjectRole>("researcher");

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const email = String(new FormData(form).get("email") ?? "").trim();
    if (await onAdd({ email, role })) {
      form.reset();
      setRole("researcher");
    }
  }

  return (
    <form onSubmit={onSubmit} className="grid gap-4" aria-labelledby={`${ids}-title`}>
      <h3 id={`${ids}-title`} className="text-sm font-semibold text-foreground">
        {t("addTitle")}
      </h3>
      <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_12rem]">
        <div className="grid gap-1.5">
          <label htmlFor={`${ids}-email`} className={STUDIO_LABEL}>
            {t("email")}
          </label>
          <input
            id={`${ids}-email`}
            name="email"
            type="email"
            required
            autoComplete="off"
            placeholder={t("emailPlaceholder")}
            className={STUDIO_FIELD}
          />
        </div>
        <div className="grid gap-1.5">
          <label htmlFor={`${ids}-role`} className={STUDIO_LABEL}>
            {t("role")}
          </label>
          <StudioSelect
            id={`${ids}-role`}
            value={role}
            aria-describedby={`${ids}-role-hint`}
            onChange={(event) => {
              if (isRole(event.target.value)) {
                setRole(event.target.value);
              }
            }}
          >
            {MEMBER_ROLES.map((value) => (
              <option key={value} value={value}>
                {tRoles(value)}
              </option>
            ))}
          </StudioSelect>
        </div>
      </div>
      <p id={`${ids}-role-hint`} className={STUDIO_HINT}>
        {t(`roleHints.${role}`)}
      </p>
      <div>
        <ShimmerButton type="submit" disabled={adding}>
          <UserPlusIcon aria-hidden />
          {adding ? t("adding") : t("add")}
        </ShimmerButton>
      </div>
    </form>
  );
}

/**
 * The project's members (useMembers). Owners and lab admins change roles, remove people (after
 * a confirmation) and add them by the email they were invited with; everyone else sees the list.
 * Changes wait for the API, so a refused one, such as demoting the last owner, never looks done:
 * the role stays, and the reason shows above the list.
 */
export function ProjectMembersTab({
  projectId,
  canManage,
}: {
  projectId: string;
  canManage: boolean;
}) {
  const t = useTranslations("studioWork.project.members");
  const tMembers = useTranslations("project.members");
  const tRoles = useTranslations("roles");
  const tCommon = useTranslations("common");
  const errorMessage = useErrorMessage();
  const user = useCurrentUser();
  const members = useMembers(projectId);
  const [removing, setRemoving] = useState<MemberOut | null>(null);
  const listId = useId();
  const roleControlId = (userId: string) => `${listId}-role-${userId}`;
  const failed = members.lastError;
  const failedMember = failed?.userId
    ? members.members.find((member) => member.user_id === failed.userId)
    : undefined;

  async function changeRole(member: MemberOut, role: ProjectRole) {
    if (role === member.role) {
      return;
    }
    const result = await members.updateRole(member.user_id, role);
    if (result.ok) {
      toast.success(t("roleChanged", { name: memberName(member), role: tRoles(role) }));
    }
  }

  async function remove(member: MemberOut) {
    setRemoving(null);
    const result = await members.remove(member.user_id);
    if (result.ok) {
      toast.success(t("removed", { name: memberName(member) }));
    }
  }

  async function add(input: { email: string; role: ProjectRole }): Promise<boolean> {
    const result = await members.add(input);
    if (result.ok) {
      toast.success(tMembers("added", { name: result.data.name || result.data.email }));
    }
    return result.ok;
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,24rem)] lg:items-start">
      <StudioPanel
        id="studio-members"
        title={tMembers("title")}
        description={canManage ? tMembers("descriptionOwner") : tMembers("description")}
        busy={members.query.isPending}
      >
        {failed && (
          <div
            role="alert"
            data-tone="danger"
            className="flex items-start gap-3 rounded-xl border border-(--tone)/30 bg-(--tone)/8 px-4 py-3 text-sm"
          >
            <TriangleAlertIcon aria-hidden className="mt-0.5 size-4 shrink-0 text-(--tone-fg)" />
            <div className="grid min-w-0 flex-1 gap-0.5">
              <p className="font-medium text-foreground">{errorMessage(failed.error)}</p>
              {failed.lastOwner && (
                <p className="text-pretty text-muted-foreground">
                  {failedMember
                    ? t("lastOwnerNamed", { name: memberName(failedMember) })
                    : t("lastOwner")}
                </p>
              )}
            </div>
            {failed.exists && failedMember && canManage && (
              <button
                type="button"
                onClick={() =>
                  document.getElementById(roleControlId(failedMember.user_id))?.focus()
                }
                className={cn(GHOST_BUTTON, "h-8 px-2.5 text-xs")}
              >
                {tMembers("changeRoleInstead")}
              </button>
            )}
            <button
              type="button"
              onClick={members.clearError}
              className={cn(GHOST_BUTTON, "h-8 px-2.5 text-xs")}
            >
              {t("dismiss")}
            </button>
          </div>
        )}
        {members.query.isPending ? (
          <div className="grid gap-2">
            <LoadingStatus label={tCommon("loading")} />
            {Array.from({ length: 3 }, (_, index) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: static placeholders never reorder
              <ShimmerSkeleton key={index} className="h-16 rounded-xl" />
            ))}
          </div>
        ) : members.query.isError ? (
          <StudioInlineError error={members.query.error} onRetry={() => members.query.refetch()} />
        ) : members.members.length === 0 ? (
          <StudioStatePanel
            variant="section"
            headingLevel={3}
            icon={<UsersIcon aria-hidden />}
            title={tMembers("empty")}
            description={canManage ? tMembers("descriptionOwner") : tMembers("description")}
          />
        ) : (
          <ul className="grid gap-2">
            {members.members.map((member) => {
              const name = memberName(member);
              const pending = members.pendingUserIds.has(member.user_id);
              const you = member.user_id === user.id;
              return (
                <li
                  key={member.user_id}
                  aria-busy={pending || undefined}
                  className={cn(
                    "flex flex-wrap items-center gap-3 rounded-xl border border-(--studio-glass-border) bg-(--studio-glass) p-3",
                    failed?.userId === member.user_id && "border-(--studio-danger)/50",
                  )}
                >
                  <StudioAvatar name={member.name} email={member.email || member.user_id} />
                  <div className="grid min-w-0 flex-1 gap-0.5">
                    <p className="flex min-w-0 items-center gap-2 text-sm font-medium text-foreground">
                      <span className="truncate">{name}</span>
                      {you && (
                        <span className="shrink-0 text-xs font-normal text-muted-foreground">
                          {t("you")}
                        </span>
                      )}
                    </p>
                    {member.email && member.email !== name && (
                      <p className="truncate text-xs text-muted-foreground">{member.email}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    {pending && <PulseDot tone="info" live label={t("saving")} />}
                    {canManage ? (
                      <StudioSelect
                        id={roleControlId(member.user_id)}
                        aria-label={t("roleOf", { name })}
                        value={member.role}
                        disabled={pending}
                        onChange={(event) => {
                          if (isRole(event.target.value)) {
                            void changeRole(member, event.target.value);
                          }
                        }}
                        className="w-36"
                      >
                        {MEMBER_ROLES.map((value) => (
                          <option key={value} value={value}>
                            {tRoles(value)}
                          </option>
                        ))}
                      </StudioSelect>
                    ) : (
                      <RolePill role={member.role} />
                    )}
                    {canManage && (
                      <button
                        type="button"
                        onClick={() => setRemoving(member)}
                        disabled={pending}
                        aria-label={t("remove", { name })}
                        title={t("remove", { name })}
                        className={cn(ICON_BUTTON, "hover:text-(--studio-danger-fg)")}
                      >
                        <TrashIcon aria-hidden />
                      </button>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </StudioPanel>

      {canManage && (
        <section className="studio-glass rounded-2xl p-4 sm:p-6" aria-label={tMembers("addTitle")}>
          <AddMemberForm onAdd={add} adding={members.isAdding} />
        </section>
      )}

      <AlertDialog.Root
        open={removing !== null}
        onOpenChange={(open) => {
          if (!open) {
            setRemoving(null);
          }
        }}
      >
        <AlertDialog.Portal>
          <AlertDialog.Backdrop className={STUDIO_BACKDROP} />
          <AlertDialog.Popup className="studio-glass studio-blur fixed top-1/2 left-1/2 z-50 grid w-[min(26rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 gap-4 rounded-2xl bg-(--studio-glass-strong) p-5 text-foreground outline-none transition-[scale,opacity] duration-200 data-ending-style:scale-[0.98] data-ending-style:opacity-0 data-starting-style:scale-[0.98] data-starting-style:opacity-0 motion-reduce:transition-none sm:p-6">
            <AlertDialog.Title className="text-lg font-semibold text-foreground">
              {t("removeTitle", { name: removing ? memberName(removing) : "" })}
            </AlertDialog.Title>
            <AlertDialog.Description className="text-sm text-pretty text-muted-foreground">
              {t("removeDescription")}
            </AlertDialog.Description>
            <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <AlertDialog.Close className={cn(GHOST_BUTTON, "h-10 justify-center")}>
                {tCommon("cancel")}
              </AlertDialog.Close>
              <button
                type="button"
                data-tone="danger"
                onClick={() => {
                  if (removing) {
                    void remove(removing);
                  }
                }}
                className="inline-flex h-10 items-center justify-center gap-2 rounded-[10px] border border-(--tone)/40 bg-(--tone)/12 px-4 text-sm font-semibold text-(--tone-fg) outline-none transition-colors hover:bg-(--tone)/20 focus-visible:ring-3 focus-visible:ring-ring/60"
              >
                <TrashIcon aria-hidden className="size-4" />
                {t("removeConfirm")}
              </button>
            </div>
          </AlertDialog.Popup>
        </AlertDialog.Portal>
      </AlertDialog.Root>
    </div>
  );
}
