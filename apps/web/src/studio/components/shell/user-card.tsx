"use client";

import { ChevronsUpDownIcon, CircleUserIcon, LayoutTemplateIcon, LogOutIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCurrentUser } from "@/components/app/current-user";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { toClassicPath } from "@/lib/ui-version";
import { cn } from "@/lib/utils";
import { useStudioSignOut } from "@/studio/hooks/use-studio-sign-out";
import { STUDIO_PROFILE_PATH } from "@/studio/lib/nav";

function initials(name: string, email: string): string {
  const source = name.trim() || email;
  const parts = source.split(/\s+/).filter(Boolean);
  const letters = parts.length > 1 ? `${parts[0]?.[0] ?? ""}${parts[1]?.[0] ?? ""}` : source[0];
  return (letters ?? "?").toUpperCase();
}

export function StudioAvatar({
  name,
  email,
  className,
}: {
  name: string;
  email: string;
  className?: string;
}) {
  return (
    <span
      aria-hidden
      className={cn(
        "flex size-8 shrink-0 items-center justify-center rounded-full bg-linear-to-br from-(--studio-cta-from) to-(--studio-cta-to) text-[0.7rem] font-semibold text-white shadow-[inset_0_1px_0_0_rgb(255_255_255/0.25)]",
        className,
      )}
    >
      {initials(name, email)}
    </span>
  );
}

/**
 * The signed-in user at the bottom of the sidebar: name and role, with a menu to open their
 * profile, open the page in Classic or sign out (back to the Studio sign-in page). The visible
 * name and role are the button's accessible name (a menu button, so it is announced as one); in
 * the collapsed sidebar they stay for screen readers and show as a tooltip.
 */
export function StudioUserCard({ collapsed = false }: { collapsed?: boolean }) {
  const t = useTranslations("nav");
  const tVersion = useTranslations("shell.version");
  const tProfile = useTranslations("profile");
  const user = useCurrentUser();
  const pathname = usePathname();
  const { signOut, signingOut } = useStudioSignOut();
  const role = t(`roles.${user.role}`);
  const displayName = user.name || user.email;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <button
            type="button"
            title={collapsed ? `${displayName} (${role})` : undefined}
            className="flex w-full min-w-0 items-center gap-3 rounded-xl p-2 text-left outline-none transition-colors hover:bg-(--studio-hover) focus-visible:ring-3 focus-visible:ring-ring/50 aria-expanded:bg-(--studio-hover) group-data-[sidebar=collapsed]/shell:justify-center"
          />
        }
      >
        <StudioAvatar name={user.name} email={user.email} />
        <span className="studio-sidebar-label grid min-w-0 flex-1 group-data-[sidebar=collapsed]/shell:sr-only">
          <span className="truncate text-sm font-medium text-foreground">{displayName}</span>
          <span className="truncate text-xs text-muted-foreground">{role}</span>
        </span>
        <ChevronsUpDownIcon
          aria-hidden
          className="studio-sidebar-label size-4 shrink-0 text-muted-foreground group-data-[sidebar=collapsed]/shell:hidden"
        />
      </DropdownMenuTrigger>
      <DropdownMenuContent
        side={collapsed ? "right" : "top"}
        align="start"
        sideOffset={8}
        className="w-64"
      >
        <DropdownMenuGroup>
          <DropdownMenuLabel className="grid gap-0.5">
            <span className="truncate text-sm font-medium text-foreground">{user.name}</span>
            <span className="truncate font-normal">{user.email}</span>
            <span className="font-normal">{role}</span>
          </DropdownMenuLabel>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem render={<Link href={STUDIO_PROFILE_PATH} />}>
          <CircleUserIcon aria-hidden />
          {tProfile("menu")}
        </DropdownMenuItem>
        <DropdownMenuItem render={<Link href={toClassicPath(pathname)} prefetch={false} />}>
          <LayoutTemplateIcon aria-hidden />
          {tVersion("switchToClassic")}
        </DropdownMenuItem>
        <DropdownMenuItem onClick={signOut} disabled={signingOut}>
          <LogOutIcon aria-hidden />
          {t("signOut")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
