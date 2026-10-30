"use client";

import { useQueryClient } from "@tanstack/react-query";
import { LogOutIcon, UserRoundIcon } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { authClient } from "@/lib/auth-client";
import { loginPathFor, STUDIO_PREFIX, uiVersionOf } from "@/lib/ui-version";
import { useCurrentUser } from "./current-user";

function initials(name: string, email: string): string {
  const source = name.trim() || email;
  const parts = source.split(/\s+/).filter(Boolean);
  const letters = parts.length > 1 ? `${parts[0]?.[0] ?? ""}${parts[1]?.[0] ?? ""}` : source[0];
  return (letters ?? "?").toUpperCase();
}

/** The profile page of the interface the visitor is in. */
export function profilePathFor(pathname: string): string {
  return uiVersionOf(pathname) === "studio" ? `${STUDIO_PREFIX}/profile` : "/profile";
}

/**
 * The account menu: who is signed in, their profile, and signing out. It works in both
 * interfaces: the profile link and the sign-in page after signing out are the current
 * interface's (`loginPathFor`).
 */
export function UserMenu() {
  const t = useTranslations();
  const user = useCurrentUser();
  const pathname = usePathname();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [signingOut, setSigningOut] = useState(false);

  async function signOut() {
    setSigningOut(true);
    const { error } = await authClient.signOut();
    if (error) {
      setSigningOut(false);
      toast.error(t("nav.signOutFailed"));
      return;
    }
    queryClient.clear();
    router.replace(loginPathFor(pathname));
    router.refresh();
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button variant="ghost" size="sm" aria-label={t("nav.userMenu")} className="gap-2">
            <span
              aria-hidden
              className="flex size-6 items-center justify-center rounded-full bg-primary text-[0.65rem] font-semibold text-primary-foreground"
            >
              {initials(user.name, user.email)}
            </span>
            <span className="hidden max-w-40 truncate lg:inline">{user.name || user.email}</span>
          </Button>
        }
      />
      <DropdownMenuContent align="end" className="w-60">
        <DropdownMenuGroup>
          <DropdownMenuLabel className="grid gap-0.5">
            <span className="truncate text-sm font-medium text-foreground">{user.name}</span>
            <span className="truncate font-normal">{user.email}</span>
            <span className="font-normal">{t(`nav.roles.${user.role}`)}</span>
          </DropdownMenuLabel>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem render={<Link href={profilePathFor(pathname)} />}>
          <UserRoundIcon aria-hidden />
          {t("profile.menu")}
        </DropdownMenuItem>
        <DropdownMenuItem onClick={signOut} disabled={signingOut}>
          <LogOutIcon aria-hidden />
          {t("nav.signOut")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
