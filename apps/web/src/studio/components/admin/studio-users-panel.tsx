"use client";

import { SendIcon, UsersIcon } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useId } from "react";
import type { IssuedLink } from "@/components/admin/link-dialog";
import { LAB_ROLES, useInviteUser } from "@/components/admin/use-invite-user";
import { authErrorOf, useLabUsers } from "@/components/admin/use-lab-users";
import { usePasswordLink } from "@/components/admin/use-password-link";
import { UserActionsMenu } from "@/components/admin/user-actions-menu";
import { useCurrentUser } from "@/components/app/current-user";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { authErrorKey } from "@/lib/auth-client";
import { cn } from "@/lib/utils";
import { STUDIO_INPUT, StudioInput } from "@/studio/components/auth/fields";
import { FormAlert } from "@/studio/components/auth/form-alert";
import { ShimmerButton } from "@/studio/components/effects/shimmer-button";
import { LoadingStatus, ShimmerSkeleton } from "@/studio/components/effects/shimmer-skeleton";
import { StudioSection, TonePill } from "@/studio/components/profile/studio-section";
import { StudioAvatar } from "@/studio/components/shell/user-card";
import { StudioStatePanel } from "@/studio/components/studio-state-panel";

function InviteForm({ onIssued }: { onIssued: (link: IssuedLink) => void }) {
  const t = useTranslations("admin.invite");
  const tr = useTranslations("roles");
  const ids = useId();
  const { role, setRole, error, pending, onSubmit } = useInviteUser(onIssued);

  return (
    <form onSubmit={onSubmit} className="grid gap-4">
      <FormAlert message={error} />
      <div className="grid gap-2">
        <Label htmlFor={`${ids}-name`}>{t("name")}</Label>
        <StudioInput id={`${ids}-name`} name="name" required maxLength={200} autoComplete="off" />
      </div>
      <div className="grid gap-2">
        <Label htmlFor={`${ids}-email`}>{t("email")}</Label>
        <StudioInput
          id={`${ids}-email`}
          name="email"
          type="email"
          required
          maxLength={320}
          autoComplete="off"
        />
      </div>
      <div className="grid gap-2">
        <Label id={`${ids}-role`}>{t("role")}</Label>
        <Select
          items={Object.fromEntries(LAB_ROLES.map((value) => [value, tr(value)]))}
          value={role}
          onValueChange={setRole}
        >
          <SelectTrigger className={cn(STUDIO_INPUT, "w-full")} aria-labelledby={`${ids}-role`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {LAB_ROLES.map((value) => (
              <SelectItem key={value} value={value}>
                {tr(value)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <ShimmerButton type="submit" disabled={pending}>
        <SendIcon aria-hidden />
        {pending ? t("sending") : t("submit")}
      </ShimmerButton>
    </form>
  );
}

/** Studio users and invites: the lab's accounts with their row actions, and the invite form. */
export function StudioUsersPanel({ onIssued }: { onIssued: (link: IssuedLink) => void }) {
  const t = useTranslations("admin");
  const te = useTranslations("auth.errors");
  const tCommon = useTranslations("common");
  const tr = useTranslations("roles");
  const format = useFormatter();
  const me = useCurrentUser();
  const users = useLabUsers();
  const passwordLink = usePasswordLink(onIssued);

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
      <StudioSection
        id="studio-admin-users"
        title={t("users.title")}
        description={t("users.description")}
      >
        <FormAlert message={passwordLink.error} />
        {users.isPending ? (
          <div className="grid gap-2" aria-busy="true">
            <LoadingStatus label={tCommon("loading")} />
            {Array.from({ length: 4 }, (_, index) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: static placeholders never reorder
              <ShimmerSkeleton key={index} className="h-14 rounded-xl" />
            ))}
          </div>
        ) : users.isError ? (
          <FormAlert message={te(authErrorKey(authErrorOf(users.error)))} />
        ) : users.data.length === 0 ? (
          <StudioStatePanel
            variant="section"
            icon={<UsersIcon aria-hidden />}
            title={t("users.empty")}
            description={t("users.description")}
          />
        ) : (
          <ul className="grid gap-2">
            {users.data.map((user) => {
              const isSelf = user.id === me.id;
              return (
                <li
                  key={user.id}
                  className="flex items-center gap-3 rounded-xl border border-(--studio-glass-border) bg-(--studio-glass) px-3 py-2.5"
                >
                  <StudioAvatar name={user.name} email={user.email} />
                  <div className="grid min-w-0 flex-1 gap-0.5">
                    <p className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-sm font-medium text-foreground">
                      <span className="truncate">{user.name || user.email}</span>
                      {isSelf && <TonePill tone="info">{t("users.you")}</TonePill>}
                      {user.banned && <TonePill tone="danger">{t("users.banned")}</TonePill>}
                    </p>
                    <p className="truncate text-xs text-muted-foreground">
                      {user.email}
                      <span aria-hidden> · </span>
                      {tr(user.role === "admin" ? "admin" : "user")}
                      <span className="hidden sm:inline">
                        <span aria-hidden> · </span>
                        {t("users.joinedOn", {
                          date: format.dateTime(new Date(user.createdAt), { dateStyle: "medium" }),
                        })}
                      </span>
                    </p>
                  </div>
                  <UserActionsMenu
                    user={user}
                    isSelf={isSelf}
                    onPasswordLink={passwordLink.issue}
                    passwordLinkPending={passwordLink.pending}
                    triggerClassName="size-9 rounded-[10px] hover:bg-(--studio-hover)"
                  />
                </li>
              );
            })}
          </ul>
        )}
      </StudioSection>
      <StudioSection
        id="studio-admin-invite"
        title={t("invite.title")}
        description={t("invite.description")}
        className="h-fit"
      >
        <InviteForm onIssued={onIssued} />
      </StudioSection>
    </div>
  );
}
